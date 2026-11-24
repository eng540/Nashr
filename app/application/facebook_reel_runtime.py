"""Exact approved Page Reel. Write claims commit before every external mutation.

Unknown writes never replay. Status/permalink checks may continue independently
of expired approval. No personal Facebook login, public media URL or cross-post.
"""
import hashlib,json,re
from dataclasses import asdict
from datetime import datetime,timedelta,timezone
from urllib.parse import urlsplit
import httpx
from sqlalchemy import select,text
from app.infrastructure.database.models import FacebookReelJobModel as Job,FacebookPageConnectionModel as Connection,ArtifactModel,PlatformCopyModel,PlatformCopyMediaModel
from app.application import facebook_page_oauth as oauth
from app.application.distribution_readiness import source_fingerprint
from app.application.instagram_plan_review import fingerprint
from app.infrastructure.artifact_storage import S3ArtifactStorage
from app.adapters.publishing.facebook_reels import FacebookReelsEdge,ReelSession


def now():return datetime.now(timezone.utc)

def describe(j):return dict(id=str(j.id),artifact_id=str(j.artifact_id),snapshot=j.snapshot,snapshot_hash=j.snapshot_hash,state=j.state,approved=bool(j.evidence_ref),video_id=(j.remote_session or {}).get('video_id'),permalink=j.permalink,error_code=j.error_code,updated_at=j.updated_at.isoformat(),no_automatic_retry=True)

async def binding(s):
    c=await oauth.configuration(s,True);r=await s.get(Connection,1,populate_existing=True)
    if not r or not r.enabled or oauth.payload(r,c)['state']!='CONNECTED_AT_LAST_CHECK' or not r.last_check_ok:raise ValueError('تحقق من صفحة Facebook المرتبطة أولاً.')
    return dict(page_id=r.page_id,page_name=r.page_name,config_hash=c['fingerprint'],connected_at=r.connected_at.isoformat(),token_hash=oauth.digest(r.token_ciphertext))

async def pinned(s,uid):
    a=await s.get(ArtifactModel,uid,populate_existing=True);p=await s.get(PlatformCopyModel,(uid,'facebook'),populate_existing=True)
    if not a or not p or a.kind!='VIDEO' or a.review_status!='APPROVED' or a.status!='AVAILABLE' or source_fingerprint(a)!=p.source_fingerprint:raise ValueError('فيديو أصلي معتمد ونسخة Facebook حديثة مطلوبان.')
    f=dict(p.fields);version=p.version;source_fp=p.source_fingerprint
    if not isinstance(f.get('description'),str) or len(f['description'])>2200 or any(f.get(k) for k in ['title','tags','alt_text']):raise ValueError('هذا المسار يدعم الوصف الكامل حتى2200حرف فقط، دون تجاهل حقول إضافية.')
    asset=await s.get(PlatformCopyMediaModel,p.selected_media_id,populate_existing=True) if p.selected_media_id else a
    if not asset or asset.mime_type!='video/mp4' or (p.selected_media_id and (asset.artifact_id!=uid or asset.platform!='facebook' or asset.source_fingerprint!=p.source_fingerprint)):raise ValueError('وسيط MP4 حالي لهذه المادة والمنصة مطلوب.')
    data=await S3ArtifactStorage.from_environment().get_bytes(asset.storage_uri,max_bytes=50_000_000)
    from app.domain.platform_media_probe import inspect_media
    import asyncio
    m=await asyncio.to_thread(inspect_media,data,'VIDEO','video/mp4')
    if (not 3<=m['duration_seconds']<=90 or m['width']<540 or m['height']<960 or abs(m['width']/m['height']-9/16)>.005 or not 24<=m['fps']<=60 or m['video_codec'] not in {'h264','hevc'} or m['pixel_format'] not in {'yuv420p','yuvj420p'} or m['field_order'] not in {None,'unknown','progressive'}):raise ValueError('الفيديو لا يطابق حدود Reel الموثقة. لن نغيّر الأصل.')
    if not m['audio'] or any(x['codec']!='aac' or x['channels']!=2 or x['sample_rate']!=48000 or x['bitrate']<128000 for x in m['audio']):raise ValueError('الصوت يتطلب AAC ستيريو48kHz بمعدل128kbps أو أعلى، دون تحويل تلقائي.')
    if m.get('header_evidence',{}).get('closed_gop')!='REFRESH_BOUNDARIES_VERIFIED':raise ValueError('تعذر إثبات closed GOP للفيديو؛ لا رفع قبل الفحص.')
    await s.refresh(a);await s.refresh(p)
    if p.version!=version or p.fields!=f or p.source_fingerprint!=source_fp or a.review_status!='APPROVED' or a.status!='AVAILABLE' or source_fingerprint(a)!=p.source_fingerprint or (str(p.selected_media_id) if p.selected_media_id else None)!=(str(asset.id) if asset is not a else None):raise ValueError('تغير الأصل أو الوسيط أثناء الفحص.')
    return dict(artifact_id=str(uid),source_fingerprint=p.source_fingerprint,copy_version=p.version,caption=f['description'],media_id=str(p.selected_media_id) if p.selected_media_id else None,media_sha256=hashlib.sha256(data).hexdigest(),size_bytes=len(data),measurements=m),data

