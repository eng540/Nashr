import httpx
import pytest

from app.application.platform_variants import DerivePlatformVariant, PLATFORM_PROFILES
from app.application.artifacts import persist_generic_artifact
from app.domain.artifacts import Artifact, ArtifactKind, ArtifactStatus
from app.infrastructure.database.models import KnowledgeUnitModel, SourceModel
from app.infrastructure.database.session import SessionFactory
from app.main import app
from datetime import datetime, timezone
from uuid import uuid4


def _test_contract(max_chars=None):
    return {
        "output_contract": {
            "contract_id": str(uuid4()),
            "version_id": str(uuid4()),
            "key": "TEST_TEXT_SOURCE",
            "version": 1,
            "definition": {
                "artifact_kind": "TEXT",
                "mime_type": "text/plain",
                "content_mode": "INLINE",
                "required_metadata_fields": ["source_type"],
                "max_content_chars": max_chars,
            },
        }
    }


async def _seed_text_artifact(content: str) -> str:
    now = datetime.now(timezone.utc)
    async with SessionFactory() as session:
        source_id, unit_id = uuid4(), uuid4()
        session.add(SourceModel(
            id=source_id, filename="variant-source.txt", mime_type="text/plain",
            storage_path="s3://test/variant-source.txt", size_bytes=len(content.encode()),
            status="STORED", content_sha256="a" * 64,
        ))
        session.add(KnowledgeUnitModel(
            id=unit_id, source_id=source_id, position=1, title="مادة اختبار النسخ",
            kind="TEXT", content=content[:500], source_reference="variant-source.txt",
        ))
        artifact = Artifact(
            id=uuid4(), source_knowledge_unit_id=unit_id, kind=ArtifactKind.TEXT,
            content=content, status=ArtifactStatus.AVAILABLE.value,
            created_at=now, updated_at=now, mime_type="text/plain",
            metadata={"source_type": "TEST_SEED"},
        )
        saved = await persist_generic_artifact(session, artifact, resolved_context=_test_contract())
        await session.commit()
        return str(saved.id)


LONG_ARABIC = "هذا نص عربي طويل مخصص لاختبار اشتقاق نسخ المنصات من المخرجات المعتمدة. " * 8  # ~640 chars


@pytest.mark.asyncio
async def test_platform_variant_requires_approved_source():
    artifact_id = await _seed_text_artifact("نص قصير غير معتمد بعد")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/artifacts/{artifact_id}/platform-variant", json={"platform": "x"})
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_x_variant_trims_weighted_and_refreshes_idempotently():
    artifact_id = await _seed_text_artifact(LONG_ARABIC)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        approve = await client.post(f"/api/artifacts/{artifact_id}/approve", json={"review_note": None})
        assert approve.status_code == 200, approve.text

        first = await client.post(f"/api/artifacts/{artifact_id}/platform-variant", json={"platform": "x"})
        assert first.status_code == 201, first.text
        body = first.json()
        assert body["review_status"] == "DRAFT"
        assert body["metadata"]["platform"] == "x"
        assert body["metadata"]["source_artifact_id"] == artifact_id
        assert body["metadata"]["constraints"]["trimmed"] is True
        measure = PLATFORM_PROFILES["x"]["measure"]
        assert measure(body["content"]) <= PLATFORM_PROFILES["x"]["max_text"]
        assert body["output_contract_key"] == "PLATFORM_VARIANT_X"

        second = await client.post(f"/api/artifacts/{artifact_id}/platform-variant", json={"platform": "x"})
        assert second.status_code == 201, second.text
        assert second.json()["id"] == body["id"], "Re-derivation must refresh the existing DRAFT variant."


@pytest.mark.asyncio
async def test_tiktok_variant_keeps_text_under_utf16_limit_without_trimming_short_text():
    artifact_id = await _seed_text_artifact(LONG_ARABIC)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(f"/api/artifacts/{artifact_id}/approve", json={"review_note": None})
        resp = await client.post(f"/api/artifacts/{artifact_id}/platform-variant", json={"platform": "tiktok"})
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["content"] == LONG_ARABIC, "Text within the TikTok limit must not be trimmed."
        assert body["metadata"]["constraints"]["trimmed"] is False
        assert body["metadata"]["constraints"]["measure"] == "utf16_units"


@pytest.mark.asyncio
async def test_unknown_platform_rejected():
    artifact_id = await _seed_text_artifact("نص")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(f"/api/artifacts/{artifact_id}/approve", json={"review_note": None})
        resp = await client.post(f"/api/artifacts/{artifact_id}/platform-variant", json={"platform": "snapchat"})
        assert resp.status_code == 422


