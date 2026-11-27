import {useRef,useState} from 'react';
import {useMutation} from '@tanstack/react-query';
import {genericArtifactsApi,type DistributionReadiness} from '../../shared/api/artifactsApi';

export function DistributionReadinessPanel({ids,onReview}:{ids:string[];onReview?:(platform:string)=>void}) {
 const [rows,setRows]=useState<DistributionReadiness[]>([]);
 const [selected,setSelected]=useState<string[]>([]);
 const [note,setNote]=useState('');
 const [mode,setMode]=useState<'replace'|'add'|'remove'>(ids.length>1?'add':'replace');
 const identity=ids.join(',');
 const activeScope=useRef({identity});if(activeScope.current.identity!==identity)activeScope.current={identity};
 const [loadedIdentity,setLoadedIdentity]=useState('');
 const [loadedScope,setLoadedScope]=useState<{identity:string}|null>(null);
 const load=useMutation({mutationFn:async({requestedIds}:{requestedIds:string[];scope:{identity:string}})=>Promise.all(requestedIds.map(id=>genericArtifactsApi.readiness(id))),onSuccess:(data,{requestedIds,scope})=>{
  const requestedIdentity=requestedIds.join(',');
  if(activeScope.current!==scope)return;
  if(data.length!==requestedIds.length||data.some((row,index)=>row.artifact_id!==requestedIds[index])){setRows([]);setLoadedIdentity('');return;}
  setRows(data);setSelected(requestedIds.length>1?[]:data[0]?.targets.filter(target=>target.selected).map(target=>target.platform)??[]);setMode(requestedIds.length>1?'add':'replace');setLoadedIdentity(requestedIdentity);setLoadedScope(scope);setNote('');
 }});
 const save=useMutation({mutationFn:({requestedIds,reviewedRows,platforms,saveMode}:{requestedIds:string[];reviewedRows:DistributionReadiness[];platforms:string[];saveMode:typeof mode;scope:{identity:string}})=>genericArtifactsApi.saveDistribution({artifact_ids:requestedIds,platforms,mode:saveMode,selection_versions:Object.fromEntries(reviewedRows.map(row=>[row.artifact_id,row.selection_version])),fingerprints:Object.fromEntries(reviewedRows.map(row=>[row.artifact_id,row.source_fingerprint]))}),onSuccess:(result,request)=>{
  if(activeScope.current!==request.scope)return;
  const ordered=request.requestedIds.map(id=>result.items.find(row=>row.artifact_id===id));
  if(result.items.length!==request.requestedIds.length||new Set(result.items.map(row=>row.artifact_id)).size!==result.items.length||ordered.some(row=>!row)){setRows([]);setLoadedIdentity('');return;}
  setRows(ordered as DistributionReadiness[]);setNote(`حُفظ اختيار ${result.saved} مادة. لم تُنشأ مسودات أو جداول ولم يُرسل شيء.`);
 }});
 const current=loadedScope===activeScope.current&&loadedIdentity===identity&&rows.length===ids.length&&rows.every((row,index)=>row.artifact_id===ids[index]);
 return <section className="space-y-3 rounded-xl border border-indigo-200 bg-indigo-50/50 p-3" aria-label={ids.length===1?`جاهزية توزيع ${ids[0]}`:'جاهزية توزيع الدفعة'}>
  <div><h4 className="text-sm font-bold">اعتماد واحد، وجهات تختارها</h4><p className="mt-1 text-xs leading-6">المحتوى يُعتمد مرة واحدة. نحافظ على الأصل دون قص، ثم نفصل أهلية النسخة عن ربط الحساب وإذن النشر.</p></div>
  <button type="button" disabled={!ids.length||load.isPending||save.isPending} onClick={()=>{setLoadedIdentity('');setNote('');load.mutate({requestedIds:[...ids],scope:activeScope.current});}} className="rounded-lg border bg-white p-2 text-sm font-semibold disabled:opacity-40">{load.isPending?'فحص الجاهزية...':`فحص جاهزية واختيار المنصات (${ids.length})`}</button>
  {current?<>
   {rows.some(row=>row.central_approval!=="APPROVED")?<p role="status" className="rounded border border-amber-200 bg-amber-50 p-3 text-xs leading-6">ابدأ بقرار مراجعة المادة أعلاه. عدم الاعتماد يحجب التجهيز لكل المنصات؛ حفظ الوجهات هنا يحفظ رغبتك فقط ولا يتجاوز هذا الشرط.</p>:null}
   <p className="text-xs leading-6">هذه قائمة الوجهات المرغوبة، وليست أمراً بالنشر. يمكنك حفظ رغبتك لمنصة محجوبة ثم استكمال متطلباتها. المواعيد والمنشورات القائمة لا تتغير.</p>
   {ids.length>1?<label className="block text-sm font-semibold">طريقة تعديل الدفعة<select aria-label="طريقة تعديل وجهات الدفعة" value={mode} disabled={save.isPending} onChange={event=>{setMode(event.target.value as typeof mode);setSelected([]);setNote('');}} className="mt-1 block w-full rounded border bg-white p-2"><option value="add">إضافة منصات مع إبقاء اختيارات كل مادة</option><option value="remove">إزالة منصات مع إبقاء بقية الاختيارات</option><option value="replace">استبدال قائمة كل مادة بالقائمة المحددة</option></select></label>:null}
   <div className="flex flex-wrap gap-3 text-xs"><button type="button" disabled={save.isPending} onClick={()=>{setSelected(rows[0].targets.map(target=>target.platform));setNote('');}} className="underline">تحديد جميع المنصات</button><button type="button" disabled={save.isPending} onClick={()=>{setSelected([]);setNote('');}} className="underline">إلغاء جميع المنصات</button></div>
   <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">{rows[0].targets.map(target=>{
    const selectedCount=rows.filter(row=>row.targets.find(item=>item.platform===target.platform)?.selected).length;
    const eligible=rows.filter(row=>row.targets.find(item=>item.platform===target.platform)?.copy_status==='ORIGINAL_ELIGIBLE'||row.targets.find(item=>item.platform===target.platform)?.copy_status==='FIELDS_VALIDATED').length;
    return <label key={target.platform} className={`flex min-w-0 items-start gap-2 rounded-lg border p-2 text-sm ${selected.includes(target.platform)?'border-indigo-400 bg-indigo-50':'border-slate-200 bg-white'}`}><input type="checkbox" disabled={save.isPending} aria-label={target.label} checked={selected.includes(target.platform)} onChange={event=>{setSelected(current=>event.target.checked?[...current,target.platform]:current.filter(key=>key!==target.platform));setNote('');}} className="mt-1"/><span className="min-w-0"><span className="block font-semibold">{target.label}</span>{ids.length>1?<span className="block text-[11px] text-slate-600">مختارة حالياً {selectedCount}/{rows.length}</span>:null}<span className={`block text-[11px] ${eligible?'text-emerald-700':'text-amber-800'}`}>{eligible===rows.length?'الحقول مقبولة مبدئياً':eligible?`${eligible}/${rows.length} مؤهل مبدئياً`:rows.some(row=>row.central_approval!=='APPROVED')?'راجع المادة واعتمدها أولاً':'متطلبات ناقصة، افتح التفاصيل'}</span></span></label>;
   })}</div>
   {ids.length>1?<p className="text-xs leading-6">{mode==='replace'?'تنبيه: الاستبدال يمحو اختلافات الوجهات بين المواد المحددة. القائمة الفارغة تلغي جميع وجهاتها.':mode==='add'?'سنضيف المنصات المؤشرة فقط. تبقى اختيارات كل مادة الأخرى واستثناءاتها كما هي.':'سنزيل المنصات المؤشرة فقط. تبقى بقية وجهات كل مادة كما هي.'} النطاق: {ids.length} مواد فقط.</p>:null}
   <button type="button" disabled={save.isPending||load.isPending||(mode!=='replace'&&!selected.length)} onClick={()=>{if(current)save.mutate({requestedIds:[...ids],reviewedRows:rows,platforms:[...selected],saveMode:mode,scope:activeScope.current});}} className="rounded-lg bg-indigo-700 px-3 py-2 text-sm font-bold text-white disabled:opacity-50">{save.isPending?'حفظ الاختيار...':'حفظ اختيار الوجهات فقط'}</button>
   {ids.length===1&&rows[0].central_approval==='APPROVED'&&onReview?<nav aria-label="مراجعة نسخ المادة دون تغيير الوجهات" className="space-y-2 rounded-lg border border-slate-200 bg-white p-3"><h5 className="text-sm font-bold">راجع نسخة منصة</h5><p className="text-xs leading-6 text-slate-600">فتح النسخة المحفوظة فقط. لا يحدد وجهة ولا يحفظ أو يجهز أو ينشر شيئاً. قبول الحقول لا يثبت ربط الحساب أو جاهزية النشر؛ راجع المتطلبات داخل المسار.</p><div className="grid grid-cols-2 gap-2 sm:grid-cols-3">{rows[0].targets.map(target=><button key={target.platform} type="button" onClick={()=>onReview(target.platform)} className="min-w-0 rounded border border-slate-300 bg-white px-3 py-2 text-sm font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-700">مراجعة نسخة {target.label}</button>)}</div></nav>:null}
   {rows.map((row,index)=><details key={row.artifact_id} className="min-w-0 rounded-lg border border-slate-200 bg-white p-3"><summary className="cursor-pointer text-xs font-semibold">تفاصيل المادة {index+1} · {row.central_approval==='APPROVED'?'اعتماد مركزي محفوظ':'بانتظار الاعتماد'}</summary>
    {row.selection_stale?<p role="alert" className="text-xs text-amber-800">تغيرت المادة منذ الاختيار. حدّث المعاينة وراجع الوجهات. في الدفعة استخدم الاستبدال الصريح بعد المراجعة.</p>:null}
    <details className="my-2"><summary className="text-xs">معاينة النص الأصلي دون تغيير</summary><p dir="auto" className="max-h-64 overflow-y-auto whitespace-pre-wrap break-words text-sm leading-7">{row.original_text}</p></details>
    {row.targets.map(target=><details key={target.platform} className="border-t py-2 text-xs leading-6"><summary className="cursor-pointer"><strong>{target.label}</strong> · {target.copy_blockers[0]??'الأصل مؤهل مبدئياً؛ تابع فحص الوسائط والوجهة'}</summary><div className="space-y-1 pt-1 text-slate-600">{target.copy_blockers.slice(1).map(reason=><p key={reason}>{reason}</p>)}{target.execution_blockers.map(reason=><p key={reason}>{reason}</p>)}{onReview&&row.central_approval==='APPROVED'?<button type="button" onClick={()=>onReview(target.platform)} className="rounded border bg-indigo-50 px-3 py-2 font-bold">فتح نسخة {target.label} ومسار مراجعتها دون نشر</button>:null}</div></details>)}
   </details>)}
  </>:null}
  {load.isError||save.isError?<p role="alert" className="break-words text-sm text-rose-700">{load.error?.message??save.error?.message}</p>:null}
  {note&&current?<p role="status" className="text-xs leading-6 text-emerald-800">{note}</p>:null}
 </section>;
}
