import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { genericArtifactsApi, type GenericArtifactReviewStatus, type GenericReviewableArtifact } from "../../shared/api/artifactsApi";
import { productionJobsApi, type ProductionProductOption, type ProductionRecipeOption } from "../../shared/api/productionJobsApi";

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
  const [cardProducts, setCardProducts] = useState<Record<string, string>>({});
  const products = useQuery({ queryKey: ["design-card-products"], queryFn: () => productionJobsApi.products() });
  const recipes = useQuery({ queryKey: ["design-card-recipes"], queryFn: () => productionJobsApi.recipes() });
  const eligibleCardProducts = (products.data ?? []).filter((product: ProductionProductOption) => {
    const version = product.versions.find((item) => item.version === product.active_version);
    if (!version) return false;
    const recipe = recipes.data?.find((item: ProductionRecipeOption) => item.key === version.definition.recipe_key);
    const recipeVersion = recipe?.versions.find((item) => item.version === recipe.active_version);
    return recipeVersion?.status === "PUBLISHED" && recipeVersion.stages.some((stage) => stage.capability_key === "render_approved_text_card" && stage.capability_version === 1);
  });
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
  const createCard = useMutation({
    mutationFn: async ({ artifact, productKey }: { artifact: GenericReviewableArtifact; productKey: string }) => {
      const product = eligibleCardProducts.find((item) => item.key === productKey);
      const version = product?.versions.find((item) => item.version === product.active_version);
      if (!product || !version) throw new Error("تعذر العثور على إصدار منتج البطاقات المنشور.");
      return productionJobsApi.create({
        scope: "SELECTION",
        source_artifact_id: artifact.id,
        product_key: product.key,
        recipe_key: version.definition.recipe_key,
        idempotency_key: `design-card:${artifact.id}:${product.key}:v${version.version}`,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["production-jobs"] });
      queryClient.invalidateQueries({ queryKey: ["generic-artifacts"] });
    },
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
        {status === "APPROVED" && artifact.kind === "TEXT" && artifact.content ? <div className="flex flex-wrap items-center gap-2 rounded-xl border border-indigo-100 bg-indigo-50 p-3">
          <label className="text-sm font-semibold">إنشاء بطاقة من هذا النص المعتمد
            <select aria-label={`منتج البطاقة ${artifact.id}`} value={cardProducts[artifact.id] ?? ""} onChange={(event) => setCardProducts((current) => ({ ...current, [artifact.id]: event.target.value }))} className="mr-2 rounded-lg border bg-white p-2 font-normal">
              <option value="">اختر منتج بطاقات منشورًا</option>
              {eligibleCardProducts.map((product) => <option key={product.key} value={product.key}>{product.name} · {product.key}</option>)}
            </select>
          </label>
          <button type="button" onClick={() => createCard.mutate({ artifact, productKey: cardProducts[artifact.id] ?? "" })} disabled={!cardProducts[artifact.id] || createCard.isPending} className="rounded-lg bg-indigo-600 px-3 py-2 text-sm font-semibold text-white">إنتاج البطاقة</button>
          {products.isLoading || recipes.isLoading ? <span className="text-xs">تحميل منتجات البطاقات...</span> : null}
          {!products.isLoading && eligibleCardProducts.length === 0 ? <span className="text-xs text-slate-600">لا يوجد منتج منشور بوصفة render_approved_text_card.</span> : null}
        </div> : null}
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
    {(save.isError || approve.isError || reject.isError || createCard.isError) ? <p role="alert" className="text-sm text-rose-700">{(save.error ?? approve.error ?? reject.error ?? createCard.error)?.message}</p> : null}
  </section>;
}
