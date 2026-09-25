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
    """Verify PDF ingestion through a PUBLISHED ledger entry."""
    pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
    async with SessionFactory() as session:
        source = await IngestPdf(LocalFileStorage("./storage/test")).execute(session, "e2e.pdf", "application/pdf", pdf)
        units = await ExtractKnowledge(FakeExtractor()).execute(session, source.id)
        assert len(units) == 5
        draft = await CreateTelegramDraft(FakeEditorialDrafter()).execute(session, units[0].id, "@test")
        edited_content = "**تحرير المستخدم**\\n\\nالنص النهائي.\\n\\n📚 e2e.pdf\\n#اختبار"\n        published = await ApproveAndPublish(FakePublisher()).execute(session, draft.id, edited_content)
        assert published.status.value == "PUBLISHED"
        assert published.external_id == "test_msg_999"\n        assert published.content == edited_content
        row = (await session.execute(select(PublicationModel).where(PublicationModel.id == draft.id))).scalar_one()
        assert row.status == "PUBLISHED"
        assert row.external_id == "test_msg_999"\n        assert row.content == edited_content
        assert row.published_at is not None
