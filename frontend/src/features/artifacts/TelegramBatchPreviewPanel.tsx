import {useState} from 'react';
import {useMutation,useQuery} from '@tanstack/react-query';
import {get,post} from '../../shared/api/client';
import type {Connections} from '../publishing/ConnectionsPage';
import {genericArtifactsApi,type TelegramBatchPreview} from '../../shared/api/artifactsApi';

export function TelegramBatchPreviewPanel({ids}:{ids:string[]}) {
 const channels=useQuery({queryKey:['connections'],queryFn:()=>get<Connections>('/api/connections'),retry:false});
 const [targets,setTargets]=useState<string[]>([]);
 const [allPreviews,setAllPreviews]=useState<TelegramBatchPreview[]>([]);
 const [preview,setPreview]=useState<TelegramBatchPreview|null>(null);
 const [loaded,setLoaded]=useState('');
 const [name,setName]=useState('خطة دفعة Telegram');
 const [start,setStart]=useState('');
 const [interval,setInterval]=useState(60);
 const [confirmed,setConfirmed]=useState(false);
 const [saved,setSaved]=useState('');
 const [savedPlans,setSavedPlans]=useState<{id:string;name:string}[]>([]);
 const key=ids.join(',')+'|'+targets.join(',');
 const schedule=useMutation({mutationFn:()=>{
   if(!preview||loaded!==key||preview.blocked_count||!confirmed||!preview.destination)throw new Error('راجع الدفعة أولاً.');
   const at=new Date(`${start}:00+03:00`);
   if(!start||!Number.isFinite(at.getTime())||at.getTime()<=Date.now())throw new Error('اختر وقت بداية مستقبلياً بتوقيت الرياض.');
   if(targets.length)return post<{plans:{id:string;name:string}[]}>('/api/connections/telegram/plans',{artifact_ids:ids,connection_ids:targets,previews:allPreviews,name,timezone:'Asia/Riyadh',start_at:at.toISOString(),interval_minutes:interval}).then(data=>{setSavedPlans(data.plans);return {id:data.plans[0].id};});
   return genericArtifactsApi.telegramBatchSchedule({artifact_ids:ids,fingerprints:Object.fromEntries(preview.items.map(item=>[item.artifact_id,item.source_fingerprint])),copy_versions:Object.fromEntries(preview.items.map(item=>[item.artifact_id,item.copy_version??null])),name,timezone:'Asia/Riyadh',start_at:at.toISOString(),interval_minutes:interval,destination:preview.destination});
 },onSuccess:data=>{setSaved(data.id);setConfirmed(false);}});
 const prepare=useMutation({mutationFn:()=>genericArtifactsApi.prepareBatchCopies(ids),onSuccess:()=>{setPreview(null);setLoaded('');setConfirmed(false);setSaved('');}});
 const check=useMutation({mutationFn:async()=>{
   if(!targets.length){const data=await genericArtifactsApi.telegramBatchPreview(ids);setAllPreviews([data]);return data;}
   const data=await post<{channels:TelegramBatchPreview[]}>('/api/connections/telegram/preview',{artifact_ids:ids,connection_ids:targets});setAllPreviews(data.channels);
   return {...data.channels[0],blocked_count:data.channels.reduce((n,c)=>n+c.blocked_count,0),ready_count:data.channels.reduce((n,c)=>n+c.ready_count,0)};
 },onSuccess:data=>{setPreview(data);setLoaded(key);setConfirmed(false);setSaved('');setSavedPlans([]);}});
 return <section aria-label="معاينة دفعة Telegram" className="space-y-3 rounded-xl border border-sky-200 bg-sky-50/50 p-3">
  <div><h4 className="text-sm font-bold">قبل تجهيز دفعة Telegram</h4><p className="mt-1 text-xs leading-6">افحص الوجهة والنص والعناصر المحجوبة معاً. لا ينشئ الفحص مسودات أو جداول ولا يعيد إرسال منشور.</p></div>
  <fieldset className="rounded border bg-white p-3 text-xs leading-7"><legend className="font-bold">قنوات هذه المادة أو الدفعة فقط</legend><p>لا قنوات محددة يعني استخدام المسار القديم فقط، لا جميع القنوات. اختيار عدة قنوات يحفظ خطة مسودة مستقلة لكل قناة، دون تفعيل.</p>{channels.data?.telegram.items.map(c=><label key={c.id} className="block"><input type="checkbox" checked={targets.includes(c.id)} onChange={e=>{setTargets(e.target.checked?[...targets,c.id]:targets.filter(id=>id!==c.id));setConfirmed(false);setSaved('');}}/> {c.label} · <bdi>{c.details.destination}</bdi></label>)}<a href="/connections" className="underline">إدارة وإضافة القنوات</a></fieldset>
  <button type="button" disabled={!ids.length||prepare.isPending||schedule.isPending} onClick={()=>prepare.mutate()} className="rounded-lg border bg-white p-2 text-sm font-semibold">{prepare.isPending?'تجهيز النسخ الناقصة...':`تجهيز نسخ المنصات للمحدد (${ids.length})`}</button>
  <p className="text-xs leading-6">التجهيز يضيف النسخ الناقصة دون استبدال تعديل سابق أو تغيير الوجهات والمواعيد. بعده افحص معاينة Telegram أدناه.</p>
  {prepare.isSuccess?<p role="status" className="text-xs text-emerald-800">جُهزت سجلات {prepare.data.prepared} مادة دون إرسال أو جدولة. فحوص الحقول داخل كل بطاقة، والوسائط والحسابات غير المعتمدة تبقى محجوبة.</p>:null}
  {prepare.isError?<p role="alert" className="text-xs text-rose-700">{prepare.error.message}</p>:null}
  <button type="button" disabled={!ids.length||check.isPending||prepare.isPending} onClick={()=>check.mutate()} className="rounded-lg border bg-white p-2 text-sm font-semibold">{check.isPending?'فحص الدفعة...':`معاينة وفحص دفعة Telegram (${ids.length})`}</button>
  {preview&&loaded===key?<>{targets.length?<div className="rounded border bg-white p-3 text-xs leading-7"><h5 className="font-bold">معاينة منفصلة لكل قناة</h5>{allPreviews.map((channel,i)=><details key={i}><summary>{(channel as TelegramBatchPreview&{channel_label:string}).channel_label} · {channel.destination} · {channel.blocked_count} محجوب</summary>{channel.items.map(item=><div key={item.artifact_id} className="border-t py-2"><p>{item.title}</p><p className="whitespace-pre-wrap break-words">{item.content}</p>{item.blockers.map(b=><p key={b} className="text-amber-900">{b}</p>)}{item.publications.map(p=><p key={p.id}>سجل هذه القناة: {p.status}</p>)}</div>)}</details>)}</div>:null}<p className="break-all rounded-lg bg-white p-2 text-xs">الوجهة الفعلية: <bdi>{targets.length?allPreviews.map(p=>p.destination).join(' · '):preview.destination??'غير مضبوطة'}</bdi></p><p className="text-xs"><span className="font-bold text-emerald-700">{preview.ready_count} مؤهل مبدئياً</span> · <span className="font-bold text-amber-800">{preview.blocked_count} محجوب</span></p>
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
   {savedPlans.length?<div className="space-y-2 text-xs">{savedPlans.map(p=><p key={p.id}><a className="underline" href={'/publishing?schedule_id='+encodeURIComponent(p.id)}>{p.name||'فتح خطة القناة'}</a></p>)}</div>:null}
   {saved?<p role="status" className="text-xs text-emerald-800">حُفظت الخطط المختارة كمسودات دون تفعيل. افتح مساحة النشر لمراجعة كل قناة وخطتها. <a href={`/publishing?schedule_id=${encodeURIComponent(saved)}`} className="underline">افتح مساحة النشر لمراجعتها</a><br/><bdi>{saved}</bdi></p>:null}
   {schedule.isError?<p role="alert" className="text-xs text-rose-700">{schedule.error.message}</p>:null}
  </>:null}
  {check.isError?<p role="alert" className="text-xs text-rose-700">{check.error.message}</p>:null}
 </section>;
}
