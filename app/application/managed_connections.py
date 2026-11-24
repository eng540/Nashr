"""Write-only connection credentials and explicit runtime selection."""
import os,re
from datetime import datetime,timezone
from uuid import UUID
import httpx
from cryptography.fernet import Fernet,InvalidToken
from sqlalchemy import select,delete,text
from app.infrastructure.database.models import ManagedConnectionModel as Connection,ScheduleItemModel,ScheduleModel,PublicationModel


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
    await session.execute(text('SELECT pg_advisory_xact_lock(606025)'))
    # A connection used by a plan/publication is immutable history, not a
    # replaceable global default. Keep the credential until safe archival exists.
    plans=(await session.execute(select(ScheduleModel.telegram_review).where(ScheduleModel.telegram_review.is_not(None)))).scalars().all()
    if any(str(uid)==str(p.get('connection_id')) for p in plans):raise ValueError('الربط مستخدم في خطة محفوظة؛ لم نحذفه كي لا تنقطع هوية القناة وسجلها.')
    if await session.scalar(select(PublicationModel.id).where(PublicationModel.connection_id==uid).limit(1)):raise ValueError('الربط مستخدم في سجل نشر؛ لم نحذفه للحفاظ على هوية الرسائل.')
    await session.execute(delete(Connection).where(Connection.id==uid));await session.commit()

async def selected(session,uid):
    row=await session.get(Connection,UUID(str(uid)))
    if row is None or row.platform!='telegram':raise ValueError('قناة Telegram المختارة غير متاحة.')
    try:token=key().decrypt(row.secret_ciphertext.encode()).decode()
    except (InvalidToken,ValueError):raise ValueError('تعذر فتح سر قناة Telegram. لم نستخدم بوتاً بديلاً.') from None
    return row,token

async def schedule_binding(session,schedule):
    review=schedule.telegram_review or {}
    if not review.get('connection_id'):return None
    row,token=await selected(session,review['connection_id'])
    if row.details['destination']!=review.get('destination') or row.details['bot_id']!=review.get('bot_id'):raise ValueError('تغيرت هوية قناة الخطة؛ لن نرسل إلى بديل.')
    return row.details['destination'],SafePublisher(token=token)

async def overview(session):
    rows=(await session.execute(select(Connection).where(Connection.platform=='telegram').order_by(Connection.verified_at.desc()))).scalars().all()
    try:key();storage=True
    except ValueError:storage=False
    return {'telegram':{'source':'LEGACY_AND_EXPLICIT_CHANNELS','legacy_configured':bool(os.getenv('TELEGRAM_BOT_TOKEN') and os.getenv('TELEGRAM_DESTINATION_ID')),'credential_storage_ready':storage,'items':[{'id':str(row.id),'label':row.label,'details':row.details,'verified_at':row.verified_at.isoformat(),'secret_saved':True}for row in rows]},'platforms':[{'key':key,'label':label,'state':state,'requirements':req}for key,label,state,req in [('youtube','YouTube','NOT_IMPLEMENTED','إعداد تطبيق Google وOAuth واختيار قناة وحقوق الرفع؛ لا موصل تنفيذ بعد.'),('facebook','Facebook','NOT_IMPLEMENTED','إعداد تطبيق Meta وصفحة وصلاحيات محددة؛ لا موصل تنفيذ بعد.'),('x','X','NOT_IMPLEMENTED','تطبيق مطور وصلاحيات وقيود تكلفة تحتاج تحققاً؛ لا شراء أو موصل تنفيذ.'),('tiktok','TikTok','PAUSED','الربط متوقف بطلب المستخدم؛ لم نعد التسجيل أو النشر.')]],'execution_authorized':False}


class SafePublisher:
    def __init__(self,token):
        from app.adapters.publishing.telegram import TelegramPublisher
        self.inner=TelegramPublisher(token=token)
    async def publish(self,**kwargs):
        try:return await self.inner.publish(**kwargs)
        except Exception:raise RuntimeError('تعذر تأكيد إرسال Telegram. راجع سجل القناة قبل إعادة المحاولة.') from None
    async def update_live_location(self,**kwargs):
        try:return await self.inner.update_live_location(**kwargs)
        except Exception:raise RuntimeError('تعذر تأكيد عملية الموقع الحي. لا تكررها قبل مراجعة الرسالة.') from None

async def publication_publisher(session,publication):
    row,token=await selected(session,publication.connection_id)
    if row.details['destination']!=publication.destination:raise ValueError('قناة سجل النشر لا تطابق الربط المحفوظ. لم نستخدم بديلاً.')
    return SafePublisher(token)
