import { useEffect, useState } from "react";

type SectionKey = "products" | "recipes" | "identities" | "policies" | "output-contracts" | "prompts";
type Stage = { key: string; capability_key: string; capability_version: number; configuration?: Record<string, unknown> };
type Version = {
  version: number;
  status: "DRAFT" | "PUBLISHED" | "ARCHIVED";
  definition?: Record<string, unknown>;
  stages?: Stage[];
  body?: string;
  created_at?: string;
  updated_at?: string;
};
type ControlItem = {
  key: string;
  name: string;
  purpose: string;
  active_version?: number | null;
  versions?: Version[];
  parent_product_id?: string | null;
  derived_from_version_id?: string | null;
  derivation?: {
    parent_product_key: string;
    source_version: number;
    source_version_id: string;
    changes: Record<string, { from: unknown; to: unknown }>;
    component_diffs: Record<string, { from: unknown; to: unknown }>;
  };
};
type StageForm = { key: string; capability_key: string; capability_version: string; configuration: string; generation_prompt: string; style_instructions: string };
type FormState = Record<string, string>;

const sections: Array<{ key: SectionKey; label: string; description: string; endpoint: string }> = [
  { key: "products", label: "المنتجات", description: "تعريف المنتج يربط الوصفة والسياسة وعقد المخرج.", endpoint: "/api/control/products" },
  { key: "recipes", label: "الوصفات", description: "مراحل الإنتاج وقدراتها المدعومة.", endpoint: "/api/control/recipes" },
  { key: "identities", label: "الهويات التحريرية", description: "الصوت والنبرة والجمهور والمبادئ التحريرية.", endpoint: "/api/control/identities" },
  { key: "policies", label: "السياسات", description: "قواعد قبول المحتوى وحدوده.", endpoint: "/api/control/policies" },
  { key: "output-contracts", label: "عقود المخرجات", description: "نوع المخرج وطريقة تخزينه وقيود المحتوى.", endpoint: "/api/control/output-contracts" },
  { key: "prompts", label: "التعليمات", description: "قوالب التعليمات وإصداراتها المنشورة.", endpoint: "/api/control/prompts" },
];

const statusLabel: Record<string, string> = { DRAFT: "مسودة", PUBLISHED: "منشور", ARCHIVED: "مؤرشف" };
const capabilityOptions = [
  ["produce_post", "إنتاج منشور"],
  ["produce_text_artifact", "إنتاج مخرج نصي"],
  ["produce_image_artifact", "إنتاج صورة"],
  ["produce_video_artifact", "إنتاج فيديو"],
  ["produce_audio_artifact", "إنتاج صوت"],
] as const;

function messageFromPayload(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object") {
    const record = payload as { detail?: unknown; message?: unknown };
    const value = record.detail ?? record.message;
    if (typeof value === "string") return value;
    if (Array.isArray(value)) return value.map((item) => typeof item === "object" && item !== null && "msg" in item ? String((item as { msg: unknown }).msg) : String(item)).join("، ");
  }
  return fallback;
}

async function request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload: unknown = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(messageFromPayload(payload, "تعذر تنفيذ العملية."));
  return payload as T;
}

function latestVersion(item: ControlItem): Version | undefined {
  return item.versions?.find((version) => version.status === "DRAFT")
    ?? item.versions?.find((version) => version.status === "PUBLISHED")
    ?? [...(item.versions ?? [])].sort((a, b) => b.version - a.version)[0];
}

function initialForm(_section: SectionKey, item?: ControlItem, version?: Version): FormState {
  const definition = version?.definition ?? {};
  const asText = (value: unknown, fallback = ""): string => value == null ? fallback : String(value);
  const asLines = (value: unknown): string => Array.isArray(value) ? value.map(String).join("\n") : "";
  return {
    key: item?.key ?? "",
    name: item?.name ?? "",
    purpose: item?.purpose ?? "",
    body: version?.body ?? "",
    recipe_key: asText(definition.recipe_key),
    output_contract_key: asText(definition.output_contract_key),
    policy_key: asText(definition.policy_key),
    prompt_key: asText(definition.prompt_key, "editorial.drafter"),
    identity_key: asText(definition.identity_key),
    component_versions_json: asText(JSON.stringify(definition.component_versions ?? {}), "{}"),
    audience: asText(definition.audience),
    experience: asText(definition.experience),
    presentation_instructions: asText(definition.presentation_instructions),
    identity_purpose: asText(definition.purpose, item?.purpose ?? ""),
    voice: asText(definition.voice),
    tone: asText(definition.tone),
    principles: asLines(definition.principles),
    objectives: asLines(definition.objectives),
    constraints: asLines(definition.constraints),
    min_content_chars: asText(definition.min_content_chars, "1"),
    max_content_chars: asText(definition.max_content_chars, "100000"),
    required_terms: asLines(definition.required_terms),
    forbidden_terms: asLines(definition.forbidden_terms),
    allow_urls: asText(definition.allow_urls, "true"),
    artifact_kind: asText(definition.artifact_kind, "TEXT"),
    mime_type: asText(definition.mime_type, "text/plain"),
    content_mode: asText(definition.content_mode, "INLINE"),
    required_metadata_fields: asLines(definition.required_metadata_fields),
    max_contract_chars: asText(definition.max_content_chars),
  };
}

function pinnedComponentVersion(version: Version | undefined, component: string): number | undefined {
  const refs = version?.definition?.component_versions;
  if (!refs || typeof refs !== "object" || Array.isArray(refs)) return undefined;
  const reference = (refs as Record<string, unknown>)[component];
  if (!reference || typeof reference !== "object" || Array.isArray(reference)) return undefined;
  const value = (reference as { version?: unknown }).version;
  return typeof value === "number" ? value : undefined;
}

function stagesFromVersion(version?: Version): StageForm[] {
  const stages = version?.stages ?? [];
  return stages.map((stage) => {
    const configuration = { ...(stage.configuration ?? {}) };
    const generationPrompt = typeof configuration.generation_prompt === "string" ? configuration.generation_prompt : "";
    const styleInstructions = typeof configuration.style_instructions === "string" ? configuration.style_instructions : "";
    delete configuration.generation_prompt;
    delete configuration.style_instructions;
    return {
      key: stage.key,
      capability_key: stage.capability_key,
      capability_version: String(stage.capability_version),
      configuration: Object.keys(configuration).length ? JSON.stringify(configuration, null, 2) : "",
      generation_prompt: generationPrompt,
      style_instructions: styleInstructions,
    };
  });
}

