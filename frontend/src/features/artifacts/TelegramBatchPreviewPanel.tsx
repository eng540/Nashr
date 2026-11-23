import {useState} from 'react';
import {useMutation} from '@tanstack/react-query';
import {genericArtifactsApi,type TelegramBatchPreview} from '../../shared/api/artifactsApi';

export function TelegramBatchPreviewPanel({ids}:{ids:string[]}) {
 const [preview,setPreview]=useState<TelegramBatchPreview|null>(null);
 const [loaded,setLoaded]=useState('');
 const [name,setName]=useState('خطة دفعة Telegram');
 const [start,setStart]=useState('');
 const [interval,setInterval]=useState(60);
 const [confirmed,setConfirmed]=useState(false);
 const [saved,setSaved]=useState('');
 const key=ids.join(',');
 const schedule=useMutation({mutationFn:()=>{
   if(!preview||loaded!==key||preview.blocked_count||!confirmed||!preview.destination)throw new Error('راجع الدفعة أولاً.');
   const at=new Date(`${start}:00+03:00`);
   if(!start||!Number.isFinite(at.getTime())||at.getTime()<=Date.now())throw new Error('اختر وقت بداية مستقبلياً بتوقيت الرياض.');
   return genericArtifactsApi.telegramBatchSchedule({artifact_ids:ids,fingerprints:Object.fromEntries(preview.items.map(item=>[item.artifact_id,item.source_fingerprint])),copy_versions:Object.fromEntries(preview.items.map(item=>[item.artifact_id,item.copy_version??null])),name,timezone:'Asia/Riyadh',start_at:at.toISOString(),interval_minutes:interval,destination:preview.destination});
 },onSuccess:data=>{setSaved(data.id);setConfirmed(false);}});
 const check=useMutation({mutationFn:()=>genericArtifactsApi.telegramBatchPreview(ids),onSuccess:data=>{setPreview(data);setLoaded(key);setConfirmed(false);setSaved('');}});
 return <section aria-label="معاينة دفعة Telegram" className="space-y-3 rounded-xl border border-sky-200 bg-sky-50/50 p-3">
  <div><h4 className="text-sm font-bold">قبل تجهيز دفعة Telegram</h4><p className="mt-1 text-xs leading-6">افحص الوجهة والنص والعناصر المحجوبة معاً. لا ينشئ الفحص مسودات أو جداول ولا يعيد إرسال منشور.</p></div>
  <button type="button" disabled={!ids.length||check.isPending} onClick={()=>check.mutate()} className="rounded-lg border bg-white p-2 text-sm font-semibold">{check.isPending?'فحص الدفعة...':`معاينة وفحص دفعة Telegram (${ids.length})`}</button>
  {preview&&loaded===key?<><p className="break-all rounded-lg bg-white p-2 text-xs">الوجهة الفعلية: <bdi>{preview.destination??'غير مضبوطة'}</bdi></p><p className="text-xs"><span className="font-bold text-emerald-700">{preview.ready_count} مؤهل مبدئياً</span> · <span className="font-bold text-amber-800">{preview.blocked_count} محجوب</span></p>
   {preview.items.map((item,index)=><details key={item.artifact_id} className="rounded-lg border bg-white p-3 text-xs leading-6"><summary className="cursor-pointer font-semibold">{index+1}. {item.title} · {item.ready?'مؤهل مبدئياً':'محجوب'}</summary>{item.blockers.map(reason=><p key={reason} className="mt-1 text-amber-900">{reason}</p>)}<p dir="auto" className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap break-words rounded bg-slate-50 p-2">{item.content}</p>{item.publications.map(publication=><p key={publication.id} className="break-all">سجل {publication.status} · {publication.external_ids.join(', ')||'لا تأكيد وصول'}</p>)}{item.schedules.map((schedule,i)=><p key={i}>{schedule.name} · {schedule.schedule_status} · {schedule.item_status}</p>)}</details>)}
   <p className="text-xs leading-6 text-slate-600">{preview.caveat}</p>
   {!preview.blocked_count&&!saved?<details className="rounded-lg border bg-white p-3 text-xs"><summary className="cursor-pointer font-bold">حفظ خطة للدفعة دون تفعيل</summary><div className="mt-3 space-y-3">
    <label className="block">اسم خطة الدفعة<input aria-label="اسم خطة الدفعة" className="block w-full rounded border p-2" value={name} onChange={e=>setName(e.target.value)}/></label>
    <label className="block">وقت البداية بتوقيت الرياض<input aria-label="بداية دفعة Telegram" type="datetime-local" className="block w-full min-w-0 rounded border p-2" value={start} onChange={e=>setStart(e.target.value)}/></label>
    <label className="block">الفاصل بالدقائق<input aria-label="فاصل دفعة Telegram" type="number" min={1} max={10080} className="block w-full rounded border p-2" value={interval} onChange={e=>setInterval(Number(e.target.value))}/></label>
    {start&&Number.isFinite(interval)&&interval>0?<p>الترتيب هو ترتيب التحديد أعلاه. المادة الأخيرة بعد {(ids.length-1)*interval} دقيقة من البداية.</p>:null}
    <label className="flex gap-2"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>راجعت النصوص والوجهة والترتيب. أحفظ خطة مسودة فقط.</label>
    <p>الحفظ لا يرسل شيئاً. راجع الخطة في مساحة النشر وفعّلها هناك بقرار مستقل. تغير المحتوى أو الوجهة أو استبعاد Telegram بعد المراجعة يمنع تنفيذ هذه الخطة.</p>
    <button type="button" disabled={!confirmed||!start||!name.trim()||schedule.isPending} onClick={()=>schedule.mutate()} className="rounded border bg-sky-700 p-2 text-white disabled:opacity-40">{schedule.isPending?'حفظ الخطة...':'حفظ خطة Telegram كمسودة'}</button>
   </div></details>:null}
   {saved?<p role="status" className="text-xs text-emerald-800">حُفظت الخطة كمسودة دون تفعيل. <a href="/publishing" className="underline">افتح مساحة النشر لمراجعتها</a><br/><bdi>{saved}</bdi></p>:null}
   {schedule.isError?<p role="alert" className="text-xs text-rose-700">{schedule.error.message}</p>:null}
  </>:null}
  {check.isError?<p role="alert" className="text-xs text-rose-700">{check.error.message}</p>:null}
 </section>;
}
