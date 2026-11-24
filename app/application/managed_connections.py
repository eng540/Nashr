"""Write-only connection credentials and explicit runtime selection."""
import os,re
from datetime import datetime,timezone
from uuid import UUID
import httpx
from cryptography.fernet import Fernet,InvalidToken
from sqlalchemy import select,text
from app.infrastructure.database.models import ManagedConnectionModel as Connection,ScheduleItemModel,ScheduleModel,PublicationModel,LegacyTelegramBindingModel as Legacy


def key():
    # Infrastructure-only bootstrap key; credentials themselves live in DB.
    raw=os.getenv('NASHR_CONNECTION_ENCRYPTION_KEY','')
    if not raw:raise ValueError('يلزم إعداد مفتاح تشفير الاتصالات في الخادم أولاً. لا تحفظ أي سر قبل ذلك.')
    try:return Fernet(raw.encode())
    except ValueError:raise ValueError('مفتاح تشفير الاتصالات غير صالح.') from None

async def telegram_check(token,destination):
    if not re.fullmatch(r'[0-9]{5,20}:[A-Za-z0-9_-]{20,200}',token):raise ValueError('صيغة رمز البوت غير صالحة.')
    if not re.fullmatch(r'(?:-?[0-9]{1,25}|@[A-Za-z0-9_]{5,100})',destination):raise ValueError('اكتب معرف القناة أو اسمها بصيغة @name.')
    async with httpx.AsyncClient(timeout=15,follow_redirects=False) as client:
        async def call(method,params=None):
            try:
                res=await client.post('https://api.telegram.org/bot'+token+'/'+method,json=params or {});res.raise_for_status();data=res.json()
                if data.get('ok') is not True:raise ValueError()
                return data['result']
            except (httpx.HTTPError,ValueError,KeyError,TypeError):raise ValueError('تعذر التحقق من البوت أو القناة وصلاحياتها. لم يُحفظ الربط ولم يُرسل محتوى.') from None
        bot=await call('getMe')
        if not bot.get('is_bot') or not bot.get('id'):raise ValueError('الرمز لا يرجع هوية بوت صالحة.')
        chat=await call('getChat',{'chat_id':destination})
        if chat.get('type')!='channel':raise ValueError('هذا المسار لقناة Telegram. لم تُضف مجموعة أو حساباً خاصاً.')
        member=await call('getChatMember',{'chat_id':str(chat['id']),'user_id':bot['id']})
        if member.get('status') not in {'administrator','creator'} or member.get('status')=='administrator' and member.get('can_post_messages') is not True:raise ValueError('أضف البوت مسؤولاً بصلاحية نشر الرسائل في القناة أولاً.')
        return {'destination':str(chat['id']),'channel_title':str(chat.get('title',''))[:300],'channel_username':str(chat.get('username',''))[:100],'bot_id':str(bot['id']),'bot_username':str(bot.get('username',''))[:100],'can_post_messages':True}

async def add_telegram(session,label,token,dest):
    crypt=key();details=await telegram_check(token,dest)
    await session.execute(text('SELECT pg_advisory_xact_lock(606025)'))
    duplicate=await session.scalar(select(Connection.id).where(Connection.platform=='telegram',Connection.details['destination'].astext==details['destination']).limit(1))
    if duplicate:raise ValueError('القناة محفوظة بالفعل. لا ننشئ لها هوية ربط أخرى أو نبدل البوت بصمت.')
    row=Connection(platform='telegram',label=label,secret_ciphertext=crypt.encrypt(token.encode()).decode(),details=details,verified_at=datetime.now(timezone.utc));session.add(row);await session.commit()
    return str(row.id)

async def remove(session,uid):
    # Compatibility route is non-destructive, including unused connections.
    await set_enabled(session,uid,False)

