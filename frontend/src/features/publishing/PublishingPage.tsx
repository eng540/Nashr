import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router";
import { useMemo, useState } from "react";
import { postsApi } from "../../shared/api/postsApi";
import { schedulesApi, type ScheduleDetail } from "../../shared/api/schedulesApi";
import { toggleSelection, selectionFromQuery } from "../../shared/utils/selection";
import { localDateTimeToUtcISOString } from "../../shared/utils/timezone";

const DEFAULT_TIMEZONE = "Asia/Aden";
export function PublishingPage() {
  const client = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedIds, setSelectedIds] = useState<string[]>(() => selectionFromQuery(searchParams.get("selected_post_ids")));
  const [scheduleOpen, setScheduleOpen] = useState(Boolean(searchParams.get("selected_post_ids")));
  const [message, setMessage] = useState("");
  const [detail, setDetail] = useState<ScheduleDetail | null>(null);
  const [form, setForm] = useState({ name: "خطة نشر", timezone: DEFAULT_TIMEZONE, startAt: "", interval: "60" });
  const [calendarDate, setCalendarDate] = useState(new Date().toISOString().slice(0, 10));

  const posts = useQuery({ queryKey: ["publishing", "eligible-posts"], queryFn: () => postsApi.list({ status: "APPROVED", publicationState: "ELIGIBLE" }) });
  const schedules = useQuery({ queryKey: ["publishing", "schedules"], queryFn: schedulesApi.list });
  const upcoming = useQuery({ queryKey: ["publishing", "upcoming"], queryFn: schedulesApi.upcoming });
  const calendar = useQuery({ queryKey: ["publishing", "calendar", calendarDate, DEFAULT_TIMEZONE], queryFn: () => schedulesApi.calendar(calendarDate, DEFAULT_TIMEZONE) });

  const eligibility = useMutation({ mutationFn: () => schedulesApi.eligibility(selectedIds) });
  const createSchedule = useMutation({
    mutationFn: () => {
      if (!form.startAt) throw new Error("حدد وقت بداية صالح.");
      return schedulesApi.create({ name: form.name.trim(), timezone: form.timezone.trim(), post_ids: selectedIds, start_at: localDateTimeToUtcISOString(form.startAt, form.timezone), interval_minutes: Number(form.interval), idempotency_key: crypto.randomUUID() });
    },
    onSuccess: (schedule) => { setMessage(`تم إنشاء الخطة بنجاح: ${schedule.name}`); setScheduleOpen(false); setDetail(schedule); void refresh(); },
  });
  const refresh = async () => { await Promise.all([client.invalidateQueries({ queryKey: ["publishing", "schedules"] }), client.invalidateQueries({ queryKey: ["publishing", "upcoming"] }), client.invalidateQueries({ queryKey: ["publishing", "calendar"])]); };
  const action = useMutation({
    mutationFn: ({ type, id }: { type: "activate"|"pause"|"cancel"|"retry"; id: string }) => type === "activate" ? schedulesApi.activate(id) : type === "pause" ? schedulesApi.pause(id) : type === "cancel" ? schedulesApi.cancel(id) : schedulesApi.retryFailed(id),
    onSuccess: (data) => { setDetail(data); setMessage(`تم تنفيذ العملية. حالة الخطة: ${data.status}`); void refresh(); },
  });
  const openDetail = async (id: string) => { try { setDetail(await schedulesApi.get(id)); } catch (e) { setMessage(e instanceof Error ? e.message : "تعذر تحميل الخطة."); } };
  const selectedPosts = useMemo(() => (posts.data?.items ?? []).filter(p => selectedIds.includes(p.post_id)), [posts.data?.items, selectedIds]);
  const setSelection = (id: string, checked: boolean) => { const next = toggleSelection(selectedIds, id, checked); setSelectedIds(next); setSearchParams(next.length ? { selected_post_ids: next.join(",") } : {}); };
  const openSchedule = async () => {
    if (!selectedIds.length) return;
    try { const result = await eligibility.mutateAsync(); const blocked = new Set(result.blocked.map(r => r.post_id)); const eligible = selectedIds.filter(id => !blocked.has(id)); setSelectedIds(eligible); setSearchParams(eligible.length ? { selected_post_ids: eligible.join(",") } : {}); setScheduleOpen(Boolean(eligible.length)); if (result.blocked.length) setMessage(`تم استبعاد ${result.blocked.length} منشور غير قابل للنشر.`); } catch (e) { setMessage(e instanceof Error ? e.message : "تعذر فحص أهلية النشر."); }
  };
  const updateItemTime = async (itemId: string, value: string) => { if (!detail) return; try { setDetail(await schedulesApi.updateItemTime(detail.id, itemId, new Date(value).toISOString())); setMessage("تم تحديث وقت العنصر."); void refresh(); } catch (e) { setMessage(e instanceof Error ? e.message : "تعذر تحديث الوقت."); } };
  const preview = async (postId: string) => { try { const p = await schedulesApi.telegramPreview(postId); setMessage(p.content); } catch (e) { setMessage(e instanceof Error ? e.message : "تعذر تحميل معاينة Telegram."); } };

  if (posts.isLoading) return <Status title="جاري تحميل المنشورات" />;
  if (posts.isError) return <Status title="تعذر تحميل المنشورات" detail={posts.error.message} error />;
  const items = posts.data?.items ?? [];
  return <section data-testid="publishing-workspace" className="space-y-6">
    <header><p className="text-sm font-semibold text-indigo-600">Workspace 03</p><h2 className="mt-1 text-3xl font-bold">مساحة النشر</h2><p className="mt-2 text-sm text-slate-600">المنشورات المعتمدة والمؤهلة فقط تدخل هنا.</p></header>
    <div className="rounded-2xl border bg-white p-5 shadow-sm"><div className="flex flex-wrap items-center justify-between gap-3"><h3 className="font-bold">المنشورات الجاهزة</h3><span data-testid="selection-count" className="rounded-full bg-indigo-50 px-3 py-1 text-sm font-bold text-indigo-700">{selectedIds.length} محدد</span></div><div className="mt-4 space-y-3">{items.length===0 && <p className="rounded-xl bg-slate-50 p-5 text-sm text-slate-500">لا توجد منشورات جاهزة للجدولة.</p>}{items.map(post => <label key={post.post_id} className="flex cursor-pointer items-start gap-3 rounded-xl border p-4"><input aria-label={`تحديد ${post.title}`} type="checkbox" checked={selectedIds.includes(post.post_id)} onChange={e => setSelection(post.post_id,e.target.checked)} className="mt-1 h-4 w-4"/><span><strong className="block">{post.title}</strong><span className="mt-1 block text-xs text-slate-500">{post.source_title}</span><span className="mt-2 block text-sm text-slate-600">{post.content_preview}</span></span></label>)}</div><button data-testid="create-plan" type="button" disabled={!selectedIds.length || eligibility.isPending} onClick={() => void openSchedule()} className="mt-5 rounded-xl bg-indigo-600 px-5 py-3 font-bold text-white disabled:opacity-40">إنشاء خطة ({selectedIds.length})</button></div>
    {message && <div role="status" className="whitespace-pre-wrap rounded-xl border bg-indigo-50 p-4 text-sm">{message}</div>}
    {scheduleOpen && <form data-testid="schedule-panel" className="rounded-2xl border-2 border-indigo-200 bg-white p-5" onSubmit={e => { e.preventDefault(); createSchedule.mutate(); }}><h3 className="font-bold">بيانات الجدولة</h3><div className="mt-4 grid gap-4 sm:grid-cols-2"><label>اسم الخطة<input aria-label="اسم الخطة" value={form.name} onChange={e=>setForm({...form,name:e.target.value})} className="mt-2 w-full rounded-xl border p-3"/></label><label>المنطقة الزمنية<input aria-label="المنطقة الزمنية" value={form.timezone} onChange={e=>setForm({...form,timezone:e.target.value})} className="mt-2 w-full rounded-xl border p-3"/></label><label>وقت البداية<input aria-label="وقت البداية" type="datetime-local" value={form.startAt} onChange={e=>setForm({...form,startAt:e.target.value})} className="mt-2 w-full rounded-xl border p-3"/></label><label>الفاصل بالدقائق<input aria-label="الفاصل بالدقائق" type="number" min="1" value={form.interval} onChange={e=>setForm({...form,interval:e.target.value})} className="mt-2 w-full rounded-xl border p-3"/></label></div><div className="mt-5 flex gap-2"><button data-testid="submit-schedule" type="submit" disabled={createSchedule.isPending} className="rounded-xl bg-emerald-600 px-5 py-3 font-bold text-white">حفظ الخطة</button><button type="button" onClick={()=>setScheduleOpen(false)} className="rounded-xl border px-5 py-3">إلغاء</button></div></form>}

    <section className="rounded-2xl border bg-white p-5 shadow-sm"><div className="flex items-center justify-between"><h3 className="font-bold">الخطط المحفوظة</h3><button type="button" onClick={() => void refresh()} className="rounded-lg border px-3 py-2 text-sm">تحديث</button></div><div className="mt-4 space-y-2">{(schedules.data?.items ?? []).map(s => <button key={s.id} type="button" onClick={() => void openDetail(s.id)} className="w-full rounded-xl border p-4 text-right hover:border-indigo-300"><div className="flex justify-between"><strong>{s.name}</strong><span>{s.status}</span></div><div className="mt-1 text-xs text-slate-500">{s.total_items} عناصر · {s.published_items} منشور · {s.failed_items} فشل · {s.timezone}</div></button>)}{!schedules.isLoading && !(schedules.data?.items.length) && <p className="text-sm text-slate-500">لا توجد خطط محفوظة.</p>}</div></section>

    {detail && <section className="rounded-2xl border-2 border-indigo-200 bg-white p-5 shadow-sm"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-xl font-bold">{detail.name}</h3><p className="text-sm text-slate-500">{detail.status} · {detail.timezone} · {detail.total_items} عناصر</p></div><div className="flex flex-wrap gap-2"><button type="button" onClick={()=>void action.mutateAsync({type:"activate",id:detail.id})} disabled={detail.status!=="DRAFT" && detail.status!=="PAUSED"} className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-bold text-white disabled:opacity-40">تفعيل النشر الآلي</button><button type="button" onClick={()=>action.mutate({type:"pause",id:detail.id})} disabled={detail.status!=="ACTIVE"} className="rounded-lg border px-3 py-2 text-sm disabled:opacity-40">إيقاف</button><button type="button" onClick={()=>action.mutate({type:"cancel",id:detail.id})} disabled={["COMPLETED","CANCELLED"].includes(detail.status)} className="rounded-lg bg-rose-600 px-3 py-2 text-sm font-bold text-white disabled:opacity-40">إلغاء</button><button type="button" onClick={()=>action.mutate({type:"retry",id:detail.id})} disabled={!detail.failed_items} className="rounded-lg bg-amber-600 px-3 py-2 text-sm font-bold text-white disabled:opacity-40">إعادة محاولة الفاشل</button></div></div><div className="mt-4 space-y-2">{detail.items.map(item => <div key={item.id} className="rounded-xl border p-4"><div className="flex flex-wrap justify-between gap-2"><strong>{item.position + 1}. {item.title}</strong><span>{item.status}</span></div><p className="mt-1 text-sm text-slate-600">{item.content_preview}</p><div className="mt-2 flex flex-wrap gap-2"><input type="datetime-local" defaultValue={new Date(item.scheduled_at).toISOString().slice(0,16)} onBlur={e=>void updateItemTime(item.id,e.target.value)} className="rounded-lg border p-2 text-sm"/><button type="button" onClick={()=>void preview(item.post_id)} className="rounded-lg border px-3 py-2 text-sm">معاينة Telegram</button>{item.status==="FAILED" && <button type="button" onClick={()=>void schedulesApi.retryItem(detail.id,item.id).then(r => setDetail(r.schedule))} className="rounded-lg bg-amber-100 px-3 py-2 text-sm">إعادة المحاولة</button>}</div>{item.last_error && <p className="mt-2 text-sm text-rose-700">{item.last_error}</p>}</div>)}</div></section>}

    <section className="rounded-2xl border bg-white p-5 shadow-sm"><div className="flex flex-wrap items-center justify-between gap-3"><h3 className="font-bold">القادم 7 أيام</h3><label className="text-sm">اليوم<input type="date" value={calendarDate} onChange={e=>setCalendarDate(e.target.value)} className="mr-2 rounded-lg border p-2"/></label></div><div className="mt-4 space-y-2">{(upcoming.data?.items ?? []).map(i=><div key={i.id} className="rounded-xl border p-3"><strong>{i.title}</strong><span className="mr-3 text-xs text-slate-500">{new Date(i.scheduled_at).toLocaleString("ar")}</span></div>)}</div><h4 className="mt-6 font-semibold">تقويم اليوم</h4><div className="mt-2 space-y-2">{(calendar.data?.items ?? []).map(i=><div key={i.id} className="rounded-xl border p-3 text-sm"><strong>{i.title}</strong> · {new Date(i.scheduled_at).toLocaleTimeString("ar",{hour:"2-digit",minute:"2-digit"})} · {i.status}</div>)}</div></section>
    <Link to="/posts/workspace" className="inline-block text-sm font-semibold text-indigo-600">العودة إلى مصنع المحتوى ←</Link>
  </section>;
}
function Status({ title, detail, error = false }: { title: string; detail?: string; error?: boolean }) { return <div role={error ? "alert" : "status"} className="rounded-2xl border bg-white p-8"><h2 className="font-bold">{title}</h2>{detail && <p className="mt-2 text-sm text-slate-600">{detail}</p>}</div>; }
