import {useState} from 'react';
import {get,post} from '../../shared/api/client';
type Job={id:string;state:string;snapshot_hash:string;permalink:string|null;snapshot:{caption:string;media_sha256:string;connection:{page_id:string;page_name:string};audience:string}};
export function FacebookReelPanel(){
 const [uid,setUid]=useState(''),[job,setJob]=useState<Job|null>(null),[ok,setOk]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const base='/api/connections/facebook/reels';
 async function run(fn:()=>Promise<void>){setBusy(true);setError('');try{await fn();}catch(e){setError(e instanceof Error?e.message:'تعذر التنفيذ');}finally{setBusy(false);}}
 return <details className="rounded border p-3"><summary>نشر Reel على صفحة Facebook، قرار مستقل</summary><p>ينشر على الصفحة العامة فقط. لا يغير Instagram. لا رفع قبل موافقتك على المعاينة. يرسل MP4 إلى Meta دون رابط ملف متاح للآخرين. الاستجابة غير المؤكدة لا تعاد تلقائياً.</p>
 <label>معرف المادة المعتمدة<input aria-label="مادة Facebook Reel" value={uid} onChange={e=>{setUid(e.target.value);setJob(null);setOk(false);}} dir="ltr" className="block w-full rounded border p-2"/></label>
 <button className="workspace-secondary" disabled={busy||!uid||!!job} onClick={()=>void run(async()=>{await post(base+'/materials/'+uid+'/prepare-delivery',{});setJob(await post<Job>(base+'/materials/'+uid+'/preview',{}));})}>تجهيز نسخة توافق خاصة ومعاينة دون نشر</button>
 {job?<div className="space-y-3"><p>الصفحة: {job.snapshot.connection.page_name} · {job.snapshot.connection.page_id}</p><p>الجمهور: Reel عام على Facebook. الوقت: بعد الاعتماد الآن.</p><p className="whitespace-pre-wrap">{job.snapshot.caption}</p><p dir="ltr" className="break-all">SHA256: {job.snapshot.media_sha256}</p><p>الحالة: {job.state}</p>{job.permalink?<a className="underline" target="_blank" rel="noreferrer" href={job.permalink}>فتح Reel المنشور</a>:null}
 {job.state==='DRAFT'?<><label><input type="checkbox" checked={ok} onChange={e=>setOk(e.target.checked)}/> أوافق على نشر هذا الفيديو والوصف على الصفحة العامة الآن وإرسال الملف إلى Meta.</label><button className="workspace-secondary" disabled={busy||!ok} onClick={()=>void run(async()=>setJob(await post<Job>(base+'/'+job.id+'/approve',{snapshot_hash:job.snapshot_hash,exact_words_approved:true,public_page_approved:true,media_transfer_approved:true})))}>اعتماد نشر Reel العام الآن</button></>:null}
 <button className="workspace-secondary" disabled={busy} onClick={()=>void run(async()=>setJob(await get<Job>(base+'/'+job.id)))}>قراءة نتيجة Reel دون إعادة النشر</button></div>:null}
 {error?<p role="alert">{error}</p>:null}</details>;
}
