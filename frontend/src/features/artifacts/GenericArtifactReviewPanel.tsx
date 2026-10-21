import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { genericArtifactsApi, type GenericArtifactReviewStatus, type GenericReviewableArtifact } from "../../shared/api/artifactsApi";
import { productionJobsApi, type ProductionProductOption, type ProductionRecipeOption } from "../../shared/api/productionJobsApi";
import { postsApi } from "../../shared/api/postsApi";

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
  const [quizDrafts, setQuizDrafts] = useState<Record<string, { id: string; status: string; external_id?: string | null }>>({});
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
    queryFn: () => genericArtifactsApi.list(status),
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
  const createQuizDraft = useMutation({
    mutationFn: (id: string) => genericArtifactsApi.createQuizDraft(id),
    onSuccess: (publication, artifactId) => setQuizDrafts((current) => ({ ...current, [artifactId]: { id: publication.id, status: publication.status } })),
  });
  const publishQuiz = useMutation({
    mutationFn: ({ artifactId, publicationId, content }: { artifactId: string; publicationId: string; content: string }) => genericArtifactsApi.publishQuiz(publicationId, content),
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
    <div className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-4 space-y-3">
      <h3 className="font-bold">إنتاج تصميم من منشور معتمد</h3>
      <p className="text-sm text-slate-600">يُستخدم نص Post المعتمد مباشرةً دون إنشاء TEXT Artifact وسيط. يظل اعتماد الصورة ومراجعتها مستقلًا.</p>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="text-sm font-semibold">المنشور المصدر
          <select aria-label="المنشور المصدر للتصميم" value={selectedPostId} onChange={(event) => setSelectedPostId(event.target.value)} className="mt-1 w-full rounded-lg border bg-white p-2 font-normal">
            <option value="">اختر منشورًا معتمدًا</option>
            {(approvedPosts.data?.items ?? []).filter((post) => post.status === "APPROVED" && post.content.trim()).map((post) => <option key={post.post_id} value={post.post_id}>{post.title} · {post.post_id.slice(0, 8)}</option>)}
          </select>
        </label>
        <label className="text-sm font-semibold">منتج التصميم المنشور
          <select aria-label="منتج التصميم من المنشور" value={postProductKey} onChange={(event) => setPostProductKey(event.target.value)} className="mt-1 w-full rounded-lg border bg-white p-2 font-normal">
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
        {status === "APPROVED" && artifact.kind === "QUIZ" ? <div className="rounded-xl border border-emerald-100 bg-emerald-50 p-3 space-y-2">
          <p className="text-sm font-semibold">اختبار تفاعلي معتمد</p>
          <p className="text-sm text-slate-700">السؤال: {String((artifact.metadata.quiz as Record<string, unknown> | undefined)?.question ?? artifact.content ?? "")}</p>
          <ol className="list-decimal space-y-1 pr-6 text-sm text-slate-700">{(Array.isArray((artifact.metadata.quiz as Record<string, unknown> | undefined)?.options) ? (artifact.metadata.quiz as Record<string, unknown>).options as string[] : []).map((option, index) => <li key={index}>{option}{index === Number((artifact.metadata.quiz as Record<string, unknown> | undefined)?.correct_option_id) ? " ✓ الإجابة الصحيحة" : ""}</li>)}</ol>
          {quizDrafts[artifact.id] ? <p role="status" className="text-xs">سجل Telegram: {quizDrafts[artifact.id].id} · الحالة {quizDrafts[artifact.id].status}{quizDrafts[artifact.id].external_id ? ` · معرّف Telegram ${quizDrafts[artifact.id].external_id}` : ""}</p> : null}
          {!quizDrafts[artifact.id] ? <button type="button" onClick={() => createQuizDraft.mutate(artifact.id)} disabled={createQuizDraft.isPending} className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-semibold text-white">{createQuizDraft.isPending ? "جارٍ إنشاء المسودة..." : "إنشاء مسودة Telegram"}</button> : null}
          {quizDrafts[artifact.id]?.status === "DRAFT" ? <button type="button" onClick={() => publishQuiz.mutate({ artifactId: artifact.id, publicationId: quizDrafts[artifact.id].id, content: String((artifact.metadata.quiz as Record<string, unknown> | undefined)?.question ?? artifact.content ?? "") })} disabled={publishQuiz.isPending} className="rounded-lg bg-indigo-700 px-3 py-2 text-sm font-semibold text-white">{publishQuiz.isPending ? "جارٍ النشر..." : "نشر الاختبار الآن"}</button> : null}
          {createQuizDraft.isError ? <p role="alert" className="text-sm text-rose-700">{createQuizDraft.error.message}</p> : null}
          {publishQuiz.isError ? <p role="alert" className="text-sm text-rose-700">{publishQuiz.error.message}</p> : null}
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
    {activeCardJob ? <div role="status" className="rounded-xl border border-indigo-100 bg-indigo-50 p-3 text-sm">
      <p className="font-semibold">مهمة إنتاج التصميم · {activeCardJob}</p>
      {activeJob.isLoading ? <p>جارٍ تحميل حالة المهمة...</p> : null}
      {activeJob.isError ? <p className="text-rose-700">تعذر تحديث حالة الإنتاج: {activeJob.error.message}</p> : null}
      {activeJob.data?.status === "QUEUED" || activeJob.data?.status === "RUNNING" ? <p>الإنتاج جارٍ · التقدم {activeJob.data.progress_percent ?? 0}% · اكتمل {activeJob.data.completed_items ?? 0} من {activeJob.data.total_items ?? 1}</p> : null}
      {activeJob.data?.status === "COMPLETED" ? <p className="text-emerald-800">اكتمل الإنتاج. حُدثت قائمة المخرجات؛ انتقل إلى حالة «قيد المراجعة» لمعاينة التصميم.</p> : null}
      {activeJob.data?.status === "FAILED" ? <p className="text-rose-700">فشل الإنتاج: {activeJob.data.error_message ?? "لم يُرجع النظام تفاصيل إضافية."}</p> : null}
    </div> : null}
    {(save.isError || approve.isError || reject.isError || createCard.isError) ? <p role="alert" className="text-sm text-rose-700">{(save.error ?? approve.error ?? reject.error ?? createCard.error)?.message}</p> : null}
  </section>;
}
