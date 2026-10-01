from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from pypdf import PdfReader, PdfWriter
from sqlalchemy import select

from app.adapters.drafting.fake import FakeEditorialDrafter
from app.adapters.publishing.fake import FakePublisher
from app.application.publications import ApproveAndPublish, CreateTelegramDraft
from app.infrastructure.database.models import KnowledgeUnitModel, PostModel, SourceModel
from app.infrastructure.database.session import SessionFactory


async def _knowledge_unit() -> UUID:
    """Create an isolated knowledge unit for publication tests."""
    source_id, unit_id = uuid4(), uuid4()
    async with SessionFactory() as session:
        session.add(SourceModel(id=source_id, filename="p.pdf", mime_type="application/pdf", storage_path="./storage/test/p.pdf", size_bytes=10, status="STORED"))
        session.add(KnowledgeUnitModel(id=unit_id, source_id=source_id, position=1, title="Title", content="Content"))
        await session.commit()
    return unit_id


async def test_create_and_publish_with_fake_publisher() -> None:
    """Verify draft approval and publication ledger success."""
    unit_id = await _knowledge_unit()
    async with SessionFactory() as session:
        draft = await CreateTelegramDraft(FakeEditorialDrafter()).execute(session, unit_id, "@test")
        assert draft.status.value == "DRAFT"
        post = (await session.execute(select(PostModel).where(PostModel.id == draft.id))).scalar_one_or_none()
        assert post is None
        post = (await session.execute(select(PostModel).where(PostModel.knowledge_unit_id == unit_id))).scalar_one()
        assert post.content == draft.content
        edited_content = "**نسخة محررة**\\n\\nنص عدله المستخدم.\\n\\n📚 p.pdf\\n#اختبار"
        published = await ApproveAndPublish(FakePublisher()).execute(session, draft.id, edited_content)
        assert published.status.value == "PUBLISHED"
        assert published.external_id == "test_msg_999"
        assert published.content == edited_content


class RecordingDrafter(FakeEditorialDrafter):
    """Capture the visual grounding payload passed by the production use case."""

    def __init__(self) -> None:
        self.pdf_slice: bytes | None = None

    async def draft(self, *, title: str, content: str, source_name: str, pdf_slice: bytes | None = None) -> str:
        self.pdf_slice = pdf_slice
        return await super().draft(
            title=title,
            content=content,
            source_name=source_name,
            pdf_slice=pdf_slice,
        )


def _pdf_bytes(page_count: int) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=200, height=200)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


async def test_create_draft_passes_visual_slice_and_restores_source() -> None:
    source_id, unit_id = uuid4(), uuid4()
    async with SessionFactory() as session:
        session.add(
            SourceModel(
                id=source_id,
                filename="visual.pdf",
                mime_type="application/pdf",
                storage_path="./storage/test/visual-source.pdf",
                size_bytes=10,
                status="STORED",
                file_payload=_pdf_bytes(12),
            )
        )
        session.add(
            KnowledgeUnitModel(
                id=unit_id,
                source_id=source_id,
                position=1,
                title="Visual title",
                content="Visual content",
                discovery_page_start=5,
                discovery_page_end=6,
            )
        )
        await session.commit()

        drafter = RecordingDrafter()
        draft = await CreateTelegramDraft(drafter).execute(session, unit_id, "@test")

        assert draft.status.value == "DRAFT"
        assert drafter.pdf_slice is not None
        assert len(PdfReader(BytesIO(drafter.pdf_slice)).pages) == 10
        assert Path("./storage/test/visual-source.pdf").is_file()


class FailingPublisher(FakePublisher):
    """Simulate a platform failure."""

    async def publish(self, *, destination: str, content: str):
        """Raise a deterministic publish failure."""
        raise RuntimeError("telegram unavailable")


async def test_publish_failure_is_recorded() -> None:
    """Verify publisher failure becomes FAILED without escaping the use case."""
    unit_id = await _knowledge_unit()
    async with SessionFactory() as session:
        draft = await CreateTelegramDraft(FakeEditorialDrafter()).execute(session, unit_id, "@test")
        result = await ApproveAndPublish(FailingPublisher()).execute(session, draft.id)
        assert result.status.value == "FAILED"
        assert result.error_message == "telegram unavailable"
