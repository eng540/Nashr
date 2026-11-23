import io
import pytest
from PIL import Image
from sqlalchemy import select
from app.application.media_bank import IngestReadyMedia
from app.application.telegram_live_photos import create_live_photo,resolve_live_photo
from app.application.generic_artifact_review import GenericArtifactReviewService
from app.infrastructure.artifact_storage import S3ArtifactStorage
from app.infrastructure.database.models import ArtifactModel
from app.infrastructure.database.session import SessionFactory
from tests.integration.test_media_bank_ingest import _FakeS3Client
from tests.unit.test_telegram_live_photo import motion_fixture


@pytest.mark.asyncio
async def test_live_photo_pair_is_reviewed_deduplicated_and_snapshot_bound(tmp_path):
    async with SessionFactory() as session:
        class Client(_FakeS3Client):
            def get_object(self, **kwargs):
                response=super().get_object(**kwargs)
                raw=response['Body'].read()
                return {'Body':io.BytesIO(raw)}
        storage=S3ArtifactStorage(client=Client(),bucket='fixture')
        output=io.BytesIO();Image.new('RGB',(64,64),'blue').save(output,format='PNG')
        photo=await IngestReadyMedia(storage=storage).execute(session,filename='static.png',content_type='image/png',data=output.getvalue(),caption='Synthetic static photo')
        video=await IngestReadyMedia(storage=storage).execute(session,filename='motion.mp4',content_type='video/mp4',data=motion_fixture(tmp_path),caption='Synthetic motion')
        for child in (photo,video):await GenericArtifactReviewService(session).approve(child.id)
        params={'photo_id':str(photo.id),'video_id':str(video.id),'title':'Synthetic Live Photo','storage':storage}
        pair=await create_live_photo(session,**params)
        assert (await GenericArtifactReviewService(session).get(pair.id))['review_status']=='DRAFT'
        assert (await create_live_photo(session,**params)).id==pair.id
        with pytest.raises(ValueError):await create_live_photo(session,photo_id=str(video.id),video_id=str(photo.id),title='Wrong order',storage=storage)
        await GenericArtifactReviewService(session).approve(pair.id)
        children,_=await resolve_live_photo(session,pair.metadata)
        children[0].review_status='REJECTED';await session.commit()
        with pytest.raises(ValueError,match='approved'):await resolve_live_photo(session,pair.metadata)
