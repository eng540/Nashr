import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router";

import { postForm } from "../../shared/api/client";
import { PageHeader } from "../../shared/components/ui";
import { productionJobsApi, type SourceSummary } from "../../shared/api/productionJobsApi";

function sourceStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    READY: "جاهز",
    STORED: "محفوظ، لم يبدأ التحليل",
    PROCESSING: "قيد المعالجة",
    PENDING: "قيد الانتظار",
    FAILED: "تعذّرت المعالجة",
  };
  return labels[status] ?? status;
}

function SourceBookMap({ sourceId }: { sourceId: string }) {
  const bookMap = useQuery({
    queryKey: ["source-book-map", sourceId],
    queryFn: () => productionJobsApi.bookMap(sourceId),
  });
  if (bookMap.isLoading) return <p role="status" className="mt-3 text-sm text-slate-500">جارٍ تحميل بنية الكتاب...</p>;
  if (bookMap.isError) return <p role="alert" className="mt-3 text-sm text-rose-700">تعذر تحميل بنية الكتاب: {bookMap.error.message}</p>;
  const data = bookMap.data;
  if (!data) return null;
  return (
    <div className="mt-3 space-y-3 rounded-xl border bg-slate-50 p-4" data-testid={`book-map-${sourceId}`}>
      {data.topics.length > 0 ? (
        <div>
          <h4 className="text-sm font-bold">المحاور ({data.topics.length})</h4>
          <ol className="mt-2 list-decimal space-y-1 pr-6 text-sm text-slate-700">
            {data.topics.map((topic) => (
              <li key={topic.id}>
                {topic.position}. {topic.title}
                <span className="text-xs text-slate-500"> · {topic.materials.length} مادة</span>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
      <div>
        <h4 className="text-sm font-bold">المواد ({data.count})</h4>
        <ul className="mt-2 max-h-72 space-y-1 overflow-y-auto text-sm text-slate-700">
          {data.materials.map((material) => (
            <li key={material.id} className="flex flex-wrap items-center gap-2 border-b border-slate-200 pb-1 last:border-b-0">
              <span className="font-semibold">{material.position}.</span>
              <span>{material.title}</span>
              {material.has_post ? <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs text-emerald-800">له منشور</span> : null}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function SourcesPage() {
  const [params]=useSearchParams();
  const [analysis,setAnalysis]=useState(params.has("analysis"));
  const [analysisId,setAnalysisId]=useState("");
  const [showOther,setShowOther]=useState(false);
  const queryClient = useQueryClient();
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [query, setQuery] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const sources = useQuery({
    queryKey: ["sources-library"],
    queryFn: () => productionJobsApi.sources(),
  });

  const upload = useMutation({
    mutationFn: () => {
      if (!uploadFile) throw new Error("اختر ملف PDF أولًا.");
      const form = new FormData();
      form.append("file", uploadFile);
      return postForm<{ id: string; status: string; filename: string }>("/sources", form);
    },
    onSuccess: () => {
      setUploadFile(null);
      queryClient.invalidateQueries({ queryKey: ["sources-library"] });
    },
  });

  const items = (sources.data ?? []).filter((source: SourceSummary) => {
    if (!showOther && source.mime_type!=="application/pdf") return false;
    const haystack = `${source.book_title} ${source.filename}`.toLowerCase();
    return haystack.includes(query.trim().toLowerCase());
  });

  return (
    <section className="space-y-4" dir="rtl">
      <PageHeader
        eyebrow="المصادر"
        title="المصادر والمكتبة"
        description="احفظ كتاب PDF، ثم حلّله لاستخراج المواد، وراجعها قبل إرسالها إلى الإنتاج. الملفات الجاهزة للمراجعة توجد في بنك المحتوى."
        actions={<>
          <Link to="/production" className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-600 hover:bg-slate-50">الإنتاج من المصادر</Link>
          <button type="button" onClick={()=>setAnalysis(v=>!v)} className="rounded-xl border bg-white px-4 py-2 text-sm font-bold">{analysis?"إغلاق تحليل الكتاب":"تحليل كتاب واستخراج المواد"}</button>
        </>}
      />

      <section className="rounded-2xl border border-emerald-100 bg-emerald-50/50 p-5" aria-label="إضافة مصدر جديد">
        <h3 className="font-bold">إضافة مصدر جديد</h3>
        <p className="mt-1 text-sm text-slate-600">ارفع ملف PDF لحفظه أولاً، ثم افتح تحليل الكتاب وابدأ استخراج مواده بقرارك. الرفع وحده لا يبدأ التحليل.</p>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="text-sm font-semibold">ملف PDF
            <input
              aria-label="ملف المصدر الجديد"
              type="file"
              accept="application/pdf"
              onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
              className="mt-1 w-full rounded-lg border bg-white p-2 font-normal"
            />
          </label>
          <button
            type="button"
            onClick={() => upload.mutate()}
            disabled={!uploadFile || upload.isPending}
            className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
          >
            {upload.isPending ? "جارٍ الرفع..." : "حفظ ملف الكتاب"}
          </button>
        </div>
        {upload.isError ? <p role="alert" className="mt-2 text-sm text-rose-700">{upload.error.message}</p> : null}
        {upload.isSuccess ? <p role="status" className="mt-2 text-sm text-emerald-800">حُفظ الملف. الخطوة التالية: افتح تحليل الكتاب، ثم ابدأ التحليل إن أردت.</p> : null}
      </section>

      {analysis?<section className="rounded-2xl border bg-white p-3" aria-label="تحليل الكتاب"><h3 className="font-bold">تحليل الكتاب واستخراج المواد</h3><p className="text-xs leading-6">أداة تحليل ضمن مساحة العمل. فتحها لا يبدأ التحليل تلقائياً. ارجع إلى الإنتاج بعد مراجعة المواد المستخرجة.</p><iframe title="أداة تحليل الكتاب" src={`/sources/book-analysis${analysisId?`?source_id=${encodeURIComponent(analysisId)}`:""}`} className="mt-3 h-[850px] w-full rounded-xl border"/></section>:null}
      <section className="rounded-2xl border bg-white p-5 shadow-sm" aria-label="قائمة المصادر">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-xl font-bold">{showOther?"جميع المصادر المحفوظة":"كتب PDF فقط"}</h3><label className="text-xs"><input type="checkbox" checked={showOther} onChange={e=>setShowOther(e.target.checked)}/> إظهار بقية الملفات والمصادر دون حذفها</label>
          <label className="text-sm font-semibold">
            <span className="sr-only">بحث المصادر</span>
            <input
              aria-label="بحث المصادر"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="ابحث بعنوان الكتاب أو اسم الملف..."
              className="w-72 max-w-full rounded-xl border p-3 font-normal"
            />
          </label>
        </div>
        {sources.isLoading ? <p role="status" className="mt-4 text-sm text-slate-500">جارٍ تحميل المصادر...</p> : null}
        {sources.isError ? <p role="alert" className="mt-4 text-sm text-rose-700">تعذر تحميل المصادر: {sources.error.message}</p> : null}
        {sources.isSuccess && items.length === 0 ? (
          <div className="mt-4 rounded-xl border border-dashed p-6 text-center text-sm text-slate-500">
            {query.trim() ? "لا توجد مصادر تطابق البحث." : "لا توجد مصادر بعد. ابدأ برفع ملف PDF من الأعلى."}
          </div>
        ) : null}
        <div className="mt-4 space-y-3">
          {items.map((source: SourceSummary) => (
            <article key={source.id} className="rounded-xl border p-4" data-testid={`source-card-${source.id}`}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <strong className="block">{source.book_title || source.filename}</strong>
                  <p className="mt-1 break-all text-xs text-slate-500">{source.filename} · {source.id}</p>
                </div>
                <span className={`rounded-full px-3 py-1 text-xs font-semibold ${source.status === "READY" ? "bg-emerald-100 text-emerald-800" : source.status === "FAILED" ? "bg-rose-100 text-rose-800" : "bg-amber-100 text-amber-800"}`}>
                  {sourceStatusLabel(source.status)}
                </span>
              </div>
              <p className="mt-2 text-sm text-slate-600">
                {source.material_count} مادة · أُنتج منها {source.produced_count} · متبقٍ {source.pending_count}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {source.mime_type==="application/pdf"?<button
                  type="button"
                  aria-expanded={expandedId === source.id}
                  onClick={() => setExpandedId((current) => (current === source.id ? null : source.id))}
                  className="rounded-lg border px-3 py-2 text-sm font-semibold"
                >
                  {expandedId === source.id ? "إخفاء البنية" : "عرض بنية الكتاب"}
                </button>:null}
                {source.mime_type==="application/pdf"?<button type="button" onClick={()=>{setAnalysisId(source.id);setAnalysis(true);}} className="rounded-lg border px-3 py-2 text-sm">فتح تحليل هذا الكتاب</button>:null}<Link to={`/production?source_id=${encodeURIComponent(source.id)}`} className="rounded-lg bg-indigo-600 px-3 py-2 text-sm font-semibold text-white">الإنتاج من هذا المصدر</Link>
              </div>
              {expandedId === source.id ? <SourceBookMap sourceId={source.id} /> : null}
            </article>
          ))}
        </div>
      </section>
    </section>
  );
}
