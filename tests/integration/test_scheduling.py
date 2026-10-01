import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import inspect, select

from app.adapters.publishing.fake import FakePublisher
from app.application.scheduling import (
    _claim_due_item,
    _finish_schedule_if_complete,
    create_schedule,
    process_due_schedule_items,
    recover_stale_schedule_items,
)
from app.infrastructure.database.models import (
    KnowledgeUnitModel,
    PostModel,
    PublicationModel,
    ScheduleItemModel,
    ScheduleModel,
    SourceModel,
    TopicModel,
)
from app.infrastructure.database.session import SessionFactory
from app.api.console import NASHR_CONSOLE_HTML
from app.main import app, lifespan


async def _post(title: str = "Scheduled post", published: bool = False, status: str = "APPROVED"):
    source_id, topic_id, unit_id, post_id = uuid4(), uuid4(), uuid4(), uuid4()
    async with SessionFactory() as session:
        session.add(SourceModel(
            id=source_id, filename=f"{source_id}.pdf", mime_type="application/pdf",
            storage_path=f"./storage/test/{source_id}.pdf", size_bytes=10, status="STORED",
            book_title=f"Book {source_id}",
        ))
        session.add(TopicModel(id=topic_id, source_id=source_id, position=1, title=f"Topic {source_id}", description="topic"))
        session.add(KnowledgeUnitModel(
            id=unit_id, source_id=source_id, topic_id=topic_id, position=1,
            title=title, content="material", source_reference="page 1",
        ))
        session.add(PostModel(id=post_id, knowledge_unit_id=unit_id, content=f"Post content {title}", status=status))
        if published:
            session.add(PublicationModel(
                id=uuid4(), knowledge_unit_id=unit_id, post_id=post_id,
                platform="telegram", destination="@test", content=f"Post content {title}",
                status="PUBLISHED", external_id="existing-1",
                published_at=datetime.now(timezone.utc),
            ))
        await session.commit()
    return source_id, topic_id, unit_id, post_id


class CountingPublisher(FakePublisher):
    calls = 0

    async def publish(self, *, destination: str, content: str):
        type(self).calls += 1
        await asyncio.sleep(0.02)
        return await super().publish(destination=destination, content=content)


@pytest.mark.asyncio
async def test_create_schedule_requires_approved_posts():
    _, _, _, draft_post = await _post("Draft schedule gate", status="DRAFT")
    _, _, _, rejected_post = await _post("Rejected schedule gate", status="REJECTED")
    _, _, _, approved_post = await _post("Approved schedule gate", status="APPROVED")
    now = datetime.now(timezone.utc) + timedelta(hours=1)
    async with SessionFactory() as session:
        with pytest.raises(RuntimeError, match="must be APPROVED"):
            await create_schedule(session, "draft", "Asia/Aden", [(draft_post, now)])
        with pytest.raises(RuntimeError, match="must be APPROVED"):
            await create_schedule(session, "rejected", "Asia/Aden", [(rejected_post, now)])
        schedule = await create_schedule(session, "approved", "Asia/Aden", [(approved_post, now)])
    assert schedule.status == "DRAFT"


@pytest.mark.asyncio
async def test_create_schedule_persists_order_and_provenance():
    _, _, _, post_a = await _post("A")
    _, _, _, post_b = await _post("B")
    now = datetime.now(timezone.utc) + timedelta(hours=1)
    async with SessionFactory() as session:
        schedule = await create_schedule(session, "October", "Asia/Aden", [(post_a, now), (post_b, now + timedelta(days=1))])
        loaded = (await session.execute(
            select(ScheduleModel).where(ScheduleModel.id == schedule.id)
        )).scalar_one()
        items = (await session.execute(
            select(ScheduleItemModel).where(ScheduleItemModel.schedule_id == schedule.id).order_by(ScheduleItemModel.position)
        )).scalars().all()
    assert loaded.status == "DRAFT"
    assert [i.post_id for i in items] == [post_a, post_b]
    assert [i.position for i in items] == [1, 2]


@pytest.mark.asyncio
async def test_create_schedule_rejects_duplicate_missing_and_naive_datetime():
    _, _, _, post = await _post()
    other = uuid4()
    async with SessionFactory() as session:
        with pytest.raises(ValueError, match="more than once"):
            await create_schedule(session, "x", "Asia/Aden", [(post, datetime.now(timezone.utc)), (post, datetime.now(timezone.utc))])
        with pytest.raises(LookupError):
            await create_schedule(session, "x", "Asia/Aden", [(other, datetime.now(timezone.utc))])
        with pytest.raises(ValueError, match="timezone-aware"):
            await create_schedule(session, "x", "Asia/Aden", [(post, datetime.now())])
        with pytest.raises(ValueError, match="Invalid timezone"):
            await create_schedule(session, "x", "Not/AZone", [(post, datetime.now(timezone.utc))])