async def prepare_delivery(s,uid):
    """Private format-only derivative. Exact video packets, narration and IG untouched."""
    import asyncio,subprocess,tempfile
    from pathlib import Path
    from uuid import uuid4
    from app.application.platform_copy_media import current_copy
    a=await s.get(ArtifactModel,uid);ig=await s.get(PlatformCopyModel,(uid,'instagram'));fb=await s.get(PlatformCopyModel,(uid,'facebook'))
    if not a or not ig or not fb or a.kind!='VIDEO' or ig.selected_media_id is not None:raise ValueError('Original approved video and Instagram copy required')
    a,fb=await current_copy(s,uid,'facebook',source_fingerprint(a),fb.version)
    # Only copy exact existing words on the owner's selected material. No generation.
    if ig.source_fingerprint!=source_fingerprint(a):raise ValueError('Instagram copy is stale')
    source=await S3ArtifactStorage.from_environment().get_bytes(a.storage_uri,max_bytes=50_000_000)
    sh=hashlib.sha256(source).hexdigest()
    recipe=dict(kind='FACEBOOK_REEL_AUDIO_COMPAT',version=2,video='COPY',audio='AAC_STEREO_48KHZ_160K',content_changed=False)
    existing=(await s.execute(select(PlatformCopyMediaModel).where(PlatformCopyMediaModel.artifact_id==uid,PlatformCopyMediaModel.platform=='facebook',PlatformCopyMediaModel.source_sha256==sh,PlatformCopyMediaModel.recipe==recipe))).scalars().first()
    if not existing:
        def convert():
            with tempfile.TemporaryDirectory() as td:
                src=Path(td)/'in.mp4';out=Path(td)/'out.mp4';src.write_bytes(source)
                subprocess.run(['ffmpeg','-v','error','-i',str(src),'-map','0:v:0','-map','0:a:0','-c:v','copy','-c:a','aac','-ac','2','-ar','48000','-b:a','160k','-movflags','+faststart','-use_editlist','0','-avoid_negative_ts','disabled',str(out)],check=True,capture_output=True,timeout=90)
                def video_hash(p):return subprocess.run(['ffmpeg','-v','error','-i',str(p),'-map','0:v:0','-c:v','copy','-f','hash','-hash','sha256','-'],check=True,capture_output=True,timeout=30).stdout
                if video_hash(src)!=video_hash(out):raise ValueError('Video packets changed')
                from app.domain.platform_media_probe import inspect_video_file
                return out.read_bytes(),inspect_video_file(str(out))
        content,m=await asyncio.to_thread(convert);mid=uuid4()
        uri=await S3ArtifactStorage.from_environment().put(key=f'artifacts/platform-copies/{uid}/facebook/{mid}.mp4',content=content,content_type='video/mp4')
        existing=PlatformCopyMediaModel(id=mid,artifact_id=uid,platform='facebook',source_fingerprint=source_fingerprint(a),source_sha256=sh,sha256=hashlib.sha256(content).hexdigest(),storage_uri=uri,mime_type='video/mp4',recipe=recipe,measurements=m);s.add(existing)
    fb.fields=dict(ig.fields);fb.selected_media_id=existing.id;fb.version+=1;fb.updated_at=now();await s.commit()
    return dict(media_id=str(existing.id),sha256=existing.sha256,original_unchanged=True,instagram_unchanged=True,video_packets_identical=True,caption_copied_exactly=True,published=False)

