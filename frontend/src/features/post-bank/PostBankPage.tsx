import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useEffect, useMemo, useState } from "react";
import { postsApi } from "../../shared/api/postsApi";
import { productionJobsApi, type ProductionScope } from "../../shared/api/productionJobsApi";
import { toggleSelection } from "../../shared/utils/selection";

const PAGE_SIZE = 30;
const ALL_SOURCES = "ALL";

type SortMode = "created" | "title" | "kind" | "topic";

export function PostBankPage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [status, setStatus] = useState(searchParams.get("status") ?? "");
  const [filterSourceId, setFilterSourceId] = useState(ALL_SOURCES);
  const [topicId, setTopicId] = useState("");
  const [kind, setKind] = useState("");
  const [sort, setSort] = useState<SortMode>("created");
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  // A filtered deep link (for example ?status=APPROVED) is an explicit request
  // to open that result set; the plain workspace still waits for the user's scope.
  const [hasLoaded, setHasLoaded] = useState(() => Boolean(searchParams.get("status")));
  const [selected, setSelected] = useState<string[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [reviewNote, setReviewNote] = useState("");
  const [productionSourceId, setProductionSourceId] = useState("");
  const [scope, setScope] = useState<ProductionScope>("SOURCE");
  const [productionTopicId, setProductionTopicId] = useState("");
  const [materialIds, setMaterialIds] = useState<string[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [message, setMessage] = useState("");

  const sources = useQuery({ queryKey: ["production", "sources"], queryFn: productionJobsApi.sources });
  const filterOptions = useQuery({
    queryKey: ["post-bank", "filter-options", filterSourceId],
    queryFn: () => postsApi.filterOptions(filterSourceId === ALL_SOURCES ? undefined : filterSourceId),
  });
  const posts = useQuery({
    queryKey: ["post-bank", filterSourceId, topicId, status, kind, query, sort, page],
    queryFn: () => postsApi.list({
      sourceId: filterSourceId === ALL_SOURCES ? undefined : filterSourceId,
      topicId: topicId || undefined,
      status: status || undefined,
      kind: kind || undefined,
      query: query || undefined,
      sort,
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    }),
    enabled: hasLoaded,
    placeholderData: (previous) => previous,
  });
  const bookMap = useQuery({ queryKey: ["production", "book-map", productionSourceId], queryFn: () => productionJobsApi.bookMap(productionSourceId), enabled: Boolean(productionSourceId) });
  const job = useQuery({ queryKey: ["production", "job", jobId], queryFn: () => productionJobsApi.get(jobId!), enabled: Boolean(jobId), refetchInterval: (q) => q.state.data && ["COMPLETED", "FAILED"].includes(q.state.data.status) ? false : 1500 });

  useEffect(() => {
    const timer = window.setTimeout(() => { setQuery(queryInput.trim()); setPage(0); }, 300);
    return () => window.clearTimeout(timer);
  }, [queryInput]);
  useEffect(() => { setPage(0); setSelected([]); }, [filterSourceId, topicId, status, kind, sort]);
  useEffect(() => {
    if (sources.data?.length === 1 && !productionSourceId) setProductionSourceId(sources.data[0].id);
  }, [sources.data, productionSourceId]);

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
      if (!productionSourceId) throw new Error("اختر كتابًا أولًا.");
      if (scope === "TOPIC" && !productionTopicId) throw new Error("اختر محورًا.");
      if (scope === "SELECTION" && !materialIds.length) throw new Error("اختر مادة واحدة على الأقل.");
      return productionJobsApi.create({ source_id: productionSourceId, scope, ...(scope === "TOPIC" ? { topic_id: productionTopicId } : {}), ...(scope === "SELECTION" ? { knowledge_unit_ids: materialIds } : {}) });
    },
    onSuccess: (data) => { setJobId(data.job_id); setMessage("بدأ إنتاج المنشورات."); void client.invalidateQueries({ queryKey: ["post-bank"] }); },
    onError: (error) => setMessage(error instanceof Error ? error.message : "تعذر بدء الإنتاج."),
  });
  const retryProduction = useMutation({ mutationFn: () => productionJobsApi.resume(jobId!), onSuccess: (data) => setJobId(data.job_id) });

  const items = posts.data?.items ?? [];
  const total = posts.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPageIds = items.map((post) => post.post_id);
  const allCurrentSelected = currentPageIds.length > 0 && currentPageIds.every((id) => selected.includes(id));
  const approvedSelected = useMemo(() => items.filter((p) => selected.includes(p.post_id) && p.status === "APPROVED"), [items, selected]);
  const topics = bookMap.data?.topics ?? [];
  const materials = scope === "TOPIC" ? topics.find((t) => t.id === productionTopicId)?.materials ?? [] : topics.flatMap((t) => t.materials);
  const filterTopics = filterOptions.data?.topics ?? [];

  const loadBank = () => { setPage(0); setSelected([]); setHasLoaded(true); };
  const clearFilters = () => { setFilterSourceId(ALL_SOURCES); setTopicId(""); setKind(""); setStatus(""); setSort("created"); setQueryInput(""); setQuery(""); setPage(0); setSelected([]); setSearchParams({}); };
  const toggleCurrentPage = (checked: boolean) => setSelected((current) => checked ? Array.from(new Set([...current, ...currentPageIds])) : current.filter((id) => !currentPageIds.includes(id)));

  return <section data-testid="post-bank-workspace" className="space-y-6">
    <header className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-sm font-semibold text-indigo-600">Workspace 02</p><h2 className="mt-1 text-3xl font-bold">مصنع المنشورات</h2><p className="mt-2 max-w-2xl text-sm leading-7 text-slate-600">حوّل المواد إلى منشورات، ثم راجعها واعتمدها قبل نقلها إلى مساحة النشر.</p></div><Link to="/publishing" className="rounded-xl border px-4 py-2 text-sm font-semibold">مساحة النشر</Link></header>

    <section className="rounded-2xl border bg-white p-5 shadow-sm" data-testid="post-bank-filters">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-xl font-bold">ابدأ من بنك المنشورات</h3><p className="mt-1 text-sm text-slate-500">اختر نطاق العمل أولًا؛ لن يتم تحميل القائمة كاملة تلقائيًا.</p></div>{hasLoaded && <button type="button" onClick={loadBank} className="rounded-xl border px-4 py-2 text-sm font-semibold">تحديث النتائج</button>}</div>
      <div className="mt-4 grid gap-3 md:grid-cols-2 lg:grid-cols-4">
        <label className="text-sm font-semibold">الكتاب<select aria-label="كتاب بنك المنشورات" value={filterSourceId} onChange={(e) => { setFilterSourceId(e.target.value); setTopicId(""); }} className="mt-2 w-full rounded-xl border p-3 font-normal"><option value={ALL_SOURCES}>كل الكتب</option>{(sources.data ?? []).map((source) => <option key={source.id} value={source.id}>{source.book_title || source.filename}</option>)}</select></label>
        <label className="text-sm font-semibold">الحالة<select aria-label="حالة المنشور" value={status} onChange={(e) => { setStatus(e.target.value); setSearchParams(e.target.value ? { status: e.target.value } : {}); }} className="mt-2 w-full rounded-xl border p-3 font-normal"><option value="">كل الحالات</option><option value="DRAFT">مسودة</option><option value="APPROVED">معتمد</option><option value="REJECTED">مرفوض</option></select></label>
        <label className="text-sm font-semibold">النوع<select aria-label="نوع المادة" value={kind} onChange={(e) => setKind(e.target.value)} className="mt-2 w-full rounded-xl border p-3 font-normal"><option value="">كل الأنواع</option>{(filterOptions.data?.kinds ?? []).map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label className="text-sm font-semibold">المحور<select aria-label="محور المادة" value={topicId} disabled={filterSourceId === ALL_SOURCES} onChange={(e) => setTopicId(e.target.value)} className="mt-2 w-full rounded-xl border p-3 font-normal disabled:bg-slate-100"><option value="">كل المحاور</option>{filterTopics.map((topic) => <option key={topic.id} value={topic.id}>{topic.position}. {topic.title}</option>)}</select></label>
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-[1fr_220px_auto]"><label className="text-sm font-semibold"><span className="sr-only">بحث المنشورات</span><input aria-label="بحث المنشورات" value={queryInput} onChange={(e) => setQueryInput(e.target.value)} placeholder="ابحث في العنوان أو النص..." className="w-full rounded-xl border p-3 font-normal" /></label><label className="text-sm font-semibold">الفرز<select aria-label="فرز المنشورات" value={sort} onChange={(e) => setSort(e.target.value as SortMode)} className="mt-2 w-full rounded-xl border p-3 font-normal"><option value="created">الأحدث أولًا</option><option value="title">العنوان: أ - ي</option><option value="kind">النوع</option><option value="topic">المحور</option></select></label><div className="flex items-end gap-2"><button type="button" onClick={clearFilters} className="rounded-xl border px-4 py-3 text-sm font-semibold">مسح الفلاتر</button><button data-testid="load-post-bank" type="button" onClick={loadBank} className="rounded-xl bg-indigo-600 px-5 py-3 text-sm font-bold text-white">عرض النتائج</button></div></div>
      {filterSourceId === ALL_SOURCES && <p className="mt-3 text-xs text-slate-500">فلتر المحور يتاح بعد اختيار كتاب محدد، بينما النوع والبحث يعملان على كل الكتب.</p>}
    </section>

    <section className="rounded-2xl border bg-white p-5 shadow-sm" data-testid="production-panel"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-xl font-bold">إنتاج منشورات جديدة</h3><p className="mt-1 text-sm text-slate-500">هذا المسار منفصل عن فلاتر العرض؛ اختر كتابًا ونطاق الإنتاج عند الحاجة.</p></div></div><div className="mt-4 grid gap-3 md:grid-cols-3"><select aria-label="الكتاب للإنتاج" value={productionSourceId} onChange={(e) => { setProductionSourceId(e.target.value); setProductionTopicId(""); setMaterialIds([]); }} className="rounded-xl border p-3"><option value="">اختر كتابًا...</option>{(sources.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.book_title || s.filename}</option>)}</select><select aria-label="نطاق الإنتاج" value={scope} onChange={(e) => setScope(e.target.value as ProductionScope)} className="rounded-xl border p-3"><option value="SOURCE">الكتاب كاملًا</option><option value="TOPIC">محور محدد</option><option value="SELECTION">مواد أحددها بنفسي</option></select>{scope === "TOPIC" && <select aria-label="المحور للإنتاج" value={productionTopicId} onChange={(e) => { setProductionTopicId(e.target.value); setMaterialIds([]); }} className="rounded-xl border p-3"><option value="">اختر محورًا...</option>{topics.map((t) => <option key={t.id} value={t.id}>{t.position}. {t.title}</option>)}</select>}</div>{scope === "SELECTION" && <div className="mt-4 max-h-64 overflow-auto rounded-xl border">{materials.map((m) => <label key={m.id} className="flex gap-3 border-b p-3"><input type="checkbox" checked={materialIds.includes(m.id)} onChange={(e) => setMaterialIds(toggleSelection(materialIds, m.id, e.target.checked))}/><span><strong>{m.title}</strong><span className="block text-xs text-slate-500">{m.kind}</span></span></label>)}</div>}<div className="mt-4 flex flex-wrap items-center gap-3"><button data-testid="start-production" type="button" onClick={() => createProduction.mutate()} disabled={createProduction.isPending || !productionSourceId} className="rounded-xl bg-indigo-600 px-5 py-3 font-bold text-white disabled:opacity-40">تشغيل إنتاج المنشورات</button><span className="text-sm text-slate-500">{scope === "SELECTION" ? `${materialIds.length} مادة محددة` : scope === "TOPIC" ? "إنتاج مواد المحور" : "إنتاج مواد الكتاب كاملة"}</span></div>{(job.data || jobId) && <div className="mt-4 rounded-xl border bg-slate-50 p-4"><div className="flex justify-between"><strong>{job.data?.status ?? "QUEUED"}</strong><span>{job.data?.completed_items ?? 0} مكتمل · {job.data?.pending_items ?? 0} متبقٍ · {job.data?.failed_items ?? 0} فشل من {job.data?.total_items ?? 0}</span></div>{job.data?.failed_items ? <button type="button" onClick={() => retryProduction.mutate()} className="mt-3 rounded-lg bg-amber-600 px-4 py-2 text-sm font-bold text-white">إعادة تشغيل العناصر الفاشلة</button> : null}</div>}</section>

    {message && <div role="status" className="rounded-xl border bg-indigo-50 p-4 text-sm">{message}</div>}
    {!hasLoaded ? <div className="rounded-2xl border border-dashed bg-white p-10 text-center"><h3 className="text-lg font-bold">بنك المنشورات جاهز</h3><p className="mt-2 text-sm text-slate-500">اختر كتابًا أو كل الكتب، ثم اضغط «عرض النتائج» لبدء التصفح.</p></div> : posts.isLoading && !posts.data ? <div role="status" className="rounded-2xl border bg-white p-10 text-center">جاري تحميل الصفحة الأولى فقط...</div> : posts.isError ? <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-5">تعذر تحميل المنشورات: {posts.error.message}</div> : <section className="space-y-3" aria-label="نتائج بنك المنشورات"><div className="rounded-2xl border bg-white p-4 shadow-sm"><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-bold">النتائج</h3><p className="text-sm text-slate-500">{total ? `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, total)} من ${total}` : "لا توجد نتائج"}</p></div><div className="flex flex-wrap gap-2"><button type="button" onClick={() => toggleCurrentPage(!allCurrentSelected)} disabled={!items.length} className="rounded-xl border px-3 py-2 text-sm font-semibold">{allCurrentSelected ? "إلغاء تحديد الصفحة" : "تحديد الصفحة"}</button><span className="rounded-xl bg-slate-100 px-3 py-2 text-sm font-semibold">{selected.length} محدد</span><button type="button" onClick={() => setSelected([])} disabled={!selected.length} className="rounded-xl border px-3 py-2 text-sm disabled:opacity-40">مسح التحديد</button></div></div><div className="mt-3 flex flex-wrap gap-2"><button type="button" onClick={() => bulkApprove.mutate()} disabled={!selected.length || bulkApprove.isPending} className="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-40">اعتماد المحدد</button>{approvedSelected.length > 0 && <button data-testid="go-publishing" type="button" onClick={() => navigate(`/publishing?selected_post_ids=${approvedSelected.map((p) => p.post_id).join(",")}`)} className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-bold">الانتقال إلى النشر ({approvedSelected.length})</button>}</div></div>{!items.length ? <div className="rounded-2xl border border-dashed bg-white p-10 text-center"><h3 className="font-bold">لا توجد نتائج مطابقة</h3><p className="mt-2 text-sm text-slate-500">جرّب تغيير الكتاب أو الحالة أو النوع أو البحث.</p></div> : items.map((post) => { const checked = selected.includes(post.post_id); return <article key={post.post_id} className="rounded-2xl border bg-white p-5 shadow-sm"><div className="flex items-start gap-3"><input aria-label={`تحديد ${post.title}`} type="checkbox" checked={checked} onChange={(e) => setSelected(toggleSelection(selected, post.post_id, e.target.checked))} className="mt-1 h-4 w-4"/><button type="button" onClick={() => { setEditing(post.post_id); setContent(post.content); setReviewNote(post.review_note ?? ""); }} className="min-w-0 flex-1 text-right"><strong className="block">{post.title}</strong><span className="mt-1 block text-xs text-slate-500">{post.source_title} · {post.topic_title || "دون محور"} · {post.status}</span><p className="mt-2 text-sm leading-7 text-slate-600">{post.content_preview}</p></button></div></article>; })}<div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border bg-white p-4"><button type="button" onClick={() => setPage((value) => Math.max(0, value - 1))} disabled={page === 0 || posts.isFetching} className="rounded-xl border px-4 py-2 disabled:opacity-40">السابق</button><span className="text-sm font-semibold">صفحة {page + 1} من {pageCount}</span><button type="button" onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))} disabled={page >= pageCount - 1 || posts.isFetching} className="rounded-xl border px-4 py-2 disabled:opacity-40">التالي</button></div></section>}

    {editing && <div className="fixed inset-0 z-20 grid place-items-center bg-slate-950/30 p-4"><div role="dialog" className="max-h-[calc(100dvh-2rem)] w-full max-w-3xl overflow-y-auto rounded-2xl bg-white p-6 shadow-xl"><h3 className="text-xl font-bold">مراجعة المنشور</h3><textarea aria-label="محتوى المنشور" value={content} onChange={(e) => setContent(e.target.value)} className="mt-4 min-h-48 w-full rounded-xl border p-4"/><input aria-label="ملاحظة المراجعة" value={reviewNote} onChange={(e) => setReviewNote(e.target.value)} placeholder="ملاحظة أو سبب الرفض" className="mt-3 w-full rounded-xl border p-3"/><div className="mt-5 flex flex-wrap gap-2"><button type="button" onClick={() => save.mutate()} disabled={save.isPending} className="rounded-xl border px-4 py-2 font-semibold">حفظ</button><button type="button" onClick={() => review.mutate({ id: editing, action: "approve" })} disabled={review.isPending} className="rounded-xl bg-emerald-600 px-4 py-2 font-semibold text-white">اعتماد</button><button type="button" onClick={() => review.mutate({ id: editing, action: "reject" })} disabled={review.isPending || !reviewNote.trim()} className="rounded-xl bg-rose-600 px-4 py-2 font-semibold text-white">رفض</button><button type="button" onClick={() => setEditing(null)} className="rounded-xl bg-slate-100 px-4 py-2 font-semibold">إغلاق</button></div></div></div>}
  </section>;
}