@pytest.mark.asyncio
async def test_schedule_api_list_detail_and_missing():
    _, _, _, post = await _post()
    async with SessionFactory() as session:
        schedule = await create_schedule(session, "API schedule", "Asia/Aden", [(post, datetime.now(timezone.utc) + timedelta(days=1))])
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        listing = await client.get("/schedules?limit=10&offset=0")
        detail = await client.get(f"/schedules/{schedule.id}")
        missing = await client.get(f"/schedules/{uuid4()}")
    assert listing.status_code == 200
    assert listing.json()["total"] >= 1
    assert detail.status_code == 200
    assert detail.json()["items"][0]["position"] == 1
    assert detail.json()["items"][0]["source_title"].startswith("Book ")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_schedule_lifecycle_and_conflicts():
    _, _, _, post = await _post()
    async with SessionFactory() as session:
        schedule = await create_schedule(session, "Lifecycle", "Asia/Aden", [(post, datetime.now(timezone.utc) + timedelta(days=1))])
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.post(f"/schedules/{schedule.id}/activate")).status_code == 200
        assert (await client.post(f"/schedules/{schedule.id}/pause")).status_code == 200
        assert (await client.post(f"/schedules/{schedule.id}/activate")).status_code == 200
        assert (await client.post(f"/schedules/{schedule.id}/cancel")).status_code == 200
        assert (await client.post(f"/schedules/{schedule.id}/pause")).status_code == 409


@pytest.mark.asyncio
async def test_due_item_is_claimed_once_concurrently():
    _, _, _, post = await _post()
    async with SessionFactory() as session:
        schedule = await create_schedule(session, "Concurrent", "Asia/Aden", [(post, datetime.now(timezone.utc) - timedelta(minutes=1))])
        schedule.status = "ACTIVE"
        await session.commit()
    now = datetime.now(timezone.utc)
    claims = await asyncio.gather(_claim_due_item(now), _claim_due_item(now))
    assert sum(x is not None for x in claims) == 1


@pytest.mark.asyncio
async def test_due_processing_reuses_existing_publication_and_does_not_duplicate():
    _, _, _, post = await _post(published=True)
    async with SessionFactory() as session:
        schedule = await create_schedule(session, "Already published", "Asia/Aden", [(post, datetime.now(timezone.utc) - timedelta(minutes=1))])
        schedule.status = "ACTIVE"
        await session.commit()
    publisher = CountingPublisher()
    before = publisher.calls
    processed = await process_due_schedule_items(publisher=publisher, destination="@test")
    async with SessionFactory() as session:
        item = (await session.execute(select(ScheduleItemModel).where(ScheduleItemModel.schedule_id == schedule.id))).scalar_one()
        publications = (await session.execute(select(PublicationModel).where(PublicationModel.post_id == post))).scalars().all()
    assert processed >= 1
    assert item.status == "SKIPPED"
    assert publisher.calls == before
    assert len(publications) == 1


@pytest.mark.asyncio
async def test_due_processing_uses_existing_publication_and_records_failure():
    _, _, _, post = await _post()
    async with SessionFactory() as session:
        schedule = await create_schedule(session, "Failure", "Asia/Aden", [(post, datetime.now(timezone.utc) - timedelta(minutes=1))])
        schedule.status = "ACTIVE"
        await session.commit()
    class BrokenPublisher(FakePublisher):
        async def publish(self, *, destination: str, content: str):
            raise RuntimeError("telegram unavailable")
    await process_due_schedule_items(publisher=BrokenPublisher(), destination="@test")
    async with SessionFactory() as session:
        item = (await session.execute(select(ScheduleItemModel).where(ScheduleItemModel.schedule_id == schedule.id))).scalar_one()
    assert item.status == "FAILED"
    assert item.attempts == 1
    assert "telegram unavailable" in item.last_error


@pytest.mark.asyncio
async def test_retry_failed_item_can_be_processed_again():
    _, _, _, post = await _post()
    async with SessionFactory() as session:
        schedule = await create_schedule(session, "Retry", "Asia/Aden", [(post, datetime.now(timezone.utc) - timedelta(minutes=1))])
        schedule.status = "ACTIVE"
        await session.commit()
    class BrokenPublisher(FakePublisher):
        async def publish(self, *, destination: str, content: str):
            raise RuntimeError("temporary")
    await process_due_schedule_items(publisher=BrokenPublisher(), destination="@test")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/schedules/{schedule.id}/retry-failed")
    assert response.status_code == 202
    async with SessionFactory() as session:
        item = (await session.execute(select(ScheduleItemModel).where(ScheduleItemModel.schedule_id == schedule.id))).scalar_one()
    assert item.status == "PENDING"


