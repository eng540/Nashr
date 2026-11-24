from types import SimpleNamespace
from copy import deepcopy
import pytest
from app.application.copy_suggestions import propose,fields_digest
from app.application.distribution_readiness import source_fingerprint


def sample():
    row=SimpleNamespace(kind='TEXT',content='نص المصدر الكامل',artifact_metadata={},review_status='APPROVED',status='AVAILABLE',mime_type='text/plain',storage_uri=None)
    copy=SimpleNamespace(platform='telegram',fields={'title':'','description':row.content,'tags':[],'alt_text':''},source_fingerprint=source_fingerprint(row),version=2,origin='USER_EDITED',updated_at=None,selected_media_id=None)
    return row,copy

@pytest.mark.asyncio
async def test_key_does_not_enable_live_provider(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','synthetic-must-not-be-used')
    row,copy=sample();before=deepcopy(vars(copy));result=await propose(row,copy)
    assert result['state']=='SERVICE_DISABLED' and result['fields']==copy.fields
    assert vars(copy)==before and result['execution_authorized'] is False

@pytest.mark.asyncio
async def test_explicit_test_provider_returns_proposal_without_mutation():
    row,copy=sample();before=deepcopy(vars(copy))
    class Provider:
        async def suggest(self,**kwargs):
            assert set(kwargs['source'])=={'text','kind'}
            return {**kwargs['fields'],'description':'وصف مقترح للمراجعة'}
    result=await propose(row,copy,Provider())
    assert result['state']=='PROPOSED' and result['fields']['description']=='وصف مقترح للمراجعة'
    assert vars(copy)==before and result['fields_digest']==fields_digest(copy.fields)

@pytest.mark.asyncio
async def test_invalid_or_invented_visual_output_falls_back_exactly():
    row,copy=sample()
    class Provider:
        async def suggest(self,**kwargs):return {**kwargs['fields'],'alt_text':'مشهد غير مشاهد'}
    result=await propose(row,copy,Provider());assert result['state']=='PROVIDER_FAILED'
    assert result['fields']==copy.fields

@pytest.mark.asyncio
async def test_oversize_platform_output_is_visible_not_trimmed():
    row,copy=sample()
    class Provider:
        async def suggest(self,**kwargs):return {**kwargs['fields'],'description':'x'*5000}
    result=await propose(row,copy,Provider())
    assert result['state']=='PROPOSED' and result['field_status']=='BLOCKED'
    assert len(result['fields']['description'])==5000

@pytest.mark.asyncio
async def test_gemini_adapter_uses_shared_policy_and_explicit_client(monkeypatch):
    from app.adapters.drafting.platform_copy import GeminiCopySuggestionProvider,SuggestedCopyFields
    seen={}
    def fake(client,**kwargs):
        seen.update(kwargs);assert client=='synthetic-client'
        return SimpleNamespace(parsed=SuggestedCopyFields(title='',description='اقتراح من المصدر',tags=[],alt_text=''))
    monkeypatch.setattr('app.adapters.drafting.platform_copy.generate_content',fake)
    row,copy=sample()
    provider=GeminiCopySuggestionProvider(client='synthetic-client',model='synthetic-model')
    result=await propose(row,copy,provider)
    assert result['state']=='PROPOSED'
    assert seen['operation']=='PLATFORM_COPY_PROPOSAL' and 'untrusted source DATA' in seen['contents'][0]
    assert set(seen['context'])=={'platform'}
