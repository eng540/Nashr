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

import asyncio
import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.artifacts import persist_generic_artifact
from app.application.media_bank import IngestReadyMedia
from app.domain.artifacts import Artifact, ArtifactKind, ArtifactStatus
from app.infrastructure.database.models import (
    ArtifactModel,
    KnowledgeUnitModel,
    SourceModel,
)
from app.infrastructure.database.session import SessionFactory

TOPIC_SOURCE_TYPE = "ENGINEERING540_TOPIC_IMPORT"
TOPIC_CONTRACT_KEY = "ENGINEERING540_TOPIC_IMPORT"
CAPTION_MAX_CHARS = 1024

TOPIC_CONTRACT = {
    "output_contract": {
        "contract_id": str(uuid4()),
        "version_id": str(uuid4()),
        "key": TOPIC_CONTRACT_KEY,
        "version": 1,
        "definition": {
            "artifact_kind": "TEXT",
            "mime_type": "text/plain",
            "content_mode": "INLINE",
            "required_metadata_fields": ["source_type"],
            "max_content_chars": None,
        },
    }
}


def parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    """Split a markdown file into its simple `key: value` frontmatter and body."""
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, raw
    meta: dict[str, str] = {}
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end = index
            break
        if ":" in lines[index]:
            key, _, value = lines[index].partition(":")
            meta[key.strip()] = value.strip()
    if end is None:
        return {}, raw
    body = "\n".join(lines[end + 1 :]).strip()
    return meta, body


async def existing_import_keys(session: AsyncSession) -> set[str]:
    result = await session.execute(
        select(ArtifactModel.artifact_metadata["import_key"].astext).where(
            ArtifactModel.artifact_metadata["import_key"].astext.isnot(None)
        )
    )
    return {row for row in result.scalars().all() if row}


async def import_topics(
    session: AsyncSession, root: Path, limit: int | None, dry_run: bool
) -> dict[str, list[str]]:
    imported: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    content_root = root / "content"
    files = sorted(content_root.glob("P*/P*-*.md"))
    known_keys = await existing_import_keys(session)
    for path in files:
        raw = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(raw)
        import_key = meta.get("رقم_الموضوع") or path.stem
        if import_key in known_keys:
            skipped.append(import_key)
            continue
        if limit is not None and len(imported) >= limit:
            break
        if dry_run:
            imported.append(import_key)
            continue
        try:
            title = meta.get("العنوان") or import_key
            rel_path = str(path.relative_to(root))
            payload = raw.encode("utf-8")
            source_id, unit_id, artifact_id = uuid4(), uuid4(), uuid4()
            now = datetime.now(timezone.utc)
            session.add(
                SourceModel(
                    id=source_id,
                    filename=path.name[:500],
                    mime_type="text/markdown",
                    storage_path=rel_path,
                    size_bytes=len(payload),
                    status="STORED",
                    content_sha256=hashlib.sha256(payload).hexdigest(),
                    book_title="Engineering540",
                )
            )
            session.add(
                KnowledgeUnitModel(
                    id=unit_id,
                    source_id=source_id,
                    position=1,
                    title=title[:500],
                    kind="ENGINEERING540_TOPIC",
                    content=raw,
                    source_reference=rel_path[:1000],
                )
            )
            artifact = Artifact(
                id=artifact_id,
                source_knowledge_unit_id=unit_id,
                kind=ArtifactKind.TEXT,
                content=body or raw,
                status=ArtifactStatus.AVAILABLE.value,
                created_at=now,
                updated_at=now,
                mime_type="text/plain",
                output_contract_key=TOPIC_CONTRACT_KEY,
                output_contract_version=1,
                resolved_context=dict(TOPIC_CONTRACT),
                metadata={
                    "source_type": TOPIC_SOURCE_TYPE,
                    "import_source": "engineering540",
                    "import_key": import_key,
                    "title": title,
                    "series": meta.get("السلسلة") or None,
                    "content_type": meta.get("النوع") or None,
                    "platforms": meta.get("المنصات") or None,
                    "readiness": meta.get("الجاهزية") or None,
                    "relative_path": rel_path,
                },
            )
            await persist_generic_artifact(session, artifact, resolved_context=dict(TOPIC_CONTRACT))
            await session.commit()
            known_keys.add(import_key)
            imported.append(import_key)
        except Exception as exc:  # noqa: BLE001 - collect and report per item
            await session.rollback()
            failed.append(f"{import_key}: import failed; retry after checking server logs.")
    return {"imported": imported, "skipped": skipped, "failed": failed}


