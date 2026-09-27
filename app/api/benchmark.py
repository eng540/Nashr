"""Nashr — Browser-based A/B Editorial Grounding Benchmark with Self-Healing Storage."""

import asyncio
import logging
import os
import time
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from google import genai
from google.genai import types
from pydantic import BaseModel
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.database.models import KnowledgeUnitModel, SourceModel
from app.infrastructure.database.session import get_session

logger = logging.getLogger(__name__)
benchmark_router = APIRouter()


class DraftResponse(BaseModel):
    content: str


SYSTEM_PROMPT = """أنت محرر محتوى عربي متخصص في تحويل المادة التراثية إلى منشور تيليجرام عالي الجودة.
مهمتك صياغة منشور مكتمل يحافظ على معنى وسياق المصدر دون اختلاق أو بتر للقصة.

قواعد التحرير:
- ابدأ بسطر افتتاحي جذاب (Hook) يلفت الانتباه.
- اعرض القصة أو الشاهد بوضوح مع ذكر أطراف الحوار وسياق الموقف كاملاً كما ورد في المادة المصدرية.
- اشرح الفائدة أو الإسقاط العملي المباشر للقارئ في حياته اليومية.
- اختم باسم الكتاب ووسوم مناسبة.
- استخدم Markdown مناسباً لتيليجرام.
- أخرج المنشور النهائي فقط داخل حقل content.
"""


def extract_page_text(pdf_path: str, page_start: int, page_end: int) -> str:
    """Extract raw text from physical PDF page span."""
    reader = PdfReader(pdf_path)
    extracted_text = []
    total_pages = len(reader.pages)
    start_idx = max(0, page_start - 1)
    end_idx = min(total_pages, page_end)
    for i in range(start_idx, end_idx):
        text = reader.pages[i].extract_text() or ""
        extracted_text.append(f"--- [صفحة {i + 1}] ---\n{text}")
    return "\n\n".join(extracted_text)


@benchmark_router.get("/benchmark", response_class=HTMLResponse, include_in_schema=False)
async def benchmark_page() -> HTMLResponse:
    """Render the interactive A/B benchmark interface."""
    return HTMLResponse(content=BENCHMARK_HTML)


@benchmark_router.get("/benchmark/materials")
async def get_benchmark_materials(session: AsyncSession = Depends(get_session)):
    """Fetch eligible literary/thematic materials for benchmarking."""
    excluded_kinds = ["مرجع", "قائمة مصادر", "فهرس"]
    query = (
        select(KnowledgeUnitModel)
        .options(selectinload(KnowledgeUnitModel.source))
        .where(
            KnowledgeUnitModel.discovery_page_start.is_not(None),
            KnowledgeUnitModel.kind.not_in(excluded_kinds),
        )
        .order_by(KnowledgeUnitModel.position.asc())
        .limit(100)
    )
    units = (await session.execute(query)).scalars().all()
    return [
        {
            "id": str(u.id),
            "title": u.title,
            "kind": u.kind or "مادة",
            "pages": f"ص {u.discovery_page_start} - {u.discovery_page_end}",
            "book": u.source.book_title or u.source.filename if u.source else "المصدر",
            "file_exists": Path(u.source.storage_path).is_file() if u.source else False,
        }
        for u in units
    ]


@benchmark_router.post("/benchmark/run/{unit_id}")
async def run_benchmark_test(
    unit_id: UUID,
    file: UploadFile | None = File(None),
    session: AsyncSession = Depends(get_session),
):
    """Execute A/B test with auto-recovery for missing physical storage."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY غير مهيأ في المتغيرات.")

    client = genai.Client(api_key=api_key)
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    unit = (
        await session.execute(
            select(KnowledgeUnitModel)
            .options(selectinload(KnowledgeUnitModel.source))
            .where(KnowledgeUnitModel.id == unit_id)
        )
    ).scalar_one_or_none()

    if not unit or not unit.source:
        raise HTTPException(status_code=404, detail="المادة أو المصدر غير موجود.")

    source = unit.source
    storage_path = Path(source.storage_path)

    # معالجة استعادة الملف إذا كان مفقوداً من قرص السيرفر المؤقت
    if not storage_path.is_file():
        if file is None:
            raise HTTPException(
                status_code=412,
                detail="FILE_MISSING_ON_DISK",
            )
        # حفظ الملف المرفوع في مكانه الصحيح مباشرة
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        content = await file.read()
        storage_path.write_bytes(content)
        logger.info("event=STORAGE_RESTORED path=%s", storage_path)

    # -------------------------------------------------------------
    # Approach A: Deterministic Exact Page Grounding (pypdf)
    # -------------------------------------------------------------
    t0_a = time.perf_counter()
    page_text = extract_page_text(
        str(storage_path),
        unit.discovery_page_start or 1,
        unit.discovery_page_end or 1,
    )
    prompt_a = f"""اسم الكتاب: {source.book_title or source.filename}
