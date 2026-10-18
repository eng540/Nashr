import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { postsApi } from "../../shared/api/postsApi";
import { productionJobsApi, type ProductionLineFilter, type ProductionScope, type ProductionProductOption, type EditorialIdentityOption, type ProductionRecipeOption } from "../../shared/api/productionJobsApi";
import { GenericArtifactReviewPanel } from "../artifacts/GenericArtifactReviewPanel";
import { toggleSelection } from "../../shared/utils/selection";

const PAGE_SIZE = 30;
const ALL_SOURCES = "ALL";
const PENDING_CLAIM_STORAGE_KEY = "nashr.pending-production-claim.v1";
type PendingClaim = { key: string; payload: string };
type CreateProductionRequest = { source_id?: string; scope: ProductionScope; production_mode?: "PRODUCT" | "PRODUCT_WITH_INSTRUCTIONS" | "CUSTOM"; input_text?: string; input_title?: string; topic_id?: string; knowledge_unit_ids?: string[]; thematic_theme?: string; recipe_key?: string; custom_instructions?: string; identity_key?: string; product_key?: string; idempotency_key: string };

function productionLineFilter(products: ProductionProductOption[] | undefined, identities: EditorialIdentityOption[] | undefined, recipes: ProductionRecipeOption[] | undefined, productKey: string, identityKey: string): ProductionLineFilter {
  const product = products?.find((item) => item.key === productKey);
  const productVersion = product?.versions.find((version) => version.version === product.active_version);
  const recipeKey = productVersion?.definition.recipe_key;
  const recipe = recipes?.find((item) => item.key === recipeKey);
  const pinnedIdentity = productVersion?.definition.component_versions?.identity;
  const identity = identities?.find((item) => item.key === (pinnedIdentity?.key ?? identityKey));
  return {
    product_key: product?.key,
    product_version: product?.active_version ?? undefined,
    identity_key: pinnedIdentity?.key ?? identity?.key,
    identity_version: pinnedIdentity?.version ?? identity?.active_version ?? undefined,
    recipe_key: recipeKey,
    recipe_version: productVersion?.definition.component_versions?.recipe.version ?? recipe?.active_version ?? undefined,
  };
}