function lines(value: string): string[] {
  return value.split("\n").map((item) => item.trim()).filter(Boolean);
}

function definitionFor(section: SectionKey, form: FormState, stages: StageForm[]): Record<string, unknown> {
  if (section === "products") {
    const definition: Record<string, unknown> = {
      recipe_key: form.recipe_key,
      output_contract_key: form.output_contract_key,
      policy_key: form.policy_key,
      prompt_key: form.prompt_key,
      identity_key: form.identity_key,
      audience: form.audience,
      experience: form.experience,
      presentation_instructions: form.presentation_instructions,
    };
    let savedReferences: Record<string, unknown> = {};
    try {
      const parsed: unknown = JSON.parse(form.component_versions_json || "{}");
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        savedReferences = parsed as Record<string, unknown>;
      }
    } catch {
      throw new Error("مراجع مكونات المنتج المحفوظة غير صالحة؛ أعد تحميل الإصدار قبل حفظه.");
    }
    const selectedKeys: Record<string, string> = {
      prompt: form.prompt_key,
      identity: form.identity_key,
      recipe: form.recipe_key,
      policy: form.policy_key,
      output_contract: form.output_contract_key,
    };
    const preserved = Object.fromEntries(
      Object.entries(savedReferences).filter(([component, reference]) => {
        if (!reference || typeof reference !== "object" || Array.isArray(reference)) return false;
        return "key" in reference && (reference as { key?: unknown }).key === selectedKeys[component];
      }),
    );
    if (Object.keys(preserved).length) definition.component_versions = preserved;
    return definition;
  }
  if (section === "recipes") return {
    stages: stages.map((stage) => {
      let configuration: Record<string, unknown> = {};
      if (stage.configuration.trim()) {
        const parsed: unknown = JSON.parse(stage.configuration);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("إعدادات المرحلة المتقدمة يجب أن تكون كائنًا صالحًا.");
        configuration = parsed as Record<string, unknown>;
      }
      if (["produce_image_artifact", "produce_video_artifact"].includes(stage.capability_key)) {
        if (stage.generation_prompt.trim()) configuration.generation_prompt = stage.generation_prompt;
        else delete configuration.generation_prompt;
      } else {
        delete configuration.generation_prompt;
      }
      if (["produce_post", "produce_text_artifact", "produce_image_artifact", "produce_video_artifact", "produce_audio_artifact"].includes(stage.capability_key)) {
        if (stage.style_instructions.trim()) configuration.style_instructions = stage.style_instructions;
        else delete configuration.style_instructions;
      } else {
        delete configuration.style_instructions;
      }
      return {
        key: stage.key.trim(),
        capability_key: stage.capability_key,
        capability_version: Number(stage.capability_version),
        configuration,
      };
    }),
  };
  if (section === "identities") return {
    definition: {
      purpose: form.identity_purpose,
      audience: form.audience,
      voice: form.voice,
      tone: form.tone,
      principles: lines(form.principles),
      objectives: lines(form.objectives),
      constraints: lines(form.constraints),
    },
  };
  if (section === "policies") return { definition: {
    min_content_chars: Number(form.min_content_chars),
    max_content_chars: Number(form.max_content_chars),
    required_terms: lines(form.required_terms),
    forbidden_terms: lines(form.forbidden_terms),
    allow_urls: form.allow_urls === "true",
  } };
  if (section === "output-contracts") return { definition: {
    artifact_kind: form.artifact_kind,
    mime_type: form.mime_type,
    content_mode: form.content_mode,
    required_metadata_fields: lines(form.required_metadata_fields),
    max_content_chars: form.max_contract_chars.trim() ? Number(form.max_contract_chars) : null,
  } };
  return { body: form.body };
}

function versionDefinition(section: SectionKey, payload: Record<string, unknown>): Record<string, unknown> {
  if (section === "recipes") return { stages: payload.stages };
  if (section === "prompts") return { body: payload.body };
  if (section === "products") return { definition: payload };
  return { definition: payload.definition };
}

function Field({ label, value, onChange, type = "text", placeholder, multiline = false, disabled = false }: {
  label: string; value: string; onChange: (value: string) => void; type?: string; placeholder?: string; multiline?: boolean; disabled?: boolean;
}) {
  return <label className="block text-sm font-semibold">
    {label}
    {multiline
      ? <textarea value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} disabled={disabled} className="mt-2 min-h-24 w-full rounded-xl border p-3 font-normal disabled:bg-slate-100" />
      : <input type={type} value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} disabled={disabled} className="mt-2 w-full rounded-xl border p-3 font-normal disabled:bg-slate-100" />}
  </label>;
}

function SelectField({ label, value, onChange, options, disabled = false }: {
  label: string; value: string; onChange: (value: string) => void; options: Array<{ value: string; label: string }>; disabled?: boolean;
}) {
  return <label className="block text-sm font-semibold">{label}
    <select value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled} className="mt-2 w-full rounded-xl border p-3 font-normal disabled:bg-slate-100">
      {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select>
  </label>;
}

