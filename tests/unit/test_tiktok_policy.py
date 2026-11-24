import pytest
from app.application.tiktok_policy import assess,requirements

def test_modes_never_mean_publishing_or_grants():
    data=requirements();assert len(data['modes'])==2 and not data['execution_enabled'] and not data['account_connected']
    assert {x['scope'] for x in data['modes']}=={'video.upload','video.publish'}
    assert len(data['sources'])==7

@pytest.mark.parametrize('mode',['INBOX_DRAFT','DIRECT_POST'])
def test_missing_acceptance_grant_and_transfer(mode):
    d=assess(mode=mode)
    assert 'APP_SCOPE_ACCEPTANCE_UNVERIFIED' in d['blockers']
    assert 'OWNER_SCOPE_GRANT_MISSING' in d['blockers']
    assert 'EXPLICIT_MEDIA_TRANSFER_CONSENT_MISSING' in d['blockers']
    assert d['transmission']=='PULL_FROM_URL' and not d['execution_enabled']

def test_audited_does_not_waive_internal_use_or_privacy():
    d=assess(mode='DIRECT_POST',app_audited=True)
    assert 'INTERNAL_UTILITY_EXCLUDED_BY_DIRECT_POST_GUIDELINES' in d['blockers']
    assert 'EXPLICIT_AVAILABLE_PRIVACY_SELECTION_REQUIRED' in d['blockers']

@pytest.mark.parametrize('selected,private',[('PUBLIC_TO_EVERYONE',True),('SELF_ONLY',False),('SELF_ONLY',None)])
def test_unaudited_needs_both_private_creator_and_self_only(selected,private):
    d=assess(mode='DIRECT_POST',selected_privacy=selected,creator_private=private,privacy_options=[selected])
    assert 'UNAUDITED_REQUIRES_PRIVATE_CREATOR_AND_SELF_ONLY' in d['blockers']

def test_even_all_inputs_never_authorize_execution():
    d=assess(mode='DIRECT_POST',storage_origin='DEVICE',app_audited=True,app_scope_approved=True,owner_granted_scope=True,transfer_consented=True,selected_privacy='SELF_ONLY',privacy_options=['SELF_ONLY'],current_creator_checked=True,intended_audience='WIDE_AUDIENCE')
    assert d['blockers']==[] and d['status']=='POLICY_INPUTS_RECORDED_NOT_EXECUTABLE'
    assert d['transmission']=='FILE_UPLOAD' and not d['external_facts_verified'] and not d['upload_enabled']

@pytest.mark.parametrize('values',[{'mode':'AUTO'},{'mode':'INBOX_DRAFT','app_audited':'yes'},{'mode':'DIRECT_POST','creator_private':'true'},{'mode':'INBOX_DRAFT','storage_origin':'GUESS'}])
def test_rejects_ambiguous_inputs(values):
    with pytest.raises(ValueError):assess(**values)
