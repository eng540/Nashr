import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useEffect, useMemo, useState } from "react";
import { postsApi } from "../../shared/api/postsApi";
import { productionJobsApi, type ProductionLineFilter, type ProductionScope, type ProductionProductOption, type EditorialIdentityOption, type ProductionRecipeOption } from "../../shared/api/productionJobsApi";
import { GenericArtifactReviewPanel } from "../artifacts/GenericArtifactReviewPanel";
import { toggleSelection } from "../../shared/utils/selection";

const PAGE_SIZE = 30;
const ALL_SOURCES = "ALL";
const PENDING_CLAIM_STORAGE_KEY = "nashr.pending-production-claim.v1";
type PendingClaim = { key: string; payload: string };
type CreateProductionRequest = { source_id: string; scope: ProductionScope; topic_id?: string; knowledge_unit_ids?: string[]; identity_key?: string; product_key?: string; idempotency_key: string };

function productionLineFilter(products: ProductionProductOption[] | undefined, identities: EditorialIdentityOption[] | undefined, recipes: ProductionRecipeOption[] | undefined, productKey: string, identityKey: string): ProductionLineFilter {
  const product = products?.find((item) => item.key === productKey);
  const productVersion = product?.versions.find((version) => version.version === product.active_version);
  const recipeKey = productVersion?.definition.recipe_key;
  const recipe = recipes?.find((item) => item.key === recipeKey);
  const identity = identities?.find((item) => item.key === identityKey);
  return { product_key: product?.key, product_version: product?.active_version ?? undefined, identity_key: identity?.key, identity_version: identity?.active_version ?? undefined, recipe_key: recipeKey, recipe_version: recipe?.active_version ?? undefined };
}

function pendingRequestFromStorage(): Partial<CreateProductionRequest> | null {
  try {
    const stored = window.localStorage.getItem(PENDING_CLAIM_STORAGE_KEY);
    if (!stored) return null;
    const claim = JSON.parse(stored) as PendingClaim;
    if (!claim.key || !claim.payload) return null;
    const request = JSON.parse(claim.payload) as Partial<CreateProductionRequest>;
    return request.source_id && request.scope ? request : null;
  } catch { return null; }
}

