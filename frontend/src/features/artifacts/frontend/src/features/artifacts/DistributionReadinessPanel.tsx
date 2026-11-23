import {useState} from 'react';
import {useMutation} from '@tanstack/react-query';
import {genericArtifactsApi,type DistributionReadiness} from '../../shared/api/artifactsApi';

export function DistributionReadinessPanel({ids}:{ids:string[]}) {
 const [rows,setRows]=useState<DistributionReadiness[]>([]);
 const [selected,setSelected]=useState<string[]>([]);
 const [note,setNote]=useState('');
 const identity=ids.join(',');
 const [loadedIdentity,setLoadedIdentity]=useState('');
 const load=useMutation({mutationFn:async()=>Promise.all(ids.map(id=>genericArtifactsApi.readiness(id))),onSuccess:data=>{setRows(data);setSelected(data[0]?.targets.filter(target=>target.selected).map(target=>target.platform)??[]);setLoadedIdentity(identity);setNote('');}});
 const save=useMutation({mutationFn:()=>genericArtifactsApi.saveDistribution({artifact_ids:ids,platforms:selected,fingerprints:Object.fromEntries(rows.map(row=>[row.artifact_id,row.source_fingerprint]))}),onSuccess:result=>{setRows(result.items);setNote(`حُفظ اختيار ${result.saved} مادة. لم تُنشأ مسودات أو جداول ولم يُرسل شيء.`);}});
 const current=loadedIdentity===identity&&rows.length===ids.length;
 return <section className="space-y-3 rounded-xl border border-indigo-200 bg-indigo-50/50 p-3" aria-label={ids.length===1?`جاهزية توزيع ${ids[0]}`:'جاهزية توزيع الدفعة'}>
  <div><h4 className="text-sm font-bold">اعتماد واحد، وجهات تختارها</h4><p className="mt-1 text-xs leading-6">اعتماد المحتوى مركزي. أهلية النسخة والربط وإذن التنفيذ أمور مستقلة. لا يلزم ذكاء اصطناعي لاستخدام الأصل دون تغيير حيث يصلح، ولا نقص النص ليتسع.</p></div>
  <button type="button" disabled={!ids.length||load.isPending||save.isPending} onClick={()=>load.mutate()} className="rounded-lg border bg-white p-2 text-sm font-semibold disabled:opacity-40">{load.isPending?'فحص الجاهزية...':`فحص جاهزية واختيار المنصات (${ids.length})`}</button>
  {current?<><p className="text-xs">حفظ الوجهات يستبدل اختيار المواد المحددة فقط، ولا يغير مواعيد أو منشورات قائمة. في الدفعة تُعرض اختيارات أول مادة كبداية، وتُطبق القائمة التي تحفظها على الدفعة.</p>
   <div className="flex flex-wrap gap-3"><button type="button" onClick={()=>setSelected(rows[0].targets.map(target=>target.platform))} className="rounded border bg-white p-2 text-xs">تحديد جميع المنصات</button><button type="button" onClick={()=>setSelected([])} className="rounded border bg-white p-2 text-xs">إلغاء جميع المنصات</button></div>
   <div className="grid gap-2 sm:grid-cols-2">{rows[0].targets.map(target=><label key={target.platform} className="flex items-center gap-2 rounded-lg border bg-white p-3 text-sm"><input type="checkbox" checked={selected.includes(target.platform)} onChange={event=>setSelected(current=>event.target.checked?[...current,target.platform]:current.filter(key=>key!==target.platform))}/>{target.label}</label>)}</div>
   {rows.map((row,index)=><details key={row.artifact_id} className="min-w-0 rounded-lg border bg-white p-3" open={false}><summary className="cursor-pointer text-sm font-semibold">جاهزية المادة {index+1} · {row.central_approval==='APPROVED'?'اعتماد مركزي محفوظ':'بانتظار الاعتماد'}</summary>
    {row.selection_stale?<p role="alert" className="text-xs text-amber-800">تغيرت المادة منذ حفظ اختيارها. تحقق من النسخ وأعد حفظ الوجهات قبل التنفيذ.</p>:null}
    <details className="my-2"><summary className="text-xs">معاينة النص الأصلي دون تغيير</summary><p dir="auto" className="whitespace-pre-wrap break-words text-sm leading-7">{row.original_text}</p></details>
    {row.targets.map(target=><div key={target.platform} className="space-y-1 border-t py-2 text-xs leading-6"><strong>{target.label} · {target.copy_status==='ORIGINAL_ELIGIBLE'?'الأصل مؤهل مبدئياً':'التجهيز محجوب'}</strong>{target.copy_blockers.map(reason=><p key={reason}>{reason}</p>)}{target.execution_blockers.map(reason=><p key={reason} className="text-slate-600">{reason}</p>)}<p className="text-slate-500">لا إذن تنفيذ من حفظ الاختيار.</p></div>)}
   </details>)}
   <button type="button" disabled={save.isPending||load.isPending} onClick={()=>save.mutate()} className="rounded-lg bg-indigo-700 p-3 text-sm font-bold text-white disabled:opacity-50">حفظ اختيار الوجهات فقط</button>
  </>:null}
  {load.isError||save.isError?<p role="alert" className="break-words text-sm text-rose-700">{load.error?.message??save.error?.message}</p>:null}
  {note?<p role="status" className="text-sm text-emerald-800">{note}</p>:null}
 </section>;
}