async def selected(session,uid,*,allow_disabled=False):
    row=await session.scalar(select(Connection).where(Connection.id==UUID(str(uid))).execution_options(populate_existing=True))
    if row is None or row.platform!='telegram':raise ValueError('قناة Telegram المختارة غير متاحة.')
    if not allow_disabled and row.last_check_ok is False:raise ValueError('فشل آخر تحقق من الربط. أعد التحقق أو حدّث رمز البوت قبل إرسال جديد.')
    if not allow_disabled and not row.enabled:raise ValueError('القناة معطلة محلياً. لم نرسل أو نستخدم وجهة بديلة.')
    try:token=key().decrypt(row.secret_ciphertext.encode()).decode()
    except (InvalidToken,ValueError):raise ValueError('تعذر فتح سر قناة Telegram. لم نستخدم بوتاً بديلاً.') from None
    return row,token

async def schedule_binding(session,schedule):
    review=schedule.telegram_review or {}
    if not review.get('connection_id'):
        legacy=await session.get(Legacy,1)
        if not legacy:return None
        row,token=await selected(session,legacy.connection_id)
        destination=review.get('destination',legacy.original_destination)
        if destination not in allowed_destinations(row):raise ValueError('الوجهة القديمة غير مطابقة للربط المحفوظ. لم نستخدم بديلاً.')
        return destination,SafePublisher(token=token,destination=row.details['destination'])
    row,token=await selected(session,review['connection_id'])
    if review.get('destination') not in allowed_destinations(row) or row.details['bot_id']!=review.get('bot_id'):raise ValueError('تغيرت هوية قناة الخطة؛ لن نرسل إلى بديل.')
    return review['destination'],SafePublisher(token=token,destination=row.details['destination'])

async def overview(session):
    rows=(await session.execute(select(Connection).where(Connection.platform=='telegram').order_by(Connection.verified_at.desc()))).scalars().all()
    try:key();storage=True
    except ValueError:storage=False
    legacy=await session.get(Legacy,1)
    return {'telegram':{'legacy_imported':bool(legacy),'legacy_connection_id':str(legacy.connection_id) if legacy else None,'source':'LEGACY_AND_EXPLICIT_CHANNELS','legacy_configured':bool(os.getenv('TELEGRAM_BOT_TOKEN') and os.getenv('TELEGRAM_DESTINATION_ID')),'credential_storage_ready':storage,'items':[{'id':str(row.id),'label':row.label,'details':row.details,'verified_at':row.verified_at.isoformat(),'enabled':row.enabled,'last_check_ok':row.last_check_ok,'last_check_at':row.last_check_at.isoformat() if row.last_check_at else None,'secret_saved':True}for row in rows]},'platforms':[{'key':key,'label':label,'state':state,'requirements':req}for key,label,state,req in [('youtube','YouTube','SYNTHETIC_EDGE_ONLY','طُوّرت حافة رفع قابل للاستئناف واختُبرت اصطناعياً. إعداد تطبيق Google وOAuth واختيار القناة وحقوق الرفع والخصوصية والموافقة ما زالت مطلوبة؛ لا رفع حي أو جدولة متاحان.'),('facebook','Facebook','NOT_IMPLEMENTED','إعداد تطبيق Meta وصفحة وصلاحيات محددة؛ لا موصل تنفيذ بعد.'),('x','X','NOT_IMPLEMENTED','تطبيق مطور وصلاحيات وقيود تكلفة تحتاج تحققاً؛ لا شراء أو موصل تنفيذ.'),('tiktok','TikTok','NOT_IMPLEMENTED','تجهيز المتطلبات فقط. مسودة داخل TikTok والنشر المباشر مساران مختلفان؛ قبول التطبيق والصلاحيات غير متحققين. لا ربط أو رفع أو نشر حي.')]],'execution_authorized':False}


class SafePublisher:
    def __init__(self,token,destination=None):
        from app.adapters.publishing.telegram import TelegramPublisher
        self.inner=TelegramPublisher(token=token)
        self.destination=destination
    async def publish(self,**kwargs):
        if self.destination:kwargs['destination']=self.destination
        try:return await self.inner.publish(**kwargs)
        except Exception:raise RuntimeError('تعذر تأكيد إرسال Telegram. راجع سجل القناة قبل إعادة المحاولة.') from None
    async def update_live_location(self,**kwargs):
        if self.destination:kwargs['destination']=self.destination
        try:return await self.inner.update_live_location(**kwargs)
        except Exception:raise RuntimeError('تعذر تأكيد عملية الموقع الحي. لا تكررها قبل مراجعة الرسالة.') from None

