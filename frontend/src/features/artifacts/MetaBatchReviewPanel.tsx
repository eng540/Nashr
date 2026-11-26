import {useEffect,useRef,useState} from 'react';
import {genericArtifactsApi,type CentralPlatformCopy,type DistributionReadiness,type GenericReviewableArtifact} from '../../shared/api/artifactsApi';
import {scheduleTimePreview,utcISOStringToLocalDateTime} from '../../shared/utils/timezone';

type Row={id:string;readiness:DistributionReadiness;copies:CentralPlatformCopy[]};
const supported=['instagram','facebook'];
function route(platform:string,kind:string){return platform==='instagram'&&['IMAGE','VIDEO'].includes(kind)?'Instagram':platform==='facebook'&&kind==='VIDEO'?'Facebook Reel':platform==='facebook'&&kind==='IMAGE'?'Facebook صورة':platform==='facebook'&&kind==='TEXT'?'Facebook نص':null;}
export function MetaBatchReviewPanel({ids,items}:{ids:string[];items:GenericReviewableArtifact[]}){
 const identity=JSON.stringify(ids),scope=useRef({identity});if(scope.current.identity!==identity)scope.current={identity};
 const [result,setResult]=useState<{scope:typeof scope.current;rows:Row[]}|null>(null);
 const [error,setError]=useState<{scope:typeof scope.current;text:string}|null>(null),[pending,setPending]=useState(false);
 const [start,setStart]=useState(''),[zone,setZone]=useState(''),[interval,setInterval]=useState('');
 const valid=ids.length>0&&ids.length<=100&&new Set(ids).size===ids.length&&ids.every(id=>{const a=items.find(a=>a.id===id);return a&&a.review_status==='APPROVED'&&a.status==='AVAILABLE'&&a.metadata.source_type!=='PLATFORM_VARIANT';});
 const current=valid&&result?.scope===scope.current?result:null;
 useEffect(()=>{setStart('');setZone('');setInterval('');},[identity]);
 async function load(){
  const requested=[...ids],requestScope=scope.current;setPending(true);setResult(null);setError(null);
  try{
   const rows:Row[]=new Array(requested.length);let next=0;
   await Promise.all(Array.from({length:Math.min(4,requested.length)},async()=>{while(next<requested.length){const i=next++,id=requested[i];const readiness=await genericArtifactsApi.readiness(id);const copies=await genericArtifactsApi.platformCopies(id);
    if(readiness.artifact_id!==id||readiness.central_approval!=='APPROVED'||!Array.isArray(readiness.targets)||new Set(readiness.targets.map(t=>t.platform)).size!==readiness.targets.length||supported.some(platform=>!readiness.targets.some(t=>t.platform===platform))||readiness.targets.some(t=>typeof t.selected!=='boolean'||!Array.isArray(t.copy_blockers)||!Array.isArray(t.execution_blockers))||!Array.isArray(copies.items)||new Set(copies.items.map(c=>c.platform)).size!==copies.items.length||copies.items.some(c=>!c.fields||typeof c.fields.description!=='string'||!Number.isInteger(c.version)||c.version<1))throw new Error('تعذر التحقق من الدفعة نفسها. لم نعرض جزءاً منها أو نستبدل موادها.');
    rows[i]={id,readiness,copies:copies.items};}}));
   if(scope.current===requestScope)setResult({scope:requestScope,rows});
  }catch(e){if(scope.current===requestScope)setError({scope:requestScope,text:(e as Error).message});}finally{setPending(false);}
 }
 let times:string[]=[],timeError='';
 if(current&&(start||zone||interval)){try{if(!start||!zone||!interval)throw new Error('أكمل البداية والمنطقة والفاصل لتظهر المواعيد المقترحة.');times=scheduleTimePreview(start,zone,Number(interval),current.rows.length);}catch(e){timeError=(e as Error).message;}}
 return <section aria-label="مراجعة دفعة Meta" className="space-y-3 rounded-xl border border-emerald-200 bg-emerald-50/50 p-3">
  <h4 className="font-bold">راجع توزيع الدفعة على Meta في مكان واحد</h4>
  <p className="text-xs leading-7">نقرأ الوجهات والنسخ المحفوظة للمواد المحددة فقط، مع إبقاء استثناءات كل مادة. هذه ورقة مراجعة قبل التنفيذ، لا خطة محفوظة ولا إذن تنفيذ. لا نفحص اتصال الحساب أو سجل النشر أو العمليات الجارية هنا، ولا نجهز أو نرسل شيئاً.</p>
  <button type="button" disabled={!valid||pending} onClick={()=>void load()} className="workspace-secondary">{pending?'قراءة الدفعة نفسها...':`مراجعة وجهات Meta المحفوظة للمحدد (${ids.length})`}</button>
  {!valid?<p role="alert">اختر حتى100مادة أصلية معتمدة ومتاحة، دون تكرار.</p>:null}
  {pending?<p role="status">جارٍ قراءة اختيارات الدفعة ونسخها، لا إنشاء عمليات...</p>:null}
  {error?.scope===scope.current?<p role="alert" className="break-words text-rose-800">{error.text}</p>:null}
  {current?<>
   <p role="status" className="text-sm">قُرئت {current.rows.length} مادة بترتيب اختيارك. حدّث هذه القراءة بعد تغيير الوجهات أو النسخ في نافذة أخرى.</p>
   <details className="rounded border bg-white p-3"><summary className="cursor-pointer font-semibold">اقتراح مواعيد محلي دون حفظ</summary>
    <p className="text-xs leading-7">اختياري: موعد واحد لكل مادة، للوجهات المختارة لها فقط. الفاصل بين المواد بترتيبها أدناه، لا بين المنصات. هذه قيم للحساب فقط ولا تُرسل لمسارات التنفيذ. كل منصة تعيد فحص حدود موعدها والحساب والمحتوى قبل أي قرار.</p>
    <div className="grid gap-2 sm:grid-cols-3"><label className="text-xs">بداية مقترحة<input aria-label="بداية مراجعة دفعة Meta" type="datetime-local" value={start} onChange={e=>setStart(e.target.value)} className="block w-full min-w-0 rounded border p-2"/></label><label className="text-xs">منطقة IANA<input aria-label="منطقة مراجعة دفعة Meta" placeholder="Asia/Riyadh" value={zone} onChange={e=>setZone(e.target.value)} className="block w-full min-w-0 rounded border p-2"/></label><label className="text-xs">الفاصل بالدقائق<input aria-label="فاصل مراجعة دفعة Meta" type="number" min="1" max="10080" value={interval} onChange={e=>setInterval(e.target.value)} className="block w-full min-w-0 rounded border p-2"/></label></div>
    {timeError?<p role="alert" className="text-xs text-amber-900">{timeError}</p>:null}
   </details>
   {current.rows.map((row,n)=>{const item=items.find(i=>i.id===row.id)!;const selected=row.readiness.targets.filter(t=>t.selected);const targets=selected.filter(t=>supported.includes(t.platform));return <article key={row.id} className="min-w-0 space-y-2 rounded border bg-white p-3 text-xs leading-7">
    <h5 className="break-words font-bold">{n+1}. {String(item.organization?.title||item.metadata.title||item.metadata.original_filename||row.id)}</h5>
    <bdi className="block break-all text-slate-500">{row.id}</bdi>
    {times[n]?<p className="rounded bg-slate-50 p-2">مقترح محلي، غير محفوظ: <bdi>{utcISOStringToLocalDateTime(times[n],zone)} · {zone}</bdi><bdi className="block break-all">UTC: {times[n]}</bdi></p>:null}
    {row.readiness.selection_stale?<p role="alert" className="text-amber-900">تغير الأصل منذ اختيار الوجهات. راجع الاختيارات واحفظها صراحةً قبل المتابعة، لا نعتمدها كاختيار حالي.</p>:null}
    {!targets.length?<p>لم تُحفظ وجهة Meta لهذه المادة. لا نختارها تلقائياً.</p>:null}
    {selected.some(t=>!supported.includes(t.platform))?<p>وجهات محفوظة خارج هذه المراجعة: {selected.filter(t=>!supported.includes(t.platform)).map(t=>t.label).join('، ')}. لم تُلغَ ولم تُضف إلى Meta.</p>:null}
    {targets.map(target=>{const copy=row.copies.find(c=>c.platform===target.platform),label=route(target.platform,item.kind);return <div key={target.platform} className="space-y-1 rounded border p-2">
     <p className="font-bold">{label||target.label+' · لا مسار تنفيذ لهذا النوع هنا'}</p>
     <p>{!copy?'لا نسخة محفوظة، لم ننشئها من هذه القراءة':copy.source_stale?'تغير الأصل، راجع النسخة':copy.field_status==='FIELDS_VALIDATED'?'حقول النسخة المحفوظة مقبولة مبدئياً':'حقول النسخة تحتاج مراجعة'}{copy?` · إصدار ${copy.version}`:''}</p>
     {target.copy_blockers.map(reason=><p key={reason} className="break-words text-amber-900">{reason}</p>)}
     {target.execution_blockers.map(reason=><p key={reason} className="break-words text-slate-600">{reason}</p>)}
     {copy?<details><summary className="cursor-pointer">النص المحفوظ لهذه المنصة دون قص</summary><p dir="auto" className="whitespace-pre-wrap break-words">{copy.fields.description}</p></details>:null}
     <a className="inline-block underline" href={`/bank?artifact_status=APPROVED&artifact_id=${encodeURIComponent(row.id)}&copy_platform=${target.platform}`} target="_blank" rel="noreferrer">فتح نسخة {target.label} ومراجعة مسارها دون نشر</a>
    </div>;})}
   </article>;})}
  </>:null}
 </section>;
}
