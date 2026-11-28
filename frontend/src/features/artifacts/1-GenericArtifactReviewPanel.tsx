import {MetaBatchReviewPanel} from './MetaBatchReviewPanel';
import {NativeTelegramPreview} from './NativeTelegramPreview';
import {NativeTelegramFields,blankNative,nativeError} from './NativeTelegramFields';
import {BatchPlatformCopiesPanel} from './BatchPlatformCopiesPanel';
import { ApprovedBatchHandoff } from "./ApprovedBatchHandoff";
import { BatchReviewPanel } from "./BatchReviewPanel";
import { useSearchParams } from "react-router";
import {EditorialReviewNotes} from "./EditorialReviewNotes";
import {ContentOrganizationPanel} from "./ContentOrganizationPanel";
import { CentralPlatformCopiesPanel, type PlatformCopyDrafts } from "./CentralPlatformCopiesPanel";
import { TelegramBatchPreviewPanel } from "./TelegramBatchPreviewPanel";
import { DistributionReadinessPanel } from "./DistributionReadinessPanel";
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { genericArtifactsApi, type GenericArtifactReviewStatus, type GenericReviewableArtifact } from "../../shared/api/artifactsApi";
import { Badge, EmptyState, Input, Select } from "../../shared/components/ui";
import { productionJobsApi, type ProductionProductOption, type ProductionRecipeOption } from "../../shared/api/productionJobsApi";
import { isSelectableOriginal } from "../../shared/utils/artifactLibrary";
import {ApiError} from "../../shared/api/client";
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
  if(artifact.organization?.title)return artifact.organization.title;
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
  if(artifact.organization?.series)return artifact.organization.series;
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
  const [offset,setOffset]=useState(0);
  const pageSize=50;
  const query=useQuery({queryKey:["artifact-publications",id,offset],queryFn:()=>genericArtifactsApi.publications(id,offset,pageSize),enabled:open});
  return <section className="space-y-2 rounded-xl border border-slate-200 bg-slate-50 p-3" aria-label={`سجل نشر المخرج ${id}`}>
    <button type="button" className="rounded border bg-white p-2 text-sm font-semibold" onClick={()=>{setOpen(true);if(open)void query.refetch();}}>عرض وتحديث سجل النشر</button>
    {open ? <><p className="text-xs">قراءة فقط، لا تنشئ مسودة ولا تعيد الإرسال. الاعتماد ليس دليلاً على النشر؛ وPUBLISHING قد تعني نتيجة غير محسومة فلا تعاود الإرسال.</p>
    {query.isLoading ? <p role="status">تحميل سجل النشر...</p>:null}{query.isError ? <p role="alert">{query.error.message}</p>:null}
    {query.data?.total===0&&offset===0&&!query.data?.connector_items?.length ? <p>لا توجد سجلات نشر لهذا العنصر. لا يشمل ذلك نشراً يدوياً خارج النظام.</p>:null}
    {offset===0&&query.data?.connector_items?.length?<p className="text-xs">نتائج الموصلات المستقلة: {query.data.connector_items.length} نتيجة في هذه القراءة، منفصلة عن سجلات النشر المرقمة أدناه.</p>:null}
    {offset===0?query.data?.connector_items?.map(item=><article key={item.record_type+item.id} className="space-y-2 rounded border bg-white p-3 text-xs"><p className="font-semibold">{item.platform} · {item.status}</p><p>سجل الموصل المستقل · {item.confirmed?'نتيجة مثبتة':item.status==='RETIRED_UNPUBLISHED'?'عملية متروكة دون نشر، محفوظة للتوثيق':'لم يثبت اكتمال النشر'}</p><p className="break-all" dir="ltr">{item.destination} · {item.external_id||'لا معرّف نتيجة'}</p>{item.permalink?<a className="underline" href={item.permalink} target="_blank" rel="noreferrer">فتح نتيجة النشر المثبتة</a>:null}<p>{item.updated_at}</p><details><summary>النص المحفوظ وقت العملية</summary><p dir="auto" className="whitespace-pre-wrap break-words">{item.content}</p></details></article>):null}
    {query.data?.items.map(item=><article key={item.id} className="space-y-2 rounded border bg-white p-3 text-xs">
      <p className="font-semibold">{item.platform} · {item.status}</p><p className="break-all">الوجهة: <bdi>{item.destination}</bdi></p>
      <p className="break-all">سجل النشر: <bdi>{item.id}</bdi></p><p className="break-all">معرفات الرسائل: <bdi>{item.external_ids.join(", ") || "لم تُثبت بعد"}</bdi></p>
      <p>وقت القبول: <bdi>{item.published_at || "لم يُثبت بعد"}</bdi></p>
      <details><summary className="cursor-pointer">النص المحفوظ في سجل النشر</summary><p dir="auto" className="whitespace-pre-wrap break-words py-2">{item.content}</p></details>
      {item.schedules.map(schedule=><p key={schedule.schedule_id} className="break-all">{schedule.name} · {schedule.schedule_status} · العنصر {schedule.item_status} · المحاولات {schedule.attempts} · <bdi>{schedule.scheduled_at}</bdi>{schedule.last_error ? ` · ${schedule.last_error}`:""}</p>)}
      {item.error_message ? <p role="alert">{item.error_message}</p>:null}
    </article>)}
    {query.isFetching&&query.data?<p role="status" className="text-xs">جارٍ تحديث الصفحة المعروضة، هذه آخر قراءة محفوظة.</p>:null}
    {query.data?<nav aria-label={`صفحات سجل النشر ${id}`} className="flex flex-wrap items-center gap-2 text-xs"><button type="button" className="workspace-secondary" disabled={offset===0||query.isFetching} onClick={()=>setOffset(value=>Math.max(0,value-pageSize))}>السجلات الأحدث</button><span role="status">{query.data.items.length?`السجلات ${offset+1} إلى ${offset+query.data.items.length} من ${query.data.total}`:'لا سجلات نشر عامة في هذه الصفحة'}</span><button type="button" className="workspace-secondary" disabled={offset+query.data.items.length>=query.data.total||query.isFetching} onClick={()=>setOffset(value=>value+pageSize)}>السجلات الأقدم</button></nav>:offset>0?<button type="button" className="workspace-secondary" disabled={query.isFetching} onClick={()=>setOffset(value=>Math.max(0,value-pageSize))}>العودة إلى السجلات الأحدث</button>:null}
    {offset>0?<p className="text-xs">نتائج الموصلات المستقلة تظهر في الصفحة الأولى فقط، ولا تدخل في عدد سجلات النشر أعلاه.</p>:null}</>:null}
  </section>;
}

