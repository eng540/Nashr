import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router";
import { useMemo, useState } from "react";
import { postsApi } from "../../shared/api/postsApi";
import { schedulesApi } from "../../shared/api/schedulesApi";
import { toggleSelection, selectionFromQuery } from "../../shared/utils/selection";
import { localDateTimeToUtcISOString } from "../../shared/utils/timezone";

const DEFAULT_TIMEZONE = "Asia/Aden";

export function PublishingPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedIds, setSelectedIds] = useState<string[]>(() => selectionFromQuery(searchParams.get("selected_post_ids")));
  const [scheduleOpen, setScheduleOpen] = useState(Boolean(searchParams.get("selected_post_ids")));
  const [message, setMessage] = useState("");
  const [form, setForm] = useState({ name: "خطة نشر", timezone: DEFAULT_TIMEZONE, startAt: "", interval: "60" });

  const posts = useQuery({
    queryKey: ["publishing", "eligible-posts"],
    queryFn: () => postsApi.list({ status: "APPROVED", publicationState: "ELIGIBLE" }),
  });

  const eligibility = useMutation({
    mutationFn: () => schedulesApi.eligibility(selectedIds),
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
    onSuccess: (schedule) => {
      setMessage(`تم إنشاء الخطة بنجاح: ${schedule.name}`);
      setScheduleOpen(false);
    },
  });

  const selectedPosts = useMemo(
    () => (posts.data?.items ?? []).filter((post) => selectedIds.includes(post.post_id)),
    [posts.data?.items, selectedIds],
  );

  const setSelection = (id: string, checked: boolean) => {
    const next = toggleSelection(selectedIds, id, checked);
    setSelectedIds(next);
    setSearchParams(next.length ? { selected_post_ids: next.join(",") } : {});
  };

  const openSchedule = async () => {
    if (!selectedIds.length) return;
    setMessage("");
    try {
      const result = await eligibility.mutateAsync();
      const blocked = new Set(result.blocked.map((row) => row.post_id));
      const eligible = selectedIds.filter((id) => !blocked.has(id));
      setSelectedIds(eligible);
      setSearchParams(eligible.length ? { selected_post_ids: eligible.join(",") } : {});
      setScheduleOpen(Boolean(eligible.length));
      if (result.blocked.length) setMessage(`تم استبعاد ${result.blocked.length} منشور غير قابل للنشر.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "تعذر فحص أهلية النشر.");
    }
  };

  if (posts.isLoading) return <Status title="جاري تحميل المنشورات" />;
  if (posts.isError) return <Status title="تعذر تحميل المنشورات" detail={posts.error.message} error />;
  const items = posts.data?.items ?? [];

  return (
    <section data-testid="publishing-workspace" className="space-y-6">
      <header>
        <p className="text-sm font-semibold text-indigo-600">Workspace 03</p>
        <h2 className="mt-1 text-3xl font-bold">مساحة النشر</h2>
        <p className="mt-2 text-sm text-slate-600">المنشورات المعتمدة فقط تدخل هنا. لا يوجد اعتماد على DOM مصنع المحتوى.</p>
      </header>

      <div className="rounded-2xl border bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="font-bold">المنشورات الجاهزة</h3>
          <span data-testid="selection-count" className="rounded-full bg-indigo-50 px-3 py-1 text-sm font-bold text-indigo-700">
            {selectedIds.length} محدد
          </span>
        </div>
        <div className="mt-4 space-y-3">
          {items.length === 0 && <p className="rounded-xl bg-slate-50 p-5 text-sm text-slate-500">لا توجد منشورات جاهزة للجدولة.</p>}
          {items.map((post) => (
            <label key={post.post_id} className="flex cursor-pointer items-start gap-3 rounded-xl border p-4 hover:border-indigo-300">
              <input
                aria-label={`تحديد ${post.title}`}
                type="checkbox"
                checked={selectedIds.includes(post.post_id)}
                onChange={(event) => setSelection(post.post_id, event.target.checked)}
                className="mt-1 h-4 w-4"
              />
              <span className="min-w-0">
                <strong className="block">{post.title}</strong>
                <span className="mt-1 block text-xs text-slate-500">{post.source_title} · {post.topic_title ?? "بدون محور"}</span>
                <span className="mt-2 block text-sm leading-6 text-slate-600">{post.content_preview}</span>
              </span>
            </label>
          ))}
        </div>
        <button
          data-testid="create-plan"
          type="button"
          disabled={selectedIds.length === 0 || eligibility.isPending}
          onClick={() => void openSchedule()}
          className="mt-5 rounded-xl bg-indigo-600 px-5 py-3 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-40"
        >
          إنشاء خطة ({selectedIds.length})
        </button>
      </div>

      {message && <div role="status" className="rounded-xl border border-indigo-200 bg-indigo-50 p-4 text-sm text-indigo-800">{message}</div>}

      {scheduleOpen && (
        <form
          data-testid="schedule-panel"
          className="rounded-2xl border-2 border-indigo-200 bg-white p-5 shadow-sm"
          onSubmit={(event) => { event.preventDefault(); createSchedule.mutate(); }}
        >
          <div className="mb-4">
            <h3 className="font-bold">بيانات الجدولة</h3>
            <p className="mt-1 text-xs text-slate-500">{selectedPosts.length} منشور في الخطة.</p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="text-sm font-semibold">
              اسم الخطة
              <input aria-label="اسم الخطة" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="mt-2 w-full rounded-xl border p-3" required />
            </label>
            <label className="text-sm font-semibold">
              المنطقة الزمنية
              <input aria-label="المنطقة الزمنية" value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })} className="mt-2 w-full rounded-xl border p-3" required />
            </label>
            <label className="text-sm font-semibold">
              وقت البداية
              <input aria-label="وقت البداية" type="datetime-local" value={form.startAt} onChange={(e) => setForm({ ...form, startAt: e.target.value })} className="mt-2 w-full rounded-xl border p-3" required />
            </label>
            <label className="text-sm font-semibold">
              الفاصل بالدقائق
              <input aria-label="الفاصل بالدقائق" type="number" min="1" value={form.interval} onChange={(e) => setForm({ ...form, interval: e.target.value })} className="mt-2 w-full rounded-xl border p-3" required />
            </label>
          </div>
          {createSchedule.isError && <p role="alert" className="mt-4 text-sm text-rose-700">{createSchedule.error.message}</p>}
          <div className="mt-5 flex gap-2">
            <button data-testid="submit-schedule" type="submit" disabled={createSchedule.isPending} className="rounded-xl bg-emerald-600 px-5 py-3 text-sm font-bold text-white disabled:opacity-40">
              {createSchedule.isPending ? "جارٍ الحفظ..." : "حفظ الخطة"}
            </button>
            <button type="button" onClick={() => setScheduleOpen(false)} className="rounded-xl border px-5 py-3 text-sm font-semibold">إلغاء</button>
          </div>
        </form>
      )}

      <Link to="/posts/workspace" className="inline-block text-sm font-semibold text-indigo-600">العودة إلى مصنع المحتوى ←</Link>
    </section>
  );
}

function Status({ title, detail, error = false }: { title: string; detail?: string; error?: boolean }) {
  return <div role={error ? "alert" : "status"} className="rounded-2xl border bg-white p-8"><h2 className="font-bold">{title}</h2>{detail && <p className="mt-2 text-sm text-slate-600">{detail}</p>}</div>;
}
