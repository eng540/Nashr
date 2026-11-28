import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { postsApi } from "../../shared/api/postsApi";
import type { BookMapMaterial } from "../../shared/api/productionJobsApi";

const PAGE_SIZE = 10;
const statusLabel = (status: string) => ({DRAFT: "مسودة", APPROVED: "معتمد", REJECTED: "مرفوض"}[status] ?? status);

function SavedMaterialPosts({ sourceId, materialId }: { sourceId: string; materialId: string }) {
  const [page, setPage] = useState(0);
  const posts = useQuery({
    queryKey: ["source-material-posts", sourceId, materialId, page],
    queryFn: async ({ signal }) => {
      const result = await postsApi.list({ sourceId, knowledgeUnitId: materialId, limit: PAGE_SIZE, offset: page * PAGE_SIZE }, signal);
      if (result.items.some((post) => post.source_id !== sourceId || post.knowledge_unit_id !== materialId || !post.post_id)) {
        throw new Error("لم تتطابق المنشورات المقروءة مع المادة المحددة.");
      }
      return result;
    },
    retry: false,
    staleTime: 0,
  });
  return <section aria-label="المنشورات المحفوظة لهذه المادة" className="mt-3 space-y-2 rounded-lg border bg-white p-3">
    <h5 className="font-semibold">المنشورات المحفوظة لهذه المادة</h5>
    <p className="text-xs text-slate-600">قد توجد عدة نسخ من المادة. وجود منشور أو اعتماده لا يعني نشره. فتحه لا يحفظ أو يعتمد أو ينشر شيئاً.</p>
    {posts.isFetching ? <p role="status">جارٍ قراءة منشورات المادة...</p> : posts.isError ? <div role="alert">تعذر قراءة منشورات المادة: {posts.error.message}<button type="button" className="mr-2 rounded border px-2 py-1" onClick={() => posts.refetch()}>إعادة قراءة المنشورات</button></div> : posts.data ? <>
      <p className="text-xs">{posts.data.total} منشور محفوظ</p>
      {!posts.data.total ? <p>لا يوجد منشور محفوظ لهذه المادة حالياً.</p> : null}
      <ul className="space-y-2">{posts.data.items.map((post) => <li key={post.post_id} className="rounded border p-2">
        <Link className="font-semibold text-indigo-700 underline" to={`/bank?post_id=${encodeURIComponent(post.post_id)}`}>فتح المنشور: {post.title}</Link>
        <p>المراجعة: {statusLabel(post.status)} · {post.published ? "له سجل نشر ناجح" : "لا يوجد سجل نشر ناجح"}</p>
        <p className="break-all text-xs text-slate-500">{post.post_id}</p>
      </li>)}</ul>
      {posts.data.total > PAGE_SIZE || page > 0 ? <nav aria-label="صفحات منشورات المادة" className="flex flex-wrap items-center gap-2">
        <button type="button" className="rounded border px-2 py-1 disabled:opacity-40" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>المنشورات السابقة</button>
        <span>صفحة {page + 1} من {Math.max(1, Math.ceil(posts.data.total / PAGE_SIZE))}</span>
        <button type="button" className="rounded border px-2 py-1 disabled:opacity-40" disabled={(page + 1) * PAGE_SIZE >= posts.data.total} onClick={() => setPage((value) => value + 1)}>المنشورات التالية</button>
      </nav> : null}
    </> : null}
  </section>;
}

export function SourceMaterialReview({ sourceId, material, focused = false }: { sourceId: string; material: BookMapMaterial; focused?: boolean }) {
  const [open, setOpen] = useState(focused);
  const target = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    if (!focused) return;
    setOpen(true);
    const frame = requestAnimationFrame(() => { target.current?.focus({preventScroll:true}); target.current?.scrollIntoView({block:"center"}); });
    return () => cancelAnimationFrame(frame);
  }, [focused, sourceId, material.id]);
  return <details ref={target} tabIndex={focused ? -1 : undefined} open={open} onToggle={(event) => setOpen(event.currentTarget.open)} className="min-w-0 rounded-lg border bg-white p-3" data-testid={`source-material-${material.id}`}>
    <summary className="cursor-pointer font-semibold">{material.position}. {material.title} · عرض المادة ومنشوراتها</summary>
    {open ? <div className="mt-3 space-y-2">
      <p className="text-xs text-slate-600">النص والمرجع المحفوظان عند الاستخراج، وليسا تحققاً من صحة المحتوى أو حداثة المصدر. لا يُعدّلان نص المنشور.</p>
      {material.source_reference ? <p className="break-words">المرجع: {material.source_reference}</p> : <p>لا يوجد مرجع محفوظ لهذه المادة.</p>}
      {material.discovery_page_start != null ? <p>الصفحات المكتشفة: {material.discovery_page_start}{material.discovery_page_end != null && material.discovery_page_end !== material.discovery_page_start ? `–${material.discovery_page_end}` : ""}</p> : null}
      {material.content?.trim() ? <p dir="auto" className="whitespace-pre-wrap break-words rounded bg-slate-50 p-3 [overflow-wrap:anywhere]">{material.content}</p> : <p>لا يوجد نص محفوظ لهذه المادة.</p>}
      <SavedMaterialPosts sourceId={sourceId} materialId={material.id} />
    </div> : null}
  </details>;
}
