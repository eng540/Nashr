"""Official Login Kit identity only. No content or publishing scope."""
import httpx
class TikTokLoginError(ValueError):pass
SCOPES={'user.info.basic'}

def token_payload(d):
    if not isinstance(d,dict) or d.get('error') or d.get('token_type')!='Bearer':raise TikTokLoginError('TOKEN_RESPONSE')
    for k in ['access_token','refresh_token','open_id']:
        if not isinstance(d.get(k),str) or not 1<=len(d[k])<=16000:raise TikTokLoginError('TOKEN_RESPONSE')
    if len(d['open_id'])>100:raise TikTokLoginError('TOKEN_IDENTITY')
    for k in ['expires_in','refresh_expires_in']:
        if type(d.get(k)) is not int or not 0<d[k]<=366*86400:raise TikTokLoginError('TOKEN_EXPIRY')
    if not isinstance(d.get('scope'),str) or set(d['scope'].split(','))!=SCOPES:raise TikTokLoginError('SCOPE_MISMATCH')
    return {k:d[k] for k in ['access_token','refresh_token','open_id','expires_in','refresh_expires_in','scope','token_type']}

async def exchange(client,config,code):
    try:
        r=await client.post('https://open.tiktokapis.com/v2/oauth/token/',data={'client_key':config['client_key'],'client_secret':config['client_secret'],'code':code,'grant_type':'authorization_code','redirect_uri':config['redirect_uri']})
        if r.status_code!=200:raise TikTokLoginError('TOKEN_EXCHANGE')
        return token_payload(r.json())
    except (httpx.HTTPError,ValueError,TypeError):raise TikTokLoginError('TOKEN_EXCHANGE') from None

async def identity(client,token,open_id):
    try:
        r=await client.get('https://open.tiktokapis.com/v2/user/info/',params={'fields':'open_id,display_name,avatar_url'},headers={'Authorization':'Bearer '+token})
        d=r.json();u=d.get('data',{}).get('user',{})
        if r.status_code!=200 or d.get('error',{}).get('code')!='ok' or u.get('open_id')!=open_id or not isinstance(u.get('display_name'),str) or not 1<=len(u['display_name'])<=500:raise ValueError()
        return {'open_id':open_id,'display_name':u['display_name']}
    except (httpx.HTTPError,ValueError,TypeError,AttributeError):raise TikTokLoginError('IDENTITY_CHECK') from None
