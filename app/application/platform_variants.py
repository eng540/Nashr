"""Derive per-platform content variants from approved generic Artifacts.

Preparation-only: variants are new DRAFT Artifacts whose text is trimmed to the
target platform's verified constraints and whose metadata records the platform,
its source artifact and the constraint snapshot used. No publishing happens
here; external publication remains out of scope. Constraint provenance is
recorded per profile (primary docs vs secondary reporting) so unverified
limits are never presented as verified capability.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.artifacts import persist_generic_artifact
from app.domain.artifacts import Artifact, ArtifactKind, ArtifactStatus
from app.infrastructure.database.models import ArtifactModel

_SOURCE_TYPE = "PLATFORM_VARIANT"
_PROFILE_VERSION = 1


def _utf16_units(text: str) -> int:
    """TikTok measures captions in UTF-16 code units (surrogate pairs count 2)."""
    return len(text.encode("utf-16-le")) // 2


_URL_RE = re.compile(r"https?://\S+")


def _x_weighted_units(text: str) -> int:
    """Approximate X weighted length: URLs count 23, other chars count by UTF-16 units.

    Matches the public twitter-text weighting scheme closely enough for trimming
    preparation; documented as an approximation, not a publishing guarantee.
    """
    total = 0
    cursor = 0
    for match in _URL_RE.finditer(text):
        total += _utf16_units(text[cursor:match.start()])
        total += 23
        cursor = match.end()
    total += _utf16_units(text[cursor:])
    return total


def _chars(text: str) -> int:
    return len(text)


PLATFORM_PROFILES: dict[str, dict[str, Any]] = {
    "tiktok": {
        "label_ar": "تيك توك",
        "max_text": 2200,
        "measure": _utf16_units,
        "measure_name": "utf16_units",
        "media_kinds": ["VIDEO", "IMAGE"],
        "notes_ar": [
            "التعليق حتى 2200 وحدة UTF-16 (موثق من مرجع TikTok Content Posting API).",
            "الحسابات غير المدققة لدى TikTok تقتصر على النشر الخاص (SELF_ONLY) حتى اجتياز المراجعة.",
        ],
        "provenance": "primary:developers.tiktok.com/content-posting-api (verified 2026-11-23)",
    },
    "instagram": {
        "label_ar": "إنستقرام",
        "max_text": 2200,
        "measure": _chars,
        "measure_name": "chars",
        "media_kinds": ["IMAGE", "VIDEO"],
        "notes_ar": [
            "التعليق حتى 2200 حرف و30 وسمًا و20 إشارة (نقلًا عن مرجع Meta لنقطة ig-user/media؛ الصفحة الرسمية لم تُجلب مباشرة).",
            "النشر عبر واجهة Graph API يتطلب حسابًا احترافيًا وتدفق حاوية ثم نشر.",
        ],
        "provenance": "secondary:meta ig-user/media reference as quoted by postnext.io/cleartexteditor.com (2026-11-23)",
    },
    "x": {
        "label_ar": "إكس",
        "max_text": 280,
        "measure": _x_weighted_units,
        "measure_name": "x_weighted",
        "media_kinds": ["TEXT", "IMAGE", "VIDEO"],
        "notes_ar": [
            "المنشور 280 حرفًا موزونًا للحسابات غير المدفوعة (الروابط تُحسب 23)؛ القياس هنا تقريبي بغرض التجهيز.",
            "حدود الكتابة للخطة المجانية غير مؤكدة من مصدر رسمي حتى الآن.",
        ],
        "provenance": "secondary:tweetapi.com create-post ref + twitter-text weighting docs (2026-11-23); official docs.x.com unreachable",
    },
}


def _variant_contract(kind: str, mime_type: str | None, platform: str, max_chars: int | None) -> dict:
    definition: dict[str, Any] = {
        "artifact_kind": kind,
        "mime_type": mime_type,
        "content_mode": "INLINE" if kind in {"TEXT", "POST"} else "STORAGE_URI",
        "required_metadata_fields": ["source_type", "platform", "source_artifact_id"],
        "max_content_chars": max_chars if kind in {"TEXT", "POST"} else None,
    }
    return {
        "output_contract": {
            "contract_id": str(uuid4()),
            "version_id": str(uuid4()),
            "key": f"PLATFORM_VARIANT_{platform.upper()}",
            "version": _PROFILE_VERSION,
            "definition": definition,
        }
    }


def _trim_to_limit(text: str, profile: dict[str, Any]) -> tuple[str, bool]:
    measure = profile["measure"]
    limit = profile["max_text"]
    if limit is None or measure(text) <= limit:
        return text, False
    trimmed = text
    while trimmed and measure(trimmed) > limit:
        # Remove roughly the overflow plus a small margin to converge quickly.
        overflow = measure(trimmed) - limit
        trimmed = trimmed[: max(0, len(trimmed) - max(overflow, 1))]
    return trimmed.rstrip(), True


class DerivePlatformVariant:
    """Create or refresh a DRAFT platform-variant Artifact from an APPROVED Artifact."""

    async def execute(
        self,
        session: AsyncSession,
        *,
        artifact_id: UUID,
        platform: str,
    ) -> Artifact:
        key = (platform or "").strip().lower()
        profile = PLATFORM_PROFILES.get(key)
        if profile is None:
            raise ValueError("منصة غير مدعومة للتجهيز حاليًا: tiktok أو instagram أو x.")
        row = (
            await session.execute(select(ArtifactModel).where(ArtifactModel.id == artifact_id))
        ).scalar_one_or_none()
        if row is None:
            raise LookupError("المخرج المصدر غير موجود.")
        if row.kind == "POST":
            raise ValueError("اشتقاق النسخ من منشورات Post يأتي في خطوة لاحقة؛ استخدم المخرجات العامة حاليًا.")
        if row.review_status != "APPROVED":
            raise ValueError("لا يمكن اشتقاق نسخة منصة إلا من مخرج معتمد.")
        kind = ArtifactKind(row.kind)
        if kind.value not in profile["media_kinds"] and kind.value != "TEXT":
            raise ValueError(f"نوع المخرج {kind.value} لا يناسب منصة {profile['label_ar']} حسب القيود الموثقة.")

        base_content: str | None = row.content
        if base_content is None and row.storage_uri is not None:
            # Media variant: caption lives in metadata for media-bank uploads.
            base_content = str((row.artifact_metadata or {}).get("caption") or "")
        trimmed_content, was_trimmed = _trim_to_limit(base_content or "", profile)
        now = datetime.now(timezone.utc)
        metadata = {
            "source_type": _SOURCE_TYPE,
            "platform": key,
            "platform_label_ar": profile["label_ar"],
            "caption": trimmed_content,
            "source_artifact_id": str(row.id),
            "profile_version": _PROFILE_VERSION,
            "constraints": {
                "max_text": profile["max_text"],
                "measure": profile["measure_name"],
                "measured_length": profile["measure"](trimmed_content),
                "trimmed": was_trimmed,
                "provenance": profile["provenance"],
            },
            "notes_ar": profile["notes_ar"],
        }

        existing = (
            await session.execute(
                select(ArtifactModel).where(
                    ArtifactModel.output_contract_key == f"PLATFORM_VARIANT_{key.upper()}",
                    ArtifactModel.review_status == "DRAFT",
                )
            )
        ).scalars().all()
        for candidate in existing:
            meta = candidate.artifact_metadata or {}
            if meta.get("source_artifact_id") == str(row.id):
                candidate.content = trimmed_content or None
                candidate.artifact_metadata = metadata
                candidate.updated_at = now
                await session.commit()
                refreshed = await session.get(ArtifactModel, candidate.id)
                return _row_to_artifact(refreshed)

        content_mode_inline = kind.value in {"TEXT"}
        artifact = Artifact(
            id=uuid4(),
            source_knowledge_unit_id=row.source_knowledge_unit_id,
            kind=kind,
            content=trimmed_content if content_mode_inline else None,
            status=ArtifactStatus.AVAILABLE.value,
            created_at=now,
            updated_at=now,
            storage_uri=None if content_mode_inline else row.storage_uri,
            mime_type=row.mime_type,
            metadata=metadata,
        )
        # Code-point cap on TEXT variants as an edit-time guard; the derivation
        # already applied the platform's own measure (utf16/weighted), which can
        # differ slightly from len() for emoji-heavy text or links on X.
        max_chars = profile["max_text"] if content_mode_inline else None
        saved = await persist_generic_artifact(
            session, artifact, resolved_context=_variant_contract(kind.value, row.mime_type, key, max_chars)
        )
        await session.commit()
        return saved


def _row_to_artifact(row: ArtifactModel) -> Artifact:
    return Artifact(
        id=row.id,
        source_knowledge_unit_id=row.source_knowledge_unit_id,
        kind=ArtifactKind(row.kind),
        content=row.content,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        storage_uri=row.storage_uri,
        mime_type=row.mime_type,
        output_contract_key=row.output_contract_key,
        output_contract_version=row.output_contract_version,
        resolved_context=row.resolved_context,
        metadata=row.artifact_metadata or {},
    )
