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
from app.main import app


async def _post(title: str = "Scheduled post", published: bool = False):
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
        session.add(PostModel(id=post_id, knowledge_unit_id=unit_id, content=f"Post content {title}"))
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
async def test_stale_processing_recovers_but_published_does_not():
    _, _, _, post = await _post()
    _, _, _, post2 = await _post("Recovery published")
    async with SessionFactory() as session:
        schedule = await create_schedule(session, "Recovery", "Asia/Aden", [(post, datetime.now(timezone.utc) + timedelta(days=1))])
        schedule.status = "ACTIVE"
        await session.commit()
        item = (await session.execute(
            select(ScheduleItemModel).where(
                ScheduleItemModel.schedule_id == schedule.id,
                ScheduleItemModel.position == 1,
            )
        )).scalar_one()
        item.status = "PROCESSING"
        item.processing_started_at = datetime.now(timezone.utc) - timedelta(minutes=20)
        await session.commit()
        published_id = uuid4()
        post2_unit = (await session.execute(
            select(PostModel.knowledge_unit_id).where(PostModel.id == post2)
        )).scalar_one()
        session.add(PublicationModel(
            id=published_id, knowledge_unit_id=post2_unit, post_id=post2,
            platform="telegram", destination="@test", content="already published",
            status="PUBLISHED", external_id="published-2",
            published_at=datetime.now(timezone.utc),
        ))
        item2 = ScheduleItemModel(
            id=uuid4(), schedule_id=schedule.id, post_id=post2, position=2,
            scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            status="PUBLISHED", publication_id=published_id,
            published_at=datetime.now(timezone.utc),
        )
        session.add(item2)
        await session.commit()
    await recover_stale_schedule_items()
    async with SessionFactory() as session:
        rows = (await session.execute(select(ScheduleItemModel).where(ScheduleItemModel.schedule_id == schedule.id).order_by(ScheduleItemModel.position))).scalars().all()
    assert rows[0].status == "PENDING"
    assert rows[1].status == "PUBLISHED"


@pytest.mark.asyncio
async def test_schedule_detail_defers_source_file_payload():
    _, _, _, post = await _post()
    async with SessionFactory() as session:
        schedule = await create_schedule(session, "Deferred source", "Asia/Aden", [(post, datetime.now(timezone.utc) + timedelta(days=1))])
        loaded = await __import__("app.application.scheduling", fromlist=["get_schedule"]).get_schedule(session, schedule.id)
        source = loaded.items[0].post.knowledge_unit.source
        assert "file_payload" in inspect(source).unloaded
