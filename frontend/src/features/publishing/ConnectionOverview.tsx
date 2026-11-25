import {useQueries} from '@tanstack/react-query';
import {get} from '../../shared/api/client';
type Saved={username?:string;page_name?:string;page_id?:string;title?:string;channel_title?:string;display_name?:string;state?:string;enabled?:boolean;last_check_at?:string|null;last_check_ok?:boolean|null};
type Status={configured:boolean;connection:Saved|null;pending?:unknown};
const specs=[{key:'instagram-connection',path:'instagram',name:'Instagram · Unified',target:'instagram-unified',capability:'نشر الصور والفيديو من المسار المعتمد، الربط ليس إذناً'},
{key:'facebook-page-connection',path:'facebook',name:'Facebook',target:'platform-facebook',capability:'نصوص وصور وReels بقرار منفصل'},
{key:'instagram-direct-connection',path:'instagram-direct',name:'Instagram · مباشر',target:'instagram-direct',capability:'ربط مستقل، لا نبدّل إليه أو ننشر تلقائياً'},
{key:'instagram-page-connection',path:'instagram-page',name:'Instagram · عبر صفحة',target:'instagram-page',capability:'ربط مستقل عبر صفحة Facebook، لا يغير Unified'},
{key:'youtube-channel',path:'youtube',name:'YouTube',target:'platform-youtube',capability:'قراءة هوية القناة فقط، لا رفع'},
{key:'tiktok-identity',path:'tiktok',name:'TikTok',target:'platform-tiktok',capability:'ربط الهوية فقط، لا رفع أو نشر'}];
export function ConnectionOverview(){
 const queries=useQueries({queries:specs.map(s=>({queryKey:[s.key],queryFn:()=>get<Status>('/api/connections/'+s.path),retry:false}))});
 return <section className="connection-overview" aria-label="ملخص الحسابات المحفوظة"><div><h2 className="workspace-section-title">حساباتك وخطوتك التالية</h2><p className="workspace-muted">حالة محفوظة من آخر تحقق، وليست فحصاً حياً أو إذناً بالنشر. افتح الحساب للتحقق أو الإدارة.</p></div><div className="connection-overview-grid">{specs.map((s,i)=>{const q=queries[i],d=q.data,c=d?.connection;
 const disabled=c?.enabled===false||c?.state==='DISABLED',attention=c?.state==='RECONNECT_REQUIRED'||c?.last_check_ok===false;
 const tone=q.isError||attention?'attention':disabled?'neutral':c?'saved':'neutral';
 const label=q.isPending?'جارٍ تحميل الحالة':q.isError?'تعذر قراءة الحالة':disabled?'معطل محلياً':attention?'يلزم مراجعة الربط':c?'حساب محفوظ':d?.pending?'اختيار الحساب لم يكتمل':d?.configured?'الإعداد جاهز، الحساب غير مربوط':'الإعداد غير مكتمل';
 const identity=c?.username?'@'+c.username:c?.page_name||c?.title||c?.channel_title||c?.display_name;
 return <article key={s.path} className={'connection-overview-card tone-'+tone}><div className="flex items-center justify-between gap-2"><h3><bdi>{s.name}</bdi></h3><span className="connection-overview-state">{label}</span></div>{identity?<p className="connection-account"><bdi>{identity}</bdi></p>:<p className="workspace-muted">{q.isPending?'نقرأ الحالة دون تغيير الربط.':q.isError?'لا نعتبر فشل القراءة حساباً غير مربوط.':'لا توجد هوية حساب محفوظة هنا.'}</p>}<p className="connection-capability">{s.capability}</p>{c?.last_check_at?<p className="connection-check">آخر تحقق مسجل: <bdi>{new Intl.DateTimeFormat('ar-SA-u-ca-gregory-nu-latn',{dateStyle:'medium',timeStyle:'short',timeZone:'Asia/Riyadh'}).format(new Date(c.last_check_at))}</bdi> · الرياض</p>:c?<p className="connection-check">وقت آخر تحقق غير موثق في هذا الملخص.</p>:null}<div className="flex flex-wrap gap-2">{q.isError?<button className="workspace-secondary" onClick={()=>void q.refetch()}>إعادة قراءة {s.name}</button>:null}<a className="workspace-secondary" href={'#'+s.target}>إدارة {s.name}</a></div></article>;
 })}</div></section>;
}