async def stage(s,uid):
    await s.execute(select(ArtifactModel).where(ArtifactModel.id==uid).with_for_update())
    facts,_=await pinned(s,uid);b=await binding(s)
    snap={**facts,'connection':b,'audience':'FACEBOOK_PAGE_PUBLIC_REEL','media_disclosure':'EXACT_MP4_BYTES_TO_META_NO_PUBLIC_URL','title':'','time':'NOW_AFTER_EXPLICIT_APPROVAL'};h=fingerprint(snap)
    old=(await s.execute(select(Job).where(Job.artifact_id==uid,Job.snapshot_hash==h,Job.state.in_(['DRAFT','APPROVED','INITIALIZING','SESSION_CREATED','UPLOADING','PROCESSING','FINISHING','FINISH_ACCEPTED','PUBLISHED','OUTCOME_UNKNOWN'])))).scalars().first()
    if old:return describe(old)
    j=Job(artifact_id=uid,snapshot=snap,snapshot_hash=h,state='DRAFT',created_at=now(),updated_at=now());s.add(j);await s.commit();return describe(j)

async def valid(s,j):
    facts,data=await pinned(s,j.artifact_id)
    for k,v in facts.items():
        if j.snapshot.get(k)!=v:raise ValueError('تغير الفيديو أو الوصف؛ لا تنفيذ.')
    if await binding(s)!=j.snapshot['connection']:raise ValueError('تغير ربط الصفحة؛ لا تنفيذ.')
    if not j.evidence_ref or not j.approved_until or j.approved_until<=now():raise ValueError('قرار النشر منتهٍ أو غير موجود.')
    return data

async def approve(s,j,h,evidence):
    if j.state!='DRAFT' or j.snapshot_hash!=h or not re.fullmatch(r'(owner-session|trusted-message):[A-Za-z0-9_.:-]{8,240}',evidence):raise ValueError('يلزم اعتماد المعاينة الحالية.')
    # Temporary checks do not become authority until exact snapshot still matches.
    facts,_=await pinned(s,j.artifact_id)
    if any(j.snapshot.get(k)!=v for k,v in facts.items()) or await binding(s)!=j.snapshot['connection']:raise ValueError('تغيرت المعاينة.')
    j.evidence_ref=evidence;j.approved_until=now()+timedelta(minutes=30);j.state='APPROVED';j.updated_at=now();await s.commit();return describe(j)

async def provider(s,j,client):
    await oauth.verify_saved_connection(s)
    if await binding(s)!=j.snapshot['connection']:raise ValueError('تغيرت الصفحة أو صلاحياتها.')
    r=await s.get(Connection,1,populate_existing=True)
    token=json.loads(oauth.key().decrypt(r.token_ciphertext.encode()))['page_token']
    return FacebookReelsEdge(client=client,token=token,page_id=r.page_id,version='v27.0')

async def claim(s,j,state):j.state=state;j.updated_at=now();await s.commit()

async def reconcile(s,j,p):
    rs=ReelSession(**j.remote_session)
    status=await p.status(rs)
    if status['state']=='REMOTE_ERROR':j.state='REMOTE_ERROR'
    elif status['publishing_complete']:
        d=await p._request('GET',rs.video_id,params={'fields':'id,description,from,permalink_url,published'})
        u=urlsplit(d.get('permalink_url',''))
        if d.get('id')==rs.video_id and d.get('from',{}).get('id')==rs.page_id and d.get('description','')==j.snapshot['caption'] and d.get('published') is True and u.scheme=='https' and u.hostname in {'www.facebook.com','facebook.com','m.facebook.com'} and not u.username and not u.password:
            j.permalink=d['permalink_url'];j.state='PUBLISHED';j.error_code=None
    j.updated_at=now();await s.commit()

