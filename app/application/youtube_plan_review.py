"""Private YouTube review snapshots. No storage/network reads or upload records."""

from datetime import datetime, timezone
from sqlalchemy import select
from app.infrastructure.database.models import (
    ArtifactModel,
    PlatformCopyModel,
    PlatformMediaInspectionModel,
    YouTubeReviewDraftModel,
)
from app.application.central_platform_copies import evaluate
from app.application.distribution_readiness import source_fingerprint
from app.application.media_inspection_history import describe
from app.application.instagram_plan_review import fingerprint, timing_intent
from app.adapters.publishing.youtube import CHANNEL
import re


def choices(
    channel_id=None,
    privacy=None,
    made_for_kids=None,
    contains_synthetic_media=None,
    rights_confirmed=None,
    category_id=None,
):
    if channel_id is not None and not CHANNEL.fullmatch(channel_id):
        raise ValueError(
            "معرف قناة YouTube غير صالح. لا يثبت إدخاله ملكية القناة أو ربطها."
        )
    if privacy is not None and privacy not in {"private", "unlisted", "public"}:
        raise ValueError("اختر خصوصية معروفة صراحةً.")
    if any(
        v is not None and type(v) is not bool
        for v in [made_for_kids, contains_synthetic_media, rights_confirmed]
    ):
        raise ValueError("اختر إقرارات الجمهور والمحتوى والحقوق صراحةً.")
    if category_id is not None and not re.fullmatch(r"[0-9]{1,10}", category_id):
        raise ValueError("معرف الفئة غير صالح؛ يلزم التحقق من إتاحتها للقناة لاحقاً.")
    return dict(
        channel_id=channel_id,
        privacy=privacy,
        made_for_kids=made_for_kids,
        contains_synthetic_media=contains_synthetic_media,
        rights_confirmed=rights_confirmed,
        category_id=category_id,
    )