export function ControlPlanePage() {
  const [activeSection, setActiveSection] = useState<SectionKey>("products");
  const [itemsBySection, setItemsBySection] = useState<Record<SectionKey, ControlItem[]>>({
    products: [], recipes: [], identities: [], policies: [], "output-contracts": [], prompts: [],
  });
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [selectedVersionNumber, setSelectedVersionNumber] = useState<number | null>(null);
  const [form, setForm] = useState<FormState>(() => initialForm("products"));
  const [stages, setStages] = useState<StageForm[]>([{ key: "produce", capability_key: "produce_post", capability_version: "1", configuration: "", generation_prompt: "", style_instructions: "" }]);
  const [busy, setBusy] = useState(false);
  const [selectingItem, setSelectingItem] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [deriveDialog, setDeriveDialog] = useState<{ key: string; name: string; purpose: string } | null>(null);

  const section = sections.find((item) => item.key === activeSection)!;
  const items = itemsBySection[activeSection];
  const selected = items.find((item) => item.key === selectedKey) ?? null;
  const selectedVersion = selected?.versions?.find((version) => version.version === selectedVersionNumber) ?? (selected ? latestVersion(selected) : undefined);
  const draft = selected?.versions?.find((version) => version.status === "DRAFT");
  const activeVersion = selected?.versions?.find((version) => version.status === "PUBLISHED");
  const isNew = selectedKey === null;
  const publishedRecipes = itemsBySection.recipes.filter((item) => item.active_version != null);
  const publishedPolicies = itemsBySection.policies.filter((item) => item.active_version != null);
  const publishedContracts = itemsBySection["output-contracts"].filter((item) => item.active_version != null);
  const publishedIdentities = itemsBySection.identities.filter((item) => item.active_version != null);
  const publishedPrompts = itemsBySection.prompts.filter((item) => item.active_version != null);

  async function reload(sectionToSelect = activeSection, keyToSelect: string | null = selectedKey, versionToSelect: number | null = selectedVersionNumber) {
    setLoading(true);
    try {
      const entries = await Promise.all(sections.map(async (entry) => [entry.key, await request<ControlItem[]>(entry.endpoint)] as const));
      const next = Object.fromEntries(entries) as Record<SectionKey, ControlItem[]>;
      // The prompt list endpoint returns template metadata only. Hydrate each
      // prompt's versions so product drafts can select a genuinely published
      // instruction template instead of showing an empty or stale option list.
      const promptEndpoint = sections.find((entry) => entry.key === "prompts")!.endpoint;
      next.prompts = await Promise.all(next.prompts.map(async (item) => {
        try {
          return await request<ControlItem>(promptEndpoint + "/" + encodeURIComponent(item.key));
        } catch {
          return item;
        }
      }));
      if (sectionToSelect === "products" && keyToSelect) {
        const productEndpoint = sections.find((entry) => entry.key === "products")!.endpoint;
        try {
          const detail = await request<ControlItem>(productEndpoint + "/" + encodeURIComponent(keyToSelect));
          next.products = next.products.map((item) => item.key === keyToSelect ? detail : item);
        } catch {
          // Keep the list response usable if optional lineage detail is unavailable.
        }
      }
      setItemsBySection(next);
      const found = keyToSelect ? next[sectionToSelect].find((item) => item.key === keyToSelect) : undefined;
      const version = found?.versions?.find((candidate) => candidate.version === versionToSelect) ?? (found ? latestVersion(found) : undefined);
      setSelectedKey(found?.key ?? null);
      setSelectedVersionNumber(version?.version ?? null);
      setForm(initialForm(sectionToSelect, found, version));
      setStages(stagesFromVersion(version).length ? stagesFromVersion(version) : [{ key: "produce", capability_key: "produce_post", capability_version: "1", configuration: "", generation_prompt: "", style_instructions: "" }]);
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "تعذر تحميل إعدادات التحكم.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void reload("products", null, null); }, []);

  function selectSection(next: SectionKey) {
    setActiveSection(next);
    setSelectedKey(null);
    setSelectedVersionNumber(null);
    setForm(initialForm(next));
    setStages([{ key: "produce", capability_key: "produce_post", capability_version: "1", configuration: "", generation_prompt: "", style_instructions: "" }]);
    setMessage("");
    setError("");
  }

  async function selectItem(item: ControlItem) {
    setSelectingItem(true);
    try {
      let resolved = item;
      if (activeSection === "prompts" || activeSection === "products") {
        resolved = await request<ControlItem>(section.endpoint + "/" + encodeURIComponent(item.key));
        setItemsBySection((current) => ({
          ...current,
          [activeSection]: current[activeSection].map((entry) => entry.key === resolved.key ? resolved : entry),
        }));
      }
      const version = latestVersion(resolved);
      setSelectedKey(resolved.key);
      setSelectedVersionNumber(version?.version ?? null);
      setForm(initialForm(activeSection, resolved, version));
      setStages(stagesFromVersion(version).length ? stagesFromVersion(version) : [{ key: "produce", capability_key: "produce_post", capability_version: "1", configuration: "", generation_prompt: "", style_instructions: "" }]);
      setMessage("");
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "تعذر تحميل تفاصيل العنصر.");
    } finally {
      setSelectingItem(false);
    }
  }

  function changeVersion(number: number) {
    if (!selected) return;
    const version = selected.versions?.find((candidate) => candidate.version === number);
    setSelectedVersionNumber(number);
    setForm(initialForm(activeSection, selected, version));
    setStages(stagesFromVersion(version).length ? stagesFromVersion(version) : [{ key: "produce", capability_key: "produce_post", capability_version: "1", configuration: "", generation_prompt: "", style_instructions: "" }]);
    setMessage("");
    setError("");
  }

  function updateField(key: string, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function bodyForCreate(): Record<string, unknown> {
    if (activeSection === "prompts") return { key: form.key.trim(), name: form.name.trim(), purpose: form.purpose.trim(), body: form.body };
    if (activeSection === "recipes") return { key: form.key.trim(), name: form.name.trim(), purpose: form.purpose.trim(), stages: definitionFor(activeSection, form, stages).stages };
    if (activeSection === "identities") return { key: form.key.trim(), name: form.name.trim(), purpose: form.purpose.trim(), definition: definitionFor(activeSection, form, stages).definition };
    if (activeSection === "policies" || activeSection === "output-contracts") return {
      key: form.key.trim(), name: form.name.trim(), purpose: form.purpose.trim(),
      definition: definitionFor(activeSection, form, stages).definition,
    };
    return { key: form.key.trim(), name: form.name.trim(), purpose: form.purpose.trim(), definition: definitionFor(activeSection, form, stages) };
  }

  async function createItem() {
    setBusy(true); setError(""); setMessage("");
    try {
      const created = await request<ControlItem>(section.endpoint, "POST", bodyForCreate());
      setSelectedKey(created.key);
      const nextVersion = created.versions?.find((version) => version.status === "DRAFT") ?? created.versions?.[0];
      setSelectedVersionNumber(nextVersion?.version ?? 1);
      await reload(activeSection, created.key, nextVersion?.version ?? 1);
      setMessage("تم إنشاء العنصر ومسودته الأولى.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "تعذر إنشاء العنصر.");
    } finally { setBusy(false); }
  }

  async function saveDraft() {
    if (!selected) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const raw = definitionFor(activeSection, form, stages);
      const payload = versionDefinition(activeSection, raw);
      const path = section.endpoint + "/" + encodeURIComponent(selected.key) + "/versions";
      const draftVersion = selected.versions?.find((version) => version.version === selectedVersionNumber && version.status === "DRAFT");
      const response = await request<Version>(
        draftVersion ? path + "/" + draftVersion.version : path,
        draftVersion ? "PATCH" : "POST",
        payload,
      );
      await reload(activeSection, selected.key, response.version);
      setMessage(draftVersion ? "تم حفظ تعديلات المسودة." : "تم إنشاء مسودة إصدار جديدة.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "تعذر حفظ المسودة.");
    } finally { setBusy(false); }
  }

  async function createDraftFromVersion(source: Version) {
    if (!selected) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const copiedForm = initialForm(activeSection, selected, source);
      const copiedStages = stagesFromVersion(source);
      const raw = definitionFor(activeSection, copiedForm, copiedStages.length ? copiedStages : stages);
      const payload = versionDefinition(activeSection, raw);
      const path = section.endpoint + "/" + encodeURIComponent(selected.key) + "/versions";
      const created = await request<Version>(path, "POST", payload);
      await reload(activeSection, selected.key, created.version);
      setMessage("تم إنشاء مسودة إصدار جديدة من الإصدار المحدد.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "تعذر إنشاء المسودة.");
    } finally { setBusy(false); }
  }

  async function deriveSelectedProduct() {
    if (activeSection !== "products" || !selected || !selectedVersion || !deriveDialog) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const created = await request<ControlItem & { created_version?: Version }>(
        "/api/control/products/" + encodeURIComponent(selected.key) + "/versions/" + selectedVersion.version + "/derive",
        "POST",
        { key: deriveDialog.key.trim(), name: deriveDialog.name.trim(), purpose: deriveDialog.purpose.trim() },
      );
      setDeriveDialog(null);
      setMessage("تم إنشاء منتج مشتق مستقل بمسودة أولى؛ المكونات المشتركة ما زالت تشير إلى الإصدارات نفسها.");
      await reload("products", created.key, created.created_version?.version ?? 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "تعذر اشتقاق المنتج.");
    } finally {
      setBusy(false);
    }
  }

  async function versionAction(action: "publish" | "archive", version: Version) {
    if (!selected) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const path = section.endpoint + "/" + encodeURIComponent(selected.key) + "/versions/" + version.version + "/" + action;
      await request<Version>(path, "POST");
      await reload(activeSection, selected.key, version.version);
      setMessage(action === "publish" ? "تم نشر الإصدار بعد تحقق الخادم." : "تمت أرشفة الإصدار وفق قواعد الخدمة.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "تعذر تنفيذ الإجراء.");
    } finally { setBusy(false); }
  }



  const versionIsDraft = selectedVersion?.status === "DRAFT";
  // Editing a published version changes only local form state; saveDraft creates a new immutable draft version.
  const formDisabled = busy || selectingItem;

  return <section dir="rtl" className="space-y-6" data-testid="control-plane-workspace">
    <header className="space-y-2">
      <p className="text-sm font-semibold text-indigo-600">Control Plane</p>
      <h2 className="text-3xl font-bold">التحكم في المنتجات والإنتاج</h2>
      <p className="max-w-3xl text-sm leading-7 text-slate-600">إدارة المنتجات والوصفات والهويات والسياسات وعقود المخرجات والتعليمات. صلاحية النشر النهائية يقررها الخادم باستخدام قواعده الحالية.</p>
    </header>

    <nav className="flex flex-wrap gap-2" aria-label="مكونات التحكم">
      {sections.map((entry) => <button key={entry.key} type="button" onClick={() => selectSection(entry.key)} disabled={loading || busy} aria-pressed={activeSection === entry.key}
        className={"rounded-xl px-4 py-2 text-sm font-semibold " + (activeSection === entry.key ? "bg-indigo-600 text-white" : "border bg-white")}>{entry.label}</button>)}
    </nav>

    <div className="grid gap-5 lg:grid-cols-[300px_minmax(0,1fr)]">
      <aside className="rounded-2xl border bg-white p-4">
        <div className="flex items-center justify-between gap-2">
          <div><h3 className="font-bold">{section.label}</h3><p className="mt-1 text-xs text-slate-500">{items.length} عنصر</p></div>
          <button type="button" disabled={loading || busy} onClick={() => { setSelectedKey(null); setSelectedVersionNumber(null); setForm(initialForm(activeSection)); setStages([{ key: "produce", capability_key: "produce_post", capability_version: "1", configuration: "", generation_prompt: "", style_instructions: "" }]); setMessage(""); setError(""); }}
            className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white disabled:opacity-40">جديد</button>
        </div>
        <p className="my-3 text-xs leading-6 text-slate-500">{section.description}</p>
        {loading ? <p role="status" className="py-8 text-center text-sm text-slate-500">تحميل العناصر...</p> : items.length === 0 ? <p className="rounded-xl bg-slate-50 p-4 text-sm text-slate-500">لا توجد عناصر بعد. أنشئ أول عنصر من هنا.</p> :
          <div className="space-y-2">{items.map((item) => {
            const published = item.versions?.find((version) => version.status === "PUBLISHED");
            const itemDraft = item.versions?.find((version) => version.status === "DRAFT");
            return <button key={item.key} type="button" onClick={() => selectItem(item)} className={"block w-full rounded-xl border p-3 text-right " + (selectedKey === item.key ? "border-indigo-500 bg-indigo-50" : "bg-white hover:bg-slate-50")}>
              <span className="block font-semibold">{item.name}</span>
              <span className="mt-1 block text-xs text-slate-500">{item.key}</span>
              <span className="mt-2 flex flex-wrap gap-1 text-xs">
                {published && <span className="rounded-full bg-emerald-100 px-2 py-1 text-emerald-800">فعال v{published.version}</span>}
                {itemDraft && <span className="rounded-full bg-amber-100 px-2 py-1 text-amber-800">مسودة v{itemDraft.version}</span>}
                {!published && !itemDraft && <span className="rounded-full bg-slate-100 px-2 py-1">لا يوجد إصدار منشور</span>}
              </span>
            </button>;
          })}</div>}
      </aside>

      <main className="min-w-0 space-y-4 rounded-2xl border bg-white p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><h3 className="text-xl font-bold">{isNew ? "إنشاء " + section.label.slice(0, -1) : selected?.name}</h3>
            <p className="mt-1 text-sm text-slate-500">{selected?.purpose ?? "أنشئ عنصرًا جديدًا؛ سيُنشئ الخادم مسودته الأولى وفق العقد الحالي."}</p></div>
          {selected && <div className="rounded-xl bg-slate-100 px-3 py-2 text-sm">الإصدار المنشور: <strong>{activeVersion ? "v" + activeVersion.version : "لا يوجد"}</strong></div>}
        </div>

        {activeSection === "products" && selected?.derivation && <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4">
          <h4 className="font-bold">سجل اشتقاق المنتج</h4>
          <p className="mt-1 text-sm">الأصل: <strong>{selected.derivation.parent_product_key}</strong> · الإصدار v{selected.derivation.source_version}</p>
          <p className="mt-1 text-xs text-slate-600">هذه نسخة مستقلة؛ التغييرات هنا لا تعدّل الأصل. المكونات التي لم تتغير تعيد استخدام مراجع الإصدارات نفسها.</p>
          {Object.entries(selected.derivation.component_diffs ?? {}).length > 0 && <div className="mt-3 space-y-2">
            <h5 className="text-sm font-semibold">تغييرات المكونات المثبتة</h5>
            {Object.entries(selected.derivation.component_diffs).map(([component, change]) => <div key={component} className="rounded-lg bg-white p-3 text-xs">
              <strong>{component}</strong>
              <p className="mt-1 break-words text-slate-600">مرجع الأصل: {JSON.stringify(change.from)}</p>
              <p className="break-words text-slate-700">مرجع المشتق: {JSON.stringify(change.to)}</p>
            </div>)}
          </div>}
          <div className="mt-3 space-y-2">
            {Object.entries(selected.derivation.changes).length === 0 && Object.entries(selected.derivation.component_diffs ?? {}).length === 0
              ? <p className="text-sm text-slate-600">لا توجد فروقات عن إصدار الأصل حتى الآن.</p>
              : Object.entries(selected.derivation.changes).map(([field, change]) => <div key={field} className="rounded-lg bg-white p-3 text-xs">
                <strong>{field}</strong>
                <p className="mt-1 break-words text-slate-600">الأصل: {JSON.stringify(change.from)}</p>
                <p className="break-words text-slate-700">المشتق: {JSON.stringify(change.to)}</p>
              </div>)}
          </div>
        </div>}
        {selected?.versions?.length ? <div className="flex flex-wrap items-center gap-3 rounded-xl bg-slate-50 p-3">
          <label className="text-sm font-semibold">الإصدار
            <select value={selectedVersionNumber ?? ""} onChange={(event) => changeVersion(Number(event.target.value))} className="mr-2 rounded-lg border bg-white p-2 font-normal">
              {selected.versions.slice().sort((a, b) => b.version - a.version).map((version) => <option key={version.version} value={version.version}>v{version.version} · {statusLabel[version.status] ?? version.status}{version.version === selected.active_version ? " · فعّال" : ""}</option>)}
            </select>
          </label>
          <span className="text-xs text-slate-500">{selected.versions.length} إصدار</span>
          {!draft && <button type="button" disabled={busy} onClick={() => {
            const source = selectedVersion ?? activeVersion ?? latestVersion(selected);
            if (source) void createDraftFromVersion(source);
          }} className="rounded-lg border bg-white px-3 py-2 text-xs font-semibold disabled:opacity-50">إنشاء مسودة من هذا الإصدار</button>}
          {activeSection === "products" && selectedVersion && ["PUBLISHED", "ARCHIVED"].includes(selectedVersion.status)
            && (() => {
              const refs = selectedVersion.definition?.component_versions as Record<string, unknown> | undefined;
              const complete = ["prompt", "identity", "recipe", "policy", "output_contract"].every((key) => refs && key in refs);
              return complete ? <button type="button" disabled={busy} onClick={() => setDeriveDialog({
                key: selected.key + "_DERIVED",
                name: selected.name + " — مشتق",
                purpose: selected.purpose,
              })} className="rounded-lg bg-indigo-50 px-3 py-2 text-xs font-semibold text-indigo-800 disabled:opacity-50">اشتقاق منتج مستقل</button> : null;
            })()}
        </div> : null}

        {activeSection !== "prompts" && <div className="grid gap-3 md:grid-cols-2">
          <Field label="المفتاح" value={form.key} onChange={(value) => updateField("key", value)} disabled={!isNew || busy} placeholder="معرّف ثابت بحروف لاتينية وأرقام وشرطة" />
          <Field label="الاسم" value={form.name} onChange={(value) => updateField("name", value)} disabled={!isNew || busy} />
          <div className="md:col-span-2"><Field label="الغرض" value={form.purpose} onChange={(value) => updateField("purpose", value)} disabled={!isNew || busy} multiline /></div>
        </div>}
        {activeSection === "prompts" && <div className="grid gap-3 md:grid-cols-2">
          <Field label="المفتاح" value={form.key} onChange={(value) => updateField("key", value)} disabled={!isNew || busy} placeholder="مثل editorial.drafter" />
          <Field label="الاسم" value={form.name} onChange={(value) => updateField("name", value)} disabled={!isNew || busy} />
          <div className="md:col-span-2"><Field label="الغرض" value={form.purpose} onChange={(value) => updateField("purpose", value)} disabled={!isNew || busy} multiline /></div>
          <div className="md:col-span-2"><Field label="نص التعليمات" value={form.body} onChange={(value) => updateField("body", value)} disabled={formDisabled} multiline /></div>
        </div>}

        {activeSection === "products" && <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <SelectField label="الوصفة المنشورة" value={form.recipe_key} onChange={(value) => updateField("recipe_key", value)} disabled={formDisabled}
              options={[{ value: "", label: "اختر وصفة..." }, ...(!publishedRecipes.some((item) => item.key === form.recipe_key) && form.recipe_key ? [{ value: form.recipe_key, label: form.recipe_key + " · لا يوجد إصدار منشور" }] : []), ...publishedRecipes.map((item) => ({ value: item.key, label: item.name + " · v" + item.active_version }))]} />
            <SelectField label="التعليمات المنشورة" value={form.prompt_key} onChange={(value) => updateField("prompt_key", value)} disabled={formDisabled}
              options={[{ value: "", label: "اختر تعليمات..." }, ...publishedPrompts.map((item) => ({ value: item.key, label: item.name + " · v" + item.active_version }))]} />
            <SelectField label="الهوية التحريرية المنشورة" value={form.identity_key} onChange={(value) => updateField("identity_key", value)} disabled={formDisabled}
              options={[{ value: "", label: "اختر هوية..." }, ...publishedIdentities.map((item) => ({ value: item.key, label: item.name + " · v" + item.active_version }))]} />
            <SelectField label="السياسة المنشورة" value={form.policy_key} onChange={(value) => updateField("policy_key", value)} disabled={formDisabled}
              options={[{ value: "", label: "اختر سياسة..." }, ...(!publishedPolicies.some((item) => item.key === form.policy_key) && form.policy_key ? [{ value: form.policy_key, label: form.policy_key + " · لا يوجد إصدار منشور" }] : []), ...publishedPolicies.map((item) => ({ value: item.key, label: item.name + " · v" + item.active_version }))]} />
            <SelectField label="عقد المخرج المنشور" value={form.output_contract_key} onChange={(value) => updateField("output_contract_key", value)} disabled={formDisabled}
              options={[{ value: "", label: "اختر عقد مخرج..." }, ...(!publishedContracts.some((item) => item.key === form.output_contract_key) && form.output_contract_key ? [{ value: form.output_contract_key, label: form.output_contract_key + " · لا يوجد إصدار منشور" }] : []), ...publishedContracts.map((item) => ({ value: item.key, label: item.name + " · v" + item.active_version }))]} />
            <Field label="الجمهور" value={form.audience} onChange={(value) => updateField("audience", value)} disabled={formDisabled} />
            <div className="md:col-span-2"><Field label="تجربة المنتج" value={form.experience} onChange={(value) => updateField("experience", value)} disabled={formDisabled} multiline /></div>
             <div className="md:col-span-2"><Field
               label="تعليمات العرض للنصوص والمنشورات"
               value={form.presentation_instructions}
               onChange={(value) => updateField("presentation_instructions", value)}
               disabled={formDisabled}
               multiline
               placeholder="مثال: طول الفقرات، المسافات بينها، استخدام العناوين أو القوائم، وما يجب تجنبه في العرض النهائي."
             /></div>
          </div>
          <p className="rounded-xl bg-slate-50 p-3 text-sm text-slate-600">هذه التعليمات تخص مخرجات TEXT/POST وتُثبت مع إصدار المنتج؛ أما الصورة والفيديو والصوت فلها توجيهات مرحلية في الوصفة.</p>
           <p className="rounded-xl bg-slate-50 p-3 text-sm text-slate-600">يتحقق الخادم من توافق الوصفة والسياسة وعقد المخرج عند النشر، وتظهر هنا رسالة السبب إذا رفض التحقق.</p>
          {selected && <div className="rounded-xl border p-4"><h4 className="font-bold">مكونات الإصدار</h4><div className="mt-3 grid gap-3 sm:grid-cols-3">
            {[
              { label: "الوصفة", component: "recipe", key: form.recipe_key, item: publishedRecipes.find((item) => item.key === form.recipe_key) },
              { label: "التعليمات", component: "prompt", key: form.prompt_key, item: publishedPrompts.find((item) => item.key === form.prompt_key) },
              { label: "الهوية التحريرية", component: "identity", key: form.identity_key, item: publishedIdentities.find((item) => item.key === form.identity_key) },
              { label: "السياسة", component: "policy", key: form.policy_key, item: publishedPolicies.find((item) => item.key === form.policy_key) },
              { label: "عقد المخرج", component: "output_contract", key: form.output_contract_key, item: publishedContracts.find((item) => item.key === form.output_contract_key) },
            ].map(({ label, component, key, item }) => {
              const pinnedVersion = pinnedComponentVersion(selectedVersion, component);
              return <div key={label} className="rounded-lg bg-slate-50 p-3 text-sm">
                <p className="text-xs text-slate-500">{label}</p><strong>{item ? item.name : key || "غير محدد"}</strong>
                <p className="mt-1 text-xs">{pinnedVersion != null ? "الإصدار المثبت v" + pinnedVersion : item ? "سيُثبت الإصدار المنشور v" + item.active_version + " عند النشر" : "لا يوجد إصدار منشور"}</p>
              </div>;
            })}
          </div><p className="mt-3 text-xs text-slate-500">الهوية التحريرية والتعليمات مثبتتان بإصدارات محددة في بيان المنتج المنشور؛ لا يحق لتشغيل عابر تجاوزهما.</p></div>}
        </div>}

        {activeSection === "recipes" && <div className="space-y-3">
          <div className="flex items-center justify-between gap-3"><h4 className="font-bold">مراحل الوصفة</h4><button type="button" disabled={formDisabled} onClick={() => setStages((current) => [...current, { key: "stage-" + (current.length + 1), capability_key: "produce_post", capability_version: "1", configuration: "", generation_prompt: "", style_instructions: "" }])} className="rounded-lg border px-3 py-2 text-sm disabled:opacity-50">إضافة مرحلة</button></div>
          {stages.map((stage, index) => <div key={index} className="space-y-3 rounded-xl border p-3">
            <div className="flex items-center justify-between"><strong>المرحلة {index + 1}</strong><button type="button" disabled={formDisabled || stages.length === 1} onClick={() => setStages((current) => current.filter((_, stageIndex) => stageIndex !== index))} className="text-sm text-rose-700 disabled:opacity-40">حذف</button></div>
            <div className="grid gap-3 md:grid-cols-3">
              <Field label="مفتاح المرحلة" value={stage.key} onChange={(value) => setStages((current) => current.map((item, i) => i === index ? { ...item, key: value } : item))} disabled={formDisabled} />
              <SelectField label="القدرة" value={stage.capability_key} onChange={(value) => setStages((current) => current.map((item, i) => i === index ? { ...item, capability_key: value } : item))} disabled={formDisabled} options={capabilityOptions.map(([value, label]) => ({ value, label }))} />
              <Field label="إصدار القدرة" type="number" value={stage.capability_version} onChange={(value) => setStages((current) => current.map((item, i) => i === index ? { ...item, capability_version: value } : item))} disabled={formDisabled} />
            </div>
            {["produce_post", "produce_text_artifact", "produce_image_artifact", "produce_video_artifact", "produce_audio_artifact"].includes(stage.capability_key) && <Field
              label={["produce_image_artifact", "produce_video_artifact"].includes(stage.capability_key)
                ? "التوجيه البصري"
                : stage.capability_key === "produce_audio_artifact" ? "توجيه الإلقاء" : "تعليمات التحرير والعرض"}
              value={stage.style_instructions}
              onChange={(value) => setStages((current) => current.map((item, i) => i === index ? { ...item, style_instructions: value } : item))}
              disabled={formDisabled}
              multiline
              placeholder="تعليمات خاصة بهذه المرحلة، تُحفظ مع إصدار الوصفة ولا تتطلب تعديل الكود."
            />}
            {["produce_image_artifact", "produce_video_artifact"].includes(stage.capability_key) && <Field
              label="قالب توجيه التوليد (قابل للتعديل ضمن إصدار الوصفة)"
              value={stage.generation_prompt}
              onChange={(value) => setStages((current) => current.map((item, i) => i === index ? { ...item, generation_prompt: value } : item))}
              disabled={formDisabled}
              multiline
              placeholder={stage.capability_key === "produce_video_artifact"
                ? "المتغيرات المطلوبة: {{audience}}, {{experience}}, {{source_title}}, {{source_name}}, {{source_excerpt}}, {{editorial_prompt}}, {{style_instructions}}"
                : "المتغيرات المطلوبة: {{audience}}, {{experience}}, {{source_title}}, {{source_name}}, {{source_excerpt}}, {{identity_context}}, {{style_instructions}}"}
            />}
            <details><summary className="cursor-pointer text-xs font-semibold text-slate-600">إعدادات متقدمة للمرحلة (اختياري)</summary><textarea value={stage.configuration} onChange={(event) => setStages((current) => current.map((item, i) => i === index ? { ...item, configuration: event.target.value } : item))} disabled={formDisabled} placeholder='{"setting": "value"}' className="mt-2 min-h-20 w-full rounded-lg border p-3 font-mono text-xs disabled:bg-slate-100" /></details>
          </div>)}
          {selectedVersion?.stages && <p className="text-xs text-slate-500">يتحقق الخادم من دعم القدرات وصحة إعداد كل مرحلة قبل قبول المسودة أو نشرها.</p>}
        </div>}

        {activeSection === "identities" && <div className="grid gap-3 md:grid-cols-2">
          <div className="md:col-span-2"><Field label="الغرض التحريري للهوية" value={form.identity_purpose} onChange={(value) => updateField("identity_purpose", value)} disabled={formDisabled} multiline /></div>
          <Field label="الجمهور" value={form.audience} onChange={(value) => updateField("audience", value)} disabled={formDisabled} />
          <Field label="الصوت التحريري" value={form.voice} onChange={(value) => updateField("voice", value)} disabled={formDisabled} />
          <Field label="النبرة" value={form.tone} onChange={(value) => updateField("tone", value)} disabled={formDisabled} />
          <Field label="المبادئ (كل عنصر في سطر)" value={form.principles} onChange={(value) => updateField("principles", value)} disabled={formDisabled} multiline />
          <Field label="الأهداف (كل عنصر في سطر)" value={form.objectives} onChange={(value) => updateField("objectives", value)} disabled={formDisabled} multiline />
          <div className="md:col-span-2"><Field label="القيود التحريرية (كل عنصر في سطر)" value={form.constraints} onChange={(value) => updateField("constraints", value)} disabled={formDisabled} multiline /></div>
        </div>}

        {activeSection === "policies" && <div className="grid gap-3 md:grid-cols-2">
          <Field label="أقل عدد أحرف" type="number" value={form.min_content_chars} onChange={(value) => updateField("min_content_chars", value)} disabled={formDisabled} />
          <Field label="أقصى عدد أحرف" type="number" value={form.max_content_chars} onChange={(value) => updateField("max_content_chars", value)} disabled={formDisabled} />
          <Field label="عبارات مطلوبة (كل عبارة في سطر)" value={form.required_terms} onChange={(value) => updateField("required_terms", value)} disabled={formDisabled} multiline />
          <Field label="عبارات ممنوعة (كل عبارة في سطر)" value={form.forbidden_terms} onChange={(value) => updateField("forbidden_terms", value)} disabled={formDisabled} multiline />
          <SelectField label="السماح بالروابط" value={form.allow_urls} onChange={(value) => updateField("allow_urls", value)} disabled={formDisabled} options={[{ value: "true", label: "مسموح" }, { value: "false", label: "ممنوع" }]} />
        </div>}

        {activeSection === "output-contracts" && <div className="grid gap-3 md:grid-cols-2">
          <SelectField label="نوع المخرج" value={form.artifact_kind} onChange={(value) => {
            const mime: Record<string, string> = { POST: "text/plain", TEXT: "text/plain", IMAGE: "image/png", VIDEO: "video/mp4", AUDIO: "audio/wav" };
            setForm((current) => ({ ...current, artifact_kind: value, mime_type: mime[value], content_mode: ["IMAGE", "VIDEO", "AUDIO"].includes(value) ? "STORAGE_URI" : "INLINE", max_contract_chars: ["POST", "TEXT"].includes(value) ? current.max_contract_chars || "10000" : "" }));
          }} disabled={formDisabled} options={[{ value: "POST", label: "منشور" }, { value: "TEXT", label: "نص" }, { value: "IMAGE", label: "صورة" }, { value: "VIDEO", label: "فيديو" }, { value: "AUDIO", label: "صوت" }]} />
          <Field label="نوع MIME" value={form.mime_type} onChange={(value) => updateField("mime_type", value)} disabled={formDisabled} />
          <SelectField label="طريقة المحتوى" value={form.content_mode} onChange={(value) => updateField("content_mode", value)} disabled={formDisabled} options={[{ value: "INLINE", label: "مضمن داخل النظام" }, { value: "STORAGE_URI", label: "مرجع إلى تخزين دائم" }]} />
          <Field label="الحد الأقصى لأحرف المحتوى (للنص فقط)" type="number" value={form.max_contract_chars} onChange={(value) => updateField("max_contract_chars", value)} disabled={formDisabled || form.content_mode === "STORAGE_URI"} />
          <div className="md:col-span-2"><Field label="حقول البيانات الوصفية المطلوبة (كل حقل في سطر)" value={form.required_metadata_fields} onChange={(value) => updateField("required_metadata_fields", value)} disabled={formDisabled} multiline /></div>
          <p className="md:col-span-2 rounded-xl bg-slate-50 p-3 text-xs leading-6 text-slate-600">العقد يفرض توافق نوع MIME وطريقة التخزين مع نوع المخرج. تبقى قواعد الصلاحية النهائية في نموذج الخادم وخدمة النشر.</p>
        </div>}

        {deriveDialog && activeSection === "products" && <div role="dialog" aria-modal="true" aria-label="اشتقاق منتج مستقل" className="rounded-2xl border border-indigo-200 bg-indigo-50 p-4">
          <h3 className="font-bold">اشتقاق منتج مستقل من {selected?.key} v{selectedVersionNumber}</h3>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <Field label="مفتاح المنتج المشتق" value={deriveDialog.key} onChange={(value) => setDeriveDialog((current) => current ? { ...current, key: value.toUpperCase().replace(/[^A-Z0-9._-]/g, "_") } : current)} disabled={busy} />
            <Field label="اسم المنتج المشتق" value={deriveDialog.name} onChange={(value) => setDeriveDialog((current) => current ? { ...current, name: value } : current)} disabled={busy} />
            <div className="md:col-span-2"><Field label="غرض المنتج المشتق" value={deriveDialog.purpose} onChange={(value) => setDeriveDialog((current) => current ? { ...current, purpose: value } : current)} disabled={busy} multiline /></div>
          </div>
          <p className="mt-3 text-xs leading-6 text-slate-600">سيُنشأ سجل منتج مستقل مرتبط بإصدار الأصل. لا تُنسخ تعريفات المكونات؛ تُحفظ مراجع الإصدارات المشتركة كما هي.</p>
          <div className="mt-3 flex gap-2">
            <button type="button" disabled={busy || !deriveDialog.key.trim() || !deriveDialog.name.trim() || !deriveDialog.purpose.trim()} onClick={() => void deriveSelectedProduct()} className="rounded-lg bg-indigo-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">إنشاء المنتج المشتق</button>
            <button type="button" disabled={busy} onClick={() => setDeriveDialog(null)} className="rounded-lg border bg-white px-4 py-2 text-sm">إلغاء</button>
          </div>
        </div>}
        <div className="flex flex-wrap gap-2 border-t pt-4">
          {isNew ? <button type="button" disabled={busy || !form.key.trim() || !form.name.trim() || !form.purpose.trim() || (activeSection === "prompts" && !form.body.trim()) || (activeSection === "products" && (!form.prompt_key || !form.identity_key))} onClick={() => void createItem()} className="rounded-xl bg-indigo-600 px-5 py-3 font-bold text-white disabled:opacity-40">إنشاء ومسودة أولى</button>
            : <button type="button" disabled={busy || !selected || selectedVersion?.status === "ARCHIVED" || (selectedVersion?.status === "PUBLISHED")} onClick={() => void saveDraft()} className="rounded-xl bg-slate-900 px-5 py-3 font-bold text-white disabled:opacity-40">حفظ / إنشاء مسودة</button>}
          {selected && versionIsDraft && <button type="button" disabled={busy} onClick={() => selectedVersion && void versionAction("publish", selectedVersion)} className="rounded-xl bg-emerald-600 px-5 py-3 font-bold text-white disabled:opacity-40">نشر الإصدار</button>}
          {selected && selectedVersion && selectedVersion.status !== "ARCHIVED" && <button type="button" disabled={busy || selectedVersion.status === "PUBLISHED"} onClick={() => selectedVersion && void versionAction("archive", selectedVersion)} className="rounded-xl border px-5 py-3 font-semibold disabled:opacity-40">أرشفة الإصدار</button>}
          {selected && activeSection !== "prompts" && <button type="button" disabled={busy} onClick={() => {
            const active = selected.versions?.find((version) => version.status === "PUBLISHED");
            if (!active) return;
            changeVersion(active.version);
          }} className="rounded-xl border px-4 py-3 text-sm disabled:opacity-40">عرض الإصدار الفعّال</button>}
        </div>
        {message && <p role="status" className="rounded-xl bg-emerald-50 p-3 text-sm text-emerald-800">{message}</p>}
        {error && <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}
        {selected && selectedVersion && <details className="rounded-xl border p-3">
          <summary className="cursor-pointer text-sm font-semibold">تفاصيل الإصدار التقنية</summary>
          <div className="mt-3 space-y-2 text-xs text-slate-500">
            <p>الحالة: {statusLabel[selectedVersion.status] ?? selectedVersion.status} · الإصدار: v{selectedVersion.version}</p>
            {selectedVersion.created_at && <p>تاريخ الإنشاء: {selectedVersion.created_at}</p>}
            {selectedVersion.updated_at && <p>آخر تحديث: {selectedVersion.updated_at}</p>}
            <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-3">{JSON.stringify(selectedVersion.definition ?? selectedVersion.stages ?? { body: selectedVersion.body }, null, 2)}</pre>
          </div>
        </details>}
      </main>
    </div>
  </section>;
}
