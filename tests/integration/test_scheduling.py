import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import func, inspect, select

from app.adapters.publishing.fake import FakePublisher
from app.application.scheduling import (
    _claim_due_item,
    _finish_schedule_if_complete,
    build_schedule_times,
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
        with pytest.raises(RuntimeError, match="not eligible"):
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
async def test_due_execution_publishes_approved_post():
    _, _, _, post = await _post("Approved execution")
    async with SessionFactory() as session:
        schedule = await create_schedule(
            session, "Approved execution", "Asia/Aden",
            [(post, datetime.now(timezone.utc) - timedelta(minutes=1))],
        )
        schedule.status = "ACTIVE"
        await session.commit()
    publisher = CountingPublisher()
    await process_due_schedule_items(publisher=publisher, destination="@test")
    async with SessionFactory() as session:
        item = (await session.execute(
            select(ScheduleItemModel).where(ScheduleItemModel.schedule_id == schedule.id)
        )).scalar_one()
        publication = (await session.execute(
            select(PublicationModel).where(PublicationModel.post_id == post)
        )).scalar_one()
    assert item.status == "PUBLISHED"
    assert publication.status == "PUBLISHED"
    assert publisher.calls >= 1


@pytest.mark.asyncio
async def test_due_execution_refuses_post_that_lost_approval():
    _, _, _, post = await _post("Approval revoked before execution")
    async with SessionFactory() as session:
        schedule = await create_schedule(
            session, "Approval revoked", "Asia/Aden",
            [(post, datetime.now(timezone.utc) - timedelta(minutes=1))],
        )
        schedule.status = "ACTIVE"
        post_row = (await session.execute(select(PostModel).where(PostModel.id == post))).scalar_one()
        post_row.status = "DRAFT"
        await session.commit()
    CountingPublisher.calls = 0
    publisher = CountingPublisher()
    await process_due_schedule_items(publisher=publisher, destination="@test")
    async with SessionFactory() as session:
        item = (await session.execute(
            select(ScheduleItemModel).where(ScheduleItemModel.schedule_id == schedule.id)
        )).scalar_one()
        publications = (await session.execute(
            select(PublicationModel).where(PublicationModel.post_id == post)
        )).scalars().all()
    assert item.status == "CANCELLED"
    assert publications == []
    assert publisher.calls == 0


@pytest.mark.asyncio
async def test_due_execution_refuses_rejected_post():
    CountingPublisher.calls = 0
    _, _, _, post = await _post("Rejected before execution")
    async with SessionFactory() as session:
        schedule = await create_schedule(
            session, "Rejected execution", "Asia/Aden",
            [(post, datetime.now(timezone.utc) - timedelta(minutes=1))],
        )
        schedule.status = "ACTIVE"
        post_row = (await session.execute(select(PostModel).where(PostModel.id == post))).scalar_one()
        post_row.status = "REJECTED"
        await session.commit()
    publisher = CountingPublisher()
    await process_due_schedule_items(publisher=publisher, destination="@test")
    async with SessionFactory() as session:
        item = (await session.execute(
            select(ScheduleItemModel).where(ScheduleItemModel.schedule_id == schedule.id)
        )).scalar_one()
        publications = (await session.execute(
            select(PublicationModel).where(PublicationModel.post_id == post)
        )).scalars().all()
    assert item.status == "CANCELLED"
    assert publications == []
    assert publisher.calls == 0


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



@pytest.mark.asyncio
async def test_build_schedule_times_is_deterministic_and_timezone_aware():
    post_ids = [uuid4(), uuid4(), uuid4()]
    start = datetime(2026, 10, 5, 20, 0, tzinfo=ZoneInfo("Asia/Aden"))
    items = build_schedule_times(post_ids, start, 30, "Asia/Aden")
    assert [post_id for post_id, _ in items] == post_ids
    assert [when for _, when in items] == [
        datetime(2026, 10, 5, 17, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 5, 17, 30, tzinfo=timezone.utc),
        datetime(2026, 10, 5, 18, 0, tzinfo=timezone.utc),
    ]


@pytest.mark.asyncio
async def test_schedule_api_can_generate_times_from_post_selection():
    _, _, _, post_a = await _post("Generated A")
    _, _, _, post_b = await _post("Generated B")
    start = "2026-10-05T17:00:00+00:00"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/schedules",
            json={
                "name": "Generated schedule",
                "timezone": "Asia/Aden",
                "post_ids": [str(post_a), str(post_b)],
                "start_at": start,
                "interval_minutes": 30,
            },
        )
    assert response.status_code == 201
    items = response.json()["items"]
    assert [item["position"] for item in items] == [1, 2]
    assert [item["scheduled_at"] for item in items] == [
        "2026-10-05T17:00:00Z",
        "2026-10-05T17:30:00Z",
    ]


