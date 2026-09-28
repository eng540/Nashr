"""Nashr — visual PDF grounding benchmark and focused editorial comparison UI."""

import asyncio
import os
import time
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from google import genai
from google.genai import types
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.application.publications import slice_pdf_pages_as_bytes
from app.infrastructure.database.models import KnowledgeUnitModel, SourceModel
from app.infrastructure.database.session import get_session

benchmark_router = APIRouter()


class DraftResponse(BaseModel):
    content: str


SYSTEM_PROMPT = """أنت محرر محتوى عربي متخصص في تحويل المادة التراثية إلى منشور تيليجرام رصين ومكتمل.
اعتمد على الوثيقة المرفقة، ولا تختلق أو تبتر السياق.
- ابدأ بافتتاحية ذكية.
- اذكر أطراف القصة والحوار والسياق كاملًا.
- أورد الآيات والأشعار والشواهد بنصها كما وردت.
- اشرح الفائدة العملية للقارئ المعاصر.
- اختم باسم الكتاب ووسوم مناسبة.
- استخدم Markdown مناسبًا لتيليجرام.
- أخرج المنشور النهائي فقط داخل حقل content.
"""


@benchmark_router.get("/benchmark", response_class=HTMLResponse, include_in_schema=False)
async def benchmark_page() -> HTMLResponse:
    return HTMLResponse(content=BENCHMARK_HTML)


@benchmark_router.get("/benchmark/sources")
async def get_benchmark_sources(session: AsyncSession = Depends(get_session)):
    """List books first; materials are loaded only after a book is selected.

    ``file_payload`` is a deferred column, so we never materialise the binary
    payload here. We ask PostgreSQL for a single boolean instead of pulling
    tens of megabytes per source row.
    """
    has_payload_expr = SourceModel.file_payload.is_not(None).label("has_db_payload")
    result = await session.execute(
        select(SourceModel, has_payload_expr).order_by(SourceModel.created_at.desc())
    )
    return [
        {
            "id": str(source.id),
            "title": source.book_title or source.filename,
            "filename": source.filename,
            "file_exists": Path(source.storage_path).is_file(),
            "has_db_payload": bool(has_db_payload),
        }
        for source, has_db_payload in result.all()
    ]


@benchmark_router.get("/benchmark/sources/{source_id}/materials")
async def get_source_materials(source_id: UUID, session: AsyncSession = Depends(get_session)):
    """Return eligible materials belonging only to the selected book."""
    source = await session.get(SourceModel, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="الكتاب غير موجود.")
    excluded_kinds = ["مرجع", "قائمة مصادر", "فهرس"]
    result = await session.execute(
        select(KnowledgeUnitModel)
        .where(
            KnowledgeUnitModel.source_id == source_id,
            KnowledgeUnitModel.discovery_page_start.is_not(None),
            KnowledgeUnitModel.kind.not_in(excluded_kinds),
        )
        .order_by(KnowledgeUnitModel.position.asc())
    )
    return [
        {
            "id": str(unit.id),
            "title": unit.title,
            "kind": unit.kind or "مادة",
            "pages": f"ص {unit.discovery_page_start} - {unit.discovery_page_end}",
            "position": unit.position,
        }
        for unit in result.scalars().all()
    ]