async def preview(session, uid, *, planned_at=None, timezone_name=None, **values):
    intent = choices(**values)
    row = await session.get(ArtifactModel, uid, populate_existing=True)
    copy = await session.get(
        PlatformCopyModel, (uid, "youtube"), populate_existing=True
    )
    if row is None or copy is None or row.kind != "VIDEO":
        raise ValueError("اختر فيديو أصلياً ونسخة YouTube محفوظة أولاً.")
    fields = evaluate(row, copy)
    blockers = list(fields["blockers"])
    blockers.append(
        "لم تُربط قناة Google مختارة أو تُتحقق صلاحياتها؛ معرف القناة المقترح ليس ربطاً."
    )
    required = {
        "channel_id": "القناة المقترحة",
        "privacy": "الخصوصية",
        "made_for_kids": "الجمهور الموجّه للأطفال",
        "contains_synthetic_media": "الإفصاح عن المحتوى المعدّل أو الاصطناعي",
        "category_id": "فئة الفيديو",
    }
    for key, label in required.items():
        if intent[key] is None:
            blockers.append("يلزم اختيار " + label + " صراحةً.")
    if intent["rights_confirmed"] is not True:
        blockers.append("يلزم إقرار امتلاك حقوق الفيديو والصوت أو إذن استخدامها.")
    records = (
        (
            await session.execute(
                select(PlatformMediaInspectionModel)
                .where(
                    PlatformMediaInspectionModel.artifact_id == uid,
                    PlatformMediaInspectionModel.platform == "youtube",
                )
                .order_by(
                    PlatformMediaInspectionModel.created_at.desc(),
                    PlatformMediaInspectionModel.id.desc(),
                )
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    inspection = None
    for record in records:
        detail = describe(row, copy, record)
        if record.selected and not detail["stale"]:
            inspection = {
                "id": str(record.id),
                "sha256": record.sha256,
                "measurements": record.result.get("measurements", {}),
                "created_at": record.created_at.isoformat(),
            }
            blockers.extend(record.result.get("blockers", []))
            break
    if not inspection:
        blockers.append("لم يُحفظ فحص حديث للوسيط المحدد. احفظه من سجل الفحوص أولاً.")
    if copy.selected_media_id is not None or row.mime_type not in {
        "video/mp4",
        "video/quicktime",
    }:
        blockers.append(
            "مسار الرفع الجاري تطويره يقتصر على أصل MP4 أو MOV، دون تبديل وسيط."
        )
    payload = dict(
        artifact_id=str(uid),
        source_fingerprint=source_fingerprint(row),
        copy_version=copy.version,
        fields=copy.fields,
        intent=intent,
        timing_intent=timing_intent(planned_at, timezone_name),
        inspection=inspection,
        blockers=list(dict.fromkeys(blockers)),
        execution_enabled=False,
        upload_created=False,
        channel_verified=False,
        outgoing_approval_recorded=False,
    )
    complete = (
        all(intent[k] is not None for k in required)
        and intent["rights_confirmed"] is True
    )
    return {
        **payload,
        "preview_hash": fingerprint(payload),
        "can_save_draft": complete
        and row.review_status == "APPROVED"
        and row.status == "AVAILABLE"
        and not fields["source_stale"],
        "caveat": "تجهيز خاص فقط، دون قراءة ملف أو اتصال بـGoogle. لا رفع أو حجز موعد أو موافقة نشر من هذه المسودة.",
    }


async def save_draft(session, uid, *, preview_hash, **values):
    await session.execute(
        select(ArtifactModel).where(ArtifactModel.id == uid).with_for_update()
    )
    await session.execute(
        select(PlatformCopyModel)
        .where(
            PlatformCopyModel.artifact_id == uid,
            PlatformCopyModel.platform == "youtube",
        )
        .with_for_update()
    )
    current = await preview(session, uid, **values)
    if current["preview_hash"] != preview_hash:
        raise ValueError(
            "تغير الأصل أو النسخة أو الفحص أو خيارات المراجعة. اعرض المعاينة مجدداً."
        )
    if not current["can_save_draft"]:
        raise ValueError("أكمل الخيارات الصريحة واعتماد الأصل قبل حفظ مسودة المراجعة.")
    if current["timing_intent"] and datetime.fromisoformat(
        current["timing_intent"]["planned_at"]
    ) <= datetime.now(timezone.utc):
        raise ValueError("الموعد المقترح مضى؛ اختر وقتاً مستقبلياً للمراجعة فقط.")
    existing = (
        (
            await session.execute(
                select(YouTubeReviewDraftModel).where(
                    YouTubeReviewDraftModel.artifact_id == uid,
                    YouTubeReviewDraftModel.snapshot_hash == preview_hash,
                    YouTubeReviewDraftModel.state == "DRAFT",
                )
            )
        )
        .scalars()
        .first()
    )
    if existing:
        return await describe_draft(session, existing)
    record = YouTubeReviewDraftModel(
        artifact_id=uid, snapshot_hash=preview_hash, snapshot=current, state="DRAFT"
    )
    session.add(record)
    await session.commit()
    return await describe_draft(session, record)


async def describe_draft(session, record):
    timing = record.snapshot.get("timing_intent")
    current = await preview(
        session,
        record.artifact_id,
        **record.snapshot["intent"],
        planned_at=datetime.fromisoformat(timing["local_time"]) if timing else None,
        timezone_name=timing["timezone"] if timing else None,
    )
    return dict(
        id=str(record.id),
        state=record.state,
        created_at=record.created_at.isoformat(),
        snapshot=record.snapshot,
        stale=current["preview_hash"] != record.snapshot_hash,
        execution_enabled=False,
        timing_elapsed=bool(
            timing
            and datetime.fromisoformat(timing["planned_at"])
            <= datetime.now(timezone.utc)
        ),
    )


async def list_drafts(session, uid):
    records = (
        (
            await session.execute(
                select(YouTubeReviewDraftModel)
                .where(YouTubeReviewDraftModel.artifact_id == uid)
                .order_by(YouTubeReviewDraftModel.created_at.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    return {
        "items": [await describe_draft(session, r) for r in records],
        "execution_enabled": False,
    }


async def cancel_draft(session, uid, draft_id):
    record = (
        await session.execute(
            select(YouTubeReviewDraftModel)
            .where(
                YouTubeReviewDraftModel.id == draft_id,
                YouTubeReviewDraftModel.artifact_id == uid,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if record is None or record.state not in {"DRAFT", "CANCELLED"}:
        raise ValueError("مسودة مراجعة غير موجودة أو لا يمكن إلغاؤها محلياً.")
    record.state = "CANCELLED"
    await session.commit()
    return {
        "id": str(record.id),
        "state": record.state,
        "remote_changed": False,
        "execution_enabled": False,
    }
