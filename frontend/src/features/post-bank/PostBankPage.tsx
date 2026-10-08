import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useEffect, useMemo, useState } from "react";
import { postsApi } from "../../shared/api/postsApi";
import { productionJobsApi, type ProductionScope } from "../../shared/api/productionJobsApi";
import { toggleSelection } from "../../shared/utils/selection";

export function PostBankPage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [status, setStatus] = useState(searchParams.get("status") ?? "");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [reviewNote, setReviewNote] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [scope, setScope] = useState<ProductionScope>("SOURCE");
  const [topicId, setTopicId] = useState("");
  const [materialIds, setMaterialIds] = useState<string[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [message, setMessage] = useState("");

  const posts = useQuery({ queryKey: ["post-bank", status, query], queryFn: () => postsApi.list({ status: status || undefined, query }) });
  const sources = useQuery({ queryKey: ["production", "sources"], queryFn: productionJobsApi.sources });
  const bookMap = useQuery({ queryKey: ["production", "book-map", sourceId], queryFn: () => productionJobsApi.bookMap(sourceId), enabled: Boolean(sourceId) });
  const job = useQuery({ queryKey: ["production", "job", jobId], queryFn: () => productionJobsApi.get(jobId!), enabled: Boolean(jobId), refetchInterval: (q) => q.state.data && ["COMPLETED", "FAILED"].includes(q.state.data.status) ? false : 1500 });

  useEffect(() => {
    if (sources.data?.length === 1 && !sourceId) setSourceId(sources.data[0].id);
  }, [sources.data, sourceId]);

  const review = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "approve" | "reject" }) => action === "approve" ? postsApi.approve(id, reviewNote) : postsApi.reject(id, reviewNote),
    onSuccess: () => { setEditing(null); setReviewNote(""); void client.invalidateQueries({ queryKey: ["post-bank"] }); },
  });
  const save = useMutation({
    mutationFn: () => postsApi.update(editing!, content),
    onSuccess: () => { setEditing(null); void client.invalidateQueries({ queryKey: ["post-bank"] }); },
  });
  const bulkApprove = useMutation({
    mutationFn: () => postsApi.bulkApprove(selected),
    onSuccess: (result) => { setMessage(`اعتمد ${result.approved_count} منشور، وفشل ${result.failed_count}.`); setSelected([]); void client.invalidateQueries({ queryKey: ["post-bank"] }); },
  });
  const createProduction = useMutation({
    mutationFn: () => {
      if (!sourceId) throw new Error("اختر كتابًا أولًا.");
      if (scope === "TOPIC" && !topicId) throw new Error("اختر محورًا.");
      if (scope === "SELECTION" && !materialIds.length) throw new Error("اختر مادة واحدة على الأقل.");
      return productionJobsApi.create({ source_id: sourceId, scope, ...(scope === "TOPIC" ? { topic_id: topicId } : {}), ...(scope === "SELECTION" ? { knowledge_unit_ids: materialIds } : {}) });
    },
    onSuccess: (data) => { setJobId(data.job_id); setMessage("بدأ إنتاج المنشورات."); void client.invalidateQueries({ queryKey: ["post-bank"] }); },
  });
  const retryProduction = useMutation({ mutationFn: () => productionJobsApi.resume(jobId!), onSuccess: (data) => setJobId(data.job_id) });

  const items = posts.data?.items ?? [];
  const approvedSelected = useMemo(() => items.filter((p) => selected.includes(p.post_id) && p.status === "APPROVED"), [items, selected]);
  const topics = bookMap.data?.topics ?? [];
  const materials = scope === "TOPIC" ? topics.find((t) => t.id === topicId)?.materials ?? [] : (topics.flatMap((t) => t.materials) ?? []);

  if (posts.isLoading) return <p role="status">جاري تحميل بنك المنشورات...</p>;
  if (posts.isError) return <p role="alert">{posts.error.message}</p>;

  return <section data-testid="post-bank-workspace" className="space-y-6">
    <header className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-sm font-semibold text-indigo-600">Workspace 02</p><h2 className="mt-1 text-3xl font-bold">مصنع المنشورات</h2><p className="mt-2 text-sm text-slate-600">إنتاج، مراجعة واعتماد.</p></div><Link to="/publishing" className="rounded-xl border px-4 py-2 text-sm font-semibold">مساحة النشر</Link></header>

    <section className="rounded-2xl border bg-white p-5 shadow-sm" data-testid="production-panel">
      <h3 className="text-xl font-bold">أنشئ Posts من كتاب</h3>
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <select aria-label="الكتاب" value={sourceId} onChange={(e) => { setSourceId(e.target.value); setTopicId(""); setMaterialIds([]); }} className="rounded-xl border p-3"><option value="">اختر كتابًا...</option>{(sources.data ?? []).map(s => <option key={s.id} value={s.id}>{s.book_title || s.filename}</option>)}</select>
        <select aria-label="نطاق الإنتاج" value={scope} onChange={(e) => setScope(e.target.value as ProductionScope)} className="rounded-xl border p-3"><option value="SOURCE">الكتاب كاملًا</option><option value="TOPIC">محور محدد</option><option value="SELECTION">مواد أحددها بنفسي</option></select>
        {scope === "TOPIC" && <select aria-label="المحور" value={topicId} onChange={(e) => { setTopicId(e.target.value); setMaterialIds([]); }} className="rounded-xl border p-3"><option value="">اختر محورًا...</option>{topics.map(t => <option key={t.id} value={t.id}>{t.position}. {t.title}</option>)}</select>}
      </div>
      {scope === "SELECTION" && <div className="mt-4 max-h-64 overflow-auto rounded-xl border">{materials.map(m => <label key={m.id} className="flex gap-3 border-b p-3"><input type="checkbox" checked={materialIds.includes(m.id)} onChange={e => setMaterialIds(toggleSelection(materialIds, m.id, e.target.checked))}/><span><strong>{m.title}</strong><span className="block text-xs text-slate-500">{m.kind}</span></span></label>)}</div>}
      <div className="mt-4 flex flex-wrap items-center gap-3"><button data-testid="start-production" type="button" onClick={() => createProduction.mutate()} disabled={createProduction.isPending || !sourceId} className="rounded-xl bg-indigo-600 px-5 py-3 font-bold text-white disabled:opacity-40">تشغيل إنتاج المنشورات</button><span className="text-sm text-slate-500">{scope === "SELECTION" ? materialIds.length + " مادة محددة" : scope === "TOPIC" ? "إنتاج مواد المحور" : "إنتاج مواد الكتاب كاملة"}</span></div>
      {(job.data || jobId) && <div className="mt-4 rounded-xl border bg-slate-50 p-4"><div className="flex justify-between"><strong>{job.data?.status ?? "QUEUED"}</strong><span>{job.data?.completed_items ?? 0} مكتمل · {job.data?.pending_items ?? 0} متبقٍ · {job.data?.failed_items ?? 0} فشل من {job.data?.total_items ?? 0}</span></div>{job.data?.failed_items ? <button type="button" onClick={() => retryProduction.mutate()} className="mt-3 rounded-lg bg-amber-600 px-4 py-2 text-sm font-bold text-white">إعادة تشغيل العناصر الفاشلة</button> : null}</div>}
    </section>

    {message && <div role="status" className="rounded-xl border bg-indigo-50 p-4 text-sm">{message}</div>}

    <div className="rounded-2xl border bg-white p-4 shadow-sm"><div className="grid gap-3 sm:grid-cols-[180px_1fr_auto]"><select aria-label="حالة المنشور" value={status} onChange={e => { setStatus(e.target.value); setSearchParams(e.target.value ? { status: e.target.value } : {}); }} className="rounded-xl border p-3"><option value="">كل الحالات</option><option value="DRAFT">مسودة</option><option value="APPROVED">معتمد</option><option value="REJECTED">مرفوض</option></select><input aria-label="بحث المنشورات" value={query} onChange={e => setQuery(e.target.value)} placeholder="ابحث..." className="rounded-xl border p-3"/><span className="rounded-xl bg-slate-100 px-4 py-3 text-sm font-semibold">{selected.length} محدد</span></div><div className="mt-3 flex flex-wrap gap-2"><button type="button" onClick={() => bulkApprove.mutate()} disabled={!selected.length || bulkApprove.isPending} className="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-40">اعتماد المحدد</button>{approvedSelected.length > 0 && <button data-testid="go-publishing" type="button" onClick={() => navigate(`/publishing?selected_post_ids=${approvedSelected.map(p => p.post_id).join(",")}`)} className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-bold text-white">الانتقال إلى النشر ({approvedSelected.length})</button>}</div></div>

    <div className="space-y-3">{items.map(post => { const checked = selected.includes(post.post_id); return <article key={post.post_id} className="rounded-2xl border bg-white p-5 shadow-sm"><div className="flex items-start gap-3"><input aria-label={`تحديد ${post.title}`} type="checkbox" checked={checked} onChange={e => setSelected(toggleSelection(selected, post.post_id, e.target.checked))} className="mt-1 h-4 w-4"/><button type="button" onClick={() => { setEditing(post.post_id); setContent(post.content); setReviewNote(post.review_note ?? ""); }} className="min-w-0 flex-1 text-right"><strong className="block">{post.title}</strong><span className="mt-1 block text-xs text-slate-500">{post.source_title} · {post.status}</span><p className="mt-2 text-sm leading-7 text-slate-600">{post.content_preview}</p></button></div></article> })}</div>

    {editing && <div className="fixed inset-0 z-20 grid place-items-center bg-slate-950/30 p-4"><div role="dialog" className="w-full max-w-3xl rounded-2xl bg-white p-6 shadow-xl"><h3 className="text-xl font-bold">مراجعة المنشور</h3><textarea aria-label="محتوى المنشور" value={content} onChange={e => setContent(e.target.value)} className="mt-4 min-h-48 w-full rounded-xl border p-4"/><input aria-label="ملاحظة المراجعة" value={reviewNote} onChange={e => setReviewNote(e.target.value)} placeholder="ملاحظة أو سبب الرفض" className="mt-3 w-full rounded-xl border p-3"/><div className="mt-5 flex flex-wrap gap-2"><button type="button" onClick={() => save.mutate()} disabled={save.isPending} className="rounded-xl border px-4 py-2 font-semibold">حفظ</button><button type="button" onClick={() => review.mutate({id: editing, action:"approve"})} disabled={review.isPending} className="rounded-xl bg-emerald-600 px-4 py-2 font-semibold text-white">اعتماد</button><button type="button" onClick={() => review.mutate({id: editing, action:"reject"})} disabled={review.isPending || !reviewNote.trim()} className="rounded-xl bg-rose-600 px-4 py-2 font-semibold text-white">رفض</button><button type="button" onClick={() => setEditing(null)} className="rounded-xl bg-slate-100 px-4 py-2 font-semibold">إغلاق</button></div></div></div>}
  </section>;
}