async def _seed_post(content: str, status: str) -> str:
    now = datetime.now(timezone.utc)
    async with SessionFactory() as session:
        from app.infrastructure.database.models import PostModel
        source_id, unit_id = uuid4(), uuid4()
        session.add(SourceModel(
            id=source_id, filename="variant-post-source.txt", mime_type="text/plain",
            storage_path="s3://test/variant-post-source.txt", size_bytes=len(content.encode()),
            status="STORED", content_sha256="c" * 64,
        ))
        session.add(KnowledgeUnitModel(
            id=unit_id, source_id=source_id, position=1, title="مادة منشور اختبار النسخ",
            kind="TEXT", content=content[:500], source_reference="variant-post-source.txt",
        ))
        post = PostModel(
            id=uuid4(), knowledge_unit_id=unit_id, content=content, status=status,
            reviewed_at=now if status == "APPROVED" else None,
        )
        session.add(post)
        await session.commit()
        return str(post.id)


@pytest.mark.asyncio
async def test_trim_prefers_sentence_boundary_and_never_splits_urls():
    from app.application.platform_variants import _trim_to_limit, PLATFORM_PROFILES as profiles
    profile = profiles["x"]
    limit = profile["max_text"]
    measure = profile["measure"]
    url = "https://example.com/article/" + "a" * 60
    sentence = "هذه جملة عربية كاملة المعنى تنتهي بنقطة. "

    # n is the largest sentence count that still leaves room for the URL (23 units + space).
    n = 0
    while measure(sentence * (n + 1)) + 1 + 23 <= limit:
        n += 1

    # URL fits: it must survive intact, and any later overflow is cut at a sentence boundary.
    text_fits = sentence * n + " " + url + " " + sentence * 5
    trimmed, was_trimmed, boundary = _trim_to_limit(text_fits, profile)
    assert was_trimmed is True
    assert measure(trimmed) <= limit
    assert url in trimmed, "A URL that fits whole must be preserved."
    assert boundary == "sentence"

    # URL does not fit: it must be excluded whole, never split, and the cut lands on a sentence end.
    text_overflow = sentence * (n + 1) + " " + url + " " + sentence * 5
    trimmed2, was_trimmed2, boundary2 = _trim_to_limit(text_overflow, profile)
    assert was_trimmed2 is True
    assert measure(trimmed2) <= limit
    assert url not in trimmed2, "A URL that cannot fit whole must be excluded, never split."
    assert trimmed2.endswith(".")
    assert boundary2 == "sentence"


@pytest.mark.asyncio
async def test_trim_never_splits_arabic_combining_clusters():
    from app.application.platform_variants import _trim_to_limit, PLATFORM_PROFILES as profiles, _COMBINING_RE
    profile = PLATFORM_PROFILES["tiktok"]
    base = "مُتَحَرِّكٌ بِالتَّشْكِيلِ " + ("نص عادي يملأ المساحة حتى الحد. " * 120)
    trimmed, was_trimmed, _ = _trim_to_limit(base, profile)
    assert was_trimmed is True
    assert profile["measure"](trimmed) <= profile["max_text"]
    assert not _COMBINING_RE.match(trimmed[-1]), "Trimmed text must not end on a bare combining mark."


@pytest.mark.asyncio
async def test_variant_metadata_marks_length_only_adaptation_and_review_need():
    artifact_id = await _seed_text_artifact(LONG_ARABIC)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(f"/api/artifacts/{artifact_id}/approve", json={"review_note": None})
        resp = await client.post(f"/api/artifacts/{artifact_id}/platform-variant", json={"platform": "x"})
        assert resp.status_code == 201, resp.text
        meta = resp.json()["metadata"]
        assert meta["adaptation"] == "length_only"
        assert meta["needs_review"] is True
        assert meta["constraints"]["original_length"] > meta["constraints"]["measured_length"]
        assert meta["constraints"]["trim_boundary"] in {"sentence", "word", "hard"}
        assert any("تجهيز طول فقط" in note for note in meta["notes_ar"])