async def publication_publisher(session,publication,*,allow_disabled=False):
    row,token=await selected(session,publication.connection_id,allow_disabled=allow_disabled)
    if publication.destination not in allowed_destinations(row):raise ValueError('قناة سجل النشر لا تطابق الربط المحفوظ. لم نستخدم بديلاً.')
    return SafePublisher(token,destination=row.details['destination'])


def allowed_destinations(row):
    return {row.details['destination'],row.details.get('legacy_destination',row.details['destination'])}

async def default_binding(session):
    legacy=await session.get(Legacy,1)
    if legacy:
        row,_=await selected(session,legacy.connection_id)
        # Preserve the exact previous address even when getChat canonicalizes it.
        return legacy.original_destination,row.id
    return os.getenv('TELEGRAM_DESTINATION_ID','').strip(),None

async def bind_legacy_publication(session,publication):
    legacy=await session.get(Legacy,1)
    if not legacy:return
    row,_=await selected(session,legacy.connection_id)
    if publication.destination in allowed_destinations(row):publication.connection_id=row.id
    else:raise ValueError('سجل Telegram غير مربوط بهوية محفوظة. لم نستخدم رمز البيئة بديلاً.')

async def pending_call(session,uid):
    busy=await session.scalar(select(PublicationModel.id).where(PublicationModel.connection_id==uid,PublicationModel.status.in_(['READY','PUBLISHING'])).limit(1))
    if busy:raise ValueError('توجد عملية إرسال قيد التنفيذ أو غير محسومة. احسمها قبل تغيير حالة الربط أو رمزه.')

async def import_legacy(session):
    # A deliberate owner action, not an automatic migration or first-page read.
    existing=await session.get(Legacy,1)
    if existing:return {'id':str(existing.connection_id),'already_imported':True,'sent_messages':0}
    crypt=key()
    token=os.getenv('TELEGRAM_BOT_TOKEN','');dest=os.getenv('TELEGRAM_DESTINATION_ID','').strip()
    if not token or not dest:raise ValueError('لا يوجد ربط خادم مكتمل لاستيراده.')
    details=await telegram_check(token,dest)
    await session.execute(text('SELECT pg_advisory_xact_lock(606025)'))
    existing=await session.get(Legacy,1)
    if existing:return {'id':str(existing.connection_id),'already_imported':True,'sent_messages':0}
    # Never bind old message identities while an old call is in flight.
    if await session.scalar(select(PublicationModel.id).where(PublicationModel.platform=='telegram',PublicationModel.destination.in_([dest,details['destination']]),PublicationModel.status.in_(['READY','PUBLISHING'])).limit(1)):raise ValueError('توجد عملية Telegram قيد التنفيذ أو غير محسومة. لم يبدأ الاستيراد.')
    if await session.scalar(select(ScheduleItemModel.id).where(ScheduleItemModel.status=='PROCESSING').limit(1)):raise ValueError('جدولة قيد التنفيذ الآن. أعد الاستيراد بعد حسمها.')
    row=await session.scalar(select(Connection).where(Connection.platform=='telegram',Connection.details['destination'].astext==details['destination']))
    if row:
        if row.details['bot_id']!=details['bot_id']:raise ValueError('القناة محفوظة بهوية بوت مختلفة؛ لم نستبدل ربطها أو نربط السجل تلقائياً.')
        # Even same bot must have a readable, matching token before history bind.
        await selected(session,row.id)
    else:
        details['legacy_destination']=dest
        row=Connection(platform='telegram',label=details['channel_title'] or 'قناة الربط السابق',details=details,secret_ciphertext=crypt.encrypt(token.encode()).decode(),verified_at=datetime.now(timezone.utc),enabled=True,last_check_ok=True,last_check_at=datetime.now(timezone.utc));session.add(row);await session.flush()
    details=dict(row.details);details['legacy_destination']=dest;row.details=details
    pubs=(await session.execute(select(PublicationModel).where(PublicationModel.platform=='telegram',PublicationModel.connection_id.is_(None),PublicationModel.destination.in_([dest,details['destination']])))).scalars().all()
    for pub in pubs:pub.connection_id=row.id
    plans=(await session.execute(select(ScheduleModel).where(ScheduleModel.telegram_review.is_(None) | ScheduleModel.telegram_review['connection_id'].astext.is_(None)).with_for_update())).scalars().all()
    bound=0
    for plan in plans:
        review=plan.telegram_review or {}
        original=review.get('destination',dest)
        if original not in {dest,details['destination']}:continue
        plan.telegram_review={**review,'connection_id':str(row.id),'bot_id':details['bot_id'],'channel_label':row.label,'destination':original,'legacy_imported':True};bound+=1
    session.add(Legacy(id=1,connection_id=row.id,original_destination=dest))
    await session.commit()
    return {'id':str(row.id),'already_imported':False,'bound_publications':len(pubs),'bound_plans':bound,'sent_messages':0}

