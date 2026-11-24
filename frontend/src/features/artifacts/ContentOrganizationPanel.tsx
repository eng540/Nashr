import {useState} from 'react';
import {useMutation,useQueryClient} from '@tanstack/react-query';
import {post} from '../../shared/api/client';
import type {GenericReviewableArtifact} from '../../shared/api/artifactsApi';

export function ContentOrganizationPanel({items}:{items:GenericReviewableArtifact[]}){
 const qc=useQueryClient();const single=items.length===1;const current=single?items[0].organization:null;
 const [title,setTitle]=useState(current?.title??''),[series,setSeries]=useState(current?.series??''),[category,setCategory]=useState(current?.category??'');
 const [useSeries,setUseSeries]=useState(single),[useCategory,setUseCategory]=useState(single),[confirmed,setConfirmed]=useState(false);
 const save=useMutation({mutationFn:()=>{
  const fields={...(single?{title}:{}),...(useSeries?{series}:{}),...(useCategory?{category}:{})};
  if(!Object.keys(fields).length||!confirmed)throw new Error('اختر حقول الدفعة وراجع أثرها أولاً.');
  return post<{updated:number}>('/api/artifacts/organization',{artifact_ids:items.map(i=>i.id),fields,versions:Object.fromEntries(items.map(i=>[i.id,i.organization?.version??0]))});
 },onSuccess:()=>{setConfirmed(false);void qc.invalidateQueries({queryKey:['generic-artifacts']});}});
 return <details className="rounded-xl border bg-slate-50 p-3 text-sm leading-7" aria-label={single?'تنظيم المادة':'تنظيم الدفعة'}><summary className="cursor-pointer font-bold">{single?'تنظيم المادة: العنوان والسلسلة والتصنيف':`تنظيم المحدد (${items.length}): السلسلة والتصنيف`}</summary>
 <p>بيانات فهرسة فقط. لا تغيّر نص الأصل أو وصف النشر أو اعتماد المادة أو نسخ المنصات أو الجداول. عنوان الفهرسة لا يُنسخ تلقائياً إلى عنوان منصة.</p>
 <form className="mt-2 grid gap-3 md:grid-cols-2" onSubmit={e=>{e.preventDefault();save.mutate();}}>
 {single?<label className="md:col-span-2">عنوان الفهرسة<input aria-label="عنوان الفهرسة" maxLength={500} value={title} onChange={e=>{setTitle(e.target.value);setConfirmed(false);}} className="block w-full rounded border p-2"/></label>:null}
 <div>{!single?<label className="block"><input type="checkbox" checked={useSeries} onChange={e=>{setUseSeries(e.target.checked);setConfirmed(false);}}/> تطبيق السلسلة على المحدد</label>:null}<label>السلسلة<input aria-label="سلسلة الفهرسة" disabled={!useSeries} maxLength={200} value={series} onChange={e=>{setSeries(e.target.value);setConfirmed(false);}} className="block w-full rounded border p-2 disabled:opacity-40"/></label></div>
 <div>{!single?<label className="block"><input type="checkbox" checked={useCategory} onChange={e=>{setUseCategory(e.target.checked);setConfirmed(false);}}/> تطبيق التصنيف على المحدد</label>:null}<label>التصنيف<input aria-label="تصنيف الفهرسة" disabled={!useCategory} maxLength={200} value={category} onChange={e=>{setCategory(e.target.value);setConfirmed(false);}} className="block w-full rounded border p-2 disabled:opacity-40"/></label></div>
 <p className="md:col-span-2 text-xs">الحقل المختار الفارغ يمسح تسمية الفهرسة المحفوظة فقط، وتعود تسمية المصدر إن وجدت. الحقول غير المختارة لا تتغير. لا استنتاج لسلسلة جديدة أو نقل ملفات.</p>
 <label className="md:col-span-2"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/> راجعت تنظيم {items.length} مادة، دون تغيير المحتوى أو النشر</label>
 <button disabled={!confirmed||save.isPending||items.length===0||items.length>100} className="rounded border bg-white p-2 disabled:opacity-40">حفظ بيانات الفهرسة</button></form>
 {save.isSuccess?<p role="status">حُفظ تنظيم {save.data.updated} مادة دون تغيير المحتوى أو اعتماداته أو جدوله.</p>:null}{save.error?<p role="alert">{save.error.message}</p>:null}</details>;
}