function LiveLocationControls({ artifactId }: { artifactId: string }) {
  const query = useQuery({ queryKey: ['live-locations', artifactId], queryFn: () => genericArtifactsApi.liveLocations(artifactId) });
  const [latitude, setLatitude] = useState('0');
  const [longitude, setLongitude] = useState('0');
  const create = useMutation({ mutationFn: ({id, action}: {id:string; action:string}) => genericArtifactsApi.locationOperation(id, action === 'STOP' ? {action} : {action, latitude:Number(latitude), longitude:Number(longitude)}), onSuccess: () => { void query.refetch(); } });
  const cancel = useMutation({ mutationFn: (id:string) => genericArtifactsApi.cancelLocationOperation(id), onSuccess: () => { void query.refetch(); } });
  const execute = useMutation({ mutationFn: (id:string) => genericArtifactsApi.executeLocationOperation(id), onSuccess: () => { void query.refetch(); } });
  return <section className="space-y-2 rounded-xl border border-teal-200 bg-teal-50 p-3"><h4 className="font-bold">دورة الموقع الحي</h4><p className="text-xs">إحداثيات مكتوبة فقط،لا اتصال بموقع جهازك. التحديث والإيقاف يُراجعان قبل التنفيذ على نفس الرسالة. مدة محدودة،لا تتبع دائم.</p><button type="button" onClick={() => { void query.refetch(); }} className="rounded border p-2">تحديث حالة الموقع الحي</button>{query.isError ? <p role="alert">{query.error.message}</p> : null}{query.data?.length === 0 ? <p>لم يُنشر هذا الموقع بعد.</p> : null}{query.data?.map(record => <div key={record.publication_id} className="space-y-2 border-t pt-2"><p dir="ltr">Telegram {record.message_id} · {record.active ? 'ACTIVE' : 'STOPPED / EXPIRED'} · {record.expires_at}</p>{record.active ? <><label className="block">خط العرض<input aria-label="خط عرض التحديث" value={latitude} onChange={e=>setLatitude(e.target.value)} className="m-1 w-28 rounded border p-2" /></label><label className="block">خط الطول<input aria-label="خط طول التحديث" value={longitude} onChange={e=>setLongitude(e.target.value)} className="m-1 w-28 rounded border p-2" /></label><button type="button" disabled={create.isPending} onClick={()=>create.mutate({id:record.publication_id,action:'UPDATE'})} className="rounded border p-2">تجهيز تحديث الموقع للمراجعة</button><button type="button" disabled={create.isPending} onClick={()=>create.mutate({id:record.publication_id,action:'STOP'})} className="rounded border p-2">تجهيز إيقاف الموقع للمراجعة</button></> : null}{record.operations.map(operation=><div key={operation.id} className="rounded border bg-white p-2"><p>{operation.action} · {operation.status}</p><details className="min-w-0"><summary className="cursor-pointer text-xs">تفاصيل العملية التقنية</summary><pre dir="ltr" className="max-w-full whitespace-pre-wrap break-all text-xs">{JSON.stringify(operation.payload)}</pre></details>{operation.status==='DRAFT' ? <button type="button" onClick={()=>cancel.mutate(operation.id)} className="rounded border p-2">إلغاء العملية قبل التنفيذ</button> : null}{operation.status==='DRAFT' && record.active ? <button type="button" disabled={execute.isPending} onClick={()=>execute.mutate(operation.id)} className="rounded bg-teal-700 p-2 text-white">اعتماد وتنفيذ {operation.action === 'STOP' ? 'إيقاف الموقع' : 'تحديث الموقع'}</button> : null}{operation.error_message ? <p role="alert">{operation.error_message}</p>:null}</div>)}</div>)}{create.isError ? <p role="alert">{create.error.message}</p>:null}{execute.isError ? <p role="alert">{execute.error.message}</p>:null}</section>;
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
    return <video aria-label="معاينة الفيديو الأصلي" src={media.data.url} controls playsInline preload="metadata" className="mx-auto h-auto max-h-[min(80svh,960px)] w-auto max-w-full rounded-xl border object-contain bg-black" />;
  }
  if (["AUDIO", "VOICE"].includes(artifact.kind)) {
    return <audio src={media.data.url} controls preload="metadata" className="w-full" />;
  }
  return <a href={media.data.url} download rel="noreferrer" className="block break-words rounded-lg bg-slate-50 p-3 text-sm text-indigo-800">تنزيل المرفق:{String(artifact.metadata.original_filename ?? artifact.kind)}</a>;
}


