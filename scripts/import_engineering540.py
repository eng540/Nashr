#!/usr/bin/env python3
"""Import the Engineering540 content collections into the Nashr artifact bank.

Two independent collections, both entering as reviewable DRAFT artifacts:

- Topics: content/P*/P#-###.md files (Arabic frontmatter + markdown body)
  become inline TEXT artifacts pinned to the ENGINEERING540_TOPIC_IMPORT
  output contract, each with its own Source/KnowledgeUnit provenance record.
- Designs: designs/batch-*/d*.webp files listed in designs/index.csv are
  ingested through the sanctioned media-bank path (IngestReadyMedia), which
  stores bytes in private artifact storage and registers a DRAFT review item.
  The publish caption comes from the index's TikTok caption column.

Everything is idempotent: an artifact whose metadata carries an import_key
that already exists in the bank is skipped. Nothing is approved, scheduled,
or published by this script; review state stays DRAFT for a human.

Usage:
    DATABASE_URL=... ARTIFACT_STORAGE_*=... \
        python scripts/import_engineering540.py --root /path/to/engineering540 \
        [--only topics|designs] [--limit N] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from app.infrastructure.database.session import SessionFactory

from app.application.engineering540_import import (
    import_topics, import_designs, parse_frontmatter, existing_import_keys, _design_caption,
)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Engineering540 topics and designs into Nashr as DRAFT artifacts.")
    parser.add_argument("--root", type=Path, required=True, help="Path to the Engineering540 repository checkout")
    parser.add_argument("--only", choices=("topics", "designs"), default=None, help="Import only one collection")
    parser.add_argument("--limit", type=int, default=None, help="Maximum NEW items imported per collection in this run; already-imported items are skipped first and do not count toward the limit, so a re-run with --limit 10 imports the next 10")
    parser.add_argument("--dry-run", action="store_true", help="Parse and count without writing to the database")
    return parser.parse_args()


async def run() -> None:
    args = parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"Root path is not a directory: {root}")
    if not os.getenv("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is required.")

    async with SessionFactory() as session:
        if args.only in (None, "topics"):
            result = await import_topics(session, root, args.limit, args.dry_run)
            print(
                f"TOPICS: imported={len(result['imported'])} "
                f"skipped={len(result['skipped'])} failed={len(result['failed'])}"
            )
            for line in result["failed"]:
                print(f"  FAILED {line}")
        if args.only in (None, "designs"):
            result = await import_designs(session, root, args.limit, args.dry_run)
            print(
                f"DESIGNS: imported={len(result['imported'])} "
                f"skipped={len(result['skipped'])} failed={len(result['failed'])}"
            )
            for line in result["failed"]:
                print(f"  FAILED {line}")


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
