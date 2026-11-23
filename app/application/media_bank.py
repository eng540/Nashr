"""Ingest ready-made media (videos/images) into the generic Artifact bank.

The media bank accepts finished media produced outside Nashr generation, stores
bytes in private artifact storage, and registers the upload as a reviewable
generic Artifact so it flows through the existing DRAFT -> APPROVED review and
publication draft routes. No generation provider is involved.
"""
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.artifacts import persist_generic_artifact
from app.domain.artifacts import Artifact, ArtifactKind, ArtifactStatus
from app.infrastructure.artifact_storage import S3ArtifactStorage
from app.infrastructure.database.models import KnowledgeUnitModel, SourceModel

_ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "video/mp4",
    "audio/mpeg", "audio/mp4", "audio/ogg", "image/gif", "video/webm", "application/x-tgsticker"}
MEDIA_KINDS = frozenset({"IMAGE", "VIDEO", "AUDIO", "DOCUMENT", "ANIMATION", "VOICE", "VIDEO_NOTE", "STICKER"})
MODE_MIMES = {
    "IMAGE": {"image/jpeg", "image/png", "image/webp"}, "VIDEO": {"video/mp4"},
    "AUDIO": {"audio/mpeg", "audio/mp4"}, "VOICE": {"audio/mpeg", "audio/mp4", "audio/ogg"},
    "ANIMATION": {"image/gif", "video/mp4"}, "VIDEO_NOTE": {"video/mp4"},
    "STICKER": {"image/webp", "video/webm", "application/x-tgsticker"},
}


def _matches_signature(mime_type: str, data: bytes) -> bool:
    """Verify the upload bytes match the declared media type."""
    if mime_type == "image/jpeg":
        return data[:3] == b"\xff\xd8\xff"
    if mime_type == "image/png":
        return data[:8] == b"\x89PNG\r\n\x1a\n"
    if mime_type == "image/webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if mime_type == "image/gif":
        return data[:6] in {b"GIF87a", b"GIF89a"}
    if mime_type == "audio/mpeg":
        return data[:3] == b"ID3" or (len(data) >= 2 and data[0] == 255 and data[1] & 224 == 224)
    if mime_type == "audio/ogg":
        return data[:4] == b"OggS" and b"OpusHead" in data[:256]
    if mime_type == "video/webm":
        return data[:4] == b"\x1aE\xdf\xa3"
    if mime_type == "application/x-tgsticker":
        return data[:2] == b"\x1f\x8b"
    if mime_type in {"video/mp4", "audio/mp4"}:
        return len(data) > 12 and data[4:8] == b"ftyp"
    return False
_DEFAULT_MAX_BYTES = 100 * 1024 * 1024
_SOURCE_TYPE = "MEDIA_BANK_UPLOAD"


def _media_bank_contract(kind: str, mime_type: str) -> dict:
    return {
        "output_contract": {
            "contract_id": str(uuid4()),
            "version_id": str(uuid4()),
            "key": "MEDIA_BANK_UPLOAD",
            "version": 1,
            "definition": {
                "artifact_kind": kind,
                "mime_type": mime_type,
                "content_mode": "STORAGE_URI",
                "required_metadata_fields": ["source_type"],
                "max_content_chars": None,
            },
        }
    }


class IngestReadyMedia:
    """Store an uploaded media file and register it as a reviewable Artifact."""

    def __init__(self, storage: S3ArtifactStorage | None = None, max_bytes: int | None = None) -> None:
        self.storage = storage
        self.max_bytes = max_bytes or int(os.getenv("NASHR_MEDIA_UPLOAD_MAX_BYTES", str(_DEFAULT_MAX_BYTES)))

    async def execute(
        self,
        session: AsyncSession,
        *,
        filename: str,
        content_type: str,
        data: bytes,
        caption: str | None = None,
        storage_key: str | None = None,
        metadata: dict | None = None,
        media_kind: str | None = None,
    ) -> Artifact:
        if not isinstance(data, (bytes, bytearray)) or not data:
            raise ValueError("Uploaded media is empty.")
        payload = bytes(data)
        if len(payload) > self.max_bytes:
            raise ValueError("Uploaded media exceeds the maximum size of %d bytes." % self.max_bytes)
        mime_type = (content_type or "").strip().lower()
        mime_type = {"audio/x-m4a": "audio/mp4", "audio/mp3": "audio/mpeg", "application/gzip": "application/x-tgsticker"}.get(mime_type, mime_type)
        if media_kind is None:
            # Keep the legacy auto mode restricted to known images and MP4.
            if mime_type not in {"image/jpeg", "image/png", "image/webp", "video/mp4"}:
                raise ValueError("Unsupported media type; select an explicit Telegram media kind.")
            media_kind = "IMAGE" if mime_type.startswith("image/") else "VIDEO"
        if media_kind not in MEDIA_KINDS:
            raise ValueError("Unsupported media kind.")
        if media_kind == "DOCUMENT":
            # Documents are stored and downloaded as attachments, never executed.
            mime_type = "application/octet-stream"
        elif mime_type not in MODE_MIMES[media_kind] or not _matches_signature(mime_type, payload):
            raise ValueError("Uploaded file content or MIME does not match its selected media kind.")
        from app.domain.telegram_media import validate_special_media
        validate_special_media(media_kind, mime_type, payload)
        from app.domain.telegram_media import media_request
        media_request(media_kind, mime_type, payload, filename)
        kind = ArtifactKind(media_kind)
        clean_filename = (filename or "").strip() or "media"
        clean_caption = (caption or "").strip() or clean_filename

        storage = self.storage or S3ArtifactStorage.from_environment()
        artifact_id = uuid4()
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", clean_filename).strip("-") or "media"
        # A caller-provided deterministic key makes a retried import idempotent in
        # storage: the retry overwrites the same object instead of leaving orphans.
        storage_uri = await storage.put(
            key=storage_key or f"artifacts/media-bank/{artifact_id}/{safe_name}",
            content=payload,
            content_type=mime_type,
        )

        now = datetime.now(timezone.utc)
        source_id, unit_id = uuid4(), uuid4()
        session.add(
            SourceModel(
                id=source_id,
                filename=clean_filename[:500],
                mime_type=mime_type,
                storage_path=storage_uri,
                size_bytes=len(payload),
                status="STORED",
                content_sha256=hashlib.sha256(payload).hexdigest(),
            )
        )
        session.add(
            KnowledgeUnitModel(
                id=unit_id,
                source_id=source_id,
                position=1,
                title=clean_caption[:500],
                kind="MEDIA_BANK",
                content=clean_caption,
                source_reference=clean_filename[:1000],
            )
        )
        artifact = Artifact(
            id=artifact_id,
            source_knowledge_unit_id=unit_id,
            kind=kind,
            content=None,
            status=ArtifactStatus.AVAILABLE.value,
            created_at=now,
            updated_at=now,
            storage_uri=storage_uri,
            mime_type=mime_type,
            metadata={
                "source_type": _SOURCE_TYPE,
                "original_filename": clean_filename,
                "caption": clean_caption,
                "telegram_media_kind": media_kind,
                **(metadata or {}),
            },
        )
        saved = await persist_generic_artifact(session, artifact, resolved_context=_media_bank_contract(kind.value, mime_type))
        await session.commit()
        return saved
