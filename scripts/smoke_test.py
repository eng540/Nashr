#!/usr/bin/env python3
"""Run the real Vertical Slice 1 smoke test.

This intentionally uses the application use-cases directly so the smoke test
covers the same production path as the vertical slice without requiring a
separate test-only endpoint.
"""

import argparse
import asyncio
import os
from pathlib import Path

from app.adapters.extraction.gemini import GeminiExtractor
from app.adapters.publishing.telegram import TelegramPublisher
from app.application.extract_knowledge import ExtractKnowledge
from app.application.ingest_pdf import IngestPdf
from app.application.publications import ApproveAndPublish, CreateTelegramDraft
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.storage import LocalFileStorage


REQUIRED_ENV = (
    "DATABASE_URL",
    "GEMINI_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_DESTINATION_ID",
)


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
        print("[1/5] Ingesting PDF...")
        source = await IngestPdf(storage).execute(
            session,
            pdf_path.name,
            "application/pdf",
            pdf_path.read_bytes(),
        )
        print(f"      Source: {source.id}")

        print("[2/5] Sending PDF to Gemini...")
        units = await ExtractKnowledge(GeminiExtractor()).execute(session, source.id)
        print(f"      Knowledge units: {len(units)}")
        for unit in units:
            print(f"      #{unit.position}: {unit.title}")

        selected = units[0]
        print(f"[3/5] Selecting Knowledge Unit #1: {selected.id}")
        draft = await CreateTelegramDraft().execute(
            session,
            selected.id,
            destination,
        )
        print(f"      Publication draft: {draft.id}")
        print(f"      Status: {draft.status.value}")

        print("[4/5] Publishing to Telegram...")
        publication = await ApproveAndPublish(TelegramPublisher()).execute(
            session,
            draft.id,
        )

        print("[5/5] Verifying publication ledger...")
        print(f"      Status:      {publication.status.value}")
        print(f"      External ID: {publication.external_id}")
        if publication.error_message:
            print(f"      Error:       {publication.error_message}")

        if publication.status.value != "PUBLISHED":
            raise SystemExit("LIVE SMOKE TEST FAILED: publication did not reach PUBLISHED.")

        print("")
        print("LIVE SMOKE TEST PASSED")
        print("Expected result: Telegram message delivered and ledger status = PUBLISHED.")


if __name__ == "__main__":
    asyncio.run(run(parse_args().pdf))
