import {FacebookPlanReviewPanel} from './FacebookPlanReviewPanel';
import {FacebookTextExecutionPanel} from './FacebookTextExecutionPanel';
import {YouTubePlanReviewPanel} from './YouTubePlanReviewPanel';
import {InstagramPlanReviewPanel,InstagramExactOperation} from './InstagramPlanReviewPanel';
import {useState,useEffect,useRef} from 'react';
import {CopySuggestionsPanel} from './CopySuggestionsPanel';
import {MediaInspectionHistoryPanel} from './MediaInspectionHistoryPanel';
import {PlatformCopyMediaPanel} from './PlatformCopyMediaPanel';
import {useMutation} from '@tanstack/react-query';
import {genericArtifactsApi,type CentralPlatformCopy} from '../../shared/api/artifactsApi';

export function CentralPlatformCopiesPanel({id,kind,onPlan,request}:{id:string;kind:string;onPlan?:()=>void;request?:{platform:string;nonce:number}}) {
 function fileSize(bytes:unknown) {const size=Number(bytes);return size<1024?`${size} بايت`:size<1024*1024?`${(size/1024).toFixed(1)} كيبيبايت`:`${(size/1024/1024).toFixed(2)} ميبيبايت`;}
 const panelRef=useRef<HTMLDetailsElement>(null);
 const [handoff,setHandoff]=useState('');
 const [rows,setRows]=useState<CentralPlatformCopy[]>([]);
 const [active,setActive]=useState('telegram');
 const [draft,setDraft]=useState<CentralPlatformCopy|null>(null);
 const [note,setNote]=useState('');
 const [background,setBackground]=useState('');
 const [jpegOpen,setJpegOpen]=useState(false);
 const jpeg=useMutation({mutationFn:()=>genericArtifactsApi.jpegPreview(id,active,shown!.current_source_fingerprint,shown!.version,background)});
 const load=useMutation({mutationFn:()=>genericArtifactsApi.platformCopies(id),onSuccess:data=>{setRows(data.items);setDraft(null);setNote('');}});
 const prepare=useMutation({mutationFn:()=>genericArtifactsApi.prepareCopies(id),onSuccess:data=>{setRows(data.items);setDraft(null);setNote('جُهزت السجلات الناقصة فقط. النسخ المعدلة لم تُستبدل، والأصل لم يتغير.');}});
 const save=useMutation({mutationFn:()=>genericArtifactsApi.updateCopy(id,draft!),onSuccess:copy=>{setRows(current=>current.map(row=>row.platform===copy.platform?copy:row));setDraft(null);setNote('حُفظت حقول النسخة فقط. لا مسودة نشر أو جدول أو إرسال من هذا الحفظ.');}});
 const inspect=useMutation({mutationFn:()=>genericArtifactsApi.inspectMedia(id,active)});
 const row=rows.find(item=>item.platform===active);
 const shown=draft??row;
 const busy=load.isPending||prepare.isPending||save.isPending||inspect.isPending||jpeg.isPending;
 useEffect(()=>{
  const params=new URLSearchParams(window.location.search);
  if(params.get('artifact_id')!==id)return;
  const platform=params.has('instagram_job_id')?'instagram':params.get('copy_platform');
  if(platform&&!['telegram','instagram','facebook','youtube','x','tiktok'].includes(platform))return;
  if(platform||params.has('text_job_id')||params.has('photo_job_id')||params.has('instagram_job_id')){
   if(panelRef.current)panelRef.current.open=true;
   setActive(platform||'facebook');load.mutate();
   setHandoff('فتح النسخة المحفوظة للمادة والمنصة المحددتين فقط، دون تجهيز أو تغيير وجهة أو نشر.');
  }
 },[id]);
 useEffect(()=>{
  if(!request)return;
  if(panelRef.current){panelRef.current.open=true;panelRef.current.scrollIntoView({block:'start',behavior:'smooth'});}
  if(draft||busy){setHandoff('احفظ تعديلات النسخة أو ألغها أولاً. لم نغيّر المنصة أو نحذف تعديلاتك.');return;}
  setActive(request.platform);setHandoff('فتح السجلات المحفوظة فقط. لا تجهيز جديد أو نشر من هذا الانتقال.');load.mutate();
 },[request?.nonce]);
 function edit(field:keyof CentralPlatformCopy['fields'],value:string|string[]) {inspect.reset();jpeg.reset();if(shown)setDraft({...shown,fields:{...shown.fields,[field]:value}});setNote('');}
 return <details ref={panelRef} className="scroll-mt-24 rounded-xl border border-violet-200 bg-violet-50/50 p-3" aria-label={`نسخ المنصات ${id}`}>
  <summary className="cursor-pointer text-xs font-bold">نسخ المنصات · حقول مرتبطة بالأصل</summary>
  <div className="mt-3 space-y-3 text-xs leading-6">{handoff?<p role="status" className="rounded border bg-white p-2">{handoff}</p>:null}<p>اعتماد الأصل واحد. ننسخ النص كما هو دون قص أو توليد؛ نتحقق من الحقول المعروفة ونبين ما ينقص. تعديل نسخة لا يغير الأصل أو بقية المنصات.</p>
   <div className="flex flex-wrap gap-2"><button type="button" disabled={busy||!!draft} onClick={()=>{inspect.reset();jpeg.reset();load.mutate();}} className="rounded border bg-white p-2">عرض النسخ المحفوظة</button><button type="button" disabled={busy||!!draft} onClick={()=>{inspect.reset();jpeg.reset();prepare.mutate();}} className="rounded border bg-white p-2">تجهيز النسخ الناقصة دون استبدال</button></div>
   {load.isSuccess&&!rows.length?<p role="status">لا توجد نسخ مركزية محفوظة لهذه المادة بعد. استخدم تجهيز النسخ الناقصة بقرار منفصل؛ لا نجهزها تلقائياً عند فتح المسار.</p>:null}
   {rows.length?<><label className="block">المنصة<select aria-label={`منصة النسخة ${id}`} disabled={!!draft||busy} value={active} onChange={e=>{setActive(e.target.value);inspect.reset();jpeg.reset();setNote('');}} className="block w-full rounded border bg-white p-2">{rows.map(copy=><option key={copy.platform} value={copy.platform}>{copy.label} · {copy.field_status==='FIELDS_VALIDATED'?'الحقول مقبولة مبدئياً':'يلزم استكمال'}</option>)}</select></label>
    {shown?<><p className="rounded bg-white p-2">{shown.origin==='UNCHANGED_ORIGINAL'?'من الأصل دون تغيير':'حقول معدلة'} · إصدار {shown.version} · {shown.central_approval==='APPROVED'?'اعتماد الأصل محفوظ':'الأصل غير معتمد'}</p>
     {draft?<p role="status" className="text-amber-800">تعديلات غير محفوظة. الحالات أدناه تخص آخر إصدار محفوظ وتُفحص مجدداً عند الحفظ.</p>:null}
     {shown.blockers.map(reason=><p key={reason} className="text-amber-900">{reason}</p>)}
     {['telegram','youtube','instagram'].includes(active)?<CopySuggestionsPanel key={`${id}:${active}:${shown.version}`} id={id} copy={shown} disabled={busy||!!draft} onApplied={()=>load.mutate()}/>:null}
     {['instagram','facebook'].includes(active)&&kind==='IMAGE'&&shown?<PlatformCopyMediaPanel key={`${id}:${active}`} id={id} copy={shown} preview={jpeg.data} background={background} disabled={busy||!!draft} onChanged={()=>{jpeg.reset();setJpegOpen(false);inspect.reset();load.mutate();}}/>:null}
     {['youtube','facebook'].includes(active)?<label className="block">{active==='facebook'?'عنوان منفصل محفوظ، لا يرسله المسار الحالي':'عنوان المنصة'}<input aria-label={`عنوان نسخة ${id}`} value={shown.fields.title} onChange={e=>edit('title',e.target.value)} className="block w-full rounded border bg-white p-2"/></label>:null}
     <label className="block">نص النشر / الوصف<textarea aria-label={`وصف نسخة ${id}`} dir="auto" rows={6} value={shown.fields.description} onChange={e=>edit('description',e.target.value)} className="block w-full rounded border bg-white p-2"/></label>
     {['youtube','facebook'].includes(active)?<label className="block">{active==='facebook'?'وسوم منفصلة محفوظة، لا يرسلها المسار الحالي':'كلمات مفتاحية، واحدة في كل سطر'}<textarea aria-label={`وسوم نسخة ${id}`} rows={2} value={shown.fields.tags.join('\n')} onChange={e=>edit('tags',e.target.value.split('\n').filter(Boolean))} className="block w-full rounded border bg-white p-2"/></label>:null}
     {(active==='instagram'&&kind==='IMAGE'||active==='facebook')?<label className="block">{active==='facebook'?'نص بديل محفوظ، لا يرسله المسار الحالي':'نص بديل للصورة، دون اختراع وصف'}<input aria-label={`نص بديل نسخة ${id}`} value={shown.fields.alt_text} onChange={e=>edit('alt_text',e.target.value)} className="block w-full rounded border bg-white p-2"/></label>:null}
     {active==='facebook'?<p>هذه الحقول محفوظة دون حذف. إذا أردت نقل عنوان أو وسم إلى نص النشر فراجعه وعدله بنفسك، أو أفرغ الحقل المنفصل صراحةً إن لم ترده. حفظ النسخة لا يوافق على نشرها، ولا يغير الأصل أو النسخ الأخرى.</p>:null}
     <div className="flex flex-wrap gap-2"><button type="button" disabled={!draft||busy} onClick={()=>{inspect.reset();jpeg.reset();save.mutate();}} className="rounded bg-violet-700 p-2 text-white disabled:opacity-40">حفظ النسخة وفحص حقولها</button>{draft?<button type="button" disabled={busy} onClick={()=>setDraft(null)} className="rounded border p-2">تجاهل التعديلات غير المحفوظة</button>:null}</div>
     {['IMAGE','VIDEO'].includes(kind)?<MediaInspectionHistoryPanel key={`${id}:${active}:${shown.version}:${shown.current_source_fingerprint}`} id={id} copy={shown} disabled={busy||!!draft}/>:null}
     {shown.source_stale?<p className="text-amber-900">الحفظ يربط هذه الحقول بالأصل الحالي بعد مراجعتك. لا يستبدل النص تلقائياً.</p>:null}
     <button type="button" disabled={busy||!!draft} onClick={()=>inspect.mutate()} className="rounded border bg-white p-2">{kind==='VIDEO'?'فحص الفيديو الأصلي (قراءة متدفقة حتى 300MB)':'فحص الملف الأصلي (قراءة حتى 50MiB)'}</button>
     {['instagram','facebook'].includes(active)&&kind==='IMAGE'&&shown?<details open={jpegOpen} onToggle={e=>setJpegOpen(e.currentTarget.open)} className="rounded border bg-white p-2"><summary>معاينة JPEG منفصلة دون حفظ أو نشر</summary><p>للصور فقط. يحافظ التحويل على كامل الإطار، يطبق اتجاه الصورة، ويجعل العرض بين 320 و1440، بجودة90 ولونsRGB. لا قص أو توليد. تزال بيانات EXIF والموقع من النسخة. عند غياب ملف لون نفترضsRGB. النسخة مؤقتة للتنزيل ولا تستخدمها خطة النشر تلقائياً.</p><label className="block">اختر خلفية للشفافية<select aria-label={`خلفية JPEG ${id}`} value={background} disabled={busy} onChange={e=>{setBackground(e.target.value);jpeg.reset();}} className="block w-full rounded border p-2"><option value="">اختر صراحةً</option><option value="#ffffff">أبيض</option><option value="#000000">أسود</option></select></label><button type="button" disabled={busy||!!draft||!background||shown.source_stale} onClick={()=>jpeg.mutate()} className="rounded border p-2">إنشاء معاينة JPEG محلية</button>{jpeg.isError?<p role="alert">{jpeg.error.message}</p>:null}{jpeg.data?<div role="status"><p>نسخة منفصلة مؤقتة من الإصدار {jpeg.data.copy_version}. الأصل وحقولك لم يتغيرا. لا جاهزية نهائية أو إذن نشر.</p><img src={jpeg.data.data_url} alt="معاينة JPEG المشتقة للمراجعة" className="max-h-96 max-w-full object-contain"/><p>{String(jpeg.data.measurements.width)} × {String(jpeg.data.measurements.height)} بكسل · {fileSize(jpeg.data.measurements.size_bytes)}</p><a href={jpeg.data.data_url} download={`instagram-${id}.jpg`} className="underline">تنزيل نسخة JPEG للمراجعة</a>{[...jpeg.data.blockers,...jpeg.data.pending].map(reason=><p key={reason}>{reason}</p>)}</div>:null}</details>:null}
     {inspect.data?<div role="status" className="rounded border bg-white p-2"><p>قياسات فقط، لا جاهزية نهائية ولا إذن نشر. إصدار النسخة {inspect.data.copy_version}.</p><dl className="grid grid-cols-2 gap-1"><dt>الصيغة</dt><dd dir="ltr">{String(inspect.data.measurements.format??'غير محددة')}</dd><dt>الأبعاد</dt><dd>{String(inspect.data.measurements.width)} × {String(inspect.data.measurements.height)} بكسل</dd><dt>حجم الملف</dt><dd>{fileSize(inspect.data.measurements.size_bytes)}</dd>{inspect.data.measurements.header_evidence?<><dt>حدود GOP</dt><dd>{(inspect.data.measurements.header_evidence as {closed_gop?:string}).closed_gop==='REFRESH_BOUNDARIES_VERIFIED'?'متحقق: حدود H.264 داخلية تبدأ بـIDR':'غير متحقق'}</dd><dt>نمط VBR</dt><dd>غير متحقق، لا نستنتجه من متوسط التدفق</dd></>:null}{inspect.data.measurements.duration_seconds!=null?<><dt>المدة</dt><dd>{Number(inspect.data.measurements.duration_seconds).toFixed(1)} ثانية</dd></>:null}<dt>نتيجة الفحص</dt><dd>{inspect.data.blockers.length?'توجد عوائق':'القياسات المفحوصة مقبولة، والفحص غير مكتمل'}</dd></dl><details className="mt-2"><summary className="cursor-pointer">بيانات تقنية اختيارية</summary><pre dir="ltr" className="overflow-auto whitespace-pre-wrap break-all">{JSON.stringify(inspect.data.measurements,null,2)}</pre></details>{[...inspect.data.blockers,...inspect.data.pending].map(reason=><p key={reason}>{reason}</p>)}</div>:null}
     {inspect.isError?<p role="alert">{inspect.error.message}</p>:null}
     <details className="rounded border bg-white p-2"><summary className="cursor-pointer">ما الذي لم يُتحقق بعد؟</summary>{[...shown.warnings,...shown.media_checks_pending,...shown.execution_blockers].map(reason=><p key={reason}>{reason}</p>)}<p>نسخة Telegram تُستخدم في معاينة الدفعة وخطتها الجديدة فقط بعد مراجعتها. تغيير النسخة يوقف الخطة السابقة. حفظ حقول أي منصة لا يأذن بالنشر. الاتصال وفحص الوسيط وخطوات التنفيذ تُراجع في مسار كل منصة على حدة.</p>{shown.sources.map(url=><a key={url} href={url} target="_blank" rel="noreferrer" className="block break-all underline">{url}</a>)}</details>
    </>:null}</>:null}
   {load.isError||prepare.isError||save.isError?<p role="alert" className="text-rose-700">{load.error?.message??prepare.error?.message??save.error?.message}</p>:null}
   {active==='instagram'?<InstagramExactOperation key={id} id={id}/>:null}
   {active==='instagram'&&row&&!draft&&['IMAGE','VIDEO'].includes(kind)?<InstagramPlanReviewPanel key={`${id}:${row.version}:${row.current_source_fingerprint}`} id={id} kind={kind} disabled={busy}/>:null}
   {active==='youtube'&&row&&!draft&&kind==='VIDEO'?<YouTubePlanReviewPanel key={`${id}:${row.version}:${row.current_source_fingerprint}`} id={id} disabled={busy}/>:null}
   {active==='facebook'&&row&&!draft&&kind==='IMAGE'?<FacebookPlanReviewPanel key={`${id}:${row.version}:${row.current_source_fingerprint}`} id={id} disabled={busy}/>:null}
   {active==='facebook'&&row&&!draft&&kind==='VIDEO'?<div className="rounded border bg-white p-3"><p>مسار Facebook للفيديو هو Reel على صفحة عامة، منفصل عن مراجعة النص والصورة. فتحه يمرر معرف الأصل فقط، ولا يجهز أو يرفع ملفاً ولا يعتمد نشراً. الربط والوسيط والوصف والصفحة وقرار التنفيذ تحتاج مراجعة هناك.</p><a className="inline-block rounded border p-2 font-bold" href={`/connections?reel_artifact_id=${encodeURIComponent(id)}#platform-facebook`}>فتح مراجعة Facebook Reel لهذه المادة</a></div>:null}
   {['x','tiktok'].includes(active)&&row?<p className="rounded border bg-amber-50 p-3">الحقول محفوظة للمراجعة فقط. لا مسار تنفيذ منشور من هذه النسخة. <a className="underline" href={`/connections#platform-${active}`}>متطلبات ربط المنصة وحدودها</a></p>:null}
   {active==='facebook'&&row&&!draft&&['TEXT','IMAGE'].includes(kind)?<FacebookTextExecutionPanel key={`${id}:${row.version}:${row.current_source_fingerprint}:execute`} id={id} photo={kind==='IMAGE'}/>:null}
   {active==='telegram'&&row&&!draft&&onPlan?<button type="button" disabled={busy} onClick={onPlan} className="rounded border bg-white p-2 font-bold">معاينة وجدولة نسخة Telegram هذه</button>:null}
   {note?<p role="status" className="text-emerald-800">{note}</p>:null}
  </div>
 </details>;
}
