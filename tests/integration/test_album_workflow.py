import io
from uuid import uuid4
import pytest
from PIL import Image
from sqlalchemy import select
from app.application.media_bank import IngestReadyMedia
from app.application.telegram_albums import create_album, resolve_album
from app.application.generic_artifact_review import GenericArtifactReviewService
from app.application.artifacts import load_artifact
from app.application.publications import CreateTelegramDraft, ApproveAndPublish
from app.infrastructure.artifact_storage import S3ArtifactStorage
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import ArtifactModel, PublicationModel
from app.domain.publications import PublishResult
from tests.integration.test_media_bank_ingest import _FakeS3Client


async def setup_album(session):
    storage = S3ArtifactStorage(client=_FakeS3Client(), bucket='test')
    ids = []
    for color in ['green', 'blue']:
        out = io.BytesIO(); Image.new('RGB', (32,32), color).save(out, format='PNG')
        item = await IngestReadyMedia(storage=storage).execute(session, filename=color+'.png', content_type='image/png', data=out.getvalue(), caption=color)
        await GenericArtifactReviewService(session).approve(item.id)
        ids.append(str(item.id))
    album = await create_album(session, artifact_ids=ids, title='Private album test')
    return album, ids


@pytest.mark.asyncio
async def test_album_child_snapshot_revalidation_and_published_dedup(monkeypatch):
    async with SessionFactory() as session:
        album, ids = await setup_album(session)
        repeated = await create_album(session, artifact_ids=ids, title='Repeated click')
        assert repeated.id == album.id
        await GenericArtifactReviewService(session).approve(album.id)
        children,_ = await resolve_album(session, album.metadata)
        publication = await CreateTelegramDraft.execute_for_artifact(session, album, 'private-test')
        assert (await CreateTelegramDraft.execute_for_artifact(session, album, 'private-test')).id == publication.id
        async def get_bytes(self, uri, **kwargs): return b'png'
        monkeypatch.setattr(S3ArtifactStorage,'from_environment',lambda: S3ArtifactStorage(client=_FakeS3Client(),bucket='test'))
        monkeypatch.setattr(S3ArtifactStorage,'get_bytes',get_bytes)
        class Publisher:
            calls=0
            async def publish(self, **kwargs):
                self.calls+=1
                assert len(kwargs['album'])==2
                return PublishResult('100',('100','101'))
        pub=Publisher()
        result=await ApproveAndPublish(pub).execute(session,publication.id)
        assert result.external_ids==('100','101')
        with pytest.raises(ValueError,match='not a DRAFT'):
            await ApproveAndPublish(pub).execute(session,publication.id)
        assert pub.calls==1
        children[0].artifact_metadata={**children[0].artifact_metadata,'caption':'changed'}
        await session.commit()
        with pytest.raises(ValueError,match='changed'):
            await resolve_album(session,album.metadata)


@pytest.mark.asyncio
async def test_album_approval_requires_current_children_and_ambiguous_send_cannot_retry(monkeypatch):
    async with SessionFactory() as session:
        album, ids=await setup_album(session)
        child=(await session.execute(select(ArtifactModel).where(ArtifactModel.id==__import__('uuid').UUID(ids[0])))).scalar_one()
        child.review_status='REJECTED'; await session.commit()
        with pytest.raises(ValueError,match='approved'):
            await GenericArtifactReviewService(session).approve(album.id)
        child.review_status='APPROVED'; await session.commit()
        await GenericArtifactReviewService(session).approve(album.id)
        publication=await CreateTelegramDraft.execute_for_artifact(session,album,'private-test')
        async def get_bytes(self,uri,**kwargs):return b'png'
        monkeypatch.setattr(S3ArtifactStorage,'from_environment',lambda:S3ArtifactStorage(client=_FakeS3Client(),bucket='test'))
        monkeypatch.setattr(S3ArtifactStorage,'get_bytes',get_bytes)
        class Publisher:
            calls=0
            async def publish(self,**kwargs):
                self.calls+=1
                raise TimeoutError('Uncertain provider response')
        pub=Publisher()
        result=await ApproveAndPublish(pub).execute(session,publication.id)
        assert result.status.value=='PUBLISHING'
        with pytest.raises(ValueError,match='not a DRAFT'):
            await ApproveAndPublish(pub).execute(session,publication.id)
        assert pub.calls==1


@pytest.mark.asyncio
async def test_album_preview_is_immutable_and_checked():
    async with SessionFactory() as session:
        album, ids = await setup_album(session)
        meta = {**album.metadata, 'album_preview': []}
        with pytest.raises(ValueError, match='immutable'):
            await GenericArtifactReviewService(session).update(album.id, None, meta)
        with pytest.raises(ValueError, match='preview'):
            await resolve_album(session, meta)


@pytest.mark.asyncio
async def test_concurrent_album_creation_reuses_selection():
    import asyncio
    async with SessionFactory() as session:
        album, ids = await setup_album(session)
        # Remove the existing wrapper to exercise simultaneous first creates.
        row = await session.get(ArtifactModel, album.id)
        row.review_status = 'REJECTED'
        await session.commit()
    async def create():
        async with SessionFactory() as session:
            return (await create_album(session, artifact_ids=ids, title='Concurrent album')).id
    left, right = await asyncio.gather(create(), create())
    assert left == right
