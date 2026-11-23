"""Derive per-platform content variants from approved Artifacts and Posts.

Preparation-only: variants are new DRAFT Artifacts whose text is trimmed to the
target platform's verified constraints at safe boundaries (sentence first, then
whitespace; URLs and Arabic combining clusters are never split). The original
text is never altered: trimming produces a separate review copy, and metadata
records original length, the trim decision and an explicit needs_review flag so
nothing reads as publish-ready without human review. No publishing happens
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
from app.infrastructure.database.models import ArtifactModel, PostModel

_SOURCE_TYPE = "PLATFORM_VARIANT"
_PROFILE_VERSION = 2


def _utf16_units(text: str) -> int:
    """TikTok measures captions in UTF-16 code units (surrogate pairs count 2)."""
    return len(text.encode("utf-16-le")) // 2


_URL_RE = re.compile(r"https?://\S+")

# Combining marks and joiners that must never start a trimmed suffix: cutting
# before one would split an Arabic vowel mark or an emoji ZWJ sequence from its
# base character.
_COMBINING_RE = re.compile(
    "[\u0300-\u036f\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u200d\u20d0-\u20f0\ufe00-\ufe0f]"
)

_SENTENCE_ENDERS = (".", "!", "?", "؟", "…", "\n")


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

_ADAPTATION_NOTE_AR = "تجهيز طول فقط: قص عند حدود آمنة دون إعادة صياغة أو تكييف أسلوب؛ يلزم مراجعة بشرية قبل أي استخدام."


def _variant_contract(kind: str, mime_type: str | None, platform: str, max_chars: int | None, source_field: str) -> dict:
    definition: dict[str, Any] = {
        "artifact_kind": kind,
        "mime_type": mime_type,
        "content_mode": "INLINE" if kind in {"TEXT", "POST"} else "STORAGE_URI",
        "required_metadata_fields": ["source_type", "platform", source_field],
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


def _hard_cut_index(text: str, limit: int, measure) -> int:
    """Largest prefix length (in code points) whose measure fits the limit,
    never ending inside a URL or just before a combining mark."""
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if measure(text[:mid]) <= limit:
            lo = mid
        else:
            hi = mid - 1
    cut = lo
    for match in _URL_RE.finditer(text):
        if match.start() < cut <= match.end():
            cut = match.start()
    while 0 < cut < len(text) and _COMBINING_RE.match(text[cut]):
        cut -= 1
    return cut


def _trim_to_limit(text: str, profile: dict[str, Any]) -> tuple[str, bool, str]:
    """Trim text to the platform limit at a safe boundary.

    Returns (trimmed_text, was_trimmed, boundary) where boundary is one of
    "none" | "sentence" | "word" | "hard". Meaning preservation strategy: keep
    the longest sentence-boundary prefix within the limit when it retains at
    least half the allowed length; otherwise fall back to the last whitespace;
    a hard character cut is the last resort and is always cluster-safe.
    """
    measure = profile["measure"]
    limit = profile["max_text"]
    if limit is None or measure(text) <= limit:
        return text, False, "none"
    hard = _hard_cut_index(text, limit, measure)
    window = text[:hard]
    url_spans = [(m.start(), m.end()) for m in _URL_RE.finditer(window)]

    def _inside_url(boundary_index: int) -> bool:
        return any(start < boundary_index <= end for start, end in url_spans)

    boundary = -1
    for ender in _SENTENCE_ENDERS:
        pos = len(window)
        while True:
            idx = window.rfind(ender, 0, pos)
            if idx == -1:
                break
            candidate = idx + 1
            if not _inside_url(candidate):
                boundary = max(boundary, candidate)
                break
            pos = idx
    # A URL kept whole is itself a safe boundary, so a fitting link survives the cut.
    for _, end in url_spans:
        boundary = max(boundary, end)
    if boundary >= hard // 2:
        return window[:boundary].rstrip(), True, "sentence"
    ws = max(window.rfind(" "), window.rfind("\n"), window.rfind("\t"))
    if ws > 0:
        return window[:ws].rstrip(), True, "word"
    return window.rstrip(), True, "hard"


def _build_metadata(
    *,
    key: str,
    profile: dict[str, Any],
    source_field: str,
    source_id: str,
    source_kind_ar: str,
    base_content: str,
    trimmed_content: str,
    was_trimmed: bool,
    boundary: str,
) -> dict:
    notes = list(profile["notes_ar"])
    notes.append(_ADAPTATION_NOTE_AR)
    if was_trimmed:
        notes.append("قُصّ النص الأصلي عند حدود جملة أو كلمة مع الحفاظ على الروابط؛ الأصل محفوظ دون تغيير في المصدر.")
    return {
        "source_type": _SOURCE_TYPE,
        "platform": key,
        "platform_label_ar": profile["label_ar"],
        "caption": trimmed_content,
        source_field: source_id,
        "source_kind_ar": source_kind_ar,
        "profile_version": _PROFILE_VERSION,
        "adaptation": "length_only",
        "needs_review": True,
        "constraints": {
            "max_text": profile["max_text"],
            "measure": profile["measure_name"],
            "measured_length": profile["measure"](trimmed_content),
            "original_length": profile["measure"](base_content),
            "trimmed": was_trimmed,
            "trim_boundary": boundary,
            "provenance": profile["provenance"],
        },
        "notes_ar": notes,
    }


async def _refresh_existing(
    session: AsyncSession,
    *,
    contract_key: str,
    source_field: str,
    source_id: str,
    trimmed_content: str,
    content_inline: bool,
    metadata: dict,
    now: datetime,
) -> Artifact | None:
    existing = (
        await session.execute(
            select(ArtifactModel).where(
                ArtifactModel.output_contract_key == contract_key,
                ArtifactModel.review_status == "DRAFT",
            )
        )
    ).scalars().all()
    for candidate in existing:
        meta = candidate.artifact_metadata or {}
        if meta.get(source_field) == source_id:
            candidate.content = trimmed_content if content_inline else None
            candidate.artifact_metadata = metadata
            candidate.updated_at = now
            await session.commit()
            refreshed = await session.get(ArtifactModel, candidate.id)
            return _row_to_artifact(refreshed)
    return None


class DerivePlatformVariant:
    """Create or refresh a DRAFT platform-variant Artifact from an APPROVED Artifact or Post."""

    async def execute(
        self,
        session: AsyncSession,
        *,
        artifact_id: UUID,
        platform: str,
    ) -> Artifact:
        key, profile = _resolve_profile(platform)
        row = (
            await session.execute(select(ArtifactModel).where(ArtifactModel.id == artifact_id))
        ).scalar_one_or_none()
        if row is None:
            raise LookupError("المخرج المصدر غير موجود.")
        if row.kind == "POST":
            raise ValueError("لاشتقاق نسخة من منشور تحريري استخدم مسار اشتقاق المنشورات المخصص.")
        if row.review_status != "APPROVED":
            raise ValueError("لا يمكن اشتقاق نسخة منصة إلا من مخرج معتمد.")
        kind = ArtifactKind(row.kind)
        if kind.value not in profile["media_kinds"] and kind.value != "TEXT":
            raise ValueError(f"نوع المخرج {kind.value} لا يناسب منصة {profile['label_ar']} حسب القيود الموثقة.")

        base_content: str | None = row.content
        if base_content is None and row.storage_uri is not None:
            # Media variant: caption lives in metadata for media-bank uploads.
            base_content = str((row.artifact_metadata or {}).get("caption") or "")
        trimmed_content, was_trimmed, boundary = _trim_to_limit(base_content or "", profile)
        now = datetime.now(timezone.utc)
        metadata = _build_metadata(
            key=key,
            profile=profile,
            source_field="source_artifact_id",
            source_id=str(row.id),
            source_kind_ar="مخرج معتمد",
            base_content=base_content or "",
            trimmed_content=trimmed_content,
            was_trimmed=was_trimmed,
            boundary=boundary,
        )

        contract_key = f"PLATFORM_VARIANT_{key.upper()}"
        refreshed = await _refresh_existing(
            session,
            contract_key=contract_key,
            source_field="source_artifact_id",
            source_id=str(row.id),
            trimmed_content=trimmed_content,
            content_inline=kind.value == "TEXT",
            metadata=metadata,
            now=now,
        )
        if refreshed is not None:
            return refreshed

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
            session,
            artifact,
            resolved_context=_variant_contract(kind.value, row.mime_type, key, max_chars, "source_artifact_id"),
        )
        await session.commit()
        return saved

    async def execute_post(
        self,
        session: AsyncSession,
        *,
        post_id: UUID,
        platform: str,
    ) -> Artifact:
        """Derive a DRAFT TEXT variant from an APPROVED editorial Post.

        The Post itself is never modified; the variant is a separate review
        copy carrying source_post_id provenance.
        """
        key, profile = _resolve_profile(platform)
        row = (
            await session.execute(select(PostModel).where(PostModel.id == post_id))
        ).scalar_one_or_none()
        if row is None:
            raise LookupError("المنشور المصدر غير موجود.")
        if row.status != "APPROVED":
            raise ValueError("لا يمكن اشتقاق نسخة منصة إلا من منشور معتمد.")

        base_content = row.content or ""
        trimmed_content, was_trimmed, boundary = _trim_to_limit(base_content, profile)
        now = datetime.now(timezone.utc)
        metadata = _build_metadata(
            key=key,
            profile=profile,
            source_field="source_post_id",
            source_id=str(row.id),
            source_kind_ar="منشور تحريري معتمد",
            base_content=base_content,
            trimmed_content=trimmed_content,
            was_trimmed=was_trimmed,
            boundary=boundary,
        )

        contract_key = f"PLATFORM_VARIANT_{key.upper()}"
        refreshed = await _refresh_existing(
            session,
            contract_key=contract_key,
            source_field="source_post_id",
            source_id=str(row.id),
            trimmed_content=trimmed_content,
            content_inline=True,
            metadata=metadata,
            now=now,
        )
        if refreshed is not None:
            return refreshed

        artifact = Artifact(
            id=uuid4(),
            source_knowledge_unit_id=row.knowledge_unit_id,
            kind=ArtifactKind.TEXT,
            content=trimmed_content,
            status=ArtifactStatus.AVAILABLE.value,
            created_at=now,
            updated_at=now,
            storage_uri=None,
            mime_type="text/plain",
            metadata=metadata,
        )
        saved = await persist_generic_artifact(
            session,
            artifact,
            resolved_context=_variant_contract("TEXT", "text/plain", key, profile["max_text"], "source_post_id"),
        )
        await session.commit()
        return saved


def _resolve_profile(platform: str) -> tuple[str, dict[str, Any]]:
    key = (platform or "").strip().lower()
    profile = PLATFORM_PROFILES.get(key)
    if profile is None:
        raise ValueError("منصة غير مدعومة للتجهيز حاليًا: tiktok أو instagram أو x.")
    return key, profile


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


async def list_platform_variants(session: AsyncSession, limit: int = 50) -> list[dict[str, Any]]:
    """Read-only listing of platform-variant drafts for the publishing workspace.

    Preparation-only: these drafts are never scheduled or published by any
    automated pipeline. The listing exists so the publishing area can show what
    has been prepared per platform for human review, with the same honest
    metadata recorded at derivation time (length-only adaptation, trim
    decision, review flag, constraint provenance).
    """
    rows = (
        await session.execute(
            select(ArtifactModel)
            .where(ArtifactModel.artifact_metadata["source_type"].astext == _SOURCE_TYPE)
            .order_by(ArtifactModel.created_at.desc(), ArtifactModel.id.desc())
            .limit(limit)
        )
    ).scalars().all()
    items: list[dict[str, Any]] = []
    for row in rows:
        meta = row.artifact_metadata or {}
        constraints = meta.get("constraints") or {}
        text = row.content if row.content is not None else str(meta.get("caption") or "")
        items.append(
            {
                "id": str(row.id),
                "platform": meta.get("platform"),
                "platform_label_ar": meta.get("platform_label_ar"),
                "review_status": row.review_status,
                "excerpt": text[:160],
                "full_length": len(text),
                "adaptation": meta.get("adaptation"),
                "needs_review": bool(meta.get("needs_review", True)),
                "source_kind_ar": meta.get("source_kind_ar"),
                "source_artifact_id": meta.get("source_artifact_id"),
                "source_post_id": meta.get("source_post_id"),
                "manual_publication": meta.get("manual_publication"),
                "constraints": {
                    "max_text": constraints.get("max_text"),
                    "measure": constraints.get("measure"),
                    "measured_length": constraints.get("measured_length"),
                    "original_length": constraints.get("original_length"),
                    "trimmed": constraints.get("trimmed"),
                    "trim_boundary": constraints.get("trim_boundary"),
                    "provenance": constraints.get("provenance"),
                },
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return items