export function GenericArtifactReviewPanel({ designCardOnly = false }: { showDesignCard?: boolean; designCardOnly?: boolean } = {}) {
  const queryClient = useQueryClient();
  const [libraryParams,setLibraryParams] = useSearchParams();
  const [status, setStatus] = useState<GenericArtifactReviewStatus>(["APPROVED","REJECTED"].includes(libraryParams.get("artifact_status")??"") ? libraryParams.get("artifact_status") as GenericArtifactReviewStatus : "DRAFT");
  const [,refreshCopyDrafts]=useState(0);
  const copyDrafts=useRef<PlatformCopyDrafts>({drafts:new Map(),saving:new Set(),errors:new Map(),changed:()=>refreshCopyDrafts(value=>value+1)});
  const [copyRequests,setCopyRequests]=useState<Record<string,{platform:string;nonce:number}>>({});
  const [focusedId,setFocusedState] = useState<string|null>(libraryParams.get("artifact_id"));
  const setFocusedId=(id:string|null)=>{setFocusedState(id);const next=new URLSearchParams(libraryParams);if(id){next.set("artifact_id",id);next.set("artifact_status",status);}else next.delete("artifact_id");if(id!==focusedId){next.delete("instagram_job_id");next.delete("text_job_id");next.delete("photo_job_id");}setLibraryParams(next,{preventScrollReset:true});};
  useEffect(()=>{setFocusedState(libraryParams.get("artifact_id"));const requested=libraryParams.get("artifact_status");if(requested&&["DRAFT","APPROVED","REJECTED"].includes(requested))setStatus(requested as GenericArtifactReviewStatus);},[libraryParams]);
  const materialNav=useRef<HTMLElement>(null);
  const returnTarget=useRef<string|null>(null);
  useEffect(()=>{if(!focusedId)return;const frame=requestAnimationFrame(()=>{materialNav.current?.focus({preventScroll:true});if(materialNav.current)window.scrollTo({top:Math.max(0,materialNav.current.getBoundingClientRect().top+window.scrollY-96),left:0,behavior:"instant"});});return()=>cancelAnimationFrame(frame);},[focusedId,status]);
  const creationTask=(["manual","upload","variant","design"].includes(libraryParams.get("library_task")??"")?libraryParams.get("library_task"):null);
  const [creationVisit,setCreationVisit]=useState(0);
  const chooseCreationTask=(task:string)=>{setCreationVisit(v=>v+1);const next=new URLSearchParams(window.location.search);next.set("library_task",task);setLibraryParams(next,{preventScrollReset:true});};
  useEffect(()=>{if(!creationTask)return;const frame=requestAnimationFrame(()=>{const panel=document.getElementById("library-create-tools") as HTMLDetailsElement|null;if(panel)panel.open=true;const heading=document.getElementById("library-task-"+creationTask);heading?.focus({preventScroll:true});heading?.scrollIntoView({block:"start"});});return()=>cancelAnimationFrame(frame);},[creationTask,creationVisit]);
  const [compact,setCompact] = useState(libraryParams.get("library_view")!=="expanded");
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
  const filterValue=(key:string,fallback:string)=>libraryParams.get(key)??fallback;
  const setLibraryFilter=(key:string,value:string,fallback:string)=>{const next=new URLSearchParams(window.location.search);if(value===fallback)next.delete(key);else next.set(key,value);next.delete("artifact_id");next.delete("instagram_job_id");next.delete("text_job_id");next.delete("photo_job_id");setLibraryParams(next,{replace:true,preventScrollReset:true});};
  const [search,setSearchText]=useState(()=>filterValue("library_q",""));
  const searchRequested=useRef(search);
  const setSearch=(value:string)=>{searchRequested.current=value;setSearchText(value);setLibraryFilter("library_q",value,"");};
  const observedQuery=useRef(filterValue("library_q",""));
  useEffect(()=>{const value=libraryParams.get("library_q")??"";if(observedQuery.current===value)return;observedQuery.current=value;if(value===searchRequested.current)return;searchRequested.current=value;setSearchText(value);},[libraryParams]);
  const kindFilter=filterValue("library_kind","ALL");const setKindFilter=(value:string)=>setLibraryFilter("library_kind",value,"ALL");
  const sourceFilter=filterValue("library_source","ALL");const setSourceFilter=(value:string)=>setLibraryFilter("library_source",value,"ALL");
  const seriesFilter=filterValue("library_series","ALL");const setSeriesFilter=(value:string)=>setLibraryFilter("library_series",value,"ALL");
  const categoryFilter=filterValue("library_category","ALL");const setCategoryFilter=(value:string)=>setLibraryFilter("library_category",value,"ALL");
  const [catalogIds,setCatalogIds]=useState<string[]>([]);
  const rawSort=filterValue("library_sort","newest");const sortMode:ArtifactSortMode=["newest","oldest","title","kind"].includes(rawSort)?rawSort as ArtifactSortMode:"newest";
  const setSortMode=(value:ArtifactSortMode)=>setLibraryFilter("library_sort",value,"newest");
  const [page, setPage] = useState(0);
  const [selectedMediaIds, setSelectedMediaIds] = useState<string[]>([]);
  const reviewBatchRaw=libraryParams.get("review_batch");
  const reviewBatchIds=useMemo(()=>reviewBatchRaw===null?[]:reviewBatchRaw.split(","),[reviewBatchRaw]);
  const finishBatchReview=(ids:string[])=>{const next=new URLSearchParams(libraryParams);next.set("artifact_status","APPROVED");next.set("review_batch",ids.join(","));next.delete("artifact_id");for(const key of ["library_q","library_kind","library_source","library_series","library_category","library_sort"])next.delete(key);setSelectedMediaIds([]);setStatus("APPROVED");setFocusedState(null);setPage(0);setLibraryParams(next,{preventScrollReset:true});void refresh();};

  const [copiesRevision,setCopiesRevision]=useState(0);
  const [batchNote, setBatchNote] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const uploadInput = useRef<HTMLInputElement>(null);
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
    queryKey: ["generic-artifacts", status, search, kindFilter, sourceFilter, seriesFilter, categoryFilter, sortMode, page],
    queryFn: () => genericArtifactsApi.library({review_status:status,q:search,kind:kindFilter,source:sourceFilter,series:seriesFilter,category:categoryFilter,sort:sortMode==="title"?"newest":sortMode,include_items:sortMode==="title"?"false":"true",limit:LIBRARY_PAGE_SIZE,offset:page*LIBRARY_PAGE_SIZE}),
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
  // Keep the existing browser Intl Arabic order, without transferring all original content.
  const resultIndex=useMemo(()=>{const index=[...(artifacts.data?.index??[])];return sortMode==="title"?index.sort((a,b)=>artifactTitle(a).localeCompare(artifactTitle(b),"ar")):index;},[artifacts.data,sortMode]);
  const titlePageIds=useMemo(()=>sortMode==="title"?resultIndex.slice(page*LIBRARY_PAGE_SIZE,(page+1)*LIBRARY_PAGE_SIZE).map(i=>i.id):[],[resultIndex,page,sortMode]);
  const requestedIds=useMemo(()=>[...new Set([...titlePageIds,...selectedMediaIds,...catalogIds,...reviewBatchIds,...(focusedId?[focusedId]:[])])],[titlePageIds,selectedMediaIds,catalogIds,reviewBatchIds,focusedId]);
  const selectedItems=useQuery({queryKey:["generic-artifacts","exact",requestedIds],queryFn:async()=>{const items=(await Promise.all(Array.from({length:Math.ceil(requestedIds.length/100)},(_,n)=>genericArtifactsApi.libraryItems(requestedIds.slice(n*100,(n+1)*100))))).flatMap(r=>r.items);if(items.length!==requestedIds.length||new Set(items.map(i=>i.id)).size!==requestedIds.length||items.some((i,n)=>i.id!==requestedIds[n]))throw new Error("لم تتطابق المواد المقروءة مع التحديد المطلوب. أعد القراءة.");return {items};},enabled:!designCardOnly&&requestedIds.length>0});
  const focusedMissing=Boolean(focusedId&&requestedIds.length===1&&selectedItems.error instanceof ApiError&&selectedItems.error.status===404);
  const selectedLoaded=requestedIds.length===0||Boolean(selectedItems.data&&requestedIds.every(id=>selectedItems.data.items.some(i=>i.id===id)));
  const selectedReady=selectedLoaded&&!selectedItems.isFetching&&!selectedItems.isError;
  const allArtifacts=useMemo(()=>Array.from(new Map([...(artifacts.data?.index??[]),...(artifacts.data?.items??[]),...(selectedItems.data?.items??[])].map(i=>[i.id,i])).values()),[artifacts.data,selectedItems.data]);
  useEffect(()=>{if(reviewBatchRaw!==null)setSelectedMediaIds([]);},[reviewBatchRaw]);
  useEffect(()=>{if(reviewBatchRaw!==null&&(artifacts.isFetching||artifacts.isError||reviewBatchIds.some(id=>!allArtifacts.some(i=>i.id===id&&i.review_status==="APPROVED"&&i.status==="AVAILABLE"&&i.metadata.source_type!=="PLATFORM_VARIANT"))))setSelectedMediaIds([]);},[reviewBatchRaw,reviewBatchIds,allArtifacts,artifacts.isFetching,artifacts.isError]);

  useEffect(()=>{if(!selectedItems.data||selectedItems.isFetching||selectedItems.isError)return;setSelectedMediaIds(current=>{const next=current.filter(id=>selectedItems.data.items.some(i=>i.id===id&&isSelectableOriginal(i)));return next.length===current.length?current:next;});},[selectedItems.data,selectedItems.isFetching,selectedItems.isError]);

  const seriesOptions = [...(artifacts.data?.filter_options?.series??[])].sort((a,b)=>a.localeCompare(b,"ar"));
  const categoryOptions = [...(artifacts.data?.filter_options?.categories??[])].sort((a,b)=>a.localeCompare(b,"ar"));
  const filteredArtifacts=useMemo(()=>{const byId=new Map(allArtifacts.map(i=>[i.id,i]));return resultIndex.map(i=>byId.get(i.id)!);},[resultIndex,allArtifacts]);
  const pageCount = Math.max(1, Math.ceil((artifacts.data?.total??0) / LIBRARY_PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  useEffect(()=>{if(artifacts.data&&!artifacts.isFetching&&!artifacts.isError&&page>=pageCount)setPage(pageCount-1);},[artifacts.data,artifacts.isFetching,artifacts.isError,page,pageCount]);
  const pagedArtifacts = sortMode==="title"?titlePageIds.flatMap(id=>selectedItems.data?.items.find(i=>i.id===id)??[]):artifacts.data?.items??[];
  const focusedArtifact=focusedId?[...(artifacts.data?.items??[]),...(selectedReady?selectedItems.data?.items??[]:[])].find(item=>item.id===focusedId&&item.review_status===status):null;
  const focusIndex=filteredArtifacts.findIndex(item=>item.id===focusedId);
  const displayArtifacts=focusedId?(focusedArtifact?[focusedArtifact]:[]):pagedArtifacts;
  useEffect(()=>{if(focusedId||!returnTarget.current||artifacts.isFetching)return;const id=returnTarget.current;const frame=requestAnimationFrame(()=>{const target=document.getElementById(`material-open-${id}`);if(target){returnTarget.current=null;target.focus({preventScroll:true});target.scrollIntoView({block:"center",behavior:"instant"});}});return()=>cancelAnimationFrame(frame);},[focusedId,artifacts.data,artifacts.isFetching,selectedItems.data,selectedItems.isFetching]);
  const returnToLibrary=()=>{returnTarget.current=focusedId;if(focusIndex>=0)setPage(Math.floor(focusIndex/LIBRARY_PAGE_SIZE));setFocusedId(null);};
  const updateFilters = (apply: () => void) => { apply(); setPage(0); setFocusedState(null); };
  const save = useMutation({
    mutationFn: (id: string) => {
      const artifact = allArtifacts.find((item) => item.id === id);
      const content = drafts[id]?.content;
      if (artifact && artifact.content === null && content !== undefined) {
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
  const approvalScope=useRef({key:''});
  const approvalKey=libraryParams.toString()+'|'+focusedId+'|'+status;
  if(approvalScope.current.key!==approvalKey)approvalScope.current={key:approvalKey};
  const approvalMounted=useRef(true);
  useEffect(()=>{approvalMounted.current=true;return()=>{approvalMounted.current=false;approvalScope.current={key:''};};},[]);
  const approve = useMutation({
    mutationFn: async (id: string) => {
      const result=await genericArtifactsApi.approve(id, drafts[id]?.review_note);
      if(result.id!==id||result.review_status!=='APPROVED')throw new Error('لم تتطابق نتيجة الاعتماد مع المادة. حدّث الحالة وتحقق قبل المحاولة مجدداً.');
      return result;
    },
    onMutate:(id:string)=>({scope:approvalScope.current,focused:focusedId===id,url:window.location.href}),
    onSuccess: (_,id,request) => {
      if(approvalMounted.current&&request?.focused&&approvalScope.current===request.scope&&window.location.href===request.url){
        const next=new URLSearchParams(window.location.search);next.set('artifact_status','APPROVED');next.set('artifact_id',id);
        for(const key of ['instagram_job_id','text_job_id','photo_job_id','copy_platform','review_batch'])next.delete(key);
        setStatus('APPROVED');setFocusedState(id);setSelectedMediaIds([]);setLibraryParams(next,{preventScrollReset:true});
      }
      return refresh();
    },
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
      if (uploadInput.current) uploadInput.current.value = "";
      setUploadCaption("");
      setStatus("DRAFT");
      refresh();
    },
  });
  const createManual = useMutation({
    mutationFn: () => genericArtifactsApi.manualDraft({ kind: manualKind === "QUIZ" ? "QUIZ" : "TEXT", title: manualTitle, content: manualContent,
      ...(NATIVE_TEMPLATES[manualKind] ? { native: (()=>{const error=nativeError(nativeJson);if(error)throw new Error(error);const parsed=JSON.parse(nativeJson);if(parsed.type!==manualKind)throw new Error("نوع البيانات لا يطابق نوع المسودة المختار.");if(parsed.last_name==="")delete parsed.last_name;return parsed;})() as Record<string, unknown> } : {}),
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

  const eligibleSelectedCount = selectedMediaIds.length;
  const batchMediaDrafts = useMutation({
    mutationFn: async (ids: string[]) => {
      if(!selectedReady)throw new Error("انتظر اكتمال قراءة المواد المحددة.");
      const preflight = await genericArtifactsApi.telegramBatchPreview(ids);
      if (preflight.blocked_count) throw new Error(`تعذر تجهيز الدفعة: ${preflight.blocked_count} مادة محجوبة. افتح معاينة الدفعة لقراءة الأسباب.`);
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
      if(!selectedReady)throw new Error("انتظر اكتمال قراءة المواد المحددة.");
      const selected = allArtifacts.filter(item => selectedMediaIds.includes(item.id));
      const photo = selected.find(item => item.kind === 'IMAGE');
      const video = selected.find(item => item.kind === 'VIDEO');
      if (selected.length !== 2 || !photo || !video) throw new Error('اختر صورة ثابتة وفيديو حركة فقط.');
      return genericArtifactsApi.livePhotoDraft({ photo_id: photo.id, video_id: video.id, title: 'صورة حية Telegram للمراجعة' });
    },
    onSuccess: () => { setSelectedMediaIds([]); setStatus('DRAFT'); setSearch(''); setBatchNote('أُنشئت صورة حية للمراجعة،لا إرسال تلقائي.'); refresh(); },
  });
  const createAlbum = useMutation({
    mutationFn: () => {if(!selectedReady)throw new Error("انتظر اكتمال قراءة المواد المحددة.");return genericArtifactsApi.albumDraft({ artifact_ids: selectedMediaIds, title: "ألبوم Telegram للمراجعة" });},
    onSuccess: () => { setSelectedMediaIds([]); setSearch(""); setStatus("DRAFT"); setBatchNote("أُنشئ ألبوم قيد المراجعة،لا نشر تلقائي."); refresh(); },
  });
  const toggleMediaSelection = (artifactId: string, checked: boolean) => {
    setSelectedMediaIds((current) => checked ? [...new Set([...current, artifactId])].slice(0,100) : current.filter((id) => id !== artifactId));
  };
  const pageEligibleIds = pagedArtifacts.filter(isSelectableOriginal).map((artifact) => artifact.id);
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
  return <section className="library-browser space-y-3" aria-label="مراجعة المخرجات العامة">
    <nav aria-label="مهام بنك المحتوى" className="grid grid-cols-2 gap-2 lg:grid-cols-4">{[["إنشاء نص أو اختبار", "manual"],["رفع وسيط جاهز", "upload"],["اشتقاق نسخة منصة", "variant"],["إنتاج بطاقة تصميم", "design"]].map(([label,target])=><button type="button" key={target} className="workspace-secondary justify-start" aria-pressed={creationTask===target} onClick={()=>chooseCreationTask(target)}>＋ {label}</button>)}</nav>
    <div className="library-heading flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 className="workspace-section-title">مكتبة المحتوى</h2>
        <p className="mt-1 text-sm text-slate-500">تصفّح المواد، ثم افتح مادة لمراجعة أصلها وتجهيز وجهاتها.</p>
      </div>
      <label className="text-sm font-semibold">الحالة
        <select aria-label="حالة مراجعة المخرجات" value={status} onChange={(event) => {const next=new URLSearchParams(window.location.search);next.delete("artifact_id");next.delete("instagram_job_id");next.delete("text_job_id");next.delete("photo_job_id");next.set("artifact_status",event.target.value);setFocusedState(null);setStatus(event.target.value as GenericArtifactReviewStatus);setLibraryParams(next,{preventScrollReset:true});}} className="mr-2 max-w-full rounded-lg border p-2 font-normal">
          <option value="DRAFT">قيد المراجعة</option>
          <option value="APPROVED">معتمد</option>
          <option value="REJECTED">مرفوض</option>
        </select>
      </label>
    </div>
    <div className="library-toolbar space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-xs text-slate-400">البحث والتصفية</h3>
        <p className="text-xs font-semibold text-slate-500">
          {artifacts.data ? `${filteredArtifacts.length} من ${artifacts.data.total} عنصرًا في هذه الحالة` : ""}
        </p>
      </div>
      <div className="grid grid-cols-2 gap-2 xl:grid-cols-3">
        <Input id="content-library-search" className="col-span-2 scroll-mt-24 xl:col-span-3" aria-label="بحث في المخرجات" value={search} onChange={(event) => updateFilters(() => setSearch(event.target.value))} placeholder="ابحث بالعنوان أو الأصل أو نسخ المنصات أو اسم الملف..." />
      </div><details open={!compact} className="library-filters"><summary>تصفية وترتيب · النوع، المصدر، السلسلة، التصنيف</summary><div className="grid grid-cols-2 gap-2 pt-3 xl:grid-cols-3">        <Select aria-label="تصفية حسب نوع المخرج" value={kindFilter} onChange={(event) => updateFilters(() => setKindFilter(event.target.value))}>
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
        <Select aria-label="تصفية حسب التصنيف" value={categoryFilter} onChange={event=>updateFilters(()=>setCategoryFilter(event.target.value))}><option value="ALL">كل التصنيفات</option>{categoryOptions.map(c=><option key={c} value={c}>{c}</option>)}</Select>
        <Select aria-label="ترتيب المخرجات" value={sortMode} onChange={(event) => updateFilters(()=>setSortMode(event.target.value as ArtifactSortMode))}>
          <option value="newest">الأحدث أولًا</option>
          <option value="oldest">الأقدم أولًا</option>
          <option value="title">العنوان أبجديًا</option>
          <option value="kind">النوع</option>
        </Select>
      </div></details>
      <details open={!compact} className="library-filters"><summary>تنظيم جماعي · تحديد الفهرسة والسلاسل والتصنيفات</summary><div className="flex flex-wrap items-center gap-2 pt-3 text-xs leading-7"><p className="text-slate-400">فهرسة المواد، مستقلة عن تحديد النشر · حتى 100 مادة</p><button type="button" className="rounded border p-2" onClick={()=>setCatalogIds(pagedArtifacts.filter(i=>i.metadata.source_type!=="PLATFORM_VARIANT").map(i=>i.id))}>تحديد صفحة الفهرسة</button> <button type="button" className="rounded border p-2" onClick={()=>setCatalogIds([])}>إلغاء تحديد الفهرسة</button><p>{catalogIds.filter(id=>allArtifacts.some(i=>i.id===id)).length} محدد للتنظيم</p></div></details>
      {selectedLoaded&&catalogIds.some(id=>allArtifacts.some(i=>i.id===id))?<fieldset disabled={!selectedReady}><ContentOrganizationPanel key={catalogIds.join(",")} items={allArtifacts.filter(i=>catalogIds.includes(i.id))}/></fieldset>:null}
      {status === "DRAFT" ? <div hidden={Boolean(focusedId)}><BatchReviewPanel unavailable={artifacts.isFetching||artifacts.isError||Boolean(focusedId)} visitKey={focusedId} key={[status,search,kindFilter,sourceFilter,seriesFilter,categoryFilter].join("|")} items={filteredArtifacts} pageItems={pagedArtifacts} unsavedIds={Object.keys(drafts).filter(id=>drafts[id]?.content!==undefined||drafts[id]?.review_note!==undefined)} renderMedia={item=>item.storage_uri?<GenericArtifactMediaPreview artifact={item}/>:null} onApproved={finishBatchReview}/></div>:null}
      {status==="APPROVED"&&reviewBatchRaw!==null?<ApprovedBatchHandoff ids={reviewBatchIds} items={allArtifacts} loading={artifacts.isFetching||selectedItems.isFetching} failed={artifacts.isError||selectedItems.isError||!selectedReady} onContinue={ids=>{setSelectedMediaIds(ids);setBatchNote(`حُددت مواد دفعة الاعتماد نفسها وعددها ${ids.length}. اختر الوجهات أو افحص Telegram أدناه؛ لم تُحفظ وجهات ولم تُنشأ خطة.`);}} onClear={()=>{const next=new URLSearchParams(libraryParams);next.delete("review_batch");setLibraryParams(next,{preventScrollReset:true});setSelectedMediaIds([]);setBatchNote("");}}/>:null}
      {status === "APPROVED" ? <div className="flex flex-wrap items-center gap-3 rounded-xl border border-emerald-100 bg-emerald-50/60 p-3">
        <label className="flex items-center gap-2 text-sm font-bold text-slate-700">
          <input
            type="checkbox"
            aria-label="تحديد كل وسائط الصفحة"
            checked={allPageSelected}
            onChange={(event) => {
              const checked = event.target.checked;
              setSelectedMediaIds((current) => checked
                ? [...new Set([...current, ...pageEligibleIds])].slice(0,100)
                : current.filter((id) => !pageEligibleIds.includes(id)));
            }}
            className="h-4 w-4 rounded border-slate-300"
          />
          تحديد كل عناصر الصفحة
        </label>
        <button type="button" onClick={()=>{const eligible=filteredArtifacts.filter(isSelectableOriginal).map(item=>item.id);setSelectedMediaIds(eligible.slice(0,100));setBatchNote(eligible.length>100?`حُدد أول 100 من ${eligible.length} نتيجة بالترتيب المعروض. حد الدفعة 100؛ عالجها ثم اختر دفعة أخرى. لم تُحدّد بقية النتائج.`:`حُددت النتائج المؤهلة وعددها ${eligible.length}.`);}} className="rounded-lg border bg-white px-3 py-2 text-xs font-bold">تحديد النتائج المؤهلة (حتى 100)</button>
        <p className="w-full text-xs text-slate-600">تحديد أصول معتمدة ومتاحة فقط، لا دليل جاهزية للنشر. يظهر الأصل حتى عند نقص ملفه كي تقرأ العائق. النسخ المشتقة والمواد غير المتاحة مستبعدة. حد الدفعة 100 مادة، مع حفظ ترتيبك بين الصفحات.</p>
        <span className="text-xs font-semibold text-slate-500" data-testid="media-selection-count">{eligibleSelectedCount} محدد</span>
        <button
          type="button"
          data-testid="create-telegram-media-drafts"
          disabled={!selectedReady || eligibleSelectedCount === 0 || batchMediaDrafts.isPending}
          onClick={() => batchMediaDrafts.mutate(selectedMediaIds)}
          className="rounded-xl bg-emerald-700 px-4 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:bg-emerald-300"
        >{batchMediaDrafts.isPending ? "جارٍ إنشاء المسودات..." : `إنشاء مسودات Telegram للمحدد (${eligibleSelectedCount})`}</button>
        <button type="button" disabled={!selectedReady || selectedMediaIds.length < 2 || selectedMediaIds.length > 10 || createAlbum.isPending} onClick={() => createAlbum.mutate()} className="rounded-xl bg-sky-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-40">إنشاء ألبوم من المحدد (2-10)</button>
        <button type="button" disabled={!selectedReady || selectedMediaIds.length !== 2 || createLivePhoto.isPending} onClick={() => createLivePhoto.mutate()} className="rounded-xl bg-violet-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-40">إنشاء صورة حية (صورة وفيديو)</button>
        {createLivePhoto.isError ? <p role="alert">{createLivePhoto.error.message}</p> : null}
        <p className="w-full text-xs">الألبوم:2-10عناصر،حتى100MiBإجمالاً. الصورة الحية:صورة وفيديوMP4حتى10ثوانٍ و10MiB. تُراجع العناصر ولا يرسلها التحديد وحده.</p>
        {createAlbum.isError ? <p role="alert">{createAlbum.error.message}</p> : null}
        {eligibleSelectedCount > 0 ? <button type="button" onClick={() => { setSelectedMediaIds([]); setBatchNote(""); }} className="text-sm font-bold text-slate-500 hover:text-slate-700">مسح التحديد</button> : null}
        <span className="w-full text-xs leading-5 text-slate-500">ينشئ مسودة نشر Telegram لكل وسيط معتمد محدد مع نص تعليقه للمراجعة؛ تجهيز فقط ولا يُنشر أو يُجدول شيء خارجيًا.</span>
        {batchNote ? <p role="status" className="w-full text-sm font-semibold text-emerald-800">{batchNote}</p> : null}
      </div> : null}
      {batchMediaDrafts.isError ? <p role="alert" className="text-sm text-rose-700">{batchMediaDrafts.error.message}</p> : null}
      {status === "APPROVED" && selectedMediaIds.length > 0 && selectedLoaded ? <fieldset disabled={!selectedReady}><BatchPlatformCopiesPanel ids={selectedMediaIds} items={allArtifacts} onPreparing={()=>setCopiesRevision(r=>r+1)}/><DistributionReadinessPanel key={copiesRevision} ids={selectedMediaIds} /><MetaBatchReviewPanel key={`meta:${copiesRevision}`} ids={selectedMediaIds} items={allArtifacts}/><TelegramBatchPreviewPanel ids={selectedMediaIds} copiesRevision={copiesRevision}/></fieldset> : null}
    </div>
    {artifacts.isLoading ? <p role="status" className="text-sm text-slate-500">تحميل المخرجات...</p> : null}
    {artifacts.isError ? <div role="alert" className="workspace-surface p-4 text-sm text-rose-700">تعذر تحميل المخرجات: {artifacts.error.message}<button className="workspace-secondary" onClick={()=>{void artifacts.refetch();if(requestedIds.length)void selectedItems.refetch();}}>إعادة قراءة مكتبة المحتوى</button><p>لا نعتبر فشل القراءة حذفاً للمادة.</p></div> : null}
    {!artifacts.isLoading && !artifacts.isError && filteredArtifacts.length === 0 ? <EmptyState title={allArtifacts.length === 0 ? "لا توجد مخرجات في هذه الحالة." : "لا توجد نتائج مطابقة للبحث أو الفلاتر الحالية."} /> : null}
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-slate-50 p-3"><p className="text-sm">افتح مادة للمراجعة والنسخ والخطط والسجل.</p><button type="button" onClick={()=>{setCompact(!compact);setFocusedId(null);}} className="rounded border bg-white p-2 text-xs font-bold">{compact?'فتح محررات جميع مواد الصفحة':'إغلاق المحررات والعودة للبطاقات'}</button></div>
    {requestedIds.length>0&&selectedItems.isFetching?<p role="status">جارٍ تحميل المواد المحددة والمرتبطة كاملةً...</p>:null}
    {requestedIds.length>0&&selectedItems.isError&&!focusedMissing?<div role="alert"><p>تعذر تحميل المواد المحددة أو المرتبطة. لا نستخدم بيانات مختصرة للمراجعة.</p><button onClick={()=>void selectedItems.refetch()}>إعادة تحميل المواد المحددة</button></div>:null}
    {focusedId?<section ref={materialNav} tabIndex={-1} aria-label="تنقل مساحة المادة" className="workspace-surface scroll-mt-24 space-y-3 p-4"><div className="flex flex-wrap items-center justify-between gap-3"><button className="workspace-secondary" onClick={returnToLibrary}>العودة إلى المكتبة</button><p className="text-sm">{focusIndex>=0?`المادة ${focusIndex+1} من ${filteredArtifacts.length} في النتائج الحالية`:"مادة مرتبطة بمعرّف مستقل"}</p><div className="flex flex-wrap gap-2"><button className="workspace-secondary" disabled={focusIndex<=0} onClick={()=>setFocusedId(filteredArtifacts[focusIndex-1].id)}>المادة السابقة</button><button className="workspace-secondary" disabled={focusIndex<0||focusIndex>=filteredArtifacts.length-1} onClick={()=>setFocusedId(filteredArtifacts[focusIndex+1].id)}>المادة التالية</button></div></div><p className="workspace-muted">التنقل لا يحفظ أو يعتمد أو ينشر. تعديلات الأصل ونسخ المنصات غير المحفوظة تبقى عند التنقل داخل المكتبة. مغادرة المكتبة أو إعادة تحميل الصفحة تفقدها؛ احفظها أولاً.</p>{focusedArtifact&&drafts[focusedArtifact.id]?.content!==undefined?<p role="status" className="text-sm text-amber-900">لهذه المادة تعديل غير محفوظ.</p>:null}{!artifacts.isLoading&&!artifacts.isError&&!selectedItems.isFetching&&(!selectedItems.isError||focusedMissing)&&!focusedArtifact?<div role="status"><h3 className="font-bold">لم تظهر المادة في الحالة المختارة</h3><p className="text-sm leading-7">قد تكون حالة المراجعة تغيرت أو الرابط غير مطابق. لم نحذف شيئاً. جرّب الحالة الأخرى أو ارجع إلى المكتبة.</p><bdi className="break-all text-xs">{focusedId}</bdi></div>:null}</section>:null}
    <div className={`grid min-w-0 items-start gap-3 ${pagedArtifacts.length>1&&!focusedId?'xl:grid-cols-2':''}`}>
      {displayArtifacts.map((artifact) => <article key={artifact.id} data-focused={focusedId===artifact.id} className="library-card min-w-0 space-y-3 rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          {artifact.metadata.source_type!=="PLATFORM_VARIANT"?<label className="text-xs"><input type="checkbox" aria-label={`تنظيم المخرج ${artifact.id}`} checked={catalogIds.includes(artifact.id)} disabled={!catalogIds.includes(artifact.id)&&catalogIds.length>=100} onChange={e=>setCatalogIds(ids=>e.target.checked?[...ids,artifact.id]:ids.filter(id=>id!==artifact.id))}/> فهرسة</label>:null}
          {status === "APPROVED" && isSelectableOriginal(artifact) ? <input
            type="checkbox"
            aria-label={`تحديد المخرج ${artifact.id}`}
            checked={selectedMediaIds.includes(artifact.id)}
            disabled={!selectedMediaIds.includes(artifact.id) && selectedMediaIds.length >= 100}
            onChange={(event) => toggleMediaSelection(artifact.id, event.target.checked)}
            className="mt-1 h-4 w-4 shrink-0 rounded border-slate-300"
          /> : null}
          <div className="min-w-0">
            <h3 className="text-sm font-extrabold text-slate-900" dir="auto">{artifactTitle(artifact)}</h3>
            <strong className="mt-0.5 block text-xs font-normal text-slate-400">{compact?(MEDIA_LABELS[artifact.kind]??({TEXT:"نص",QUIZ:"اختبار"} as Record<string,string>)[artifact.kind]??artifact.kind):`${artifact.kind} · ${artifact.mime_type??"نوع غير محدد"}`}</strong>
            <p className="mt-1 text-[11px] text-slate-400">المعرّف {artifact.id.slice(0, 8)}</p>
          </div>
          <span className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700">{artifact.metadata.source_type === "MEDIA_BANK_UPLOAD" ? "رفع يدوي" : artifact.metadata.source_type === "PLATFORM_VARIANT" ? `نسخة ${String(artifact.metadata.platform_label_ar ?? artifact.metadata.platform ?? "منصة")}${(artifact.metadata.constraints as Record<string, unknown> | undefined)?.trimmed ? " · مقصوصة للحد" : ""}` : "مخرج مولّد"}</span>
          {artifact.organization?.category?<Badge tone="sky">{artifact.organization.category}</Badge>:null}
          {artifactSeries(artifact) ? <Badge tone="sky">{artifactSeries(artifact)}</Badge> : null}
          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs">{({DRAFT:"قيد المراجعة",APPROVED:"معتمد",REJECTED:"مرفوض"})[artifact.review_status]??artifact.review_status}</span>
        </div>
        {compact?<div className="space-y-2">{focusedId!==artifact.id?<p dir="auto" className="line-clamp-3 whitespace-pre-wrap text-sm leading-7 text-slate-600">{artifact.content??String(artifact.metadata.caption??'ملف محفوظ في المكتبة')}</p>:null}<button id={`material-open-${artifact.id}`} type="button" aria-expanded={focusedId===artifact.id} onClick={()=>focusedId===artifact.id?returnToLibrary():setFocusedId(artifact.id)} className="library-card-primary rounded-lg px-4 py-2 text-sm font-bold focus:outline-2 focus:outline-offset-2 focus:outline-emerald-700">{focusedId===artifact.id?'إغلاق مساحة المادة':'فتح المادة والتجهيز والتتبع'}</button></div>:null}
        {!compact||focusedId===artifact.id?<div className="space-y-3" aria-label={`مساحة المادة ${artifact.id}`}>
        {artifact.metadata.source_type!=="PLATFORM_VARIANT"?<ContentOrganizationPanel key={artifact.id+":"+(artifact.organization?.version??0)} items={[artifact]}/>:null}
        <nav aria-label="مراحل العمل على المادة" className="flex flex-wrap gap-2 rounded bg-slate-50 p-2 text-xs text-slate-600"><a href={`#original-${artifact.id}`} className="underline">1. الأصل والملاحظات</a><a href={`#review-${artifact.id}`} aria-current={status==="DRAFT"?"step":undefined} className="underline">2. قرار المراجعة</a><a href={`#destinations-${artifact.id}`} aria-current={status==="APPROVED"?"step":undefined} className="underline">3. النسخ والوجهات والخطة</a><a href={`#history-${artifact.id}`} className="underline">4. سجل النشر</a></nav><div id={`original-${artifact.id}`} className="scroll-mt-24"/>
        <EditorialReviewNotes artifact={artifact}/>
        {(artifact.metadata.telegram_native as Record<string, unknown> | undefined)?.type === 'LIVE_LOCATION' ? <LiveLocationControls artifactId={artifact.id} /> : null}
        {artifact.metadata.telegram_live_photo ? <section className="rounded-xl border border-violet-200 bg-violet-50 p-3"><h4 className="font-bold">صورة حية،الصورة الثابتة ثم فيديو الحركة</h4><p className="text-xs">راجع الصورة أولاً، ثم فيديو الحركة أدناه، مع تعليق كل وسيط.</p><ol className="list-inside list-decimal space-y-1 text-sm">{(Array.isArray(artifact.metadata.live_photo_preview) ? artifact.metadata.live_photo_preview : []).map((value,index)=>{const item=value as {id:string;filename?:string;caption?:string};return <li key={item.id??index} className="break-words"><bdi dir="ltr" className="[overflow-wrap:anywhere]">{item.filename||`وسيط ${index+1}`}</bdi>{item.caption?<p dir="auto" className="whitespace-pre-wrap text-xs">{item.caption}</p>:null}</li>;})}</ol><details><summary className="text-xs">بيانات الصورة الحية التقنية</summary><pre dir="ltr" className="whitespace-pre-wrap break-all text-xs">{JSON.stringify(artifact.metadata.live_photo_preview, null, 2)}</pre></details>{(Array.isArray(artifact.metadata.live_photo_preview) ? artifact.metadata.live_photo_preview : []).map(value => <AlbumChildPreview key={(value as {id:string}).id} id={(value as {id:string}).id} />)}<p className="text-xs">يُرسلان كصورة حية واحدة،وليست ألبوماً أو فيديو منفرداً.</p></section> : null}
        {artifact.metadata.telegram_album ? <section className="rounded-xl border border-sky-200 bg-sky-50 p-3"><h4 className="font-bold">ألبوم Telegram،الترتيب والتعليقات المعتمدة</h4><p className="text-xs">ترتيب الوسائط أدناه هو ترتيب الألبوم المحفوظ. راجع كل وسيط وتعليقه قبل الاعتماد.</p><ol className="list-inside list-decimal space-y-1 text-sm">{(Array.isArray(artifact.metadata.album_preview) ? artifact.metadata.album_preview : []).map((value,index)=>{const item=value as {id:string;filename?:string;caption?:string};return <li key={item.id??index} className="break-words"><bdi dir="ltr" className="[overflow-wrap:anywhere]">{item.filename||`وسيط ${index+1}`}</bdi>{item.caption?<p dir="auto" className="whitespace-pre-wrap text-xs">{item.caption}</p>:null}</li>;})}</ol><details><summary className="text-xs">بيانات ترتيب الألبوم التقنية</summary><pre dir="ltr" className="whitespace-pre-wrap break-all text-xs">{JSON.stringify(artifact.metadata.album_preview, null, 2)}</pre></details><div className="grid gap-2 sm:grid-cols-2">{(Array.isArray(artifact.metadata.album_preview) ? artifact.metadata.album_preview : []).map((value) => { const item = value as { id: string }; return <AlbumChildPreview key={item.id} id={item.id} />; })}</div><p className="text-xs">الصور والفيديو معًا،أو صوت فقط،أو مستندات فقط. تتوقف العملية إذا تغيّر اعتماد أو محتوى أي عنصر.</p></section> : null}
        {artifact.metadata.telegram_native ? <NativeTelegramPreview value={artifact.metadata.telegram_native}/> : null}
        {compact && artifact.content !== null && status !== 'DRAFT' ? <section aria-label={`معاينة قراءة المخرج ${artifact.id}`} className="rounded-xl bg-slate-50 p-4"><h3 className="text-xs font-bold text-slate-500">الأصل للقراءة، تحرير النسخ أدناه</h3><p dir="auto" data-testid={`artifact-text-preview-${artifact.id}`} className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-words text-base leading-8">{artifact.content}</p></section> : artifact.content !== null ? <div className="grid gap-4 xl:grid-cols-2">
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
        <details open={!compact} className="rounded-xl border p-3"><summary className="cursor-pointer text-xs font-bold">الأصل والمعاينة وأدوات الإنتاج</summary>
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
        </details>
        <details open={!compact} className="rounded-xl border border-slate-200 p-3"><summary className="cursor-pointer text-xs font-bold">خيارات متقدمة: اشتقاق نسخة ومسودة من الأصل</summary>
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
          {!mediaDrafts[artifact.id] ? <button type="button" onClick={() => createMediaDraft.mutate(artifact.id)} disabled={createMediaDraft.isPending} className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-semibold text-white">{createMediaDraft.isPending ? "جارٍ إنشاء المسودة..." : "إنشاء مسودة Telegram من الأصل"}</button> : null}
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
        </details>
        {artifact.metadata.source_type === "PLATFORM_VARIANT" ? <section aria-label={`نسخة منصة ${artifact.id}`} className="space-y-2 rounded-xl border border-indigo-200 bg-indigo-50 p-4">
          <h4 className="font-bold">نسخة {String(artifact.metadata.platform_label_ar ?? artifact.metadata.platform)} مستقلة</h4>
          <p className="text-xs">تعديل النسخة لا يغيّر الأصل. احفظ التعديلات قبل الاعتماد. إعادة الاشتقاق لا تستبدل المسودة الموجودة.</p>
          {artifact.content === null ? <textarea aria-label={`تعليق نسخة المنصة ${artifact.id}`} value={drafts[artifact.id]?.content ?? String(artifact.metadata.caption ?? "")} onChange={e=>setDrafts(current=>({...current,[artifact.id]:{...current[artifact.id],content:e.target.value}}))} disabled={status!=="DRAFT"} dir="auto" className="min-h-40 w-full rounded border bg-white p-3" /> : null}
          <p className="text-xs">الحد: {String((artifact.metadata.constraints as Record<string,unknown>)?.max_text ?? "غير محدد")} · القياس: {String((artifact.metadata.constraints as Record<string,unknown>)?.measure ?? "")} · الحالي: {variantLength(artifact, drafts[artifact.id]?.content)}</p>
          {artifact.content === null && status === "DRAFT" ? <button type="button" onClick={()=>save.mutate(artifact.id)} disabled={save.isPending} className="rounded border bg-white p-2">حفظ تعليق النسخة</button> : null}
          {drafts[artifact.id]?.content !== undefined && drafts[artifact.id]?.content !== (artifact.content ?? String(artifact.metadata.caption ?? "")) ? <p role="status" className="text-sm">توجد تعديلات غير محفوظة؛ احفظها قبل الاعتماد.</p> : null}
        </section> : null}
        {artifact.metadata.source_type === "PLATFORM_VARIANT" && variantLength(artifact, drafts[artifact.id]?.content) > Number((artifact.metadata.constraints as Record<string,unknown>)?.max_text ?? Infinity) ? <p role="alert" className="text-sm text-rose-700">تجاوزت النسخة حد المنصة. قصّر النص قبل الحفظ والاعتماد.</p> : null}
        <section id={`review-${artifact.id}`} aria-label="قرار مراجعة المادة" className="scroll-mt-24 space-y-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4"><h4 className="font-bold">الخطوة التالية: {status==="DRAFT"?"راجع الأصل ثم اعتمد المادة":"المادة معتمدة، اختر وجهاتها وافحص متطلباتها"}</h4><p className="text-xs leading-6">اعتماد المادة يثبت مراجعتها فقط، ولا ينشرها. اختر الوجهات بعد المراجعة؛ إذن التنفيذ منفصل.</p>        {status==='DRAFT'?<input aria-label={`ملاحظة مراجعة المخرج ${artifact.id}`} value={drafts[artifact.id]?.review_note ?? artifact.review_note ?? ""} onChange={(event) => setDrafts((current) => ({ ...current, [artifact.id]: { ...current[artifact.id], review_note: event.target.value } }))} placeholder="ملاحظة المراجعة أو سبب الرفض" disabled={status !== "DRAFT"} className="w-full rounded-xl border p-3 text-sm"/>:null}
        {status === "DRAFT" ? <div className="flex flex-wrap gap-2">
          {(artifact.content !== null || typeof artifact.metadata.caption === "string") ? <button type="button" onClick={() => save.mutate(artifact.id)} disabled={save.isPending} className="rounded-lg border px-3 py-2 text-sm font-semibold">حفظ التعديل</button> : null}
          <button type="button" onClick={() => approve.mutate(artifact.id)} disabled={approve.isPending || drafts[artifact.id]?.content !== undefined && drafts[artifact.id]?.content !== (artifact.content ?? String(artifact.metadata.caption ?? ""))} className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white">اعتماد المادة فقط، دون نشر</button>
          <button type="button" onClick={() => reject.mutate(artifact.id)} disabled={reject.isPending || !(drafts[artifact.id]?.review_note ?? "").trim()} className="rounded-lg bg-rose-600 px-3 py-2 text-sm font-semibold text-white">رفض المخرج</button>
        </div> : null}</section>
        {artifact.metadata.source_type !== "PLATFORM_VARIANT" ? <div id={`destinations-${artifact.id}`} className="scroll-mt-24"><DistributionReadinessPanel ids={[artifact.id]} onReview={platform=>setCopyRequests(current=>({...current,[artifact.id]:{platform,nonce:Date.now()}}))} /></div> : null}
          {artifact.review_status === "APPROVED" && artifact.metadata.source_type !== "PLATFORM_VARIANT" ? <CentralPlatformCopiesPanel draftCache={copyDrafts.current} id={artifact.id} kind={artifact.kind} request={copyRequests[artifact.id]} onPlan={() => {setSelectedMediaIds([artifact.id]); requestAnimationFrame(() => document.querySelector('[aria-label="معاينة دفعة Telegram"]')?.scrollIntoView({behavior:'smooth',block:'start'}));}} /> : null}
        <div id={`history-${artifact.id}`} className="scroll-mt-24"><ArtifactPublicationLedger id={artifact.id} /></div>

        <details className="text-xs text-slate-500"><summary>تفاصيل تقنية للمادة</summary><p className="break-all">عقد المخرج: {artifact.output_contract_key ?? "غير محدد"} · الإصدار {artifact.output_contract_version ?? "—"}</p></details>
        {typeof artifact.metadata.caption === "string" ? <><p dir="auto" className="min-w-0 whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm leading-7 text-slate-800 [overflow-wrap:anywhere]">{String(artifact.metadata.caption)}</p>{status === "DRAFT" && artifact.content === null && artifact.metadata.source_type !== "PLATFORM_VARIANT" ? <label className="block text-sm">تعديل تعليق الوسيط<textarea rows={7} aria-label={`تعليق الوسيط ${artifact.id}`} value={drafts[artifact.id]?.content ?? artifact.metadata.caption} onChange={e=>setDrafts(current=>({...current,[artifact.id]:{...current[artifact.id],content:e.target.value}}))} className="block w-full rounded border p-3" dir="auto"/></label> : null}</> : null}
        {artifact.metadata.video_library && typeof artifact.metadata.video_library === "object" ? <details className="space-y-3 rounded-xl border border-indigo-100 bg-indigo-50 p-4">
          <summary className="cursor-pointer text-sm font-bold text-indigo-900">النص الأصلي ونسخ المنصات</summary>
          {([
            ["tiktok_text", "وصف تيك توك الكامل"],
            ["telegram_caption", "تعليق Telegram المقترح"],
          ] as const).map(([key, label]) => <section key={key} className="mt-3 space-y-1">
            <h4 className="text-xs font-bold text-indigo-900">{label}</h4>
            <p dir="auto" className="max-h-80 overflow-y-auto whitespace-pre-wrap break-words rounded-lg bg-white p-3 text-sm leading-7 text-slate-800">{String((artifact.metadata.video_library as Record<string, unknown>)[key] ?? "")}</p>
          </section>)}
          <p className="mt-3 text-xs leading-6 text-indigo-800">نسخ منفصلة للمراجعة. حفظها لا يغيّر تعليق النشر الحالي ولا ينشر شيئاً. تعليمات التحرير محفوظة مع الأصل ولا تضاف تلقائياً إلى نسخ المنصات.</p>
        </details> : null}
        

        </div>:null}
      </article>)}
    </div>
    {!focusedId&&pageCount > 1 ? <nav className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white p-3" aria-label="ترقيم صفحات المخرجات">
      <button type="button" onClick={() => {setFocusedId(null);setPage((current) => Math.max(0, current - 1));}} disabled={safePage === 0} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-bold text-slate-600 disabled:opacity-40">السابق</button>
      <span className="text-xs font-semibold text-slate-500">صفحة {safePage + 1} من {pageCount} · عرض {pagedArtifacts.length} من {filteredArtifacts.length}</span>
      <button type="button" onClick={() => {setFocusedId(null);setPage((current) => Math.min(pageCount - 1, current + 1));}} disabled={safePage >= pageCount - 1} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-bold text-slate-600 disabled:opacity-40">التالي</button>
    </nav> : null}
    <details id="library-create-tools" open={!compact||Boolean(creationTask)} className="workspace-disclosure space-y-3 p-4">
      <summary className="cursor-pointer text-sm font-bold text-slate-600">إنشاء نص أو اختبار · رفع وسيط · اشتقاق نسخة منصة · بطاقة تصميم</summary>
      <div className="mt-3 space-y-3">
      <nav aria-label="تغيير مهمة الإنشاء" className="flex flex-wrap gap-2">{[["نص أو اختبار","manual"],["رفع وسيط","upload"],["نسخة منصة","variant"],["بطاقة تصميم","design"]].map(([label,key])=><button type="button" key={key} aria-pressed={(creationTask??"manual")===key} className="workspace-secondary" onClick={()=>chooseCreationTask(key)}>{label}</button>)}</nav>
      <p className="text-sm leading-7 text-slate-600">تظهر أداة المهمة المختارة فقط. يمكنك تغييرها دون إرسال أو اعتماد محتوى. تبقى المدخلات أثناء التنقل هنا، لكنها لا تُحفظ عند إعادة تحميل الصفحة حتى تحفظ المسودة.</p>
    <div hidden={(creationTask??"manual")!=="manual"} className="space-y-3 rounded-xl border border-emerald-100 bg-emerald-50/50 p-4">
      <h3 tabIndex={-1} id="library-task-manual" className="scroll-mt-24 font-bold">نص أو اختبار تفاعلي</h3>
      <select aria-label="نوع المسودة اليدوية" value={manualKind} onChange={e => { setManualKind(e.target.value); if (NATIVE_TEMPLATES[e.target.value]) setNativeJson(JSON.stringify(blankNative(e.target.value), null, 2)); }} className="w-full rounded-lg border p-2"><option value="TEXT">نص</option><option value="QUIZ">اختبار</option><option value="POLL">استطلاع</option><option value="LOCATION">موقع</option><option value="LIVE_LOCATION">موقع حي محدود المدة</option><option value="VENUE">مكان</option><option value="CONTACT">جهة اتصال</option><option value="DICE">نرد تفاعلي</option></select>
      <input aria-label="عنوان المسودة اليدوية" value={manualTitle} onChange={e => setManualTitle(e.target.value)} placeholder="عنوان داخلي" className="w-full rounded-lg border p-2" />
      <textarea aria-label="نص المسودة اليدوية" value={manualContent} onChange={e => setManualContent(e.target.value)} placeholder={manualKind === "QUIZ" ? "سؤال الاختبار" : "النص الكامل"} className="min-h-32 w-full rounded-lg border p-2" />
      {NATIVE_TEMPLATES[manualKind] ? <p className="text-sm leading-7">العنوان والنص أعلاه وصف داخلي للمراجعة، وليس رسالة إضافية. تفاصيل Telegram أدناه هي المحتوى الذي سيُراجع للإرسال.</p> : null}
      {NATIVE_TEMPLATES[manualKind] ? <NativeTelegramFields key={manualKind} kind={manualKind} value={nativeJson} onChange={setNativeJson}/> : null}
      {manualKind === "QUIZ" ? <><textarea aria-label="خيارات الاختبار" value={quizOptions} onChange={e => setQuizOptions(e.target.value)} placeholder="كل خيار في سطر" className="w-full rounded-lg border p-2" /><label className="block">رقم الإجابة الصحيحة بدءاً من1<input aria-label="رقم الإجابة الصحيحة" type="number" min="1" value={quizAnswer + 1} onChange={e => setQuizAnswer(Number(e.target.value) - 1)} className="mx-2 rounded border p-2" /></label></> : null}
      <button type="button" onClick={() => createManual.mutate()} disabled={!manualTitle.trim() || !manualContent.trim() || Boolean(NATIVE_TEMPLATES[manualKind]&&nativeError(nativeJson)) || createManual.isPending} className="rounded-lg bg-indigo-700 px-3 py-2 text-white">حفظ مسودة للمراجعة</button>
      {createManual.isError ? <p role="alert" className="text-rose-700">{createManual.error.message}</p> : null}
      {createManual.isSuccess ? <p role="status">حُفظت المسودة،لا نشر ولا اعتماد تلقائي.</p> : null}
    </div>
    <div hidden={creationTask!=="upload"} className="space-y-3 rounded-xl border border-emerald-100 bg-emerald-50/50 p-4">
      <h3 tabIndex={-1} id="library-task-upload" className="scroll-mt-24 border-t pt-4 font-bold">بنك الوسائط الجاهزة</h3>
      <p className="text-sm text-slate-600">اختر نوع إرسال Telegram صراحةً للصوت والملفات والملصقات. كل رفع يدخل قيد المراجعة. حد Telegram: الصور10MiB، وبقية الملفات50MiB. الأصل محفوظ؛ تعليق النشر محدود1024حرفاً، ولا تعليق للملصق أو الفيديو الدائري.</p>
      <label className="block text-sm font-semibold">نوع الإرسال
        <select aria-label="نوع الوسيط المرفوع" value={uploadKind} onChange={e => setUploadKind(e.target.value)} className="mt-1 w-full rounded-lg border bg-white p-2">
          <option value="">تلقائي:صورة أوMP4</option>
          {Object.entries(MEDIA_LABELS).map(([k,v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </label>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="text-sm font-semibold">ملف الوسيط
          <input ref={uploadInput} aria-label="ملف الوسيط الجاهز" type="file" onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)} className="mt-1 w-full max-w-full rounded-lg border bg-white p-2 font-normal" />
        </label>
        <label className="text-sm font-semibold">التعليق (يظهر نصًا مع الوسيط عند النشر)
          <textarea rows={5} aria-label="تعليق الوسيط الجاهز" value={uploadCaption} onChange={(event) => setUploadCaption(event.target.value)} className="mt-1 w-full rounded-lg border bg-white p-2 font-normal" placeholder="نص يرافق الوسيط عند النشر" />
        </label>
      </div>
      <button type="button" onClick={() => ingestMedia.mutate()} disabled={!uploadFile || ingestMedia.isPending} className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-semibold text-white">{ingestMedia.isPending ? "جارٍ الرفع..." : "رفع إلى بنك الوسائط"}</button>
      {ingestMedia.isError ? <p role="alert" className="text-sm text-rose-700">{ingestMedia.error.message}</p> : null}
      {ingestMedia.isSuccess ? <p role="status" className="text-sm text-emerald-800">تم الرفع؛ الوسيط الآن قيد المراجعة.</p> : null}
    </div>
    <div hidden={creationTask!=="variant"} className="space-y-3 rounded-xl border border-sky-100 bg-sky-50/50 p-4">
      <h3 tabIndex={-1} id="library-task-variant" className="scroll-mt-24 font-bold">اشتقاق نسخة بحدود منصة من منشور معتمد</h3>
      <p className="text-sm text-slate-600">ينشئ نسخة مراجعة منفصلة من منشور تحريري معتمد. يحتفظ بالنص؛ إذا تجاوز حد المنصة يرفض الطلب بسبب واضح، ولا يقصه تلقائياً. قد تبقى نسخ قديمة مقصوصة وموسومة بذلك، ولا نستبدلها. هذا المسار لا يختار وجهات النشر. لمواد مكتبة المحتوى استخدم النسخ والوجهات داخل المادة. لا يُنشر شيء خارجيًا.</p>
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
      <div hidden={creationTask!=="design"} tabIndex={-1} id="library-task-design" className="scroll-mt-24">{designCard}</div>
      </div>
    </details>
    {jobStatus}
    {mutationError}
  </section>;
}
