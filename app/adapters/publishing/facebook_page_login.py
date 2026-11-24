"""Read-only Pages discovery. No writes, refreshes, or publishing permission grant.

System user /me/accounts: Meta Business Management APIs, System Users/API Calls.
Actual token type, app, scopes, tasks and Page identity are always checked.
"""
from dataclasses import dataclass,field
from datetime import datetime,timezone
import re
import httpx
BASE='https://graph.facebook.com/v27.0/'
REQUIRED=frozenset({'pages_show_list','pages_read_engagement','pages_manage_posts'})
ID=re.compile(r'^[0-9]{1,100}$')
class FacebookLoginError(ValueError):pass
@dataclass(frozen=True)
class FacebookPageCandidate:
    page_id:str
    page_name:str
    tasks:tuple[str,...]
    scopes:tuple[str,...]
    token_type:str
    token:str=field(repr=False)
    expires_at:int|None=None
    source_token:str=field(default='',repr=False)
    def public(self):return dict(page_id=self.page_id,page_name=self.page_name,tasks=list(self.tasks),scopes=list(self.scopes),token_type=self.token_type,execution_authorized=False)
class FacebookPagesLogin:
    def __init__(self,*,client,app_id,app_secret,token_mode):
        if not isinstance(app_id,str) or not ID.fullmatch(app_id) or not isinstance(app_secret,str) or not app_secret or token_mode not in {'USER','SYSTEM_USER'}:raise FacebookLoginError('Explicit Pages app and token mode required')
        self.client=client;self.app_id=app_id;self.app_secret=app_secret;self.token_mode=token_mode
    async def read(self,path,*,token,params=None):
        try:
            r=await self.client.get(BASE+path,headers={'Authorization':'Bearer '+token},params=params or {},follow_redirects=False)
            d=r.json()
            if r.status_code!=200 or not isinstance(d,dict) or d.get('error'):raise ValueError()
            return d
        except (httpx.HTTPError,ValueError,TypeError):raise FacebookLoginError('FACEBOOK_PAGES_READ_FAILED') from None
    async def debug(self,token,expected_type):
        d=(await self.read('debug_token',token=self.app_id+'|'+self.app_secret,params={'input_token':token})).get('data')
        if not isinstance(d,dict) or d.get('is_valid') is not True or str(d.get('app_id',''))!=self.app_id or d.get('type')!=expected_type:raise FacebookLoginError('FACEBOOK_PAGES_TOKEN_MISMATCH')
        scopes=d.get('scopes')
        if not isinstance(scopes,list) or not all(isinstance(x,str) for x in scopes) or not REQUIRED.issubset(scopes):raise FacebookLoginError('FACEBOOK_PAGES_PERMISSION_REQUIRED')
        expiries=[]
        for k in ['expires_at','data_access_expires_at']:
            v=d.get(k)
            if v is not None and (type(v) is not int or v<0):raise FacebookLoginError('FACEBOOK_PAGES_INVALID_EXPIRY')
            if v:
                if v<=datetime.now(timezone.utc).timestamp():raise FacebookLoginError('FACEBOOK_PAGES_TOKEN_EXPIRED')
                expiries.append(v)
        return tuple(sorted(set(scopes))),min(expiries) if expiries else None
    async def discover(self,token):
        if not isinstance(token,str) or not token or len(token)>16000:raise FacebookLoginError('FACEBOOK_PAGES_TOKEN_REQUIRED')
        scopes,expiry=await self.debug(token,self.token_mode)
        if self.token_mode=='SYSTEM_USER':
            business=await self.read('me',token=token,params={'fields':'client_business_id'})
            if not isinstance(business.get('client_business_id'),str) or not ID.fullmatch(business['client_business_id']):raise FacebookLoginError('FACEBOOK_PAGES_BUSINESS_ID_REQUIRED')
        data=await self.read('me/accounts',token=token,params={'fields':'id,name,tasks,access_token','limit':100})
        pages=data.get('data');paging=data.get('paging',{})
        if not isinstance(pages,list) or len(pages)>100 or not isinstance(paging,dict) or paging.get('next'):raise FacebookLoginError('FACEBOOK_PAGES_INCOMPLETE')
        result=[];seen=set()
        for p in pages:
            if not isinstance(p,dict):raise FacebookLoginError('FACEBOOK_PAGES_INVALID_PAGE')
            tasks=p.get('tasks')
            if not isinstance(tasks,list) or not all(isinstance(x,str) for x in tasks):raise FacebookLoginError('FACEBOOK_PAGES_INVALID_TASKS')
            if 'CREATE_CONTENT' not in tasks:continue
            pid,name,pt=p.get('id'),p.get('name'),p.get('access_token')
            if not isinstance(pid,str) or not ID.fullmatch(pid) or pid in seen or not isinstance(name,str) or not name or len(name)>500 or not isinstance(pt,str) or not pt or len(pt)>16000:raise FacebookLoginError('FACEBOOK_PAGES_INVALID_CANDIDATE')
            seen.add(pid);result.append(FacebookPageCandidate(pid,name,tuple(sorted(set(tasks))),scopes,'PAGE',pt,expiry,token))
        if not result:raise FacebookLoginError('FACEBOOK_PAGES_NO_ELIGIBLE_PAGE')
        return result
    async def verify_selected(self,candidate):
        if not candidate.source_token:raise FacebookLoginError('FACEBOOK_PAGES_SOURCE_RECHECK_REQUIRED')
        current=await self.discover(candidate.source_token)
        matching=[x for x in current if x.page_id==candidate.page_id]
        if len(matching)!=1:raise FacebookLoginError('FACEBOOK_PAGES_TASK_OR_ASSET_CHANGED')
        scopes,expiry=await self.debug(candidate.token,'PAGE')
        page=await self.read('me',token=candidate.token,params={'fields':'id,name'})
        if page.get('id')!=candidate.page_id or not isinstance(page.get('name'),str) or not page['name'] or page['name']!=candidate.page_name:raise FacebookLoginError('FACEBOOK_PAGES_IDENTITY_CHANGED')
        deadlines=[x for x in [candidate.expires_at,expiry,matching[0].expires_at] if x]
        return {**matching[0].public(),'expires_at':min(deadlines) if deadlines else None,'permission_verified_at_last_check':True,'execution_authorized':False}
