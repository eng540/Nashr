import {useState} from 'react';
import {useMutation} from '@tanstack/react-query';
import {post} from '../../shared/api/client';
import type {CentralPlatformCopy} from '../../shared/api/artifactsApi';
type Proposal={state:string;reason:string;fields:CentralPlatformCopy['fields'];suggestion_id?:string;copy_version:number;source_fingerprint:string;blockers?:string[]};
export function CopySuggestionsPanel({id,copy,disabled,onApplied}:{id:string;copy:CentralPlatformCopy;disabled:boolean;onApplied:()=>void}){
 const [confirmed,setConfirmed]=useState(false);
 const labels={title:'العنوان',description:'الوصف والمطلع',tags:'الوسوم',alt_text:'النص البديل'};
 const showFields=(fields:CentralPlatformCopy['fields'])=><dl className="space-y-2">{(Object.keys(labels) as Array<keyof typeof labels>).map(key=><div key={key}><dt className="font-bold text-slate-500">{labels[key]}</dt><dd dir="auto" className="whitespace-pre-wrap break-words rounded border p-2">{(Array.isArray(fields[key])?(fields[key] as string[]).join('، '):fields[key])||'فارغ'}</dd></div>)}</dl>;
 const request=useMutation({mutationFn:()=>post<Proposal>(`/api/artifacts/${id}/platform-copies/${copy.platform}/suggestions`,{version:copy.version,current_source_fingerprint:copy.current_source_fingerprint}),onSuccess:()=>setConfirmed(false)});
 const proposal=request.data;
 const apply=useMutation({mutationFn:()=>post(`/api/artifacts/${id}/platform-copies/${copy.platform}/suggestions/apply`,{suggestion_id:proposal!.suggestion_id,version:copy.version,current_source_fingerprint:copy.current_source_fingerprint,confirmed}),onSuccess:onApplied});
 return <details className="rounded border bg-white p-3" aria-label="اقتراحات النسخة الاختيارية"><summary className="cursor-pointer font-bold">اقتراح عنوان ومطلع ووصف ووسوم · اختياري</summary>
 <p>الخدمة الحية غير مفعلة في هذه المرحلة حتى التحقق من الإذن والتكلفة. وجود إعداد مزود لا يعني تشغيله. لا إرسال للمصدر إلى مزود ولا تغيير للأصل أو الاعتماد أو التوزيع. يمكنك متابعة التحرير يدوياً.</p>
 <button type="button" disabled={disabled||request.isPending||copy.source_stale} onClick={()=>request.mutate()} className="rounded border p-2 disabled:opacity-40">التحقق من إتاحة الاقتراحات دون توليد حي</button>
 {proposal?<div role="status"><p>{proposal.reason}</p>{proposal.state==='PROPOSED'&&proposal.suggestion_id?<><p>راجع النصين كاملين. لا يضاف المطلع أو الوسم تلقائياً خارج النص المقترح. لا نص بديل من وسيط غير مشاهد.</p><div className="grid gap-3 md:grid-cols-2"><section><h4 className="font-bold">المحفوظ قبل التطبيق</h4>{showFields(copy.fields)}</section><section><h4 className="font-bold">الاقتراح الكامل</h4>{showFields(proposal.fields)}</section></div>{proposal.blockers?.map(b=><p key={b}>{b}</p>)}<label className="block"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/> راجعت الحقول كاملة وأريد تطبيقها على هذه المنصة فقط دون نشر</label><button type="button" disabled={!confirmed||disabled||apply.isPending} onClick={()=>apply.mutate()} className="rounded border p-2 disabled:opacity-40">تطبيق الاقتراح على النسخة فقط</button></>:null}</div>:null}
 {request.error||apply.error?<p role="alert">{request.error?.message??apply.error?.message}</p>:null}
 </details>;
}
