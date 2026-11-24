import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router";
import { useEffect, useMemo, useState } from "react";
import { postsApi } from "../../shared/api/postsApi";
import { genericArtifactsApi, type PlatformVariantDraft } from "../../shared/api/artifactsApi";
import { schedulesApi, type ScheduleDetail } from "../../shared/api/schedulesApi";
import { toggleSelection, selectionFromQuery } from "../../shared/utils/selection";
import { localDateTimeToUtcISOString, utcISOStringToLocalDateTime } from "../../shared/utils/timezone";
import { TelegramPreview } from "../post-bank/PostBankPage";
import {UnifiedPublishingQueue} from "./UnifiedPublishingQueue";
import { PageHeader } from "../../shared/components/ui";

const DEFAULT_TIMEZONE = "Asia/Aden";
const PAGE_SIZE = 20;
type Section = "ready" | "plans" | "calendar" | "platforms";

export function PublishingPage() {
  const client = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [section, setSection] = useState<Section>(searchParams.get("schedule_id")?"plans":"ready");
  const [selectedIds, setSelectedIds] = useState<string[]>(() => selectionFromQuery(searchParams.get("selected_post_ids")));
  const [scheduleOpen, setScheduleOpen] = useState(Boolean(searchParams.get("selected_post_ids")));
  const [message, setMessage] = useState("");
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [visualArtifactSelections, setVisualArtifactSelections] = useState<Record<string, string>>({});
  const [visualPreviewUrls, setVisualPreviewUrls] = useState<Record<string, string>>({});
  const [detail, setDetail] = useState<ScheduleDetail | null>(null);
  const [itemTimes, setItemTimes] = useState<Record<string,string>>({});
  const [readyQuery, setReadyQuery] = useState("");
  const [readySort, setReadySort] = useState<"created" | "title" | "kind" | "topic">("created");
  const [readySourceId, setReadySourceId] = useState("");
  const [readyKind, setReadyKind] = useState("");
  const [readyPage, setReadyPage] = useState(0);
  const [planQuery, setPlanQuery] = useState("");
  const [planStatus, setPlanStatus] = useState("");
  const [planPage, setPlanPage] = useState(0);
  const [calendarDate, setCalendarDate] = useState(new Date().toISOString().slice(0, 10));
  const [manualPub, setManualPub] = useState<{ id: string; date: string; url: string } | null>(null);
  const [form, setForm] = useState({ name: "خطة نشر", timezone: DEFAULT_TIMEZONE, startAt: "", interval: "60" });

  const posts = useQuery({
    queryKey: ["publishing", "eligible-posts", readyQuery, readySort, readySourceId, readyKind, readyPage],
    queryFn: () => postsApi.list({
      status: "APPROVED",
      publicationState: "ELIGIBLE",
      sourceId: readySourceId || undefined,
      kind: readyKind || undefined,
      query: readyQuery.trim() || undefined,
      sort: readySort,
      limit: PAGE_SIZE,
      offset: readyPage * PAGE_SIZE,
    }),
    placeholderData: (previous) => previous,
  });
  const approvedImages = useQuery({
    queryKey: ["publishing", "approved-image-artifacts"],
    queryFn: async () => (await genericArtifactsApi.listAll("APPROVED")).items.filter(
      (artifact) => artifact.kind === "IMAGE" && artifact.status === "AVAILABLE" && Boolean(artifact.storage_uri) && ["image/png", "image/jpeg", "image/webp"].includes(artifact.mime_type ?? ""),
    ),
  });
  const readyFilterOptions = useQuery({
    queryKey: ["publishing", "filter-options", readySourceId],
    queryFn: () => postsApi.filterOptions(readySourceId || undefined, "ELIGIBLE"),
  });
  const schedules = useQuery({ queryKey: ["publishing", "schedules"], queryFn: schedulesApi.list });
  const upcoming = useQuery({ queryKey: ["publishing", "upcoming"], queryFn: schedulesApi.upcoming });
  const platformVariants = useQuery({ queryKey: ["publishing", "platform-variants"], queryFn: genericArtifactsApi.listPlatformVariants });
  const calendar = useQuery({
    queryKey: ["publishing", "calendar", calendarDate, DEFAULT_TIMEZONE],
    queryFn: () => schedulesApi.calendar(calendarDate, DEFAULT_TIMEZONE),
  });

  const eligibility = useMutation({ mutationFn: () => schedulesApi.eligibility(selectedIds) });
  const recordManual = useMutation({
    mutationFn: (input: { id: string; published_at: string; external_url: string | null }) =>
      genericArtifactsApi.recordManualPublication(input.id, { published_at: input.published_at, external_url: input.external_url }),
    onSuccess: () => {
      setManualPub(null);
      void client.invalidateQueries({ queryKey: ["publishing", "platform-variants"] });
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : "تعذر تسجيل النشر اليدوي."),
  });

  const variantGroups = useMemo(() => {
    const items = platformVariants.data ?? [];
    return {
      drafts: items.filter((v) => !v.manual_publication && v.review_status === "DRAFT"),
      approved: items.filter((v) => !v.manual_publication && v.review_status === "APPROVED"),
      published: items.filter((v) => Boolean(v.manual_publication)),
      rejected: items.filter((v) => !v.manual_publication && v.review_status === "REJECTED"),
    };
  }, [platformVariants.data]);

  const submitManualPublication = (id: string) => {
    if (!manualPub || manualPub.id !== id || !manualPub.date) return;
    const publishedAt = new Date(`${manualPub.date}T12:00:00`).toISOString();
    const url = manualPub.url.trim();
    recordManual.mutate({ id, published_at: publishedAt, external_url: url ? url : null });
  };
  const attachVisual = useMutation({
    mutationFn: ({ postId, artifactId }: { postId: string; artifactId: string }) => postsApi.attachVisualArtifact(postId, artifactId),
    onSuccess: async () => {
      setMessage("تم إرفاق التصميم المعتمد بالمنشور. سيستخدمه مسار النشر الحالي بعد إعادة التحقق من اعتماده.");
      await refresh();
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : "تعذر إرفاق التصميم."),
  });
  const detachVisual = useMutation({
    mutationFn: (postId: string) => postsApi.detachVisualArtifact(postId),
    onSuccess: async () => {
      setMessage("تم فصل التصميم عن المنشور دون تغيير اعتماد النص.");
      await refresh();
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : "تعذر فصل التصميم."),
  });

  const createSchedule = useMutation({
    mutationFn: () => {
      if (!form.startAt) throw new Error("حدد وقت بداية صالح.");
      return schedulesApi.create({
        name: form.name.trim(),
        timezone: form.timezone.trim(),
        post_ids: selectedIds,
        start_at: localDateTimeToUtcISOString(form.startAt, form.timezone),
        interval_minutes: Number(form.interval),
        idempotency_key: crypto.randomUUID(),
      });
    },
    onSuccess: async (schedule) => {
      setMessage(`تم إنشاء الخطة بنجاح: ${schedule.name}`);
      setScheduleOpen(false);
      setSection("plans");
      setDetail(await schedulesApi.get(schedule.id));
      void refresh();
    },
  });
  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["publishing", "schedules"] }),
      client.invalidateQueries({ queryKey: ["publishing", "upcoming"] }),
      client.invalidateQueries({ queryKey: ["publishing", "calendar"] }),
      client.invalidateQueries({ queryKey: ["publishing", "eligible-posts"] }),
    ]);
  };
  const action = useMutation({
    mutationFn: ({ type, id }: { type: "activate" | "pause" | "cancel" | "retry"; id: string }) =>
      type === "activate"
        ? schedulesApi.activate(id)
        : type === "pause"
          ? schedulesApi.pause(id)
          : type === "cancel"
            ? schedulesApi.cancel(id)
            : schedulesApi.retryFailed(id).then((r) => r.schedule),
    onSuccess: (data) => {
      setDetail(data);
      setMessage(`تم تنفيذ العملية. حالة الخطة: ${data.status}`);
      void refresh();
    },
  });
  const openDetail = async (id: string) => {
    try {
      setDetail(await schedulesApi.get(id));
      setSection("plans");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "تعذر تحميل الخطة.");
    }
  };
  const linkedScheduleId=searchParams.get('schedule_id');
  useEffect(()=>{
    if(!linkedScheduleId)return;
    let active=true;
    void schedulesApi.get(linkedScheduleId).then(value=>{if(active){setDetail(value);setSection('plans');}}).catch(error=>{if(active)setMessage(error instanceof Error?error.message:'تعذر تحميل الخطة.');});
    return ()=>{active=false;};
  },[linkedScheduleId]);
  const setSelection = (id: string, checked: boolean) => {
    const next = toggleSelection(selectedIds, id, checked);
    setSelectedIds(next);
    setSearchParams(next.length ? { selected_post_ids: next.join(",") } : {});
  };
  const togglePageSelection = (checked: boolean) => {
    const ids = posts.data?.items.map((post) => post.post_id) ?? [];
    setSelectedIds((current) => checked ? Array.from(new Set([...current, ...ids])) : current.filter((id) => !ids.includes(id)));
    const next = checked ? Array.from(new Set([...selectedIds, ...ids])) : selectedIds.filter((id) => !ids.includes(id));
    setSearchParams(next.length ? { selected_post_ids: next.join(",") } : {});
  };
  const openSchedule = async () => {
    if (!selectedIds.length) return;
    try {
      const result = await eligibility.mutateAsync();
      const blocked = new Set(result.blocked.map((r) => r.post_id));
      const eligible = selectedIds.filter((id) => !blocked.has(id));
      setSelectedIds(eligible);
      setSearchParams(eligible.length ? { selected_post_ids: eligible.join(",") } : {});
      setScheduleOpen(Boolean(eligible.length));
      if (result.blocked.length) setMessage(`تم استبعاد ${result.blocked.length} منشور غير قابل للنشر.`);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "تعذر فحص أهلية النشر.");
    }
  };
  const updateItemTime = async (itemId: string, value: string) => {
    if (!detail) return;
    try {
      setDetail(await schedulesApi.updateItemTime(detail.id, itemId, localDateTimeToUtcISOString(value, detail.timezone)));
      setItemTimes(current=>{const next={...current};delete next[itemId];return next;});
      setMessage("تم تحديث وقت العنصر.");
      void refresh();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "تعذر تحديث الوقت.");
    }
  };
  const preview = async (postId: string) => {
    try {
      const p = await schedulesApi.telegramPreview(postId);
      setPreviewContent(p.content);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "تعذر تحميل معاينة Telegram.");
    }
  };

  const previewVisual = async (postId: string, artifactId: string) => {
    try {
      const media = await genericArtifactsApi.mediaUrl(artifactId);
      setVisualPreviewUrls((current) => ({ ...current, [postId]: media.url }));
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "تعذر تحميل معاينة التصميم المخزن.");
    }
  };

  const readyItems = posts.data?.items ?? [];
  const readyTotal = posts.data?.total ?? 0;
  const readyPageCount = Math.max(1, Math.ceil(readyTotal / PAGE_SIZE));
  const readyPageIds = readyItems.map((post) => post.post_id);
  const allReadySelected = readyPageIds.length > 0 && readyPageIds.every((id) => selectedIds.includes(id));
  const planItems = useMemo(() => {
    const query = planQuery.trim().toLowerCase();
    return (schedules.data?.items ?? []).filter((schedule) => {
      const matchesQuery = !query || schedule.name.toLowerCase().includes(query) || schedule.timezone.toLowerCase().includes(query);
      const matchesStatus = !planStatus || schedule.status === planStatus;
      return matchesQuery && matchesStatus;
    });
  }, [planQuery, planStatus, schedules.data?.items]);
  const planPageCount = Math.max(1, Math.ceil(planItems.length / PAGE_SIZE));
  const visiblePlans = planItems.slice(planPage * PAGE_SIZE, (planPage + 1) * PAGE_SIZE);

  const switchSection = (next: Section) => {
    setSection(next);
    if (next !== "plans") setDetail(null);
  };

  if (posts.isLoading && !posts.data) return <Status title="جاري تحميل المنشورات الجاهزة" />;
  if (posts.isError && !posts.data) return <Status title="تعذر تحميل المنشورات" detail={posts.error.message} error />;

  return (
    <section data-testid="publishing-workspace" className="space-y-6">
      <PageHeader
        eyebrow="مساحة العمل"
        title="مساحة النشر"
        description="منطقة مرتبة للجاهز، خطط النشر، والتقويم. كل خطوة تظهر عندما تكون منطقية للحالة الحالية."
        actions={<Link to="/bank" className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-600 hover:bg-slate-50">العودة إلى بنك المحتوى</Link>}
      />

      <div className="rounded-xl border border-sky-200 bg-sky-50 p-4 text-sm leading-7"><p>الصور والفيديوهات والنصوص المستوردة تُجهز من المكتبة. الخطط المحفوظة منها تظهر هنا في «خطط النشر». قائمة المحتوى الموحدة أدناه تجمع المعتمد وتفصل حالته عن أدوات جدولة المنشورات التحريرية.</p><Link to="/bank?artifact_status=APPROVED" className="font-bold text-indigo-700 underline">فتح مكتبة المخرجات المعتمدة والتجهيز</Link></div>
      <nav aria-label="أقسام مساحة النشر" className="grid gap-2 rounded-2xl border bg-slate-50 p-2 sm:grid-cols-2 lg:grid-cols-4">
        {([
          ["ready", "المحتوى والتجهيز", "↗", "قائمة موحدة، ثم أدوات جدولة النصوص"],
          ["plans", "خطط النشر", schedules.data?.total ?? schedules.data?.items.length ?? 0, "الخطط المحفوظة وحالاتها"],
          ["calendar", "التقويم", upcoming.data?.items.length ?? 0, "القادم وجدول اليوم"],
          ["platforms", "مسودات المنصات", platformVariants.data?.length ?? 0, "تحضير يدوي فقط، بلا نشر آلي"],
        ] as const).map(([key, label, count, hint]) => (
          <button key={key} type="button" onClick={() => switchSection(key)} className={`rounded-xl p-4 text-right transition ${section === key ? "bg-white shadow-sm ring-1 ring-indigo-200" : "hover:bg-white"}`}>
            <div className="flex items-center justify-between gap-3"><strong>{label}</strong><span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-bold">{count}</span></div>
            <span className="mt-1 block text-xs text-slate-500">{hint}</span>
          </button>
        ))}
      </nav>

      {message && <div role="status" className="whitespace-pre-wrap rounded-xl border bg-indigo-50 p-4 text-sm">{message}</div>}
      {previewContent !== null && <div className="rounded-2xl border bg-white p-4 shadow-sm"><TelegramPreview content={previewContent} onClose={() => setPreviewContent(null)} /></div>}

      {section === "ready" && (
        <section className="space-y-4" data-testid="publishing-ready">
          <UnifiedPublishingQueue/>
          <div className="rounded-2xl border bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div><h3 className="text-xl font-bold">جدولة المنشورات التحريرية المؤهلة</h3><p className="mt-1 text-sm text-slate-500">لا يظهر هنا إلا ما هو معتمد ومؤهل للنشر.</p></div>
              <span data-testid="selection-count" className="rounded-full bg-indigo-50 px-3 py-1 text-sm font-bold text-indigo-700">{selectedIds.length} محدد</span>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2 lg:grid-cols-[1fr_220px_220px_220px_auto]">
              <label className="text-sm font-semibold"><span className="sr-only">بحث المنشورات الجاهزة</span><input aria-label="بحث المنشورات الجاهزة" value={readyQuery} onChange={(e) => { setReadyQuery(e.target.value); setReadyPage(0); }} placeholder="ابحث في العنوان أو النص..." className="w-full rounded-xl border p-3 font-normal" /></label>
              <label className="text-sm font-semibold">الكتاب<select aria-label="كتاب المنشورات الجاهزة" value={readySourceId} onChange={(e) => { setReadySourceId(e.target.value); setReadyKind(""); setReadyPage(0); }} className="mt-2 w-full rounded-xl border p-3 font-normal"><option value="">كل الكتب المتاحة</option>{(readyFilterOptions.data?.sources ?? []).map((source) => <option key={source.id} value={source.id}>{source.title}</option>)}</select></label>
              <label className="text-sm font-semibold">نوع المحتوى<select aria-label="نوع المنشورات الجاهزة" value={readyKind} onChange={(e) => { setReadyKind(e.target.value); setReadyPage(0); }} className="mt-2 w-full rounded-xl border p-3 font-normal"><option value="">كل الأنواع المتاحة</option>{(readyFilterOptions.data?.kinds ?? []).map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
              <label className="text-sm font-semibold">الفرز<select aria-label="فرز المنشورات الجاهزة" value={readySort} onChange={(e) => { setReadySort(e.target.value as typeof readySort); setReadyPage(0); }} className="mt-2 w-full rounded-xl border p-3 font-normal"><option value="created">الأحدث أولًا</option><option value="title">العنوان: أ - ي</option><option value="kind">النوع</option><option value="topic">المحور</option></select></label>
              <button type="button" onClick={() => { setReadyQuery(""); setReadySourceId(""); setReadyKind(""); setReadySort("created"); setReadyPage(0); setSelectedIds([]); setSearchParams({}); }} className="rounded-xl border px-4 py-3 text-sm font-semibold">مسح الفلاتر</button>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              {allReadySelected
                ? <button type="button" onClick={() => togglePageSelection(false)} className="rounded-xl border px-3 py-2 text-sm font-semibold">إلغاء تحديد الصفحة</button>
                : <button type="button" onClick={() => togglePageSelection(true)} disabled={!readyItems.length} className="rounded-xl border px-3 py-2 text-sm font-semibold disabled:opacity-40">تحديد الصفحة</button>}
              {selectedIds.length > 0 && <button type="button" onClick={() => { setSelectedIds([]); setSearchParams({}); }} className="rounded-xl border px-3 py-2 text-sm">مسح التحديد</button>}
              {selectedIds.length > 0 && <button data-testid="create-plan" type="button" onClick={() => void openSchedule()} disabled={eligibility.isPending} className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-40">إنشاء خطة ({selectedIds.length})</button>}
            </div>
          </div>

          {readyItems.length === 0
            ? <div className="rounded-2xl border border-dashed bg-white p-10 text-center"><h3 className="font-bold">لا توجد منشورات جاهزة</h3><p className="mt-2 text-sm text-slate-500">جرّب تغيير عبارة البحث، أو عد إلى بنك المحتوى لاعتماد منشورات جديدة.</p></div>
            : <div className="space-y-3">{readyItems.map((post) => {
              const matchingImages = (approvedImages.data ?? []).filter((image) => image.source_knowledge_unit_id === post.knowledge_unit_id);
              return <article key={post.post_id} className="rounded-2xl border bg-white p-4 shadow-sm" data-testid={`ready-post-${post.post_id}`}>
                <label className="flex cursor-pointer items-start gap-3">
                  <input aria-label={`تحديد ${post.title}`} type="checkbox" checked={selectedIds.includes(post.post_id)} onChange={(e) => setSelection(post.post_id, e.target.checked)} className="mt-1 h-4 w-4"/>
                  <span className="min-w-0"><strong className="block">{post.title}</strong><span className="mt-1 block text-xs text-slate-500">{post.source_title}</span><p className="mt-2 text-sm leading-7 text-slate-600">{post.content_preview}</p></span>
                </label>
                <div className="mt-4 rounded-xl border border-dashed p-3">
                  {post.visual_artifact_id ? <>
                    <p className="text-sm font-semibold text-emerald-700">تصميم معتمد مرفق</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <button type="button" className="rounded-lg border px-3 py-2 text-sm" onClick={() => void previewVisual(post.post_id, post.visual_artifact_id!)}>معاينة التصميم المخزن</button>
                      <button type="button" className="rounded-lg border px-3 py-2 text-sm" disabled={detachVisual.isPending} onClick={() => detachVisual.mutate(post.post_id)}>فصل التصميم</button>
                    </div>
                    {visualPreviewUrls[post.post_id] && <img src={visualPreviewUrls[post.post_id]} alt="معاينة التصميم المعتمد" className="mt-3 max-h-96 rounded-lg border object-contain"/>}
                  </> : <>
                    <label className="block text-sm font-semibold">إرفاق تصميم بصري معتمد
                      <select aria-label={`تصميم معتمد لـ ${post.title}`} className="mt-2 block w-full rounded-lg border p-2 font-normal" value={visualArtifactSelections[post.post_id] ?? ""} onChange={(event) => setVisualArtifactSelections((current) => ({ ...current, [post.post_id]: event.target.value }))}>
                        <option value="">اختر تصميمًا اختياريًا</option>
                        {matchingImages.map((image) => <option key={image.id} value={image.id}>{String(image.metadata.title ?? image.id)} · {image.mime_type}</option>)}
                      </select>
                    </label>
                    {matchingImages.length === 0 && <p className="mt-2 text-xs text-slate-500">لا توجد صور معتمدة لهذه المادة. اعتماد النص وحده لا يرفق صورة.</p>}
                    <button type="button" className="mt-2 rounded-lg border px-3 py-2 text-sm font-semibold" disabled={!visualArtifactSelections[post.post_id] || attachVisual.isPending} onClick={() => attachVisual.mutate({ postId: post.post_id, artifactId: visualArtifactSelections[post.post_id] })}>إرفاق التصميم</button>
                  </>}
                </div>
              </article>;
            })}</div>}

          <Pagination page={readyPage} pageCount={readyPageCount} onChange={setReadyPage} loading={posts.isFetching} label="صفحات المنشورات الجاهزة" />
        </section>
      )}

      {section === "plans" && (
        <section className="space-y-4" data-testid="publishing-plans">
          <div className="rounded-2xl border bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-xl font-bold">خطط النشر</h3><p className="mt-1 text-sm text-slate-500">راجع الخطط حسب الحالة وافتح الخطة المطلوبة فقط.</p></div><button type="button" onClick={() => void refresh()} className="rounded-xl border px-4 py-2 text-sm font-semibold">تحديث</button></div>
            <div className="mt-4 grid gap-3 md:grid-cols-[1fr_220px]"><label className="text-sm font-semibold"><span className="sr-only">بحث الخطط</span><input aria-label="بحث الخطط" value={planQuery} onChange={(e) => { setPlanQuery(e.target.value); setPlanPage(0); }} placeholder="ابحث باسم الخطة أو المنطقة الزمنية..." className="mt-2 w-full rounded-xl border p-3 font-normal"/></label><label className="text-sm font-semibold">الحالة<select aria-label="حالة الخطة" value={planStatus} onChange={(e) => { setPlanStatus(e.target.value); setPlanPage(0); }} className="mt-2 w-full rounded-xl border p-3 font-normal"><option value="">كل الحالات</option><option value="DRAFT">مسودة</option><option value="ACTIVE">نشطة</option><option value="PAUSED">متوقفة</option><option value="COMPLETED">مكتملة</option><option value="CANCELLED">ملغاة</option></select></label></div>
          </div>
          {!visiblePlans.length ? <div className="rounded-2xl border border-dashed bg-white p-10 text-center"><h3 className="font-bold">لا توجد خطط مطابقة</h3><p className="mt-2 text-sm text-slate-500">أنشئ خطة من قسم «الجاهز للنشر» أو غيّر الفلاتر.</p></div> : <div className="space-y-2">{visiblePlans.map((s) => <button key={s.id} type="button" onClick={() => void openDetail(s.id)} className={`w-full rounded-2xl border bg-white p-4 text-right shadow-sm transition hover:border-indigo-300 ${detail?.id === s.id ? "border-indigo-300 ring-1 ring-indigo-200" : ""}`}><div className="flex flex-wrap items-center justify-between gap-3"><strong>{s.name}</strong><span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold">{s.status}</span></div><div className="mt-2 text-xs text-slate-500">{s.total_items} عناصر · {s.published_items} منشور · {s.failed_items} فشل · {s.timezone}</div></button>)}</div>}
          <Pagination page={planPage} pageCount={planPageCount} onChange={setPlanPage} loading={schedules.isFetching} label="صفحات خطط النشر" />
        </section>
      )}

      {section === "plans" && detail && (
        <section className="rounded-2xl border-2 border-indigo-200 bg-white p-5 shadow-sm" data-testid="schedule-detail">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><p className="text-xs font-semibold text-indigo-600">تفاصيل الخطة</p><h3 className="mt-1 text-xl font-bold">{detail.name}</h3><p className="text-sm text-slate-500">{detail.status} · {detail.timezone} · {detail.total_items} عناصر</p></div>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={()=>void openDetail(detail.id)} className="rounded-lg border px-3 py-2 text-sm">تحديث تفاصيل الخطة</button>
              {(detail.status === "DRAFT" || detail.status === "PAUSED") && <button type="button" onClick={() => void action.mutateAsync({ type: "activate", id: detail.id })} className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-bold text-white">تفعيل النشر الآلي</button>}
              {detail.status === "ACTIVE" && <button type="button" onClick={() => action.mutate({ type: "pause", id: detail.id })} className="rounded-lg border px-3 py-2 text-sm font-semibold">إيقاف مؤقت</button>}
              {!["COMPLETED", "CANCELLED"].includes(detail.status) && <button type="button" onClick={() => action.mutate({ type: "cancel", id: detail.id })} className="rounded-lg bg-rose-600 px-3 py-2 text-sm font-bold text-white">إلغاء الخطة</button>}
              {detail.failed_items > 0 && <button type="button" onClick={() => action.mutate({ type: "retry", id: detail.id })} className="rounded-lg bg-amber-600 px-3 py-2 text-sm font-bold text-white">إعادة محاولة الفاشل</button>}
            </div>
          </div>
          <div className="mt-4 space-y-2">{detail.items.map((item) => <div key={item.id} className="rounded-xl border p-4"><div className="flex flex-wrap justify-between gap-2"><strong>{item.position}. {item.title}</strong><span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-bold">{item.status}</span></div><p className="mt-1 text-sm text-slate-600">{item.content_preview}</p><div className="mt-2 flex flex-wrap gap-2"><input aria-label={`وقت نشر ${item.title}`} type="datetime-local" value={itemTimes[item.id] ?? utcISOStringToLocalDateTime(item.scheduled_at, detail.timezone)} onChange={(e) => setItemTimes(current=>({...current,[item.id]:e.target.value}))} disabled={!["DRAFT","PAUSED"].includes(detail.status) || item.status!=="PENDING"} className="rounded-lg border p-2 text-sm"/><button type="button" disabled={!["DRAFT","PAUSED"].includes(detail.status) || item.status!=="PENDING" || !itemTimes[item.id] || itemTimes[item.id]===utcISOStringToLocalDateTime(item.scheduled_at,detail.timezone)} onClick={()=>void updateItemTime(item.id,itemTimes[item.id])} className="rounded-lg border px-3 py-2 text-sm disabled:opacity-40">حفظ الموعد</button>{item.post_id?<button type="button" onClick={() => void preview(item.post_id)} className="rounded-lg border px-3 py-2 text-sm">معاينة Telegram</button>:item.artifact_id?<Link to={`/bank?artifact_status=APPROVED&artifact_id=${encodeURIComponent(item.artifact_id)}`} className="rounded-lg border px-3 py-2 text-sm">فتح المادة ونسخها وسجلها</Link>:null}{item.status === "FAILED" && <button type="button" onClick={() => void schedulesApi.retryItem(detail.id, item.id).then((r) => { setDetail(r.schedule); void refresh(); })} className="rounded-lg bg-amber-100 px-3 py-2 text-sm font-semibold">إعادة المحاولة</button>}</div>{item.publication_external_id && <p className="mt-2 text-xs text-emerald-700">معرّفات Telegram: {(item.publication_external_ids?.length ? item.publication_external_ids : [item.publication_external_id]).join(", ")}</p>}{item.last_error && <p className="mt-2 rounded-lg bg-rose-50 p-2 text-sm text-rose-700">{item.last_error}</p>}</div>)}</div>
        </section>
      )}

      {section === "calendar" && (
        <section className="space-y-4" data-testid="publishing-calendar">
          <div className="rounded-2xl border bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="text-xl font-bold">التقويم</h3><p className="mt-1 text-sm text-slate-500">راجع ما سيُنشر حسب اليوم قبل التنفيذ.</p></div><label className="text-sm font-semibold">اليوم<input aria-label="تاريخ التقويم" type="date" value={calendarDate} onChange={(e) => setCalendarDate(e.target.value)} className="mr-2 rounded-lg border p-2 font-normal"/></label></div>
          </div>
          <div className="rounded-2xl border bg-white p-5 shadow-sm"><h3 className="font-bold">القادم 7 أيام</h3>{upcoming.isError?<p role="alert" className="mt-4 text-rose-700">تعذر تحميل القادم. أعد المحاولة، لا نستنتج أن القائمة فارغة.</p>:!(upcoming.data?.items.length) ? <p className="mt-4 rounded-xl bg-slate-50 p-5 text-sm text-slate-500">لا توجد عناصر مجدولة في الأيام القادمة.</p> : <div className="mt-4 space-y-2">{upcoming.data!.items.map((i) => <button key={i.id} type="button" onClick={() => void openDetail(i.schedule_id)} className="w-full rounded-xl border p-3 text-right hover:border-indigo-300"><div className="flex flex-wrap justify-between gap-2"><strong>{i.title}</strong><span className="text-xs text-slate-500">{new Date(i.scheduled_at).toLocaleString("ar", { timeZone: i.timezone })}</span></div><p className="mt-1 text-xs text-slate-500">{i.schedule_name} · {i.status}</p></button>)}</div>}</div>
          <div className="rounded-2xl border bg-white p-5 shadow-sm"><div className="flex flex-wrap items-center justify-between gap-3"><h3 className="font-bold">تقويم اليوم</h3><span className="text-xs text-slate-500">{calendar.data?.timezone ?? DEFAULT_TIMEZONE}</span></div>{calendar.isError?<p role="alert" className="mt-4 text-rose-700">تعذر تحميل التقويم. أعد المحاولة، لا نستنتج عدم وجود مواد.</p>:!(calendar.data?.items.length) ? <p className="mt-4 rounded-xl bg-slate-50 p-5 text-sm text-slate-500">لا توجد منشورات مجدولة لهذا اليوم.</p> : <div className="mt-4 space-y-2">{calendar.data!.items.map((i) => <button key={i.id} type="button" onClick={() => void openDetail(i.schedule_id)} className="w-full rounded-xl border p-3 text-right hover:border-indigo-300"><div className="flex flex-wrap justify-between gap-2"><strong>{i.title}</strong><span>{new Date(i.scheduled_at).toLocaleTimeString("ar", { hour: "2-digit", minute: "2-digit", timeZone: i.timezone })}</span></div><p className="mt-1 text-xs text-slate-500">{i.schedule_name} · {i.status}</p></button>)}</div>}</div>
        </section>
      )}

      {section === "platforms" && (
        <section className="space-y-4" data-testid="publishing-platforms">
          <div className="rounded-2xl border bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div><h3 className="text-xl font-bold">مسودات المنصات الاجتماعية</h3><p className="mt-1 text-sm text-slate-500">نسخ معدّة من المخرجات والمنشورات المعتمدة للمراجعة اليدوية لكل منصة.</p></div>
              <button type="button" onClick={() => void platformVariants.refetch()} className="rounded-xl border px-4 py-2 text-sm font-semibold">تحديث</button>
            </div>
            <p className="mt-3 rounded-xl bg-amber-50 p-3 text-xs leading-6 text-amber-800">تحضير فقط: هذه المسودات لا تدخل الجدولة الآلية ولا تُنشر تلقائيًا. الاقتصار هنا على ضبط الطول عند حدود آمنة مع الحفاظ على المعنى والروابط، والنص الأصلي محفوظ دون تغيير في المصدر، وكل مسودة تتطلب مراجعة يدوية قبل أي استخدام. تسجيل النشر اليدوي يوثّق ما نشرته بنفسك خارج التطبيق فقط، وليس نشرًا عبر واجهات المنصات.</p>
          </div>
          {platformVariants.isLoading ? (
            <Status title="جارٍ تحميل مسودات المنصات..." />
          ) : !(platformVariants.data?.length) ? (
            <div className="rounded-2xl border border-dashed bg-white p-10 text-center"><h3 className="font-bold">لا توجد مسودات منصات بعد</h3><p className="mt-2 text-sm text-slate-500">اشتق نسخة منصة من مخرج معتمد أو منشور معتمد من بنك المحتوى.</p></div>
          ) : (
            <>
              <div className="rounded-2xl border bg-white p-4 text-sm text-slate-600" data-testid="variant-pipeline-summary">
                مسار التحضير: مسودة <bdi>{variantGroups.drafts.length}</bdi> · معتمدة بانتظار النشر اليدوي <bdi>{variantGroups.approved.length}</bdi> · منشورة يدويًا <bdi>{variantGroups.published.length}</bdi>
              </div>
              {([
                { key: "drafts", title: "مسودات قيد المراجعة", items: variantGroups.drafts },
                { key: "approved", title: "معتمدة بانتظار النشر اليدوي", items: variantGroups.approved },
                { key: "published", title: "منشورة يدويًا", items: variantGroups.published },
                { key: "rejected", title: "مرفوضة", items: variantGroups.rejected },
              ] as const).filter((group) => group.items.length > 0).map((group) => (
                <div key={group.key} className="space-y-3">
                  <h4 className="text-sm font-bold text-slate-600">{group.title} (<bdi>{group.items.length}</bdi>)</h4>
                  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                    {group.items.map((v) => <VariantCard key={v.id} v={v} manualPub={manualPub} setManualPub={setManualPub} recordManualPending={recordManual.isPending} onSubmitManual={submitManualPublication} />)}
                  </div>
                </div>
              ))}
            </>
          )}
        </section>
      )}

      {scheduleOpen && <form data-testid="schedule-panel" className="rounded-2xl border-2 border-indigo-200 bg-white p-5 shadow-sm" onSubmit={(e) => { e.preventDefault(); createSchedule.mutate(); }}><div className="flex items-start justify-between gap-3"><div><h3 className="font-bold">إنشاء خطة نشر</h3><p className="mt-1 text-sm text-slate-500">{selectedIds.length} منشور جاهز للخطة.</p></div><button type="button" onClick={() => setScheduleOpen(false)} className="rounded-lg border px-3 py-2 text-sm">إغلاق</button></div><div className="mt-4 grid gap-4 sm:grid-cols-2"><label>اسم الخطة<input aria-label="اسم الخطة" value={form.name} onChange={(e) => setForm({...form, name: e.target.value})} className="mt-2 w-full rounded-xl border p-3"/></label><label>المنطقة الزمنية<input aria-label="المنطقة الزمنية" value={form.timezone} onChange={(e) => setForm({...form, timezone: e.target.value})} className="mt-2 w-full rounded-xl border p-3"/></label><label>وقت البداية<input aria-label="وقت البداية" type="datetime-local" value={form.startAt} onChange={(e) => setForm({...form, startAt: e.target.value})} className="mt-2 w-full rounded-xl border p-3"/></label><label>الفاصل بالدقائق<input aria-label="الفاصل بالدقائق" type="number" min="1" value={form.interval} onChange={(e) => setForm({...form, interval: e.target.value})} className="mt-2 w-full rounded-xl border p-3"/></label></div><div className="mt-5 flex gap-2"><button data-testid="submit-schedule" type="submit" disabled={createSchedule.isPending} className="rounded-xl bg-emerald-600 px-5 py-3 font-bold text-white">حفظ الخطة</button><button type="button" onClick={() => setScheduleOpen(false)} className="rounded-xl border px-5 py-3">إلغاء</button></div></form>}
    </section>
  );
}

function VariantCard({ v, manualPub, setManualPub, recordManualPending, onSubmitManual }: {
  v: PlatformVariantDraft;
  manualPub: { id: string; date: string; url: string } | null;
  setManualPub: (value: { id: string; date: string; url: string } | null) => void;
  recordManualPending: boolean;
  onSubmitManual: (id: string) => void;
}) {
  const [showFull, setShowFull] = useState(false);
  const [mediaOpen, setMediaOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const isMedia = v.kind === "IMAGE" || v.kind === "VIDEO";
  const media = useQuery({
    queryKey: ["publishing", "variant-media", v.id],
    queryFn: () => genericArtifactsApi.mediaUrl(v.id),
    enabled: mediaOpen && isMedia,
    staleTime: 240_000,
  });
  const copyFullText = async () => {
    try {
      await navigator.clipboard.writeText(v.content);
    } catch {
      const area = document.createElement("textarea");
      area.value = v.content;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  };
  return (
    <article data-testid="platform-variant-card" className="rounded-2xl border bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <strong>{v.platform_label_ar ?? v.platform ?? "منصة"}</strong>
        <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-bold">{v.manual_publication ? "منشورة يدويًا" : v.review_status === "APPROVED" ? "معتمدة" : v.review_status === "REJECTED" ? "مرفوضة" : "مسودة"}</span>
      </div>
      <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-7 text-slate-700">{showFull ? v.content : v.excerpt}{!showFull && v.full_length > v.excerpt.length ? "…" : ""}</p>
      <dl className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
        <div><dt className="inline">المصدر: </dt><dd className="inline">{v.source_kind_ar ?? "غير محدد"}</dd></div>
        {v.constraints.max_text != null && <div><dt className="inline">الطول الحالي: </dt><dd className="inline"><bdi>{v.constraints.measured_length ?? "؟"}</bdi> من <bdi>{v.constraints.max_text}</bdi>{v.constraints.measure ? <span className="mr-1 text-slate-400" dir="ltr">({v.constraints.measure})</span> : null}</dd></div>}
        {v.constraints.trimmed && <div><dt className="inline">القص: </dt><dd className="inline">عند حد {v.constraints.trim_boundary === "sentence" ? "جملة" : v.constraints.trim_boundary === "whitespace" ? "كلمة" : "ثابت"}</dd></div>}
      </dl>
      <div className="mt-3 flex flex-wrap gap-2">
        {v.needs_review && v.review_status !== "APPROVED" && !v.manual_publication && <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-bold text-amber-800">تتطلب مراجعة</span>}
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">ضبط طول فقط، ليست صياغة مخصصة</span>
        {v.constraints.provenance && <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-500">مصدر القيود: {v.constraints.provenance === "primary" ? "وثائق رسمية" : "مصادر ثانوية"}</span>}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {v.full_length > v.excerpt.length && (
          <button type="button" onClick={() => setShowFull((open) => !open)} className="rounded-lg border px-3 py-1.5 text-xs font-semibold">{showFull ? "إخفاء النص الكامل" : "عرض النص الكامل"}</button>
        )}
        <button type="button" onClick={() => void copyFullText()} className="rounded-lg border px-3 py-1.5 text-xs font-semibold">{copied ? "نُسخ النص" : "نسخ النص للنشر اليدوي"}</button>
        {isMedia && (
          <button type="button" onClick={() => setMediaOpen((open) => !open)} className="rounded-lg border px-3 py-1.5 text-xs font-semibold">{mediaOpen ? "إخفاء الوسيط" : "عرض الوسيط"}</button>
        )}
      </div>
      {mediaOpen && isMedia && (
        <div className="mt-3 rounded-xl border bg-slate-50 p-3" data-testid="variant-media-preview">
          {media.isLoading ? <p className="text-xs text-slate-500">جارٍ تحميل الوسيط...</p>
            : media.isError || !media.data?.url ? <p className="text-xs text-red-600">تعذر تحميل الوسيط.</p>
            : <>
              {v.kind === "IMAGE"
                ? <img src={media.data.url} alt={v.excerpt.slice(0, 80)} className="max-h-64 w-full rounded-lg object-contain" />
                : <video src={media.data.url} controls playsInline className="max-h-64 w-full rounded-lg" />}
              <a href={media.data.url} target="_blank" rel="noreferrer" dir="ltr" className="mt-2 inline-block break-all text-xs font-semibold text-indigo-700 underline">فتح الوسيط في تبويب</a>
            </>}
        </div>
      )}
      {v.manual_publication ? (
        <div className="mt-3 rounded-xl bg-emerald-50 p-3 text-xs leading-6 text-emerald-800" data-testid="manual-publication-record">
          <div>نُشرت يدويًا خارج التطبيق في <bdi>{new Date(v.manual_publication.published_at).toLocaleDateString("ar")}</bdi></div>
          {v.manual_publication.external_url && <a href={v.manual_publication.external_url} target="_blank" rel="noreferrer" dir="ltr" className="break-all font-semibold underline">رابط المنشور</a>}
        </div>
      ) : v.review_status === "APPROVED" ? (
        manualPub?.id === v.id ? (
          <form className="mt-3 space-y-2 rounded-xl border p-3" data-testid="manual-publication-form" onSubmit={(e) => { e.preventDefault(); onSubmitManual(v.id); }}>
            <label className="block text-xs font-semibold">تاريخ النشر اليدوي
              <input aria-label="تاريخ النشر اليدوي" type="date" required max={new Date().toISOString().slice(0, 10)} value={manualPub.date} onChange={(e) => setManualPub({ ...manualPub, date: e.target.value })} className="mt-1 w-full rounded-lg border p-2 font-normal" />
            </label>
            <label className="block text-xs font-semibold">رابط المنشور (اختياري)
              <input aria-label="رابط المنشور" type="url" inputMode="url" dir="ltr" placeholder="https://…" value={manualPub.url} onChange={(e) => setManualPub({ ...manualPub, url: e.target.value })} className="mt-1 w-full rounded-lg border p-2 font-normal" />
            </label>
            <div className="flex flex-wrap gap-2">
              <button type="submit" disabled={recordManualPending} className="rounded-lg bg-emerald-600 px-4 py-2 text-xs font-bold text-white">حفظ التسجيل</button>
              <button type="button" onClick={() => setManualPub(null)} className="rounded-lg border px-4 py-2 text-xs">إلغاء</button>
            </div>
          </form>
        ) : (
          <button type="button" onClick={() => setManualPub({ id: v.id, date: new Date().toISOString().slice(0, 10), url: "" })} className="mt-3 rounded-xl border border-emerald-300 px-4 py-2 text-xs font-bold text-emerald-700">تسجيل نشر يدوي</button>
        )
      ) : null}
    </article>
  );
}

function Pagination({ page, pageCount, onChange, loading, label }: { page: number; pageCount: number; onChange: (page: number) => void; loading: boolean; label: string }) {
  return <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border bg-white p-4" aria-label={label}>
    <button type="button" onClick={() => onChange(Math.max(0, page - 1))} disabled={page === 0 || loading} className="rounded-xl border px-4 py-2 disabled:opacity-40">السابق</button>
    <span className="text-sm font-semibold">صفحة {page + 1} من {pageCount}</span>
    <button type="button" onClick={() => onChange(Math.min(pageCount - 1, page + 1))} disabled={page >= pageCount - 1 || loading} className="rounded-xl border px-4 py-2 disabled:opacity-40">التالي</button>
  </div>;
}

function Status({ title, detail, error = false }: { title: string; detail?: string; error?: boolean }) {
  return <div role={error ? "alert" : "status"} className="rounded-2xl border bg-white p-8"><h2 className="font-bold">{title}</h2>{detail && <p className="mt-2 text-sm text-slate-600">{detail}</p>}</div>;
}