@benchmark_router.post("/benchmark/run/{unit_id}")
async def run_benchmark_test(
    unit_id: UUID,
    file: UploadFile | None = File(None),
    session: AsyncSession = Depends(get_session),
):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY غير مهيأ.")

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
    try:
        storage_path = source.ensure_file_on_disk()
    except FileNotFoundError:
        if file is None:
            raise HTTPException(
                status_code=412,
                detail=f"ملف الكتاب الأصلي ({source.filename}) غير متوفر على السيرفر.",
            )
        content = await file.read()
        storage_path = Path(source.storage_path)
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_bytes(content)
        source.file_payload = content
        await session.commit()

    client = genai.Client(api_key=api_key)
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    # Approach A: send a visual, bounded PDF slice instead of lossy local text extraction.
    t0_a = time.perf_counter()
    pdf_slice = slice_pdf_pages_as_bytes(
        str(storage_path), unit.discovery_page_start or 1, unit.discovery_page_end or 1, 10
    )
    slice_part = types.Part.from_bytes(data=pdf_slice, mime_type="application/pdf")
    prompt_a = f"""اسم الكتاب: {source.book_title or source.filename}
عنوان المادة: {unit.title}
الملخص الأولي: {unit.content}

هذه شريحة PDF بصرية من 10 صفحات تغطي موضع المادة وسياقها. استخرج القصة والشواهد كاملة كما وردت، ثم صغ منشور تيليجرام مكتملًا دون اختصار مخل."""
    response_a = await asyncio.to_thread(
        client.models.generate_content,
        model=model,
        contents=[SYSTEM_PROMPT, prompt_a, slice_part],
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=DraftResponse
        ),
    )
    latency_a = time.perf_counter() - t0_a
    usage_a = getattr(response_a, "usage_metadata", None)

    # Approach B: retrieve from the full Gemini document for comparison.
    t0_b = time.perf_counter()
    if source.gemini_file_uri and source.gemini_file_mime_type:
        document_part = types.Part.from_uri(
            file_uri=source.gemini_file_uri, mime_type=source.gemini_file_mime_type
        )
    else:
        uploaded = await asyncio.to_thread(client.files.upload, file=str(storage_path))
        document_part = types.Part.from_uri(file_uri=uploaded.uri, mime_type=uploaded.mime_type)
    prompt_b = f"""اسم الكتاب: {source.book_title or source.filename}
عنوان المادة: {unit.title}
الملخص المستخرج: {unit.content}
ابحث في وثيقة الكتاب الكاملة عن السياق الأصلي، ثم اكتب منشور تيليجرام مكتملًا يضم الحوار والقصة والشواهد دون بتر."""
    response_b = await asyncio.to_thread(
        client.models.generate_content,
        model=model,
        contents=[SYSTEM_PROMPT, prompt_b, document_part],
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=DraftResponse
        ),
    )
    latency_b = time.perf_counter() - t0_b
    usage_b = getattr(response_b, "usage_metadata", None)

    def metric(usage, name: str):
        return getattr(usage, name, "غير متاح")

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
            "input_tokens": metric(usage_a, "prompt_token_count"),
            "output_tokens": metric(usage_a, "candidates_token_count"),
            "draft": response_a.parsed.content if response_a.parsed else "فشل التوليد",
        },
        "approach_b": {
            "latency": round(latency_b, 2),
            "input_tokens": metric(usage_b, "prompt_token_count"),
            "output_tokens": metric(usage_b, "candidates_token_count"),
            "draft": response_b.parsed.content if response_b.parsed else "فشل التوليد",
        },
    }