@pytest.mark.asyncio
async def test_schedule_api_rejects_invalid_generated_schedule_request():
    _, _, _, post = await _post("Invalid generated")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/schedules",
            json={
                "name": "Invalid",
                "timezone": "Asia/Aden",
                "post_ids": [str(post)],
            },
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upcoming_queue_returns_active_pending_items():
    _, _, _, post = await _post("Upcoming")
    async with SessionFactory() as session:
        schedule = await create_schedule(
            session,
            "Upcoming schedule",
            "Asia/Aden",
            [(post, datetime.now(timezone.utc) + timedelta(hours=1))],
        )
        schedule.status = "ACTIVE"
        await session.commit()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/schedules/upcoming?days=2")
    assert response.status_code == 200
    assert any(item["post_id"] == str(post) for item in response.json()["items"])


@pytest.mark.asyncio
async def test_telegram_preview_uses_canonical_post_content():
    _, _, _, post = await _post("Preview")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/posts/{post}/telegram-preview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["post_id"] == str(post)
    assert payload["platform"] == "telegram"
    assert payload["content"] == "Post content Preview"
    assert payload["ready"] is True



@pytest.mark.asyncio
async def test_schedule_creation_idempotency_returns_same_schedule():
    _, _, _, post = await _post("Idempotent schedule")
    transport = httpx.ASGITransport(app=app)
    payload = {
        "name": "Idempotent",
        "timezone": "Asia/Aden",
        "post_ids": [str(post)],
        "start_at": "2026-10-05T17:00:00+00:00",
        "interval_minutes": 30,
        "idempotency_key": "schedule-test-idempotency-1",
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/schedules", json=payload)
        second = await client.post("/schedules", json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert len(second.json()["items"]) == 1


@pytest.mark.asyncio
async def test_schedule_api_rejects_unapproved_post_with_409():
    _, _, _, post = await _post("API draft gate", status="DRAFT")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/schedules",
            json={
                "name": "Blocked",
                "timezone": "Asia/Aden",
                "post_ids": [str(post)],
                "start_at": "2026-10-05T17:00:00+00:00",
                "interval_minutes": 30,
            },
        )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_schedule_idempotency_key_rejects_conflicting_request():
    _, _, _, post_a = await _post("Idempotency A")
    _, _, _, post_b = await _post("Idempotency B")
    transport = httpx.ASGITransport(app=app)
    key = "schedule-conflicting-idempotency-test"
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/schedules",
            json={
                "name": "First",
                "timezone": "Asia/Aden",
                "post_ids": [str(post_a)],
                "start_at": "2026-10-05T17:00:00+00:00",
                "interval_minutes": 30,
                "idempotency_key": key,
            },
        )
        second = await client.post(
            "/schedules",
            json={
                "name": "Different",
                "timezone": "Asia/Aden",
                "post_ids": [str(post_b)],
                "start_at": "2026-10-05T18:00:00+00:00",
                "interval_minutes": 60,
                "idempotency_key": key,
            },
        )
    assert first.status_code == 201
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_schedule_calendar_returns_items_by_schedule_timezone():
    _, _, _, post = await _post("Calendar item")
    async with SessionFactory() as session:
        schedule = await create_schedule(
            session,
            "Calendar",
            "Asia/Aden",
            [(post, datetime(2026, 10, 5, 17, 0, tzinfo=timezone.utc))],
        )
        schedule.status = "ACTIVE"
        await session.commit()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/schedules/calendar?date=2026-10-05&timezone=Asia/Aden")
    assert response.status_code == 200
    assert str(post) in [item["post_id"] for item in response.json()["items"]]


