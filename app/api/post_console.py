"""Dedicated editorial production and Post Bank console."""

NASHR_POSTS_HTML = r'''<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nashr — المنشورات</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
body{font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
.card{transition:box-shadow .15s ease,border-color .15s ease}.card:hover{box-shadow:0 8px 24px rgb(15 23 42/.08)}
</style>
</head>
<body class="min-h-screen bg-slate-50 text-slate-900">
<main class="mx-auto max-w-7xl px-4 py-7 sm:py-10">
<header class="mb-7 flex flex-wrap items-start justify-between gap-4 border-b pb-6">
  <div>
    <p class="text-sm font-semibold text-indigo-600">Nashr — المنشورات</p>
    <h1 class="mt-1 text-3xl font-bold tracking-tight">مصنع المنشورات</h1>
    <p class="mt-2 max-w-3xl text-sm leading-7 text-slate-600">هنا فقط تعمل على تحويل مواد الكتاب إلى Posts، ثم مراجعتها واعتمادها. الجدولة والنشر لهما مسارهما بعد اكتمال هذه المرحلة.</p>
  </div>
  <nav class="flex flex-wrap gap-2 text-sm" aria-label="التنقل الرئيسي">
    <a href="/console" class="rounded-full bg-white px-4 py-2 font-semibold text-slate-600 shadow-sm hover:text-indigo-600">📚 المكتبة</a>
    <span class="rounded-full bg-indigo-50 px-4 py-2 font-semibold text-indigo-700">✍️ المنشورات</span>
    <a href="/console#scheduling-section" class="rounded-full bg-white px-4 py-2 font-semibold text-slate-600 shadow-sm hover:text-indigo-600">📅 الجدولة</a>
  </nav>
</header>

<section class="mb-7 rounded-3xl border bg-white p-5 shadow-sm sm:p-7">
  <div class="flex flex-wrap items-start justify-between gap-4">
    <div>
      <p class="text-xs font-bold text-indigo-600">01 — الإنتاج</p>
      <h2 class="mt-1 text-2xl font-bold">أنشئ Posts من كتاب</h2>
      <p class="mt-2 max-w-3xl text-sm leading-7 text-slate-600">اختر كتابًا ثم حدد نطاق العمل. لا تحتاج إلى إنشاء كل Post يدويًا؛ Nashr يشغل Production Job ويحفظ الناتج في Post Bank.</p>
    </div>
    <a href="/console" class="text-sm font-semibold text-indigo-600 hover:underline">← العودة إلى الكتاب</a>
  </div>

  <div class="mt-6 grid gap-4 lg:grid-cols-3">
    <label class="block"><span class="mb-2 block text-sm font-bold">الكتاب</span>
      <select id="source" class="w-full rounded-xl border bg-slate-50 p-3 text-sm"></select>
    </label>
    <label class="block"><span class="mb-2 block text-sm font-bold">نطاق الإنتاج</span>
      <select id="scope" class="w-full rounded-xl border bg-slate-50 p-3 text-sm">
        <option value="SOURCE">الكتاب كاملًا</option>
        <option value="TOPIC">محور محدد</option>
        <option value="SELECTION">مواد أحددها بنفسي</option>
      </select>
    </label>
    <label id="topic-wrap" class="hidden block"><span class="mb-2 block text-sm font-bold">المحور</span>
      <select id="topic" class="w-full rounded-xl border bg-slate-50 p-3 text-sm"></select>
    </label>
  </div>

  <div id="selection-wrap" class="mt-5 hidden rounded-2xl border bg-slate-50 p-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div><h3 class="font-bold">اختر المواد</h3><p id="selection-help" class="mt-1 text-xs text-slate-500"></p></div>
      <div class="flex gap-2"><button id="select-all-materials" class="rounded-lg border bg-white px-3 py-2 text-xs font-semibold">تحديد الكل</button><button id="clear-materials" class="rounded-lg border bg-white px-3 py-2 text-xs font-semibold">مسح</button></div>
    </div>
    <div class="mt-4 max-h-96 overflow-auto rounded-xl border bg-white" id="materials"></div>
  </div>

  <div class="mt-5 flex flex-wrap items-center gap-3">
    <button id="start-production" class="rounded-xl bg-indigo-600 px-5 py-3 text-sm font-bold text-white hover:bg-indigo-700 disabled:opacity-40">تشغيل إنتاج المنشورات</button>
    <span id="production-summary" class="text-sm text-slate-500"></span>
  </div>

  <div id="job-panel" class="mt-5 hidden rounded-2xl border border-indigo-100 bg-indigo-50 p-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div><p class="text-xs font-bold text-indigo-700">Production Job</p><p id="job-status" class="mt-1 font-bold"></p></div>
      <p id="job-counts" class="text-sm text-indigo-800"></p>
    </div>
    <div class="mt-3 h-2 overflow-hidden rounded-full bg-indigo-100"><div id="job-bar" class="h-full bg-indigo-600 transition-all" style="width:0%"></div></div>
    <p id="job-error" class="mt-3 text-sm text-rose-700"></p>
    <button id="retry-job" class="mt-3 hidden rounded-xl bg-amber-600 px-4 py-2 text-sm font-bold text-white">إعادة تشغيل العناصر الفاشلة</button>
  </div>
</section>

<section class="rounded-3xl border bg-white p-5 shadow-sm sm:p-7" aria-labelledby="bank-title">
  <div class="flex flex-wrap items-start justify-between gap-4">
    <div><p class="text-xs font-bold text-indigo-600">02 — Post Bank</p><h2 id="bank-title" class="mt-1 text-2xl font-bold">المخزون التحريري</h2><p class="mt-2 text-sm leading-7 text-slate-600">هنا كل المنشورات الناتجة. افتح أي Post لتحريره ومراجعته. المعتمد فقط ينتقل لاحقًا إلى الجدولة.</p></div>
    <div class="flex flex-wrap gap-2"><span id="selected-count" class="rounded-full bg-indigo-50 px-3 py-2 text-xs font-bold text-indigo-700">0 محدد</span><button id="bulk-approve" disabled class="rounded-lg bg-emerald-600 px-3 py-2 text-xs font-bold text-white disabled:cursor-not-allowed disabled:opacity-40">اعتماد المحدد</button><button id="select-approved" class="rounded-lg border px-3 py-2 text-xs font-semibold">تحديد كل القابلين للنشر</button><button id="clear-selected" class="rounded-lg border px-3 py-2 text-xs font-semibold">مسح التحديد</button></div>
  </div>
  <div class="mt-5 grid gap-3 md:grid-cols-4">
    <input id="search" type="search" placeholder="ابحث في العنوان أو المحتوى..." class="rounded-xl border bg-slate-50 p-3 text-sm md:col-span-2">
    <select id="post-source" class="rounded-xl border bg-slate-50 p-3 text-sm"><option value="">كل الكتب</option></select>
    <select id="status" class="rounded-xl border bg-slate-50 p-3 text-sm"><option value="">كل الحالات</option><option value="DRAFT">مسودة — تحتاج مراجعة</option><option value="APPROVED">معتمد — جاهز</option><option value="REJECTED">مرفوض — يحتاج تعديل</option></select>
    <select id="publication-state" class="rounded-xl border bg-slate-50 p-3 text-sm"><option value="UNPUBLISHED">غير منشور</option><option value="ELIGIBLE">قابل للنشر</option><option value="">كل حالات النشر</option><option value="PUBLISHED">منشور سابقًا</option><option value="SCHEDULED">موجود في خطة</option></select>
  </div>
  <div id="action-message" class="mt-4 hidden rounded-xl border p-3 text-sm" role="status" aria-live="polite"></div>
  <div class="mt-3 flex items-center justify-between text-xs text-slate-500"><span id="summary">جارٍ التحميل...</span><button id="refresh" class="rounded-lg border px-3 py-2 font-semibold">تحديث</button></div>
  <div id="posts" class="mt-5 grid gap-4 lg:grid-cols-2"></div>
  <div id="empty" class="mt-5 hidden rounded-2xl border border-dashed bg-slate-50 p-8 text-center"><p class="font-bold">لا توجد منشورات</p><p class="mt-1 text-sm text-slate-500">شغّل Production Job أعلاه أو غيّر التصفية.</p></div>
  <div class="mt-6 rounded-2xl border border-indigo-100 bg-indigo-50 p-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div><p class="text-xs font-bold text-indigo-700">الخطوة التالية</p><p class="mt-1 text-sm font-semibold text-slate-800">بعد اعتماد المنشورات، ابنِ خطة النشر والتوقيت من المساحة المخصصة للجدولة.</p></div>
      <button id="next-to-scheduling" disabled class="rounded-xl bg-indigo-600 px-5 py-3 text-sm font-bold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40">التالي: بناء خطة النشر →</button>
    </div>
    <p id="next-to-scheduling-help" class="mt-2 text-xs text-indigo-800">حدد منشورًا معتمدًا واحدًا على الأقل للمتابعة.</p>
  </div>
</section>

<section id="editor" class="fixed inset-0 z-50 hidden grid place-items-center bg-slate-900/60 p-4">
 <div class="w-full max-w-4xl max-h-[92vh] overflow-auto rounded-3xl bg-white p-5 shadow-2xl sm:p-7">
  <div class="flex items-start justify-between gap-4"><div><p class="text-xs font-bold text-indigo-600">03 — المراجعة البشرية</p><h2 id="editor-title" class="mt-1 text-2xl font-bold"></h2><p id="editor-meta" class="mt-2 text-xs text-slate-500"></p></div><button id="close-editor" class="rounded-xl border px-3 py-2">إغلاق</button></div>
  <div class="mt-5 grid gap-5 lg:grid-cols-2">
   <div><p class="mb-2 text-sm font-bold">النص التحريري</p><textarea id="content" dir="rtl" class="min-h-[360px] w-full rounded-2xl border p-4 leading-8"></textarea></div>
   <div><p class="mb-2 text-sm font-bold">المصدر / Provenance</p><div id="provenance" class="rounded-2xl bg-slate-50 p-4 text-sm leading-7"></div><div class="mt-4"><label class="text-sm font-bold">ملاحظة المراجعة</label><textarea id="note" dir="rtl" class="mt-2 min-h-28 w-full rounded-xl border p-3 leading-7" placeholder="سبب الرفض مطلوب عند الرفض."></textarea></div></div>
  </div>
  <p id="editor-error" class="mt-3 text-sm text-rose-600"></p>
  <div class="mt-5 flex flex-wrap justify-end gap-2"><button id="save" class="rounded-xl border px-4 py-2.5 font-bold">حفظ التعديل</button><button id="reject" class="rounded-xl bg-rose-600 px-5 py-2.5 font-bold text-white">رفض</button><button id="approve" class="rounded-xl bg-emerald-600 px-5 py-2.5 font-bold text-white">اعتماد</button></div>
 </div>
</section>
</main>
<script>
const $=id=>document.getElementById(id);
const state={source:null,topics:[],units:[],jobId:null,selectedMaterials:new Set(),selectedPosts:new Set(),postMeta:{},posts:[],timer:null};
async function api(url,opt={}){const r=await fetch(url,opt);const d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.detail||'تعذر تنفيذ العملية.');return d;}
function esc(v){return String(v??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function statusLabel(s){return({DRAFT:'DRAFT — يحتاج مراجعة',APPROVED:'APPROVED — جاهز للجدولة',REJECTED:'REJECTED — يحتاج تعديل'}[s]||s);}
function loadSourceOptions(list){$('source').innerHTML='<option value="">اختر كتابًا...</option>'+list.map(s=>'<option value="'+esc(s.id)+'">'+esc(s.book_title||s.filename)+'</option>').join('');$('post-source').innerHTML='<option value="">كل الكتب</option>'+list.map(s=>'<option value="'+esc(s.id)+'">'+esc(s.book_title||s.filename)+'</option>').join('');}
async function loadSources(){const list=await api('/sources');loadSourceOptions(list);if(list.length===1){$('source').value=list[0].id;await loadBook(list[0].id);}}
async function loadBook(id){if(!id){state.topics=[];state.units=[];$('topic').innerHTML='';$('materials').innerHTML='';return;}const d=await api('/sources/'+id+'/book-map');state.source=id;state.topics=d.topics||[];state.units=state.topics.flatMap(t=>t.materials||[]);$('topic').innerHTML=state.topics.map(t=>'<option value="'+esc(t.id)+'">'+esc(t.position+'. '+t.title)+'</option>').join('');renderMaterials();updateSelectionHelp();}
function renderMaterials(){const topicId=$('topic').value;const list=topicId?state.topics.find(t=>t.id===topicId)?.materials||[]:state.units; $('materials').innerHTML=list.map(m=>'<label class="flex gap-3 border-b p-3 last:border-b-0"><input type="checkbox" data-unit="'+esc(m.id)+'" class="mt-1 h-4 w-4" '+(state.selectedMaterials.has(m.id)?'checked':'')+'><span class="min-w-0"><strong class="text-sm">'+esc(m.title)+'</strong><span class="mr-2 text-xs text-slate-400">'+esc(m.kind||'مادة')+'</span><span class="mt-1 block line-clamp-2 text-xs leading-6 text-slate-500">'+esc(m.content)+'</span></span></label>').join('')||'<p class="p-5 text-sm text-slate-500">لا توجد مواد.</p>';document.querySelectorAll('[data-unit]').forEach(x=>x.onchange=()=>{x.checked?state.selectedMaterials.add(x.dataset.unit):state.selectedMaterials.delete(x.dataset.unit);updateSelectionHelp();});}
function updateSelectionHelp(){ $('selection-help').textContent=state.selectedMaterials.size+' مادة محددة'; $('production-summary').textContent=$('scope').value==='SELECTION'?(state.selectedMaterials.size+' مادة ستدخل الإنتاج'):($('scope').value==='TOPIC'?'سيتم إنتاج مواد المحور المحدد':'سيتم إنتاج مواد الكتاب كاملة');}
function renderScope(){const s=$('scope').value;$('topic-wrap').classList.toggle('hidden',s!=='TOPIC');$('selection-wrap').classList.toggle('hidden',s!=='SELECTION');updateSelectionHelp();}
async function startProduction(){try{if(!state.source)throw Error('اختر كتابًا أولًا.');const scope=$('scope').value;const body={source_id:state.source,scope};if(scope==='TOPIC'){if(!$('topic').value)throw Error('اختر محورًا.');body.topic_id=$('topic').value;}if(scope==='SELECTION'){if(!state.selectedMaterials.size)throw Error('اختر مادة واحدة على الأقل.');body.knowledge_unit_ids=[...state.selectedMaterials];} $('start-production').disabled=true;const d=await api('/production-jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});state.jobId=d.job_id;$('job-panel').classList.remove('hidden');pollJob();}catch(e){alert(e.message);}finally{$('start-production').disabled=false;}}
async function pollJob(){if(!state.jobId)return;try{const d=await api('/production-jobs/'+state.jobId);const total=d.total_items||0,done=d.completed_items||0,failed=d.failed_items||0,pending=d.pending_items||0;const pct=total?Math.round(done/total*100):0;$('job-status').textContent=d.status==='COMPLETED'?'اكتمل الإنتاج':d.status==='FAILED'?'فشل الإنتاج':d.status==='RUNNING'?'جاري إنتاج المنشورات':'في الانتظار';$('job-counts').textContent=done+' مكتمل · '+pending+' متبقٍ · '+failed+' فشل من '+total;$('job-bar').style.width=pct+'%';$('job-error').textContent=d.error_message||'';$('retry-job').classList.toggle('hidden',failed===0||d.status==='RUNNING');if(d.status==='COMPLETED'||d.status==='FAILED'){await loadPosts();return;}state.timer=setTimeout(pollJob,1500);}catch(e){$('job-error').textContent=e.message;}}
function postParams(){
  const p=new URLSearchParams();
  const source=$('post-source').value,status=$('status').value,q=$('search').value.trim(),publicationState=$('publication-state').value;
  if(source)p.set('source_id',source);
  if(status)p.set('status',status);
  if(publicationState)p.set('publication_state',publicationState);
  if(q)p.set('q',q);
  p.set('limit','50');p.set('offset','0');
  return p;
}
async function loadPosts(){
  const d=await api('/posts?'+postParams());
  state.posts=d.items||[];
  state.posts.forEach(p=>state.postMeta[p.post_id]=p);
  renderPosts(d);
}
function showActionMessage(message,kind='info'){
  const box=$('action-message');
  box.textContent=message;
  box.className='mt-4 rounded-xl border p-3 text-sm '+(kind==='error'?'border-rose-200 bg-rose-50 text-rose-700':kind==='success'?'border-emerald-200 bg-emerald-50 text-emerald-700':'border-indigo-200 bg-indigo-50 text-indigo-700');
  box.classList.remove('hidden');
}
function selectedNonApproved(){
  return [...state.selectedPosts].filter(id=>state.postMeta[id]?.status!=='APPROVED');
}
function renderPosts(d){
  $('summary').textContent=(d.total||0)+' Posts';
  $('empty').classList.toggle('hidden',state.posts.length>0);
  $('posts').innerHTML=state.posts.map(p=>{
    const approved=p.status==='APPROVED';
    const selectable=p.status!=='APPROVED'||p.eligible_for_scheduling;
    const stateText=p.published?'منشور سابقًا':p.scheduled?'موجود في خطة':p.eligible_for_scheduling?'قابل للنشر':'غير جاهز';
    return '<article class="card rounded-2xl border p-5 '+(state.selectedPosts.has(p.post_id)?'border-indigo-400 bg-indigo-50':'bg-white')+'"><div class="flex items-start justify-between gap-3"><label class="flex items-start gap-3"><input type="checkbox" data-post="'+esc(p.post_id)+'" '+(state.selectedPosts.has(p.post_id)?'checked':'')+' '+(selectable?'':'disabled')+' class="mt-1 h-4 w-4"><span><p class="text-xs text-slate-400">'+esc(p.source_title||'')+'</p><h3 class="mt-1 font-bold">'+esc(p.title)+'</h3><p class="mt-1 text-xs text-slate-500">'+esc(p.topic_title||'بدون محور')+'</p></span></label><span class="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold">'+esc(statusLabel(p.status))+'</span></div><p class="mt-3 whitespace-pre-wrap text-sm leading-8 text-slate-700">'+esc(p.content)+'</p><div class="mt-4 flex flex-wrap items-center justify-between gap-3"><span class="rounded-full bg-slate-100 px-2 py-1 text-xs">'+esc(stateText)+'</span><button data-edit="'+esc(p.post_id)+'" class="rounded-xl border px-4 py-2 text-sm font-bold">تحرير / تفاصيل</button></div></article>';
  }).join('');
  document.querySelectorAll('[data-post]').forEach(x=>x.onchange=()=>{x.checked?state.selectedPosts.add(x.dataset.post):state.selectedPosts.delete(x.dataset.post);renderPosts(d);});
  document.querySelectorAll('[data-edit]').forEach(x=>x.onclick=()=>openEditor(x.dataset.edit));
  updateSelected();
}
function updateSelected(){
  $('selected-count').textContent=state.selectedPosts.size+' محدد';
  $('bulk-approve').disabled=selectedNonApproved().length===0;
  $('next-to-scheduling').disabled=state.selectedPosts.size===0;
  $('next-to-scheduling-help').textContent=state.selectedPosts.size?('تم تحديد '+state.selectedPosts.size+' منشورًا. سيتم التحقق من قابلية النشر قبل الجدولة.'):'حدد منشورًا واحدًا على الأقل للمتابعة.';
}
async function bulkApproveSelected(){
  const ids=selectedNonApproved();
  if(!ids.length)return showActionMessage('كل المنشورات المحددة معتمدة بالفعل.','info');
  $('bulk-approve').disabled=true;
  try{
    const result=await api('/posts/bulk-approve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({post_ids:ids})});
    (result.results||[]).forEach(row=>{
      state.postMeta[row.post_id]=state.postMeta[row.post_id]||{post_id:row.post_id};
      if(row.status==='APPROVED')state.postMeta[row.post_id].status='APPROVED';
    });
    if(result.failed_count){
      showActionMessage('تم اعتماد '+result.approved_count+' منشورًا، وتعذر اعتماد '+result.failed_count+'؛ '+(result.results||[]).filter(x=>x.status==='FAILED').map(x=>x.message).join('؛ '),result.approved_count?'success':'error');
    }else{
      showActionMessage('تم اعتماد '+result.approved_count+' منشورًا بنجاح. المجموعة ما زالت محددة ويمكنك الانتقال إلى الجدولة.','success');
    }
    await loadPosts();
    state.selectedPosts=new Set([...state.selectedPosts].filter(id=>state.postMeta[id]?.status==='APPROVED'));
    updateSelected();
  }catch(e){showActionMessage(e.message,'error');}
  finally{updateSelected();}
}
async function prepareScheduling(){
  const ids=[...state.selectedPosts];
  if(!ids.length)return;
  const params=new URLSearchParams();
  ids.forEach(id=>params.append('post_ids',id));
  const result=await api('/schedules/eligibility?'+params.toString());
  const blocked=result.blocked||[];
  const blockedIds=new Set(blocked.map(x=>x.post_id));
  const eligible=ids.filter(id=>!blockedIds.has(id));
  state.selectedPosts=new Set(eligible);
  if(blocked.length)showActionMessage('تم استبعاد '+blocked.length+' منشورًا من الجدولة: '+blocked.map(x=>x.message).join('؛ '),'info');
  updateSelected();
  if(!eligible.length)return;
  window.location.href='/console?selected_post_ids='+encodeURIComponent(eligible.join(','))+'#scheduling-section';
}

async function openEditor(id){const p=await api('/posts/'+id);$('editor').dataset.id=id;$('editor-title').textContent=p.title;$('editor-meta').textContent=statusLabel(p.status)+' · '+(p.source_title||'')+' · '+(p.topic_title||'');$('content').value=p.content||'';$('note').value=p.review_note||'';$('provenance').innerHTML='<strong>المصدر:</strong> '+esc(p.source_title||'غير محدد')+'<br><strong>المحور:</strong> '+esc(p.topic_title||'بدون محور')+'<br><strong>المادة:</strong> '+esc(p.title||'غير محدد')+'<br><strong>المرجع:</strong> '+esc(p.source_reference||'غير محدد')+((p.discovery_page_start||p.discovery_page_end)?'<br><strong>الصفحات:</strong> '+esc((p.discovery_page_start||'?')+'–'+(p.discovery_page_end||'?')):'');$('editor-error').textContent='';$('editor').classList.remove('hidden');}
async function savePost(){const id=$('editor').dataset.id,content=$('content').value.trim();if(!content)return $('editor-error').textContent='المحتوى لا يمكن أن يكون فارغًا.';try{const p=await api('/posts/'+id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({content})});if(p.status!=='APPROVED')state.selectedPosts.delete(id);$('editor').classList.add('hidden');await loadPosts();}catch(e){$('editor-error').textContent=e.message;}}
async function review(action){const id=$('editor').dataset.id,note=$('note').value.trim();if(action==='reject'&&!note)return $('editor-error').textContent='سبب الرفض مطلوب.';try{const p=await api('/posts/'+id+'/'+(action==='approve'?'approve':'reject'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(action==='approve'?{note}:{reason:note})});if(p.status!=='APPROVED')state.selectedPosts.delete(id);await loadPosts();$('editor').classList.add('hidden');}catch(e){$('editor-error').textContent=e.message;}}
$('scope').onchange=renderScope;$('source').onchange=async()=>{state.selectedMaterials.clear();await loadBook($('source').value);renderScope();};$('topic').onchange=renderMaterials;$('start-production').onclick=startProduction;$('select-all-materials').onclick=()=>{const list=$('topic').value?state.topics.find(t=>t.id===$('topic').value)?.materials||[]:state.units;list.forEach(m=>state.selectedMaterials.add(m.id));renderMaterials();updateSelectionHelp();};$('clear-materials').onclick=()=>{state.selectedMaterials.clear();renderMaterials();updateSelectionHelp();};$('retry-job').onclick=async()=>{if(!state.jobId)return;try{const d=await api('/production-jobs/'+state.jobId+'/resume',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({retry_failed:true})});state.jobId=d.job_id;pollJob();}catch(e){alert(e.message);}};$('search').oninput=()=>{clearTimeout(state.searchTimer);state.searchTimer=setTimeout(loadPosts,250);};$('post-source').onchange=loadPosts;$('status').onchange=loadPosts;$('publication-state').onchange=loadPosts;$('refresh').onclick=loadPosts;$('select-approved').onclick=async()=>{try{const base=new URLSearchParams();const s=$('post-source').value,q=$('search').value.trim();if(s)base.set('source_id',s);if(q)base.set('q',q);base.set('status','APPROVED');base.set('publication_state','ELIGIBLE');base.set('limit','500');let offset=0;const ids=[];while(true){base.set('offset',String(offset));const d=await api('/posts?'+base);ids.push(...(d.items||[]).map(x=>x.post_id));offset+=(d.items||[]).length;if(offset>=Number(d.total||0)||(d.items||[]).length===0)break;}state.selectedPosts=new Set(ids);await loadPosts();}catch(e){alert(e.message);}};$('clear-selected').onclick=()=>{state.selectedPosts.clear();loadPosts();};$('bulk-approve').onclick=bulkApproveSelected;$('next-to-scheduling').onclick=()=>prepareScheduling();$('close-editor').onclick=()=>$('editor').classList.add('hidden');$('save').onclick=savePost;$('approve').onclick=()=>review('approve');$('reject').onclick=()=>review('reject');
(async()=>{try{await loadSources();await loadPosts();renderScope();}catch(e){alert('تعذر تحميل مساحة المنشورات: '+e.message);}})();
</script>
</body></html>'''
