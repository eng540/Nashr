from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.adapters.drafting.fake import FakeEditorialDrafter
from app.application.posts import ProducePost
from app.infrastructure.database.models import (
    KnowledgeUnitModel,
    PostModel,
    PublicationModel,
    SourceModel,
    TopicModel,
)
from app.infrastructure.database.session import SessionFactory
from app.main import app


async def _fixture():
    source_a, source_b = uuid4(), uuid4()
    topic_a1, topic_a2, topic_b1 = uuid4(), uuid4(), uuid4()
    units = []
    async with SessionFactory() as session:
        session.add_all([
            SourceModel(id=source_a, filename="book-a.pdf", mime_type="application/pdf", storage_path="./storage/test/a.pdf", size_bytes=10, status="STORED", book_title="Book A"),
            SourceModel(id=source_b, filename="book-b.pdf", mime_type="application/pdf", storage_path="./storage/test/b.pdf", size_bytes=10, status="STORED", book_title="Book B"),
            TopicModel(id=topic_a1, source_id=source_a, position=1, title="Topic A1", description="A1"),
            TopicModel(id=topic_a2, source_id=source_a, position=2, title="Topic A2", description="A2"),
            TopicModel(id=topic_b1, source_id=source_b, position=1, title="Topic B1", description="B1"),
        ])
        unique = str(source_a)[:8]
        for position, (source_id, topic_id, title) in enumerate([
            (source_a, topic_a1, f"Alpha-{unique}"),
            (source_a, topic_a2, "Beta"),
            (source_b, topic_b1, "Gamma"),
        ], start=1):
            unit_id = uuid4()
            units.append(unit_id)
            session.add(KnowledgeUnitModel(
                id=unit_id, source_id=source_id, topic_id=topic_id,
                position=position, title=title, kind="حكمة", content=f"Content {title}",
            ))
        await session.commit()
    async with SessionFactory() as session:
        for unit_id in units:
            post = PostModel(id=uuid4(), knowledge_unit_id=unit_id, content=f"Post {unit_id}", status="DRAFT")
            session.add(post)
        await session.commit()
        posts = (await session.execute(
            select(PostModel).where(PostModel.knowledge_unit_id.in_(units))
        )).scalars().all()
        post_by_unit = {p.knowledge_unit_id: p.id for p in posts}
    return source_a, source_b, topic_a1, topic_a2, topic_b1, units, post_by_unit


@pytest.mark.asyncio
async def test_list_posts_returns_paginated_inventory_and_provenance():
    source_a, _, _, _, _, units, _ = await _fixture()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/posts?source_id={source_a}&limit=2&offset=0")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert len(payload["items"]) == 2
    item = payload["items"][0]
    assert {"post_id", "title", "status", "knowledge_unit_id", "topic_id", "topic_title", "source_id", "source_title", "content_preview", "created_at", "updated_at"} <= set(item)
    assert item["knowledge_unit_id"] in {str(x) for x in units}


@pytest.mark.asyncio
async def test_list_posts_filters_source_topic_and_status():
    source_a, _, topic_a1, _, _, _, _ = await _fixture()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        source_response = await client.get(f"/posts?source_id={source_a}")
        topic_response = await client.get(f"/posts?topic_id={topic_a1}")
        status_response = await client.get(f"/posts?source_id={source_a}&status=DRAFT")
    assert len(source_response.json()["items"]) == 2
    assert all(x["source_id"] == str(source_a) for x in source_response.json()["items"])
    assert all(x["topic_id"] == str(topic_a1) for x in topic_response.json()["items"])
    assert len(status_response.json()["items"]) == 2


@pytest.mark.asyncio
async def test_list_posts_searches_content_and_material_title():
    source_a, _, _, _, _, _, _ = await _fixture()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/posts?q={str(source_a)[:8]}")
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["title"].startswith("Alpha-")


@pytest.mark.asyncio
async def test_post_detail_exposes_provenance_and_publication_indicator():
    source_a, _, topic_a1, _, _, units, post_by_unit = await _fixture()
    async with SessionFactory() as session:
        session.add(PublicationModel(
            id=uuid4(), knowledge_unit_id=units[0], post_id=post_by_unit[units[0]],
            platform="telegram", destination="@test", content="Published content",
            status="PUBLISHED", external_id="msg-1",
        ))
        await session.commit()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/posts/{post_by_unit[units[0]]}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source_id"] == str(source_a)
    assert payload["topic_id"] == str(topic_a1)
    assert payload["knowledge_unit_id"] == str(units[0])
    assert payload["published"] is True


@pytest.mark.asyncio
async def test_patch_post_updates_canonical_content_and_persists():
    _, _, _, _, _, units, post_by_unit = await _fixture()
    post_id = post_by_unit[units[0]]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/posts/{post_id}",
            json={"content": "  Edited canonical content  "},
        )
        assert response.status_code == 200
        assert response.json()["content"] == "Edited canonical content"
        reread = await client.get(f"/posts/{post_id}")
    assert reread.status_code == 200
    assert reread.json()["content"] == "Edited canonical content"


@pytest.mark.asyncio
async def test_patch_post_rejects_empty_content_and_missing_post():
    _, _, _, _, _, _, _ = await _fixture()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        empty = await client.patch(f"/posts/{uuid4()}", json={"content": "   "})
        missing = await client.get(f"/posts/{uuid4()}")
    assert empty.status_code in {400, 422}
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_existing_post_is_not_duplicated():
    _, _, _, _, _, units, post_by_unit = await _fixture()
    unit_id = units[0]
    post_id = post_by_unit[unit_id]
    async with SessionFactory() as session:
        result = await ProducePost(FakeEditorialDrafter()).execute(session, unit_id)
        assert result.id == post_id
        count = len((await session.execute(
            select(PostModel).where(PostModel.knowledge_unit_id == unit_id)
        )).scalars().all())
    assert count == 1


