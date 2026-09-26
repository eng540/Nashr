"""Embedded HTML interface for the Nashr hierarchical discovery console."""

NASHR_CONSOLE_HTML = '''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nashr Console</title><script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="min-h-screen bg-slate-50 text-slate-900">
<main class="mx-auto max-w-6xl px-4 py-8">
<header class="mb-8">
<p class="text-sm font-semibold text-indigo-600">Nashr — Vertical Slice 2</p>
<h1 class="mt-1 text-3xl font-bold">خريطة الكتاب والمخزون التحريري</h1>
<p class="mt-2 text-sm text-slate-600">ارفع الكتاب أو اختر كتاباً محفوظاً، ثم راقب الاستكشاف حتى تظهر الخريطة والمواد تدريجياً.</p>
</header>

<section class="rounded-2xl border bg-white p-5 shadow-sm">
<div class="grid gap-4 lg:grid-cols-2">
<div>
<label class="mb-2 block text-sm font-semibold">كتاب محفوظ</label>
<div class="flex gap-2">
<select id="source-select" class="min-w-0 flex-1 rounded-xl border bg-slate-50 p-3 text-sm"></select>
<button id="source-btn" class="rounded-xl bg-slate-800 px-5 py-3 font-semibold text-white disabled:opacity-50">استكشاف الكتاب</button>
</div>
</div>
<div>
<label class="mb-2 block text-sm font-semibold">رفع كتاب جديد</label>
<div class="flex gap-2">
<input id="pdf-file" type="file" accept="application/pdf" class="min-w-0 flex-1 rounded-xl border bg-slate-50 p-3 text-sm">
<button id="upload-btn" class="rounded-xl bg-indigo-600 px-5 py-3 font-semibold text-white disabled:opacity-50">رفع</button>
</div>
</div>
</div>
<div id="progress" class="mt-4 hidden rounded-xl bg-indigo-50 p-4 text-sm text-indigo-900"></div>
<div id="error" class="mt-4 hidden rounded-xl bg-red-50 p-4 text-sm text-red-700"></div>
<div id="retry-box" class="mt-3 hidden"><button id="retry-btn" class="rounded-xl bg-amber-600 px-5 py-3 font-semibold text-white">إعادة المحاولة</button></div>
</section>

<section id="book-section" class="mt-8 hidden">
<div class="rounded-2xl border bg-white p-5 shadow-sm">
<p class="text-xs font-semibold text-indigo-600">BOOK MAP</p>
<h2 id="book-title" class="mt-1 text-2xl font-bold"></h2>
<p id="book-description" class="mt-2 text-sm leading-7 text-slate-600"></p>
<div class="mt-4 flex flex-wrap gap-2 text-xs">
<span id="topic-count" class="rounded-full bg-slate-100 px-3 py-1"></span>
<span id="material-count" class="rounded-full bg-slate-100 px-3 py-1"></span>
<span id="book-status" class="rounded-full bg-slate-100 px-3 py-1"></span>
</div>
</div>
<div id="topics" class="mt-5 space-y-4"></div>
</section>

<section id="draft-section" class="mt-8 hidden rounded-2xl border border-indigo-200 bg-indigo-50 p-5">
<p class="text-xs font-semibold text-indigo-700">EDITORIAL DRAFT</p>
<h2 class="mt-1 text-xl font-bold">مسودة المادة المختارة</h2>
<textarea id="draft-content" dir="rtl" class="mt-4 min-h-80 w-full rounded-xl border bg-white p-4 leading-7"></textarea>
<button id="publish-btn" class="mt-4 w-full rounded-xl bg-emerald-600 px-6 py-4 font-bold text-white disabled:opacity-50">نشر بعد المراجعة في تيليجرام</button>
</section>

<section id="success-section" class="mt-8 hidden rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
<h2 class="text-xl font-bold text-emerald-800">تم النشر بنجاح</h2>
<p class="mt-2 text-sm">Telegram message ID</p><code id="external-id" class="mt-1 block rounded bg-white p-2"></code>
</section>
</main>

<script>
const $=id=>document.getElementById(id);
const state={sourceId:null,jobId:null,publicationId:null,pollTimer:null};

function setBusy(v){$('upload-btn').disabled=v;$('source-btn').disabled=v;$('retry-btn').disabled=v;$('publish-btn').disabled=v;}
function showProgress(msg){$('progress').classList.remove('hidden');$('progress').textContent=msg||'';}
function hideProgress(){$('progress').classList.add('hidden');}
function error(m){$('error').textContent=m;$('error').classList.remove('hidden');}
function clearError(){$('error').classList.add('hidden');$('retry-box').classList.add('hidden');}
function esc(t){return (t??'').toString().replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
async function request(url,opt={}){
 const r=await fetch(url,opt);const d=await r.json().catch(()=>({}));
 if(!r.ok)throw Error(d.detail||'تعذر تنفيذ العملية.');
 return d;
}
async function loadSources(){
 const sources=await request('/sources');
 const select=$('source-select');
 select.innerHTML='<option value="">اختر كتاباً محفوظاً...</option>'+sources.map(s=>'<option value="'+esc(s.id)+'">'+esc(s.book_title||s.filename)+'</option>').join('');
}
function stageLabel(stage){
 return ({PREPARING_DOCUMENT:'جاري تجهيز وثيقة الكتاب في Gemini',BUILDING_BOOK_MAP:'جاري بناء خريطة الكتاب',DISCOVERING_MATERIALS:'جاري اكتشاف المواد داخل المحاور',FINALIZING:'جاري إنهاء المخزون'}[stage]||stage||'جاري الاستكشاف');
}
function renderBook(d){
 $('book-title').textContent=d.book.title;$('book-description').textContent=d.book.description||'';
 $('topic-count').textContent=d.topics.length+' محاور';$('material-count').textContent=d.count+' مواد';
 $('book-status').textContent=d.job?('حالة الاستكشاف: '+d.job.status):'';
 const html=d.topics.map(function(t){
  const mats=t.materials.map(function(m){
   return '<button data-id="'+esc(m.id)+'" class="material text-right rounded-xl border bg-white p-4 hover:border-indigo-400 '+(t.discovery_status==='COMPLETED'?'':'opacity-90')+'"><div class="flex justify-between gap-3"><strong class="text-sm">'+esc(m.title)+'</strong><span class="text-xs text-slate-400">'+esc(m.kind||'مادة')+'</span></div><p class="mt-2 line-clamp-3 text-xs leading-6 text-slate-600">'+esc(m.content)+'</p><p class="mt-2 text-xs text-slate-400">'+esc(m.source_reference||'مرجع غير محدد')+'</p></button>';
  }).join('');
  return '<article class="rounded-2xl border bg-white p-5 shadow-sm"><div class="flex items-start justify-between gap-4"><div><p class="text-xs text-slate-400">المحور '+t.position+'</p><h3 class="text-lg font-bold">'+esc(t.title)+'</h3><p class="mt-1 text-sm leading-6 text-slate-600">'+esc(t.description)+'</p></div><div class="text-left"><span class="rounded-full bg-indigo-50 px-3 py-1 text-xs text-indigo-700">'+t.materials.length+' مواد</span><p class="mt-2 text-xs text-slate-400">'+esc(t.discovery_status)+'</p></div></div><div class="mt-4 grid gap-3">'+(mats||'<p class="text-sm text-slate-400">لم تُكتشف مواد في هذا المحور حتى الآن.</p>')+'</div></article>';
 }).join('');
 $('topics').innerHTML=html;$('book-section').classList.remove('hidden');
 document.querySelectorAll('.material').forEach(function(b){b.onclick=function(){selectMaterial(b.dataset.id);};});
}
async function refreshBook(){
 if(!state.sourceId)return;
 try{const d=await request('/sources/'+state.sourceId+'/book-map');renderBook(d);}catch(e){}
}
async function poll(){
 if(!state.jobId)return;
 try{
  const d=await request('/sources/'+state.sourceId+'/discovery/status');
  state.jobId=d.job_id||state.jobId;
  showProgress(stageLabel(d.stage)+' — '+(d.topics_completed||0)+' / '+(d.topics_total||0)+' محاور، '+(d.materials_discovered||0)+' مواد');
  await refreshBook();
  if(d.status==='COMPLETED'){showProgress('اكتمل الاستكشاف. الخريطة والمخزون جاهزان.');setBusy(false);await refreshBook();return;}
  if(d.status==='FAILED'){setBusy(false);error(d.error||'فشل الاستكشاف.');if(d.retryable)$('retry-box').classList.remove('hidden');return;}
  state.pollTimer=setTimeout(poll,2000);
 }catch(e){setBusy(false);error(e.message);}
}
async function startDiscovery(sourceId){
 clearError();state.sourceId=sourceId;state.jobId=null;$('draft-section').classList.add('hidden');$('success-section').classList.add('hidden');setBusy(true);
 try{
  const d=await request('/sources/'+sourceId+'/discovery',{method:'POST'});
  state.jobId=d.job_id;showProgress(stageLabel(d.stage));await refreshBook();poll();
 }catch(e){setBusy(false);error(e.message);}
}
async function selectMaterial(id){
 clearError();setBusy(true);showProgress('جاري إنشاء المسودة عبر المحرر الحالي...');
 try{
  const d=await request('/knowledge-units/'+id+'/draft',{method:'POST'});
  state.publicationId=d.id;$('draft-content').value=d.content||'';$('draft-section').classList.remove('hidden');$('draft-section').scrollIntoView({behavior:'smooth'});
 }catch(e){error(e.message);}finally{setBusy(false);}
}
$('source-btn').onclick=function(){const id=$('source-select').value;if(!id)return error('اختر كتاباً محفوظاً أولاً.');startDiscovery(id);};
$('upload-btn').onclick=async function(){
 clearError();const file=$('pdf-file').files[0];if(!file)return error('اختر ملف PDF أولاً.');setBusy(true);
 try{const form=new FormData();form.append('file',file);const s=await request('/sources',{method:'POST',body:form});await loadSources();$('source-select').value=s.id;startDiscovery(s.id);}
 catch(e){setBusy(false);error(e.message);}
};
$('retry-btn').onclick=function(){if(state.sourceId)startRetry();};
async function startRetry(){
 clearError();setBusy(true);
 try{const d=await request('/sources/'+state.sourceId+'/discovery/retry',{method:'POST'});state.jobId=d.job_id;showProgress(stageLabel(d.stage));poll();}
 catch(e){setBusy(false);error(e.message);}
}
$('publish-btn').onclick=async function(){
 if(!state.publicationId)return;clearError();setBusy(true);showProgress('جاري حفظ المراجعة والنشر في تيليجرام...');
 try{
  const d=await request('/publications/'+state.publicationId+'/publish',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:$('draft-content').value})});
  if(d.status!=='PUBLISHED')throw Error(d.error_message||'تعذر تأكيد النشر.');
  $('external-id').textContent=d.external_id||'غير متاح';$('success-section').classList.remove('hidden');hideProgress();
 }catch(e){error(e.message);}finally{setBusy(false);}
};
loadSources().catch(e=>error(e.message));
</script>
</body></html>'''
