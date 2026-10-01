from app.adapters.drafting.fake import FakeEditorialDrafter
from app.adapters.extraction.fake import FakeExtractor
from app.adapters.publishing.fake import FakePublisher
from app.application.extract_knowledge import ExtractKnowledge
from app.application.ingest_pdf import IngestPdf
from app.application.publications import ApproveAndPublish, CreateTelegramDraft
from app.application.reviews import ReviewPost
from app.application.scheduling import create_schedule, process_due_schedule_items
from app.infrastructure.database.models import PostModel, PublicationModel
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.storage import LocalFileStorage
from sqlalchemy import select
from datetime import datetime, timedelta, timezone


async def test_vertical_slice_e2e() -> None:
    """Verify PDF ingestion through a PUBLISHED ledger entry with provenance."""
    pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
    async with SessionFactory() as session:
        source = await IngestPdf(LocalFileStorage("./storage/test")).execute(session, "e2e.pdf", "application/pdf", pdf)
        units = await ExtractKnowledge(FakeExtractor(6)).execute(session, source.id)
        assert len(units) == 6
        selected = units[0]
        assert selected.source_id == source.id
        assert selected.original_text is not None
        assert selected.source_reference is not None
        draft = await CreateTelegramDraft(FakeEditorialDrafter()).execute(session, selected.id, "@test")
        edited_content = "**نسخة محررة**\\n\\nنص عدله المستخدم.\\n\\n📚 e2e.pdf\\n#اختبار"
        post = (await session.execute(select(PostModel).where(PostModel.knowledge_unit_id == selected.id))).scalar_one()
        post.content = edited_content
        post.status = "DRAFT"
        await session.commit()
        await ReviewPost().approve(session, post.id, "تمت المراجعة")
        published = await ApproveAndPublish(FakePublisher()).execute(session, draft.id)
        assert published.status.value == "PUBLISHED"
        assert published.external_id == "test_msg_999"
        assert published.content == edited_content
        post = (await session.execute(select(PostModel).where(PostModel.knowledge_unit_id == selected.id))).scalar_one()
        assert post.content == edited_content
        assert post.status == "APPROVED"
        row = (await session.execute(select(PublicationModel).where(PublicationModel.id == draft.id))).scalar_one()
        assert row.status == "PUBLISHED"
        assert row.external_id == "test_msg_999"
        assert row.content == edited_content
        assert row.published_at is not None
        assert row.knowledge_unit_id == selected.id


@pytest.mark.asyncio
async def test_full_operational_publication_journey():
    pdf = b"%PDF-1.4\\n1 0 obj\\n<< /Type /Catalog >>\\nendobj\\n%%EOF\\n"
    async with SessionFactory() as session:
        source = await IngestPdf(LocalFileStorage("./storage/test")).execute(
            session, "operational-e2e.pdf", "application/pdf", pdf
        )
        units = await ExtractKnowledge(FakeExtractor(3)).execute(session, source.id)
        posts = []
        for unit in units:
            await CreateTelegramDraft(FakeEditorialDrafter()).execute(session, unit.id, "@test")
            post = (await session.execute(
                select(PostModel).where(PostModel.knowledge_unit_id == unit.id)
            )).scalar_one()
            await ReviewPost().approve(session, post.id, "approved for operational e2e")
            posts.append(post.id)
        schedule = await create_schedule(
            session,
            "Operational E2E",
            "Asia/Aden",
            [
                (post_id, datetime.now(timezone.utc) - timedelta(minutes=1 + index))
                for index, post_id in enumerate(posts)
            ],
            "operational-e2e-idempotency",
        )
        schedule.status = "ACTIVE"
        await session.commit()

    publisher = FakePublisher()
    await process_due_schedule_items(publisher=publisher, destination="@test")

    async with SessionFactory() as session:
        items = (await session.execute(
            select(ScheduleItemModel)
            .where(ScheduleItemModel.schedule_id == schedule.id)
            .order_by(ScheduleItemModel.position)
        )).scalars().all()
        publications = (await session.execute(
            select(PublicationModel).where(PublicationModel.post_id.in_(posts))
        )).scalars().all()
        assert len(items) == 3
        assert all(item.status == "PUBLISHED" for item in items)
        assert len(publications) == 3
        assert {item.publication_id for item in items} == {publication.id for publication in publications}
        assert all(publication.status == "PUBLISHED" for publication in publications)
        assert {publication.knowledge_unit_id for publication in publications} == {
            unit.id for unit in units
        }