@pytest.mark.asyncio
async def test_schedule_scales_to_hundreds_of_posts_deterministically():
    posts = [await _post(f"Scale {index}") for index in range(200)]
    post_ids = [row[3] for row in posts]
    start = datetime(2026, 10, 5, 17, 0, tzinfo=timezone.utc)
    async with SessionFactory() as session:
        schedule = await create_schedule(
            session,
            "Scale schedule",
            "Asia/Aden",
            build_schedule_times(post_ids, start, 5, "Asia/Aden"),
        )
        items = (await session.execute(
            select(ScheduleItemModel)
            .where(ScheduleItemModel.schedule_id == schedule.id)
            .order_by(ScheduleItemModel.position)
        )).scalars().all()
    assert len(items) == 200
    assert [item.position for item in items] == list(range(1, 201))
    assert [item.post_id for item in items] == post_ids
    assert len({item.scheduled_at for item in items}) == 200


@pytest.mark.asyncio
async def test_schedule_validation_reports_unapproved_item_without_blocking_schedule():
    _, _, _, post = await _post("Activation recheck")
    async with SessionFactory() as session:
        schedule = await create_schedule(
            session,
            "Activation recheck",
            "Asia/Aden",
            [(post, datetime.now(timezone.utc) + timedelta(hours=1))],
        )
        loaded_post = (await session.execute(select(PostModel).where(PostModel.id == post))).scalar_one()
        loaded_post.status = "DRAFT"
        await session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        validation = await client.get(f"/schedules/{schedule.id}/validation")
        activation = await client.post(f"/schedules/{schedule.id}/activate")

    assert validation.status_code == 200
    assert validation.json()["valid"] is True
    assert any(item["reason_code"] == "POST_NOT_APPROVED" for item in validation.json()["blocked_items"])
    assert activation.status_code == 200

    async with SessionFactory() as session:
        refreshed = (await session.execute(select(ScheduleModel).where(ScheduleModel.id == schedule.id))).scalar_one()
    assert refreshed.status == "ACTIVE"


@pytest.mark.asyncio
async def test_schedule_validation_reports_publish_execution_summary():
    _, _, _, post = await _post("Activation summary")
    async with SessionFactory() as session:
        schedule = await create_schedule(
            session,
            "Activation summary",
            "Asia/Aden",
            [(post, datetime.now(timezone.utc) + timedelta(hours=1))],
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/schedules/{schedule.id}/validation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert payload["total_items"] == 1
    assert payload["pending_items"] == 1
    assert payload["errors"] == []


@pytest.mark.asyncio
async def test_schedule_eligibility_excludes_published_and_existing_schedule() -> None:
    _, _, _, published_post = await _post("Already published", published=True)
    _, _, _, scheduled_post = await _post("Already scheduled")
    _, _, _, eligible_post = await _post("Eligible")
    async with SessionFactory() as session:
        await create_schedule(
            session,
            "Existing",
            "Asia/Aden",
            [(scheduled_post, datetime.now(timezone.utc) + timedelta(hours=1))],
        )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/schedules/eligibility",
            params=[
                ("post_ids", str(published_post)),
                ("post_ids", str(scheduled_post)),
                ("post_ids", str(eligible_post)),
            ],
        )
    assert response.status_code == 200
    payload = response.json()
    assert str(eligible_post) in payload["eligible_ids"]
    blocked = {row["post_id"]: row["reason_code"] for row in payload["blocked"]}
    assert blocked[str(published_post)] == "ALREADY_PUBLISHED"
    assert blocked[str(scheduled_post)] == "ALREADY_SCHEDULED"


@pytest.mark.asyncio
async def test_create_schedule_rejects_already_published_or_scheduled_post() -> None:
    _, _, _, published_post = await _post("Create published", published=True)
    _, _, _, scheduled_post = await _post("Create scheduled")
    async with SessionFactory() as session:
        await create_schedule(
            session,
            "Existing schedule",
            "Asia/Aden",
            [(scheduled_post, datetime.now(timezone.utc) + timedelta(hours=2))],
        )
        with pytest.raises(RuntimeError, match="not eligible"):
            await create_schedule(
                session,
                "Published schedule",
                "Asia/Aden",
                [(published_post, datetime.now(timezone.utc) + timedelta(hours=1))],
            )
        with pytest.raises(RuntimeError, match="not eligible"):
            await create_schedule(
                session,
                "Duplicate schedule",
                "Asia/Aden",
                [(scheduled_post, datetime.now(timezone.utc) + timedelta(hours=3))],
            )