@pytest.mark.asyncio
async def test_post_variant_derives_from_approved_post_and_refreshes():
    post_id = await _seed_post(LONG_ARABIC, "APPROVED")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(f"/api/artifacts/post-source/{post_id}/platform-variant", json={"platform": "x"})
        assert first.status_code == 201, first.text
        body = first.json()
        assert body["kind"] == "TEXT"
        assert body["review_status"] == "DRAFT"
        assert body["metadata"]["source_post_id"] == post_id
        assert body["metadata"]["source_kind_ar"] == "منشور تحريري معتمد"
        measure = PLATFORM_PROFILES["x"]["measure"]
        assert measure(body["content"]) <= PLATFORM_PROFILES["x"]["max_text"]
        assert body["metadata"]["constraints"]["trimmed"] is True

        second = await client.post(f"/api/artifacts/post-source/{post_id}/platform-variant", json={"platform": "x"})
        assert second.status_code == 201, second.text
        assert second.json()["id"] == body["id"], "Re-derivation must refresh the existing DRAFT variant."


@pytest.mark.asyncio
async def test_post_variant_requires_approved_post():
    post_id = await _seed_post("مسودة منشور قصيرة", "DRAFT")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/artifacts/post-source/{post_id}/platform-variant", json={"platform": "x"})
        assert resp.status_code == 422
        missing = await client.post(f"/api/artifacts/post-source/{uuid4()}/platform-variant", json={"platform": "x"})
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_platform_variants_listing_surfaces_drafts_with_honest_metadata():
    artifact_id = await _seed_text_artifact(LONG_ARABIC)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        approve = await client.post(f"/api/artifacts/{artifact_id}/approve", json={"review_note": None})
        assert approve.status_code == 200, approve.text
        derived = await client.post(
            f"/api/artifacts/{artifact_id}/platform-variant", json={"platform": "tiktok"}
        )
        assert derived.status_code == 201, derived.text

        listing = await client.get("/api/artifacts/platform-variants")
        assert listing.status_code == 200, listing.text
        items = listing.json()
        match = [item for item in items if item["source_artifact_id"] == artifact_id]
        assert len(match) == 1
        item = match[0]
        assert item["platform"] == "tiktok"
        assert item["adaptation"] == "length_only"
        assert item["needs_review"] is True
        assert item["review_status"] == "DRAFT"
        assert item["constraints"]["max_text"] == PLATFORM_PROFILES["tiktok"]["max_text"]
        assert item["excerpt"]
        # The approved seed artifact itself is not a variant and must not appear.
        assert all(entry["id"] != artifact_id for entry in items)


def _media_contract():
    return {
        "output_contract": {
            "contract_id": str(uuid4()),
            "version_id": str(uuid4()),
            "key": "TEST_MEDIA_UPLOAD",
            "version": 1,
            "definition": {
                "artifact_kind": "IMAGE",
                "mime_type": "image/png",
                "content_mode": "STORAGE_URI",
                "required_metadata_fields": ["source_type"],
                "max_content_chars": None,
            },
        }
    }


async def _seed_media_artifact(caption: str | None) -> str:
    now = datetime.now(timezone.utc)
    async with SessionFactory() as session:
        source_id, unit_id = uuid4(), uuid4()
        session.add(SourceModel(
            id=source_id, filename="variant-media.png", mime_type="image/png",
            storage_path="s3://test/variant-media.png", size_bytes=179,
            status="STORED", content_sha256="b" * 64,
        ))
        session.add(KnowledgeUnitModel(
            id=unit_id, source_id=source_id, position=1, title="مادة وسائط اختبار النسخ",
            kind="IMAGE", content=(caption or "")[:500], source_reference="variant-media.png",
        ))
        metadata = {"source_type": "MEDIA_BANK_UPLOAD"}
        if caption is not None:
            metadata["caption"] = caption
        artifact = Artifact(
            id=uuid4(), source_knowledge_unit_id=unit_id, kind=ArtifactKind.IMAGE,
            content=None, status=ArtifactStatus.AVAILABLE.value,
            created_at=now, updated_at=now, mime_type="image/png",
            storage_uri="s3://test-bucket/variant-media.png",
            metadata=metadata,
        )
        saved = await persist_generic_artifact(session, artifact, resolved_context=_media_contract())
        await session.commit()
        return str(saved.id)