@pytest.mark.asyncio
async def test_canonical_lookup_does_not_filter_by_draft_status():
    _, _, _, _, _, units, _ = await _fixture()
    unit_id = units[0]
    async with SessionFactory() as session:
        row = (await session.execute(select(PostModel).where(PostModel.knowledge_unit_id == unit_id))).scalar_one()
        row.status = "NON_DRAFT_TEST_STATE"
        await session.commit()
        found = await ProducePost(FakeEditorialDrafter())._find_existing(session, unit_id)
    assert found is not None
    assert found.id == row.id


@pytest.mark.asyncio
async def test_post_review_lifecycle_and_metadata():
    _, _, _, _, _, units, post_by_unit = await _fixture()
    post_id = post_by_unit[units[0]]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        approved = await client.post(f"/posts/{post_id}/approve", json={"note": "تمت المراجعة"})
        assert approved.status_code == 200
        assert approved.json()["status"] == "APPROVED"
        assert approved.json()["reviewed_at"] is not None
        assert approved.json()["review_note"] == "تمت المراجعة"

        duplicate = await client.post(f"/posts/{post_id}/approve", json={"note": "مرة أخرى"})
        assert duplicate.status_code == 409

        edited = await client.patch(f"/posts/{post_id}", json={"content": "Edited after approval"})
        assert edited.status_code == 200
        assert edited.json()["status"] == "DRAFT"
        assert edited.json()["reviewed_at"] is None
        assert edited.json()["review_note"] is None

        rejected = await client.post(f"/posts/{post_id}/reject", json={"reason": "يحتاج إعادة صياغة"})
        assert rejected.status_code == 200
        assert rejected.json()["status"] == "REJECTED"
        assert rejected.json()["review_note"] == "يحتاج إعادة صياغة"

        edited_again = await client.patch(f"/posts/{post_id}", json={"content": "Revised rejected content"})
        assert edited_again.status_code == 200
        assert edited_again.json()["status"] == "DRAFT"

        approved_again = await client.post(f"/posts/{post_id}/approve", json={"note": "مقبول"})
        assert approved_again.status_code == 200
        assert approved_again.json()["status"] == "APPROVED"

        reject_approved = await client.post(f"/posts/{post_id}/reject", json={"reason": "late"})
        assert reject_approved.status_code == 409


@pytest.mark.asyncio
async def test_reject_requires_reason_and_missing_post_is_404():
    _, _, _, _, _, units, post_by_unit = await _fixture()
    post_id = post_by_unit[units[0]]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        empty = await client.post(f"/posts/{post_id}/reject", json={"reason": "   "})
        missing = await client.post(f"/posts/{uuid4()}/approve", json={"note": "x"})
    assert empty.status_code == 400
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_production_post_is_created_as_draft():
    _, _, _, _, _, units, _ = await _fixture()
    async with SessionFactory() as session:
        result = await ProducePost(FakeEditorialDrafter()).execute(session, units[0])
    assert result.status.value == "DRAFT"


@pytest.mark.asyncio
async def test_posts_workspace_contains_editorial_review_controls_and_status_filters():
    from app.api.routes import posts_console
    response = await posts_console()
    body = response.body.decode("utf-8")
    assert 'value="APPROVED">APPROVED' in body
    assert 'value="REJECTED">REJECTED' in body
    assert "post-editor-approve" in body
    assert "post-editor-reject" in body
    assert "/approve" in body
    assert "/reject" in body



@pytest.mark.asyncio
async def test_bulk_approve_is_server_side_partial_and_idempotent() -> None:
    _, _, _, _, _, units, post_by_unit = await _fixture()
    ids = [post_by_unit[units[0]], post_by_unit[units[1]]]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/posts/bulk-approve", json={"post_ids": [str(ids[0]), str(ids[1])]})
        second = await client.post("/posts/bulk-approve", json={"post_ids": [str(ids[0]), str(ids[1]), str(uuid4())]})
    assert first.status_code == 200
    assert first.json()["approved_count"] == 2
    assert first.json()["failed_count"] == 0
    assert second.status_code == 200
    assert second.json()["approved_count"] == 0
    assert second.json()["failed_count"] == 3
    reasons = {row["reason_code"] for row in second.json()["results"]}
    assert reasons == {"ALREADY_APPROVED", "POST_NOT_FOUND"}


@pytest.mark.asyncio
async def test_post_bank_exposes_publication_state_filters() -> None:
    source_a, _, _, _, _, units, post_by_unit = await _fixture()
    published_id = post_by_unit[units[0]]
    async with SessionFactory() as session:
        session.add(PublicationModel(
            id=uuid4(), knowledge_unit_id=units[0], post_id=published_id,
            platform="telegram", destination="@test", content="published",
            status="PUBLISHED", external_id="published-filter",
        ))
        await session.commit()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        published = await client.get(f"/posts?source_id={source_a}&publication_state=PUBLISHED")
        unpublished = await client.get(f"/posts?source_id={source_a}&publication_state=UNPUBLISHED")
        eligible = await client.get(f"/posts?source_id={source_a}&publication_state=ELIGIBLE")
    assert published.status_code == 200
    assert unpublished.status_code == 200
    assert eligible.status_code == 200
    assert [row["post_id"] for row in published.json()["items"]] == [str(published_id)]
    assert str(published_id) not in {row["post_id"] for row in unpublished.json()["items"]}
    assert str(published_id) not in {row["post_id"] for row in eligible.json()["items"]}