عنوان الفكرة: {unit.title}
الملخص المستخرج: {unit.content}

النص الكامل المأخوذ من نفس الصفحات ({unit.discovery_page_start}-{unit.discovery_page_end}) من الكتاب الأصلي:
{page_text}
"""
    resp_a = await asyncio.to_thread(
        client.models.generate_content,
        model=model,
        contents=[SYSTEM_PROMPT, prompt_a],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=DraftResponse,
        ),
    )
    latency_a = time.perf_counter() - t0_a
    usage_a = getattr(resp_a, "usage_metadata", None)

    # -------------------------------------------------------------
    # Approach B: Retrieval from Uploaded Gemini Document
    # -------------------------------------------------------------
    t0_b = time.perf_counter()
    if not source.gemini_file_uri or not source.gemini_file_mime_type:
        uploaded = await asyncio.to_thread(client.files.upload, file=str(storage_path))
        doc_part = types.Part.from_uri(file_uri=uploaded.uri, mime_type=uploaded.mime_type)
    else:
        doc_part = types.Part.from_uri(file_uri=source.gemini_file_uri, mime_type=source.gemini_file_mime_type)

    prompt_b = f"""اسم الكتاب: {source.book_title or source.filename}
عنوان الفكرة المستخرجة: {unit.title}
النص المقتضب المستخرج: {unit.content}

