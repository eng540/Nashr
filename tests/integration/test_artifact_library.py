from uuid import UUID, uuid4
from datetime import datetime, timezone, timedelta
import pytest
from app.infrastructure.database.models import ArtifactModel, ArtifactOrganizationModel
from app.infrastructure.database.session import SessionFactory
from tests.integration.test_managed_connections import config, browser
from tests.integration.test_platform_variants import _seed_text_artifact


@pytest.mark.asyncio
async def test_library_pages_global_filters_index_and_exact_items(config):
    marker='library-'+str(uuid4())
    ids=[await _seed_text_artifact(marker+' original '+str(i)+' '+'full-content-'*150) for i in range(15)]
    async with SessionFactory() as session:
        for i,uid in enumerate(ids):
            row=await session.get(ArtifactModel,UUID(uid));row.created_at=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(minutes=i)
            row.artifact_metadata={**row.artifact_metadata,'original_filename':f'{i}-b2v{i}.mp4','title':f'{marker} {i:02}','source_type':'READY_MEDIA' if i==0 else 'GENERATED',**({'telegram_album':{'huge_private_payload':'album-payload-'*1000}} if i==1 else {})}
            if i==0:session.add(ArtifactOrganizationModel(artifact_id=row.id,title='organized',series='custom-'+marker,category='category-'+marker,version=1,updated_at=datetime.now(timezone.utc)))
        await session.commit()
    async with browser() as client:
        r=await client.get('/api/artifacts/library',params={'q':marker,'sort':'oldest'})
        assert r.status_code==200,r.text
        data=r.json();assert data['total']==15 and len(data['items'])==12
        assert [i['id'] for i in data['items']]==ids[:12]
        assert [i['id'] for i in data['index']]==ids
        assert data['index'][1]['metadata']['telegram_album'] is True
        assert 'album-payload-' not in str(data['index'])
        index_only=(await client.get('/api/artifacts/library',params={'q':marker,'include_items':'false'})).json()
        assert not index_only['items'] and len(index_only['index'])==15
        assert all('content' not in i and 'storage_uri' not in i and 'full-content-' not in str(i) for i in data['index'])
        assert 'custom-'+marker in data['filter_options']['series'] and 'وش معنى' in data['filter_options']['series']
        assert 'category-'+marker in data['filter_options']['categories']
        second=(await client.get('/api/artifacts/library',params={'q':marker,'sort':'oldest','offset':12})).json()
        assert [i['id'] for i in second['items']]==ids[12:] and second['total']==15
        filtered=(await client.get('/api/artifacts/library',params={'q':marker,'series':'custom-'+marker})).json()
        assert filtered['total']==1 and filtered['items'][0]['id']==ids[0]
        assert 'وش معنى' in filtered['filter_options']['series']
        assert (await client.get('/api/artifacts/library',params={'q':marker,'source':'READY_MEDIA'})).json()['total']==1
        assert (await client.get('/api/artifacts/library',params={'q':marker,'category':'category-'+marker})).json()['total']==1
        exact=await client.get('/api/artifacts/library-items',params=[('ids',ids[14]),('ids',ids[0])])
        assert exact.status_code==200,exact.text
        assert [i['id'] for i in exact.json()['items']]==[ids[14],ids[0]]
        assert exact.json()['items'][1]['organization']['title']=='organized'
        assert (await client.get('/api/artifacts/library-items',params=[('ids',ids[0]),('ids',str(uuid4()))])).status_code==404
        assert (await client.get('/api/artifacts/library-items',params=[('ids',ids[0]),('ids',ids[0])])).status_code==422
        assert (await client.get('/api/artifacts/library',params={'sort':'unsafe'})).status_code==422
        assert (await client.get('/api/artifacts/library',params={'q':'%'+marker})).json()['total']==0

@pytest.mark.asyncio
async def test_library_metadata_string_fallbacks_and_ascii_kind_order(config):
    marker='parity-'+str(uuid4())
    metadata=[
        {'title':42,'series':42,'original_filename':'   ','caption':{'not':'a string'}},
        {'title':{'nested':'x'},'series':{'nested':'x'},'caption':' \n  Caption fallback  \n second'},
        {'title':' \t Kept title \n','series':'','source_type':42},
        {'title':False,'original_filename':'  filename.mp4  ','description':42},
    ]
    ids=[await _seed_text_artifact(marker) for _ in metadata]
    async with SessionFactory() as session:
        for uid,value in zip(ids,metadata):
            row=await session.get(ArtifactModel,UUID(uid));row.artifact_metadata=value
        await session.commit()
    async with browser() as client:
        data=(await client.get('/api/artifacts/library',params={'q':marker})).json()
        by_id={i['id']:i for i in data['index']}
        assert by_id[ids[0]]['metadata']['title']=='مخرج TEXT'
        assert by_id[ids[1]]['metadata']['title']=='Caption fallback'
        assert by_id[ids[2]]['metadata']['title']=='Kept title'
        assert by_id[ids[3]]['metadata']['title']=='  filename.mp4  '
        assert (await client.get('/api/artifacts/library',params={'q':marker,'series':'غير مصنف'})).json()['total']==3
        assert (await client.get('/api/artifacts/library',params={'q':marker,'series':''})).json()['total']==1
        assert (await client.get('/api/artifacts/library',params={'q':marker,'source':'GENERATED'})).json()['total']==4
        assert (await client.get('/api/artifacts/library',params={'q':'nested'})).json()['total']==0
        ordered=(await client.get('/api/artifacts/library',params={'q':marker,'sort':'kind'})).json()['index']
        assert [i['kind'] for i in ordered]==sorted(i['kind'] for i in ordered)
