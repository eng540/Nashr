"""Integration coverage for scheduled media Artifacts (IMAGE/VIDEO).

Covers the paths that guard against duplicate external sends: happy-path
publish, failure then retry with a single publication row, route-level
duplicate schedule rejection, the approval gate, and execution-level skip
when a second schedule item races an already-published artifact.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.adapters.publishing.fake import FakePublisher
from app.api.artifacts import QuizScheduleRequest, schedule_approved_quiz
from app.application import publications as publications_module
from app.application.scheduling import (
    process_due_schedule_items,
    retry_failed_item,
    transition,
)
from app.infrastructure.database.models import (
    ArtifactModel,
    KnowledgeUnitModel,
    PublicationModel,
    ScheduleItemModel,
    ScheduleModel,
    SourceModel,
)
from app.infrastructure.database.session import SessionFactory


class _StubStorage:
    async def get_bytes(self, storage_uri: str) -> bytes:
        return b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes"


@pytest.fixture(autouse=True)
def _stub_artifact_storage(monkeypatch):
    monkeypatch.setattr(publications_module.S3ArtifactStorage, "from_environment", staticmethod(lambda: _StubStorage()))


class CountingPublisher(FakePublisher):
    calls = 0

    async def publish(self, **kwargs):
        type(self).calls += 1
        return await super().publish(**kwargs)


class BrokenPublisher(FakePublisher):
    async def publish(self, **kwargs):
        raise RuntimeError("telegram unavailable")


async def _media_artifact(review_status: str = "APPROVED", caption: str = "تعليق تجريبي"):
    source_id, unit_id, artifact_id = uuid4(), uuid4(), uuid4()
    async with SessionFactory() as session:
        session.add(SourceModel(
            id=source_id, filename=f"{artifact_id}.webp", mime_type="image/webp",
            storage_path=f"s3://fake/{artifact_id}/img.webp", size_bytes=10, status="STORED",
        ))
        session.add(KnowledgeUnitModel(
            id=unit_id, source_id=source_id, position=1, title="وسيط تجريبي",
            kind="MEDIA_BANK", content=caption,
        ))
        await session.flush()
        session.add(ArtifactModel(
            id=artifact_id, source_knowledge_unit_id=unit_id, kind="IMAGE", status="AVAILABLE",
            review_status=review_status, storage_uri=f"s3://fake/{artifact_id}/img.webp",
            mime_type="image/webp",
            artifact_metadata={"source_type": "MEDIA_BANK_UPLOAD", "caption": caption},
            resolved_context={"output_contract": {
                "contract_id": str(uuid4()), "version_id": str(uuid4()),
                "key": "MEDIA_BANK_UPLOAD", "version": 1,
                "definition": {
                    "artifact_kind": "IMAGE", "mime_type": "image/webp",
                    "content_mode": "STORAGE_URI", "required_metadata_fields": ["source_type"],
                    "max_content_chars": None,
                },
            }},
        ))
        await session.commit()
    return artifact_id


async def _schedule_and_activate(artifact_id, scheduled_at):
    payload = QuizScheduleRequest(name=f"media-{artifact_id}", timezone="Asia/Riyadh", scheduled_at=scheduled_at)
    async with SessionFactory() as session:
        result = await schedule_approved_quiz(artifact_id=artifact_id, payload=payload, session=session)
    async with SessionFactory() as session:
        schedule = (await session.execute(select(ScheduleModel).where(ScheduleModel.id == result["id"]))).scalar_one()
        transition(schedule, "activate")
        await session.commit()
    return result["id"]


@pytest.mark.asyncio
async def test_media_schedule_publishes_with_caption():
    artifact_id = await _media_artifact()
    schedule_id = await _schedule_and_activate(artifact_id, datetime.now(timezone.utc) - timedelta(minutes=1))

    processed = await process_due_schedule_items(publisher=FakePublisher(), destination="@test")

    assert processed == 1
    async with SessionFactory() as session:
        item = (await session.execute(select(ScheduleItemModel).where(ScheduleItemModel.schedule_id == schedule_id))).scalar_one()
        assert item.status == "PUBLISHED"
        pubs = (await session.execute(select(PublicationModel).where(PublicationModel.artifact_id == artifact_id))).scalars().all()
        assert len(pubs) == 1
        assert pubs[0].status == "PUBLISHED"
        assert pubs[0].content == "تعليق تجريبي"
        assert pubs[0].external_id == "test_msg_999"


@pytest.mark.asyncio
async def test_media_schedule_rerun_does_not_republish():
    artifact_id = await _media_artifact()
    await _schedule_and_activate(artifact_id, datetime.now(timezone.utc) - timedelta(minutes=1))

    first = await process_due_schedule_items(publisher=FakePublisher(), destination="@test")
    second = await process_due_schedule_items(publisher=FakePublisher(), destination="@test")

    assert first == 1
    assert second == 0
    async with SessionFactory() as session:
        pubs = (await session.execute(select(PublicationModel).where(PublicationModel.artifact_id == artifact_id))).scalars().all()
        assert len(pubs) == 1
        assert pubs[0].status == "PUBLISHED"


@pytest.mark.asyncio
async def test_media_schedule_failed_then_retry_single_publication():
    artifact_id = await _media_artifact()
    schedule_id = await _schedule_and_activate(artifact_id, datetime.now(timezone.utc) - timedelta(minutes=1))

    await process_due_schedule_items(publisher=BrokenPublisher(), destination="@test")

    async with SessionFactory() as session:
        item = (await session.execute(select(ScheduleItemModel).where(ScheduleItemModel.schedule_id == schedule_id))).scalar_one()
        assert item.status == "FAILED"
        pubs = (await session.execute(select(PublicationModel).where(PublicationModel.artifact_id == artifact_id))).scalars().all()
        assert len(pubs) == 1
        assert pubs[0].status == "FAILED"
        await retry_failed_item(session, schedule_id, item.id)

    await process_due_schedule_items(publisher=FakePublisher(), destination="@test")

    async with SessionFactory() as session:
        item = (await session.execute(select(ScheduleItemModel).where(ScheduleItemModel.schedule_id == schedule_id))).scalar_one()
        assert item.status == "PUBLISHED"
        pubs = (await session.execute(select(PublicationModel).where(PublicationModel.artifact_id == artifact_id))).scalars().all()
        assert len(pubs) == 1
        assert pubs[0].status == "PUBLISHED"
        assert pubs[0].content == "تعليق تجريبي"


@pytest.mark.asyncio
async def test_media_schedule_duplicate_rejected():
    artifact_id = await _media_artifact()
    schedule_id = await _schedule_and_activate(artifact_id, datetime.now(timezone.utc) + timedelta(hours=1))

    payload = QuizScheduleRequest(
        name=f"dup-{artifact_id}", timezone="Asia/Riyadh",
        scheduled_at=datetime.now(timezone.utc) + timedelta(hours=2),
    )
    try:
        with pytest.raises(Exception, match="active or draft schedule"):
            async with SessionFactory() as session:
                await schedule_approved_quiz(artifact_id=artifact_id, payload=payload, session=session)
    finally:
        # Do not leak an ACTIVE schedule with pending items into other integration tests.
        async with SessionFactory() as session:
            schedule = (await session.execute(
                select(ScheduleModel)
                .options(selectinload(ScheduleModel.items))
                .where(ScheduleModel.id == schedule_id)
            )).scalar_one()
            transition(schedule, "cancel")
            await session.commit()


@pytest.mark.asyncio
async def test_media_schedule_requires_approval():
    artifact_id = await _media_artifact(review_status="DRAFT")
    payload = QuizScheduleRequest(
        name=f"unapproved-{artifact_id}", timezone="Asia/Riyadh",
        scheduled_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    with pytest.raises(Exception, match="must be approved"):
        async with SessionFactory() as session:
            await schedule_approved_quiz(artifact_id=artifact_id, payload=payload, session=session)


@pytest.mark.asyncio
async def test_second_schedule_item_skipped_after_publish():
    """A second active schedule for the same artifact must skip, never double-send."""
    artifact_id = await _media_artifact()
    schedule_id = await _schedule_and_activate(artifact_id, datetime.now(timezone.utc) - timedelta(minutes=1))

    async with SessionFactory() as session:
        schedule2 = ScheduleModel(id=uuid4(), name="dup-schedule", timezone="Asia/Riyadh", status="ACTIVE")
        schedule2.items = [ScheduleItemModel(
            id=uuid4(), artifact_id=artifact_id, post_id=None, position=1,
            scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1), status="PENDING",
        )]
        session.add(schedule2)
        await session.commit()
        schedule2_id = schedule2.id

    CountingPublisher.calls = 0
    processed = await process_due_schedule_items(publisher=CountingPublisher(), destination="@test")

    assert processed == 2
    assert CountingPublisher.calls == 1
    async with SessionFactory() as session:
        statuses = {
            str(row.schedule_id): row.status
            for row in (await session.execute(
                select(ScheduleItemModel.schedule_id, ScheduleItemModel.status)
                .where(ScheduleItemModel.schedule_id.in_([schedule_id, schedule2_id]))
            )).all()
        }
        assert statuses[str(schedule_id)] == "PUBLISHED"
        assert statuses[str(schedule2_id)] == "SKIPPED"
        pubs = (await session.execute(select(PublicationModel).where(PublicationModel.artifact_id == artifact_id))).scalars().all()
        assert len(pubs) == 1

@pytest.mark.asyncio
async def test_media_preview_draft_and_send_share_original_text(monkeypatch):
    from app.api.artifacts import create_telegram_media_draft_for_artifact
    from app.application.telegram_batch_preview import preview_telegram_batch
    from app.application.publications import ApproveAndPublish
    from sqlalchemy import select
    from uuid import UUID
    uid=await _media_artifact(caption='وصف قديم')
    uid=UUID(str(uid))
    monkeypatch.setenv('TELEGRAM_DESTINATION_ID','synthetic-only')
    class Capture(FakePublisher):
        seen=None
        async def publish(self,**kwargs):
            self.seen=kwargs['content']
            return await super().publish(**kwargs)
    capture=Capture()
    async with SessionFactory() as session:
        row=await session.get(ArtifactModel,uid)
        row.content='نص أصلي مختلف'
        await session.commit()
        preview=await preview_telegram_batch(session,[uid])
        assert preview['items'][0]['content']=='نص أصلي مختلف'
        draft=await create_telegram_media_draft_for_artifact(uid,session)
        assert draft['content']=='نص أصلي مختلف'
        await ApproveAndPublish(capture).execute(session,UUID(draft['id']))
        assert capture.seen=='نص أصلي مختلف'

@pytest.mark.asyncio
async def test_sticker_draft_and_send_have_no_caption(monkeypatch):
    from app.api.artifacts import create_telegram_media_draft_for_artifact
    from app.application.telegram_batch_preview import preview_telegram_batch
    from app.application.publications import ApproveAndPublish
    from uuid import UUID
    uid=UUID(str(await _media_artifact(caption='عنوان محفوظ وليس تعليق نشر')))
    monkeypatch.setenv('TELEGRAM_DESTINATION_ID','synthetic-sticker')
    class Capture(FakePublisher):
        seen=None
        async def publish(self,**kwargs):
            self.seen=kwargs['content']
            return await super().publish(**kwargs)
    capture=Capture()
    async with SessionFactory() as session:
        row=await session.get(ArtifactModel,uid)
        row.kind='STICKER';row.mime_type='image/webp'
        await session.commit()
        preview=await preview_telegram_batch(session,[uid])
        assert preview['items'][0]['content']==''
        draft=await create_telegram_media_draft_for_artifact(uid,session)
        assert draft['content']==''
        await ApproveAndPublish(capture).execute(session,UUID(draft['id']))
        assert capture.seen==''
