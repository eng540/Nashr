#!/usr/bin/env python3
"""Run the real Vertical Slice 1 smoke test."""

import argparse
import asyncio
import os
from pathlib import Path

from app.adapters.drafting.gemini import GeminiEditorialDrafter
from app.adapters.extraction.gemini import GeminiExtractor
from app.adapters.publishing.telegram import TelegramPublisher
from app.application.extract_knowledge import ExtractKnowledge
from app.application.ingest_pdf import IngestPdf
from app.application.publications import ApproveAndPublish, CreateTelegramDraft
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.storage import LocalFileStorage


REQUIRED_ENV = ("DATABASE_URL", "GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_DESTINATION_ID")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Nashr Vertical Slice 1 live smoke test")
    parser.add_argument("pdf", type=Path, help="Path to a real PDF file")
    return parser.parse_args()


async def run(pdf_path: Path) -> None:
    missing = [name for name in REQUIRED_ENV if not os.getenv(name)]
    if missing:
        raise SystemExit("Missing required environment variables: " + ", ".join(missing))
    if not pdf_path.is_file():
        raise SystemExit(f"PDF not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise SystemExit("Smoke test input must have a .pdf extension.")

    destination = os.environ["TELEGRAM_DESTINATION_ID"]
    storage = LocalFileStorage(os.getenv("STORAGE_PATH", "./storage"))
    print("== Nashr Vertical Slice 1 / LIVE SMOKE TEST ==")
    print(f"PDF:         {pdf_path}")
    print(f"Destination: {destination}")
    print(f"Gemini:      {os.getenv('GEMINI_MODEL', 'gemini-3.8-flash')}")

    async with SessionFactory() as session:
        print("[1/6] Ingesting original PDF...")
        source = await IngestPdf(storage).execute(session, pdf_path.name, "application/pdf", pdf_path.read_bytes())
        print(f"      Source: {source.id}")

        print("[2/6] Sending original PDF to Gemini File API for discovery...")
        units = await ExtractKnowledge(GeminiExtractor()).execute(session, source.id)
        print(f"      Materials discovered: {len(units)}")
        for unit in units:
            print(f"      #{unit.position}: {unit.title} | ref={unit.source_reference or 'not returned'}")
        if not units:
            raise SystemExit("LIVE SMOKE TEST STOPPED: Gemini discovered zero materials; nothing can be selected.")

        selected = units[0]
        print(f"[3/6] Selecting material #{selected.position}: {selected.id}")
        draft = await CreateTelegramDraft(GeminiEditorialDrafter()).execute(session, selected.id, destination)
        print(f"      Publication draft: {draft.id}")
        print("      Status: DRAFT (review required before publish)")

        print("[4/6] Approving reviewed draft and publishing to Telegram...")
        publication = await ApproveAndPublish(TelegramPublisher()).execute(session, draft.id, draft.content)

        print("[5/6] Verifying publication ledger and provenance...")
        print(f"      Status:      {publication.status.value}")
        print(f"      External ID: {publication.external_id}")
        print(f"      Material:    {publication.knowledge_unit_id}")
        print(f"      Source:      {source.id}")
        if publication.error_message:
            print(f"      Error:       {publication.error_message}")
        if publication.status.value != "PUBLISHED":
            raise SystemExit("LIVE SMOKE TEST FAILED: publication did not reach PUBLISHED.")
        if publication.knowledge_unit_id != selected.id:
            raise SystemExit("LIVE SMOKE TEST FAILED: publication provenance does not point to selected material.")

        print("[6/6] Provenance verified: publication -> material -> source")
        print("LIVE SMOKE TEST PASSED")


if __name__ == "__main__":
    asyncio.run(run(parse_args().pdf))
