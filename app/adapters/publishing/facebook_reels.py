"""Dormant Reel upload transport, synthetic tests only.

No routes, storage reads, OAuth, scheduler, retry or authority resolver. A future
orchestrator must durably pin the full owner-approved effect, exact inspected
bytes, Page token/task, lifecycle session and remote result before using this.
"""
from dataclasses import dataclass
import hashlib
from urllib.parse import urlsplit
import httpx
from app.adapters.publishing.facebook import FacebookPagePublisher,FacebookProviderError,ID

@dataclass(frozen=True)
class ReelSession:
    page_id:str
    video_id:str
    upload_url:str
    sha256:str
    size_bytes:int


def upload_url_valid(url,video_id,version):
    try:
        p=urlsplit(url) if isinstance(url,str) else None
        return bool(p and p.scheme=='https' and p.netloc=='rupload.facebook.com' and not p.query and not p.fragment and p.path in {'/video-upload/'+video_id,'/video-upload/'+version+'/'+video_id})
    except ValueError:return False


def decode_status(body,*,size_bytes):
    """Never infer public publication from byte completion or generic success."""
    if type(size_bytes) is not int or size_bytes<1:raise ValueError('Known total required')
    s=body.get('status') if isinstance(body,dict) else None
    if not isinstance(s,dict):raise FacebookProviderError('FACEBOOK_REEL_STATUS_UNVERIFIED')
    phases={}
    for key in ['uploading_phase','processing_phase','publishing_phase']:
        value=s.get(key)
        if not isinstance(value,dict) or value.get('status') not in {'not_started','in_progress','complete','error'}:
            raise FacebookProviderError('FACEBOOK_REEL_STATUS_UNVERIFIED')
        phases[key]=value
    offset=phases['uploading_phase'].get('bytes_transfered')
    if offset is not None and (type(offset) is not int or not 0<=offset<=size_bytes):raise FacebookProviderError('FACEBOOK_REEL_OFFSET_UNVERIFIED')
    failed=any(p.get('error') or p['status']=='error' for p in phases.values()) or s.get('video_status')=='error'
    complete=all(p['status']=='complete' for p in phases.values())
    return dict(state='REMOTE_ERROR' if failed else 'REMOTE_PHASES_COMPLETE_NOT_PUBLICATION_VERIFIED' if complete else 'REMOTE_PROCESSING',
        received_bytes=offset,upload_complete=not failed and phases['uploading_phase']['status']=='complete',
        processing_complete=not failed and phases['processing_phase']['status']=='complete',
        publishing_complete=not failed and phases['publishing_phase']['status']=='complete',
        publishing_not_started=not failed and phases['publishing_phase']['status']=='not_started',
        public_post_verified=False,automatic_retry_allowed=False)


