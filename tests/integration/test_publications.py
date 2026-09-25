from uuid import UUID, uuid4

from app.adapters.drafting.fake import FakeEditorialDrafter
from app.adapters.publishing.fake import FakePublisher
from app.application.publications import ApproveAndPublish, CreateTelegramDraft
from app.infrastructure.database.models import KnowledgeUnitModel, SourceModel
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
        edited_content = "**نسخة محررة**\\n\\nنص عدله المستخدم.\\n\\n📚 p.pdf\\n#اختبار"\n        published = await ApproveAndPublish(FakePublisher()).execute(session, draft.id, edited_content)
        assert published.status.value == "PUBLISHED"
        assert published.external_id == "test_msg_999"\n        assert published.content == edited_content


class FailingPublisher(FakePublisher):
    """Simulate a platform failure."""

    async def publish(self, *, destination: str, content: str):
        """Raise a deterministic publish failure."""
        raise RuntimeError("telegram unavailable")


async def test_publish_failure_is_recorded() -> None:
    """Verify publisher failure becomes FAILED without escaping the use case."""
    unit_id = await _knowledge_unit()
    async with SessionFactory() as session:
        draft = await CreateTelegramDraft().execute(session, unit_id, "@test")
        result = await ApproveAndPublish(FailingPublisher()).execute(session, draft.id)
        assert result.status.value == "FAILED"
        assert result.error_message == "telegram unavailable"