async def process_one(s,j):
    async with httpx.AsyncClient(timeout=60,follow_redirects=False) as client:
        p=await provider(s,j,client)
        if j.state in {'FINISH_ACCEPTED','OUTCOME_UNKNOWN'}:
            if j.remote_session:await reconcile(s,j,p)
            return
        data=await valid(s,j)
        flags=dict(authorized=True,public_page_acknowledged=True,media_transfer_authorized=True)
        if j.state=='APPROVED':
            await claim(s,j,'INITIALIZING')
            rs=await p.initialize(content=data,sha256=j.snapshot['media_sha256'],mime_type='video/mp4',inspection_confirmed=True,**flags)
            j.remote_session=asdict(rs);await claim(s,j,'SESSION_CREATED')
        if j.state=='SESSION_CREATED':
            data=await valid(s,j);rs=ReelSession(**j.remote_session)
            await claim(s,j,'UPLOADING');await p.upload(rs,content=data,initial_transfer=True,**flags);await claim(s,j,'PROCESSING')
        if j.state=='PROCESSING':
            rs=ReelSession(**j.remote_session);status=await p.status(rs)
            if status['state']=='REMOTE_ERROR':await claim(s,j,'REMOTE_ERROR');return
            if not status['upload_complete'] or not status['processing_complete']:return
            if not status['publishing_not_started']:await claim(s,j,'OUTCOME_UNKNOWN');return
            await valid(s,j);await claim(s,j,'FINISHING')
            await p.finish(rs,description=j.snapshot['caption'],title='',**flags)
            await claim(s,j,'FINISH_ACCEPTED');await reconcile(s,j,p)

async def process_approved():
    from app.infrastructure.database.session import SessionFactory,engine
    async with engine.connect() as lock_connection, SessionFactory() as s:
        # Dedicated connection owns session lock across job transaction commits.
        got=(await lock_connection.execute(text('SELECT pg_try_advisory_lock(606029)'))).scalar()
        if not got:return
        try:
            interrupted=(await s.execute(select(Job).where(Job.state.in_(['INITIALIZING','UPLOADING','FINISHING'])))).scalars().all()
            for old in interrupted:await claim(s,old,'OUTCOME_UNKNOWN')
            rows=(await s.execute(select(Job).where(Job.state.in_(['APPROVED','SESSION_CREATED','PROCESSING','FINISH_ACCEPTED','OUTCOME_UNKNOWN'])).order_by(Job.created_at).limit(3))).scalars().all()
            for j in rows:
                try:await process_one(s,j)
                except Exception as error:
                    await s.rollback();j=await s.get(Job,j.id,populate_existing=True)
                    j.error_code=getattr(error,'code','FACEBOOK_REEL_CHECK_OR_ACTION_FAILED')
                    j.state='OUTCOME_UNKNOWN' if j.state in {'INITIALIZING','UPLOADING','FINISHING'} else j.state if j.state in {'FINISH_ACCEPTED','OUTCOME_UNKNOWN'} else 'BLOCKED'
                    j.updated_at=now();await s.commit()
        finally:await lock_connection.execute(text('SELECT pg_advisory_unlock(606029)'));await lock_connection.commit()


async def retire_unfinished(s,j):
    """Retire a known session forever before replacing, never delete evidence."""
    if j.state!='OUTCOME_UNKNOWN' or not j.remote_session:raise ValueError('Only a known unknown session can be retired')
    async with httpx.AsyncClient(timeout=30,follow_redirects=False) as client:
        p=await provider(s,j,client)
        body=await p._request('GET',j.remote_session['video_id'],params={'fields':'status'})
        st=body.get('status',{})
        if st.get('video_status')!='uploading' or st.get('processing_phase',{}).get('status')!='not_started' or st.get('publishing_phase',{}).get('status')!='not_started':raise ValueError('Remote session changed; do not replace')
        j.remote_session={**j.remote_session,'retired_status_evidence':st,'retired_at':now().isoformat(),'never_resume':True}
        j.state='RETIRED_UNPUBLISHED';j.updated_at=now();await s.commit();return describe(j)
