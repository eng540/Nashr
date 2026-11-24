import {useState} from 'react';
import {useMutation,useQuery} from '@tanstack/react-query';
import {genericArtifactsApi,type CentralPlatformCopy} from '../../shared/api/artifactsApi';
export function MediaInspectionHistoryPanel({id,copy,disabled}:{id:string;copy:CentralPlatformCopy;disabled:boolean}){
 const [open,setOpen]=useState(false);
 const query=useQuery({queryKey:['media-inspections',id,copy.platform,copy.version,copy.current_source_fingerprint],enabled:open,queryFn:()=>genericArtifactsApi.mediaInspections(id,copy.platform)});
 const save=useMutation({mutationFn:()=>genericArtifactsApi.saveMediaInspection(id,copy.platform,{source_fingerprint:copy.current_source_fingerprint,copy_version:copy.version,selected:true}),onSuccess:()=>query.refetch()});
 return <details className="rounded border bg-white p-2" open={open} onToggle={e=>setOpen(e.currentTarget.open)}><summary>سجل فحوص الوسيط المرتبط بالإصدار</summary><p>سجل قياسات، لا شهادة قبول أو إذن نشر. لا يعيد عرض السجل قراءة بايتات الملف. الفحص أدناه يقرأ الوسيط المختار حالياً ويحفظ نتيجته فقط.</p>
 <button type="button" disabled={disabled||save.isPending||copy.source_stale} onClick={()=>save.mutate()} className="rounded border p-2">{save.isPending?'فحص وحفظ القياسات...':'فحص الوسيط الحالي وحفظ سجل خاص'}</button>
 {query.isLoading?<p>تحميل سجل الفحوص...</p>:null}{query.data?.items.length===0?<p>لا فحوص محفوظة لهذه المنصة.</p>:null}
 {query.data?.items.map(record=><details key={record.id} className="mt-2 rounded border p-2"><summary>{record.stale?'قديم، يحتاج فحصاً جديداً':'مرتبط بالإصدار الحالي، لا قبول نهائي'} · إصدار {record.copy_version}</summary><p>{record.created_at} · {record.selected?'الوسيط المختار وقت الفحص':'الأصل وقت الفحص'}</p><p>{record.caveat}</p>{record.stale_reasons.map(reason=><p key={reason}>{reason}</p>)}<p>{String(record.result.measurements.format)} · {String(record.result.measurements.width)} × {String(record.result.measurements.height)}</p><p>{record.result.blockers.length?'الفحص يحتوي عوائق':'القياسات المسجلة دون عائق، وتبقى الفحوص المعلقة'}</p>{[...record.result.blockers,...record.result.pending].map(reason=><p key={reason}>{reason}</p>)}</details>)}
 {query.isError||save.isError?<p role="alert">{query.error?.message??save.error?.message}</p>:null}
 </details>;
}