function pendingRequestFromStorage(): Partial<CreateProductionRequest> | null {
  try {
    const stored = window.localStorage.getItem(PENDING_CLAIM_STORAGE_KEY);
    if (!stored) return null;
    const claim = JSON.parse(stored) as PendingClaim;
    if (!claim.key || !claim.payload) return null;
    const request = JSON.parse(claim.payload) as Partial<CreateProductionRequest>;
    return (request.source_id || request.input_text) && request.scope ? request : null;
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

function productionJobStatusLabel(status: string): string {
  return ({ QUEUED: "في انتظار بدء التنفيذ", RUNNING: "قيد التنفيذ", COMPLETED: "اكتملت المهمة", FAILED: "تعذرت المهمة" } as Record<string, string>)[status] ?? "حالة غير معروفة";
}

function productionItemStatusLabel(status: string): string {
  return ({ PENDING: "بانتظار التنفيذ", RUNNING: "قيد التنفيذ", COMPLETED: "مكتمل", FAILED: "تعثر" } as Record<string, string>)[status] ?? "حالة غير معروفة";
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

const TELEGRAM_HTML_TAGS = new Set(["b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "code", "pre", "a", "blockquote", "span", "br"]);

function isTelegramMarkupValid(content: string): boolean {
  const tagPattern = /<\/?([a-zA-Z][\w-]*)([^>]*)>/g;
  const tags = Array.from(content.matchAll(tagPattern));
  const hasRichTag = tags.some((match) => TELEGRAM_HTML_TAGS.has(match[1].toLowerCase()));
  if (!hasRichTag) return true;
  const stack: string[] = [];
  for (const match of tags) {
    const tag = match[1].toLowerCase();
    const closing = match[0].startsWith("</");
    const selfClosing = /\/>$/.test(match[0]) || tag === "br";
    if (!TELEGRAM_HTML_TAGS.has(tag)) return false;
    if (closing) {
      if (stack.pop() !== tag) return false;
    } else if (!selfClosing) {
      stack.push(tag);
    }
  }
  return stack.length === 0;
}

function renderTelegramNode(node: Node, key: string): ReactNode {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent;
  if (!(node instanceof HTMLElement)) return null;
  const tag = node.tagName.toLowerCase();
  const children = Array.from(node.childNodes).map((child, index) => renderTelegramNode(child, `${key}-${index}`));
  switch (tag) {
    case "b": case "strong": return <strong key={key}>{children}</strong>;
    case "i": case "em": return <em key={key}>{children}</em>;
    case "u": case "ins": return <u key={key}>{children}</u>;
    case "s": case "strike": case "del": return <del key={key}>{children}</del>;
    case "code": return <code key={key} className="rounded bg-slate-100 px-1">{children}</code>;
    case "pre": return <pre key={key} className="overflow-x-auto rounded-lg bg-slate-100 p-3 text-left" dir="ltr">{children}</pre>;
    case "blockquote": return <blockquote key={key} className="my-2 border-r-4 border-slate-300 pr-3 text-slate-600">{children}</blockquote>;
    case "br": return <br key={key} />;
    case "span": return node.classList.contains("tg-spoiler") ? <span key={key} className="rounded bg-slate-800 text-slate-800 hover:text-white">{children}</span> : <span key={key}>{children}</span>;
    case "a": {
      const href = node.getAttribute("href") ?? "";
      if (!/^(https?:\/\/|tg:\/\/)/i.test(href)) return <span key={key}>{children}</span>;
      return <a key={key} href={href} target="_blank" rel="noreferrer" className="text-indigo-700 underline">{children}</a>;
    }
    default: return <span key={key}>{children}</span>;
  }
}

export function TelegramPreview({ content, onClose }: { content: string; onClose?: () => void }) {
  const valid = isTelegramMarkupValid(content);
  const nodes = useMemo(() => {
    if (!valid) return null;
    const doc = new DOMParser().parseFromString(content, "text/html");
    const hasRichTag = Array.from(doc.body.querySelectorAll("*")).some((element) => TELEGRAM_HTML_TAGS.has(element.tagName.toLowerCase()));
    if (!hasRichTag) return content;
    return Array.from(doc.body.childNodes).map((node, index) => renderTelegramNode(node, `telegram-preview-${index}`));
  }, [content, valid]);
  return <section className="mt-4 rounded-xl border bg-slate-50 p-4" aria-label="معاينة تيليجرام">
    <div className="mb-2 flex items-center justify-between gap-2"><h4 className="text-sm font-bold">معاينة تيليجرام</h4>{onClose ? <button type="button" onClick={onClose} className="rounded-lg border bg-white px-3 py-1 text-sm">إغلاق المعاينة</button> : <span className="text-xs text-slate-500">عرض تقني للتنسيق قبل الاعتماد</span>}</div>
    {!valid
      ? <p role="alert" className="text-sm text-rose-700">وسوم HTML غير متوازنة أو غير مدعومة. لن يقبل محول تيليجرام هذا التنسيق.</p>
      : <div dir="auto" className="whitespace-pre-wrap break-words rounded-lg bg-white p-4 text-sm leading-7 text-slate-800">{nodes}</div>}
  </section>;
}


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
  const [thematicTheme, setThematicTheme] = useState(() => pendingRequestFromStorage()?.thematic_theme ?? "");
  const [customInstructions, setCustomInstructions] = useState(() => pendingRequestFromStorage()?.custom_instructions ?? "");
  const [productionModeChoice, setProductionModeChoice] = useState<"PRODUCT" | "PRODUCT_WITH_INSTRUCTIONS" | "CUSTOM">(() => pendingRequestFromStorage()?.production_mode ?? "PRODUCT");
  const [directInputText, setDirectInputText] = useState(() => pendingRequestFromStorage()?.input_text ?? "");
  const [directInputTitle, setDirectInputTitle] = useState(() => pendingRequestFromStorage()?.input_title ?? "");
  const [customInputMode, setCustomInputMode] = useState<"TEXT" | "LIBRARY">("TEXT");
  const [customRecipeKey, setCustomRecipeKey] = useState(() => pendingRequestFromStorage()?.recipe_key ?? "");
  const [productInputMode, setProductInputMode] = useState<"LIBRARY" | "TEXT">(() => pendingRequestFromStorage()?.input_text ? "TEXT" : "LIBRARY");
  const [productionKind, setProductionKind] = useState("");
  const [productionMaterialQuery, setProductionMaterialQuery] = useState("");
  const [productionMaterialPage, setProductionMaterialPage] = useState(0);
  const [scope, setScope] = useState<ProductionScope>(() => pendingRequestFromStorage()?.scope ?? "SOURCE");
  const [productionTopicId, setProductionTopicId] = useState(() => pendingRequestFromStorage()?.topic_id ?? "");
  const [materialIds, setMaterialIds] = useState<string[]>(() => pendingRequestFromStorage()?.knowledge_unit_ids ?? []);
  const [jobId, setJobId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [productionStep, setProductionStep] = useState<1 | 2 | 3>(1);
  const [workspaceView, setWorkspaceView] = useState<"production" | "job" | "review">(() => searchParams.get("status") ? "review" : "production");

  const identities = useQuery({ queryKey: ["control-plane", "identities"], queryFn: productionJobsApi.identities });
  const products = useQuery({ queryKey: ["control-plane", "products"], queryFn: productionJobsApi.products });
  const recipes = useQuery({ queryKey: ["control-plane", "recipes"], queryFn: productionJobsApi.recipes });
  const resolvedLineFilter = productionLineFilter(products.data, identities.data, recipes.data, productKey, identityKey);
  const lineFilter = productionModeChoice === "CUSTOM" ? undefined : resolvedLineFilter;
  const queryProduct = products.data?.find((product) => product.key === productKey);
  const queryProductVersion = queryProduct?.versions.find((version) => version.version === queryProduct.active_version);
  const queryRecipe = recipes.data?.find((recipe) => recipe.key === queryProductVersion?.definition.recipe_key);
  const queryRecipeVersion = queryRecipe?.versions.find((version) => version.version === queryProductVersion?.definition.component_versions?.recipe.version);
  const isThematicProduct = Boolean(queryRecipeVersion?.stages.some((stage) => stage.capability_key === "compose_thematic_artifact"));
  const sources = useQuery({
    queryKey: ["production", "sources", resolvedLineFilter.product_key, resolvedLineFilter.product_version, resolvedLineFilter.identity_key, resolvedLineFilter.identity_version, resolvedLineFilter.recipe_key, resolvedLineFilter.recipe_version],
    queryFn: () => productionJobsApi.sources(lineFilter),
  });
  const thematicSourceList = (sources.data ?? []).filter((source) => source.material_count > 0);
  const thematicBookMaps = useQueries({
    queries: isThematicProduct ? thematicSourceList.map((source) => ({
      queryKey: ["production", "thematic-book-map", source.id, resolvedLineFilter.product_key, resolvedLineFilter.product_version, resolvedLineFilter.recipe_key, resolvedLineFilter.recipe_version],
      queryFn: () => productionJobsApi.bookMap(source.id, lineFilter),
    })) : [],
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
  const bookMap = useQuery({ queryKey: ["production", "book-map", productionSourceId, resolvedLineFilter.product_key, resolvedLineFilter.product_version, resolvedLineFilter.identity_key, resolvedLineFilter.identity_version, resolvedLineFilter.recipe_key, resolvedLineFilter.recipe_version], queryFn: () => productionJobsApi.bookMap(productionSourceId, lineFilter), enabled: Boolean(productionSourceId) });
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
  useEffect(() => { if (isThematicProduct && scope !== "SELECTION") { setScope("SELECTION"); setProductionTopicId(""); setMaterialIds([]); } }, [isThematicProduct, scope]);

  useEffect(() => {
    if (!products.data) return;
    const available = products.data.filter((product) => {
      if (product.active_version === null) return false;
      const version = product.versions.find((item) => item.version === product.active_version);
      return Boolean(version?.definition.component_versions);
    });
    if (!available.some((product) => product.key === productKey)) setProductKey(available[0]?.key ?? "");
  }, [products.data, productKey]);
  useEffect(() => {
    if (!products.data) return;
    const product = products.data.find((item) => item.key === productKey);
    const version = product?.versions.find((item) => item.version === product.active_version);
    const pinnedIdentityKey = version?.definition.component_versions?.identity.key;
    if (pinnedIdentityKey && identityKey !== pinnedIdentityKey) setIdentityKey(pinnedIdentityKey);
  }, [products.data, productKey, identityKey]);

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
      setJobId(data.job_id); setJobItemsPage(0); setWorkspaceView("job"); setMessage("بدأت مطالبة الإنتاج."); void client.invalidateQueries({ queryKey: ["post-bank"] });
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
  const thematicMaterials = thematicBookMaps.flatMap((result, index) => {
    const source = thematicSourceList[index];
    if (!source || !result.data) return [];
    const bookMaterials = result.data.materials ?? result.data.topics.flatMap((topic) => topic.materials);
    return bookMaterials.map((material) => ({ ...material, source_id: source.id, source_title: source.book_title || source.filename }));
  });
  const availableIdentities = (identities.data ?? []).filter((identity) => identity.active_version !== null);
  const availableProducts = (products.data ?? []).filter((product) => {
    if (product.active_version === null) return false;
    const version = product.versions.find((item) => item.version === product.active_version);
    return Boolean(version?.definition.component_versions);
  });
  const selectedProduct = availableProducts.find((product) => product.key === productKey);
  const activeProductVersion = selectedProduct?.versions.find((version) => version.version === selectedProduct.active_version);
  const pinnedIdentity = activeProductVersion?.definition.component_versions?.identity;
  const isPostProduct = activeProductVersion ? activeProductVersion.definition.output_contract_key === "TELEGRAM_POST" : true;
  const productionSources = (sources.data ?? []).filter((source) => productionModeChoice === "CUSTOM" ? source.material_count > 0 : !isPostProduct
    ? source.material_count > 0
    : productionMode === "ALL" || productionMode === "NEEDS" && source.pending_count > 0 || productionMode === "DONE" && source.pending_count === 0 && source.material_count > 0);
  const visibleTopics = topics.filter((topic) => !isPostProduct
    ? topic.materials.length > 0
    : productionMode === "ALL" || productionMode === "NEEDS" && topic.materials.some((material) => !material.has_post) || productionMode === "DONE" && topic.materials.length > 0 && topic.materials.every((material) => material.has_post));
  const allProductionMaterials = isThematicProduct ? thematicMaterials : scope === "SELECTION"
    ? sourceMaterials
    : scope === "TOPIC"
      ? visibleTopics.find((t) => t.id === productionTopicId)?.materials ?? []
      : sourceMaterials;
  const materials = allProductionMaterials.filter((material) => (!isPostProduct || productionMode === "ALL" || productionMode === "NEEDS" && !material.has_post || productionMode === "DONE" && material.has_post) && (!productionKind || material.kind === productionKind) && (!productionMaterialQuery.trim() || material.title.toLocaleLowerCase().includes(productionMaterialQuery.trim().toLocaleLowerCase())));
  const materialPageCount = Math.max(1, Math.ceil(materials.length / 20));
  const materialPageItems = materials.slice(productionMaterialPage * 20, (productionMaterialPage + 1) * 20);
  const currentMaterialPageIds = materialPageItems.map((material) => material.id);
  const allCurrentMaterialPageSelected = currentMaterialPageIds.length > 0 && currentMaterialPageIds.every((id) => materialIds.includes(id));
  const selectedTopic = topics.find((topic) => topic.id === productionTopicId);
  const scopeMaterialCount = isThematicProduct ? materialIds.filter((id) => thematicMaterials.some((material) => material.id === id)).length : scope === "SOURCE" ? sourceMaterials.length : scope === "TOPIC" ? (selectedTopic?.materials.length ?? 0) : materialIds.filter((id) => sourceMaterials.some((material) => material.id === id)).length;
  const productionKinds = Array.from(new Set(allProductionMaterials.map((material) => material.kind).filter((kind): kind is string => Boolean(kind)))).sort();
  const selectedSource = productionSources.find((source) => source.id === productionSourceId);
  const selectedThematicMaterials = materialIds.map((id) => thematicMaterials.find((material) => material.id === id)).filter((material): material is (typeof thematicMaterials)[number] => Boolean(material));
  const thematicAnchorSourceId = selectedThematicMaterials[0]?.source_id;
  const thematicAnchorSource = productionSources.find((source) => source.id === thematicAnchorSourceId);
  const productReady = products.isSuccess && availableProducts.some((product) => product.key === productKey);
  const identityReady = identities.isSuccess && Boolean(pinnedIdentity && identityKey === pinnedIdentity.key && identities.data?.some((identity) => identity.key === pinnedIdentity.key));
  const selectedRecipeKey = activeProductVersion?.definition.recipe_key;
  const recipeReady = recipes.isSuccess && Boolean(selectedRecipeKey && recipes.data.some((recipe) => recipe.key === selectedRecipeKey && recipe.active_version !== null));
  const lineReady = productReady && identityReady && recipeReady;
  const sourceReady = productInputMode === "TEXT" && !isThematicProduct
    ? Boolean(directInputText.trim())
    : isThematicProduct
      ? Boolean(thematicAnchorSourceId && sources.isSuccess && thematicBookMaps.length > 0 && thematicBookMaps.every((result) => result.isSuccess))
      : Boolean(selectedSource && sources.isSuccess);
  const topicReady = scope === "TOPIC" && bookMap.isSuccess && Boolean(selectedTopic && topics.some((topic) => topic.id === productionTopicId) && selectedTopic.materials.length > 0);
  const selectedMaterialIds = materialIds.filter((id) => allProductionMaterials.some((material) => material.id === id));
  const scopeReady = productInputMode === "TEXT" && !isThematicProduct
    ? Boolean(sourceReady)
    : isThematicProduct
      ? Boolean(sourceReady && thematicTheme.trim() && selectedMaterialIds.length >= 2 && selectedMaterialIds.length === materialIds.length)
      : Boolean(sourceReady && bookMap.isSuccess && scopeMaterialCount > 0
        && (scope !== "TOPIC" || topicReady)
        && (scope !== "SELECTION" || selectedMaterialIds.length > 0 && selectedMaterialIds.length === materialIds.length));
  const canReviewProduction = Boolean(lineReady && scopeReady && !products.isFetching && !identities.isFetching && !recipes.isFetching && !sources.isFetching && !bookMap.isFetching && !thematicBookMaps.some((result) => result.isFetching));

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
  const toggleMaterialPageSelection = (checked: boolean) => setMaterialIds((current) => checked ? Array.from(new Set([...current, ...currentMaterialPageIds])) : current.filter((id) => !currentMaterialPageIds.includes(id)));

  return <section data-testid="post-bank-workspace" className="space-y-6">
    <header className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-sm font-semibold text-indigo-600">Workspace 02</p><h2 className="mt-1 text-3xl font-bold">مصنع المنشورات</h2><p className="mt-2 max-w-2xl text-sm leading-7 text-slate-600">حوّل المواد إلى منشورات، ثم راجعها واعتمدها قبل نقلها إلى مساحة النشر.</p></div><Link to="/publishing" className="rounded-xl border px-4 py-2 text-sm font-semibold">مساحة النشر</Link></header>

    <nav aria-label="أقسام مصنع المحتوى" className="grid gap-2 rounded-2xl border bg-white p-2 sm:grid-cols-3">
      <button type="button" onClick={() => setWorkspaceView("production")} aria-current={workspaceView === "production" ? "page" : undefined} className={`rounded-xl px-4 py-3 text-right text-sm font-bold ${workspaceView === "production" ? "bg-indigo-600 text-white" : "hover:bg-slate-50"}`}><span className="block">إعداد الإنتاج</span><span className={`mt-1 block text-xs font-normal ${workspaceView === "production" ? "text-indigo-100" : "text-slate-500"}`}>اختر المنتج والمصدر والنطاق</span></button>
      <button type="button" onClick={() => setWorkspaceView("job")} aria-current={workspaceView === "job" ? "page" : undefined} className={`rounded-xl px-4 py-3 text-right text-sm font-bold ${workspaceView === "job" ? "bg-indigo-600 text-white" : "hover:bg-slate-50"}`}><span className="block">متابعة المهمة</span><span className={`mt-1 block text-xs font-normal ${workspaceView === "job" ? "text-indigo-100" : "text-slate-500"}`}>{job.data ? `الحالة: ${job.data.status}` : "تفاصيل العملية الحالية"}</span></button>
      <button type="button" onClick={() => setWorkspaceView("review")} aria-current={workspaceView === "review" ? "page" : undefined} className={`rounded-xl px-4 py-3 text-right text-sm font-bold ${workspaceView === "review" ? "bg-indigo-600 text-white" : "hover:bg-slate-50"}`}><span className="block">بنك المحتوى والمراجعة</span><span className={`mt-1 block text-xs font-normal ${workspaceView === "review" ? "text-indigo-100" : "text-slate-500"}`}>تحرير المنشورات واعتماد المخرجات</span></button>
    </nav>

    {workspaceView === "review" && <section className="rounded-2xl border bg-white p-5 shadow-sm" data-testid="post-bank-filters">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-xl font-bold">ابدأ من بنك المنشورات</h3><p className="mt-1 text-sm text-slate-500">اختر نطاق العمل أولًا؛ لن يتم تحميل القائمة كاملة تلقائيًا.</p></div>{hasLoaded && <button type="button" onClick={loadBank} className="rounded-xl border px-4 py-2 text-sm font-semibold">تحديث النتائج</button>}</div>
      <div className="mt-4 grid gap-3 md:grid-cols-2 lg:grid-cols-4">
        <label className="text-sm font-semibold">الكتاب<select aria-label="كتاب بنك المنشورات" value={filterSourceId} onChange={(e) => { setFilterSourceId(e.target.value); setTopicId(""); }} className="mt-2 w-full rounded-xl border p-3 font-normal"><option value={ALL_SOURCES}>كل الكتب</option>{(sources.data ?? []).map((source) => <option key={source.id} value={source.id}>{source.book_title || source.filename}</option>)}</select></label>
        <label className="text-sm font-semibold">الحالة<select aria-label="حالة المنشور" value={status} onChange={(e) => { setStatus(e.target.value); setSearchParams(e.target.value ? { status: e.target.value } : {}); }} className="mt-2 w-full rounded-xl border p-3 font-normal"><option value="">كل الحالات</option><option value="DRAFT">مسودة</option><option value="APPROVED">معتمد</option><option value="REJECTED">مرفوض</option></select></label>
        <label className="text-sm font-semibold">النوع<select aria-label="نوع المادة" value={kind} onChange={(e) => setKind(e.target.value)} className="mt-2 w-full rounded-xl border p-3 font-normal"><option value="">كل الأنواع</option>{(filterOptions.data?.kinds ?? []).map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label className="text-sm font-semibold">المحور<select aria-label="محور المادة" value={topicId} disabled={filterSourceId === ALL_SOURCES} onChange={(e) => setTopicId(e.target.value)} className="mt-2 w-full rounded-xl border p-3 font-normal disabled:bg-slate-100"><option value="">كل المحاور</option>{filterTopics.map((topic) => <option key={topic.id} value={topic.id}>{topic.position}. {topic.title}</option>)}</select></label>
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-[1fr_220px_auto]"><label className="text-sm font-semibold"><span className="sr-only">بحث المنشورات</span><input aria-label="بحث المنشورات" value={queryInput} onChange={(e) => setQueryInput(e.target.value)} placeholder="ابحث في العنوان أو النص..." className="w-full rounded-xl border p-3 font-normal" /></label><label className="text-sm font-semibold">الفرز<select aria-label="فرز المنشورات" value={sort} onChange={(e) => setSort(e.target.value as SortMode)} className="mt-2 w-full rounded-xl border p-3 font-normal"><option value="created">الأحدث أولًا</option><option value="title">العنوان: أ - ي</option><option value="kind">النوع</option><option value="topic">المحور</option></select></label><div className="flex items-end gap-2"><button type="button" onClick={clearFilters} className="rounded-xl border px-4 py-3 text-sm font-semibold">مسح الفلاتر</button><button data-testid="load-post-bank" type="button" onClick={loadBank} className="rounded-xl bg-indigo-600 px-5 py-3 text-sm font-bold text-white">عرض النتائج</button></div></div>
      {filterSourceId === ALL_SOURCES && <p className="mt-3 text-xs text-slate-500">فلتر المحور يتاح بعد اختيار كتاب محدد، بينما النوع والبحث يعملان على كل الكتب.</p>}
    </section>}

    {workspaceView !== "review" && <section className="rounded-2xl border bg-white p-5 shadow-sm" data-testid="production-panel">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-xl font-bold">{workspaceView === "job" ? "متابعة عملية الإنتاج" : isPostProduct ? "إنتاج منشورات جديدة" : "إنتاج مخرجات عامة"}</h3><p className="mt-1 text-sm text-slate-500">{workspaceView === "job" ? "تابع تقدم المهمة والعناصر المكتملة والمتعثرة، وافتح التشخيص المتقدم عند الحاجة." : isPostProduct ? "ابدأ إعدادًا جديدًا من المنتج والمصدر، ثم راجع النطاق قبل التشغيل." : "اختر المنتج والمصدر لإنتاج مخرج مستقل عن مسار المنشورات."}</p></div></div>
      {workspaceView === "production" && <div className="grid gap-3 rounded-2xl border bg-white p-4 sm:grid-cols-3" aria-label="وضع الإنتاج">
        <button type="button" aria-pressed={productionModeChoice === "PRODUCT"} onClick={() => setProductionModeChoice("PRODUCT")} className={`rounded-xl border p-3 text-right ${productionModeChoice === "PRODUCT" ? "border-indigo-600 bg-indigo-50" : ""}`}><strong className="block">منتج</strong><span className="mt-1 block text-xs text-slate-500">استخدم إعدادات المنتج كما هي</span></button>
        <button type="button" aria-pressed={productionModeChoice === "PRODUCT_WITH_INSTRUCTIONS"} onClick={() => setProductionModeChoice("PRODUCT_WITH_INSTRUCTIONS")} className={`rounded-xl border p-3 text-right ${productionModeChoice === "PRODUCT_WITH_INSTRUCTIONS" ? "border-indigo-600 bg-indigo-50" : ""}`}><strong className="block">منتج مع تعليمات إضافية</strong><span className="mt-1 block text-xs text-slate-500">خصّص هذه المهمة دون تعديل المنتج</span></button>
        <button type="button" aria-pressed={productionModeChoice === "CUSTOM"} onClick={() => setProductionModeChoice("CUSTOM")} className={`rounded-xl border p-3 text-right ${productionModeChoice === "CUSTOM" ? "border-indigo-600 bg-indigo-50" : ""}`}><strong className="block">توجيه مخصص — دون منتج</strong><span className="mt-1 block text-xs text-slate-500">ابدأ من نص مباشر باستخدام مسار النص المتاح</span></button>
      </div>}
      {workspaceView === "production" && productionModeChoice === "CUSTOM" && <section className="space-y-4 rounded-2xl border bg-white p-5" data-testid="custom-production-form"><h3 className="text-lg font-bold">مهمة مخصصة دون منتج</h3><p className="text-sm leading-6 text-slate-600">اختر وصفة نصية متوافقة، ثم نصًا مباشرًا أو مواد من المكتبة. تُحفظ النتيجة ضمن دورة المهام والمراجعة الحالية.</p><label className="block text-sm font-semibold">مسار الإنتاج النصي<select value={customRecipeKey} onChange={(e) => setCustomRecipeKey(e.target.value)} disabled={!recipes.isSuccess || recipes.isFetching} className="mt-2 w-full rounded-xl border p-3 font-normal"><option value="">اختر مسارًا...</option>{(recipes.data ?? []).filter((recipe) => recipe.active_version !== null && recipe.versions.some((version) => version.version === recipe.active_version && version.stages.length > 0 && version.stages.every((stage) => stage.capability_key === "produce_post"))).map((recipe) => <option key={recipe.key} value={recipe.key}>{recipe.name} · {recipe.key}</option>)}</select><span className="mt-1 block text-xs font-normal text-slate-500">تظهر هنا الوصفات المنشورة التي تنتج منشورات نصية فقط. المخرجات الأخرى تتطلب منتجًا يثبت عقدها.</span></label><div className="flex flex-wrap gap-2"><button type="button" aria-pressed={customInputMode === "TEXT"} onClick={() => setCustomInputMode("TEXT")} className={`rounded-lg border px-4 py-2 text-sm ${customInputMode === "TEXT" ? "border-indigo-600 bg-indigo-50" : ""}`}>لصق نص مباشر</button><button type="button" aria-pressed={customInputMode === "LIBRARY"} onClick={() => { setCustomInputMode("LIBRARY"); setScope("SELECTION"); }} className={`rounded-lg border px-4 py-2 text-sm ${customInputMode === "LIBRARY" ? "border-indigo-600 bg-indigo-50" : ""}`}>اختيار مواد المكتبة</button></div>{customInputMode === "TEXT" ? <><label className="block text-sm font-semibold">عنوان النص (اختياري)<input value={directInputTitle} onChange={(e) => setDirectInputTitle(e.target.value)} maxLength={500} className="mt-2 w-full rounded-xl border p-3 font-normal" placeholder="عنوان مختصر للمادة" /></label><label className="block text-sm font-semibold">النص المدخل<textarea value={directInputText} onChange={(e) => setDirectInputText(e.target.value)} maxLength={100000} rows={7} className="mt-2 w-full rounded-xl border p-3 font-normal leading-7" placeholder="ألصق النص الذي تريد العمل عليه..." /></label></> : <><label className="block text-sm font-semibold">مصدر المكتبة<select value={productionSourceId} onChange={(e) => { setProductionSourceId(e.target.value); setScope("SELECTION"); setProductionTopicId(""); setMaterialIds([]); }} className="mt-2 w-full rounded-xl border p-3 font-normal"><option value="">اختر كتابًا أو مصدرًا...</option>{productionSources.map((source) => <option key={source.id} value={source.id}>{source.book_title || source.filename} · {source.material_count} مادة</option>)}</select></label><div className="max-h-80 overflow-y-auto rounded-xl border">{bookMap.isFetching ? <p className="p-4 text-sm text-slate-500">جارٍ تحميل المواد...</p> : sourceMaterials.map((material) => <label key={material.id} className="flex gap-3 border-b p-3 last:border-b-0"><input type="checkbox" checked={materialIds.includes(material.id)} onChange={(e) => { setMaterialIds((current) => e.target.checked ? [...current.filter((id) => id !== material.id), material.id] : current.filter((id) => id !== material.id)); }} className="mt-1" /><span className="text-sm"><strong>{material.title}</strong><span className="mt-1 block text-xs text-slate-500">{material.content.slice(0,180)}</span></span></label>)}</div><p className="text-xs text-slate-500">{selectedMaterialIds.length} مادة محددة</p></>}<label className="block text-sm font-semibold">التوجيه المخصص<textarea value={customInstructions} onChange={(e) => setCustomInstructions(e.target.value)} maxLength={12000} rows={4} className="mt-2 w-full rounded-xl border p-3 font-normal leading-7" placeholder="ما المهمة التي تريد تنفيذها؟" /></label><button type="button" data-testid="start-custom-production" disabled={createProduction.isPending || !customRecipeKey || !recipes.isSuccess || !customInstructions.trim() || (customInputMode === "TEXT" ? !directInputText.trim() : !productionSourceId || selectedMaterialIds.length === 0)} onClick={() => { try { const request: Omit<CreateProductionRequest, "idempotency_key"> = customInputMode === "TEXT" ? { scope: "SELECTION", production_mode: "CUSTOM", recipe_key: customRecipeKey, input_text: directInputText.trim(), ...(directInputTitle.trim() ? { input_title: directInputTitle.trim() } : {}), custom_instructions: customInstructions.trim() } : { source_id: productionSourceId, scope: "SELECTION", knowledge_unit_ids: [...selectedMaterialIds], production_mode: "CUSTOM", recipe_key: customRecipeKey, custom_instructions: customInstructions.trim() }; const claim = pendingClaimFor(JSON.stringify(request)); createProduction.mutate({ ...request, idempotency_key: claim.key }); } catch (error) { setMessage(error instanceof Error ? error.message : "تعذر بدء المهمة المخصصة."); } }} className="rounded-xl bg-indigo-600 px-5 py-3 font-bold text-white disabled:opacity-40">بدء المهمة المخصصة</button></section>}
      {workspaceView === "production" && productionModeChoice !== "CUSTOM" && <>
      <nav aria-label="خطوات إعداد الإنتاج" className="mt-4 grid grid-cols-3 gap-2 rounded-xl bg-slate-50 p-2">
        {([{ step: 1, title: "المنتج والهوية التحريرية" }, { step: 2, title: "المصدر والنطاق" }, { step: 3, title: "مراجعة إعداد الإنتاج" }] as const).map(({ step, title }) => {
          const stepReady = step === 1 ? lineReady : step === 2 ? lineReady && sourceReady && !sources.isFetching : canReviewProduction;
          const stepReachable = step <= productionStep || step === productionStep + 1 && stepReady;
          return <button key={step} type="button" onClick={() => { if (stepReachable && (step !== 3 || canReviewProduction)) setProductionStep(step); }} disabled={!stepReachable || step === 3 && !canReviewProduction} aria-current={productionStep === step ? "step" : undefined} className={`rounded-lg px-2 py-3 text-sm font-semibold transition ${productionStep === step ? "bg-indigo-600 text-white shadow-sm" : productionStep > step ? "bg-emerald-50 text-emerald-800" : "text-slate-500"} disabled:cursor-not-allowed disabled:opacity-50`}><span className="ml-1 inline-flex h-6 w-6 items-center justify-center rounded-full border text-xs">{step}</span>{title}</button>;
        })}
      </nav>
      <p className="mt-3 text-sm text-slate-600">{productionStep === 1 ? "اختر منتجًا منشورًا يثبت تعليماته وهويته التحريرية. لا يمكن تجاوز هوية المنتج من تشغيل عابر." : productionStep === 2 ? "اختر الكتاب ونطاق الإنتاج، ثم أكمل اختيار المحور أو المواد هنا قبل مراجعة الإعدادات." : "راجع إعداد الإنتاج النهائي. يعكس الملخص الطلب الذي سترسله الواجهة إلى API؛ يمكنك الرجوع لتعديل المصدر أو النطاق قبل البدء."}</p>
      <div className="mt-4 grid gap-3 md:grid-cols-2 lg:grid-cols-4">
        {productionStep === 2 && !isThematicProduct && <div className="mb-4 flex flex-wrap gap-2"><button type="button" aria-pressed={productInputMode === "LIBRARY"} onClick={() => setProductInputMode("LIBRARY")} className={`rounded-lg border px-4 py-2 text-sm ${productInputMode === "LIBRARY" ? "border-indigo-600 bg-indigo-50" : ""}`}>اختيار من المكتبة</button><button type="button" aria-pressed={productInputMode === "TEXT"} onClick={() => { setProductInputMode("TEXT"); setScope("SELECTION"); setProductionSourceId(""); setProductionTopicId(""); setMaterialIds([]); }} className={`rounded-lg border px-4 py-2 text-sm ${productInputMode === "TEXT" ? "border-indigo-600 bg-indigo-50" : ""}`}>لصق نص مباشر</button></div>}{productionStep === 2 && productInputMode === "TEXT" && !isThematicProduct && <div className="mb-4 space-y-3 rounded-xl border bg-white p-4"><label className="block text-sm font-semibold">عنوان النص (اختياري)<input value={directInputTitle} onChange={(e) => setDirectInputTitle(e.target.value)} maxLength={500} className="mt-2 w-full rounded-xl border p-3 font-normal" placeholder="عنوان مختصر للمادة" /></label><label className="block text-sm font-semibold">النص المدخل<textarea value={directInputText} onChange={(e) => setDirectInputText(e.target.value)} maxLength={100000} rows={7} className="mt-2 w-full rounded-xl border p-3 font-normal leading-7" placeholder="ألصق النص الذي تريد العمل عليه..." /></label></div>}{productionStep === 2 && productInputMode === "LIBRARY" && isPostProduct && <label className="text-sm font-semibold">حالة الإنتاج<select aria-label="حالة إنتاج الكتب" value={productionMode} onChange={(e) => { setProductionMode(e.target.value as typeof productionMode); setProductionKind(""); setProductionTopicId(""); setMaterialIds([]); setProductionMaterialQuery(""); setProductionMaterialPage(0); }} className="mt-2 w-full rounded-xl border p-3 font-normal"><option value="NEEDS">يحتاج إنتاجًا</option><option value="ALL">كل الكتب</option><option value="DONE">اكتمل إنتاجه</option></select></label>}
        {productionStep === 2 && productInputMode === "LIBRARY" && !isThematicProduct && <label className="text-sm font-semibold">الكتاب للإنتاج<select aria-label="الكتاب للإنتاج" value={productionSourceId} onChange={(e) => { setProductionSourceId(e.target.value); setProductionTopicId(""); setMaterialIds([]); setProductionKind(""); setProductionMaterialQuery(""); setProductionMaterialPage(0); }} disabled={!sources.isSuccess || sources.isFetching} className="mt-2 w-full rounded-xl border p-3 font-normal disabled:bg-slate-100"><option value="">اختر كتابًا...</option>{productionSources.map((source) => <option key={source.id} value={source.id}>{source.book_title || source.filename} — {isPostProduct ? `${source.pending_count} متبقٍ` : `${source.material_count} مادة`}</option>)}</select></label>}
        {productionStep === 2 && productInputMode === "LIBRARY" && <label className="text-sm font-semibold">نطاق الإنتاج<select aria-label="نطاق الإنتاج" value={scope} onChange={(e) => { setScope(e.target.value as ProductionScope); setProductionTopicId(""); setMaterialIds([]); setProductionKind(""); setProductionMaterialQuery(""); setProductionMaterialPage(0); }} disabled={!sourceReady || !bookMap.isSuccess || bookMap.isFetching} className="mt-2 w-full rounded-xl border p-3 font-normal disabled:bg-slate-100">{isThematicProduct ? <option value="SELECTION">تركيب موضوعي من مواد متعددة الكتب</option> : <><option value="SOURCE">الكتاب كاملًا</option><option value="TOPIC">محور محدد</option><option value="SELECTION">مواد أحددها بنفسي</option></>}</select></label>}
        {productionStep === 2 && productInputMode === "LIBRARY" && isThematicProduct && <label className="text-sm font-semibold md:col-span-2">الثيمة الموضوعية<input aria-label="الثيمة الموضوعية" value={thematicTheme} onChange={(e) => setThematicTheme(e.target.value)} maxLength={500} placeholder="مثال: معنى الصبر والحلم في التراث العربي" className="mt-2 w-full rounded-xl border p-3 font-normal" /><span className="mt-1 block text-xs font-normal text-slate-500">اختر مادتين على الأقل من كتابين أو أكثر. سينتج الطلب مخرجًا نصيًا واحدًا مع حفظ إحالات جميع المصادر.</span></label>}
        {productionStep === 2 && productInputMode === "LIBRARY" && scope === "TOPIC" && <label className="text-sm font-semibold">المحور للإنتاج<select aria-label="المحور للإنتاج" value={productionTopicId} onChange={(e) => { setProductionTopicId(e.target.value); setMaterialIds([]); setProductionMaterialQuery(""); setProductionMaterialPage(0); }} disabled={!bookMap.isSuccess || bookMap.isFetching} className="mt-2 w-full rounded-xl border p-3 font-normal disabled:bg-slate-100"><option value="">اختر محورًا...</option>{visibleTopics.map((topic) => <option key={topic.id} value={topic.id}>{topic.position}. {topic.title} — {isPostProduct ? `${topic.materials.filter((material) => !material.has_post).length} متبقٍ` : `${topic.materials.length} مادة`}</option>)}</select></label>}
        {productionStep === 1 && <label className="text-sm font-semibold">المنتج<select aria-label="المنتج" value={productKey} onChange={(e) => { setProductKey(e.target.value); setProductInputMode("LIBRARY"); setProductionSourceId(""); setProductionTopicId(""); setMaterialIds([]); setThematicTheme(""); }} disabled={!products.isSuccess || products.isFetching} className="mt-2 w-full rounded-xl border p-3 font-normal disabled:bg-slate-100"><option value="">اختر منتجًا...</option>{availableProducts.map((product) => <option key={product.key} value={product.key}>{product.name} · v{product.active_version}</option>)}</select></label>}
        {productionStep === 1 && <label className="text-sm font-semibold">الهوية التحريرية المحددة بالمنتج<select aria-label="الهوية التحريرية للإنتاج" value={pinnedIdentity?.key ?? ""} disabled={!identities.isSuccess || identities.isFetching || Boolean(pinnedIdentity)} className="mt-2 w-full rounded-xl border p-3 font-normal disabled:bg-slate-100"><option value="">{pinnedIdentity ? "تعذر قراءة الهوية المثبتة" : "اختر منتجًا يحدد هويته التحريرية"}</option>{pinnedIdentity && <option value={pinnedIdentity.key}>{identities.data?.find((identity) => identity.key === pinnedIdentity.key)?.name ?? pinnedIdentity.key} · v{pinnedIdentity.version} (مثبتة في المنتج)</option>}{!pinnedIdentity && availableIdentities.map((identity) => <option key={identity.key} value={identity.key}>{identity.name} · v{identity.active_version}</option>)}</select></label>}
      </div>
      {productionStep === 1 && (products.isLoading || identities.isLoading || recipes.isLoading) && <p role="status" className="mt-3 text-sm text-slate-500">جارٍ تحميل المنتجات والهويات والوصفات والتحقق من توافقها...</p>}
      {productionStep === 1 && (products.isError || identities.isError || recipes.isError) && <div role="alert" className="mt-3 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">تعذر تحميل خيارات المنتج أو الهوية أو الوصفة. أعد المحاولة قبل المتابعة.<div className="mt-2 flex flex-wrap gap-2">{products.isError && <button type="button" onClick={() => void products.refetch()} className="rounded-lg border bg-white px-3 py-1.5">إعادة تحميل المنتجات</button>}{identities.isError && <button type="button" onClick={() => void identities.refetch()} className="rounded-lg border bg-white px-3 py-1.5">إعادة تحميل الهويات</button>}{recipes.isError && <button type="button" onClick={() => void recipes.refetch()} className="rounded-lg border bg-white px-3 py-1.5">إعادة تحميل الوصفات</button>}</div></div>}
      {productionStep === 1 && products.isSuccess && availableProducts.length === 0 && <p role="status" className="mt-3 rounded-lg border bg-amber-50 p-3 text-sm text-amber-800">لا توجد منتجات ذات إصدار منشور وبيان مكونات ثابت متاح للإنتاج. حدّث تعريف المنتج من Control Plane ثم انشر إصدارًا جديدًا.</p>}
      {productionStep === 1 && identities.isSuccess && identityKey && !identityReady && <p role="alert" className="mt-3 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">الهوية المختارة لم تعد متاحة أو نشطة. اختر هوية أخرى أو استخدم إعدادات القالب الحالية.</p>}
      {productionStep === 2 && productInputMode === "LIBRARY" && sources.isLoading && <p role="status" className="mt-3 text-sm text-slate-500">جارٍ تحميل الكتب المتاحة لهذا المنتج والهوية...</p>}
      {productionStep === 2 && productInputMode === "LIBRARY" && sources.isError && <div role="alert" className="mt-3 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">تعذر تحميل الكتب المتاحة. تحقق من الاتصال ثم أعد المحاولة.<button type="button" onClick={() => void sources.refetch()} className="mr-2 rounded-lg border bg-white px-3 py-1.5">إعادة تحميل الكتب</button></div>}
      {productionStep === 2 && productInputMode === "LIBRARY" && sources.isSuccess && productionSources.length === 0 && <p role="status" className="mt-3 rounded-lg border bg-amber-50 p-3 text-sm text-amber-800">لا توجد كتب بمواد متاحة لهذا المنتج وحالة الإنتاج المحددة.</p>}
      {productionStep === 2 && productInputMode === "LIBRARY" && (isThematicProduct ? thematicBookMaps.some((result) => result.isLoading) : productionSourceId && bookMap.isLoading) && <p role="status" className="mt-3 text-sm text-slate-500">{isThematicProduct ? "جارٍ تحميل مواد الكتب المتاحة للتركيب الموضوعي..." : "جارٍ تحميل محاور ومواد الكتاب..."}</p>}
      {productionStep === 2 && productInputMode === "LIBRARY" && (isThematicProduct ? thematicBookMaps.some((result) => result.isError) : productionSourceId && bookMap.isError) && <div role="alert" className="mt-3 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{isThematicProduct ? "تعذر تحميل مواد أحد الكتب؛ لن يبدأ التركيب قبل اكتمال تحميل جميع المصادر." : "تعذر تحميل محاور ومواد الكتاب. تحقق من الاتصال ثم أعد المحاولة."}<button type="button" onClick={() => { if (isThematicProduct) void Promise.all(thematicBookMaps.map((result) => result.refetch())); else void bookMap.refetch(); }} className="mr-2 rounded-lg border bg-white px-3 py-1.5">إعادة تحميل المواد</button></div>}
      {productionStep === 2 && productInputMode === "LIBRARY" && scope === "SOURCE" && bookMap.isSuccess && scopeMaterialCount === 0 && <p role="status" className="mt-3 rounded-lg border bg-amber-50 p-3 text-sm text-amber-800">لا توجد مواد ضمن هذا النطاق؛ اختر مصدرًا أو نطاقًا آخر قبل المتابعة.</p>}
      {productionStep === 2 && productInputMode === "LIBRARY" && scope === "TOPIC" && bookMap.isSuccess && visibleTopics.length === 0 && <p role="status" className="mt-3 rounded-lg border bg-amber-50 p-3 text-sm text-amber-800">{topics.length === 0 ? "لم تُكتشف محاور لهذا الكتاب بعد. يمكنك اختيار المواد المتاحة يدويًا، أو إكمال اكتشاف الكتاب أولًا." : "لا توجد محاور تطابق حالة الإنتاج الحالية. غيّر حالة الإنتاج إلى «كل الكتب» لعرض جميع المحاور."}</p>}
      {productionStep === 2 && productInputMode === "LIBRARY" && scope === "TOPIC" && bookMap.isSuccess && visibleTopics.length > 0 && !topicReady && <p role="status" className="mt-3 text-sm text-amber-800">اختر محورًا صالحًا من هذا الكتاب قبل الانتقال إلى مراجعة إعداد الإنتاج.</p>}
      {productionStep === 2 && productInputMode === "LIBRARY" && scope === "SELECTION" && <div className="mt-4 space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm font-semibold">نوع المادة
            <select aria-label="نوع المادة للإنتاج" value={productionKind} onChange={(e) => { setProductionKind(e.target.value); setProductionMaterialPage(0); }} className="mt-2 w-full rounded-xl border p-3 font-normal">
              <option value="">كل الأنواع المتاحة</option>{productionKinds.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
          <label className="text-sm font-semibold">البحث في المواد
            <input aria-label="بحث مواد الإنتاج" value={productionMaterialQuery} onChange={(e) => { setProductionMaterialQuery(e.target.value); setProductionMaterialPage(0); }} placeholder="ابحث بعنوان المادة..." className="mt-2 w-full rounded-xl border p-3 font-normal" />
          </label>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-slate-50 p-3">
          <span className="text-sm font-semibold">{selectedMaterialIds.length} مادة محددة{selectedMaterialIds.some((id) => !materials.some((material) => material.id === id)) ? " · توجد اختيارات محفوظة خارج الفلتر الحالي" : ""}</span>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => toggleMaterialPageSelection(!allCurrentMaterialPageSelected)} disabled={!materialPageItems.length || bookMap.isFetching || thematicBookMaps.some((result) => result.isFetching)} className="rounded-lg border bg-white px-3 py-2 text-sm font-semibold disabled:opacity-40">{allCurrentMaterialPageSelected ? "إلغاء تحديد الصفحة" : "تحديد الصفحة"}</button>
            <button type="button" onClick={() => setMaterialIds([])} disabled={!materialIds.length} className="rounded-lg border bg-white px-3 py-2 text-sm disabled:opacity-40">مسح التحديد</button>
          </div>
        </div>
        <div className="max-h-80 overflow-auto rounded-xl border">
          {(isThematicProduct ? thematicBookMaps.some((result) => result.isLoading) : bookMap.isLoading) ? <p role="status" className="p-3 text-sm text-slate-500">جارٍ تحميل المواد...</p> : (isThematicProduct ? thematicBookMaps.some((result) => result.isError) : bookMap.isError) ? <p role="alert" className="p-3 text-sm text-rose-700">تعذر تحميل المواد.</p> : materialPageItems.length ? materialPageItems.map((material) => <label key={material.id} className="flex gap-3 border-b p-3">
            <input type="checkbox" checked={materialIds.includes(material.id)} onChange={(e) => setMaterialIds(toggleSelection(materialIds, material.id, e.target.checked))}/>
            <span><strong>{material.title}</strong><span className="block text-xs text-slate-500">{("source_title" in material ? material.source_title + " · " : "")}{material.kind || "بدون نوع"}{material.topic_id ? " · ضمن محور" : " · غير مصنّفة ضمن محور"}</span></span>
          </label>) : <p className="p-3 text-sm text-slate-500">{materials.length ? "لا توجد مواد في هذه الصفحة." : "لا توجد مواد تطابق البحث والفلاتر الحالية."}</p>}
        </div>
        {materials.length > 20 && <nav aria-label="صفحات مواد الإنتاج" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-3">
          <button type="button" onClick={() => setProductionMaterialPage((page) => Math.max(0, page - 1))} disabled={productionMaterialPage === 0 || bookMap.isFetching || thematicBookMaps.some((result) => result.isFetching)} className="rounded-lg border px-3 py-2 text-sm disabled:opacity-40">السابق</button>
          <span className="text-sm font-semibold">صفحة {productionMaterialPage + 1} من {materialPageCount} · {materials.length} مادة مطابقة</span>
          <button type="button" onClick={() => setProductionMaterialPage((page) => Math.min(materialPageCount - 1, page + 1))} disabled={productionMaterialPage >= materialPageCount - 1 || bookMap.isFetching || thematicBookMaps.some((result) => result.isFetching)} className="rounded-lg border px-3 py-2 text-sm disabled:opacity-40">التالي</button>
        </nav>}
      </div>}
      {productionStep < 3 && <div className="mt-4 flex flex-wrap items-center gap-3"><button type="button" onClick={() => setProductionStep((step) => step === 1 ? 2 : 3)} disabled={productionStep === 1 ? !lineReady || products.isFetching || identities.isFetching || recipes.isFetching : !canReviewProduction} className="rounded-xl bg-indigo-600 px-5 py-3 font-bold text-white disabled:opacity-40">{productionStep === 1 ? "متابعة إلى اختيار المصدر" : "متابعة إلى مراجعة إعداد الإنتاج"}</button>{productionStep === 2 && productInputMode === "LIBRARY" && <button type="button" onClick={() => setProductionStep(1)} className="rounded-xl border px-4 py-3 text-sm font-semibold">رجوع إلى المنتج والهوية</button>}</div>}
      {productionStep === 3 && productionModeChoice === "PRODUCT_WITH_INSTRUCTIONS" && <label className="mb-4 block rounded-xl border bg-white p-4 text-sm font-semibold">تعليمات إضافية لهذه المهمة (اختياري)<textarea data-testid="custom-production-instructions" aria-label="تعليمات إضافية لهذه المهمة" value={customInstructions} onChange={(e) => setCustomInstructions(e.target.value)} maxLength={12000} rows={4} placeholder="خصّص زاوية المعالجة أو طول النص أو ما ينبغي التركيز عليه، دون تغيير نوع المخرج الذي يحدده المنتج." className="mt-2 w-full rounded-lg border p-3 font-normal leading-6" /><span className="mt-1 block text-xs font-normal text-slate-500">تخص هذه المهمة فقط، وتُمرر إلى التنفيذ مع الحفاظ على متطلبات المنتج.</span></label>}
      {productionStep === 3 && <div className="mb-4 rounded-xl border border-indigo-100 bg-indigo-50/60 p-4" data-testid="production-summary"><h4 className="font-bold">مراجعة إعداد الإنتاج</h4>{productionModeChoice === "PRODUCT_WITH_INSTRUCTIONS" && customInstructions.trim() && <p className="mt-2 whitespace-pre-wrap text-sm leading-6"><strong>تعليمات هذه المهمة:</strong> {customInstructions.trim()}</p>}<dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2"><div><dt className="text-slate-500">المنتج</dt><dd className="mt-1 font-semibold">{selectedProduct?.name ?? productKey}</dd></div><div><dt className="text-slate-500">الهوية التحريرية</dt><dd className="mt-1 font-semibold">{identityKey ? availableIdentities.find((identity) => identity.key === identityKey)?.name ?? identityKey : "إعدادات القالب الحالية"}</dd></div><div><dt className="text-slate-500">الكتاب</dt><dd className="mt-1 font-semibold">{productInputMode === "TEXT" && !isThematicProduct ? (directInputTitle.trim() || "نص مباشر") : (isThematicProduct ? thematicAnchorSource : selectedSource)?.book_title || (isThematicProduct ? thematicAnchorSource : selectedSource)?.filename || (isThematicProduct ? "يُحدد من أول مادة مختارة" : "—")}</dd></div><div><dt className="text-slate-500">النطاق</dt><dd className="mt-1 font-semibold">{productInputMode === "TEXT" && !isThematicProduct ? "نص مباشر" : scope === "SOURCE" ? "الكتاب كاملًا" : scope === "TOPIC" ? `محور: ${selectedTopic?.title ?? "غير محدد"}` : "مواد محددة"}</dd></div><div><dt className="text-slate-500">المواد الداخلة في الطلب</dt><dd className="mt-1 font-semibold">{productInputMode === "TEXT" && !isThematicProduct ? "نص مباشر واحد" : isThematicProduct ? `${selectedMaterialIds.length} مادة من ${new Set(selectedThematicMaterials.map((material) => material.source_id)).size} كتاب` : !bookMap.isSuccess ? "لم يكتمل تحميل العدد" : scopeMaterialCount}</dd></div>{scope === "SELECTION" && <div><dt className="text-slate-500">معرّفات المواد المحددة</dt><dd className="mt-1 break-all font-mono text-xs">{selectedMaterialIds.join(", ")}</dd></div>}</dl><p className="mt-3 text-xs leading-6 text-slate-600">{scope === "SOURCE" ? "سيشمل الطلب جميع المواد المرتبطة بهذا الكتاب وفق نطاق المصدر في الخادم، وليس المواد الظاهرة فقط بعد مرشحات الواجهة." : scope === "TOPIC" ? "سيشمل الطلب المواد المرتبطة بالمحور المختار من هذا الكتاب." : "سيشمل الطلب المواد المحددة صراحةً فقط، بمعرّفاتها المعروضة أعلاه."} لن يبدأ أي إنتاج حتى تضغط زر البدء أدناه.</p><button type="button" onClick={() => setProductionStep(2)} className="mt-3 rounded-lg border bg-white px-3 py-2 text-sm font-semibold">تعديل المصدر والنطاق</button></div>}
      {productionStep === 3 && <div className="mt-4 flex flex-wrap items-center gap-3"><button data-testid="start-production" type="button" onClick={() => {
        try {
          if (!canReviewProduction || !selectedProduct) throw new Error("تحقق من المنتج والهوية والمصدر والنطاق قبل البدء.");
          if (scope === "TOPIC" && !topicReady) throw new Error("اختر محورًا صالحًا أولًا.");
          if (productInputMode !== "TEXT" && scope === "SELECTION" && selectedMaterialIds.length === 0) throw new Error("اختر مادة واحدة على الأقل.");
          if (isThematicProduct && !thematicTheme.trim()) throw new Error("اكتب الثيمة الموضوعية أولًا.");
          if (isThematicProduct && selectedMaterialIds.length < 2) throw new Error("اختر مادتين على الأقل للتركيب الموضوعي.");
          const request: Omit<CreateProductionRequest, "idempotency_key"> = productInputMode === "TEXT" && !isThematicProduct ? { scope: "SELECTION", production_mode: productionModeChoice, product_key: productKey, input_text: directInputText.trim(), ...(directInputTitle.trim() ? { input_title: directInputTitle.trim() } : {}), ...(productionModeChoice === "PRODUCT_WITH_INSTRUCTIONS" && customInstructions.trim() ? { custom_instructions: customInstructions.trim() } : {}), ...(identityKey ? { identity_key: identityKey } : {}) } : { source_id: isThematicProduct ? (thematicAnchorSourceId ?? "") : productionSourceId, scope, production_mode: productionModeChoice, product_key: productKey, ...(scope === "TOPIC" ? { topic_id: productionTopicId } : {}), ...(scope === "SELECTION" ? { knowledge_unit_ids: isThematicProduct ? [...selectedMaterialIds] : [...selectedMaterialIds].sort() } : {}), ...(isThematicProduct ? { thematic_theme: thematicTheme.trim() } : {}), ...(productionModeChoice === "PRODUCT_WITH_INSTRUCTIONS" && customInstructions.trim() ? { custom_instructions: customInstructions.trim() } : {}), ...(identityKey ? { identity_key: identityKey } : {}) };
          const claim = pendingClaimFor(JSON.stringify(request));
          createProduction.mutate({ ...request, idempotency_key: claim.key });
        } catch (error) { setMessage(error instanceof Error ? error.message : "تعذر بدء المطالبة."); }
      }} disabled={createProduction.isPending || !canReviewProduction || !selectedProduct} className="rounded-xl bg-indigo-600 px-5 py-3 font-bold text-white disabled:opacity-40">بدء الإنتاج</button><button data-testid="new-production-claim" type="button" onClick={() => { clearPendingClaim(); setMessage("يمكنك الآن بدء مطالبة مستقلة جديدة؛ لن تُدمج مع المطالبة السابقة."); }} className="rounded-xl border px-4 py-3 text-sm font-semibold">بدء مطالبة جديدة</button><span className="text-sm text-slate-500">{scope === "SELECTION" ? `${selectedMaterialIds.length} مادة محددة` : scope === "TOPIC" ? "إنتاج مواد المحور" : "إنتاج مواد الكتاب كاملة"}</span></div>}
      </>}
      {workspaceView === "job" && (job.data || jobId) && <div className="mt-4 space-y-4 rounded-xl border bg-slate-50 p-4" data-testid="production-job-details">
        {job.data?.request_details && <section className="rounded-xl border bg-white p-4" data-testid="production-request-details"><h4 className="font-bold">بيانات طلب الإنتاج</h4><p className="mt-2 text-sm text-slate-600">وضع الإنتاج: {job.data.request_details.production_mode === "CUSTOM" ? "توجيه مخصص دون منتج" : job.data.request_details.production_mode === "PRODUCT_WITH_INSTRUCTIONS" ? "منتج مع تعليمات إضافية" : job.data.request_details.production_mode === "PRODUCT" ? "منتج" : "طلب سابق"}</p>{job.data.request_details.product_key && <p className="mt-1 text-sm text-slate-600">المنتج: {job.data.request_details.product_key}</p>}{job.data.request_details.materials.length > 0 && <div className="mt-3"><strong className="text-sm">المواد المستخدمة ({job.data.request_details.materials.length})</strong><ul className="mt-1 list-inside list-disc space-y-1 text-sm text-slate-600">{job.data.request_details.materials.map((material) => <li key={material.id}>{material.title}</li>)}</ul></div>}{job.data.request_details.custom_instructions && <div className="mt-3"><strong className="text-sm">التعليمات المستخدمة</strong><p className="mt-1 whitespace-pre-wrap text-sm leading-6">{job.data.request_details.custom_instructions}</p></div>}{job.data.request_details.input_title && <p className="mt-2 text-sm">عنوان المدخل: {job.data.request_details.input_title}</p>}{job.data.request_details.input_text_preview && <div className="mt-2"><strong className="text-sm">معاينة النص المدخل</strong><p className="mt-1 whitespace-pre-wrap text-sm leading-6">{job.data.request_details.input_text_preview}</p></div>}</section>}
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><strong>{productionJobStatusLabel(job.data?.status ?? "QUEUED")}</strong><p className="mt-1 text-xs text-slate-500">الحالة التقنية: <code>{job.data?.status ?? "QUEUED"}</code></p><p className="mt-1 break-all text-xs text-slate-500">مرجع العملية: {job.data?.job_id ?? jobId}</p></div>
          <span className="text-sm">{job.data?.completed_items ?? 0} مكتمل · {job.data?.pending_items ?? 0} متبقٍ · {job.data?.failed_items ?? 0} فشل من {job.data?.total_items ?? 0}</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-slate-200" role="progressbar" aria-label="تقدم عملية الإنتاج" aria-valuemin={0} aria-valuemax={100} aria-valuenow={job.data?.progress_percent ?? 0}><div className="h-full bg-indigo-600 transition-all" style={{ width: `${job.data?.progress_percent ?? 0}%` }} /></div>
        <p className="text-xs text-slate-500">{job.data?.progress_percent ?? 0}% مكتمل · المحاولات: {job.data?.attempts ?? 0}</p>
        {Boolean(job.data?.reconciliation_required_items) && <div role="alert" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><strong>نتيجة المزوّد غير محسومة</strong><p className="mt-1">هناك {job.data?.reconciliation_required_items} عنصرًا يحتاج إلى تحقق قبل إعادة المحاولة. أوقف النظام إعادة المحاولة العادية لتجنب إنتاج أو تكلفة مكررة.</p></div>}
        {job.data?.error_message && <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm"><strong>سبب التعثر: {job.data.error_code || "PRODUCTION_ERROR"}</strong><p className="mt-1 whitespace-pre-wrap">{job.data.error_message}</p><p className="mt-2 text-xs">الإجراء التالي: {job.data.next_action === "RETRY_FAILED_ITEMS" ? "إعادة محاولة العناصر الفاشلة" : "راجع تفاصيل العناصر لمعرفة السبب."}</p></div>}
        {job.data?.status === "FAILED" && job.data.next_action === "RETRY_FAILED_ITEMS" && <button type="button" onClick={() => retryProduction.mutate()} disabled={retryProduction.isPending} className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-40">إعادة تشغيل العناصر الفاشلة</button>}
        <details className="rounded-lg border bg-white p-3">
          <summary className="cursor-pointer font-semibold">سياق القالب المثبّت على هذه العملية</summary>
          {job.data?.resolved_prompt.available ? <div className="mt-3 space-y-2 text-sm"><p>المفتاح: <code>{job.data.resolved_prompt.key}</code> · الإصدار المثبّت: <strong>v{job.data.resolved_prompt.version}</strong></p>{job.data.resolved_context.available && job.data.resolved_context.prompt_template && <div className="rounded-lg bg-slate-50 p-3 text-xs"><p>نسخة السياق: v{job.data.resolved_context.schema_version} · المصدر: {job.data.resolved_context.origin === "RUNTIME_RESOLUTION" ? "تثبيت وقت إنشاء العملية" : "استعادة من تثبيت سابق"}</p>{job.data.resolved_context.recipe && <><p className="mt-1">الوصفة المثبّتة: <code>{job.data.resolved_context.recipe.key}</code> v{job.data.resolved_context.recipe.version} · المراحل: {job.data.resolved_context.recipe.stages.map((stage) => stage.key).join(" ← ")}</p>{job.data.resolved_context.recipe?.recipe_id && <p className="mt-1 break-all">معرّف الوصفة: {job.data.resolved_context.recipe?.recipe_id}</p>}{job.data.resolved_context.recipe?.version_id && <p className="mt-1 break-all">معرّف إصدار الوصفة: {job.data.resolved_context.recipe?.version_id}</p>}</>}{job.data.resolved_context.product && <p className="mt-1">المنتج المثبّت: <code>{job.data.resolved_context.product.key}</code> v{job.data.resolved_context.product.version}</p>}{job.data.resolved_context.output_contract && <p className="mt-1">عقد المخرج المثبّت: <code>{job.data.resolved_context.output_contract.key}</code> v{job.data.resolved_context.output_contract.version} · {job.data.resolved_context.output_contract.definition.artifact_kind} · {job.data.resolved_context.output_contract.definition.content_mode}</p>}{job.data.resolved_context.policy && <p className="mt-1">السياسة المثبّتة: <code>{job.data.resolved_context.policy.key}</code> v{job.data.resolved_context.policy.version}</p>}{job.data.resolved_context.identity && <p className="mt-1">الهوية المثبّتة: <code>{job.data.resolved_context.identity.key}</code> v{job.data.resolved_context.identity.version}</p>}<p className="mt-1 break-all">معرّف القالب: {job.data.resolved_context.prompt_template.template_id}</p><p className="mt-1 break-all">معرّف إصدار القالب: {job.data.resolved_context.prompt_template.version_id}</p>{job.data.resolved_context.captured_at && <p className="mt-1">وقت التثبيت: {job.data.resolved_context.captured_at}</p>}</div>}{job.data.resolved_context.invalid && <p role="alert" className="text-rose-700">سياق الإنتاج المخزّن غير صالح؛ لن يُعاد تفسيره باستخدام إعدادات منشورة أخرى.</p>}<pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-xs">{job.data.resolved_prompt.body}</pre></div> : <p className="mt-3 text-sm text-amber-700">لا يتوفر سياق قالب مثبت لهذه العملية القديمة؛ لن ننسب إليها إصدارًا بالتخمين.</p>}
        </details>
        <div className="rounded-lg border bg-white p-3">
          <div className="flex flex-wrap items-center justify-between gap-2"><strong>مواد العملية ومصدرها</strong><span className="text-xs text-slate-500">{jobItems.data?.total ?? job.data?.total_items ?? 0} مادة</span></div>
          {jobItems.isLoading ? <p role="status" className="mt-3 text-sm text-slate-500">تحميل تفاصيل المواد...</p> : jobItems.isError ? <p role="alert" className="mt-3 text-sm text-rose-700">تعذر تحميل تفاصيل المواد.</p> : <div className="mt-2 divide-y">{(jobItems.data?.items ?? []).map((item) => <article key={item.item_id} className="py-3 text-sm">
            <div className="flex flex-wrap items-start justify-between gap-2"><strong>{item.position}. {item.title}</strong><span className={item.status === "FAILED" ? "rounded bg-rose-100 px-2 py-1 text-xs text-rose-700" : "rounded bg-slate-100 px-2 py-1 text-xs"}>{productionItemStatusLabel(item.status)}</span></div>
            <p className="mt-1 text-xs text-slate-500">{item.source_title} · المادة {item.knowledge_unit_id}{item.source_reference ? ` · ${item.source_reference}` : ""}{item.page_start ? ` · ص ${item.page_start}${item.page_end && item.page_end !== item.page_start ? `–${item.page_end}` : ""}` : ""}</p>
            {item.artifact_id && <p className="mt-1 break-all text-xs text-indigo-700">معرّف المخرج (Artifact): {item.artifact_id}</p>}{item.post_id && <p className="mt-1 break-all text-xs text-emerald-700">معرّف المنشور التحريري: {item.post_id}</p>}
            {item.error_message && <p className="mt-1 whitespace-pre-wrap text-xs text-rose-700">{item.error_code || "PRODUCTION_ERROR"}: {item.error_message}</p>}
          </article>)}</div>}
          {(jobItems.data?.total ?? 0) > 20 && <div className="mt-3 flex items-center justify-between"><button type="button" onClick={() => setJobItemsPage((value) => Math.max(0, value - 1))} disabled={jobItemsPage === 0} className="rounded-lg border px-3 py-1 text-xs disabled:opacity-40">السابق</button><span className="text-xs text-slate-500">صفحة {jobItemsPage + 1} من {Math.ceil((jobItems.data?.total ?? 0) / 20)}</span><button type="button" onClick={() => setJobItemsPage((value) => Math.min(Math.ceil((jobItems.data?.total ?? 0) / 20) - 1, value + 1))} disabled={jobItemsPage >= Math.ceil((jobItems.data?.total ?? 0) / 20) - 1} className="rounded-lg border px-3 py-1 text-xs disabled:opacity-40">التالي</button></div>}
        </div>
      </div>}
    </section>}
    {workspaceView === "job" && !jobId && <div className="rounded-2xl border border-dashed bg-white p-10 text-center"><h3 className="font-bold">لا توجد مهمة محددة للمتابعة</h3><p className="mt-2 text-sm text-slate-500">ابدأ الإنتاج أولًا لعرض تفاصيل المهمة هنا. لا تعرض هذه المساحة سجلًا تاريخيًا للمهام؛ API الحالي يوفّر تفاصيل المهمة عند معرفة معرّفها.</p><button type="button" onClick={() => setWorkspaceView("production")} className="mt-4 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-bold text-white">إعداد إنتاج جديد</button></div>}
    {message && <div role="status" className="rounded-xl border bg-indigo-50 p-4 text-sm">{message}</div>}
    {workspaceView === "review" && (!hasLoaded ? <div className="rounded-2xl border border-dashed bg-white p-10 text-center"><h3 className="text-lg font-bold">بنك المنشورات جاهز</h3><p className="mt-2 text-sm text-slate-500">اختر كتابًا أو كل الكتب، ثم اضغط «عرض النتائج» لبدء التصفح.</p></div> : posts.isLoading && !posts.data ? <div role="status" className="rounded-2xl border bg-white p-10 text-center">جاري تحميل الصفحة الأولى فقط...</div> : posts.isError ? <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-5">تعذر تحميل المنشورات: {posts.error.message}</div> : <section className="space-y-3" aria-label="نتائج بنك المنشورات"><div className="rounded-2xl border bg-white p-4 shadow-sm"><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-bold">النتائج</h3><p className="text-sm text-slate-500">{total ? `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, total)} من ${total}` : "لا توجد نتائج"}</p></div><div className="flex flex-wrap gap-2"><button type="button" onClick={() => toggleCurrentPage(!allCurrentSelected)} disabled={!items.length} className="rounded-xl border px-3 py-2 text-sm font-semibold">{allCurrentSelected ? "إلغاء تحديد الصفحة" : "تحديد الصفحة"}</button><span className="rounded-xl bg-slate-100 px-3 py-2 text-sm font-semibold">{selected.length} محدد</span><button type="button" onClick={() => setSelected([])} disabled={!selected.length} className="rounded-xl border px-3 py-2 text-sm disabled:opacity-40">مسح التحديد</button></div></div><div className="mt-3 flex flex-wrap gap-2"><button type="button" onClick={() => bulkApprove.mutate()} disabled={!selected.length || bulkApprove.isPending} className="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-40">اعتماد المحدد</button>{approvedSelected.length > 0 && <button data-testid="go-publishing" type="button" onClick={() => navigate(`/publishing?selected_post_ids=${approvedSelected.map((p) => p.post_id).join(",")}`)} className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-bold">الانتقال إلى النشر ({approvedSelected.length})</button>}</div></div>{!items.length ? <div className="rounded-2xl border border-dashed bg-white p-10 text-center"><h3 className="font-bold">لا توجد نتائج مطابقة</h3><p className="mt-2 text-sm text-slate-500">جرّب تغيير الكتاب أو الحالة أو النوع أو البحث.</p></div> : items.map((post) => { const checked = selected.includes(post.post_id); return <article key={post.post_id} className="rounded-2xl border bg-white p-5 shadow-sm"><div className="flex items-start gap-3"><input aria-label={`تحديد ${post.title}`} type="checkbox" checked={checked} onChange={(e) => setSelected(toggleSelection(selected, post.post_id, e.target.checked))} className="mt-1 h-4 w-4"/><button type="button" onClick={() => { setEditing(post.post_id); setContent(post.content); setReviewNote(post.review_note ?? ""); }} className="min-w-0 flex-1 text-right"><strong className="block">{post.title}</strong><span className="mt-1 block text-xs text-slate-500">{post.source_title} · {post.topic_title || "دون محور"} · {post.status}</span><p className="mt-2 text-sm leading-7 text-slate-600">{post.content_preview}</p></button></div></article>; })}<div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border bg-white p-4"><button type="button" onClick={() => setPage((value) => Math.max(0, value - 1))} disabled={page === 0 || posts.isFetching} className="rounded-xl border px-4 py-2 disabled:opacity-40">السابق</button><span className="text-sm font-semibold">صفحة {page + 1} من {pageCount}</span><button type="button" onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))} disabled={page >= pageCount - 1 || posts.isFetching} className="rounded-xl border px-4 py-2 disabled:opacity-40">التالي</button></div></section>)}

    {workspaceView === "review" && editing && <div className="fixed inset-0 z-20 grid place-items-center bg-slate-950/30 p-4"><div role="dialog" className="max-h-[calc(100dvh-2rem)] w-full max-w-3xl overflow-y-auto rounded-2xl bg-white p-6 shadow-xl"><h3 className="text-xl font-bold">مراجعة المنشور</h3><textarea aria-label="محتوى المنشور" value={content} onChange={(e) => setContent(e.target.value)} className="mt-4 min-h-48 w-full rounded-xl border p-4"/><p className="mt-2 text-xs leading-6 text-slate-500">يمكن استخدام تنسيق تيليجرام HTML مثل &lt;b&gt;النص البارز&lt;/b&gt; و&lt;blockquote&gt;الاقتباس&lt;/blockquote&gt;. المعاينة أدناه لعرض التنسيق فقط؛ الحكم التحريري لك.</p><TelegramPreview content={content} /><input aria-label="ملاحظة المراجعة" value={reviewNote} onChange={(e) => setReviewNote(e.target.value)} placeholder="ملاحظة أو سبب الرفض" className="mt-3 w-full rounded-xl border p-3"/><div className="mt-5 flex flex-wrap gap-2"><button type="button" onClick={() => save.mutate()} disabled={save.isPending} className="rounded-xl border px-4 py-2 font-semibold">حفظ</button><button type="button" onClick={() => review.mutate({ id: editing, action: "approve" })} disabled={review.isPending} className="rounded-xl bg-emerald-600 px-4 py-2 font-semibold text-white">اعتماد</button><button type="button" onClick={() => review.mutate({ id: editing, action: "reject" })} disabled={review.isPending || !reviewNote.trim()} className="rounded-xl bg-rose-600 px-4 py-2 font-semibold text-white">رفض</button><button type="button" onClick={() => setEditing(null)} className="rounded-xl bg-slate-100 px-4 py-2 font-semibold">إغلاق</button></div></div></div>}
    {workspaceView === "review" && <GenericArtifactReviewPanel />}
  </section>;
}