@pytest.mark.asyncio
async def test_schedule_validation_keeps_item_blockers_from_blocking_siblings() -> None:
    _, _, _, published_post = await _post("Legacy published", published=True)
    _, _, _, good_post = await _post("Legacy good")
    async with SessionFactory() as session:
        schedule = await create_schedule(
            session,
            "Legacy mixed",
            "Asia/Aden",
            [(good_post, datetime.now(timezone.utc) + timedelta(hours=1))],
        )
        unit_id = (await session.execute(
            select(PostModel.knowledge_unit_id).where(PostModel.id == good_post)
        )).scalar_one()
        session.add(PublicationModel(
            id=uuid4(), knowledge_unit_id=unit_id, post_id=good_post,
            platform="telegram", destination="@test", content="legacy",
            status="PUBLISHED", external_id="legacy-published",
        ))
        await session.commit()
        session.add(ScheduleItemModel(
            id=uuid4(), schedule_id=schedule.id, post_id=published_post, position=2,
            scheduled_at=datetime.now(timezone.utc) + timedelta(hours=2),
            status="PENDING",
        ))
        await session.commit()
        validation = await __import__(
            "app.application.scheduling",
            fromlist=["validate_schedule_for_activation"],
        ).validate_schedule_for_activation(session, schedule.id)
    assert validation["valid"] is True
    assert validation["blocked_items"]


@pytest.mark.asyncio
async def test_due_processing_isolates_one_item_failure_and_completes_schedule() -> None:
    posts = [await _post(f"Isolation {index}") for index in range(5)]
    post_ids = [row[3] for row in posts]
    async with SessionFactory() as session:
        schedule = await create_schedule(
            session,
            "Failure isolation",
            "Asia/Aden",
            [(post_id, datetime.now(timezone.utc) - timedelta(minutes=1)) for post_id in post_ids],
        )
        schedule.status = "ACTIVE"
        await session.commit()

    class OneFailsPublisher(FakePublisher):
        async def publish(self, *, destination: str, content: str):
            if "Isolation 2" in content:
                raise RuntimeError("telegram failure for one item")
            return await super().publish(destination=destination, content=content)

    processed = await process_due_schedule_items(
        limit=20,
        publisher=OneFailsPublisher(),
        destination="@test",
    )
    assert processed == 5
    async with SessionFactory() as session:
        schedule_row = (await session.execute(
            select(ScheduleModel).where(ScheduleModel.id == schedule.id)
        )).scalar_one()
        items = (await session.execute(
            select(ScheduleItemModel)
            .where(ScheduleItemModel.schedule_id == schedule.id)
            .order_by(ScheduleItemModel.position)
        )).scalars().all()
    assert [item.status for item in items] == ["PUBLISHED", "PUBLISHED", "FAILED", "PUBLISHED", "PUBLISHED"]
    assert schedule_row.status == "COMPLETED"


@pytest.mark.asyncio
async def test_failed_item_can_be_retried_after_schedule_completed() -> None:
    _, _, _, post = await _post("Retry completed")
    async with SessionFactory() as session:
        schedule = await create_schedule(
            session,
            "Retry completed",
            "Asia/Aden",
            [(post, datetime.now(timezone.utc) - timedelta(minutes=1))],
        )
        schedule.status = "ACTIVE"
        await session.commit()

    class BrokenPublisher(FakePublisher):
        async def publish(self, *, destination: str, content: str):
            raise RuntimeError("temporary retry failure")

    await process_due_schedule_items(publisher=BrokenPublisher(), destination="@test")
    async with SessionFactory() as session:
        completed = (await session.execute(
            select(ScheduleModel).where(ScheduleModel.id == schedule.id)
        )).scalar_one()
    assert completed.status == "COMPLETED"

    async with SessionFactory() as session:
        eligibility = await __import__(
            "app.application.scheduling",
            fromlist=["get_posts_publish_eligibility"],
        ).get_posts_publish_eligibility(session, [post])
    assert eligibility["eligible_ids"] == []
    assert eligibility["blocked"][0]["reason_code"] == "ALREADY_SCHEDULED"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/schedules/{schedule.id}/retry-failed")
    assert response.status_code == 202
    assert response.json()["retried_items"] == 1

    await process_due_schedule_items(publisher=FakePublisher(), destination="@test")
    async with SessionFactory() as session:
        item = (await session.execute(
            select(ScheduleItemModel).where(ScheduleItemModel.schedule_id == schedule.id)
        )).scalar_one()
        publications = (await session.execute(
            select(PublicationModel).where(
                PublicationModel.post_id == post,
                PublicationModel.status == "PUBLISHED",
            )
        )).scalars().all()
    assert item.status == "PUBLISHED"
    assert len(publications) == 1