المهمة:
ابحث داخل وثيقة الكتاب المرفقة عن السياق الكامل لهذه القصة/المادة المحددة، ثم صغ منها منشور تيليجرام مكتملاً يضم تفاصيل الحوار والقصة كاملة كما وردت في الأصل.
"""
    resp_b = await asyncio.to_thread(
        client.models.generate_content,
        model=model,
        contents=[SYSTEM_PROMPT, prompt_b, doc_part],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=DraftResponse,
        ),
    )
    latency_b = time.perf_counter() - t0_b
    usage_b = getattr(resp_b, "usage_metadata", None)

    return {
        "material": {
            "title": unit.title,
            "kind": unit.kind,
            "pages": f"ص {unit.discovery_page_start} - {unit.discovery_page_end}",
            "book": source.book_title or source.filename,
            "summary": unit.content,
        },
        "approach_a": {
            "latency": round(latency_a, 2),
            "input_tokens": getattr(usage_a, "prompt_token_count", "غير متاح"),
            "output_tokens": getattr(usage_a, "candidates_token_count", "غير متاح"),
            "draft": resp_a.parsed.content if resp_a.parsed else "فشل التوليد",
        },
        "approach_b": {
            "latency": round(latency_b, 2),
            "input_tokens": getattr(usage_b, "prompt_token_count", "غير متاح"),
            "output_tokens": getattr(usage_b, "candidates_token_count", "غير متاح"),
            "draft": resp_b.parsed.content if resp_b.parsed else "فشل التوليد",
        },
    }


BENCHMARK_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nashr — مختبر المقارنة الميدانية</title>
<script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="min-h-screen bg-slate-50 text-slate-900">
<main class="mx-auto max-w-6xl px-4 py-8">
  <header class="mb-8 border-b pb-6">
    <a href="/console" class="text-xs font-semibold text-indigo-600 hover:underline">← العودة إلى Nashr Console</a>
    <h1 class="mt-2 text-3xl font-bold">مختبر المقارنة الميدانية (A/B Grounding Benchmark)</h1>
    <p class="mt-2 text-sm text-slate-600">
      اختبار عملي حاسم ومباشر: هل الإسناد الحتمي بنص الصفحة (pypdf) أفضل وأدق، أم البحث والاسترجاع الدلالي من وثيقة جوجل؟
    </p>
  </header>

  <section class="rounded-2xl border bg-white p-6 shadow-sm">
    <label class="block text-sm font-semibold mb-2">اختر مادة تراثية (قصة، حكمة، حوار):</label>
    <div class="flex flex-col sm:flex-row gap-3">
      <select id="unit-select" class="flex-1 rounded-xl border bg-slate-50 p-3 text-sm"></select>
      <button id="run-btn" class="rounded-xl bg-indigo-600 px-6 py-3 font-bold text-white transition hover:bg-indigo-700 disabled:opacity-50">
        🚀 تشغيل المقارنة الميدانية
      </button>
    </div>

    <!-- صندوق الاستعادة التلقائية للملف إذا فُقد من قرص الحاوية -->
    <div id="file-restore-box" class="mt-4 hidden rounded-xl border border-amber-300 bg-amber-50 p-4">
      <p class="text-sm font-bold text-amber-900">⚠️ تنبيه: ملف الـ PDF غير موجود على قرص السيرفر الحالي (بسبب إعادة بناء الحاوية)</p>
      <p class="mt-1 text-xs text-amber-700">اختر ملف الكتاب من جهازك مرة واحدة، وسيقوم السيرفر بحفظه وتشغيل المقارنة فوراً:</p>
      <div class="mt-3 flex gap-2">
        <input type="file" id="restore-file" accept="application/pdf" class="rounded-lg border bg-white p-2 text-xs flex-1">
        <button id="restore-btn" class="rounded-lg bg-amber-600 px-4 py-2 text-xs font-bold text-white hover:bg-amber-700">رفع وتشغيل</button>
      </div>
    </div>

    <div id="progress" class="mt-4 hidden rounded-xl bg-indigo-50 p-4 text-sm text-indigo-900"></div>
    <div id="error" class="mt-4 hidden rounded-xl bg-red-50 p-4 text-sm text-red-700 font-semibold leading-relaxed"></div>
  </section>

  <!-- النتائج -->
  <section id="results" class="mt-8 hidden space-y-6">
    <div class="rounded-2xl border bg-white p-5 shadow-sm">
      <span class="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700" id="res-kind"></span>
      <h2 class="mt-2 text-xl font-bold" id="res-title"></h2>
      <p class="mt-1 text-xs text-slate-500" id="res-meta"></p>
      <p class="mt-3 text-xs leading-6 text-slate-600 bg-slate-50 p-3 rounded-xl border" id="res-summary"></p>
    </div>

    <div class="overflow-hidden rounded-2xl border bg-white shadow-sm">
      <div class="bg-slate-900 px-6 py-3 text-white font-bold text-sm">مصفوفة القياس الرقمية الحية</div>
      <table class="w-full text-right text-sm">
        <thead class="bg-slate-50 border-b text-xs text-slate-500">
          <tr>
            <th class="p-4">المعيار الهندسي</th>
            <th class="p-4 text-emerald-700">الخيار (أ): الإسناد الحتمي بنص الصفحة</th>
            <th class="p-4 text-blue-700">الخيار (ب): استرجاع وثيقة جوجل الكاملة</th>
          </tr>
        </thead>
        <tbody class="divide-y text-slate-700">
          <tr>
            <td class="p-4 font-semibold">زمن التنفيذ (Latency)</td>
            <td class="p-4 font-mono font-bold text-emerald-600" id="time-a">-</td>
            <td class="p-4 font-mono font-bold text-blue-600" id="time-b">-</td>
          </tr>
          <tr>
            <td class="p-4 font-semibold">توكن المدخلات (Input Tokens)</td>
            <td class="p-4 font-mono font-bold text-emerald-600" id="tokens-in-a">-</td>
            <td class="p-4 font-mono font-bold text-blue-600" id="tokens-in-b">-</td>
          </tr>
          <tr>
            <td class="p-4 font-semibold">توكن المخرجات (Output Tokens)</td>
            <td class="p-4 font-mono" id="tokens-out-a">-</td>
            <td class="p-4 font-mono" id="tokens-out-b">-</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="grid gap-6 lg:grid-cols-2">
      <div class="rounded-2xl border border-emerald-200 bg-emerald-50/40 p-5 shadow-sm">
        <div class="flex items-center justify-between pb-3 border-b border-emerald-200">
          <h3 class="font-bold text-emerald-900">مسودة الخيار (أ) — نص الصفحة الكامل</h3>
          <span class="text-xs bg-emerald-100 text-emerald-800 px-2.5 py-1 rounded-full font-semibold">Pypdf Slicing</span>
        </div>
        <div class="mt-4 whitespace-pre-wrap text-sm leading-7 text-slate-800 font-sans" id="draft-a"></div>
      </div>

      <div class="rounded-2xl border border-blue-200 bg-blue-50/40 p-5 shadow-sm">
        <div class="flex items-center justify-between pb-3 border-b border-blue-200">
          <h3 class="font-bold text-blue-900">مسودة الخيار (ب) — استرجاع وثيقة جوجل</h3>
          <span class="text-xs bg-blue-100 text-blue-800 px-2.5 py-1 rounded-full font-semibold">Gemini File Part</span>
        </div>
        <div class="mt-4 whitespace-pre-wrap text-sm leading-7 text-slate-800 font-sans" id="draft-b"></div>
      </div>
    </div>
  </section>
</main>

<script>
const $ = id => document.getElementById(id);
let cachedMaterials = [];

async function loadMaterials() {
  try {
    const res = await fetch('/benchmark/materials');
    cachedMaterials = await res.json();
    const sel = $('unit-select');
    sel.innerHTML = cachedMaterials.map(m => 
      `<option value="${m.id}">[${m.kind}] ${m.title} (${m.pages})</option>`
    ).join('');
    checkSelectedFile();
  } catch (e) {
    $('error').textContent = 'تعذر تحميل المواد من قاعدة البيانات.';
    $('error').classList.remove('hidden');
  }
}

function checkSelectedFile() {
  const unitId = $('unit-select').value;
  const item = cachedMaterials.find(m => m.id === unitId);
  if (item && !item.file_exists) {
    $('file-restore-box').classList.remove('hidden');
  } else {
    $('file-restore-box').classList.add('hidden');
  }
}

$('unit-select').onchange = checkSelectedFile;

async function executeRun(fileObj) {
  const unitId = $('unit-select').value;
  if (!unitId) return;

  $('run-btn').disabled = true;
  $('results').classList.add('hidden');$('error').classList.add('hidden');
  $('progress').classList.remove('hidden');$('progress').textContent = 'جاري تنفيذ الاختبار المقارن... جاري استدعاء الخيار (أ) ثم الخيار (ب)...';

  try {
    const form = new FormData();
    if (fileObj) form.append('file', fileObj);

    const res = await fetch('/benchmark/run/' + unitId, { method: 'POST', body: form });
    const data = await res.json().catch(() => ({}));

    if (res.status === 412) {
      $('progress').classList.add('hidden');
      $('file-restore-box').classList.remove('hidden');$('run-btn').disabled = false;
      return;
    }

    if (!res.ok) throw new Error(data.detail || 'حدث خطأ في السيرفر.');

    $('res-title').textContent = data.material.title;
    $('res-kind').textContent = data.material.kind || 'مادة';
    $('res-meta').textContent = `${data.material.book} | ${data.material.pages}`;
    $('res-summary').textContent = data.material.summary;

    $('time-a').textContent = data.approach_a.latency + ' ثانية';
    $('time-b').textContent = data.approach_b.latency + ' ثانية';
    $('tokens-in-a').textContent = Number(data.approach_a.input_tokens).toLocaleString() + ' توكن';
    $('tokens-in-b').textContent = Number(data.approach_b.input_tokens).toLocaleString() + ' توكن';
    $('tokens-out-a').textContent = data.approach_a.output_tokens + ' توكن';
    $('tokens-out-b').textContent = data.approach_b.output_tokens + ' توكن';

    $('draft-a').textContent = data.approach_a.draft;
    $('draft-b').textContent = data.approach_b.draft;

    $('file-restore-box').classList.add('hidden');$('progress').classList.add('hidden');
    $('results').classList.remove('hidden');$('results').scrollIntoView({ behavior: 'smooth' });
  } catch (err) {
    $('progress').classList.add('hidden');$('error').textContent = err.message;
    $('error').classList.remove('hidden');
  } finally {
    $('run-btn').disabled = false;
  }
}

$('run-btn').onclick = () => executeRun(null);$('restore-btn').onclick = () => {
  const f = $('restore-file').files[0];
  if (!f) return alert('الرجاء اختيار ملف PDF أولاً.');
  executeRun(f);
};

loadMaterials();
</script>
</body>
</html>
"""