import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router";
import { useMemo, useState } from "react";
import { postsApi } from "../../shared/api/postsApi";
import { schedulesApi, type ScheduleDetail } from "../../shared/api/schedulesApi";
import { toggleSelection, selectionFromQuery } from "../../shared/utils/selection";
import { localDateTimeToUtcISOString, utcISOStringToLocalDateTime } from "../../shared/utils/timezone";

const DEFAULT_TIMEZONE = "Asia/Aden";
const PAGE_SIZE = 20;
type Section = "ready" | "plans" | "calendar";

export function PublishingPage() {
  const client = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [section, setSection] = useState<Section>("ready");
  const [selectedIds, setSelectedIds] = useState<string[]>(() => selectionFromQuery(searchParams.get("selected_post_ids")));
  const [scheduleOpen, setScheduleOpen] = useState(Boolean(searchParams.get("selected_post_ids")));
  const [message, setMessage] = useState("");
  const [detail, setDetail] = useState<ScheduleDetail | null>(null);
  const [readyQuery, setReadyQuery] = useState("");
  const [readySort, setReadySort] = useState<"created" | "title" | "kind" | "topic">("created");
  const [readyPage, setReadyPage] = useState(0);
  const [planQuery, setPlanQuery] = useState("");
  const [planStatus, setPlanStatus] = useState("");
  const [planPage, setPlanPage] = useState(0);
  const [calendarDate, setCalendarDate] = useState(new Date().toISOString().slice(0, 10));
  const [form, setForm] = useState({ name: "خطة نشر", timezone: DEFAULT_TIMEZONE, startAt: "", interval: "60" });

  const posts = useQuery({
    queryKey: ["publishing", "eligible-posts", readyQuery, readySort, readyPage],
    queryFn: () => postsApi.list({
      status: "APPROVED",
      publicationState: "ELIGIBLE",
      query: readyQuery.trim() || undefined,
      sort: readySort,
      limit: PAGE_SIZE,
      offset: readyPage * PAGE_SIZE,
    }),
    placeholderData: (previous) => previous,
  });
  const schedules = useQuery({ queryKey: ["publishing", "schedules"], queryFn: schedulesApi.list });
  const upcoming = useQuery({ queryKey: ["publishing", "upcoming"], queryFn: schedulesApi.upcoming });
  const calendar = useQuery({
    queryKey: ["publishing", "calendar", calendarDate, DEFAULT_TIMEZONE],
    queryFn: () => schedulesApi.calendar(calendarDate, DEFAULT_TIMEZONE),
  });

  const eligibility = useMutation({ mutationFn: () => schedulesApi.eligibility(selectedIds) });
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
      setMessage("تم تحديث وقت العنصر.");
      void refresh();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "تعذر تحديث الوقت.");
    }
  };
  const preview = async (postId: string) => {
    try {
      const p = await schedulesApi.telegramPreview(postId);
      setMessage(p.content);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "تعذر تحميل معاينة Telegram.");
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
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-indigo-600">Workspace 03</p>
          <h2 className="mt-1 text-3xl font-bold">مساحة النشر</h2>
          <p className="mt-2 max-w-3xl text-sm leading-7 text-slate-600">منطقة مرتبة للجاهز، خطط النشر، والتقويم. كل خطوة تظهر عندما تكون منطقية للحالة الحالية.</p>
        </div>
        <Link to="/posts/workspace" className="rounded-xl border px-4 py-2 text-sm font-semibold">العودة إلى مصنع المحتوى</Link>
      </header>

      <nav aria-label="أقسام مساحة النشر" className="grid gap-2 rounded-2xl border bg-slate-50 p-2 sm:grid-cols-3">
        {([
          ["ready", "الجاهز للنشر", readyTotal, "منشورات معتمدة ومؤهلة"],
          ["plans", "خطط النشر", schedules.data?.total ?? schedules.data?.items.length ?? 0, "الخطط المحفوظة وحالاتها"],
          ["calendar", "التقويم", upcoming.data?.items.length ?? 0, "القادم وجدول اليوم"],
        ] as const).map(([key, label, count, hint]) => (
          <button key={key} type="button" onClick={() => switchSection(key)} className={`rounded-xl p-4 text-right transition ${section === key ? "bg-white shadow-sm ring-1 ring-indigo-200" : "hover:bg-white"}`}>
            <div className="flex items-center justify-between gap-3"><strong>{label}</strong><span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-bold">{count}</span></div>
            <span className="mt-1 block text-xs text-slate-500">{hint}</span>
          </button>
        ))}
      </nav>

      {message && <div role="status" className="whitespace-pre-wrap rounded-xl border bg-indigo-50 p-4 text-sm">{message}</div>}

      {section === "ready" && (
        <section className="space-y-4" data-testid="publishing-ready">
          <div className="rounded-2xl border bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div><h3 className="text-xl font-bold">المنشورات الجاهزة</h3><p className="mt-1 text-sm text-slate-500">لا يظهر هنا إلا ما هو معتمد ومؤهل للنشر.</p></div>
              <span data-testid="selection-count" className="rounded-full bg-indigo-50 px-3 py-1 text-sm font-bold text-indigo-700">{selectedIds.length} محدد</span>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-[1fr_220px_auto]">
              <label className="text-sm font-semibold"><span className="sr-only">بحث المنشورات الجاهزة</span><input aria-label="بحث المنشورات الجاهزة" value={readyQuery} onChange={(e) => { setReadyQuery(e.target.value); setReadyPage(0); }} placeholder="ابحث في العنوان أو النص..." className="w-full rounded-xl border p-3 font-normal" /></label>
              <label className="text-sm font-semibold">الفرز<select aria-label="فرز المنشورات الجاهزة" value={readySort} onChange={(e) => { setReadySort(e.target.value as typeof readySort); setReadyPage(0); }} className="mt-2 w-full rounded-xl border p-3 font-normal"><option value="created">الأحدث أولًا</option><option value="title">العنوان: أ - ي</option><option value="kind">النوع</option><option value="topic">المحور</option></select></label>
              <button type="button" onClick={() => { setReadyQuery(""); setReadySort("created"); setReadyPage(0); setSelectedIds([]); setSearchParams({}); }} className="rounded-xl border px-4 py-3 text-sm font-semibold">مسح البحث</button>
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
            ? <div className="rounded-2xl border border-dashed bg-white p-10 text-center"><h3 className="font-bold">لا توجد منشورات جاهزة</h3><p className="mt-2 text-sm text-slate-500">جرّب تغيير عبارة البحث، أو عد إلى مصنع المحتوى لاعتماد منشورات جديدة.</p></div>
            : <div className="space-y-3">{readyItems.map((post) => <article key={post.post_id} className="rounded-2xl border bg-white p-4 shadow-sm"><label className="flex cursor-pointer items-start gap-3"><input aria-label={`تحديد ${post.title}`} type="checkbox" checked={selectedIds.includes(post.post_id)} onChange={(e) => setSelection(post.post_id, e.target.checked)} className="mt-1 h-4 w-4"/><span className="min-w-0"><strong className="block">{post.title}</strong><span className="mt-1 block text-xs text-slate-500">{post.source_title}</span><p className="mt-2 text-sm leading-7 text-slate-600">{post.content_preview}</p></span></label></article>)}</div>}

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
              {(detail.status === "DRAFT" || detail.status === "PAUSED") && <button type="button" onClick={() => void action.mutateAsync({ type: "activate", id: detail.id })} className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-bold text-white">تفعيل النشر الآلي</button>}
              {detail.status === "ACTIVE" && <button type="button" onClick={() => action.mutate({ type: "pause", id: detail.id })} className="rounded-lg border px-3 py-2 text-sm font-semibold">إيقاف مؤقت</button>}
              {!["COMPLETED", "CANCELLED"].includes(detail.status) && <button type="button" onClick={() => action.mutate({ type: "cancel", id: detail.id })} className="rounded-lg bg-rose-600 px-3 py-2 text-sm font-bold text-white">إلغاء الخطة</button>}
              {detail.failed_items > 0 && <button type="button" onClick={() => action.mutate({ type: "retry", id: detail.id })} className="rounded-lg bg-amber-600 px-3 py-2 text-sm font-bold text-white">إعادة محاولة الفاشل</button>}
            </div>
          </div>
          <div className="mt-4 space-y-2">{detail.items.map((item) => <div key={item.id} className="rounded-xl border p-4"><div className="flex flex-wrap justify-between gap-2"><strong>{item.position + 1}. {item.title}</strong><span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-bold">{item.status}</span></div><p className="mt-1 text-sm text-slate-600">{item.content_preview}</p><div className="mt-2 flex flex-wrap gap-2"><input aria-label={`وقت نشر ${item.title}`} type="datetime-local" defaultValue={utcISOStringToLocalDateTime(item.scheduled_at, detail.timezone)} onBlur={(e) => void updateItemTime(item.id, e.target.value)} className="rounded-lg border p-2 text-sm"/><button type="button" onClick={() => void preview(item.post_id)} className="rounded-lg border px-3 py-2 text-sm">معاينة Telegram</button>{item.status === "FAILED" && <button type="button" onClick={() => void schedulesApi.retryItem(detail.id, item.id).then((r) => { setDetail(r.schedule); void refresh(); })} className="rounded-lg bg-amber-100 px-3 py-2 text-sm font-semibold">إعادة المحاولة</button>}</div>{item.last_error && <p className="mt-2 rounded-lg bg-rose-50 p-2 text-sm text-rose-700">{item.last_error}</p>}</div>)}</div>
        </section>
      )}

      {section === "calendar" && (
        <section className="space-y-4" data-testid="publishing-calendar">
          <div className="rounded-2xl border bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="text-xl font-bold">التقويم</h3><p className="mt-1 text-sm text-slate-500">راجع ما سيُنشر حسب اليوم قبل التنفيذ.</p></div><label className="text-sm font-semibold">اليوم<input aria-label="تاريخ التقويم" type="date" value={calendarDate} onChange={(e) => setCalendarDate(e.target.value)} className="mr-2 rounded-lg border p-2 font-normal"/></label></div>
          </div>
          <div className="rounded-2xl border bg-white p-5 shadow-sm"><h3 className="font-bold">القادم 7 أيام</h3>{!(upcoming.data?.items.length) ? <p className="mt-4 rounded-xl bg-slate-50 p-5 text-sm text-slate-500">لا توجد عناصر مجدولة في الأيام القادمة.</p> : <div className="mt-4 space-y-2">{upcoming.data!.items.map((i) => <button key={i.id} type="button" onClick={() => void openDetail(i.schedule_id)} className="w-full rounded-xl border p-3 text-right hover:border-indigo-300"><div className="flex flex-wrap justify-between gap-2"><strong>{i.title}</strong><span className="text-xs text-slate-500">{new Date(i.scheduled_at).toLocaleString("ar", { timeZone: i.timezone })}</span></div><p className="mt-1 text-xs text-slate-500">{i.schedule_name} · {i.status}</p></button>)}</div>}</div>
          <div className="rounded-2xl border bg-white p-5 shadow-sm"><div className="flex flex-wrap items-center justify-between gap-3"><h3 className="font-bold">تقويم اليوم</h3><span className="text-xs text-slate-500">{calendar.data?.timezone ?? DEFAULT_TIMEZONE}</span></div>{!(calendar.data?.items.length) ? <p className="mt-4 rounded-xl bg-slate-50 p-5 text-sm text-slate-500">لا توجد منشورات مجدولة لهذا اليوم.</p> : <div className="mt-4 space-y-2">{calendar.data!.items.map((i) => <button key={i.id} type="button" onClick={() => void openDetail(i.schedule_id)} className="w-full rounded-xl border p-3 text-right hover:border-indigo-300"><div className="flex flex-wrap justify-between gap-2"><strong>{i.title}</strong><span>{new Date(i.scheduled_at).toLocaleTimeString("ar", { hour: "2-digit", minute: "2-digit", timeZone: i.timezone })}</span></div><p className="mt-1 text-xs text-slate-500">{i.schedule_name} · {i.status}</p></button>)}</div>}</div>
        </section>
      )}

      {scheduleOpen && <form data-testid="schedule-panel" className="rounded-2xl border-2 border-indigo-200 bg-white p-5 shadow-sm" onSubmit={(e) => { e.preventDefault(); createSchedule.mutate(); }}><div className="flex items-start justify-between gap-3"><div><h3 className="font-bold">إنشاء خطة نشر</h3><p className="mt-1 text-sm text-slate-500">{selectedIds.length} منشور جاهز للخطة.</p></div><button type="button" onClick={() => setScheduleOpen(false)} className="rounded-lg border px-3 py-2 text-sm">إغلاق</button></div><div className="mt-4 grid gap-4 sm:grid-cols-2"><label>اسم الخطة<input aria-label="اسم الخطة" value={form.name} onChange={(e) => setForm({...form, name: e.target.value})} className="mt-2 w-full rounded-xl border p-3"/></label><label>المنطقة الزمنية<input aria-label="المنطقة الزمنية" value={form.timezone} onChange={(e) => setForm({...form, timezone: e.target.value})} className="mt-2 w-full rounded-xl border p-3"/></label><label>وقت البداية<input aria-label="وقت البداية" type="datetime-local" value={form.startAt} onChange={(e) => setForm({...form, startAt: e.target.value})} className="mt-2 w-full rounded-xl border p-3"/></label><label>الفاصل بالدقائق<input aria-label="الفاصل بالدقائق" type="number" min="1" value={form.interval} onChange={(e) => setForm({...form, interval: e.target.value})} className="mt-2 w-full rounded-xl border p-3"/></label></div><div className="mt-5 flex gap-2"><button data-testid="submit-schedule" type="submit" disabled={createSchedule.isPending} className="rounded-xl bg-emerald-600 px-5 py-3 font-bold text-white">حفظ الخطة</button><button type="button" onClick={() => setScheduleOpen(false)} className="rounded-xl border px-5 py-3">إلغاء</button></div></form>}
    </section>
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