async def verify_saved(session,uid):
    row,token=await selected(session,uid,allow_disabled=True)
    checked_ciphertext=row.secret_ciphertext
    try:
        details=await telegram_check(token,row.details['destination'])
        if details['destination']!=row.details['destination'] or details['bot_id']!=row.details['bot_id']:raise ValueError('فشل تطابق هوية الربط.')
    except ValueError:
        await session.execute(text('SELECT pg_advisory_xact_lock(606025)'))
        await session.refresh(row)
        if row.secret_ciphertext!=checked_ciphertext:raise ValueError('تغير الرمز أثناء الفحص. أعد التحقق.') from None
        row.last_check_ok=False;row.last_check_at=datetime.now(timezone.utc);await session.commit()
        raise ValueError('فشل آخر تحقق من البوت والقناة والصلاحيات. لم نغيّر السر أو الوجهة.') from None
    await session.execute(text('SELECT pg_advisory_xact_lock(606025)'))
    await session.refresh(row)
    if row.secret_ciphertext!=checked_ciphertext:raise ValueError('تغير الرمز أثناء الفحص. أعد التحقق.')
    row.last_check_ok=True;row.last_check_at=datetime.now(timezone.utc);row.verified_at=row.last_check_at
    await session.commit();return {'verified':True,'sent_messages':0}

async def rotate_token(session,uid,token):
    crypt=key()
    row=await session.get(Connection,UUID(str(uid)))
    if row is None or row.platform!='telegram':raise ValueError('الربط غير موجود.')
    details=await telegram_check(token,row.details['destination'])
    if details['destination']!=row.details['destination'] or details['bot_id']!=row.details['bot_id']:raise ValueError('الرمز يخص بوتاً أو قناة مختلفين. لم نستبدل الربط؛ أضف وجهة جديدة مستقلة عند الحاجة.')
    await session.execute(text('SELECT pg_advisory_xact_lock(606025)'))
    await session.refresh(row)
    await pending_call(session,uid)
    row.secret_ciphertext=crypt.encrypt(token.encode()).decode();row.last_check_ok=True;row.last_check_at=datetime.now(timezone.utc);row.verified_at=row.last_check_at
    await session.commit();return {'updated':True,'enabled':row.enabled,'sent_messages':0}

async def set_enabled(session,uid,enabled):
    if enabled:await verify_saved(session,uid)
    await session.execute(text('SELECT pg_advisory_xact_lock(606025)'))
    row=await session.scalar(select(Connection).where(Connection.id==UUID(str(uid)),Connection.platform=='telegram').execution_options(populate_existing=True))
    if row is None:raise ValueError('الربط غير موجود.')
    await pending_call(session,uid)
    row.enabled=enabled;await session.commit()
    return {'enabled':enabled,'history_preserved':True,'remote_changed':False,'sent_messages':0}
