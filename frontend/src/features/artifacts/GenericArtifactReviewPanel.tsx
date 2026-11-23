import { DistributionReadinessPanel } from "./DistributionReadinessPanel";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { genericArtifactsApi, type GenericArtifactReviewStatus, type GenericReviewableArtifact } from "../../shared/api/artifactsApi";
import { Badge, EmptyState, Input, Select } from "../../shared/components/ui";
import { productionJobsApi, type ProductionProductOption, type ProductionRecipeOption } from "../../shared/api/productionJobsApi";
import { artifactSearchText, artifactSeriesKey } from "../../shared/utils/artifactLibrary";
import { postsApi } from "../../shared/api/postsApi";


const LIBRARY_PAGE_SIZE = 12;
const STORED_MEDIA = ["IMAGE", "VIDEO", "AUDIO", "DOCUMENT", "ANIMATION", "VOICE", "VIDEO_NOTE", "STICKER"];
const NATIVE_TEMPLATES: Record<string, Record<string, unknown>> = {
  POLL: { type: "POLL", question: "سؤال الاستطلاع", options: ["الخيار الأول", "الخيار الثاني"], allows_multiple_answers: false },
  LIVE_LOCATION: { type: "LIVE_LOCATION", latitude: 0, longitude: 0, live_period: 60 },
  LOCATION: { type: "LOCATION", latitude: 0, longitude: 0 },
  VENUE: { type: "VENUE", latitude: 0, longitude: 0, title: "اسم المكان", address: "العنوان" },
  CONTACT: { type: "CONTACT", phone_number: "+000000000", first_name: "جهة اتصال تجريبية" },
  DICE: { type: "DICE", emoji: "🎲" },
};
const MEDIA_LABELS: Record<string, string> = { IMAGE: "صورة", VIDEO: "فيديو", AUDIO: "ملف صوتي", DOCUMENT: "ملف", ANIMATION: "صورة متحركة", VOICE: "رسالة صوتية", VIDEO_NOTE: "رسالة فيديو دائرية", STICKER: "ملصق" };

function variantLength(artifact: GenericReviewableArtifact, draft: string | undefined): number {
  const text = draft ?? artifact.content ?? String(artifact.metadata.caption ?? "");
  const measure = (artifact.metadata.constraints as Record<string,unknown> | undefined)?.measure;
  if (measure === "chars") return Array.from(text).length;
  if (measure === "x_weighted") return text.replace(/https?:\/\/\S+/g, "x".repeat(23)).length;
  return text.length;
}

function artifactTitle(artifact: GenericReviewableArtifact): string {
  const title = artifact.metadata.title;
  if (typeof title === "string" && title.trim()) return title.trim();
  const caption = artifact.metadata.caption;
  if (typeof caption === "string" && caption.trim()) {
    const firstLine = caption.trim().split("\n")[0].trim();
    return firstLine.length > 90 ? firstLine.slice(0, 90) + "…" : firstLine;
  }
  const filename = artifact.metadata.original_filename;
  if (typeof filename === "string" && filename.trim()) return filename.replace(/^\d+-/, "");
  return `مخرج ${artifact.kind}`;
}

function artifactSeries(artifact: GenericReviewableArtifact): string | null {
  const filename = typeof artifact.metadata.original_filename === "string" ? artifact.metadata.original_filename.replace(/^\d+-/, "") : "";
  const episode = filename.match(/^b(\d+)v\d+/);
  if (episode) return `وش معنى · دفعة ${episode[1]}`;
  const womdha = filename.match(/^womdha-(\d+)/);
  if (womdha) return `ومضة ${womdha[1]}`;
  const intro = filename.match(/^v(\d+)-/);
  if (intro) return `فيديو تعريفي ${intro[1]}`;
  return null;
}

type ArtifactSortMode = "newest" | "oldest" | "title" | "kind";

function TelegramMediaDraftPreview({ artifact }: { artifact: GenericReviewableArtifact }) {
  const media = useQuery({
    queryKey: ["generic-artifact-media-url", artifact.id],
    queryFn: () => genericArtifactsApi.mediaUrl(artifact.id),
    enabled: Boolean(artifact.storage_uri) && STORED_MEDIA.includes(artifact.kind),
    staleTime: 4 * 60 * 1000,
  });
  const caption = ["VIDEO_NOTE", "STICKER"].includes(artifact.kind) ? "" : typeof artifact.metadata.caption === "string" ? artifact.metadata.caption : "";
  return (
    <section aria-label={`معاينة مسودة تيليجرام ${artifact.id}`} className="rounded-xl border border-sky-200 bg-[#0e1621] p-3">
      <div className="mx-auto max-w-sm rounded-2xl bg-white p-2 shadow">
        {media.isLoading ? <p role="status" className="p-3 text-sm text-slate-500">تحميل الوسيط للمعاينة...</p> : null}
        {media.isError ? <p role="alert" className="p-3 text-sm text-rose-700">تعذر تحميل الوسيط: {media.error?.message ?? "رابط غير متاح"}</p> : null}
        {media.data?.url && (artifact.kind === "IMAGE" || artifact.kind === "ANIMATION" && artifact.mime_type === "image/gif") ? <img src={media.data.url} alt={caption || "معاينة الوسيط"} className="max-h-72 w-full rounded-xl object-contain" /> : null}
        {media.data?.url && (["VIDEO", "VIDEO_NOTE"].includes(artifact.kind) || artifact.kind === "ANIMATION" && artifact.mime_type === "video/mp4") ? <video src={media.data.url} controls preload="metadata" className="max-h-72 w-full rounded-xl bg-black object-contain" /> : null}
        {media.data?.url && ["AUDIO", "VOICE"].includes(artifact.kind) ? <audio src={media.data.url} controls className="w-full" /> : null}
        {media.data?.url && ["DOCUMENT", "STICKER"].includes(artifact.kind) ? <p className="p-3 text-sm">مرفق:{String(artifact.metadata.original_filename ?? artifact.kind)}</p> : null}
        {caption ? <p dir="auto" className="whitespace-pre-wrap break-words p-3 text-sm leading-6 text-slate-900">{caption}</p> : null}
        <p dir="ltr" className="px-3 pb-2 text-left text-[11px] text-slate-400">قناة المعاينة · الآن</p>
      </div>
      <p className="mt-2 text-xs leading-5 text-slate-300">محاكاة تقريبية لشكل المنشور في تيليجرام (وسيط + تعليق)؛ التنسيق النهائي يعتمد على تيليجرام نفسه.</p>
    </section>
  );
}

function ArtifactPublicationLedger({id}:{id:string}) {
  const [open,setOpen]=useState(false);
  const query=useQuery({queryKey:["artifact-publications",id],queryFn:()=>genericArtifactsApi.publications(id),enabled:open});
  return <section className="space-y-2 rounded-xl border border-slate-200 bg-slate-50 p-3" aria-label={`سجل نشر المخرج ${id}`}>
    <button type="button" className="rounded border bg-white p-2 text-sm font-semibold" onClick={()=>{setOpen(true);if(open)void query.refetch();}}>عرض وتحديث سجل النشر</button>
    {open ? <><p className="text-xs">قراءة فقط، لا تنشئ مسودة ولا تعيد الإرسال. الاعتماد ليس دليلاً على النشر؛ وPUBLISHING قد تعني نتيجة غير محسومة فلا تعاود الإرسال.</p>
    {query.isLoading ? <p role="status">تحميل سجل النشر...</p>:null}{query.isError ? <p role="alert">{query.error.message}</p>:null}
    {query.data?.total===0 ? <p>لا توجد سجلات نشر لهذا العنصر. لا يشمل ذلك نشراً يدوياً خارج النظام.</p>:null}
    {query.data?.items.map(item=><article key={item.id} className="space-y-2 rounded border bg-white p-3 text-xs">
      <p className="font-semibold">{item.platform} · {item.status}</p><p className="break-all">الوجهة: <bdi>{item.destination}</bdi></p>
      <p className="break-all">سجل النشر: <bdi>{item.id}</bdi></p><p className="break-all">معرفات الرسائل: <bdi>{item.external_ids.join(", ") || "لم تُثبت بعد"}</bdi></p>
      <p>وقت القبول: <bdi>{item.published_at || "لم يُثبت بعد"}</bdi></p>
      <details><summary className="cursor-pointer">النص المحفوظ في سجل النشر</summary><p dir="auto" className="whitespace-pre-wrap break-words py-2">{item.content}</p></details>
      {item.schedules.map(schedule=><p key={schedule.schedule_id} className="break-all">{schedule.name} · {schedule.schedule_status} · العنصر {schedule.item_status} · المحاولات {schedule.attempts} · <bdi>{schedule.scheduled_at}</bdi>{schedule.last_error ? ` · ${schedule.last_error}`:""}</p>)}
      {item.error_message ? <p role="alert">{item.error_message}</p>:null}
    </article>)}
    {query.data && query.data.total>query.data.items.length ? <p>أحدث {query.data.items.length} من {query.data.total} سجلاً.</p>:null}</>:null}
  </section>;
}