function pendingClaimFor(payload: string): PendingClaim {
  const stored = window.localStorage.getItem(PENDING_CLAIM_STORAGE_KEY);
  if (stored) {
    try {
      const claim = JSON.parse(stored) as PendingClaim;
      if (claim.key && claim.payload === payload) return claim;
      if (claim.key && claim.payload !== payload) throw new Error("هناك مطالبة سابقة لم تُحسم بعد بإعدادات مختلفة. استخدم «بدء مطالبة جديدة» إذا كنت تقصد إنشاء مطالبة مستقلة.");
    } catch (error) {
      if (error instanceof Error && error.message.includes("مطالبة سابقة")) throw error;
      window.localStorage.removeItem(PENDING_CLAIM_STORAGE_KEY);
    }
  }
  const key = typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `claim-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const claim = { key, payload };
  window.localStorage.setItem(PENDING_CLAIM_STORAGE_KEY, JSON.stringify(claim));
  return claim;
}

function clearPendingClaim(key?: string) {
  const stored = window.localStorage.getItem(PENDING_CLAIM_STORAGE_KEY);
  if (!stored) return;
  try {
    const claim = JSON.parse(stored) as PendingClaim;
    if (!key || claim.key === key) window.localStorage.removeItem(PENDING_CLAIM_STORAGE_KEY);
  } catch { window.localStorage.removeItem(PENDING_CLAIM_STORAGE_KEY); }
}

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
  const [productionSourceId, setProductionSourceId] = useState(() => pendingRequestFromStorage()?.source_id ?? "");
  const [identityKey, setIdentityKey] = useState(() => pendingRequestFromStorage()?.identity_key ?? "");
  const [productKey, setProductKey] = useState(() => pendingRequestFromStorage()?.product_key ?? "ARABIC_LITERATURE_TELEGRAM_POST");
  const [productionMode, setProductionMode] = useState<"ALL" | "NEEDS" | "DONE">(() => pendingRequestFromStorage() ? "ALL" : "NEEDS");
  const [productionKind, setProductionKind] = useState("");
  const [scope, setScope] = useState<ProductionScope>(() => pendingRequestFromStorage()?.scope ?? "SOURCE");
  const [productionTopicId, setProductionTopicId] = useState(() => pendingRequestFromStorage()?.topic_id ?? "");
  const [materialIds, setMaterialIds] = useState<string[]>(() => pendingRequestFromStorage()?.knowledge_unit_ids ?? []);
  const [jobId, setJobId] = useState<string | null>(null);
  const [message, setMessage] = useState("");

  const identities = useQuery({ queryKey: ["control-plane", "identities"], queryFn: productionJobsApi.identities });
  const products = useQuery({ queryKey: ["control-plane", "products"], queryFn: productionJobsApi.products });
  const recipes = useQuery({ queryKey: ["control-plane", "recipes"], queryFn: productionJobsApi.recipes });
  const lineFilter = productionLineFilter(products.data, identities.data, recipes.data, productKey, identityKey);
  const sources = useQuery({
    queryKey: ["production", "sources", lineFilter.product_key, lineFilter.product_version, lineFilter.identity_key, lineFilter.identity_version, lineFilter.recipe_key, lineFilter.recipe_version],
    queryFn: () => productionJobsApi.sources(lineFilter),
  });
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
  const bookMap = useQuery({ queryKey: ["production", "book-map", productionSourceId, lineFilter.product_key, lineFilter.product_version, lineFilter.identity_key, lineFilter.identity_version, lineFilter.recipe_key, lineFilter.recipe_version], queryFn: () => productionJobsApi.bookMap(productionSourceId, lineFilter), enabled: Boolean(productionSourceId) });
  const [jobItemsPage, setJobItemsPage] = useState(0);
  const job = useQuery({ queryKey: ["production", "job", jobId], queryFn: () => productionJobsApi.get(jobId!), enabled: Boolean(jobId), refetchInterval: (q) => q.state.data && ["COMPLETED", "FAILED"].includes(q.state.data.status) ? false : 1500 });
  const jobItems = useQuery({ queryKey: ["production", "job-items", jobId, jobItemsPage], queryFn: () => productionJobsApi.items(jobId!, jobItemsPage * 20, 20), enabled: Boolean(jobId) });

  useEffect(() => {
    const timer = window.setTimeout(() => { setQuery(queryInput.trim()); setPage(0); }, 300);
    return () => window.clearTimeout(timer);
  }, [queryInput]);
  useEffect(() => { setPage(0); setSelected([]); }, [filterSourceId, topicId, status, kind, sort]);
  useEffect(() => {
    if (sources.data?.length === 1 && !productionSourceId) setProductionSourceId(sources.data[0].id);
  }, [sources.data, productionSourceId]);
  useEffect(() => {
    if (!products.data) return;
    const available = products.data.filter((product) => product.active_version !== null);
    if (!available.some((product) => product.key === productKey)) setProductKey(available[0]?.key ?? "");
  }, [products.data, productKey]);

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
    mutationFn: (request: CreateProductionRequest) => productionJobsApi.create(request),
    onSuccess: (data, request) => {
      clearPendingClaim(request.idempotency_key);
      setJobId(data.job_id); setJobItemsPage(0); setMessage("بدأت مطالبة الإنتاج."); void client.invalidateQueries({ queryKey: ["post-bank"] });
      void client.invalidateQueries({ queryKey: ["production", "sources"] });
      void client.invalidateQueries({ queryKey: ["production", "book-map", productionSourceId] });
    },
    onError: (error) => setMessage(`تعذر بدء الإنتاج: ${error instanceof Error ? error.message : "حدث خطأ غير معروف."} احتُفظ بمفتاح الطلب لإعادة الإرسال بأمان.`),
  });
  const retryProduction = useMutation({ mutationFn: () => productionJobsApi.resume(jobId!), onSuccess: (data) => { setJobId(data.job_id); setJobItemsPage(0); void client.invalidateQueries({ queryKey: ["production", "job", jobId] }); void client.invalidateQueries({ queryKey: ["production", "job-items", jobId] }); } });

  const items = posts.data?.items ?? [];
  const total = posts.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPageIds = items.map((post) => post.post_id);
  const allCurrentSelected = currentPageIds.length > 0 && currentPageIds.every((id) => selected.includes(id));
  const approvedSelected = useMemo(() => items.filter((p) => selected.includes(p.post_id) && p.status === "APPROVED"), [items, selected]);
  const topics = bookMap.data?.topics ?? [];
  const sourceMaterials = bookMap.data?.materials ?? topics.flatMap((topic) => topic.materials);
  const availableIdentities = (identities.data ?? []).filter((identity) => identity.active_version !== null);
  const availableProducts = (products.data ?? []).filter((product) => product.active_version !== null);
  const selectedProduct = availableProducts.find((product) => product.key === productKey);
  const activeProductVersion = selectedProduct?.versions.find((version) => version.version === selectedProduct.active_version);
  const isPostProduct = activeProductVersion ? activeProductVersion.definition.output_contract_key === "TELEGRAM_POST" : true;
  const productionSources = (sources.data ?? []).filter((source) => !isPostProduct
    ? source.material_count > 0
    : productionMode === "ALL" || productionMode === "NEEDS" && source.pending_count > 0 || productionMode === "DONE" && source.pending_count === 0 && source.material_count > 0);
  const visibleTopics = topics.filter((topic) => !isPostProduct
    ? topic.materials.length > 0
    : productionMode === "ALL" || productionMode === "NEEDS" && topic.materials.some((material) => !material.has_post) || productionMode === "DONE" && topic.materials.length > 0 && topic.materials.every((material) => material.has_post));
  const allProductionMaterials = scope === "SELECTION"
    ? sourceMaterials
    : scope === "TOPIC"
      ? visibleTopics.find((t) => t.id === productionTopicId)?.materials ?? []
      : sourceMaterials;
  const materials = allProductionMaterials.filter((material) => (!isPostProduct || productionMode === "ALL" || productionMode === "NEEDS" && !material.has_post || productionMode === "DONE" && material.has_post) && (!productionKind || material.kind === productionKind));
  const productionKinds = Array.from(new Set(allProductionMaterials.map((material) => material.kind).filter((kind): kind is string => Boolean(kind)))).sort();
  const filterTopics = filterOptions.data?.topics ?? [];

  useEffect(() => {
    // Do not clear a user's book selection while product/line filters are still loading.
    if (products.isFetching || sources.isFetching || !products.isSuccess || !sources.isSuccess) return;
    if (productionSourceId && !productionSources.some((source) => source.id === productionSourceId)) {
      setProductionSourceId("");
      setProductionTopicId("");
      setMaterialIds([]);
    }
  }, [products.isFetching, products.isSuccess, sources.isFetching, sources.isSuccess, productionMode, productionSourceId, productionSources]);

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

    <section className="rounded-2xl border bg-white p-5 shadow-sm" data-testid="production-panel">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-xl font-bold">{isPostProduct ? "إنتاج منشورات جديدة" : "إنتاج مخرجات عامة"}</h3><p className="mt-1 text-sm text-slate-500">{isPostProduct ? "اعرض الكتب أو المحاور التي ما زالت لها مواد بلا مسودات، أو راجع ما اكتمل إنتاجه." : "اختر المواد المصدرية لإنتاج مخرج مستقل عن مسار المنشورات."}</p></div></div>
      <div className="mt-4 grid gap-3 md:grid-cols-2 lg:grid-cols-4">
        {isPostProduct && <label className="text-sm font-semibold">حالة الإنتاج<select aria-label="حالة إنتاج الكتب" value={productionMode} onChange={(e) => { setProductionMode(e.target.value as typeof productionMode); setProductionKind(""); }} className="mt-2 w-full rounded-xl border p-3 font-normal"><option value="NEEDS">يحتاج إنتاجًا</option><option value="ALL">كل الكتب</option><option value="DONE">اكتمل إنتاجه</option></select></label>}
        <label className="text-sm font-semibold">الكتاب للإنتاج<select aria-label="الكتاب للإنتاج" value={productionSourceId} onChange={(e) => { setProductionSourceId(e.target.value); setProductionTopicId(""); setMaterialIds([]); setProductionKind(""); }} className="mt-2 w-full rounded-xl border p-3 font-normal"><option value="">اختر كتابًا...</option>{productionSources.map((s) => <option key={s.id} value={s.id}>{s.book_title || s.filename} — {isPostProduct ? `${s.pending_count} متبقٍ` : `${s.material_count} مادة`}</option>)}</select></label>
        <label className="text-sm font-semibold">نطاق الإنتاج<select aria-label="نطاق الإنتاج" value={scope} onChange={(e) => setScope(e.target.value as ProductionScope)} className="mt-2 w-full rounded-xl border p-3 font-normal"><option value="SOURCE">الكتاب كاملًا</option><option value="TOPIC">محور محدد</option><option value="SELECTION">مواد أحددها بنفسي</option></select></label>
        {scope === "TOPIC" && <label className="text-sm font-semibold">المحور للإنتاج<select aria-label="المحور للإنتاج" value={productionTopicId} onChange={(e) => { setProductionTopicId(e.target.value); setMaterialIds([]); }} className="mt-2 w-full rounded-xl border p-3 font-normal"><option value="">اختر محورًا...</option>{visibleTopics.map((t) => <option key={t.id} value={t.id}>{t.position}. {t.title} — {isPostProduct ? `${t.materials.filter((m) => !m.has_post).length} متبقٍ` : `${t.materials.length} مادة`}</option>)}</select></label>}
        <label className="text-sm font-semibold">المنتج<select aria-label="المنتج" value={productKey} onChange={(e) => setProductKey(e.target.value)} className="mt-2 w-full rounded-xl border p-3 font-normal"><option value="">اختر منتجًا...</option>{availableProducts.map((product) => <option key={product.key} value={product.key}>{product.name} · v{product.active_version}</option>)}</select></label>
        <label className="text-sm font-semibold">الهوية التحريرية<select aria-label="الهوية التحريرية للإنتاج" value={identityKey} onChange={(e) => setIdentityKey(e.target.value)} className="mt-2 w-full rounded-xl border p-3 font-normal"><option value="">استخدم إعدادات القالب الحالية</option>{availableIdentities.map((identity) => <option key={identity.key} value={identity.key}>{identity.name} · v{identity.active_version}</option>)}</select></label>
      </div>
      {scope === "TOPIC" && bookMap.isLoading && <p role="status" className="mt-3 text-sm text-slate-500">جارٍ تحميل محاور الكتاب...</p>}
      {scope !== "SOURCE" && bookMap.isError && <p role="alert" className="mt-3 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">تعذر تحميل محاور ومواد الكتاب. تحقق من الاتصال ثم أعد اختيار الكتاب.</p>}
      {scope === "TOPIC" && bookMap.isSuccess && visibleTopics.length === 0 && <p role="status" className="mt-3 rounded-lg border bg-amber-50 p-3 text-sm text-amber-800">{topics.length === 0 ? "لم تُكتشف محاور لهذا الكتاب بعد. يمكنك اختيار المواد المتاحة يدويًا، أو إكمال اكتشاف الكتاب أولًا." : "لا توجد محاور تطابق حالة الإنتاج الحالية. غيّر حالة الإنتاج إلى «كل الكتب» لعرض جميع المحاور."}</p>}
      {scope === "SELECTION" && <div className="mt-4"><label className="text-sm font-semibold">نوع المادة<select aria-label="نوع المادة للإنتاج" value={productionKind} onChange={(e) => setProductionKind(e.target.value)} className="mt-2 w-full rounded-xl border p-3 font-normal"><option value="">كل الأنواع المتاحة</option>{productionKinds.map((value) => <option key={value} value={value}>{value}</option>)}</select></label><div className="mt-3 max-h-64 overflow-auto rounded-xl border">{bookMap.isLoading ? <p role="status" className="p-3 text-sm text-slate-500">جارٍ تحميل مواد الكتاب...</p> : bookMap.isError ? <p role="alert" className="p-3 text-sm text-rose-700">تعذر تحميل مواد الكتاب.</p> : materials.length ? materials.map((m) => <label key={m.id} className="flex gap-3 border-b p-3"><input type="checkbox" checked={materialIds.includes(m.id)} onChange={(e) => setMaterialIds(toggleSelection(materialIds, m.id, e.target.checked))}/><span><strong>{m.title}</strong><span className="block text-xs text-slate-500">{m.kind || "بدون نوع"}{m.topic_id ? " · ضمن محور" : " · غير مصنّفة ضمن محور"}</span></span></label>) : <p className="p-3 text-sm text-slate-500">لا توجد مواد متاحة لهذا الكتاب ضمن حالة الإنتاج ونوع المادة المحددين.</p>}</div></div>}
      <div className="mt-4 flex flex-wrap items-center gap-3"><button data-testid="start-production" type="button" onClick={() => {
        try {
          if (!productionSourceId) throw new Error("اختر كتابًا أولًا.");
          if (scope === "TOPIC" && !productionTopicId) throw new Error("اختر محورًا أولًا.");
          if (scope === "SELECTION" && !materialIds.length) throw new Error("اختر مادة واحدة على الأقل.");
          const request: Omit<CreateProductionRequest, "idempotency_key"> = { source_id: productionSourceId, scope, product_key: productKey, ...(scope === "TOPIC" ? { topic_id: productionTopicId } : {}), ...(scope === "SELECTION" ? { knowledge_unit_ids: [...materialIds].sort() } : {}), ...(identityKey ? { identity_key: identityKey } : {}) };
          const claim = pendingClaimFor(JSON.stringify(request));
          createProduction.mutate({ ...request, idempotency_key: claim.key });
        } catch (error) { setMessage(error instanceof Error ? error.message : "تعذر بدء المطالبة."); }
      }} disabled={createProduction.isPending || !productionSourceId || !productKey} className="rounded-xl bg-indigo-600 px-5 py-3 font-bold text-white disabled:opacity-40">تشغيل مطالبة الإنتاج</button><button data-testid="new-production-claim" type="button" onClick={() => { clearPendingClaim(); setMessage("يمكنك الآن بدء مطالبة مستقلة جديدة؛ لن تُدمج مع المطالبة السابقة."); }} className="rounded-xl border px-4 py-3 text-sm font-semibold">بدء مطالبة جديدة</button><span className="text-sm text-slate-500">{scope === "SELECTION" ? `${materialIds.length} مادة محددة` : scope === "TOPIC" ? "إنتاج مواد المحور" : "إنتاج مواد الكتاب كاملة"}</span></div>
      {(job.data || jobId) && <div className="mt-4 space-y-4 rounded-xl border bg-slate-50 p-4" data-testid="production-job-details">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><strong>{job.data?.status ?? "QUEUED"}</strong><p className="mt-1 break-all text-xs text-slate-500">معرّف العملية: {job.data?.job_id ?? jobId}</p></div>
          <span className="text-sm">{job.data?.completed_items ?? 0} مكتمل · {job.data?.pending_items ?? 0} متبقٍ · {job.data?.failed_items ?? 0} فشل من {job.data?.total_items ?? 0}</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-slate-200" role="progressbar" aria-label="تقدم عملية الإنتاج" aria-valuemin={0} aria-valuemax={100} aria-valuenow={job.data?.progress_percent ?? 0}><div className="h-full bg-indigo-600 transition-all" style={{ width: `${job.data?.progress_percent ?? 0}%` }} /></div>
        <p className="text-xs text-slate-500">{job.data?.progress_percent ?? 0}% مكتمل · المحاولات: {job.data?.attempts ?? 0}</p>
        {job.data?.error_message && <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm"><strong>سبب التعثر: {job.data.error_code || "PRODUCTION_ERROR"}</strong><p className="mt-1 whitespace-pre-wrap">{job.data.error_message}</p><p className="mt-2 text-xs">الإجراء التالي: {job.data.next_action === "RETRY_FAILED_ITEMS" ? "إعادة محاولة العناصر الفاشلة" : "راجع تفاصيل العناصر لمعرفة السبب."}</p></div>}
        {job.data?.status === "FAILED" && job.data.next_action === "RETRY_FAILED_ITEMS" && <button type="button" onClick={() => retryProduction.mutate()} disabled={retryProduction.isPending} className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-40">إعادة تشغيل العناصر الفاشلة</button>}
        <details className="rounded-lg border bg-white p-3">
          <summary className="cursor-pointer font-semibold">سياق القالب المثبّت على هذه العملية</summary>
          {job.data?.resolved_prompt.available ? <div className="mt-3 space-y-2 text-sm"><p>المفتاح: <code>{job.data.resolved_prompt.key}</code> · الإصدار المثبّت: <strong>v{job.data.resolved_prompt.version}</strong></p>{job.data.resolved_context.available && job.data.resolved_context.prompt_template && <div className="rounded-lg bg-slate-50 p-3 text-xs"><p>نسخة السياق: v{job.data.resolved_context.schema_version} · المصدر: {job.data.resolved_context.origin === "RUNTIME_RESOLUTION" ? "تثبيت وقت إنشاء العملية" : "استعادة من تثبيت سابق"}</p>{job.data.resolved_context.recipe && <><p className="mt-1">الوصفة المثبّتة: <code>{job.data.resolved_context.recipe.key}</code> v{job.data.resolved_context.recipe.version} · المراحل: {job.data.resolved_context.recipe.stages.map((stage) => stage.key).join(" ← ")}</p>{job.data.resolved_context.recipe?.recipe_id && <p className="mt-1 break-all">معرّف الوصفة: {job.data.resolved_context.recipe?.recipe_id}</p>}{job.data.resolved_context.recipe?.version_id && <p className="mt-1 break-all">معرّف إصدار الوصفة: {job.data.resolved_context.recipe?.version_id}</p>}</>}{job.data.resolved_context.product && <p className="mt-1">المنتج المثبّت: <code>{job.data.resolved_context.product.key}</code> v{job.data.resolved_context.product.version}</p>}{job.data.resolved_context.output_contract && <p className="mt-1">عقد المخرج المثبّت: <code>{job.data.resolved_context.output_contract.key}</code> v{job.data.resolved_context.output_contract.version} · {job.data.resolved_context.output_contract.definition.artifact_kind} · {job.data.resolved_context.output_contract.definition.content_mode}</p>}{job.data.resolved_context.policy && <p className="mt-1">السياسة المثبّتة: <code>{job.data.resolved_context.policy.key}</code> v{job.data.resolved_context.policy.version}</p>}{job.data.resolved_context.identity && <p className="mt-1">الهوية المثبّتة: <code>{job.data.resolved_context.identity.key}</code> v{job.data.resolved_context.identity.version}</p>}<p className="mt-1 break-all">معرّف القالب: {job.data.resolved_context.prompt_template.template_id}</p><p className="mt-1 break-all">معرّف إصدار القالب: {job.data.resolved_context.prompt_template.version_id}</p>{job.data.resolved_context.captured_at && <p className="mt-1">وقت التثبيت: {job.data.resolved_context.captured_at}</p>}</div>}{job.data.resolved_context.invalid && <p role="alert" className="text-rose-700">سياق الإنتاج المخزّن غير صالح؛ لن يُعاد تفسيره باستخدام إعدادات منشورة أخرى.</p>}<pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-xs">{job.data.resolved_prompt.body}</pre></div> : <p className="mt-3 text-sm text-amber-700">لا يتوفر سياق قالب مثبت لهذه العملية القديمة؛ لن ننسب إليها إصدارًا بالتخمين.</p>}
        </details>
        <div className="rounded-lg border bg-white p-3">
          <div className="flex flex-wrap items-center justify-between gap-2"><strong>مواد العملية ومصدرها</strong><span className="text-xs text-slate-500">{jobItems.data?.total ?? job.data?.total_items ?? 0} مادة</span></div>
          {jobItems.isLoading ? <p role="status" className="mt-3 text-sm text-slate-500">تحميل تفاصيل المواد...</p> : jobItems.isError ? <p role="alert" className="mt-3 text-sm text-rose-700">تعذر تحميل تفاصيل المواد.</p> : <div className="mt-2 divide-y">{(jobItems.data?.items ?? []).map((item) => <article key={item.item_id} className="py-3 text-sm">
            <div className="flex flex-wrap items-start justify-between gap-2"><strong>{item.position}. {item.title}</strong><span className={item.status === "FAILED" ? "rounded bg-rose-100 px-2 py-1 text-xs text-rose-700" : "rounded bg-slate-100 px-2 py-1 text-xs"}>{item.status}</span></div>
            <p className="mt-1 text-xs text-slate-500">{item.source_title} · المادة {item.knowledge_unit_id}{item.source_reference ? ` · ${item.source_reference}` : ""}{item.page_start ? ` · ص ${item.page_start}${item.page_end && item.page_end !== item.page_start ? `–${item.page_end}` : ""}` : ""}</p>
            {item.artifact_id && <p className="mt-1 break-all text-xs text-indigo-700">معرّف المخرج (Artifact): {item.artifact_id}</p>}{item.post_id && <p className="mt-1 break-all text-xs text-emerald-700">معرّف المنشور التحريري: {item.post_id}</p>}
            {item.error_message && <p className="mt-1 whitespace-pre-wrap text-xs text-rose-700">{item.error_code || "PRODUCTION_ERROR"}: {item.error_message}</p>}
          </article>)}</div>}
          {(jobItems.data?.total ?? 0) > 20 && <div className="mt-3 flex items-center justify-between"><button type="button" onClick={() => setJobItemsPage((value) => Math.max(0, value - 1))} disabled={jobItemsPage === 0} className="rounded-lg border px-3 py-1 text-xs disabled:opacity-40">السابق</button><span className="text-xs text-slate-500">صفحة {jobItemsPage + 1} من {Math.ceil((jobItems.data?.total ?? 0) / 20)}</span><button type="button" onClick={() => setJobItemsPage((value) => Math.min(Math.ceil((jobItems.data?.total ?? 0) / 20) - 1, value + 1))} disabled={jobItemsPage >= Math.ceil((jobItems.data?.total ?? 0) / 20) - 1} className="rounded-lg border px-3 py-1 text-xs disabled:opacity-40">التالي</button></div>}
        </div>
      </div>}
    </section>
    {message && <div role="status" className="rounded-xl border bg-indigo-50 p-4 text-sm">{message}</div>}
    {!hasLoaded ? <div className="rounded-2xl border border-dashed bg-white p-10 text-center"><h3 className="text-lg font-bold">بنك المنشورات جاهز</h3><p className="mt-2 text-sm text-slate-500">اختر كتابًا أو كل الكتب، ثم اضغط «عرض النتائج» لبدء التصفح.</p></div> : posts.isLoading && !posts.data ? <div role="status" className="rounded-2xl border bg-white p-10 text-center">جاري تحميل الصفحة الأولى فقط...</div> : posts.isError ? <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-5">تعذر تحميل المنشورات: {posts.error.message}</div> : <section className="space-y-3" aria-label="نتائج بنك المنشورات"><div className="rounded-2xl border bg-white p-4 shadow-sm"><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-bold">النتائج</h3><p className="text-sm text-slate-500">{total ? `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, total)} من ${total}` : "لا توجد نتائج"}</p></div><div className="flex flex-wrap gap-2"><button type="button" onClick={() => toggleCurrentPage(!allCurrentSelected)} disabled={!items.length} className="rounded-xl border px-3 py-2 text-sm font-semibold">{allCurrentSelected ? "إلغاء تحديد الصفحة" : "تحديد الصفحة"}</button><span className="rounded-xl bg-slate-100 px-3 py-2 text-sm font-semibold">{selected.length} محدد</span><button type="button" onClick={() => setSelected([])} disabled={!selected.length} className="rounded-xl border px-3 py-2 text-sm disabled:opacity-40">مسح التحديد</button></div></div><div className="mt-3 flex flex-wrap gap-2"><button type="button" onClick={() => bulkApprove.mutate()} disabled={!selected.length || bulkApprove.isPending} className="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-40">اعتماد المحدد</button>{approvedSelected.length > 0 && <button data-testid="go-publishing" type="button" onClick={() => navigate(`/publishing?selected_post_ids=${approvedSelected.map((p) => p.post_id).join(",")}`)} className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-bold">الانتقال إلى النشر ({approvedSelected.length})</button>}</div></div>{!items.length ? <div className="rounded-2xl border border-dashed bg-white p-10 text-center"><h3 className="font-bold">لا توجد نتائج مطابقة</h3><p className="mt-2 text-sm text-slate-500">جرّب تغيير الكتاب أو الحالة أو النوع أو البحث.</p></div> : items.map((post) => { const checked = selected.includes(post.post_id); return <article key={post.post_id} className="rounded-2xl border bg-white p-5 shadow-sm"><div className="flex items-start gap-3"><input aria-label={`تحديد ${post.title}`} type="checkbox" checked={checked} onChange={(e) => setSelected(toggleSelection(selected, post.post_id, e.target.checked))} className="mt-1 h-4 w-4"/><button type="button" onClick={() => { setEditing(post.post_id); setContent(post.content); setReviewNote(post.review_note ?? ""); }} className="min-w-0 flex-1 text-right"><strong className="block">{post.title}</strong><span className="mt-1 block text-xs text-slate-500">{post.source_title} · {post.topic_title || "دون محور"} · {post.status}</span><p className="mt-2 text-sm leading-7 text-slate-600">{post.content_preview}</p></button></div></article>; })}<div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border bg-white p-4"><button type="button" onClick={() => setPage((value) => Math.max(0, value - 1))} disabled={page === 0 || posts.isFetching} className="rounded-xl border px-4 py-2 disabled:opacity-40">السابق</button><span className="text-sm font-semibold">صفحة {page + 1} من {pageCount}</span><button type="button" onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))} disabled={page >= pageCount - 1 || posts.isFetching} className="rounded-xl border px-4 py-2 disabled:opacity-40">التالي</button></div></section>}

    {editing && <div className="fixed inset-0 z-20 grid place-items-center bg-slate-950/30 p-4"><div role="dialog" className="max-h-[calc(100dvh-2rem)] w-full max-w-3xl overflow-y-auto rounded-2xl bg-white p-6 shadow-xl"><h3 className="text-xl font-bold">مراجعة المنشور</h3><textarea aria-label="محتوى المنشور" value={content} onChange={(e) => setContent(e.target.value)} className="mt-4 min-h-48 w-full rounded-xl border p-4"/><input aria-label="ملاحظة المراجعة" value={reviewNote} onChange={(e) => setReviewNote(e.target.value)} placeholder="ملاحظة أو سبب الرفض" className="mt-3 w-full rounded-xl border p-3"/><div className="mt-5 flex flex-wrap gap-2"><button type="button" onClick={() => save.mutate()} disabled={save.isPending} className="rounded-xl border px-4 py-2 font-semibold">حفظ</button><button type="button" onClick={() => review.mutate({ id: editing, action: "approve" })} disabled={review.isPending} className="rounded-xl bg-emerald-600 px-4 py-2 font-semibold text-white">اعتماد</button><button type="button" onClick={() => review.mutate({ id: editing, action: "reject" })} disabled={review.isPending || !reviewNote.trim()} className="rounded-xl bg-rose-600 px-4 py-2 font-semibold text-white">رفض</button><button type="button" onClick={() => setEditing(null)} className="rounded-xl bg-slate-100 px-4 py-2 font-semibold">إغلاق</button></div></div></div>}
    <GenericArtifactReviewPanel />
  </section>;
}
