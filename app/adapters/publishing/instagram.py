"""Single JPEG/Reel provider edge. Not connected to production execution routes.

A caller must already hold explicit publish authority and a pinned, intentionally
provider-readable media grant. This module never creates URLs or reads storage.
No automatic retry of mutations: a lost response is an unknown outcome.
"""
from dataclasses import dataclass
import re
from urllib.parse import urlsplit
import httpx

BASE='https://graph.facebook.com/v27.0'
ID=re.compile(r'^[0-9]{1,100}$')
STATES={'IN_PROGRESS','FINISHED','ERROR','EXPIRED','PUBLISHED'}

class InstagramProviderError(RuntimeError):
    def __init__(self,code,*,outcome_unknown=False):
        self.code=code;self.outcome_unknown=outcome_unknown
        super().__init__(code)

@dataclass(frozen=True)
class ContainerState:
    container_id:str
    status:str

class InstagramPublisher:
    graph_base=BASE
    def __init__(self,*,client:httpx.AsyncClient,token:str,account_id:str):
        if not token or len(token)>16000 or not ID.fullmatch(account_id):raise ValueError('Invalid Instagram credentials')
        self.client=client;self.token=token;self.account_id=account_id

    async def _request(self,method,path,*,params=None,data=None):
        mutation=method=='POST'
        try:
            response=await self.client.request(method,self.graph_base+path,headers={'Authorization':'Bearer '+self.token},params=params,data=data,follow_redirects=False)
        except httpx.HTTPError:
            raise InstagramProviderError('INSTAGRAM_OUTCOME_UNKNOWN' if mutation else 'INSTAGRAM_READ_FAILED',outcome_unknown=mutation) from None
        try:body=response.json()
        except (ValueError,TypeError):
            raise InstagramProviderError('INSTAGRAM_OUTCOME_UNKNOWN' if mutation else 'INSTAGRAM_INVALID_RESPONSE',outcome_unknown=mutation) from None
        if not isinstance(body,dict):raise InstagramProviderError('INSTAGRAM_INVALID_RESPONSE',outcome_unknown=mutation)
        if response.is_error or body.get('error'):
            error=body.get('error') if isinstance(body.get('error'),dict) else {}
            code=error.get('code')
            if code==190:raise InstagramProviderError('INSTAGRAM_RECONNECT_REQUIRED')
            if code in {10,200}:raise InstagramProviderError('INSTAGRAM_PERMISSION_REQUIRED')
            # Server/proxy failures may follow an accepted mutation. Never retry
            # even if an upstream is_transient field recommends doing so.
            unknown=mutation and (response.status_code>=500 or not error)
            raise InstagramProviderError('INSTAGRAM_OUTCOME_UNKNOWN' if unknown else 'INSTAGRAM_REQUEST_REJECTED',outcome_unknown=unknown)
        if response.status_code<200 or response.status_code>=300:
            raise InstagramProviderError('INSTAGRAM_OUTCOME_UNKNOWN' if mutation else 'INSTAGRAM_READ_FAILED',outcome_unknown=mutation)
        return body

    @staticmethod
    def _media_url(value):
        u=urlsplit(value)
        # This is a grant supplied by the application, not an arbitrary-source
        # fetch. Reject insecure, credential-bearing and obvious private URLs.
        host=(u.hostname or '').lower()
        import ipaddress
        try:address=ipaddress.ip_address(host)
        except ValueError:
            address=None
            if host.replace('.','').isdigit() or ':' in host:raise ValueError('Invalid provider media host') from None
        if address is not None and not address.is_global:raise ValueError('Provider media grant is not externally reachable')
        if u.scheme!='https' or not host or u.username or u.password or u.fragment or host=='localhost' or host.endswith(('.local','.internal','.localhost')):
            raise ValueError('Invalid provider media grant')
        return value

    async def create_container(self,*,kind,media_url,caption,alt_text='',share_to_feed=None):
        if kind not in {'IMAGE','VIDEO'}:raise ValueError('Only single JPEG or Reel supported')
        if not isinstance(caption,str) or len(caption)>2200:raise ValueError('Caption limit exceeded; text was not shortened')
        if len(re.findall(r'(?<!\w)#\w+',caption))>30 or len(re.findall(r'(?<!\w)@\w+',caption))>20:raise ValueError('Caption tag limit exceeded')
        if not isinstance(alt_text,str) or len(alt_text)>1000 or (kind=='VIDEO' and alt_text):raise ValueError('Invalid image alternative text')
        data={'caption':caption,'image_url' if kind=='IMAGE' else 'video_url':self._media_url(media_url)}
        if kind=='VIDEO':
            if not isinstance(share_to_feed,bool):raise ValueError('Choose Reel feed visibility explicitly')
            data.update(media_type='REELS',share_to_feed='true' if share_to_feed else 'false')
        elif alt_text:data['alt_text']=alt_text
        body=await self._request('POST','/'+self.account_id+'/media',data=data)
        container=str(body.get('id',''))
        if not ID.fullmatch(container):raise InstagramProviderError('INSTAGRAM_OUTCOME_UNKNOWN',outcome_unknown=True)
        return container

    async def container_status(self,container_id):
        if not ID.fullmatch(container_id):raise ValueError('Invalid container identity')
        body=await self._request('GET','/'+container_id,params={'fields':'id,status_code'})
        if str(body.get('id',container_id))!=container_id or body.get('status_code') not in STATES:raise InstagramProviderError('INSTAGRAM_INVALID_RESPONSE')
        return ContainerState(container_id,body['status_code'])

    async def publish_container(self,container_id):
        # One read, no hidden poll loop. Caller persists status and arranges any
        # provider-rate-respecting continuation outside this low-level adapter.
        status=await self.container_status(container_id)
        if status.status=='PUBLISHED':raise InstagramProviderError('INSTAGRAM_ALREADY_PUBLISHED_RECONCILE')
        if status.status!='FINISHED':raise InstagramProviderError('INSTAGRAM_CONTAINER_'+status.status)
        body=await self._request('POST','/'+self.account_id+'/media_publish',data={'creation_id':container_id})
        media_id=str(body.get('id',''))
        if not ID.fullmatch(media_id):raise InstagramProviderError('INSTAGRAM_OUTCOME_UNKNOWN',outcome_unknown=True)
        return media_id

    async def published_media(self,media_id):
        if not ID.fullmatch(media_id):raise ValueError('Invalid media identity')
        body=await self._request('GET','/'+media_id,params={'fields':'id,permalink,owner'})
        owner=body.get('owner')
        if str(body.get('id',''))!=media_id or not isinstance(owner,dict) or str(owner.get('id',''))!=self.account_id:raise InstagramProviderError('INSTAGRAM_ACCOUNT_MISMATCH')
        permalink=body.get('permalink');u=urlsplit(permalink if isinstance(permalink,str) else '')
        if u.scheme!='https' or u.hostname not in {'instagram.com','www.instagram.com'} or u.username or u.password:raise InstagramProviderError('INSTAGRAM_INVALID_PERMALINK')
        return {'media_id':media_id,'permalink':permalink,'account_id':self.account_id}

    async def verify_account(self,*,app_access_token,expected_app_id):
        """Read-only capability check for a future owner-authorized execution.

        Returns selected identity and token facts, not a publishing grant. No
        permission request, account conversion, token refresh or media request.
        """
        from datetime import datetime,timezone
        if not isinstance(app_access_token,str) or not app_access_token or len(app_access_token)>16000 or not ID.fullmatch(expected_app_id):raise ValueError('Valid app verification credentials required')
        # debug_token needs the app token, not the selected account token. Keep
        # it in the bearer header; upstream diagnostics must never escape.
        try:
            response=await self.client.get(BASE+'/debug_token',headers={'Authorization':'Bearer '+app_access_token},params={'input_token':self.token},follow_redirects=False)
            body=response.json()
        except (httpx.HTTPError,ValueError,TypeError):raise InstagramProviderError('INSTAGRAM_READ_FAILED') from None
        if response.status_code!=200 or not isinstance(body,dict) or not isinstance(body.get('data'),dict):raise InstagramProviderError('INSTAGRAM_INVALID_RESPONSE')
        facts=body['data'];scopes=facts.get('scopes')
        if facts.get('is_valid') is not True or str(facts.get('app_id',''))!=expected_app_id:raise InstagramProviderError('INSTAGRAM_RECONNECT_REQUIRED')
        if not isinstance(scopes,list) or not all(isinstance(v,str) for v in scopes) or not {'instagram_basic','instagram_content_publish'}.issubset(scopes):raise InstagramProviderError('INSTAGRAM_PERMISSION_REQUIRED')
        expiries=[]
        for key in ('expires_at','data_access_expires_at'):
            value=facts.get(key)
            if value is not None and (isinstance(value,bool) or not isinstance(value,int) or value<0):raise InstagramProviderError('INSTAGRAM_INVALID_RESPONSE')
            if value:
                if value<=datetime.now(timezone.utc).timestamp():raise InstagramProviderError('INSTAGRAM_RECONNECT_REQUIRED')
                expiries.append(value)
        business=await self._request('GET','/me',params={'fields':'client_business_id'})
        business_id=str(business.get('client_business_id',''))
        if not ID.fullmatch(business_id):raise InstagramProviderError('INSTAGRAM_BUSINESS_ID_REQUIRED')
        assigned=await self._request('GET','/me/assigned_instagram_accounts',params={'fields':'id,username','limit':100})
        accounts=assigned.get('data')
        paging=assigned.get('paging',{})
        if not isinstance(accounts,list) or len(accounts)>100 or not isinstance(paging,dict) or paging.get('next'):raise InstagramProviderError('INSTAGRAM_ACCOUNT_CHECK_INCOMPLETE')
        selected=[a for a in accounts if isinstance(a,dict) and str(a.get('id',''))==self.account_id]
        if len(selected)!=1:raise InstagramProviderError('INSTAGRAM_ACCOUNT_MISMATCH')
        username=selected[0].get('username')
        if not isinstance(username,str) or not re.fullmatch(r'[A-Za-z0-9_.]{1,100}',username):raise InstagramProviderError('INSTAGRAM_INVALID_RESPONSE')
        return {'account_id':self.account_id,'username':username,'client_business_id':business_id,'scopes':sorted(set(scopes)),'expires_at':min(expiries) if expiries else None,'checked_at':datetime.now(timezone.utc).isoformat(),'execution_authorized':False}
