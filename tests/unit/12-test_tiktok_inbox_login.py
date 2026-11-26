import pytest
from app.adapters.publishing.tiktok_inbox_login import token_payload,TikTokLoginError
from app.adapters.publishing.tiktok_login import token_payload as basic
VALID=dict(access_token='access',refresh_token='refresh',open_id='id',expires_in=7200,refresh_expires_in=86400,scope='user.info.basic,video.upload',token_type='Bearer')
def test_exact_draft_scopes_never_direct_publish_or_basic_only():
    assert token_payload(VALID)['scope']==VALID['scope']
    with pytest.raises(ValueError):basic(VALID)
    for scope in ['user.info.basic','video.upload','user.info.basic,video.upload,video.publish','user.info.basic,video.publish','',None]:
        with pytest.raises(TikTokLoginError):token_payload({**VALID,'scope':scope})
@pytest.mark.parametrize('key,value',[('expires_in',True),('refresh_expires_in',0),('token_type','bearer'),('open_id',''),('access_token',''),('error','denied')])
def test_invalid_token_fails_closed(key,value):
    with pytest.raises(TikTokLoginError):token_payload({**VALID,key:value})
