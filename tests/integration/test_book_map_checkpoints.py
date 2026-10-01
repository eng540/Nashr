from uuid import uuid4

import pytest
from sqlalchemy import select

from app.application.discover_book import DiscoverBook
from app.domain.book_map import BookMap, BookTopic
from app.domain.extraction import DocumentReference
from app.infrastructure.database.models import BookMapSectionModel, SourceModel
from app.infrastructure.database.session import SessionFactory
from app.adapters.extraction.gemini import GeminiBookMap, GeminiTopic


class CheckpointMapper:
    def __init__(self) -> None:
        self.fail_section = 2
        self.calls: list[int] = []

    async def prepare_document(self, source):
        return DocumentReference("fake-document", "fake://document", "application/pdf")

    async def plan_book_sections(self, source):
        return [(1, 64), (65, 128)]

    async def map_book_section(self, source, document, page_start, page_end, section_index):
        self.calls.append(section_index)
        if section_index == self.fail_section:
            raise RuntimeError("simulated Gemini 503")
        return [
            GeminiBookMap(
                title=f"Local {section_index}",
                description=f"Local section {section_index}",
                topics=[
                    GeminiTopic(
                        position=1,
                        title=f"Topic {section_index}",
                        description="Evidence",
                        source_reference=f"pages {page_start}-{page_end}",
                        page_start=page_start,
                        page_end=page_end,
                    )
                ],
            )
        ]

    async def merge_book_maps(self, source, local_maps, page_count, section_count):
        topics = []
        for position, local in enumerate(local_maps, start=1):
            topic = local.topics[0]
            topics.append(
                BookTopic.create(
                    source.id,
                    position,
                    topic.title,
                    topic.description,
                    topic.source_reference,
                    topic.page_start,
                    topic.page_end,
                )
            )
        return BookMap(source.id, source.filename, "Merged", topics)


async def _new_source():
    source_id = uuid4()
    async with SessionFactory() as session:
        session.add(SourceModel(
            id=source_id,
            filename="checkpoint-test.pdf",
            mime_type="application/pdf",
            storage_path="./storage/test/checkpoint-test.pdf",
            size_bytes=10,
            status="STORED",
            content_sha256="checkpoint-test-hash",
            file_payload=b"%PDF-test",
        ))
        await session.commit()
    return source_id


@pytest.mark.asyncio
async def test_book_map_sections_resume_without_repeating_completed_gemini_work():
    source_id = await _new_source()
    mapper = CheckpointMapper()
    use_case = DiscoverBook(mapper, material_discoverer=None)
    document = DocumentReference("fake-document", "fake://document", "application/pdf")

    with pytest.raises(RuntimeError, match="simulated Gemini 503"):
        async with SessionFactory() as session:
            await use_case.build_book_map(session, source_id, document)

    async with SessionFactory() as session:
        rows = (await session.execute(
            select(BookMapSectionModel)
            .where(BookMapSectionModel.source_id == source_id)
            .order_by(BookMapSectionModel.section_index)
        )).scalars().all()
        assert [(row.section_index, row.status) for row in rows] == [
            (1, "COMPLETED"),
            (2, "FAILED"),
        ]
        assert rows[0].payload

    mapper.fail_section = None
    async with SessionFactory() as session:
        book_map = await use_case.build_book_map(session, source_id, document)

    assert mapper.calls == [1, 2, 2]
    assert [topic.position for topic in book_map.topics] == [1, 2]

    async with SessionFactory() as session:
        rows = (await session.execute(
            select(BookMapSectionModel)
            .where(BookMapSectionModel.source_id == source_id)
            .order_by(BookMapSectionModel.section_index)
        )).scalars().all()
        assert all(row.status == "COMPLETED" for row in rows)