class FacebookReelsEdge(FacebookPagePublisher):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.version=kwargs['version']

    @staticmethod
    def _consent(authorized,public_page_acknowledged,media_transfer_authorized):
        if any(v is not True for v in [authorized,public_page_acknowledged,media_transfer_authorized]):
            raise ValueError('Explicit public Page and exact media disclosure approval required')

    @staticmethod
    def _bytes(content,sha256):
        if not isinstance(content,bytes) or not content or len(content)>50_000_000 or hashlib.sha256(content).hexdigest()!=sha256:
            raise ValueError('Pinned inspected MP4 bytes within conservative local50MB cap required')

    def _session(self,session):
        if not isinstance(session,ReelSession) or session.page_id!=self.page_id or not isinstance(session.video_id,str) or not ID.fullmatch(session.video_id) or not upload_url_valid(session.upload_url,session.video_id,self.version) or type(session.size_bytes) is not int or not 0<session.size_bytes<=50_000_000 or not isinstance(session.sha256,str) or len(session.sha256)!=64:
            raise ValueError('Pinned session and selected Page required')

    async def initialize(self,*,content,sha256,mime_type,inspection_confirmed=False,authorized=False,public_page_acknowledged=False,media_transfer_authorized=False):
        self._consent(authorized,public_page_acknowledged,media_transfer_authorized)
        self._bytes(content,sha256)
        if inspection_confirmed is not True or mime_type!='video/mp4':raise ValueError('Explicit inspected MP4 only')
        await self.verify_page()
        body=await self._request('POST',self.page_id+'/video_reels',json={'upload_phase':'start'})
        video=body.get('video_id');url=body.get('upload_url')
        if not isinstance(video,str) or not ID.fullmatch(video) or not upload_url_valid(url,video,self.version):
            raise FacebookProviderError('FACEBOOK_REEL_SESSION_UNVERIFIED',outcome_unknown=True)
        return ReelSession(self.page_id,video,url,sha256,len(content))

    async def status(self,session):
        self._session(session)
        body=await self._request('GET',session.video_id,params={'fields':'status'})
        return decode_status(body,size_bytes=session.size_bytes)

    async def upload(self,session,*,content,offset=0,authorized=False,public_page_acknowledged=False,media_transfer_authorized=False):
        self._consent(authorized,public_page_acknowledged,media_transfer_authorized)
        self._session(session);self._bytes(content,session.sha256)
        if len(content)!=session.size_bytes or type(offset) is not int or not 0<=offset<session.size_bytes:raise ValueError('Pinned complete bytes and explicit offset required')
        # Always read current offset before sending. Never retry an ambiguous POST
        # from zero, and never accept an offset merely supplied by a caller.
        current=await self.status(session)
        remote=current['received_bytes']
        if current['state']=='REMOTE_ERROR' or current['upload_complete'] or remote is None or (remote is not None and remote!=offset):raise FacebookProviderError('FACEBOOK_REEL_OFFSET_RECONCILIATION_REQUIRED')
        await self.verify_page()
        try:
            r=await self.client.post(session.upload_url,headers={'Authorization':'OAuth '+self.token,'Content-Type':'application/octet-stream','offset':str(offset),'file_size':str(session.size_bytes)},content=content[offset:],follow_redirects=False)
        except httpx.HTTPError:raise FacebookProviderError('FACEBOOK_REEL_TRANSFER_OUTCOME_UNKNOWN',outcome_unknown=True) from None
        try:body=r.json()
        except (ValueError,TypeError):raise FacebookProviderError('FACEBOOK_REEL_TRANSFER_OUTCOME_UNKNOWN',outcome_unknown=True) from None
        if r.status_code not in {200,201} or not isinstance(body,dict) or body.get('success') is not True or body.get('error'):
            raise FacebookProviderError('FACEBOOK_REEL_TRANSFER_OUTCOME_UNKNOWN',outcome_unknown=True)
        return dict(state='TRANSFER_ACCEPTED_NOT_PUBLISHED',video_id=session.video_id,public_post_verified=False,automatic_retry_allowed=False)

    async def finish(self,session,*,description,title='',authorized=False,public_page_acknowledged=False,media_transfer_authorized=False):
        self._consent(authorized,public_page_acknowledged,media_transfer_authorized);self._session(session)
        self.validate_message(description,allow_empty=True)
        if not isinstance(title,str) or len(title)>200:raise ValueError('Exact title within conservative local limit required')
        current=await self.status(session)
        if current['state']=='REMOTE_ERROR' or not current['upload_complete'] or not current['processing_complete'] or not current['publishing_not_started']:
            raise FacebookProviderError('FACEBOOK_REEL_NOT_READY_OR_FINISH_ALREADY_OBSERVED')
        await self.verify_page()
        body=await self._request('POST',self.page_id+'/video_reels',json={'upload_phase':'finish','video_id':session.video_id,'video_state':'PUBLISHED','description':description,'title':title})
        if body.get('success') is not True:raise FacebookProviderError('FACEBOOK_REEL_FINISH_OUTCOME_UNKNOWN',outcome_unknown=True)
        return dict(state='FINISH_ACCEPTED_NOT_PUBLICATION_VERIFIED',video_id=session.video_id,public_post_verified=False,automatic_retry_allowed=False)
