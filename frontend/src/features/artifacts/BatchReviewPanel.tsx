import { useState, type ReactNode } from "react";
import { genericArtifactsApi, type GenericReviewableArtifact } from "../../shared/api/artifactsApi";

type Snapshot = GenericReviewableArtifact & { review_fingerprint: string };
export function BatchReviewPanel({ items, pageItems, unsavedIds, renderMedia, onApproved }: {
  items: GenericReviewableArtifact[]; pageItems: GenericReviewableArtifact[]; unsavedIds: string[];
  renderMedia: (item: GenericReviewableArtifact) => ReactNode; onApproved: (ids:string[]) => void;
}) {
  const [ids, setIds] = useState<string[]>([]);
  const [preview, setPreview] = useState<Snapshot[] | null>(null);
  const [reviewed, setReviewed] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const originals = items.filter(i => i.review_status === "DRAFT" && i.status === "AVAILABLE" && i.metadata.source_type !== "PLATFORM_VARIANT" && i.metadata.telegram_album == null && i.metadata.telegram_live_photo == null);
  const selected = originals.filter(i => ids.includes(i.id));
  const unsaved = selected.some(i => unsavedIds.includes(i.id));
  const select = (next: string[]) => { setIds([...new Set(next)].slice(0,100)); setPreview(null); setReviewed([]); setError(""); setDone(""); };
  const load = async () => {
    setBusy(true); setError(""); setPreview(null); setReviewed([]);
    try {
      const requested=[...ids]; const result = await genericArtifactsApi.previewBatchReview(requested);
      if(result.publishing_authorized!==false||result.items.length!==requested.length||new Set(result.items.map(i=>i.id)).size!==requested.length||requested.some(id=>!result.items.some(i=>i.id===id))||result.items.some(i=>i.review_status!=="DRAFT"||i.status!=="AVAILABLE"||!i.review_fingerprint||i.metadata.source_type==="PLATFORM_VARIANT"||i.metadata.telegram_album!=null||i.metadata.telegram_live_photo!=null))throw new Error("لم تتطابق معاينة الدفعة مع الأصول المحددة. أعد القراءة دون اعتماد مواد أخرى.");
      setPreview(requested.map(id=>result.items.find(i=>i.id===id)!));
    }
    catch(e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const approve = async () => {
    if(!preview || unsaved || busy || preview.length!==ids.length || preview.some(i=>!ids.includes(i.id)||!reviewed.includes(i.id))) return;
    setBusy(true); setError("");
    try { const result = await genericArtifactsApi.approveBatchReview(preview); if(result.publishing_authorized!==false||result.approved_ids.length!==preview.length||new Set(result.approved_ids).size!==preview.length||preview.some(i=>!result.approved_ids.includes(i.id)))throw new Error("لم تتطابق نتيجة الاعتماد مع الدفعة. قد يكون الحفظ تم، حدّث المكتبة وتحقق من الحالات قبل أي محاولة جديدة."); setDone(`اعتمدت ${result.approved_ids.length} مادة وجهزت نسخ المنصات. لم ينشر أو يجدول شيء.`); setPreview(null); setReviewed([]); setIds([]); onApproved(result.approved_ids); }
    catch(e) { setError((e as Error).message); setPreview(null); setReviewed([]); }
    finally { setBusy(false); }
  };
  return <section aria-label="مراجعة واعتماد دفعة" className="space-y-3 rounded-xl border border-indigo-200 bg-indigo-50/50 p-3">
    <h3 className="font-bold">مراجعة واعتماد دفعة</h3>
    <p className="text-sm leading-7">اختر الأصول، ثم راجع نسخة محفوظة كاملة لكل مادة. الاعتماد يجهز نسخ المنصات فقط ولا يسمح بالنشر أو الجدولة. حتى100مادة. الألبومات والصور الحية تراجع منفردة لضمان معاينة عناصرها.</p>
    <div className="flex flex-wrap gap-2">
      <button className="workspace-secondary" disabled={busy} onClick={()=>select([...ids,...pageItems.filter(i=>originals.some(o=>o.id===i.id)).map(i=>i.id)])}>تحديد أصول الصفحة للمراجعة</button>
      <button className="workspace-secondary" disabled={busy||!ids.length} onClick={()=>select([])}>مسح تحديد المراجعة</button>
      <span role="status">{ids.length} محدد للمراجعة</span>
    </div>
    <details><summary>اختيار مواد الصفحة</summary><div className="space-y-2 pt-2">{pageItems.filter(i=>originals.some(o=>o.id===i.id)).map(i=><label className="flex items-start gap-2 text-sm" key={i.id}><input type="checkbox" disabled={busy||!ids.includes(i.id)&&ids.length>=100} checked={ids.includes(i.id)} onChange={e=>select(e.target.checked?[...ids,i.id]:ids.filter(id=>id!==i.id))}/><span className="min-w-0 break-words" dir="auto">{String(i.metadata.title||i.kind)} · {i.id.slice(0,8)}</span></label>)}</div></details>
    {unsaved?<p role="alert" className="text-amber-900">بعض المواد المحددة لها تعديلات غير محفوظة. احفظها أو أزلها من الدفعة قبل المراجعة.</p>:null}
    <button className="workspace-secondary" disabled={busy||!ids.length||selected.length!==ids.length||unsaved} onClick={()=>void load()}>{busy?"جارٍ التحقق...":`معاينة الدفعة المحفوظة (${ids.length})`}</button>
    {preview?<div className="space-y-3" aria-label="معاينة الاعتماد الجماعي"><p className="text-sm">راجع كل أصل وضع علامة المراجعة. أي تغيير محفوظ بعد هذه المعاينة يمنع اعتماد الدفعة كلها.</p>{preview.map(i=><article key={i.id} className="min-w-0 space-y-2 rounded-xl border bg-white p-3"><h4 className="break-words font-bold" dir="auto">{String(i.metadata.title||i.kind)}</h4><bdi className="block break-all text-xs">{i.id}</bdi><p className="text-xs">{i.kind} · {i.mime_type}</p>{renderMedia(i)}<p className="whitespace-pre-wrap break-words text-sm leading-7" dir="auto">{i.content??String(i.metadata.caption??"")}</p><details><summary>بيانات المادة وملاحظات المراجعة</summary><pre className="max-w-full whitespace-pre-wrap break-all text-xs" dir="auto">{JSON.stringify(i.metadata,null,2)}</pre><p>{i.review_note}</p></details><label className="flex items-start gap-2 text-sm"><input aria-label={`راجعت أصل المادة ${i.id}`} type="checkbox" disabled={busy} checked={reviewed.includes(i.id)} onChange={e=>setReviewed(r=>e.target.checked?[...r,i.id]:r.filter(id=>id!==i.id))}/>راجعت النص والوسيط وبيانات هذه المادة وأوافق على اعتماد أصلها.</label></article>)}<button className="workspace-primary" disabled={busy||unsaved||preview.some(i=>!reviewed.includes(i.id))} onClick={()=>void approve()}>تأكيد اعتماد الدفعة فقط ({preview.length})</button></div>:null}
    {error?<p role="alert" className="break-words text-rose-800">{error}</p>:null}{done?<p role="status" className="text-emerald-800">{done}</p>:null}
  </section>;
}