@pytest.mark.asyncio
async def test_media_variant_uses_caption_and_preserves_storage_reference():
    caption = "وصف عربي طويل لصورة مرفوعة في بنك الوسائط مخصص لاختبار اشتقاق نسخة منصة إكس. " * 8
    artifact_id = await _seed_media_artifact(caption)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        approve = await client.post(f"/api/artifacts/{artifact_id}/approve", json={})
        assert approve.status_code == 200, approve.text
        derived = await client.post(f"/api/artifacts/{artifact_id}/platform-variant", json={"platform": "x"})
        assert derived.status_code == 201, derived.text
        variant = derived.json()
        assert variant["kind"] == "IMAGE"
        assert variant["storage_uri"] == "s3://test-bucket/variant-media.png"
        assert variant["content"] is None
        assert variant["metadata"]["source_type"] == "PLATFORM_VARIANT"
        assert variant["metadata"]["constraints"]["trimmed"] is True

        listing = await client.get("/api/artifacts/platform-variants")
        match = [i for i in listing.json() if i["source_artifact_id"] == artifact_id]
        assert len(match) == 1
        assert match[0]["kind"] == "IMAGE"
        assert match[0]["mime_type"] == "image/png"
        assert match[0]["content"].strip()
        assert match[0]["full_length"] == len(match[0]["content"])


@pytest.mark.asyncio
async def test_media_variant_requires_nonempty_caption():
    artifact_id = await _seed_media_artifact(None)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        approve = await client.post(f"/api/artifacts/{artifact_id}/approve", json={})
        assert approve.status_code == 200, approve.text
        derived = await client.post(f"/api/artifacts/{artifact_id}/platform-variant", json={"platform": "x"})
        assert derived.status_code == 422, derived.text


@pytest.mark.asyncio
@pytest.mark.parametrize('media', [False, True])
async def test_rederive_preserves_saved_edits_and_independent_approval(media):
    from uuid import UUID
    from app.infrastructure.database.models import ArtifactModel
    artifact_id = await (_seed_media_artifact('original media caption') if media else _seed_text_artifact('original text'))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        await client.post(f'/api/artifacts/{artifact_id}/approve', json={})
        first = (await client.post(f'/api/artifacts/{artifact_id}/platform-variant',json={'platform':'x'})).json()
        uid = first['id']
        edited = 'تعليق مستقل عُدّل بيد المستخدم'
        body = {'metadata':{**first['metadata'],'caption':edited}} if media else {'content':edited}
        update = await client.patch(f'/api/artifacts/{uid}',json=body)
        assert update.status_code == 200, update.text
        assert update.json()['metadata']['caption'] == edited
        repeat = await client.post(f'/api/artifacts/{artifact_id}/platform-variant',json={'platform':'x'})
        assert repeat.status_code == 201, repeat.text
        assert repeat.json()['id'] == uid
        assert repeat.json()['metadata']['caption'] == edited
        assert repeat.json()['content'] == (None if media else edited)
        approve = await client.post(f'/api/artifacts/{uid}/approve',json={})
        assert approve.status_code == 200, approve.text
        assert approve.json()['metadata']['needs_review'] is False
        blocked = await client.patch(f'/api/artifacts/{uid}',json=body)
        assert blocked.status_code == 409
        async with SessionFactory() as session:
            original = await session.get(ArtifactModel,UUID(artifact_id))
            assert (original.artifact_metadata.get('caption') if media else original.content) == ('original media caption' if media else 'original text')


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [('platform','instagram'),('source_artifact_id','fake'),('constraints',{}),('source_type','OTHER')])
async def test_variant_provenance_is_immutable(field,value):
    artifact_id = await _seed_text_artifact('نص معتمد')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        await client.post(f'/api/artifacts/{artifact_id}/approve',json={})
        first = (await client.post(f'/api/artifacts/{artifact_id}/platform-variant',json={'platform':'x'})).json()
        change = await client.patch('/api/artifacts/'+first['id'],json={'metadata':{**first['metadata'],field:value}})
        assert change.status_code == 409, change.text


@pytest.mark.asyncio
async def test_media_variant_rejects_overlength_and_empty_caption():
    artifact_id = await _seed_media_artifact('تعليق')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        await client.post(f'/api/artifacts/{artifact_id}/approve',json={})
        first = (await client.post(f'/api/artifacts/{artifact_id}/platform-variant',json={'platform':'x'})).json()
        for text in ['','ك'*281,'😀'*141]:
            response = await client.patch('/api/artifacts/'+first['id'],json={'metadata':{**first['metadata'],'caption':text}})
            assert response.status_code == 409, response.text


@pytest.mark.asyncio
async def test_concurrent_derivation_reuses_one_draft():
    import asyncio
    artifact_id = await _seed_text_artifact('نص متزامن')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        await client.post(f'/api/artifacts/{artifact_id}/approve',json={})
        responses=await asyncio.gather(*[client.post(f'/api/artifacts/{artifact_id}/platform-variant',json={'platform':'x'}) for _ in range(3)])
        assert all(r.status_code == 201 for r in responses)
        assert len({r.json()['id'] for r in responses}) == 1
