"""Central approval, untouched fallback and an explicit distribution choice.
No providers, media downloads, drafts, schedules or external writes.
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from sqlalchemy import select
from app.infrastructure.database.models import ArtifactModel, DistributionSelectionModel
from app.application.platform_variants import PLATFORM_PROFILES

PLATFORMS = {"telegram": "Telegram", "instagram": "Instagram", "x": "X", "youtube": "YouTube", "facebook": "Facebook", "tiktok": "TikTok"}


def source_fingerprint(row):
    metadata = row.artifact_metadata or {}
    payload = [row.kind, row.content, row.storage_uri, row.mime_type, metadata, row.review_status]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def readiness(row, selection=None):
    meta = row.artifact_metadata or {}
    text = row.content if row.content is not None else str(meta.get("caption") or "")
    selected = {"platforms": selection.platforms, "source_fingerprint": selection.source_fingerprint, "saved_at": selection.saved_at.isoformat(), "execution_authorized": False} if selection else {}
    current = source_fingerprint(row)
    stale = bool(selected and selected.get("source_fingerprint") != current)
    items = []
    for platform, label in PLATFORMS.items():
        blockers = []
        if row.review_status != "APPROVED" or row.status != "AVAILABLE":
            blockers.append("المادة الأصلية غير معتمدة ومتاحة بعد.")
        if meta.get("source_type") == "PLATFORM_VARIANT":
            blockers.append("اختر المادة الأصلية للاعتماد المركزي، لا نسخة منصة مشتقة.")
        if not text.strip():
            blockers.append("لا يوجد نص أصلي أو وصف صالح للاستخدام دون توليد.")
        if row.kind not in {"TEXT", "QUIZ"} and not row.storage_uri:
            blockers.append("ملف الوسيط الأصلي غير متاح.")
        if platform in PLATFORM_PROFILES:
            profile = PLATFORM_PROFILES[platform]
            if row.kind not in profile["media_kinds"]:
                blockers.append("نوع المادة لا يلائم ملف قيود هذه المنصة.")
            if profile["measure"](text) > profile["max_text"]:
                blockers.append("النص الأصلي يتجاوز حد المنصة. لم يُقص؛ يلزم تجهيز نسخة مناسبة.")
            if not profile["provenance"].startswith("primary:"):
                blockers.append("قيود هذه المنصة تعتمد على مراجع ثانوية وتحتاج تحققاً رسمياً قبل اعتبار النسخة جاهزة.")
            if platform == "x":
                blockers.append("قياس X تقريبي ولم تُتحقق صلاحية النسخة النهائية.")
        elif platform == "telegram":
            if row.kind not in {"TEXT", "QUIZ", "IMAGE", "VIDEO", "AUDIO", "DOCUMENT", "ANIMATION", "VOICE", "VIDEO_NOTE", "STICKER"}:
                blockers.append("نوع المادة غير مدعوم في مسار Telegram الحالي.")
            if row.kind == "TEXT" and len(text.encode("utf-16-le")) // 2 > 4096:
                blockers.append("النص يتجاوز4096وحدة؛ الأصل محفوظ دون قص.")
        else:
            blockers.append("ملف متطلبات النسخة لهذه المنصة لم يكتمل التحقق منه بعد.")
        execution = []
        if platform == "telegram":
            if not os.getenv("TELEGRAM_BOT_TOKEN") or not os.getenv("TELEGRAM_DESTINATION_ID"):
                execution.append("ربط Telegram أو وجهته غير مكتمل في إعدادات الخادم.")
            execution.append("يلزم فحص الوسائط والحمولة ومعاينة الوجهة واعتماد موعد التنفيذ في مسار Telegram.")
        else:
            execution.append("موصل النشر الرسمي وصلاحيات الحساب غير متحققين في هذا المسار.")
        items.append({"platform": platform, "label": label, "selected": platform in selected.get("platforms", []),
                      "copy_status": "BLOCKED" if blockers else "ORIGINAL_ELIGIBLE",
                      "copy_blockers": blockers, "execution_status": "NOT_AUTHORIZED", "execution_blockers": execution,
                      "approval": "INHERITED" if row.review_status == "APPROVED" else "PENDING"})
    return {"artifact_id": str(row.id), "source_fingerprint": current, "central_approval": row.review_status,
            "preparation_mode": "UNCHANGED_ORIGINAL", "ai_required": False, "original_text": text,
            "selection_stale": stale, "selection": selected, "targets": items}


async def get_readiness(session, artifact_id):
    row = await session.get(ArtifactModel, artifact_id)
    if row is None or row.kind == "POST":
        raise LookupError("المادة الأصلية غير موجودة في مسار المخرجات.")
    return readiness(row, await session.get(DistributionSelectionModel, artifact_id))


async def save_selection(session, artifact_ids, platforms, fingerprints):
    if len(set(artifact_ids)) != len(artifact_ids) or len(set(platforms)) != len(platforms):
        raise ValueError("القائمة تحتوي معرّفات أو منصات مكررة.")
    if any(platform not in PLATFORMS for platform in platforms):
        raise ValueError("منصة غير معروفة.")
    rows = (await session.execute(select(ArtifactModel).where(ArtifactModel.id.in_(artifact_ids)).order_by(ArtifactModel.id).with_for_update())).scalars().all()
    if len(rows) != len(artifact_ids):
        raise LookupError("بعض المواد غير موجودة، لم يُحفظ أي اختيار.")
    for row in rows:
        if row.kind == "POST" or row.review_status != "APPROVED" or row.status != "AVAILABLE" or (row.artifact_metadata or {}).get("source_type") == "PLATFORM_VARIANT":
            raise ValueError("اختيار التوزيع يخص المواد الأصلية المعتمدة والمتاحة فقط.")
        if fingerprints.get(str(row.id)) != source_fingerprint(row):
            raise ValueError("تغيرت المادة منذ المعاينة. حدّث الجاهزية قبل حفظ الاختيار.")
    selections = {}
    for row in rows:
        selection = await session.get(DistributionSelectionModel, row.id)
        if selection is None:
            selection = DistributionSelectionModel(artifact_id=row.id)
            session.add(selection)
        selection.platforms = platforms
        selection.source_fingerprint = source_fingerprint(row)
        selection.saved_at = datetime.now(timezone.utc)
        selections[row.id] = selection
    await session.commit()
    return {"items": [readiness(row, selections[row.id]) for row in rows], "saved": len(rows), "publications_created": 0, "schedules_created": 0}