BENCHMARK_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nashr — مختبر الجودة</title><script src="https://cdn.tailwindcss.com"></script>
<style>body{font-family:ui-sans-serif,system-ui,sans-serif}.step{transition:.2s}.step.active{border-color:#4f46e5;background:#eef2ff}.step.done{border-color:#10b981;background:#ecfdf5}</style>
</head>
<body class="min-h-screen bg-slate-50 text-slate-900">
<main class="mx-auto max-w-6xl px-4 py-8 sm:py-12">
<header class="mb-8 flex flex-wrap items-start justify-between gap-4 border-b pb-6">
<div><a href="/console" class="text-sm font-semibold text-indigo-600 hover:underline">← العودة إلى مساحة العمل</a>
<h1 class="mt-3 text-3xl font-bold tracking-tight">مختبر الجودة والتحرير</h1>
<p class="mt-2 max-w-2xl text-sm leading-7 text-slate-600">قارن بين قراءة شريحة بصرية من الكتاب واسترجاع الوثيقة الكاملة، مع إبقاء الاختيار واضحًا ومتدرجًا.</p></div>
<div class="rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-slate-500 shadow-sm">تجربة داخلية</div>
</header>
<section class="mb-6 grid gap-3 sm:grid-cols-3">
<div id="step-source" class="step active rounded-2xl border-2 p-4"><p class="text-xs font-bold text-indigo-600">01</p><p class="mt-1 font-bold">اختر الكتاب</p><p class="mt-1 text-xs text-slate-500">نحدد المصدر أولًا</p></div>
<div id="step-material" class="step rounded-2xl border-2 border-slate-200 bg-white p-4"><p class="text-xs font-bold text-slate-400">02</p><p class="mt-1 font-bold">اختر المادة</p><p class="mt-1 text-xs text-slate-500">نعرض مواد هذا الكتاب فقط</p></div>
<div id="step-run" class="step rounded-2xl border-2 border-slate-200 bg-white p-4"><p class="text-xs font-bold text-slate-400">03</p><p class="mt-1 font-bold">شغّل المقارنة</p><p class="mt-1 text-xs text-slate-500">نقيس الجودة والزمن</p></div>
</section>
<section class="rounded-3xl border bg-white p-5 shadow-sm sm:p-7">
<div class="grid gap-6 lg:grid-cols-2">
<div><label class="mb-2 block text-sm font-bold">الكتاب المصدر</label><select id="source-select" class="w-full rounded-xl border bg-slate-50 p-3 text-sm"></select><span id="source-status" class="mt-3 hidden inline-flex rounded-full px-3 py-1 text-xs font-semibold"></span></div>
<div><label class="mb-2 block text-sm font-bold">المادة المراد اختبارها</label><select id="unit-select" disabled class="w-full rounded-xl border bg-slate-50 p-3 text-sm disabled:cursor-not-allowed disabled:opacity-50"></select></div>
</div>
<div id="restore-box" class="mt-6 hidden rounded-2xl border border-amber-300 bg-amber-50 p-4"><p id="restore-msg" class="font-bold text-amber-900"></p><p class="mt-1 text-xs leading-6 text-amber-800">اختر نسخة PDF مرة واحدة؛ سيتم حفظها تلقائيًا لاستعمالها لاحقًا.</p><input id="restore-file" type="file" accept="application/pdf" class="mt-3 w-full rounded-lg border bg-white p-2 text-xs"></div>
<button id="run-btn" disabled class="mt-6 w-full rounded-xl bg-indigo-600 py-3.5 font-bold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50">تشغيل فحص الجودة والمقارنة</button>
<div id="progress" class="mt-4 hidden rounded-2xl bg-indigo-50 p-4 text-sm leading-7 text-indigo-900"></div><div id="error" class="mt-4 hidden rounded-2xl bg-red-50 p-4 text-sm leading-7 text-red-700"></div>
</section>
<section id="results" class="mt-8 hidden space-y-6"><div class="rounded-2xl border bg-white p-5 shadow-sm"><span id="res-kind" class="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold"></span><h2 id="res-title" class="mt-3 text-2xl font-bold"></h2><p id="res-meta" class="mt-1 text-xs text-slate-500"></p><p id="res-summary" class="mt-4 rounded-xl border bg-slate-50 p-4 text-sm leading-7 text-slate-600"></p></div>
<div class="overflow-hidden rounded-2xl border bg-white shadow-sm"><div class="bg-slate-900 px-5 py-3 text-sm font-bold text-white">مصفوفة القياس</div><div class="overflow-x-auto"><table class="w-full min-w-[620px] text-right text-sm"><thead class="border-b bg-slate-50 text-xs text-slate-500"><tr><th class="p-4">المعيار</th><th class="p-4 text-emerald-700">أ — شريحة PDF بصرية</th><th class="p-4 text-blue-700">ب — الوثيقة الكاملة</th></tr></thead><tbody class="divide-y"><tr><td class="p-4 font-semibold">زمن التنفيذ</td><td id="time-a" class="p-4 font-mono font-bold text-emerald-600">—</td><td id="time-b" class="p-4 font-mono font-bold text-blue-600">—</td></tr><tr><td class="p-4 font-semibold">توكن المدخلات</td><td id="tokens-in-a" class="p-4 font-mono text-emerald-600">—</td><td id="tokens-in-b" class="p-4 font-mono text-blue-600">—</td></tr><tr><td class="p-4 font-semibold">توكن المخرجات</td><td id="tokens-out-a" class="p-4 font-mono">—</td><td id="tokens-out-b" class="p-4 font-mono">—</td></tr></tbody></table></div></div>
<div class="grid gap-6 lg:grid-cols-2"><article class="rounded-2xl border border-emerald-200 bg-emerald-50/40 p-5"><h3 class="font-bold text-emerald-900">المسودة أ — القراءة البصرية</h3><div id="draft-a" class="mt-4 whitespace-pre-wrap text-sm leading-8"></div></article><article class="rounded-2xl border border-blue-200 bg-blue-50/40 p-5"><h3 class="font-bold text-blue-900">المسودة ب — الوثيقة الكاملة</h3><div id="draft-b" class="mt-4 whitespace-pre-wrap text-sm leading-8"></div></article></div></section>
</main>
<script>
const $=id=>document.getElementById(id);let sources=[];
function setStep(n){['step-source','step-material','step-run'].forEach((id,i)=>$(id).className='step rounded-2xl border-2 p-4 '+(i<n?'done ':'')+(i===n?'active ':'')+(i>n?'border-slate-200 bg-white':''));}
function showError(msg){$('error').textContent=msg;$('error').classList.remove('hidden');}
function clearError(){$('error').classList.add('hidden');}
function formatMetric(v){return typeof v==='number'?v.toLocaleString('ar-EG'):v||'غير متاح';}
async function loadSources(){const r=await fetch('/benchmark/sources');if(!r.ok)throw Error('تعذر تحميل الكتب.');sources=await r.json();$('source-select').innerHTML='<option value="">اختر كتابًا محفوظًا...</option>'+sources.map(s=>`<option value="${s.id}">${s.title} — ${s.filename}</option>`).join('');}
$('source-select').onchange=async()=>{clearError();const id=$('source-select').value;const unit=$('unit-select');$('run-btn').disabled=true;unit.disabled=true;unit.innerHTML='';$('source-status').classList.add('hidden');$('restore-box').classList.add('hidden');if(!id){setStep(0);return;}const source=sources.find(s=>s.id===id);$('source-status').className='mt-3 inline-flex rounded-full px-3 py-1 text-xs font-semibold '+(source.file_exists||source.has_db_payload?'bg-emerald-100 text-emerald-800':'bg-amber-100 text-amber-800');$('source-status').textContent=source.file_exists||source.has_db_payload?'الملف متوفر وجاهز':'الملف يحتاج إلى استعادة';$('source-status').classList.remove('hidden');if(!source.file_exists&&!source.has_db_payload){$('restore-msg').textContent=`ملف الكتاب «${source.filename}» غير موجود على القرص.`;$('restore-box').classList.remove('hidden');}unit.innerHTML='<option>جاري تحميل مواد الكتاب...</option>';try{const r=await fetch(`/benchmark/sources/${id}/materials`);if(!r.ok)throw Error();const materials=await r.json();if(!materials.length){unit.innerHTML='<option value="">لا توجد مواد قابلة للمقارنة</option>';setStep(1);return;}unit.innerHTML='<option value="">اختر مادة من هذا الكتاب...</option>'+materials.map(m=>`<option value="${m.id}">[${m.kind}] #${m.position} ${m.title} (${m.pages})</option>`).join('');unit.disabled=false;setStep(1);}catch(e){unit.innerHTML='<option value="">تعذر تحميل المواد</option>';showError('تعذر تحميل مواد هذا الكتاب.');}};
$('unit-select').onchange=()=>{const ready=Boolean($('unit-select').value);$('run-btn').disabled=!ready;setStep(ready?2:1);};
$('run-btn').onclick=async()=>{clearError();const source=sources.find(s=>s.id===$('source-select').value);const file=$('restore-file').files[0];if(source&&!source.file_exists&&!source.has_db_payload&&!file){showError(`يرجى اختيار ملف «${source.filename}» لاستعادته أولًا.`);return;}$('run-btn').disabled=true;$('progress').classList.remove('hidden');$('progress').textContent='جاري إرسال شريحة PDF البصرية ثم مقارنة الوثيقة الكاملة...';$('results').classList.add('hidden');try{const form=new FormData();if(file)form.append('file',file);const r=await fetch('/benchmark/run/'+$('unit-select').value,{method:'POST',body:form});const d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.detail||'تعذر تشغيل المقارنة.');$('res-title').textContent=d.material.title;$('res-kind').textContent=d.material.kind||'مادة';$('res-meta').textContent=`${d.material.book} | ${d.material.pages}`;$('res-summary').textContent=d.material.summary;$('time-a').textContent=d.approach_a.latency+' ثانية';$('time-b').textContent=d.approach_b.latency+' ثانية';$('tokens-in-a').textContent=formatMetric(d.approach_a.input_tokens);$('tokens-in-b').textContent=formatMetric(d.approach_b.input_tokens);$('tokens-out-a').textContent=formatMetric(d.approach_a.output_tokens);$('tokens-out-b').textContent=formatMetric(d.approach_b.output_tokens);$('draft-a').textContent=d.approach_a.draft;$('draft-b').textContent=d.approach_b.draft;$('results').classList.remove('hidden');$('results').scrollIntoView({behavior:'smooth'});$('progress').classList.add('hidden');}catch(e){$('progress').classList.add('hidden');showError(e.message);}finally{$('run-btn').disabled=!$('unit-select').value;}};
loadSources().catch(e=>showError(e.message));
</script></body></html>"""