@pytest.mark.asyncio
async def test_stale_processing_recovery_respects_schedule_lifecycle():
    _, _, _, active_post = await _post("Recovery active")
    _, _, _, paused_post = await _post("Recovery paused")
    _, _, _, cancelled_post = await _post("Recovery cancelled")
    _, _, _, published_post = await _post("Recovery published")

    async with SessionFactory() as session:
        active = await create_schedule(session, "Recovery active", "Asia/Aden", [(active_post, datetime.now(timezone.utc) + timedelta(days=1))])
        paused = await create_schedule(session, "Recovery paused", "Asia/Aden", [(paused_post, datetime.now(timezone.utc) + timedelta(days=1))])
        cancelled = await create_schedule(session, "Recovery cancelled", "Asia/Aden", [(cancelled_post, datetime.now(timezone.utc) + timedelta(days=1))])
        published = await create_schedule(session, "Recovery published", "Asia/Aden", [(published_post, datetime.now(timezone.utc) + timedelta(days=1))])
        active.status = "ACTIVE"
        paused.status = "PAUSED"
        cancelled.status = "CANCELLED"

        stale_at = datetime.now(timezone.utc) - timedelta(minutes=20)
        for schedule in (active, paused, cancelled):
            item = (await session.execute(
                select(ScheduleItemModel).where(ScheduleItemModel.schedule_id == schedule.id)
            )).scalar_one()
            item.status = "PROCESSING"
            item.processing_started_at = stale_at

        published_id = uuid4()
        published_unit = (await session.execute(
            select(PostModel.knowledge_unit_id).where(PostModel.id == published_post)
        )).scalar_one()
        session.add(PublicationModel(
            id=published_id, knowledge_unit_id=published_unit, post_id=published_post,
            platform="telegram", destination="@test", content="already published",
            status="PUBLISHED", external_id="published-2",
            published_at=datetime.now(timezone.utc),
        ))
        published_item = (await session.execute(
            select(ScheduleItemModel).where(ScheduleItemModel.schedule_id == published.id)
        )).scalar_one()
        published_item.status = "PUBLISHED"
        published_item.publication_id = published_id
        published_item.published_at = datetime.now(timezone.utc)
        await session.commit()

    recovered = await recover_stale_schedule_items()
    assert len(recovered) == 3

    async with SessionFactory() as session:
        rows = (await session.execute(
            select(ScheduleItemModel, ScheduleModel.status)
            .join(ScheduleModel)
            .where(ScheduleItemModel.id.in_(recovered))
        )).all()
    by_status = {schedule_status: item.status for item, schedule_status in rows}
    assert by_status["ACTIVE"] == "PENDING"
    assert by_status["PAUSED"] == "PENDING"
    assert by_status["CANCELLED"] == "CANCELLED"

    async with SessionFactory() as session:
        cancelled_item = (await session.execute(
            select(ScheduleItemModel).where(ScheduleItemModel.schedule_id == cancelled.id)
        )).scalar_one()
        assert "external publication outcome is unknown" in cancelled_item.last_error

    async with SessionFactory() as session:
        untouched = (await session.execute(
            select(ScheduleItemModel).where(ScheduleItemModel.schedule_id == published.id)
        )).scalar_one()
    assert untouched.status == "PUBLISHED"


@pytest.mark.asyncio
async def test_cancelled_schedule_never_becomes_completed():
    _, _, _, post = await _post("Cancelled completion guard")
    async with SessionFactory() as session:
        schedule = await create_schedule(
            session,
            "Cancelled completion guard",
            "Asia/Aden",
            [(post, datetime.now(timezone.utc) - timedelta(minutes=1))],
        )
        schedule.status = "CANCELLED"
        item = (await session.execute(
            select(ScheduleItemModel).where(ScheduleItemModel.schedule_id == schedule.id)
        )).scalar_one()
        item.status = "PUBLISHED"
        await session.commit()

    async with SessionFactory() as session:
        await _finish_schedule_if_complete(session, schedule.id)
        await session.commit()
        refreshed = (await session.execute(
            select(ScheduleModel).where(ScheduleModel.id == schedule.id)
        )).scalar_one()

    assert refreshed.status == "CANCELLED"


@pytest.mark.asyncio
async def test_schedule_trigger_runs_from_application_lifespan(monkeypatch):
    triggered = asyncio.Event()

    async def fake_process_due_schedule_items(*, limit=20):
        triggered.set()
        return 0

    async def no_recovery():
        return []

    monkeypatch.setattr("app.main.process_due_schedule_items", fake_process_due_schedule_items)
    monkeypatch.setattr("app.main.recover_stale_jobs", no_recovery)
    monkeypatch.setattr("app.main.recover_stale_production_jobs", no_recovery)
    monkeypatch.setattr("app.main.recover_stale_schedule_items", no_recovery)

    async with lifespan(app):
        await asyncio.wait_for(triggered.wait(), timeout=1.0)


@pytest.mark.asyncio
async def test_console_schedule_time_conversion_is_timezone_aware():
    assert "localDateTimeToUtcISOString" in NASHR_CONSOLE_HTML
    assert "timeZone,hourCycle:'h23'" in NASHR_CONSOLE_HTML
    assert "new Date(x.value).toISOString()" not in NASHR_CONSOLE_HTML


@pytest.mark.asyncio
async def test_schedule_detail_defers_source_file_payload():
    _, _, _, post = await _post()
    async with SessionFactory() as session:
        schedule = await create_schedule(session, "Deferred source", "Asia/Aden", [(post, datetime.now(timezone.utc) + timedelta(days=1))])
        loaded = await __import__("app.application.scheduling", fromlist=["get_schedule"]).get_schedule(session, schedule.id)
        source = loaded.items[0].post.knowledge_unit.source
        assert "file_payload" in inspect(source).unloaded
