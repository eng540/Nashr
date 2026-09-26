#!/usr/bin/env python3
"""Run the real Nashr Vertical Slice 2 smoke test."""
import argparse
import asyncio
import os
from pathlib import Path

from app.adapters.drafting.gemini import GeminiEditorialDrafter
from app.adapters.extraction.gemini import GeminiBookMapper, GeminiTopicMaterialDiscoverer
from app.adapters.publishing.telegram import TelegramPublisher
from app.application.discover_book import DiscoverBook
from app.application.ingest_pdf import IngestPdf
from app.application.publications import ApproveAndPublish, CreateTelegramDraft
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.storage import LocalFileStorage

REQUIRED_ENV = ("DATABASE_URL", "GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_DESTINATION_ID")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Nashr Vertical Slice 2 live smoke test")
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
        print("== Nashr Vertical Slice 2 / LIVE SMOKE TEST ==")
        source = await IngestPdf(LocalFileStorage(os.getenv("STORAGE_PATH", "./storage"))).execute(session, pdf_path.name, "application/pdf", pdf_path.read_bytes())
        print(f"[1] Source: {source.id}")
        book_map, units = await DiscoverBook(GeminiBookMapper(), GeminiTopicMaterialDiscoverer()).execute(session, source.id)
        print(f"[2] Book: {book_map.title}")
        print(f"    Topics: {len(book_map.topics)}")
        print(f"    Materials: {len(units)}")
        for topic in book_map.topics:
            topic_units = [u for u in units if u.topic_id == topic.id]
            print(f"    Topic {topic.position}: {topic.title} ({len(topic_units)} materials)")
            for unit in topic_units[:3]:
                print(f"      - {unit.title} | kind={unit.kind or 'unknown'} | ref={unit.source_reference or 'UNKNOWN'}")
        if not units:
            raise SystemExit("LIVE SMOKE TEST STOPPED: zero materials were discovered; no publication was attempted.")
        selected = units[0]
        print(f"[3] Selected material: {selected.id} | {selected.title}")
        draft = await CreateTelegramDraft(GeminiEditorialDrafter()).execute(session, selected.id, destination)
        print(f"[4] Draft: {draft.id} (DRAFT; review required)")
        publication = await ApproveAndPublish(TelegramPublisher()).execute(session, draft.id, draft.content)
        print(f"[5] Publication status: {publication.status.value}")
        print(f"    Telegram message ID: {publication.external_id}")
        print(f"    Material: {publication.knowledge_unit_id}")
        print(f"    Source: {source.id}")
        if publication.status.value != "PUBLISHED" or publication.knowledge_unit_id != selected.id:
            raise SystemExit("LIVE SMOKE TEST FAILED: publication or provenance verification failed.")
        print("[6] LIVE SMOKE TEST PASSED: book -> topics -> materials -> draft -> Telegram")


if __name__ == "__main__":
    asyncio.run(run(parse_args().pdf))
