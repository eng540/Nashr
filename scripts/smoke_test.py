#!/usr/bin/env python3
"""Run the real Nashr Vertical Slice 2 lifecycle smoke test."""
import argparse
import asyncio
import os
from pathlib import Path

from app.adapters.drafting.gemini import GeminiEditorialDrafter
from app.adapters.publishing.telegram import TelegramPublisher
from app.application.discovery_jobs import create_discovery_job, run_discovery_job
from app.application.ingest_pdf import IngestPdf
from app.application.publications import ApproveAndPublish, CreateTelegramDraft
from app.infrastructure.database.models import DiscoveryJobModel, KnowledgeUnitModel, TopicModel
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.storage import LocalFileStorage
from sqlalchemy import select


REQUIRED_ENV = ("DATABASE_URL", "GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_DESTINATION_ID")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Nashr Vertical Slice 2 live lifecycle smoke test")
    parser.add_argument("pdf", type=Path, help="Path to a real PDF file")
    return parser.parse_args()


async def run(pdf_path: Path) -> None:
    missing = [name for name in REQUIRED_ENV if not os.getenv(name)]
    if missing:
        raise SystemExit("Missing required environment variables: " + ", ".join(missing))
    if not pdf_path.is_file() or pdf_path.suffix.lower() != ".pdf":
        raise SystemExit("Smoke test input must be an existing PDF.")

    destination = os.environ["TELEGRAM_DESTINATION_ID"]
    async with SessionFactory() as session:
        print("== Nashr Vertical Slice 2 / LIVE LIFECYCLE SMOKE TEST ==")
        source = await IngestPdf(LocalFileStorage(os.getenv("STORAGE_PATH", "./storage"))).execute(
            session, pdf_path.name, "application/pdf", pdf_path.read_bytes()
        )
        print(f"[1] Source: {source.id}")

        job = await create_discovery_job(session, source.id)
        print(f"[2] Discovery job: {job.id} | status={job.status}")

    await run_discovery_job(job.id)

    async with SessionFactory() as session:
        job = (await session.execute(select(DiscoveryJobModel).where(DiscoveryJobModel.id == job.id))).scalar_one()
        topics = (await session.execute(select(TopicModel).where(TopicModel.source_id == source.id).order_by(TopicModel.position))).scalars().all()
        units = (await session.execute(select(KnowledgeUnitModel).where(KnowledgeUnitModel.source_id == source.id).order_by(KnowledgeUnitModel.position))).scalars().all()

        print(f"[3] Job: {job.status} | stage={job.stage} | topics={job.topics_completed}/{job.topics_total} | materials={job.materials_discovered}")
        for topic in topics:
            topic_units = [u for u in units if u.topic_id == topic.id]
            print(f"    Topic {topic.position}: {topic.title} | status={topic.discovery_status} | materials={len(topic_units)}")
            for unit in topic_units[:3]:
                print(f"      - {unit.title} | kind={unit.kind or 'UNKNOWN'} | ref={unit.source_reference or 'UNKNOWN'}")

        if job.status != "COMPLETED":
            raise SystemExit(f"LIVE SMOKE TEST FAILED: discovery job did not complete: {job.error_message or 'UNKNOWN'}")
        if not units:
            raise SystemExit("LIVE SMOKE TEST STOPPED: zero materials were discovered; no publication was attempted.")

        selected = units[0]
        print(f"[4] Selected material: {selected.id} | {selected.title}")
        draft = await CreateTelegramDraft(GeminiEditorialDrafter()).execute(session, selected.id, destination)
        print(f"[5] Draft: {draft.id} | status={draft.status.value}")

        publication = await ApproveAndPublish(TelegramPublisher()).execute(session, draft.id, draft.content)
        print(f"[6] Publication status: {publication.status.value}")
        print(f"    Telegram message ID: {publication.external_id}")
        print(f"    Material: {publication.knowledge_unit_id}")
        print(f"    Source: {source.id}")

        if publication.status.value != "PUBLISHED" or publication.knowledge_unit_id != selected.id:
            raise SystemExit("LIVE SMOKE TEST FAILED: publication or provenance verification failed.")

        print("[7] LIVE SMOKE TEST PASSED: source -> job -> Gemini -> map -> topics -> materials -> draft -> Telegram")


if __name__ == "__main__":
    asyncio.run(run(parse_args().pdf))
