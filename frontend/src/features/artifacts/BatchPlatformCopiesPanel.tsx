import {useRef,useState} from 'react';
import {genericArtifactsApi,type CentralPlatformCopy,type GenericReviewableArtifact} from '../../shared/api/artifactsApi';

type Result={artifact_id:string;items:CentralPlatformCopy[]};
const platforms=[['telegram','Telegram'],['instagram','Instagram'],['facebook','Facebook'],['youtube','YouTube'],['x','X'],['tiktok','TikTok']];
export function BatchPlatformCopiesPanel({ids,items,onPreparing}:{ids:string[];items:GenericReviewableArtifact[];onPreparing:()=>void}){
 const identity=ids.join(',');const scope=useRef({identity});if(scope.current.identity!==identity)scope.current={identity};
 const [result,setResult]=useState<{scope:typeof scope.current;rows:Result[];prepared:boolean}|null>(null);
 const [pending,setPending]=useState(false),[error,setError]=useState<{scope:typeof scope.current;text:string}|null>(null);
 const current=result?.scope===scope.current?result:null;
 async function read(prepare:boolean){
  if(prepare)onPreparing();
  const requestScope=scope.current,requested=[...ids];setPending(true);setResult(null);setError(null);
  try{
   const rows=prepare?(await genericArtifactsApi.prepareBatchCopies(requested)).items:await Promise.all(requested.map(async id=>({artifact_id:id,...await genericArtifactsApi.platformCopies(id)})));
   if(rows.length!==requested.length||new Set(rows.map(r=>r.artifact_id)).size!==requested.length||requested.some(id=>!rows.some(r=>r.artifact_id===id))||rows.some(r=>new Set(r.items.map(c=>c.platform)).size!==r.items.length||r.items.some(c=>!platforms.some(([key])=>key===c.platform))))throw new Error('لم تكتمل قراءة نسخ الدفعة نفسها. أعد القراءة، لم نستبدلها بمواد أخرى.');
   if(scope.current===requestScope)setResult({scope:requestScope,rows:requested.map(id=>rows.find(r=>r.artifact_id===id)!),prepared:prepare});
  }catch(e){if(scope.current===requestScope)setError({scope:requestScope,text:(e as Error).message});}
  finally{if(prepare)onPreparing();setPending(false);}
 }
 return <section aria-label="نسخ منصات الدفعة" className="space-y-3 rounded-xl border border-violet-200 bg-violet-50/50 p-3">
  <h4 className="font-bold">تجهيز الدفعة لكل منصة</h4>
  <p className="text-xs leading-7">اعتماد الأصل واحد. اعرض النسخ المحفوظة أو جهز الناقص فقط، دون استبدال تعديلاتك. لا يغير هذا اختيار الوجهات أو استثناءات المواد، ولا ينشئ خطة أو ينشر شيئاً.</p>
  <div className="flex flex-wrap gap-2"><button disabled={pending||!ids.length||ids.length>100} className="workspace-secondary" onClick={()=>void read(false)}>عرض نسخ الدفعة المحفوظة ({ids.length})</button><button disabled={pending||!ids.length||ids.length>100} className="workspace-secondary" onClick={()=>void read(true)}>تجهيز نسخ المنصات للمحدد ({ids.length})</button></div>
  {pending?<p role="status">جارٍ قراءة أو تجهيز نسخ الدفعة...</p>:null}
  {error?.scope===scope.current?<p role="alert" className="break-words text-sm text-rose-800">{error.text}</p>:null}
  {current?<><p role="status" className="text-xs leading-7">{current.prepared?'جُهزت السجلات الناقصة':'قُرئت النسخ المحفوظة'} لعدد {current.rows.length} مادة دون إرسال أو جدولة. قبول الحقول لا يعني جاهزية الوسيط أو الحساب أو إذن النشر.</p>
   <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">{platforms.map(([platform,label])=>{
    const entries=current.rows.map(r=>({row:r,copy:r.items.find(c=>c.platform===platform)}));
    const valid=entries.filter(e=>e.copy?.field_status==='FIELDS_VALIDATED'&&!e.copy.source_stale).length,missing=entries.filter(e=>!e.copy).length;
    return <details key={platform} className="min-w-0 rounded-lg border bg-white p-3"><summary className="cursor-pointer text-sm font-bold">{label} · {valid}/{ids.length} حقول مقبولة</summary><p className="text-xs leading-7">{missing} بلا نسخة محفوظة · {ids.length-valid-missing} تحتاج مراجعة</p><ol className="space-y-3 pt-2">{entries.map(({row,copy},index)=>{
     const item=items.find(i=>i.id===row.artifact_id);const title=item?.organization?.title||item?.metadata.title||item?.metadata.original_filename||row.artifact_id.slice(0,8);
     return <li key={row.artifact_id} className="min-w-0 border-t pt-2 text-xs leading-7"><p className="break-words" dir="auto">{index+1}. {String(title)}</p><p>{!copy?'لم تُجهز نسخة بعد':copy.source_stale?'تغير الأصل، راجع النسخة':copy.blockers[0]||(copy.field_status==='FIELDS_VALIDATED'?'حقول مقبولة مبدئياً':'تحتاج مراجعة')}</p><a target="_blank" rel="noreferrer" className="inline-block underline" href={`/bank?artifact_status=APPROVED&artifact_id=${encodeURIComponent(row.artifact_id)}&copy_platform=${platform}`}>فتح نسخة {label} لهذه المادة في نافذة جديدة</a></li>;
    })}</ol></details>;
   })}</div></>:null}
 </section>;
}
