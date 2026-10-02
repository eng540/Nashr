"""Dedicated publishing workspace; reuses the existing scheduling domain/API."""

NASHR_PUBLISHING_HTML = r'''<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Nashr — النشر</title><script src="https://cdn.tailwindcss.com"></script><style>body{font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}</style></head>
<body class="min-h-screen bg-slate-50 text-slate-900"><main class="mx-auto max-w-6xl px-4 py-8 sm:py-12">
<header class="mb-8 flex flex-wrap items-start justify-between gap-4 border-b pb-6"><div><p class="text-sm font-semibold text-indigo-600">Nashr — النشر</p><h1 class="mt-1 text-3xl font-bold">مساحة النشر</h1><p class="mt-2 max-w-3xl text-sm leading-7 text-slate-600">خطة النشر، المراجعة النهائية، الجدولة والتنفيذ الآلي. لا يوجد هنا رفع كتب أو تحليل أو إنتاج منشورات.</p></div><nav class="flex flex-wrap gap-2 text-sm"><a href="/console" class="rounded-full bg-white px-4 py-2 font-semibold text-slate-600 shadow-sm">📚 المكتبة</a><a href="/posts/workspace" class="rounded-full bg-white px-4 py-2 font-semibold text-slate-600 shadow-sm">✍️ مصنع المحتوى</a><span class="rounded-full bg-indigo-50 px-4 py-2 font-semibold text-indigo-700">📅 النشر</span></nav></header>
<div class="mb-6 grid gap-3 sm:grid-cols-3"><a href="/console" class="rounded-2xl border bg-white p-4"><p class="text-xs font-bold">01</p><p class="mt-1 font-bold">المكتبة</p><p class="mt-1 text-xs text-slate-500">الكتب والخريطة والمواد</p></a><a href="/posts/workspace" class="rounded-2xl border bg-white p-4"><p class="text-xs font-bold">02</p><p class="mt-1 font-bold">مصنع المحتوى</p><p class="mt-1 text-xs text-slate-500">إنتاج ومراجعة واعتماد</p></a><div class="rounded-2xl border-2 border-indigo-200 bg-indigo-50 p-4"><p class="text-xs font-bold text-indigo-600">03</p><p class="mt-1 font-bold">النشر</p><p class="mt-1 text-xs text-slate-600">خطة وجدولة وتنفيذ وسجل</p></div></div>
<section id="scheduling-section" class="mb-8 rounded-3xl border bg-white p-5 shadow-sm sm:p-7">
  <div class="flex flex-wrap items-start justify-between gap-4">
    <div><p class="text-xs font-bold text-indigo-600">07 — خطة النشر</p><h2 id="scheduling-heading" class="mt-1 text-2xl font-bold">بناء خطة النشر</h2><p class="mt-2 max-w-3xl text-sm leading-7 text-slate-600">راجع الاختيار، رتّب المنشورات وحدد البداية والفاصل، ثم راجع الخطة كاملة قبل تفعيل النشر الآلي.</p></div>
    <button id="schedule-from-selection" class="rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-40">إنشاء خطة من المحدد</button>
  </div>
  <div class="mt-5 grid gap-2 sm:grid-cols-5" aria-label="مراحل النشر">
    <div class="rounded-xl bg-slate-50 p-3 text-xs"><b>✓ الاختيار</b><span class="mt-1 block text-slate-500">منشورات معتمدة</span></div>
    <div class="rounded-xl bg-indigo-50 p-3 text-xs text-indigo-800"><b>→ خطة النشر</b><span class="mt-1 block">أنت هنا</span></div>
    <div class="rounded-xl bg-slate-50 p-3 text-xs"><b>المراجعة النهائية</b><span class="mt-1 block text-slate-500">فحص الجاهزية</span></div>
    <div class="rounded-xl bg-slate-50 p-3 text-xs"><b>النشر الآلي</b><span class="mt-1 block text-slate-500">تفعيل التنفيذ</span></div>
    <div class="rounded-xl bg-slate-50 p-3 text-xs"><b>السجل</b><span class="mt-1 block text-slate-500">Publication Ledger</span></div>
  </div>
  <div id="schedule-create-panel" class="mt-5 hidden rounded-2xl border bg-slate-50 p-4">
    <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      <input id="schedule-name" class="rounded-xl border bg-white p-3 text-sm" placeholder="اسم الخطة">
      <input id="schedule-timezone" class="rounded-xl border bg-white p-3 text-sm" value="Asia/Aden">
      <input id="schedule-start-at" type="datetime-local" class="rounded-xl border bg-white p-3 text-sm">
      <input id="schedule-interval" type="number" min="1" max="10080" value="30" class="rounded-xl border bg-white p-3 text-sm" placeholder="الفاصل بالدقائق">
    </div>
    <p class="mt-2 text-xs leading-6 text-slate-500">اختر وقت البداية والفاصل بالدقائق. سيولد Nashr المواعيد بالتسلسل حسب ترتيب العناصر. يمكنك تغيير ترتيب العناصر قبل الحفظ.</p>
    <div id="schedule-selection-rows" class="mt-4 space-y-2"></div>
    <div class="mt-4 flex justify-end gap-2"><button id="schedule-cancel-create" class="rounded-xl border px-4 py-2 text-sm">إلغاء</button><button id="schedule-save-create" class="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-bold text-white">حفظ الخطة</button></div>
    <p id="schedule-create-error" class="mt-2 text-sm text-red-600"></p>
  </div>
  <div class="mt-6 flex items-center justify-between"><h3 class="font-bold">الخطط المحفوظة</h3><button id="schedule-refresh" class="rounded-lg border px-3 py-2 text-xs font-semibold">تحديث</button></div>
  <div id="schedule-list" class="mt-4 space-y-3"></div>
  <div id="schedule-detail" class="mt-5 hidden rounded-2xl border bg-slate-50 p-4"></div>
  <section id="activation-confirm" class="fixed inset-0 z-50 hidden grid place-items-center bg-slate-900/60 p-4">
    <div class="w-full max-w-xl rounded-3xl bg-white p-6 shadow-2xl">
      <p class="text-xs font-bold text-indigo-600">المراجعة النهائية</p><h2 class="mt-1 text-2xl font-bold">تفعيل النشر الآلي؟</h2>
      <div id="activation-confirm-summary" class="mt-4 rounded-2xl bg-slate-50 p-4 text-sm leading-7"></div>
      <p class="mt-3 text-xs leading-6 text-slate-500">بعد التفعيل سيبدأ Nashr بتنفيذ العناصر المستحقة تلقائيًا عبر نظام النشر الحالي.</p>
      <div class="mt-5 flex flex-wrap justify-end gap-2"><button id="activation-confirm-cancel" class="rounded-xl border px-4 py-2.5 font-bold">العودة للمراجعة</button><button id="activation-confirm-ok" class="rounded-xl bg-emerald-600 px-5 py-2.5 font-bold text-white">نعم، فعّل النشر الآلي</button></div>
      <p id="activation-confirm-error" class="mt-3 text-sm text-rose-600"></p>
    </div>
  </section>
  <div class="mt-6"><div class="flex flex-wrap items-center justify-between gap-3"><h3 class="font-bold">التقويم اليومي</h3><div class="flex items-center gap-2"><input id="calendar-date" type="date" class="rounded-lg border bg-white px-3 py-2 text-xs"><button id="calendar-refresh" class="rounded-lg border px-3 py-2 text-xs font-semibold">عرض اليوم</button></div></div><div id="calendar-list" class="mt-3 space-y-2"></div></div>
  <div class="mt-6"><h3 class="font-bold">القادم</h3><div id="upcoming-list" class="mt-3 space-y-2"></div></div>
</section>

<section id="telegram-preview" class="fixed inset-0 z-50 hidden grid place-items-center bg-slate-900/60 p-4"><div class="w-full max-w-3xl rounded-3xl bg-white p-5 shadow-2xl"><div class="flex items-center justify-between"><div><p class="text-xs font-bold text-indigo-600">Telegram Preview</p><h2 class="text-xl font-bold">المعاينة النهائية</h2></div><button id="telegram-preview-close" class="rounded-xl border px-3 py-2">إغلاق</button></div><p id="telegram-preview-meta" class="mt-3 text-xs text-slate-500"></p><pre id="telegram-preview-content" dir="rtl" class="mt-4 max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-2xl border bg-slate-50 p-5 text-sm leading-8"></pre></div></section>
</main><script>
const $=id=>document.getElementById(id);const state={selectedPostIds:[],selectedPostMeta:{},scheduleIdempotencyKey:null,activeScheduleId:null,pendingActivationId:null};
async function request(url,opt={}){const r=await fetch(url,opt);const d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.detail||'تعذر تنفيذ العملية.');return d;}
function esc(t){return(t??'').toString().replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function showPostBankMessage(message,kind='info'){const box=document.getElementById('schedule-create-error');if(box)box.textContent=message;}
function renderSelectionCount(){const button=$('schedule-from-selection');if(button)button.disabled=state.selectedPostIds.length===0;}
async function renderScheduleSelection(){
  const ids=[...new Set(window.nashrPostSelection?window.nashrPostSelection():state.selectedPostIds)];
  state.selectedPostIds=ids;
  const rows=$('schedule-selection-rows');
  const renderRows=()=>{rows.innerHTML=ids.map((id,i)=>'<div data-schedule-row="'+esc(id)+'" class="flex items-center gap-3 rounded-xl border bg-white p-3"><span class="w-7 text-xs font-bold text-slate-400">'+(i+1)+'</span><span class="min-w-0 flex-1"><b class="block truncate">'+esc(state.selectedPostMeta[id]?.title||'جاري تحميل عنوان المنشور…')+'</b><span class="block truncate text-[11px] text-slate-400">'+esc(state.selectedPostMeta[id]?.source_title||id)+'</span></span><button type="button" data-move-up="'+esc(id)+'" class="rounded-lg border px-2 py-1 text-xs">↑</button><button type="button" data-move-down="'+esc(id)+'" class="rounded-lg border px-2 py-1 text-xs">↓</button><span data-schedule-time="'+esc(id)+'" class="w-40 text-xs text-slate-500"></span></div>').join('');document.querySelectorAll('[data-move-up]').forEach(b=>b.onclick=()=>moveSelectedPost(b.dataset.moveUp,-1));document.querySelectorAll('[data-move-down]').forEach(b=>b.onclick=()=>moveSelectedPost(b.dataset.moveDown,1));updateGeneratedScheduleTimes();};
  renderRows();
  const missing=ids.filter(id=>!state.selectedPostMeta[id]);
  if(missing.length){await Promise.all(missing.map(async id=>{try{state.selectedPostMeta[id]=await request('/posts/'+id);}catch(e){state.selectedPostMeta[id]={title:'منشور '+id.slice(0,8),source_title:'تعذر تحميل التفاصيل'};}}));renderRows();}
}
function moveSelectedPost(id,direction){
  const index=state.selectedPostIds.indexOf(id);
  const target=index+direction;
  if(index<0||target<0||target>=state.selectedPostIds.length)return;
  const next=[...state.selectedPostIds];[next[index],next[target]]=[next[target],next[index]];
  state.selectedPostIds=next;renderSelectionCount();renderScheduleSelection();
}
function updateGeneratedScheduleTimes(){
  const start=$('schedule-start-at').value,interval=Number($('schedule-interval').value||0),timezone=$('schedule-timezone').value.trim();
  document.querySelectorAll('[data-schedule-time]').forEach((el,index)=>{
    if(!start||!interval||!timezone){el.textContent='';return;}
    try{
      const base=new Date(localDateTimeToUtcISOString(start,timezone));
      const when=new Date(base.getTime()+index*interval*60000);
      el.textContent=when.toLocaleString('ar',{timeZone:timezone,dateStyle:'short',timeStyle:'short'});
    }catch(e){el.textContent='وقت غير صالح';}
  });
}
function localDateTimeToUtcISOString(value,timeZone){if(!value)return null;const match=/^(\\d{4})-(\\d{2})-(\\d{2})T(\\d{2}):(\\d{2})$/.exec(value);if(!match)throw new Error('موعد غير صالح.');const [,y,m,d,h,min]=match;const wall=Date.UTC(Number(y),Number(m)-1,Number(d),Number(h),Number(min),0);const formatter=new Intl.DateTimeFormat('en-US',{calendar:'gregory',numberingSystem:'latn',timeZone,hourCycle:'h23',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'});const parts=Object.fromEntries(formatter.formatToParts(new Date(wall)).filter(p=>p.type!=='literal').map(p=>[p.type,p.value]));const zoneWall=Date.UTC(Number(parts.year),Number(parts.month)-1,Number(parts.day),Number(parts.hour),Number(parts.minute),Number(parts.second));const candidate=new Date(wall-(zoneWall-wall));const check=Object.fromEntries(formatter.formatToParts(candidate).filter(p=>p.type!=='literal').map(p=>[p.type,p.value]));if(check.year!==y||check.month!==m||check.day!==d||check.hour!==h||check.minute!==min)throw new Error('الوقت المحدد غير صالح في المنطقة الزمنية '+timeZone+'.');return candidate.toISOString();}
async function loadSchedules(){try{const d=await request('/schedules?limit=50&offset=0');$('schedule-list').innerHTML=d.items.length?d.items.map(s=>'<button data-schedule-id="'+esc(s.id)+'" class="block w-full rounded-2xl border bg-white p-4 text-right hover:border-indigo-400"><div class="flex items-center justify-between gap-3"><strong>'+esc(s.name)+'</strong><span class="rounded-full bg-slate-100 px-2 py-1 text-xs">'+esc(s.status)+'</span></div><p class="mt-2 text-xs text-slate-500">'+s.total_items+' عناصر · '+s.published_items+' منشورة · '+s.failed_items+' فاشلة · '+(s.skipped_items||0)+' متجاوزة · التالي: '+esc(s.next_scheduled_at||'لا يوجد')+'</p></button>').join(''):'<p class="rounded-xl border border-dashed p-6 text-center text-sm text-slate-500">لا توجد خطط بعد.</p>';document.querySelectorAll('[data-schedule-id]').forEach(b=>b.onclick=()=>openSchedule(b.dataset.scheduleId));}catch(e){$('schedule-list').textContent=e.message;}}
async function showTelegramPreview(id){
  try{
    const p=await request('/posts/'+id+'/telegram-preview');
    $('telegram-preview-meta').textContent='Telegram · '+(p.destination||'لم يحدد الوجهة')+' · '+(p.status==='APPROVED'?'معتمد':'غير معتمد');
    $('telegram-preview-content').textContent=p.content||'';
    $('telegram-preview').classList.remove('hidden');
  }catch(e){alert(e.message);}
}
async function loadCalendar(){
  try{
    const date=$('calendar-date').value || new Date().toISOString().slice(0,10);
    $('calendar-date').value=date;
    const d=await request('/schedules/calendar?date='+encodeURIComponent(date)+'&timezone='+encodeURIComponent($('schedule-timezone').value||'Asia/Aden'));
    $('calendar-list').innerHTML=d.items.length?d.items.map(i=>'<button data-calendar-preview="'+esc(i.post_id)+'" class="w-full rounded-xl border bg-white p-3 text-right hover:border-indigo-400"><div class="flex flex-wrap items-center justify-between gap-3"><strong>'+esc(i.title)+'</strong><span class="text-xs text-slate-500">'+new Date(i.scheduled_at).toLocaleTimeString('ar',{hour:'2-digit',minute:'2-digit',timeZone:d.timezone})+'</span></div><p class="mt-1 text-xs text-slate-400">'+esc(i.schedule_name)+' · '+esc(i.status)+' · الموضع '+i.position+(i.last_error?' · '+esc(i.last_error):'')+'</p></button>').join(''):'<p class="rounded-xl border border-dashed p-4 text-center text-sm text-slate-500">لا توجد عناصر لهذا اليوم.</p>';
    document.querySelectorAll('[data-calendar-preview]').forEach(b=>b.onclick=()=>showTelegramPreview(b.dataset.calendarPreview));
  }catch(e){$('calendar-list').textContent=e.message;}
}
async function loadUpcoming(){
  try{
    const d=await request('/schedules/upcoming?days=7&limit=100');
    const box=$('upcoming-list');
    box.innerHTML=d.items.length?d.items.map(i=>'<button data-upcoming-preview="'+esc(i.post_id)+'" class="w-full rounded-xl border bg-white p-3 text-right hover:border-indigo-400"><div class="flex flex-wrap items-center justify-between gap-3"><strong>'+esc(i.title)+'</strong><span class="text-xs text-slate-500">'+new Date(i.scheduled_at).toLocaleString('ar',{timeZone:i.timezone})+'</span></div><p class="mt-1 text-xs text-slate-400">'+esc(i.schedule_name)+' · '+esc(i.status)+'</p></button>').join(''):'<p class="rounded-xl border border-dashed p-4 text-center text-sm text-slate-500">لا توجد منشورات قادمة في الخطط النشطة.</p>';
    document.querySelectorAll('[data-upcoming-preview]').forEach(b=>b.onclick=()=>showTelegramPreview(b.dataset.upcomingPreview));
  }catch(e){$('upcoming-list').textContent=e.message;}
}
function scheduleStatusLabel(status){return({DRAFT:'مسودة',PAUSED:'متوقفة مؤقتًا',ACTIVE:'نشطة',COMPLETED:'مكتملة',CANCELLED:'ملغاة'}[status]||status);}
function itemStatusLabel(status){return({PENDING:'بانتظار التنفيذ',PROCESSING:'قيد التنفيذ',PUBLISHED:'منشور',FAILED:'فشل',SKIPPED:'تم تجاوزه',CANCELLED:'ملغى'}[status]||status);}
function toLocalDateTimeValue(iso,timeZone){const d=new Date(iso);const f=new Intl.DateTimeFormat('en-US',{calendar:'gregory',numberingSystem:'latn',timeZone,hourCycle:'h23',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});const p=Object.fromEntries(f.formatToParts(d).filter(x=>x.type!=='literal').map(x=>[x.type,x.value]));return p.year+'-'+p.month+'-'+p.day+'T'+p.hour+':'+p.minute;}
function scheduleSummary(s){const first=s.items?.[0],last=s.items?.[s.items.length-1],next=s.next_scheduled_at;return '<div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><div class="rounded-xl bg-white p-3"><p class="text-xs text-slate-500">المنشورات</p><b class="text-lg">'+s.total_items+'</b></div><div class="rounded-xl bg-white p-3"><p class="text-xs text-slate-500">الحالة</p><b class="text-lg">'+esc(scheduleStatusLabel(s.status))+'</b></div><div class="rounded-xl bg-white p-3"><p class="text-xs text-slate-500">أول نشر</p><b class="text-sm">'+(first?esc(new Date(first.scheduled_at).toLocaleString('ar',{timeZone:s.timezone})):'—')+'</b></div><div class="rounded-xl bg-white p-3"><p class="text-xs text-slate-500">آخر نشر</p><b class="text-sm">'+(last?esc(new Date(last.scheduled_at).toLocaleString('ar',{timeZone:s.timezone})):'—')+'</b></div></div><div class="mt-3 rounded-xl border bg-white p-3 text-sm"><b>حالة التنفيذ:</b> '+s.published_items+' منشورة · '+s.pending_items+' متبقية · '+s.failed_items+' فاشلة · '+(s.skipped_items||0)+' متجاوزة'+(next?' · النشر التالي '+esc(new Date(next).toLocaleString('ar',{timeZone:s.timezone})):'');}
async function loadScheduleValidation(id){try{return await request('/schedules/'+id+'/validation');}catch(e){return {valid:false,errors:[e.message],warnings:[]};}}
function renderValidation(v){return '<div class="mt-4 rounded-2xl border '+(v.valid?'border-emerald-200 bg-emerald-50':'border-rose-200 bg-rose-50')+' p-4"><div class="flex items-center justify-between gap-3"><b>'+ (v.valid?'✓ الخطة جاهزة للتفعيل':'⚠ توجد مشاكل تمنع التفعيل')+'</b><span class="text-xs">'+(v.pending_items||0)+' بانتظار · '+(v.published_items||0)+' منشورة · '+(v.failed_items||0)+' فاشلة</span></div>'+(v.errors?.length?'<ul class="mt-3 list-disc space-y-1 pr-5 text-sm text-rose-700">'+v.errors.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>':'')+(v.warnings?.length?'<ul class="mt-3 list-disc space-y-1 pr-5 text-sm text-amber-700">'+v.warnings.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>':'')+(v.blocked_items?.length?'<div class="mt-3 rounded-xl border border-amber-200 bg-white p-3 text-sm"><b>عناصر لن توقف بقية الخطة:</b><ul class="mt-2 list-disc space-y-1 pr-5">'+v.blocked_items.map(x=>'<li>الموضع '+x.position+' — '+esc(x.message)+'</li>').join('')+'</ul></div>':'')+'</div>';}
async function openSchedule(id){try{const s=await request('/schedules/'+id);state.activeScheduleId=id;$('schedule-detail').classList.remove('hidden');const actions=(s.status==='DRAFT'||s.status==='PAUSED'?'<button data-schedule-action="activate" class="rounded-xl bg-emerald-600 px-4 py-2.5 text-xs font-bold text-white">تفعيل النشر الآلي</button>':'')+(s.status==='ACTIVE'?'<button data-schedule-action="pause" class="rounded-xl border px-4 py-2.5 text-xs font-bold">إيقاف مؤقت</button>':'')+(s.status==='DRAFT'||s.status==='ACTIVE'||s.status==='PAUSED'?'<button data-schedule-action="cancel" class="rounded-xl border px-4 py-2.5 text-xs font-bold">إلغاء الخطة</button>':'');const validation=await loadScheduleValidation(id);$('schedule-detail').innerHTML='<div class="flex flex-wrap items-start justify-between gap-3"><div><p class="text-xs font-bold text-indigo-600">مراجعة الخطة</p><h3 class="mt-1 text-xl font-bold">'+esc(s.name)+'</h3><p class="mt-1 text-xs text-slate-500">'+esc(s.timezone)+' · '+esc(scheduleStatusLabel(s.status))+'</p></div><div class="flex flex-wrap gap-2">'+actions+'</div></div><div class="mt-4">'+scheduleSummary(s)+'</div>'+renderValidation(validation)+'<div class="mt-5 space-y-2"><h4 class="font-bold">المنشورات داخل الخطة</h4>'+s.items.map(i=>'<div class="rounded-xl border bg-white p-3"><div class="flex flex-wrap items-center gap-3"><b class="w-7">'+i.position+'</b><span class="min-w-0 flex-1 font-semibold">'+esc(i.title)+'</span><span class="rounded-full bg-slate-100 px-2 py-1 text-xs">'+esc(itemStatusLabel(i.status))+'</span><button data-item-preview="'+esc(i.post_id)+'" class="rounded-lg border px-2 py-1 text-xs">معاينة</button>'+(i.status==='FAILED'?'<button data-item-retry="'+esc(i.id)+'" class="rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-bold text-white">إعادة المحاولة</button>':'')+'</div><p class="mt-1 text-xs text-slate-400">'+esc(i.source_title)+' ← '+esc(i.topic_title||'بدون محور')+' · محاولات '+i.attempts+(i.last_error?' · '+esc(i.last_error):'')+'</p>'+(i.status==='PENDING'?'<div class="mt-3 flex flex-wrap items-center gap-2"><input data-item-time="'+esc(i.id)+'" type="datetime-local" value="'+esc(toLocalDateTimeValue(i.scheduled_at,s.timezone))+'" class="rounded-lg border bg-slate-50 p-2 text-xs"><button data-save-item-time="'+esc(i.id)+'" class="rounded-lg border px-3 py-2 text-xs font-semibold">حفظ الوقت</button></div>':'')+'</div>').join('')+'</div>';window.location.hash='scheduling-section';document.querySelectorAll('[data-item-preview]').forEach(b=>b.onclick=()=>showTelegramPreview(b.dataset.itemPreview));document.querySelectorAll('[data-item-retry]').forEach(b=>b.onclick=()=>retryScheduleItem(id,b.dataset.itemRetry));document.querySelectorAll('[data-save-item-time]').forEach(b=>b.onclick=()=>saveScheduleItemTime(id,b.dataset.saveItemTime,s.timezone));document.querySelectorAll('[data-schedule-action]').forEach(b=>b.onclick=()=>scheduleAction(id,b.dataset.scheduleAction));}catch(e){$('schedule-detail').textContent=e.message;}}
async function retryScheduleItem(scheduleId,itemId){try{await request('/schedules/'+scheduleId+'/items/'+itemId+'/retry',{method:'POST'});await loadSchedules();await loadUpcoming();await openSchedule(scheduleId);}catch(e){alert(e.message);}}
async function saveScheduleItemTime(scheduleId,itemId,timeZone){const input=document.querySelector('[data-item-time="'+itemId+'"]');try{if(!input?.value)throw Error('حدد وقتًا صالحًا.');const scheduledAt=localDateTimeToUtcISOString(input.value,timeZone);await request('/schedules/'+scheduleId+'/items/'+itemId,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({scheduled_at:scheduledAt})});await openSchedule(scheduleId);}catch(e){alert(e.message);}}
async function scheduleAction(id,action){if(action==='activate'){const validation=await loadScheduleValidation(id);if(!validation.valid){await openSchedule(id);return;}const s=await request('/schedules/'+id);$('activation-confirm-summary').innerHTML='<b>'+esc(s.name)+'</b><br>'+s.total_items+' منشورًا<br>المنطقة الزمنية: '+esc(s.timezone)+'<br>أول نشر: '+esc(new Date(s.items[0].scheduled_at).toLocaleString('ar',{timeZone:s.timezone}))+'<br>آخر نشر: '+esc(new Date(s.items[s.items.length-1].scheduled_at).toLocaleString('ar',{timeZone:s.timezone}))+(validation.warnings?.length?'<br><span class="text-amber-700">تنبيه: '+esc(validation.warnings.join('؛ '))+'</span>':'');state.pendingActivationId=id;$('activation-confirm-error').textContent='';$('activation-confirm').classList.remove('hidden');return;}const path=action==='retry-failed'?'/retry-failed':'/'+action;try{if(action==='cancel'&&!confirm('هل تريد إلغاء خطة النشر؟'))return;await request('/schedules/'+id+path,{method:'POST'});await loadSchedules();await loadUpcoming();await openSchedule(id);}catch(e){alert(e.message);}}

function selectedPost(id){return state.selectedPostIds.includes(id)}
function togglePostSelection(id){if(selectedPost(id))state.selectedPostIds=state.selectedPostIds.filter(x=>x!==id);else state.selectedPostIds.push(id);renderSelectionCount();}
function renderSelectionCount(){
  $('post-selection-count').textContent=state.selectedPostIds.length+' محدد';
  const selectedNonApproved=state.selectedPostIds.filter(id=>{
    const item=state.selectedPostMeta?.[id];
    return item ? item.status!=='APPROVED' : true;
  }).length;
  $('post-bulk-approve').disabled=selectedNonApproved===0;
  $('schedule-from-selection').disabled=state.selectedPostIds.length===0;
  window.nashrPostSelection=()=>[...state.selectedPostIds];
}
function statusLabel(status){return({DRAFT:'مسودة — تحتاج مراجعة',APPROVED:'معتمد — جاهز للجدولة',REJECTED:'مرفوض — يحتاج تعديل'}[status]||status);}
function publicationStateLabel(state){return({PUBLISHED:'منشور سابقًا',SCHEDULED:'موجود في خطة',ELIGIBLE:'قابل للنشر',NOT_READY:'غير جاهز'}[state]||state);}
function showPostBankMessage(message,kind='info'){
  const box=$('post-bank-action-message');
  box.textContent=message;
  box.className='mt-4 rounded-xl border p-3 text-sm '+(kind==='error'?'border-rose-200 bg-rose-50 text-rose-700':kind==='success'?'border-emerald-200 bg-emerald-50 text-emerald-700':'border-indigo-200 bg-indigo-50 text-indigo-700');
  box.classList.remove('hidden');
}
function renderPostBank(d){
  state.postTotal=d.total;
  state.postItems=d.items||[];
  state.postItems.forEach(p=>{state.selectedPostMeta[p.post_id]=p;});
  const grid=$('post-bank-grid');
  grid.innerHTML=(d.items||[]).map(p=>{
    const selectable=p.status!=='APPROVED' || p.eligible_for_scheduling;
    const selected=selectedPost(p.post_id);
    const stateText=p.published?'منشور سابقًا':p.scheduled?'موجود في خطة':p.eligible_for_scheduling?'قابل للنشر':'غير جاهز';
    return '<article class="rounded-2xl border p-4 '+(selected?'border-indigo-400 bg-indigo-50':'bg-white')+'"><div class="flex items-start justify-between gap-3"><label class="flex items-start gap-3"><input type="checkbox" '+(selected?'checked':'')+' '+(selectable?'':'disabled')+' data-select-post="'+esc(p.post_id)+'" class="mt-1 h-4 w-4"><span><h3 class="font-bold">'+esc(p.title)+'</h3><p class="mt-1 text-xs text-slate-500">'+esc(p.topic_title||'بدون محور')+' · '+esc(p.source_title)+'</p></span></label><span class="rounded-full bg-slate-100 px-2 py-1 text-[11px]">'+esc(statusLabel(p.status))+'</span></div><p class="mt-3 whitespace-pre-wrap text-sm leading-8 text-slate-700">'+esc(p.content)+'</p><div class="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs"><span class="rounded-full bg-slate-100 px-2 py-1">'+esc(stateText)+'</span><div class="flex gap-2"><button data-open-post="'+esc(p.post_id)+'" class="rounded-lg border px-3 py-1.5 font-semibold text-slate-700 hover:border-indigo-400">تحرير / تفاصيل</button></div></div></article>';
  }).join('');
  document.querySelectorAll('[data-select-post]').forEach(el=>el.onchange=()=>{togglePostSelection(el.dataset.selectPost);renderPostBank({...d,items:d.items});});
  document.querySelectorAll('[data-open-post]').forEach(el=>el.onclick=()=>openPostEditor(el.dataset.openPost));
  $('post-bank-empty').classList.toggle('hidden',(d.items||[]).length>0);
  $('post-bank-summary').textContent=d.total+' Posts · '+(d.items||[]).length+' معروضة';
  const page=Math.floor(d.offset/d.limit)+1;const pages=Math.max(1,Math.ceil(d.total/d.limit));$('post-page').textContent='صفحة '+page+' من '+pages;
  $('post-prev').disabled=d.offset===0;$('post-next').disabled=d.offset+d.limit>=d.total;
  renderSelectionCount();
}
async function loadPostBank(){
  const params=new URLSearchParams();
  const source=$('post-source').value,topic=$('post-topic').value,status=$('post-status').value,q=$('post-search').value.trim(),publicationState=$('post-publication-state').value;
  if(source)params.set('source_id',source);
  if(topic)params.set('topic_id',topic);
  if(status)params.set('status',status);
  if(publicationState)params.set('publication_state',publicationState);
  if(q)params.set('q',q);
  params.set('limit','50');params.set('offset',String(state.postOffset));
  try{renderPostBank(await request('/posts?'+params.toString()));}
  catch(e){$('post-bank-summary').textContent=e.message;}
}
async function filterSelectionForScheduling(){
  const ids=[...state.selectedPostIds];
  if(!ids.length)return {eligible:[],blocked:[]};
  const chunkSize=500;
  const blocked=[];
  const blockedIds=new Set();
  for(let offset=0;offset<ids.length;offset+=chunkSize){
    const chunk=ids.slice(offset,offset+chunkSize);
    const params=new URLSearchParams();
    chunk.forEach(id=>params.append('post_ids',id));
    const result=await request('/schedules/eligibility?'+params.toString());
    (result.blocked||[]).forEach(row=>{blocked.push(row);blockedIds.add(row.post_id);});
  }
  state.selectedPostIds=ids.filter(id=>!blockedIds.has(id));
  if(blocked.length){
    showPostBankMessage('تم استبعاد '+blocked.length+' منشورًا غير قابل للنشر من خطة الجدولة: '+blocked.map(x=>x.message).join('؛ '),'info');
  }
  renderSelectionCount();
  return {eligible:state.selectedPostIds,blocked};
}


async function openScheduleCreation(){const result=await filterSelectionForScheduling();if(!result.eligible.length){$('schedule-create-panel').classList.add('hidden');state.scheduleIdempotencyKey=null;return;}await renderScheduleSelection();state.scheduleIdempotencyKey=crypto.randomUUID?crypto.randomUUID():String(Date.now());$('schedule-create-panel').classList.remove('hidden');$('schedule-name').focus();}
$('schedule-from-selection').onclick=openScheduleCreation;
async function hydrateSelection(){const raw=new URLSearchParams(location.search).get('selected_post_ids');if(!raw){renderSelectionCount();return;}state.selectedPostIds=[...new Set(raw.split(',').map(x=>x.trim()).filter(Boolean))];await renderScheduleSelection();const result=await filterSelectionForScheduling();if(result.eligible.length){state.scheduleIdempotencyKey=crypto.randomUUID?crypto.randomUUID():String(Date.now());$('schedule-create-panel').classList.remove('hidden');}else{$('schedule-create-panel').classList.add('hidden');}renderSelectionCount();}
$('schedule-cancel-create').onclick=()=>{$('schedule-create-panel').classList.add('hidden');state.scheduleIdempotencyKey=null;};
$('schedule-save-create').onclick=async()=>{const ids=state.selectedPostIds,timezone=$('schedule-timezone').value.trim(),start=$('schedule-start-at').value,interval=Number($('schedule-interval').value||0);if(!$('schedule-name').value.trim())return $('schedule-create-error').textContent='اسم الخطة مطلوب.';if(!timezone)return $('schedule-create-error').textContent='المنطقة الزمنية مطلوبة.';if(!ids.length)return $('schedule-create-error').textContent='اختر منشورًا معتمدًا واحدًا على الأقل.';if(ids.length>500)return $('schedule-create-error').textContent='الخطة الواحدة تدعم 500 منشور كحد أقصى.';if(!start)return $('schedule-create-error').textContent='وقت البداية مطلوب.';if(!interval||interval<1)return $('schedule-create-error').textContent='الفاصل بالدقائق مطلوب.';$('schedule-save-create').disabled=true;try{const startAt=localDateTimeToUtcISOString(start,timezone);const created=await request('/schedules',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('schedule-name').value.trim(),timezone,post_ids:ids,start_at:startAt,interval_minutes:interval,idempotency_key:state.scheduleIdempotencyKey})});$('schedule-create-panel').classList.add('hidden');state.scheduleIdempotencyKey=null;await loadSchedules();await loadUpcoming();await openSchedule(created.id);}catch(e){$('schedule-create-error').textContent=e.message;}finally{$('schedule-save-create').disabled=false;}};
$('activation-confirm-cancel').onclick=()=>{$('activation-confirm').classList.add('hidden');state.pendingActivationId=null;};
$('activation-confirm-ok').onclick=async()=>{const id=state.pendingActivationId;if(!id)return;$('activation-confirm-ok').disabled=true;try{await request('/schedules/'+id+'/activate',{method:'POST'});$('activation-confirm').classList.add('hidden');state.pendingActivationId=null;await loadSchedules();await loadUpcoming();await openSchedule(id);}catch(e){$('activation-confirm-error').textContent=e.message;}finally{$('activation-confirm-ok').disabled=false;}};
$('schedule-refresh').onclick=()=>{loadSchedules();loadUpcoming();loadCalendar();};$('calendar-refresh').onclick=loadCalendar;$('calendar-date').value=new Date().toISOString().slice(0,10);$('schedule-start-at').onchange=updateGeneratedScheduleTimes;$('schedule-interval').oninput=updateGeneratedScheduleTimes;$('schedule-timezone').oninput=updateGeneratedScheduleTimes;$('telegram-preview-close').onclick=()=>$('telegram-preview').classList.add('hidden');
Promise.all([loadSchedules(),loadUpcoming(),loadCalendar(),hydrateSelection()]).catch(e=>console.error(e));
</script></body></html>'''
