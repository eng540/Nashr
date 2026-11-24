"""Dormant Page-linked discovery for a User-token Login configuration.

Not a permission grant, publishing route, or fallback from Unified login.
Candidate tokens are server-only and must be encrypted before persistence.
"""
from dataclasses import dataclass,field
from datetime import datetime,timezone
import re
import httpx

BASE='https://graph.facebook.com/v27.0/'
REQUIRED=frozenset({'instagram_basic','instagram_content_publish','pages_show_list','pages_read_engagement'})
ID=re.compile(r'^[0-9]{1,100}$')

class PageLoginError(ValueError):
    pass

@dataclass(frozen=True)
class PageCandidate:
    account_id:str
    username:str
    page_id:str
    page_name:str
    tasks:tuple[str,...]
    token:str=field(repr=False)
    expires_at:int|None=None
    user_token:str=field(default='',repr=False)

    def public(self):
        return dict(account_id=self.account_id,username=self.username,page_id=self.page_id,page_name=self.page_name,token_type='PAGE',execution_authorized=False)

class PageLinkedLogin:
    def __init__(self,*,client,app_id,app_secret):
        if not isinstance(app_id,str) or not ID.fullmatch(app_id) or not isinstance(app_secret,str) or not app_secret:
            raise PageLoginError('Explicit app verification credentials required')
        self.client=client;self.app_id=app_id;self.app_secret=app_secret

    async def read(self,path,*,token,params=None):
        try:
            r=await self.client.get(BASE+path,headers={'Authorization':'Bearer '+token},params=params or {},follow_redirects=False)
            data=r.json()
            if r.status_code!=200 or not isinstance(data,dict) or data.get('error'):raise ValueError()
            return data
        except (httpx.HTTPError,ValueError,TypeError):
            raise PageLoginError('META_PAGE_LOGIN_READ_FAILED') from None

    async def debug(self,token,*,expected_type):
        data=await self.read('debug_token',token=self.app_id+'|'+self.app_secret,params={'input_token':token})
        d=data.get('data')
        if not isinstance(d,dict) or d.get('is_valid') is not True or str(d.get('app_id',''))!=self.app_id or d.get('type')!=expected_type:
            raise PageLoginError('META_PAGE_LOGIN_TOKEN_MISMATCH')
        scopes=d.get('scopes')
        if not isinstance(scopes,list) or not all(isinstance(x,str) for x in scopes) or not REQUIRED.issubset(scopes):
            raise PageLoginError('META_PAGE_LOGIN_PERMISSION_REQUIRED')
        expiries=[]
        for key in ['expires_at','data_access_expires_at']:
            value=d.get(key)
            if value is not None and (type(value) is not int or value<0):raise PageLoginError('META_PAGE_LOGIN_INVALID_EXPIRY')
            if value:
                if value<=datetime.now(timezone.utc).timestamp():raise PageLoginError('META_PAGE_LOGIN_TOKEN_EXPIRED')
                expiries.append(value)
        return min(expiries) if expiries else None

    async def discover(self,user_token):
        if not isinstance(user_token,str) or not user_token or len(user_token)>16000:raise PageLoginError('META_PAGE_LOGIN_TOKEN_REQUIRED')
        expiry=await self.debug(user_token,expected_type='USER')
        data=await self.read('me/accounts',token=user_token,params={'fields':'id,name,tasks,access_token,instagram_business_account{id,username}','limit':100})
        pages=data.get('data');paging=data.get('paging',{})
        if not isinstance(pages,list) or len(pages)>100 or not isinstance(paging,dict) or paging.get('next'):
            raise PageLoginError('META_PAGE_LOGIN_INCOMPLETE_PAGES')
        result=[];seen=set()
        for p in pages:
            if not isinstance(p,dict):raise PageLoginError('META_PAGE_LOGIN_INVALID_PAGE')
            tasks=p.get('tasks',[])
            if not isinstance(tasks,list) or not all(isinstance(x,str) for x in tasks):raise PageLoginError('META_PAGE_LOGIN_INVALID_TASKS')
            # Viewing or advertising alone is not content creation capability.
            if not {'CREATE_CONTENT','MANAGE'}.intersection(tasks):continue
            ig=p.get('instagram_business_account')
            if ig is None:continue
            if not isinstance(ig,dict):raise PageLoginError('META_PAGE_LOGIN_INVALID_ACCOUNT')
            pid=p.get('id');iid=ig.get('id');name=p.get('name');username=ig.get('username');token=p.get('access_token')
            if not isinstance(pid,str) or not ID.fullmatch(pid) or not isinstance(iid,str) or not ID.fullmatch(iid) or not isinstance(name,str) or not name or len(name)>500 or not isinstance(username,str) or not re.fullmatch('[A-Za-z0-9_.]{1,100}',username) or not isinstance(token,str) or not token or len(token)>16000 or iid in seen:
                raise PageLoginError('META_PAGE_LOGIN_INVALID_CANDIDATE')
            seen.add(iid)
            result.append(PageCandidate(iid,username,pid,name,tuple(sorted(set(tasks))),token,expiry,user_token))
        if not result:raise PageLoginError('META_PAGE_LOGIN_NO_ELIGIBLE_ACCOUNT')
        return result

    async def verify_selected(self,candidate):
        if not candidate.user_token:raise PageLoginError('META_PAGE_LOGIN_USER_RECHECK_REQUIRED')
        current=await self.discover(candidate.user_token)
        matching=[x for x in current if x.page_id==candidate.page_id and x.account_id==candidate.account_id and x.username==candidate.username]
        if len(matching)!=1:raise PageLoginError('META_PAGE_LOGIN_TASK_OR_LINK_CHANGED')
        # The selected Page token is rechecked separately, never swapped silently.
        page_expiry=await self.debug(candidate.token,expected_type='PAGE')
        page=await self.read('me',token=candidate.token,params={'fields':'id,name,instagram_business_account{id,username}'})
        ig=page.get('instagram_business_account')
        if page.get('id')!=candidate.page_id or not isinstance(ig,dict) or ig.get('id')!=candidate.account_id or ig.get('username')!=candidate.username:
            raise PageLoginError('META_PAGE_LOGIN_SELECTED_IDENTITY_CHANGED')
        deadlines=[x for x in [candidate.expires_at,page_expiry,matching[0].expires_at] if x]
        return {**candidate.public(),'expires_at':min(deadlines) if deadlines else None,'permission_verified_at_last_check':True,'execution_authorized':False}
