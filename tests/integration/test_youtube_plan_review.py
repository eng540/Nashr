from datetime import datetime, timezone, timedelta
from uuid import UUID
import pytest
from sqlalchemy import select, func
from app.application import youtube_plan_review as flow
from app.infrastructure.database.models import (
    PlatformCopyModel,
    YouTubeUploadModel,
    YouTubeReviewDraftModel,
    ScheduleModel,
)
from app.infrastructure.database.session import SessionFactory
from tests.integration.test_youtube_execution import seed, CHANNEL
from tests.integration.test_instagram_oauth import config, browser

CHOICES = dict(
    channel_id=CHANNEL,
    privacy="private",
    made_for_kids=False,
    contains_synthetic_media=False,
    rights_confirmed=True,
    category_id="27",
)


@pytest.mark.asyncio
async def test_private_review_exact_content_hash_history_and_no_jobs():
    uid, _ = await seed()
    async with SessionFactory() as s:
        counts = [
            await s.scalar(select(func.count()).select_from(m))
            for m in [YouTubeUploadModel, ScheduleModel]
        ]
        p = await flow.preview(s, uid, **CHOICES)
        assert (
            p["can_save_draft"]
            and p["blockers"]
            and not p["channel_verified"]
            and not p["execution_enabled"]
            and not p["upload_created"]
        )
        d = await flow.save_draft(s, uid, preview_hash=p["preview_hash"], **CHOICES)
        assert (
            not d["stale"]
            and (
                await flow.save_draft(s, uid, preview_hash=p["preview_hash"], **CHOICES)
            )["id"]
            == d["id"]
        )
        assert counts == [
            await s.scalar(select(func.count()).select_from(m))
            for m in [YouTubeUploadModel, ScheduleModel]
        ]
        copy = await s.get(PlatformCopyModel, (uid, "youtube"))
        copy.fields = {**copy.fields, "description": "مراجعة دون تغيير الأصل"}
        await s.commit()
        with pytest.raises(ValueError):
            await flow.save_draft(s, uid, preview_hash=p["preview_hash"], **CHOICES)
        assert (await flow.list_drafts(s, uid))["items"][0]["stale"]
        assert d["snapshot"]["fields"]["description"] != copy.fields["description"]
        await flow.cancel_draft(s, uid, UUID(d["id"]))
        assert (await flow.list_drafts(s, uid))["items"][0]["state"] == "CANCELLED"
        with pytest.raises(ValueError):
            await flow.cancel_draft(
                s, UUID("00000000-0000-0000-0000-000000000000"), UUID(d["id"])
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("privacy", None),
        ("made_for_kids", None),
        ("contains_synthetic_media", None),
        ("rights_confirmed", False),
        ("category_id", None),
        ("channel_id", None),
    ],
)
async def test_explicit_choices_required_for_save(field, value):
    uid, _ = await seed()
    options = {**CHOICES, field: value}
    async with SessionFactory() as s:
        p = await flow.preview(s, uid, **options)
        assert not p["can_save_draft"]
        with pytest.raises(ValueError):
            await flow.save_draft(s, uid, preview_hash=p["preview_hash"], **options)


@pytest.mark.asyncio
async def test_timing_choices_and_cancel_resave():
    uid, _ = await seed()
    at = datetime.now(timezone.utc) + timedelta(days=1)
    async with SessionFactory() as s:
        p = await flow.preview(s, uid, **CHOICES, planned_at=at, timezone_name="UTC")
        with pytest.raises(ValueError):
            await flow.save_draft(
                s,
                uid,
                preview_hash=p["preview_hash"],
                **{**CHOICES, "privacy": "public"},
                planned_at=at,
                timezone_name="UTC",
            )
        d = await flow.save_draft(
            s,
            uid,
            preview_hash=p["preview_hash"],
            **CHOICES,
            planned_at=at,
            timezone_name="UTC",
        )
        await flow.cancel_draft(s, uid, UUID(d["id"]))
        new = await flow.save_draft(
            s,
            uid,
            preview_hash=p["preview_hash"],
            **CHOICES,
            planned_at=at,
            timezone_name="UTC",
        )
        assert new["id"] != d["id"]
        past = at - timedelta(days=2)
        p = await flow.preview(s, uid, **CHOICES, planned_at=past, timezone_name="UTC")
        with pytest.raises(ValueError):
            await flow.save_draft(
                s,
                uid,
                preview_hash=p["preview_hash"],
                **CHOICES,
                planned_at=past,
                timezone_name="UTC",
            )


@pytest.mark.asyncio
async def test_no_network_storage_or_tokens_in_private_preview(monkeypatch):
    from app.infrastructure.artifact_storage import S3ArtifactStorage
    import httpx

    uid, _ = await seed()

    def forbidden(*a, **kw):
        raise AssertionError("No external reads allowed")

    monkeypatch.setattr(S3ArtifactStorage, "from_environment", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden)
    async with SessionFactory() as s:
        p = await flow.preview(s, uid, **CHOICES)
        await flow.save_draft(s, uid, preview_hash=p["preview_hash"], **CHOICES)
        assert "storage_uri" not in str(p) and "session_ciphertext" not in str(p)


@pytest.mark.asyncio
async def test_owner_strict_same_origin_and_no_execution_endpoint(config):
    import httpx
    from app.main import app

    uid, _ = await seed()
    base = f"/api/connections/youtube/materials/{uid}"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as c:
        assert (await c.post(base + "/preview", json=CHOICES)).status_code == 401
        assert (await c.get(base + "/drafts")).status_code == 401
    async with browser() as c:
        assert (
            await c.post(
                base + "/preview",
                json=CHOICES,
                headers={"Origin": "https://evil.invalid"},
            )
        ).status_code == 403
        assert (
            await c.post(base + "/preview", json={**CHOICES, "made_for_kids": "false"})
        ).status_code == 422
        p = await c.post(base + "/preview", json=CHOICES)
        assert p.status_code == 200, p.text
        assert p.headers["cache-control"] == "no-store"
        body = {**CHOICES, "preview_hash": p.json()["preview_hash"]}
        assert (
            await c.post(base + "/drafts", json={**body, "authorized": True})
        ).status_code == 422
        d = await c.post(base + "/drafts", json=body)
        assert d.status_code == 200, d.text
        assert not d.json()["execution_enabled"]
        assert (await c.post(base + "/execute", json={})).status_code in {404, 405}
