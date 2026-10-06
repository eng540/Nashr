import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useState } from "react";
import { postsApi } from "../../shared/api/postsApi";
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

  const posts = useQuery({
    queryKey: ["post-bank", status, query],
    queryFn: () => postsApi.list({ status: status || undefined, query }),
  });

  const review = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "approve" | "reject" }) =>
      action === "approve" ? postsApi.approve(id, reviewNote) : postsApi.reject(id, reviewNote),
    onSuccess: () => {
      setEditing(null);
      setReviewNote("");
      void client.invalidateQueries({ queryKey: ["post-bank"] });
    },
  });

  const save = useMutation({
    mutationFn: () => postsApi.update(editing!, content),
    onSuccess: () => {
      setEditing(null);
      void client.invalidateQueries({ queryKey: ["post-bank"] });
    },
  });

  if (posts.isLoading) return <p role="status">جاري تحميل بنك المنشورات...</p>;
  if (posts.isError) return <p role="alert">{posts.error.message}</p>;

  const items = posts.data?.items ?? [];
  const selectedApproved = items.filter((post) => selected.includes(post.post_id) && post.status === "APPROVED");

  return (
    <section data-testid="post-bank-workspace" className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-indigo-600">Workspace 02</p>
          <h2 className="mt-1 text-3xl font-bold">بنك المنشورات</h2>
          <p className="mt-2 text-sm text-slate-600">إنتاج، مراجعة واعتماد. هذه الصفحة لا تعتمد على DOM مساحة النشر.</p>
        </div>
        <Link to="/publishing" className="rounded-xl border px-4 py-2 text-sm font-semibold">مساحة النشر</Link>
      </header>

      <div className="rounded-2xl border bg-white p-4 shadow-sm">
        <div className="grid gap-3 sm:grid-cols-[180px_1fr_auto]">
          <select aria-label="حالة المنشور" value={status} onChange={(e) => { setStatus(e.target.value); setSearchParams(e.target.value ? { status: e.target.value } : {}); }} className="rounded-xl border p-3">
            <option value="">كل الحالات</option>
            <option value="DRAFT">مسودة</option>
            <option value="APPROVED">معتمد</option>
            <option value="REJECTED">مرفوض</option>
          </select>
          <input aria-label="بحث المنشورات" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="ابحث..." className="rounded-xl border p-3" />
          <span className="rounded-xl bg-slate-100 px-4 py-3 text-sm font-semibold">{selected.length} محدد</span>
        </div>
      </div>

      <div className="space-y-3">
        {items.map((post) => {
          const checked = selected.includes(post.post_id);
          return (
            <article key={post.post_id} className="rounded-2xl border bg-white p-5 shadow-sm">
              <div className="flex items-start gap-3">
                <input
                  aria-label={`تحديد ${post.title}`}
                  type="checkbox"
                  checked={checked}
                  onChange={(e) => setSelected(toggleSelection(selected, post.post_id, e.target.checked))}
                  className="mt-1 h-4 w-4"
                />
                <button type="button" onClick={() => { setEditing(post.post_id); setContent(post.content); setReviewNote(post.review_note ?? ""); }} className="min-w-0 flex-1 text-right">
                  <strong className="block">{post.title}</strong>
                  <span className="mt-1 block text-xs text-slate-500">{post.source_title} · {post.status}</span>
                  <p className="mt-2 text-sm leading-7 text-slate-600">{post.content_preview}</p>
                </button>
              </div>
            </article>
          );
        })}
      </div>

      {selectedApproved.length > 0 && (
        <button
          type="button"
          data-testid="go-publishing"
          onClick={() => navigate(`/publishing?selected_post_ids=${selectedApproved.map((post) => post.post_id).join(",")}`)}
          className="sticky bottom-4 rounded-xl bg-indigo-600 px-5 py-3 text-sm font-bold text-white shadow-lg"
        >
          الانتقال إلى النشر ({selectedApproved.length})
        </button>
      )}

      {editing && (
        <div className="fixed inset-0 z-20 grid place-items-center bg-slate-950/30 p-4">
          <div role="dialog" className="w-full max-w-3xl rounded-2xl bg-white p-6 shadow-xl">
            <h3 className="text-xl font-bold">مراجعة المنشور</h3>
            <textarea aria-label="محتوى المنشور" value={content} onChange={(e) => setContent(e.target.value)} className="mt-4 min-h-48 w-full rounded-xl border p-4" />
            <input aria-label="ملاحظة المراجعة" value={reviewNote} onChange={(e) => setReviewNote(e.target.value)} placeholder="ملاحظة أو سبب الرفض" className="mt-3 w-full rounded-xl border p-3" />
            {review.isError && <p role="alert" className="mt-3 text-sm text-rose-700">{review.error.message}</p>}
            {save.isError && <p role="alert" className="mt-3 text-sm text-rose-700">{save.error.message}</p>}
            <div className="mt-5 flex flex-wrap gap-2">
              <button type="button" onClick={() => save.mutate()} disabled={save.isPending} className="rounded-xl border px-4 py-2 font-semibold">حفظ</button>
              <button type="button" onClick={() => review.mutate({ id: editing, action: "approve" })} disabled={review.isPending} className="rounded-xl bg-emerald-600 px-4 py-2 font-semibold text-white">اعتماد</button>
              <button type="button" onClick={() => { if (reviewNote.trim()) review.mutate({ id: editing, action: "reject" }); }} disabled={review.isPending || !reviewNote.trim()} className="rounded-xl bg-rose-600 px-4 py-2 font-semibold text-white">رفض</button>
              <button type="button" onClick={() => setEditing(null)} className="rounded-xl bg-slate-100 px-4 py-2 font-semibold">إغلاق</button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
