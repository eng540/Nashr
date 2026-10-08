import { useEffect, useState } from "react";

type Version = { version: number; body: string; status: "DRAFT" | "PUBLISHED" | "ARCHIVED"; created_at: string; updated_at: string };
type Prompt = { key: string; name: string; purpose: string; versions?: Version[]; active_version?: number | null };

export function ControlPlanePage() {
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Prompt | null>(null);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function loadList() {
    const response = await fetch("/api/control/prompts");
    if (!response.ok) throw new Error("تعذر تحميل قوالب التعليمات.");
    setPrompts(await response.json());
  }

  async function loadPrompt(key: string) {
    const response = await fetch("/api/control/prompts/" + encodeURIComponent(key));
    if (!response.ok) throw new Error("تعذر تحميل القالب.");
    const data: Prompt = await response.json();
    setSelected(key);
    setDetail(data);
    const draft = data.versions?.find((version) => version.status === "DRAFT");
    const active = data.versions?.find((version) => version.status === "PUBLISHED");
    setBody(draft?.body ?? active?.body ?? "");
  }

  useEffect(() => { loadList().catch((error) => setMessage(error.message)); }, []);

  async function saveDraft() {
    if (!detail) return;
    setBusy(true);
    try {
      const draft = detail.versions?.find((version) => version.status === "DRAFT");
      const url = draft
        ? "/api/control/prompts/" + encodeURIComponent(detail.key) + "/versions/" + draft.version
        : "/api/control/prompts/" + encodeURIComponent(detail.key) + "/versions";
      const response = await fetch(url, {
        method: draft ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body }),
      });
      if (!response.ok) throw new Error((await response.json()).detail ?? "تعذر حفظ المسودة.");
      setMessage("تم حفظ المسودة.");
      await loadPrompt(detail.key);
      await loadList();
    } finally {
      setBusy(false);
    }
  }

  async function publishDraft() {
    if (!detail) return;
    const draft = detail.versions?.find((version) => version.status === "DRAFT");
    if (!draft) return;
    setBusy(true);
    try {
      const response = await fetch(
        "/api/control/prompts/" + encodeURIComponent(detail.key) + "/versions/" + draft.version + "/publish",
        { method: "POST" },
      );
      if (!response.ok) throw new Error((await response.json()).detail ?? "تعذر نشر النسخة.");
      setMessage("تم نشر v" + draft.version + " وأصبحت النسخة الفعالة.");
      await loadPrompt(detail.key);
      await loadList();
    } finally {
      setBusy(false);
    }
  }

  const active = detail?.versions?.find((version) => version.status === "PUBLISHED");
  const draft = detail?.versions?.find((version) => version.status === "DRAFT");

  return (
    <section dir="rtl" className="space-y-6">
      <div>
        <p className="text-sm font-semibold text-indigo-600">Control Plane</p>
        <h2 className="text-3xl font-bold">التعليمات التحريرية</h2>
        <p className="mt-2 text-slate-600">إدارة نسخ التعليمات التي يستخدمها Runtime عند الإنتاج.</p>
      </div>
      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <aside className="rounded-2xl border bg-white p-4">
          <h3 className="mb-3 font-bold">Prompt Templates</h3>
          <div className="space-y-2">
            {prompts.map((prompt) => (
              <button key={prompt.key} onClick={() => loadPrompt(prompt.key).catch((error) => setMessage(error.message))}
                className={"block w-full rounded-xl p-3 text-right " + (selected === prompt.key ? "bg-indigo-600 text-white" : "bg-slate-100")}>
                <div className="font-semibold">{prompt.name}</div>
                <div className="text-xs opacity-75">{prompt.key}</div>
              </button>
            ))}
          </div>
        </aside>
        <main className="rounded-2xl border bg-white p-5">
          {!detail ? (
            <div className="py-16 text-center text-slate-500">اختر تعليمة من القائمة.</div>
          ) : (
            <>
              <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
                <div>
                  <h3 className="text-2xl font-bold">{detail.name}</h3>
                  <p className="mt-1 text-sm text-slate-500">{detail.purpose}</p>
                </div>
                <div className="rounded-xl bg-slate-100 px-4 py-2 text-sm">
                  الفعالة: <strong>{active ? "v" + active.version : "لا توجد"}</strong>
                </div>
              </div>
              <div className="mb-3 flex flex-wrap gap-2">
                {detail.versions?.map((version) => (
                  <span key={version.version} className="rounded-full bg-slate-100 px-3 py-1 text-xs">
                    v{version.version} · {version.status}
                  </span>
                ))}
              </div>
              <textarea value={body} onChange={(event) => setBody(event.target.value)} dir="rtl"
                className="min-h-[520px] w-full rounded-2xl border bg-slate-50 p-4 font-mono text-sm leading-7" disabled={busy} />
              <div className="mt-4 flex flex-wrap gap-3">
                <button disabled={busy || !body.trim()} onClick={() => saveDraft().catch((error) => setMessage(error.message))}
                  className="rounded-xl bg-slate-900 px-5 py-3 font-semibold text-white disabled:opacity-50">حفظ المسودة</button>
                <button disabled={busy || !draft} onClick={() => publishDraft().catch((error) => setMessage(error.message))}
                  className="rounded-xl bg-indigo-600 px-5 py-3 font-semibold text-white disabled:opacity-50">نشر النسخة</button>
              </div>
              {message && <p className="mt-4 rounded-xl bg-slate-100 p-3 text-sm">{message}</p>}
            </>
          )}
        </main>
      </div>
    </section>
  );
}