def _design_caption(row: dict[str, str]) -> str:
    """Platform caption copy (truncated to the media-bank 1024-char limit).

    The complete original text always survives in metadata: full_caption holds
    the untruncated TikTok caption and hashtags the full hashtag line.
    """
    caption = (row.get("نص النشر (تيك توك)") or "").strip()
    hashtags = (row.get("الهاشتاقات") or "").strip()
    if hashtags and len(caption) + len(hashtags) + 2 <= CAPTION_MAX_CHARS:
        caption = f"{caption}\n{hashtags}".strip()
    return caption[:CAPTION_MAX_CHARS]


async def import_designs(
    session: AsyncSession, root: Path, limit: int | None, dry_run: bool
) -> dict[str, list[str]]:
    imported: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    index_path = root / "designs" / "index.csv"
    with index_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    known_keys = await existing_import_keys(session)
    ingester = IngestReadyMedia()
    for row in rows:
        rel_file = (row.get("الملف") or "").strip()
        if not rel_file:
            continue
        # import key is the design path relative to designs/, e.g. batch-01/d01.webp
        import_key = rel_file.split("designs/", 1)[-1]
        if import_key in known_keys:
            skipped.append(import_key)
            continue
        if limit is not None and len(imported) >= limit:
            break
        file_path = root / rel_file
        if not file_path.is_file():
            failed.append(f"{import_key}: file missing at {rel_file}")
            continue
        if dry_run:
            imported.append(import_key)
            continue
        try:
            safe_name = import_key.replace("/", "-")
            artifact = await ingester.execute(
                session,
                filename=f"eng540-{safe_name}",
                content_type="image/webp",
                data=file_path.read_bytes(),
                caption=_design_caption(row) or (row.get("عنوان النشر") or import_key),
                # Deterministic key: a retried import overwrites the same object,
                # so an interrupted run never accumulates orphan files in storage.
                storage_key=f"artifacts/media-bank/eng540/{safe_name}",
                metadata={
                    "import_source": "engineering540",
                    "import_key": import_key,
                    "full_caption": (row.get("نص النشر (تيك توك)") or "").strip() or None,
                    "hashtags": (row.get("الهاشتاقات") or "").strip() or None,
                    "caption_truncated": len((row.get("نص النشر (تيك توك)") or "").strip()) + len((row.get("الهاشتاقات") or "").strip()) + 2 > CAPTION_MAX_CHARS,
                    "description": (row.get("الوصف") or "").strip() or None,
                    "publish_title": (row.get("عنوان النشر") or "").strip() or None,
                    "hook": (row.get("الهوك") or "").strip() or None,
                    "series": (row.get("السلسلة/التصنيف") or "").strip() or None,
                    "readiness": (row.get("جاهزية النشر") or "").strip() or None,
                    "dimensions": (row.get("الأبعاد") or "").strip() or None,
                    "relative_path": rel_file,
                },
            )
            known_keys.add(import_key)
            imported.append(import_key)
        except Exception as exc:  # noqa: BLE001 - collect and report per item
            await session.rollback()
            failed.append(f"{import_key}: import failed; retry after checking server logs.")
    return {"imported": imported, "skipped": skipped, "failed": failed}
