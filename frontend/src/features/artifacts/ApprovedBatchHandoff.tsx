import type {GenericReviewableArtifact} from "../../shared/api/artifactsApi";

export function ApprovedBatchHandoff({ids,items,loading,failed,onContinue,onClear}:{
 ids:string[];items:GenericReviewableArtifact[];loading:boolean;failed:boolean;
 onContinue:(ids:string[])=>void;onClear:()=>void;
}) {
 const valid=ids.length>0&&ids.length<=100&&new Set(ids).size===ids.length&&ids.every(id=>/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id));
 const rows=ids.map(id=>items.find(i=>i.id===id));
 const complete=valid&&!loading&&!failed&&rows.every(i=>i&&i.review_status==="APPROVED"&&i.status==="AVAILABLE"&&i.metadata.source_type!=="PLATFORM_VARIANT");
 return <section aria-label="متابعة الدفعة المعتمدة" className="space-y-3 rounded-xl border border-emerald-200 bg-emerald-50/60 p-3">
  <h3 className="font-bold">تابع الدفعة نفسها إلى التجهيز والوجهات</h3>
  <p className="text-sm leading-7">الرابط يحتفظ بمعرّفات {ids.length} مادة فقط، لا جميع المواد المعتمدة. نعيد قراءة حالتها قبل تحديدها. لا يختار منصات ولا ينشئ خطة أو ينشر شيئاً.</p>
  {loading?<p role="status">جارٍ التحقق من المواد المعتمدة...</p>:!complete?<p role="alert" className="text-sm text-rose-800">تعذر التحقق من كامل الدفعة، أو تغيرت حالة إحدى موادها. لم نحدد جزءاً منها ولم نستبدلها بمواد أخرى. حدّث القراءة أو امسح رابط الدفعة.</p>:null}
  <details><summary>المواد المحددة في رابط المتابعة ({ids.length})</summary><ol className="space-y-2 pt-2">{ids.map((id,n)=><li key={`${id}-${n}`} className="min-w-0 break-words text-sm"><span dir="auto">{rows[n]?String(rows[n]?.organization?.title||rows[n]?.metadata.title||rows[n]?.metadata.original_filename||`${rows[n]?.kind} · ${id.slice(0,8)}`):"مادة غير متاحة في القراءة الحالية"}</span><bdi className="block break-all text-xs">{id}</bdi></li>)}</ol></details>
  <div className="flex flex-wrap gap-2"><button className="workspace-primary" disabled={!complete} onClick={()=>onContinue(ids)}>تحديد الدفعة نفسها للتجهيز ({ids.length})</button><button className="workspace-secondary" onClick={onClear}>مسح متابعة الدفعة</button></div>
 </section>;
}