function LiveLocationControls({ artifactId }: { artifactId: string }) {
  const query = useQuery({ queryKey: ['live-locations', artifactId], queryFn: () => genericArtifactsApi.liveLocations(artifactId) });
  const [latitude, setLatitude] = useState('0');
  const [longitude, setLongitude] = useState('0');
  const create = useMutation({ mutationFn: ({id, action}: {id:string; action:string}) => genericArtifactsApi.locationOperation(id, action === 'STOP' ? {action} : {action, latitude:Number(latitude), longitude:Number(longitude)}), onSuccess: () => { void query.refetch(); } });
  const cancel = useMutation({ mutationFn: (id:string) => genericArtifactsApi.cancelLocationOperation(id), onSuccess: () => { void query.refetch(); } });
  const execute = useMutation({ mutationFn: (id:string) => genericArtifactsApi.executeLocationOperation(id), onSuccess: () => { void query.refetch(); } });
  return <section className="space-y-2 rounded-xl border border-teal-200 bg-teal-50 p-3"><h4 className="font-bold">دورة الموقع الحي</h4><p className="text-xs">إحداثيات مكتوبة فقط،لا اتصال بموقع جهازك. التحديث والإيقاف يُراجعان قبل التنفيذ على نفس الرسالة. مدة محدودة،لا تتبع دائم.</p><button type="button" onClick={() => { void query.refetch(); }} className="rounded border p-2">تحديث حالة الموقع الحي</button>{query.isError ? <p role="alert">{query.error.message}</p> : null}{query.data?.length === 0 ? <p>لم يُنشر هذا الموقع بعد.</p> : null}{query.data?.map(record => <div key={record.publication_id} className="space-y-2 border-t pt-2"><p dir="ltr">Telegram {record.message_id} · {record.active ? 'ACTIVE' : 'STOPPED / EXPIRED'} · {record.expires_at}</p>{record.active ? <><label className="block">خط العرض<input aria-label="خط عرض التحديث" value={latitude} onChange={e=>setLatitude(e.target.value)} className="m-1 w-28 rounded border p-2" /></label><label className="block">خط الطول<input aria-label="خط طول التحديث" value={longitude} onChange={e=>setLongitude(e.target.value)} className="m-1 w-28 rounded border p-2" /></label><button type="button" disabled={create.isPending} onClick={()=>create.mutate({id:record.publication_id,action:'UPDATE'})} className="rounded border p-2">تجهيز تحديث الموقع للمراجعة</button><button type="button" disabled={create.isPending} onClick={()=>create.mutate({id:record.publication_id,action:'STOP'})} className="rounded border p-2">تجهيز إيقاف الموقع للمراجعة</button></> : null}{record.operations.map(operation=><div key={operation.id} className="rounded border bg-white p-2"><p>{operation.action} · {operation.status}</p><pre dir="ltr">{JSON.stringify(operation.payload)}</pre>{operation.status==='DRAFT' ? <button type="button" onClick={()=>cancel.mutate(operation.id)} className="rounded border p-2">إلغاء العملية قبل التنفيذ</button> : null}{operation.status==='DRAFT' && record.active ? <button type="button" disabled={execute.isPending} onClick={()=>execute.mutate(operation.id)} className="rounded bg-teal-700 p-2 text-white">اعتماد وتنفيذ {operation.action === 'STOP' ? 'إيقاف الموقع' : 'تحديث الموقع'}</button> : null}{operation.error_message ? <p role="alert">{operation.error_message}</p>:null}</div>)}</div>)}{create.isError ? <p role="alert">{create.error.message}</p>:null}{execute.isError ? <p role="alert">{execute.error.message}</p>:null}</section>;
}

function AlbumChildPreview({ id }: { id: string }) {
  const child = useQuery({ queryKey: ["album-child", id], queryFn: () => genericArtifactsApi.get(id) });
  return child.data ? <TelegramMediaDraftPreview artifact={child.data} /> : <p className="text-xs">{child.isError ? "تعذر تحميل عنصر الألبوم،راجع اعتماده." : "تحميل معاينة عنصر الألبوم..."}</p>;
}

function GenericArtifactMediaPreview({ artifact }: { artifact: GenericReviewableArtifact }) {
  const media = useQuery({
    queryKey: ["generic-artifact-media-url", artifact.id],
    queryFn: () => genericArtifactsApi.mediaUrl(artifact.id),
    enabled: Boolean(artifact.storage_uri) && STORED_MEDIA.includes(artifact.kind),
    staleTime: 4 * 60 * 1000,
  });
  if (!artifact.storage_uri) {
    return <p className="rounded-lg bg-amber-50 p-3 text-sm">مرجع الوسيط غير متوفر.</p>;
  }
  if (media.isLoading) {
    return <p role="status" className="rounded-lg bg-slate-50 p-3 text-sm">تحميل معاينة الوسيط...</p>;
  }
  if (media.isError || !media.data?.url) {
    return <p role="alert" className="rounded-lg bg-rose-50 p-3 text-sm">تعذر تحميل معاينة الوسيط: {media.error?.message ?? "رابط المعاينة غير متاح."}</p>;
  }
  const title = typeof artifact.metadata.title === "string" ? artifact.metadata.title : `معاينة ${artifact.kind}`;
  if (artifact.kind === "IMAGE" || artifact.kind === "ANIMATION" && artifact.mime_type === "image/gif") {
    return <img src={media.data.url} alt={title} className="max-h-64 max-w-full rounded-xl border object-contain" />;
  }
  if (["VIDEO", "VIDEO_NOTE"].includes(artifact.kind) || artifact.kind === "ANIMATION" && artifact.mime_type === "video/mp4") {
    return <video src={media.data.url} controls preload="metadata" className="max-h-64 w-full rounded-xl border object-contain bg-black" />;
  }
  if (["AUDIO", "VOICE"].includes(artifact.kind)) {
    return <audio src={media.data.url} controls preload="metadata" className="w-full" />;
  }
  return <a href={media.data.url} download rel="noreferrer" className="block break-words rounded-lg bg-slate-50 p-3 text-sm text-indigo-800">تنزيل المرفق:{String(artifact.metadata.original_filename ?? artifact.kind)}</a>;
}


