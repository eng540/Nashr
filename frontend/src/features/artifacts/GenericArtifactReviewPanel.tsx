import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { genericArtifactsApi, type GenericArtifactReviewStatus, type GenericReviewableArtifact } from "../../shared/api/artifactsApi";

function GenericArtifactMediaPreview({ artifact }: { artifact: GenericReviewableArtifact }) {
  const media = useQuery({
    queryKey: ["generic-artifact-media-url", artifact.id],
    queryFn: () => genericArtifactsApi.mediaUrl(artifact.id),
    enabled: Boolean(artifact.storage_uri) && ["IMAGE", "VIDEO", "AUDIO"].includes(artifact.kind),
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
  if (artifact.kind === "IMAGE") {
    return <img src={media.data.url} alt={title} className="max-h-[32rem] max-w-full rounded-xl border object-contain" />;
  }
  if (artifact.kind === "VIDEO") {
    return <video src={media.data.url} controls preload="metadata" className="max-h-[32rem] w-full rounded-xl border" />;
  }
  if (artifact.kind === "AUDIO") {
    return <audio src={media.data.url} controls preload="metadata" className="w-full" />;
  }
  return <p className="break-all rounded-lg bg-slate-50 p-3 text-sm">مخرج محفوظ في تخزين الوسائط.</p>;
}


export function GenericArtifactReviewPanel() {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<GenericArtifactReviewStatus>("DRAFT");
  const [drafts, setDrafts] = useState<Record<string, { content?: string; review_note?: string }>>({});
  const artifacts = useQuery({
    queryKey: ["generic-artifacts", status],
    queryFn: () => genericArtifactsApi.list(status),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["generic-artifacts"] });
  const save = useMutation({
    mutationFn: (id: string) => genericArtifactsApi.update(id, { content: drafts[id]?.content }),
    onSuccess: refresh,
  });
  const approve = useMutation({
    mutationFn: (id: string) => genericArtifactsApi.approve(id, drafts[id]?.review_note),
    onSuccess: refresh,
  });
  const reject = useMutation({
    mutationFn: (id: string) => genericArtifactsApi.reject(id, drafts[id]?.review_note ?? ""),
    onSuccess: refresh,
  });

  return <section className="space-y-3 rounded-2xl border bg-white p-5 shadow-sm" aria-label="مراجعة المخرجات العامة">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 className="text-lg font-bold">مراجعة المخرجات العامة</h2>
        <p className="mt-1 text-sm text-slate-500">النصوص والوسائط التي لا تمثل منشورات Telegram تمر بمراجعة مستقلة.</p>
      </div>
      <label className="text-sm font-semibold">الحالة
        <select aria-label="حالة مراجعة المخرجات" value={status} onChange={(event) => setStatus(event.target.value as GenericArtifactReviewStatus)} className="mr-2 rounded-lg border p-2 font-normal">
          <option value="DRAFT">قيد المراجعة</option>
          <option value="APPROVED">معتمد</option>
          <option value="REJECTED">مرفوض</option>
        </select>
      </label>
    </div>
    {artifacts.isLoading ? <p role="status" className="text-sm text-slate-500">تحميل المخرجات...</p> : null}
    {artifacts.isError ? <p role="alert" className="text-sm text-rose-700">تعذر تحميل المخرجات: {artifacts.error.message}</p> : null}
    {artifacts.data?.length === 0 ? <div className="rounded-xl border border-dashed p-5 text-sm text-slate-500">لا توجد مخرجات في هذه الحالة.</div> : null}
    <div className="space-y-3">
      {(artifacts.data ?? []).map((artifact) => <article key={artifact.id} className="space-y-3 rounded-xl border p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <strong>{artifact.kind} · {artifact.mime_type ?? "نوع غير محدد"}</strong>
            <p className="mt-1 break-all text-xs text-slate-500">Artifact {artifact.id} · المادة {artifact.source_knowledge_unit_id}</p>
          </div>
          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs">{artifact.review_status}</span>
        </div>
        {artifact.content !== null ? <textarea aria-label={`محتوى المخرج ${artifact.id}`} value={drafts[artifact.id]?.content ?? artifact.content} onChange={(event) => setDrafts((current) => ({ ...current, [artifact.id]: { ...current[artifact.id], content: event.target.value } }))} disabled={status !== "DRAFT"} className="min-h-32 w-full rounded-xl border p-3 text-sm leading-7"/> : <GenericArtifactMediaPreview artifact={artifact} />}
        <p className="break-all text-xs text-slate-500">عقد المخرج: {artifact.output_contract_key ?? "غير محدد"} · الإصدار {artifact.output_contract_version ?? "—"}</p>
        {Object.keys(artifact.metadata).length > 0 ? <pre className="overflow-x-auto rounded-lg bg-slate-50 p-3 text-xs">{JSON.stringify(artifact.metadata, null, 2)}</pre> : null}
        <input aria-label={`ملاحظة مراجعة المخرج ${artifact.id}`} value={drafts[artifact.id]?.review_note ?? artifact.review_note ?? ""} onChange={(event) => setDrafts((current) => ({ ...current, [artifact.id]: { ...current[artifact.id], review_note: event.target.value } }))} placeholder="ملاحظة المراجعة أو سبب الرفض" disabled={status !== "DRAFT"} className="w-full rounded-xl border p-3 text-sm"/>
        {status === "DRAFT" ? <div className="flex flex-wrap gap-2">
          {artifact.content !== null ? <button type="button" onClick={() => save.mutate(artifact.id)} disabled={save.isPending} className="rounded-lg border px-3 py-2 text-sm font-semibold">حفظ التعديل</button> : null}
          <button type="button" onClick={() => approve.mutate(artifact.id)} disabled={approve.isPending} className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white">اعتماد المخرج</button>
          <button type="button" onClick={() => reject.mutate(artifact.id)} disabled={reject.isPending || !(drafts[artifact.id]?.review_note ?? "").trim()} className="rounded-lg bg-rose-600 px-3 py-2 text-sm font-semibold text-white">رفض المخرج</button>
        </div> : null}
      </article>)}
    </div>
    {(save.isError || approve.isError || reject.isError) ? <p role="alert" className="text-sm text-rose-700">{(save.error ?? approve.error ?? reject.error)?.message}</p> : null}
  </section>;
}
