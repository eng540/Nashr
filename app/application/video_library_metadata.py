"""Restore source material separately from platform publication copy.

Only existing videos are enriched. No media, review states, publications or
schedules are created or changed. The original upload caption is retained.
"""
from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import ArtifactModel

TEXT_FIELDS = ("title", "source_file", "source_original", "tiktok_text",
               "telegram_caption", "catalog_caption_original")


def validate_entries(entries: list[dict]) -> None:
    if not entries or len(entries) > 104:
        raise ValueError("Expected 1 to 104 video entries.")
    ids = set()
    filenames = set()
    for entry in entries:
        uid = UUID(entry["artifact_id"])
        filename = entry["filename"]
        if uid in ids or filename in filenames:
            raise ValueError("Duplicate video identity.")
        ids.add(uid)
        filenames.add(filename)
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+\.mp4", filename):
            raise ValueError("Invalid video filename.")
        if any(not isinstance(entry.get(k), str) or not entry[k].strip() for k in TEXT_FIELDS if k != "source_file"):
            raise ValueError("Source and platform text fields are required.")
        if entry.get("source_file") is not None and not isinstance(entry["source_file"], str):
            raise ValueError("Source filename must be text when known.")
        if any(len(entry[k]) > 100000 for k in TEXT_FIELDS if isinstance(entry.get(k), str)):
            raise ValueError("Video text field is too long.")
        if len(entry["title"]) > 500 or len(entry["telegram_caption"]) > 1024:
            raise ValueError("Title or Telegram caption exceeds its limit.")
        curated = entry.get("review_notes")
        if curated is not None and (not isinstance(curated, list) or len(curated) > 100 or any(not isinstance(n, str) or len(n) > 10000 for n in curated)):
            raise ValueError("Curated review notes must be a bounded text list.")
        notes = entry.get("editorial_notes")
        if not isinstance(notes, list) or any(not isinstance(n, str) or len(n) > 100000 for n in notes):
            raise ValueError("Editorial notes must be a text list.")


async def restore_video_metadata(session: AsyncSession, entries: list[dict]) -> dict:
    validate_entries(entries)
    ids = [UUID(e["artifact_id"]) for e in entries]
    rows = (await session.execute(select(ArtifactModel).where(ArtifactModel.id.in_(ids)).with_for_update())).scalars().all()
    by_id = {str(row.id): row for row in rows}
    # Validate the whole batch before changing a row, including owner-selected
    # filename-to-id matching. Never use title similarity to select a video.
    for entry in entries:
        row = by_id.get(entry["artifact_id"])
        if row is None or row.kind != "VIDEO":
            raise ValueError("A selected video is missing.")
        filename = (row.artifact_metadata or {}).get("original_filename", "")
        if re.sub(r"^\d+-", "", filename) != entry["filename"]:
            raise ValueError("Video id and original filename do not match.")
    updated = []
    skipped = []
    for entry in entries:
        row = by_id[entry["artifact_id"]]
        metadata = dict(row.artifact_metadata or {})
        archive = {k: entry[k] for k in TEXT_FIELDS}
        archive["editorial_notes"] = entry["editorial_notes"]
        previous = metadata.get("video_library") or {}
        if "review_notes" in entry:
            archive["review_notes"] = entry["review_notes"]
        elif isinstance(previous, dict) and "review_notes" in previous:
            archive["review_notes"] = previous["review_notes"]
        archive["version"] = 1
        if metadata.get("video_library") == archive:
            skipped.append(str(row.id))
            continue
        metadata["video_library"] = archive
        metadata["title"] = entry["title"]
        # Publication copy stays as-is, especially on approved/published rows.
        # A separately reviewed platform draft may use the restored copy later.
        row.artifact_metadata = metadata
        updated.append(str(row.id))
    await session.commit()
    return {"updated": updated, "skipped": skipped, "published": False}
