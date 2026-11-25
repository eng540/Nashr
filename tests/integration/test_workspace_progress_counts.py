from uuid import uuid4
import httpx
import pytest
from app.main import app
from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.models import SourceModel,KnowledgeUnitModel,ArtifactModel,PostModel,PlatformCopyModel

@pytest.mark.asyncio
async def test_progress_counts_keep_original_copy_and_post_separate():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        before=(await client.get('/api/workspace/progress')).json()
        source,unit=uuid4(),uuid4()
        async with SessionFactory() as session:
            session.add(SourceModel(id=source,filename='progress.pdf',mime_type='application/pdf',storage_path='./test/progress.pdf',size_bytes=10,status='STORED'))
            session.add(KnowledgeUnitModel(id=unit,source_id=source,position=1,title='عنوان مادة محفوظة',content='نص'))
            await session.flush()
            original=ArtifactModel(source_knowledge_unit_id=unit,kind='TEXT',status='AVAILABLE',review_status='DRAFT',content='أصل',artifact_metadata={})
            session.add(original);await session.flush()
            session.add(PlatformCopyModel(artifact_id=original.id,platform='telegram',fields={'title':'','description':'أصل','tags':[],'alt_text':''},source_fingerprint='test',origin='UNCHANGED_ORIGINAL',version=1))
            session.add_all([ArtifactModel(source_knowledge_unit_id=unit,kind='TEXT',status='AVAILABLE',review_status='DRAFT',content='نسخة',artifact_metadata={'source_type':'PLATFORM_VARIANT'}),PostModel(knowledge_unit_id=unit,content='منشور',status='DRAFT')]);await session.commit()
        after=(await client.get('/api/workspace/progress')).json()
        assert after['materials'].get('DRAFT',0)==before['materials'].get('DRAFT',0)+1
        assert after['editorial_posts'].get('DRAFT',0)==before['editorial_posts'].get('DRAFT',0)+1
        assert after['platform_copies']==before['platform_copies']+1
        assert after['legacy_platform_variants']==before['legacy_platform_variants']+1
        assert after['pdf_sources']==before['pdf_sources']+1