@pytest.mark.asyncio
async def test_retry_after_existing_publication_never_creates_duplicate() -> None:
    _, _, _, post = await _post("Retry duplicate", published=True)
    async with SessionFactory() as session:
        schedule = ScheduleModel(
            id=uuid4(), name="Retry duplicate", timezone="Asia/Aden", status="ACTIVE",
        )
        schedule.items = [ScheduleItemModel(
            id=uuid4(), post_id=post, position=1,
            scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            status="FAILED",
        )]
        session.add(schedule)
        await session.commit()

    from app.application.scheduling import retry_failed_items
    async with SessionFactory() as session:
        count_before = int((await session.execute(
            select(func.count(PublicationModel.id)).where(
                PublicationModel.post_id == post,
                PublicationModel.status == "PUBLISHED",
            )
        )).scalar_one())
        await retry_failed_items(session, schedule.id)

    await process_due_schedule_items(publisher=FakePublisher(), destination="@test")
    async with SessionFactory() as session:
        count_after = int((await session.execute(
            select(func.count(PublicationModel.id)).where(
                PublicationModel.post_id == post,
                PublicationModel.status == "PUBLISHED",
            )
        )).scalar_one())
    assert count_before == count_after == 1


@pytest.mark.asyncio
async def test_concurrent_schedule_creation_reserves_a_post_once() -> None:
    _, _, _, post = await _post("Concurrent reservation")

    async def create(name: str):
        async with SessionFactory() as session:
            return await create_schedule(
                session,
                name,
                "Asia/Aden",
                [(post, datetime.now(timezone.utc) + timedelta(hours=1))],
            )

    results = await asyncio.gather(
        create("Concurrent A"),
        create("Concurrent B"),
        return_exceptions=True,
    )
    successes = [result for result in results if isinstance(result, ScheduleModel)]
    failures = [result for result in results if isinstance(result, RuntimeError)]
    assert len(successes) == 1
    assert len(failures) == 1


@pytest.mark.asyncio
async def test_failed_item_can_be_retried_individually() -> None:
    _, _, _, post_a = await _post("Individual retry A")
    _, _, _, post_b = await _post("Individual retry B")
    async with SessionFactory() as session:
        schedule = await create_schedule(
            session,
            "Individual retry",
            "Asia/Aden",
            [
                (post_a, datetime.now(timezone.utc) - timedelta(minutes=1)),
                (post_b, datetime.now(timezone.utc) + timedelta(hours=1)),
            ],
        )
        schedule.status = "ACTIVE"
        item = (await session.execute(
            select(ScheduleItemModel).where(
                ScheduleItemModel.schedule_id == schedule.id,
                ScheduleItemModel.post_id == post_a,
            )
        )).scalar_one()
        item.status = "FAILED"
        item.last_error = "temporary"
        await session.commit()
        item_id = item.id

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/schedules/{schedule.id}/items/{item_id}/retry")
    assert response.status_code == 202
    async with SessionFactory() as session:
        refreshed_a = (await session.execute(
            select(ScheduleItemModel).where(ScheduleItemModel.id == item_id)
        )).scalar_one()
        refreshed_b = (await session.execute(
            select(ScheduleItemModel).where(
                ScheduleItemModel.schedule_id == schedule.id,
                ScheduleItemModel.post_id == post_b,
            )
        )).scalar_one()
    assert refreshed_a.status == "PENDING"
    assert refreshed_b.status == "PENDING"
