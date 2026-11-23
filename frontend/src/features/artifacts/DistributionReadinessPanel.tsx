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
  <div><h4 className="text-sm font-bold">اعتماد واحد، وجهات تختارها</h4><p className="mt-1 text-xs leading-6">المحتوى يُعتمد مرة واحدة. نحافظ على الأصل دون قص، ثم نفصل أهلية النسخة عن ربط الحساب وإذن النشر.</p></div>
  <button type="button" disabled={!ids.length||load.isPending||save.isPending} onClick={()=>load.mutate()} className="rounded-lg border bg-white p-2 text-sm font-semibold disabled:opacity-40">{load.isPending?'فحص الجاهزية...':`فحص جاهزية واختيار المنصات (${ids.length})`}</button>
  {current?<>
   <p className="text-xs leading-6">هذه قائمة الوجهات المرغوبة، وليست أمراً بالنشر. يمكنك حفظ رغبتك لمنصة محجوبة ثم استكمال متطلباتها. المواعيد والمنشورات القائمة لا تتغير.</p>
   <div className="flex flex-wrap gap-3 text-xs"><button type="button" disabled={save.isPending} onClick={()=>{setSelected(rows[0].targets.map(target=>target.platform));setNote('');}} className="underline">تحديد جميع المنصات</button><button type="button" disabled={save.isPending} onClick={()=>{setSelected([]);setNote('');}} className="underline">إلغاء جميع المنصات</button></div>
   <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">{rows[0].targets.map(target=>{
    const eligible=rows.filter(row=>row.targets.find(item=>item.platform===target.platform)?.copy_status==='ORIGINAL_ELIGIBLE').length;
    return <label key={target.platform} className={`flex min-w-0 items-start gap-2 rounded-lg border p-2 text-sm ${selected.includes(target.platform)?'border-indigo-400 bg-indigo-50':'border-slate-200 bg-white'}`}><input type="checkbox" disabled={save.isPending} aria-label={target.label} checked={selected.includes(target.platform)} onChange={event=>{setSelected(current=>event.target.checked?[...current,target.platform]:current.filter(key=>key!==target.platform));setNote('');}} className="mt-1"/><span className="min-w-0"><span className="block font-semibold">{target.label}</span><span className={`block text-[11px] ${eligible?'text-emerald-700':'text-amber-800'}`}>{eligible===rows.length?'الأصل مؤهل مبدئياً':eligible?`${eligible}/${rows.length} مؤهل مبدئياً`:'التجهيز محجوب'}</span></span></label>;
   })}</div>
   {ids.length>1?<p className="text-xs leading-6">بدأنا باختيار أول مادة. الحفظ يطبق قائمتك على {ids.length} مواد فقط. عدّل أي مادة منفردة لاحقاً للاستثناء.</p>:null}
   <button type="button" disabled={save.isPending||load.isPending} onClick={()=>save.mutate()} className="rounded-lg bg-indigo-700 px-3 py-2 text-sm font-bold text-white disabled:opacity-50">{save.isPending?'حفظ الاختيار...':'حفظ اختيار الوجهات فقط'}</button>
   {rows.map((row,index)=><details key={row.artifact_id} className="min-w-0 rounded-lg border border-slate-200 bg-white p-3"><summary className="cursor-pointer text-xs font-semibold">تفاصيل المادة {index+1} · {row.central_approval==='APPROVED'?'اعتماد مركزي محفوظ':'بانتظار الاعتماد'}</summary>
    {row.selection_stale?<p role="alert" className="text-xs text-amber-800">تغيرت المادة منذ الاختيار. حدّث المعاينة وأعد حفظ الوجهات.</p>:null}
    <details className="my-2"><summary className="text-xs">معاينة النص الأصلي دون تغيير</summary><p dir="auto" className="max-h-64 overflow-y-auto whitespace-pre-wrap break-words text-sm leading-7">{row.original_text}</p></details>
    {row.targets.map(target=><details key={target.platform} className="border-t py-2 text-xs leading-6"><summary className="cursor-pointer"><strong>{target.label}</strong> · {target.copy_blockers[0]??'الأصل مؤهل مبدئياً؛ تابع فحص الوسائط والوجهة'}</summary><div className="space-y-1 pt-1 text-slate-600">{target.copy_blockers.slice(1).map(reason=><p key={reason}>{reason}</p>)}{target.execution_blockers.map(reason=><p key={reason}>{reason}</p>)}</div></details>)}
   </details>)}
  </>:null}
  {load.isError||save.isError?<p role="alert" className="break-words text-sm text-rose-700">{load.error?.message??save.error?.message}</p>:null}
  {note&&current?<p role="status" className="text-xs leading-6 text-emerald-800">{note}</p>:null}
 </section>;
}
