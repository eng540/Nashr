from app.adapters.drafting.fake import FakeEditorialDrafter
from app.adapters.extraction.fake import FakeExtractor
from app.adapters.publishing.fake import FakePublisher
from app.application.extract_knowledge import ExtractKnowledge
from app.application.ingest_pdf import IngestPdf
from app.application.publications import ApproveAndPublish, CreateTelegramDraft
from app.infrastructure.database.models import PublicationModel
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.storage import LocalFileStorage
from sqlalchemy import select


async def test_vertical_slice_e2e() -> None:
    """Verify PDF ingestion through a PUBLISHED ledger entry with provenance."""
    pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
    async with SessionFactory() as session:
        source = await IngestPdf(LocalFileStorage("./storage/test")).execute(session, "e2e.pdf", "application/pdf", pdf)
        units = await ExtractKnowledge(FakeExtractor()).execute(session, source.id)
        assert len(units) == 5
        selected = units[0]
        assert selected.source_id == source.id
        assert selected.original_text is not None
        assert selected.source_reference is not None
        draft = await CreateTelegramDraft(FakeEditorialDrafter()).execute(session, selected.id, "@test")
        edited_content = "**نسخة محررة**\\n\\nنص عدله المستخدم.\\n\\n📚 e2e.pdf\\n#اختبار"
        published = await ApproveAndPublish(FakePublisher()).execute(session, draft.id, edited_content)
        assert published.status.value == "PUBLISHED"
        assert published.external_id == "test_msg_999"
        assert published.content == edited_content
        row = (await session.execute(select(PublicationModel).where(PublicationModel.id == draft.id))).scalar_one()
        assert row.status == "PUBLISHED"
        assert row.external_id == "test_msg_999"
        assert row.content == edited_content
        assert row.published_at is not None
        assert row.knowledge_unit_id == selected.id
