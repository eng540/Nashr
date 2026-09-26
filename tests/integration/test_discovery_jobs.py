from uuid import uuid4

from sqlalchemy import select

from app.application.discovery_jobs import (
    DiscoveryJobRunner,
    DiscoveryJobStatus,
    create_discovery_job,
    retry_discovery_job,
)
from app.domain.book_map import BookMap, BookTopic
from app.domain.extraction import DiscoverySpan, DocumentReference, ExtractedIdea
from app.infrastructure.database.models import DiscoveryJobModel, DiscoveryChunkModel, KnowledgeUnitModel, SourceModel, TopicModel
from app.infrastructure.database.session import SessionFactory


class TwoTopicMapper:
    async def prepare_document(self, source):
        return DocumentReference("fake-document", "fake://document", "application/pdf")

    async def map_book(self, source, document):
        return BookMap(
            source.id,
            source.filename,
            "Two topic test book",
            [
                BookTopic.create(source.id, 1, "Topic 1", "First", "pages 1-1", 1, 1),
                BookTopic.create(source.id, 2, "Topic 2", "Second", "pages 2-3", 2, 3),
            ],
        )


class ToggleDiscoverer:
    def __init__(self):
        self.fail_on_second = True
        self.spans: list[DiscoverySpan] = []

    async def discover_topic(self, source, topic, document, span):
        self.spans.append(span)
        if topic.position == 2 and self.fail_on_second:
            raise RuntimeError("simulated topic failure")
        return [
            ExtractedIdea(
                position=1,
                title=f"Material {topic.position}",
                content=f"Content {topic.position}",
                original_text=f"Original {topic.position}",
                source_reference=f"pages {span.page_start}-{span.page_end}",
                kind="نوع مكتشف",
            )
        ]


async def _new_source():
    source_id = uuid4()
    async with SessionFactory() as session:
        session.add(
            SourceModel(
                id=source_id,
                filename="job-test.pdf",
                mime_type="application/pdf",
                storage_path="./storage/test/job-test.pdf",
                size_bytes=10,
                status="STORED",
                content_sha256="test-hash",
            )
        )
        await session.commit()
    return source_id


async def test_discovery_job_checkpoints_failure_and_resumes() -> None:
    source_id = await _new_source()
    async with SessionFactory() as session:
        job = await create_discovery_job(session, source_id)

    discoverer = ToggleDiscoverer()
    runner = DiscoveryJobRunner(TwoTopicMapper(), discoverer)
    await runner.run(job.id)

    async with SessionFactory() as session:
        failed_job = (await session.execute(select(DiscoveryJobModel).where(DiscoveryJobModel.id == job.id))).scalar_one()
        topics = (await session.execute(select(TopicModel).where(TopicModel.source_id == source_id).order_by(TopicModel.position))).scalars().all()
        chunks = (await session.execute(select(DiscoveryChunkModel).join(TopicModel).where(TopicModel.source_id == source_id))).scalars().all()
        units = (await session.execute(select(KnowledgeUnitModel).where(KnowledgeUnitModel.source_id == source_id))).scalars().all()

        assert failed_job.status == DiscoveryJobStatus.FAILED
        assert failed_job.topics_total == 2
        assert failed_job.chunks_total == 2
        assert topics[0].discovery_status == "COMPLETED"
        assert topics[1].discovery_status == "FAILED"
        assert len(units) == 1
        assert [chunk.status for chunk in sorted(chunks, key=lambda item: item.chunk_index)] == ["COMPLETED", "FAILED"]

    discoverer.fail_on_second = False
    async with SessionFactory() as session:
        retry_job = await retry_discovery_job(session, source_id)

    assert retry_job.id == job.id
    await runner.run(retry_job.id)
    await runner.run(retry_job.id)

    async with SessionFactory() as session:
        final_job = (await session.execute(select(DiscoveryJobModel).where(DiscoveryJobModel.id == job.id))).scalar_one()
        topics = (await session.execute(select(TopicModel).where(TopicModel.source_id == source_id).order_by(TopicModel.position))).scalars().all()
        chunks = (await session.execute(select(DiscoveryChunkModel).join(TopicModel).where(TopicModel.source_id == source_id))).scalars().all()
        units = (await session.execute(select(KnowledgeUnitModel).where(KnowledgeUnitModel.source_id == source_id))).scalars().all()

        assert final_job.status == DiscoveryJobStatus.COMPLETED
        assert final_job.attempts == 2
        assert final_job.topics_completed == 2
        assert final_job.chunks_completed == 2
        assert final_job.materials_discovered == 2
        assert [topic.discovery_status for topic in topics] == ["COMPLETED", "COMPLETED"]
        assert [chunk.status for chunk in sorted(chunks, key=lambda item: item.chunk_index)] == ["COMPLETED", "COMPLETED"]
        assert len(units) == 2
        assert discoverer.spans == [
            DiscoverySpan(1, 1, 1),
            DiscoverySpan(2, 3, 1),
            DiscoverySpan(2, 3, 1),
        ]