export function GenericArtifactReviewPanel({ showDesignCard = true, designCardOnly = false }: { showDesignCard?: boolean; designCardOnly?: boolean } = {}) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<GenericArtifactReviewStatus>("DRAFT");
  const [drafts, setDrafts] = useState<Record<string, { content?: string; review_note?: string }>>({});
  const [cardProducts, setCardProducts] = useState<Record<string, string>>({});
  const [quizDrafts, setQuizDrafts] = useState<Record<string, { id: string; status: string; external_id?: string | null }>>({});
  const [mediaDrafts, setMediaDrafts] = useState<Record<string, { id: string; status: string }>>({});
  const [mediaSchedules, setMediaSchedules] = useState<Record<string, { id: string; status: string; at: string }>>({});
  const [scheduleInputs, setScheduleInputs] = useState<Record<string, string>>({});
  const [variantPlatform, setVariantPlatform] = useState<Record<string, string>>({});
  const [variantNotes, setVariantNotes] = useState<Record<string, string>>({});
  const [variantPostId, setVariantPostId] = useState("");
  const [variantPostPlatform, setVariantPostPlatform] = useState("");
  const [variantPostNote, setVariantPostNote] = useState("");
  const [search, setSearch] = useState("");
  const [kindFilter, setKindFilter] = useState("ALL");
  const [sourceFilter, setSourceFilter] = useState("ALL");
  const [seriesFilter, setSeriesFilter] = useState("ALL");
  const [sortMode, setSortMode] = useState<ArtifactSortMode>("newest");
  const [page, setPage] = useState(0);
  const [selectedMediaIds, setSelectedMediaIds] = useState<string[]>([]);
  const [batchNote, setBatchNote] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadCaption, setUploadCaption] = useState("");
  const [uploadKind, setUploadKind] = useState("");
  const [manualKind, setManualKind] = useState("TEXT");
  const [manualTitle, setManualTitle] = useState("");
  const [manualContent, setManualContent] = useState("");
  const [quizOptions, setQuizOptions] = useState("");
  const [quizAnswer, setQuizAnswer] = useState(0);
  const [nativeJson, setNativeJson] = useState("");
  const [selectedPostId, setSelectedPostId] = useState("");
  const [postProductKey, setPostProductKey] = useState("");
  const [activeCardJob, setActiveCardJob] = useState("");
  const approvedPosts = useQuery({ queryKey: ["approved-posts-for-design-cards"], queryFn: () => postsApi.list({ status: "APPROVED", limit: 100 }) });
  const products = useQuery({ queryKey: ["design-card-products"], queryFn: () => productionJobsApi.products() });
  const recipes = useQuery({ queryKey: ["design-card-recipes"], queryFn: () => productionJobsApi.recipes() });
  const eligibleCardProducts = (products.data ?? []).filter((product: ProductionProductOption) => {
    const version = product.versions.find((item) => item.version === product.active_version);
    if (!version) return false;
    const recipe = recipes.data?.find((item: ProductionRecipeOption) => item.key === version.definition.recipe_key);
    const pinnedRecipeVersion = version.definition.component_versions?.recipe.version;
    const recipeVersion = recipe?.versions.find((item) => item.version === (pinnedRecipeVersion ?? recipe.active_version));
    return ["PUBLISHED", "ARCHIVED"].includes(recipeVersion?.status ?? "") && Boolean(recipeVersion?.stages.some((stage) => stage.capability_key === "render_approved_text_card" && stage.capability_version === 1));
  });
  const artifacts = useQuery({
    queryKey: ["generic-artifacts", status],
    queryFn: () => genericArtifactsApi.listAll(status),
    enabled: !designCardOnly,
  });
  const activeJob = useQuery({
    queryKey: ["design-card-production-job", activeCardJob],
    queryFn: () => productionJobsApi.get(activeCardJob),
    enabled: Boolean(activeCardJob),
    refetchInterval: (query) => {
      const jobStatus = query.state.data?.status;
      return jobStatus === "COMPLETED" || jobStatus === "FAILED" ? false : 1500;
    },
  });
  useEffect(() => {
    if (activeJob.data?.status === "COMPLETED" || activeJob.data?.status === "FAILED") {
      queryClient.invalidateQueries({ queryKey: ["generic-artifacts"] });
    }
  }, [activeJob.data?.status, queryClient]);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["generic-artifacts"] });
  const allArtifacts = useMemo(() => artifacts.data?.items ?? [], [artifacts.data]);
  const seriesOptions = useMemo(() => [...new Set(allArtifacts.map(artifactSeriesKey))].sort((a,b) => a.localeCompare(b, "ar")), [allArtifacts]);
  const filteredArtifacts = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const matches = allArtifacts.filter((artifact) => {
      if (kindFilter !== "ALL" && artifact.kind !== kindFilter) return false;
      const sourceType = typeof artifact.metadata.source_type === "string" ? artifact.metadata.source_type : "GENERATED";
      if (sourceFilter !== "ALL" && sourceType !== sourceFilter) return false;
      if (seriesFilter !== "ALL" && artifactSeriesKey(artifact) !== seriesFilter) return false;
      if (!needle) return true;
      const haystack = artifactSearchText(artifact);
      return haystack.includes(needle);
    });
    const sorted = [...matches];
    if (sortMode === "oldest") sorted.sort((a, b) => a.created_at.localeCompare(b.created_at));
    else if (sortMode === "title") sorted.sort((a, b) => artifactTitle(a).localeCompare(artifactTitle(b), "ar"));
    else if (sortMode === "kind") sorted.sort((a, b) => a.kind.localeCompare(b.kind) || b.created_at.localeCompare(a.created_at));
    else sorted.sort((a, b) => b.created_at.localeCompare(a.created_at));
    return sorted;
  }, [allArtifacts, search, kindFilter, sourceFilter, seriesFilter, sortMode]);
  const pageCount = Math.max(1, Math.ceil(filteredArtifacts.length / LIBRARY_PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const pagedArtifacts = filteredArtifacts.slice(safePage * LIBRARY_PAGE_SIZE, safePage * LIBRARY_PAGE_SIZE + LIBRARY_PAGE_SIZE);
  const updateFilters = (apply: () => void) => { apply(); setPage(0); };
  const save = useMutation({
    mutationFn: (id: string) => {
      const artifact = (artifacts.data?.items ?? []).find((item) => item.id === id);
      const content = drafts[id]?.content;
      if (artifact?.metadata.source_type === "PLATFORM_VARIANT" && artifact.content === null && content !== undefined) {
        return genericArtifactsApi.update(id, { metadata: { ...artifact.metadata, caption: content } });
      }
      if (artifact?.kind === "QUIZ" && content !== undefined) {
        const quiz = artifact.metadata.quiz && typeof artifact.metadata.quiz === "object" && !Array.isArray(artifact.metadata.quiz)
          ? artifact.metadata.quiz as Record<string, unknown>
          : {};
        return genericArtifactsApi.update(id, {
          content,
          metadata: { ...artifact.metadata, quiz: { ...quiz, question: content } },
        });
      }
      return genericArtifactsApi.update(id, { content });
    },
    onSuccess: (_, id) => { setDrafts(current => { const next = {...current}; delete next[id]; return next; }); return refresh(); },
  });
  const approve = useMutation({
    mutationFn: (id: string) => genericArtifactsApi.approve(id, drafts[id]?.review_note),
    onSuccess: refresh,
  });
  const reject = useMutation({
    mutationFn: (id: string) => genericArtifactsApi.reject(id, drafts[id]?.review_note ?? ""),
    onSuccess: refresh,
  });
  const createQuizDraft = useMutation({
    mutationFn: (id: string) => genericArtifactsApi.createQuizDraft(id),
    onSuccess: (publication, artifactId) => setQuizDrafts((current) => ({ ...current, [artifactId]: { id: publication.id, status: publication.status } })),
  });
  const ingestMedia = useMutation({
    mutationFn: () => {
      if (!uploadFile) throw new Error("اختر ملف صورة أو فيديو أولًا.");
      return genericArtifactsApi.ingestReadyMedia({ file: uploadFile, caption: uploadCaption, media_kind: uploadKind || undefined });
    },
    onSuccess: () => {
      setUploadFile(null);
      setUploadCaption("");
      setStatus("DRAFT");
      refresh();
    },
  });
  const createManual = useMutation({
    mutationFn: () => genericArtifactsApi.manualDraft({ kind: manualKind === "QUIZ" ? "QUIZ" : "TEXT", title: manualTitle, content: manualContent,
      ...(NATIVE_TEMPLATES[manualKind] ? { native: JSON.parse(nativeJson) as Record<string, unknown> } : {}),
      ...(manualKind === "QUIZ" ? { quiz: { question: manualContent, options: quizOptions.split("\n").map(v => v.trim()).filter(Boolean), correct_option_id: quizAnswer } } : {}) }),
    onSuccess: () => { setStatus("DRAFT"); setManualTitle(""); setManualContent(""); refresh(); },
  });
  const deriveVariant = useMutation({
    mutationFn: ({ id, platform }: { id: string; platform: string }) => genericArtifactsApi.derivePlatformVariant(id, platform),
    onSuccess: (variant, input) => {
      setVariantNotes((current) => ({ ...current, [input.id]: `نسخة ${String(variant.metadata.platform_label_ar ?? input.platform)} جاهزة للمراجعة؛ إن كانت موجودة فقد حُفظت تعديلاتك دون استبدالها.` }));
      refresh();
    },
  });
  const derivePostVariant = useMutation({
    mutationFn: ({ postId, platform }: { postId: string; platform: string }) => genericArtifactsApi.derivePlatformVariantFromPost(postId, platform),
    onSuccess: (variant, input) => {
      setVariantPostNote(`أُنشئت نسخة ${String(variant.metadata.platform_label_ar ?? input.platform)} بحدود الطول من المنشور وهي الآن قيد المراجعة في قائمة المخرجات.`);
      refresh();
    },
  });
  const createMediaDraft = useMutation({
    mutationFn: (id: string) => genericArtifactsApi.createTelegramMediaDraft(id),
    onSuccess: (publication, artifactId) => setMediaDrafts((current) => ({ ...current, [artifactId]: { id: publication.id, status: publication.status } })),
  });
  const scheduleMediaDraft = useMutation({
    mutationFn: ({ id, scheduledAt }: { id: string; scheduledAt: string }) => {
      // datetime-local carries no timezone; interpret the entered wall time as
      // Asia/Riyadh (fixed UTC+3) so the saved instant is browser-independent.
      const when = new Date(`${scheduledAt}:00+03:00`);
      if (Number.isNaN(when.getTime())) throw new Error("الموعد المحدد غير صالح.");
      return genericArtifactsApi.scheduleArtifact(id, {
        name: `جدولة مسودة ${id.slice(0, 8)}`,
        timezone: "Asia/Riyadh",
        scheduled_at: when.toISOString(),
      });
    },
    onSuccess: (schedule, input) => setMediaSchedules((current) => ({ ...current, [input.id]: { id: schedule.id, status: schedule.status, at: schedule.items[0]?.scheduled_at ?? "" } })),
  });
  const isTelegramMediaEligible = (artifact: GenericReviewableArtifact) =>
    (STORED_MEDIA.includes(artifact.kind) && Boolean(artifact.storage_uri) || ["TEXT", "QUIZ"].includes(artifact.kind)) && artifact.review_status === "APPROVED";
  const eligibleSelectedCount = selectedMediaIds.length;
  const batchMediaDrafts = useMutation({
    mutationFn: async (ids: string[]) => {
      const results: Array<{ artifactId: string; id?: string; status?: string; error?: string }> = [];
      for (const artifactId of ids) {
        try {
          const publication = await genericArtifactsApi.createTelegramMediaDraft(artifactId);
          results.push({ artifactId, id: publication.id, status: publication.status });
        } catch (error) {
          results.push({ artifactId, error: error instanceof Error ? error.message : "تعذر إنشاء المسودة" });
        }
      }
      return results;
    },
    onSuccess: (results) => {
      setMediaDrafts((current) => {
        const next = { ...current };
        results.forEach((result) => {
          if (result.id) next[result.artifactId] = { id: result.id, status: result.status ?? "DRAFT" };
        });
        return next;
      });
      const succeeded = results.filter((result) => result.id).length;
      const failed = results.length - succeeded;
      setBatchNote(failed === 0
        ? `أُنشئت ${succeeded} مسودة Telegram قيد المراجعة في سجل النشر. لا يُنشر شيء خارجيًا دون اعتمادك.`
        : `أُنشئت ${succeeded} مسودة وتعذر إنشاء ${failed}. راجع العناصر المحددة لمعرفة السبب.`);
      if (failed === 0) setSelectedMediaIds([]);
    },
    onError: (error) => setBatchNote(`تعذر إنشاء المسودات: ${error instanceof Error ? error.message : "خطأ غير معروف"}`),
  });
  const createLivePhoto = useMutation({
    mutationFn: () => {
      const selected = allArtifacts.filter(item => selectedMediaIds.includes(item.id));
      const photo = selected.find(item => item.kind === 'IMAGE');
      const video = selected.find(item => item.kind === 'VIDEO');
      if (selected.length !== 2 || !photo || !video) throw new Error('اختر صورة ثابتة وفيديو حركة فقط.');
      return genericArtifactsApi.livePhotoDraft({ photo_id: photo.id, video_id: video.id, title: 'صورة حية Telegram للمراجعة' });
    },
    onSuccess: () => { setSelectedMediaIds([]); setStatus('DRAFT'); setSearch(''); setBatchNote('أُنشئت صورة حية للمراجعة،لا إرسال تلقائي.'); refresh(); },
  });
  const createAlbum = useMutation({
    mutationFn: () => genericArtifactsApi.albumDraft({ artifact_ids: selectedMediaIds, title: "ألبوم Telegram للمراجعة" }),
    onSuccess: () => { setSelectedMediaIds([]); setSearch(""); setStatus("DRAFT"); setBatchNote("أُنشئ ألبوم قيد المراجعة،لا نشر تلقائي."); refresh(); },
  });
  const toggleMediaSelection = (artifactId: string, checked: boolean) => {
    setSelectedMediaIds((current) => checked ? [...new Set([...current, artifactId])] : current.filter((id) => id !== artifactId));
  };
  const pageEligibleIds = pagedArtifacts.filter(isTelegramMediaEligible).map((artifact) => artifact.id);
  const allPageSelected = pageEligibleIds.length > 0 && pageEligibleIds.every((id) => selectedMediaIds.includes(id));
  const publishQuiz = useMutation({
    mutationFn: ({ publicationId, content }: { artifactId: string; publicationId: string; content: string }) => genericArtifactsApi.publishQuiz(publicationId, content),
    onSuccess: (publication, input) => setQuizDrafts((current) => ({ ...current, [input.artifactId]: { id: publication.id, status: publication.status, external_id: publication.external_id } })),
  });
  const createCard = useMutation({
    mutationFn: async ({ artifact, postId, productKey }: { artifact?: GenericReviewableArtifact; postId?: string; productKey: string }) => {
      if (Boolean(artifact) === Boolean(postId)) throw new Error("اختر مصدرًا واحدًا للتصميم.");
      const product = eligibleCardProducts.find((item) => item.key === productKey);
      const version = product?.versions.find((item) => item.version === product.active_version);
      if (!product || !version) throw new Error("تعذر العثور على إصدار منتج البطاقات المنشور.");
      const sourceId = artifact?.id ?? postId!;
      const job = await productionJobsApi.create({
        scope: "SELECTION",
        ...(artifact ? { source_artifact_id: artifact.id } : { source_post_id: postId }),
        product_key: product.key,
        recipe_key: version.definition.recipe_key,
        idempotency_key: `design-card:${crypto.randomUUID()}`,
      });
      return { sourceId, postSource: Boolean(postId), job };
    },
    onSuccess: ({ job }) => {
      setActiveCardJob(job.job_id);
      queryClient.invalidateQueries({ queryKey: ["production-jobs"] });
    },
  });

  const designCard = (
    <div className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-4 space-y-3">
      <h3 className="font-bold">إنتاج تصميم من منشور معتمد</h3>
      <p className="text-sm text-slate-600">يُستخدم نص Post المعتمد مباشرةً دون إنشاء TEXT Artifact وسيط. يظل اعتماد الصورة ومراجعتها مستقلًا.</p>
      <div className="grid gap-3 md:grid-cols-2">
          <label className="text-sm font-semibold">المنشور المصدر
          <select aria-label="المنشور المصدر للتصميم" value={selectedPostId} onChange={(event) => setSelectedPostId(event.target.value)} className="mt-1 w-full max-w-full rounded-lg border bg-white p-2 font-normal">
            <option value="">اختر منشورًا معتمدًا</option>
            {(approvedPosts.data?.items ?? []).filter((post) => post.status === "APPROVED" && post.content.trim()).map((post) => <option key={post.post_id} value={post.post_id}>{post.title} · {post.post_id.slice(0, 8)}</option>)}
          </select>
        </label>
        <label className="text-sm font-semibold">منتج التصميم المنشور
          <select aria-label="منتج التصميم من المنشور" value={postProductKey} onChange={(event) => setPostProductKey(event.target.value)} className="mt-1 w-full max-w-full rounded-lg border bg-white p-2 font-normal">
            <option value="">اختر منتجًا</option>
            {eligibleCardProducts.map((product) => <option key={product.key} value={product.key}>{product.name} · {product.key}</option>)}
          </select>
        </label>
      </div>
      {selectedPostId ? <div className="rounded-lg bg-white p-3 text-sm leading-7 text-slate-700" dir="auto">{(approvedPosts.data?.items ?? []).find((post) => post.post_id === selectedPostId)?.content ?? "تعذر تحميل نص المنشور المحدد."}</div> : null}
      {products.isLoading || recipes.isLoading ? <p role="status" className="text-sm text-slate-500">تحميل منتجات التصميم المنشورة...</p> : null}
      {products.isError || recipes.isError ? <p role="alert" className="text-sm text-rose-700">تعذر تحميل منتجات التصميم أو وصفاته: {(products.error ?? recipes.error)?.message}</p> : null}
      {!products.isLoading && !recipes.isLoading && !products.isError && !recipes.isError && eligibleCardProducts.length === 0 ? <p role="status" className="text-sm text-amber-800">لا يوجد حاليًا منتج تصميم منشور مرتبط بوصفة تدعم إنتاج البطاقات.</p> : null}
      <button type="button" onClick={() => createCard.mutate({ postId: selectedPostId, productKey: postProductKey })} disabled={!selectedPostId || !postProductKey || createCard.isPending || products.isLoading || recipes.isLoading} className="rounded-lg bg-indigo-600 px-3 py-2 text-sm font-semibold text-white">{createCard.isPending ? "جارٍ بدء الإنتاج..." : "إنتاج تصميم للمنشور"}</button>
      {approvedPosts.isLoading ? <p role="status" className="text-sm text-slate-500">تحميل المنشورات المعتمدة...</p> : null}
      {approvedPosts.isError ? <p role="alert" className="text-sm text-rose-700">تعذر تحميل المنشورات المعتمدة: {approvedPosts.error.message}</p> : null}
    </div>
  );
  const jobStatus = activeCardJob ? <div role="status" className="rounded-xl border border-indigo-100 bg-indigo-50 p-3 text-sm">
      <p className="font-semibold">مهمة إنتاج التصميم · {activeCardJob}</p>
      {activeJob.isLoading ? <p>جارٍ تحميل حالة المهمة...</p> : null}
      {activeJob.isError ? <p className="text-rose-700">تعذر تحديث حالة الإنتاج: {activeJob.error.message}</p> : null}
      {activeJob.data?.status === "QUEUED" || activeJob.data?.status === "RUNNING" ? <p>الإنتاج جارٍ · التقدم {activeJob.data.progress_percent ?? 0}% · اكتمل {activeJob.data.completed_items ?? 0} من {activeJob.data.total_items ?? 1}</p> : null}
      {activeJob.data?.status === "COMPLETED" ? <p className="text-emerald-800">اكتمل الإنتاج. حُدثت قائمة المخرجات؛ انتقل إلى حالة «قيد المراجعة» لمعاينة التصميم.</p> : null}
      {activeJob.data?.status === "FAILED" ? <p className="text-rose-700">فشل الإنتاج: {activeJob.data.error_message ?? "لم يُرجع النظام تفاصيل إضافية."}</p> : null}
    </div> : null;
  const mutationError = (save.isError || approve.isError || reject.isError || createCard.isError) ? <p role="alert" className="text-sm text-rose-700">{(save.error ?? approve.error ?? reject.error ?? createCard.error)?.message}</p> : null;
  if (designCardOnly) {
    return (
      <section className="space-y-3 rounded-2xl border bg-white p-5 shadow-sm" aria-label="إنتاج تصميم من منشور معتمد">
        {designCard}
        {jobStatus}
        {mutationError}
      </section>
    );
  }
  return <section className="space-y-3 rounded-2xl border bg-white p-5 shadow-sm" aria-label="مراجعة المخرجات العامة">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 className="text-lg font-bold">مراجعة المخرجات العامة</h2>
        <p className="mt-1 text-sm text-slate-500">النصوص والوسائط التي لا تمثل منشورات Telegram تمر بمراجعة مستقلة.</p>
      </div>
      <label className="text-sm font-semibold">الحالة
        <select aria-label="حالة مراجعة المخرجات" value={status} onChange={(event) => setStatus(event.target.value as GenericArtifactReviewStatus)} className="mr-2 max-w-full rounded-lg border p-2 font-normal">
          <option value="DRAFT">قيد المراجعة</option>
          <option value="APPROVED">معتمد</option>
          <option value="REJECTED">مرفوض</option>
        </select>
      </label>
    </div>
    <div className="space-y-3 rounded-xl border border-slate-200 bg-slate-50/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-bold">مكتبة المخرجات</h3>
        <p className="text-xs font-semibold text-slate-500">
          {artifacts.data ? `${filteredArtifacts.length} من ${artifacts.data.total} عنصرًا في هذه الحالة` : ""}
        </p>
      </div>
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        <Input aria-label="بحث في المخرجات" value={search} onChange={(event) => updateFilters(() => setSearch(event.target.value))} placeholder="ابحث بالعنوان أو الأصل أو نسخ المنصات أو اسم الملف..." />
        <Select aria-label="تصفية حسب نوع المخرج" value={kindFilter} onChange={(event) => updateFilters(() => setKindFilter(event.target.value))}>
          <option value="ALL">كل الأنواع</option>
          <option value="VIDEO">فيديو</option>
          <option value="IMAGE">صورة</option>
          <option value="TEXT">نص</option>
          <option value="AUDIO">صوت</option>
          <option value="QUIZ">اختبار</option>
          {Object.entries(MEDIA_LABELS).filter(([k]) => !["IMAGE", "VIDEO", "AUDIO"].includes(k)).map(([k,v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
        <Select aria-label="تصفية حسب مصدر المخرج" value={sourceFilter} onChange={(event) => updateFilters(() => setSourceFilter(event.target.value))}>
          <option value="ALL">كل المصادر</option>
          <option value="MEDIA_BANK_UPLOAD">رفع يدوي</option>
          <option value="GENERATED">مخرج مولّد</option>
          <option value="PLATFORM_VARIANT">نسخة منصة</option>
        </Select>
        <Select aria-label="تصفية حسب السلسلة" value={seriesFilter} onChange={(event) => updateFilters(() => setSeriesFilter(event.target.value))}>
          <option value="ALL">كل السلاسل</option>
          {seriesOptions.map((series) => <option key={series} value={series}>{series}</option>)}
        </Select>
        <Select aria-label="ترتيب المخرجات" value={sortMode} onChange={(event) => setSortMode(event.target.value as ArtifactSortMode)}>
          <option value="newest">الأحدث أولًا</option>
          <option value="oldest">الأقدم أولًا</option>
          <option value="title">العنوان أبجديًا</option>
          <option value="kind">النوع</option>
        </Select>
      </div>
      {status === "APPROVED" ? <div className="flex flex-wrap items-center gap-3 rounded-xl border border-emerald-100 bg-emerald-50/60 p-3">
        <label className="flex items-center gap-2 text-sm font-bold text-slate-700">
          <input
            type="checkbox"
            aria-label="تحديد كل وسائط الصفحة"
            checked={allPageSelected}
            onChange={(event) => {
              const checked = event.target.checked;
              setSelectedMediaIds((current) => checked
                ? [...new Set([...current, ...pageEligibleIds])]
                : current.filter((id) => !pageEligibleIds.includes(id)));
            }}
            className="h-4 w-4 rounded border-slate-300"
          />
          تحديد كل عناصر الصفحة
        </label>
        <span className="text-xs font-semibold text-slate-500" data-testid="media-selection-count">{eligibleSelectedCount} محدد</span>
        <button
          type="button"
          data-testid="create-telegram-media-drafts"
          disabled={eligibleSelectedCount === 0 || batchMediaDrafts.isPending}
          onClick={() => batchMediaDrafts.mutate(selectedMediaIds)}
          className="rounded-xl bg-emerald-700 px-4 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:bg-emerald-300"
        >{batchMediaDrafts.isPending ? "جارٍ إنشاء المسودات..." : `إنشاء مسودات Telegram للمحدد (${eligibleSelectedCount})`}</button>
        <button type="button" disabled={selectedMediaIds.length < 2 || selectedMediaIds.length > 10 || createAlbum.isPending} onClick={() => createAlbum.mutate()} className="rounded-xl bg-sky-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-40">إنشاء ألبوم من المحدد (2-10)</button>
        <button type="button" disabled={selectedMediaIds.length !== 2 || createLivePhoto.isPending} onClick={() => createLivePhoto.mutate()} className="rounded-xl bg-violet-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-40">إنشاء صورة حية (صورة وفيديو)</button>
        {createLivePhoto.isError ? <p role="alert">{createLivePhoto.error.message}</p> : null}
        <p className="w-full text-xs">الألبوم:2-10عناصر،حتى100MiBإجمالاً. الصورة الحية:صورة وفيديوMP4حتى10ثوانٍ و10MiB. تُراجع العناصر ولا يرسلها التحديد وحده.</p>
        {createAlbum.isError ? <p role="alert">{createAlbum.error.message}</p> : null}
        {eligibleSelectedCount > 0 ? <button type="button" onClick={() => { setSelectedMediaIds([]); setBatchNote(""); }} className="text-sm font-bold text-slate-500 hover:text-slate-700">مسح التحديد</button> : null}
        <span className="w-full text-xs leading-5 text-slate-500">ينشئ مسودة نشر Telegram لكل وسيط معتمد محدد مع نص تعليقه للمراجعة؛ تجهيز فقط ولا يُنشر أو يُجدول شيء خارجيًا.</span>
        {batchNote ? <p role="status" className="w-full text-sm font-semibold text-emerald-800">{batchNote}</p> : null}
      </div> : null}
      {status === "APPROVED" && selectedMediaIds.length > 0 ? <DistributionReadinessPanel ids={selectedMediaIds} /> : null}
    </div>
    {artifacts.isLoading ? <p role="status" className="text-sm text-slate-500">تحميل المخرجات...</p> : null}
    {artifacts.isError ? <p role="alert" className="text-sm text-rose-700">تعذر تحميل المخرجات: {artifacts.error.message}</p> : null}
    {!artifacts.isLoading && !artifacts.isError && filteredArtifacts.length === 0 ? <EmptyState title={allArtifacts.length === 0 ? "لا توجد مخرجات في هذه الحالة." : "لا توجد نتائج مطابقة للبحث أو الفلاتر الحالية."} /> : null}
    <div className="grid min-w-0 gap-3 xl:grid-cols-2">
      {pagedArtifacts.map((artifact) => <article key={artifact.id} className="min-w-0 space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-2">
          {status === "APPROVED" && isTelegramMediaEligible(artifact) ? <input
            type="checkbox"
            aria-label={`تحديد المخرج ${artifact.id}`}
            checked={selectedMediaIds.includes(artifact.id)}
            onChange={(event) => toggleMediaSelection(artifact.id, event.target.checked)}
            className="mt-1 h-4 w-4 shrink-0 rounded border-slate-300"
          /> : null}
          <div className="min-w-0">
            <h3 className="text-sm font-extrabold text-slate-900" dir="auto">{artifactTitle(artifact)}</h3>
            <strong className="mt-0.5 block text-xs font-semibold text-slate-500">{artifact.kind} · {artifact.mime_type ?? "نوع غير محدد"}</strong>
            <p className="mt-1 text-[11px] text-slate-400">المعرّف {artifact.id.slice(0, 8)}</p>
          </div>
          <span className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700">{artifact.metadata.source_type === "MEDIA_BANK_UPLOAD" ? "رفع يدوي" : artifact.metadata.source_type === "PLATFORM_VARIANT" ? `نسخة ${String(artifact.metadata.platform_label_ar ?? artifact.metadata.platform ?? "منصة")}${(artifact.metadata.constraints as Record<string, unknown> | undefined)?.trimmed ? " · مقصوصة للحد" : ""}` : "مخرج مولّد"}</span>
          {artifactSeries(artifact) ? <Badge tone="sky">{artifactSeries(artifact)}</Badge> : null}
          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs">{artifact.review_status}</span>
        </div>
        {(artifact.metadata.telegram_native as Record<string, unknown> | undefined)?.type === 'LIVE_LOCATION' ? <LiveLocationControls artifactId={artifact.id} /> : null}
        {artifact.metadata.telegram_live_photo ? <section className="rounded-xl border border-violet-200 bg-violet-50 p-3"><h4 className="font-bold">صورة حية،الصورة الثابتة ثم فيديو الحركة</h4><pre dir="auto" className="whitespace-pre-wrap break-words text-xs">{JSON.stringify(artifact.metadata.live_photo_preview, null, 2)}</pre>{(Array.isArray(artifact.metadata.live_photo_preview) ? artifact.metadata.live_photo_preview : []).map(value => <AlbumChildPreview key={(value as {id:string}).id} id={(value as {id:string}).id} />)}<p className="text-xs">يُرسلان كصورة حية واحدة،وليست ألبوماً أو فيديو منفرداً.</p></section> : null}
        {artifact.metadata.telegram_album ? <section className="rounded-xl border border-sky-200 bg-sky-50 p-3"><h4 className="font-bold">ألبوم Telegram،الترتيب والتعليقات المعتمدة</h4><pre dir="auto" className="whitespace-pre-wrap break-words text-sm">{JSON.stringify(artifact.metadata.album_preview, null, 2)}</pre><div className="grid gap-2 sm:grid-cols-2">{(Array.isArray(artifact.metadata.album_preview) ? artifact.metadata.album_preview : []).map((value) => { const item = value as { id: string }; return <AlbumChildPreview key={item.id} id={item.id} />; })}</div><p className="text-xs">الصور والفيديو معًا،أو صوت فقط،أو مستندات فقط. تتوقف العملية إذا تغيّر اعتماد أو محتوى أي عنصر.</p></section> : null}
        {artifact.metadata.telegram_native ? <section className="rounded-lg border bg-sky-50 p-3"><h4 className="font-bold">معاينة بيانات Telegram</h4><pre dir="ltr" className="whitespace-pre-wrap break-all text-xs">{JSON.stringify(artifact.metadata.telegram_native, null, 2)}</pre></section> : null}
        {artifact.content !== null ? <div className="grid gap-4 xl:grid-cols-2">
          <section aria-label={`تحرير المخرج ${artifact.id}`} className="min-w-0 space-y-2">
            <h3 className="text-sm font-bold text-slate-700">المحرر</h3>
            <textarea
              aria-label={`محتوى المخرج ${artifact.id}`}
              value={drafts[artifact.id]?.content ?? artifact.content}
              onChange={(event) => setDrafts((current) => ({ ...current, [artifact.id]: { ...current[artifact.id], content: event.target.value } }))}
              disabled={status !== "DRAFT"}
              dir="auto"
              className="min-h-64 w-full rounded-xl border bg-white p-4 text-sm leading-8"
            />
            <p className="text-xs leading-5 text-slate-500">تظهر المعاينة بجانب المحرر وتتحدث مع كل تعديل؛ احفظ التغييرات قبل الاعتماد.</p>
          </section>
          <section aria-label={`معاينة قراءة المخرج ${artifact.id}`} className="min-w-0 space-y-2">
            <h3 className="text-sm font-bold text-slate-700">معاينة القراءة</h3>
            <div
              data-testid={`artifact-text-preview-${artifact.id}`}
              dir="auto"
              className="min-h-64 max-h-[36rem] overflow-y-auto rounded-xl border bg-slate-50 p-5 text-base leading-8 text-slate-800"
              style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", textAlign: "start" }}
            >{drafts[artifact.id]?.content ?? artifact.content}</div>
            <p className="text-xs leading-5 text-slate-500">تحافظ المعاينة على فواصل الأسطر والفقرات كما هي في النص. وهي معاينة للنص العادي، وليست محاكاة كاملة لتنسيقات القناة المستهدفة.</p>
          </section>
        </div> : <GenericArtifactMediaPreview artifact={artifact} />}
        {status === "APPROVED" && artifact.kind === "TEXT" && !artifact.metadata.telegram_album && !artifact.metadata.telegram_live_photo && !artifact.metadata.telegram_native && artifact.content ? <div className="flex flex-wrap items-center gap-2 rounded-xl border border-indigo-100 bg-indigo-50 p-3">
          <label className="w-full text-sm font-semibold sm:w-auto">إنشاء بطاقة من هذا النص المعتمد
            <select aria-label={`منتج البطاقة ${artifact.id}`} value={cardProducts[artifact.id] ?? ""} onChange={(event) => setCardProducts((current) => ({ ...current, [artifact.id]: event.target.value }))} className="mt-1 w-full max-w-full rounded-lg border bg-white p-2 font-normal sm:mt-0 sm:w-auto sm:max-w-md">
              <option value="">اختر منتج بطاقات منشورًا</option>
              {eligibleCardProducts.map((product) => <option key={product.key} value={product.key}>{product.name} · {product.key}</option>)}
            </select>
          </label>
          <button type="button" onClick={() => createCard.mutate({ artifact, productKey: cardProducts[artifact.id] ?? "" })} disabled={!cardProducts[artifact.id] || createCard.isPending} className="rounded-lg bg-indigo-600 px-3 py-2 text-sm font-semibold text-white">إنتاج البطاقة</button>
          {products.isLoading || recipes.isLoading ? <span className="text-xs">تحميل منتجات البطاقات...</span> : null}
          {!products.isLoading && eligibleCardProducts.length === 0 ? <span className="text-xs text-slate-600">لا يوجد منتج منشور بوصفة render_approved_text_card.</span> : null}
        </div> : null}
        {status === "APPROVED" && ["TEXT", "IMAGE", "VIDEO"].includes(artifact.kind) && artifact.metadata.source_type !== "PLATFORM_VARIANT" ? <div className="flex flex-wrap items-center gap-2 rounded-xl border border-sky-100 bg-sky-50 p-3">
          <label className="w-full text-sm font-semibold sm:w-auto">اشتقاق نسخة بحدود منصة
            <select aria-label={`منصة النسخة ${artifact.id}`} value={variantPlatform[artifact.id] ?? ""} onChange={(event) => setVariantPlatform((current) => ({ ...current, [artifact.id]: event.target.value }))} className="mt-1 w-full max-w-full rounded-lg border bg-white p-2 font-normal sm:mt-0 sm:w-auto">
              <option value="">اختر المنصة</option>
              <option value="tiktok">تيك توك</option>
              <option value="instagram">إنستقرام</option>
              <option value="x">إكس</option>
            </select>
          </label>
          <button type="button" onClick={() => deriveVariant.mutate({ id: artifact.id, platform: variantPlatform[artifact.id] ?? "" })} disabled={!variantPlatform[artifact.id] || deriveVariant.isPending} className="rounded-lg bg-sky-700 px-3 py-2 text-sm font-semibold text-white">{deriveVariant.isPending ? "جارٍ الاشتقاق..." : "اشتقاق النسخة"}</button>
          {variantNotes[artifact.id] ? <span role="status" className="text-xs text-sky-900">{variantNotes[artifact.id]}</span> : null}
          {deriveVariant.isError ? <span role="alert" className="text-xs text-rose-700">{deriveVariant.error.message}</span> : null}
          <span className="text-xs text-slate-600">نحتفظ بالنص الأصلي. إذا تجاوز حد المنصة تتوقف العملية بسبب واضح، دون قص أو تغيير معنى. النسخ القديمة محفوظة ولا تُستبدل. لا يُنشر شيء من هنا.</span>
        </div> : null}
        {status === "APPROVED" && STORED_MEDIA.includes(artifact.kind) && artifact.storage_uri ? <TelegramMediaDraftPreview artifact={artifact} /> : null}
        {status === "APPROVED" && (STORED_MEDIA.includes(artifact.kind) || ["TEXT", "QUIZ"].includes(artifact.kind)) ? <div className="space-y-2 rounded-xl border border-emerald-100 bg-emerald-50 p-3">
          <p className="text-sm font-semibold">محتوى معتمد جاهز لمسودة Telegram</p>
          {mediaDrafts[artifact.id] ? <p role="status" className="text-xs">سجل نشر Telegram: {mediaDrafts[artifact.id].id} · الحالة {mediaDrafts[artifact.id].status} · المسودة جاهزة للمراجعة في سجل النشر.</p> : null}
          {!mediaDrafts[artifact.id] ? <button type="button" onClick={() => createMediaDraft.mutate(artifact.id)} disabled={createMediaDraft.isPending} className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-semibold text-white">{createMediaDraft.isPending ? "جارٍ إنشاء المسودة..." : "إنشاء مسودة نشر Telegram"}</button> : null}
          {createMediaDraft.isError ? <p role="alert" className="text-sm text-rose-700">{createMediaDraft.error.message}</p> : null}
          <div className="flex flex-wrap items-center gap-2 border-t border-emerald-100 pt-2">
            <label className="text-sm font-semibold">موعد الجدولة (بتوقيت الرياض)
              <input type="datetime-local" aria-label={`موعد جدولة المخرج ${artifact.id}`} value={scheduleInputs[artifact.id] ?? ""} onChange={(event) => setScheduleInputs((current) => ({ ...current, [artifact.id]: event.target.value }))} className="mt-1 w-full rounded-lg border bg-white p-2 font-normal sm:mt-0 sm:w-auto" />
            </label>
            <button type="button" onClick={() => scheduleMediaDraft.mutate({ id: artifact.id, scheduledAt: scheduleInputs[artifact.id] ?? "" })} disabled={!scheduleInputs[artifact.id] || scheduleMediaDraft.isPending} className="rounded-lg bg-indigo-700 px-3 py-2 text-sm font-semibold text-white">{scheduleMediaDraft.isPending ? "جارٍ إنشاء مسودة الجدولة..." : "جدولة المسودة"}</button>
          </div>
          {mediaSchedules[artifact.id] ? <p role="status" className="text-xs">مسودة جدولة: <span dir="ltr">{mediaSchedules[artifact.id].id}</span> · الحالة {mediaSchedules[artifact.id].status} · الموعد <span dir="ltr">{mediaSchedules[artifact.id].at}</span> · تبقى مسودة؛ التفعيل والتنفيذ يتمان باعتمادك من صفحة النشر.</p> : null}
          {scheduleMediaDraft.isError ? <p role="alert" className="text-sm text-rose-700">{scheduleMediaDraft.error.message}</p> : null}
        </div> : null}
        {status === "APPROVED" && artifact.kind === "QUIZ" ? <div className="rounded-xl border border-emerald-100 bg-emerald-50 p-3 space-y-2">
          <p className="text-sm font-semibold">اختبار تفاعلي معتمد</p>
          <p className="text-sm text-slate-700">السؤال: {String((artifact.metadata.quiz as Record<string, unknown> | undefined)?.question ?? artifact.content ?? "")}</p>
          <ol className="list-decimal space-y-1 pr-6 text-sm text-slate-700">{(Array.isArray((artifact.metadata.quiz as Record<string, unknown> | undefined)?.options) ? (artifact.metadata.quiz as Record<string, unknown>).options as string[] : []).map((option, index) => <li key={index}>{option}{index === Number((artifact.metadata.quiz as Record<string, unknown> | undefined)?.correct_option_id) ? " ✓ الإجابة الصحيحة" : ""}</li>)}</ol>
          {quizDrafts[artifact.id] ? <p role="status" className="text-xs">سجل Telegram: {quizDrafts[artifact.id].id} · الحالة {quizDrafts[artifact.id].status}{quizDrafts[artifact.id].external_id ? ` · معرّف Telegram ${quizDrafts[artifact.id].external_id}` : ""}</p> : null}
          {(!quizDrafts[artifact.id] || quizDrafts[artifact.id].status === "FAILED") ? <button type="button" onClick={() => createQuizDraft.mutate(artifact.id)} disabled={createQuizDraft.isPending} className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-semibold text-white">{createQuizDraft.isPending ? "جارٍ تجهيز المسودة..." : quizDrafts[artifact.id] ? "إعادة تجهيز المسودة" : "إنشاء مسودة Telegram"}</button> : null}
          {quizDrafts[artifact.id]?.status === "DRAFT" ? <button type="button" onClick={() => publishQuiz.mutate({ artifactId: artifact.id, publicationId: quizDrafts[artifact.id].id, content: String((artifact.metadata.quiz as Record<string, unknown> | undefined)?.question ?? artifact.content ?? "") })} disabled={publishQuiz.isPending} className="rounded-lg bg-indigo-700 px-3 py-2 text-sm font-semibold text-white">{publishQuiz.isPending ? "جارٍ النشر..." : "نشر الاختبار الآن"}</button> : null}
          {createQuizDraft.isError ? <p role="alert" className="text-sm text-rose-700">{createQuizDraft.error.message}</p> : null}
          {publishQuiz.isError ? <p role="alert" className="text-sm text-rose-700">{publishQuiz.error.message}</p> : null}
        </div> : null}
        {artifact.metadata.source_type === "PLATFORM_VARIANT" ? <section aria-label={`نسخة منصة ${artifact.id}`} className="space-y-2 rounded-xl border border-indigo-200 bg-indigo-50 p-4">
          <h4 className="font-bold">نسخة {String(artifact.metadata.platform_label_ar ?? artifact.metadata.platform)} مستقلة</h4>
          <p className="text-xs">تعديل النسخة لا يغيّر الأصل. احفظ التعديلات قبل الاعتماد. إعادة الاشتقاق لا تستبدل المسودة الموجودة.</p>
          {artifact.content === null ? <textarea aria-label={`تعليق نسخة المنصة ${artifact.id}`} value={drafts[artifact.id]?.content ?? String(artifact.metadata.caption ?? "")} onChange={e=>setDrafts(current=>({...current,[artifact.id]:{...current[artifact.id],content:e.target.value}}))} disabled={status!=="DRAFT"} dir="auto" className="min-h-40 w-full rounded border bg-white p-3" /> : null}
          <p className="text-xs">الحد: {String((artifact.metadata.constraints as Record<string,unknown>)?.max_text ?? "غير محدد")} · القياس: {String((artifact.metadata.constraints as Record<string,unknown>)?.measure ?? "")} · الحالي: {variantLength(artifact, drafts[artifact.id]?.content)}</p>
          {artifact.content === null && status === "DRAFT" ? <button type="button" onClick={()=>save.mutate(artifact.id)} disabled={save.isPending} className="rounded border bg-white p-2">حفظ تعليق النسخة</button> : null}
          {drafts[artifact.id]?.content !== undefined && drafts[artifact.id]?.content !== (artifact.content ?? String(artifact.metadata.caption ?? "")) ? <p role="status" className="text-sm">توجد تعديلات غير محفوظة؛ احفظها قبل الاعتماد.</p> : null}
        </section> : null}
        {artifact.metadata.source_type === "PLATFORM_VARIANT" && variantLength(artifact, drafts[artifact.id]?.content) > Number((artifact.metadata.constraints as Record<string,unknown>)?.max_text ?? Infinity) ? <p role="alert" className="text-sm text-rose-700">تجاوزت النسخة حد المنصة. قصّر النص قبل الحفظ والاعتماد.</p> : null}
        {artifact.metadata.source_type !== "PLATFORM_VARIANT" ? <DistributionReadinessPanel ids={[artifact.id]} /> : null}
        <ArtifactPublicationLedger id={artifact.id} />
        <p className="break-all text-xs text-slate-500">عقد المخرج: {artifact.output_contract_key ?? "غير محدد"} · الإصدار {artifact.output_contract_version ?? "—"}</p>
        {typeof artifact.metadata.caption === "string" && artifact.metadata.caption ? <p dir="auto" className="rounded-lg bg-slate-50 p-3 text-sm leading-7 text-slate-800">{String(artifact.metadata.caption)}</p> : null}
        {artifact.metadata.video_library && typeof artifact.metadata.video_library === "object" ? <details className="space-y-3 rounded-xl border border-indigo-100 bg-indigo-50 p-4">
          <summary className="cursor-pointer text-sm font-bold text-indigo-900">النص الأصلي ونسخ المنصات</summary>
          {([
            ["source_original", "النص الأصلي الكامل"],
            ["tiktok_text", "وصف تيك توك الكامل"],
            ["telegram_caption", "تعليق Telegram المقترح"],
          ] as const).map(([key, label]) => <section key={key} className="mt-3 space-y-1">
            <h4 className="text-xs font-bold text-indigo-900">{label}</h4>
            <p dir="auto" className="max-h-80 overflow-y-auto whitespace-pre-wrap break-words rounded-lg bg-white p-3 text-sm leading-7 text-slate-800">{String((artifact.metadata.video_library as Record<string, unknown>)[key] ?? "")}</p>
          </section>)}
          <p className="mt-3 text-xs leading-6 text-indigo-800">نسخ منفصلة للمراجعة. حفظها لا يغيّر تعليق النشر الحالي ولا ينشر شيئاً. تعليمات التحرير محفوظة مع الأصل ولا تضاف تلقائياً إلى نسخ المنصات.</p>
        </details> : null}
        {Object.keys(artifact.metadata).length > 0 ? <details className="rounded-lg bg-slate-50 p-3 text-xs"><summary className="cursor-pointer font-semibold text-slate-600">تفاصيل تقنية</summary><pre dir="ltr" className="mt-2 overflow-x-auto whitespace-pre-wrap break-all text-left">{JSON.stringify(artifact.metadata, null, 2)}</pre></details> : null}
        <input aria-label={`ملاحظة مراجعة المخرج ${artifact.id}`} value={drafts[artifact.id]?.review_note ?? artifact.review_note ?? ""} onChange={(event) => setDrafts((current) => ({ ...current, [artifact.id]: { ...current[artifact.id], review_note: event.target.value } }))} placeholder="ملاحظة المراجعة أو سبب الرفض" disabled={status !== "DRAFT"} className="w-full rounded-xl border p-3 text-sm"/>
        {status === "DRAFT" ? <div className="flex flex-wrap gap-2">
          {artifact.content !== null ? <button type="button" onClick={() => save.mutate(artifact.id)} disabled={save.isPending} className="rounded-lg border px-3 py-2 text-sm font-semibold">حفظ التعديل</button> : null}
          <button type="button" onClick={() => approve.mutate(artifact.id)} disabled={approve.isPending || drafts[artifact.id]?.content !== undefined && drafts[artifact.id]?.content !== (artifact.content ?? String(artifact.metadata.caption ?? ""))} className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white">اعتماد المخرج</button>
          <button type="button" onClick={() => reject.mutate(artifact.id)} disabled={reject.isPending || !(drafts[artifact.id]?.review_note ?? "").trim()} className="rounded-lg bg-rose-600 px-3 py-2 text-sm font-semibold text-white">رفض المخرج</button>
        </div> : null}
      </article>)}
    </div>
    {pageCount > 1 ? <nav className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white p-3" aria-label="ترقيم صفحات المخرجات">
      <button type="button" onClick={() => setPage((current) => Math.max(0, current - 1))} disabled={safePage === 0} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-bold text-slate-600 disabled:opacity-40">السابق</button>
      <span className="text-xs font-semibold text-slate-500">صفحة {safePage + 1} من {pageCount} · عرض {pagedArtifacts.length} من {filteredArtifacts.length}</span>
      <button type="button" onClick={() => setPage((current) => Math.min(pageCount - 1, current + 1))} disabled={safePage >= pageCount - 1} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-bold text-slate-600 disabled:opacity-40">التالي</button>
    </nav> : null}
    <details className="space-y-3 rounded-xl border border-slate-200 bg-slate-50/40 p-4" open>
      <summary className="cursor-pointer text-sm font-bold text-slate-600">إجراءات إضافية: رفع وسيط جاهز، اشتقاق نسخة منصة، وبطاقة تصميم</summary>
      <div className="mt-3 space-y-3">
    <div className="space-y-3 rounded-xl border border-emerald-100 bg-emerald-50/50 p-4">
      <h3 className="font-bold">نص أو اختبار تفاعلي</h3>
      <select aria-label="نوع المسودة اليدوية" value={manualKind} onChange={e => { setManualKind(e.target.value); if (NATIVE_TEMPLATES[e.target.value]) setNativeJson(JSON.stringify(NATIVE_TEMPLATES[e.target.value], null, 2)); }} className="w-full rounded-lg border p-2"><option value="TEXT">نص</option><option value="QUIZ">اختبار</option><option value="POLL">استطلاع</option><option value="LOCATION">موقع</option><option value="LIVE_LOCATION">موقع حي محدود المدة</option><option value="VENUE">مكان</option><option value="CONTACT">جهة اتصال</option><option value="DICE">نرد تفاعلي</option></select>
      <input aria-label="عنوان المسودة اليدوية" value={manualTitle} onChange={e => setManualTitle(e.target.value)} placeholder="عنوان داخلي" className="w-full rounded-lg border p-2" />
      <textarea aria-label="نص المسودة اليدوية" value={manualContent} onChange={e => setManualContent(e.target.value)} placeholder={manualKind === "QUIZ" ? "سؤال الاختبار" : "النص الكامل"} className="min-h-32 w-full rounded-lg border p-2" />
      {NATIVE_TEMPLATES[manualKind] ? <label className="block text-sm">البيانات المنظمة(JSON)،عدّل القيم قبل الحفظ<textarea aria-label="بيانات Telegram المنظمة" value={nativeJson} onChange={e => setNativeJson(e.target.value)} dir="ltr" className="min-h-48 w-full rounded-lg border p-3 font-mono text-xs" /></label> : null}
      {manualKind === "QUIZ" ? <><textarea aria-label="خيارات الاختبار" value={quizOptions} onChange={e => setQuizOptions(e.target.value)} placeholder="كل خيار في سطر" className="w-full rounded-lg border p-2" /><label className="block">رقم الإجابة الصحيحة بدءاً من1<input aria-label="رقم الإجابة الصحيحة" type="number" min="1" value={quizAnswer + 1} onChange={e => setQuizAnswer(Number(e.target.value) - 1)} className="mx-2 rounded border p-2" /></label></> : null}
      <button type="button" onClick={() => createManual.mutate()} disabled={!manualTitle.trim() || !manualContent.trim() || createManual.isPending} className="rounded-lg bg-indigo-700 px-3 py-2 text-white">حفظ مسودة للمراجعة</button>
      {createManual.isError ? <p role="alert" className="text-rose-700">{createManual.error.message}</p> : null}
      {createManual.isSuccess ? <p role="status">حُفظت المسودة،لا نشر ولا اعتماد تلقائي.</p> : null}
      <h3 className="border-t pt-4 font-bold">بنك الوسائط الجاهزة</h3>
      <p className="text-sm text-slate-600">اختر نوع إرسال Telegram صراحةً للصوت والملفات والملصقات. كل رفع يدخل قيد المراجعة. حد Telegram: الصور10MiB، وبقية الملفات50MiB. الأصل محفوظ؛ تعليق النشر محدود1024حرفاً، ولا تعليق للملصق أو الفيديو الدائري.</p>
      <label className="block text-sm font-semibold">نوع الإرسال
        <select aria-label="نوع الوسيط المرفوع" value={uploadKind} onChange={e => setUploadKind(e.target.value)} className="mt-1 w-full rounded-lg border bg-white p-2">
          <option value="">تلقائي:صورة أوMP4</option>
          {Object.entries(MEDIA_LABELS).map(([k,v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </label>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="text-sm font-semibold">ملف الوسيط
          <input aria-label="ملف الوسيط الجاهز" type="file" onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)} className="mt-1 w-full max-w-full rounded-lg border bg-white p-2 font-normal" />
        </label>
        <label className="text-sm font-semibold">التعليق (يظهر نصًا مع الوسيط عند النشر)
          <input aria-label="تعليق الوسيط الجاهز" value={uploadCaption} onChange={(event) => setUploadCaption(event.target.value)} className="mt-1 w-full rounded-lg border bg-white p-2 font-normal" placeholder="نص يرافق الوسيط عند النشر" />
        </label>
      </div>
      <button type="button" onClick={() => ingestMedia.mutate()} disabled={!uploadFile || ingestMedia.isPending} className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-semibold text-white">{ingestMedia.isPending ? "جارٍ الرفع..." : "رفع إلى بنك الوسائط"}</button>
      {ingestMedia.isError ? <p role="alert" className="text-sm text-rose-700">{ingestMedia.error.message}</p> : null}
      {ingestMedia.isSuccess ? <p role="status" className="text-sm text-emerald-800">تم الرفع؛ الوسيط الآن قيد المراجعة.</p> : null}
    </div>
    <div className="space-y-3 rounded-xl border border-sky-100 bg-sky-50/50 p-4">
      <h3 className="font-bold">اشتقاق نسخة بحدود منصة من منشور معتمد</h3>
      <p className="text-sm text-slate-600">ينشئ نسخة نصية منفصلة من منشور معتمد، مقصوصة عند حدود آمنة ضمن حد المنصة الموثق. تجهيز طول فقط دون إعادة صياغة؛ المنشور الأصلي لا يتغير، والنسخة تُحفظ قيد المراجعة، ولا يُنشر شيء خارجيًا.</p>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="text-sm font-semibold">المنشور المصدر
          <select aria-label="المنشور المصدر للنسخة" value={variantPostId} onChange={(event) => setVariantPostId(event.target.value)} className="mt-1 w-full max-w-full rounded-lg border bg-white p-2 font-normal">
            <option value="">اختر منشورًا معتمدًا</option>
            {(approvedPosts.data?.items ?? []).filter((post) => post.status === "APPROVED" && post.content.trim()).map((post) => <option key={post.post_id} value={post.post_id}>{post.title} · {post.post_id.slice(0, 8)}</option>)}
          </select>
        </label>
        <label className="text-sm font-semibold">المنصة
          <select aria-label="منصة نسخة المنشور" value={variantPostPlatform} onChange={(event) => setVariantPostPlatform(event.target.value)} className="mt-1 w-full max-w-full rounded-lg border bg-white p-2 font-normal">
            <option value="">اختر المنصة</option>
            <option value="tiktok">تيك توك</option>
            <option value="instagram">إنستقرام</option>
            <option value="x">إكس</option>
          </select>
        </label>
      </div>
      <button type="button" onClick={() => derivePostVariant.mutate({ postId: variantPostId, platform: variantPostPlatform })} disabled={!variantPostId || !variantPostPlatform || derivePostVariant.isPending} className="rounded-lg bg-sky-700 px-3 py-2 text-sm font-semibold text-white">{derivePostVariant.isPending ? "جارٍ الاشتقاق..." : "اشتقاق نسخة المنشور"}</button>
      {variantPostNote ? <p role="status" className="text-sm text-sky-900">{variantPostNote}</p> : null}
      {derivePostVariant.isError ? <p role="alert" className="text-sm text-rose-700">تعذر اشتقاق النسخة: {derivePostVariant.error.message}</p> : null}
      {approvedPosts.isLoading ? <p role="status" className="text-sm text-slate-500">تحميل المنشورات المعتمدة...</p> : null}
    </div>
      {showDesignCard ? designCard : null}
      </div>
    </details>
    {jobStatus}
    {mutationError}
  </section>;
}
