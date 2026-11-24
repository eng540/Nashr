import {useState} from 'react';
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {get,post} from '../../shared/api/client';
type Status={configured:boolean;missing_configuration:string[];connection:null|{username:string;state:string;expires_at:string|null;caveat:string};pending:null|{accounts:{account_id:string;username:string}[]};requirements:string[];source:string};
const base='/api/connections/instagram';
export function InstagramConnectionPanel(){
 const client=useQueryClient();const [choice,setChoice]=useState('');const [confirm,setConfirm]=useState(false);
 const state=useQuery({queryKey:['instagram-connection'],queryFn:()=>get<Status>(base),retry:false});
 const start=useMutation({mutationFn:()=>post<{authorization_url:string}>(base+'/start'),onSuccess:data=>window.location.assign(data.authorization_url)});
 const select=useMutation({mutationFn:()=>post(base+'/select',{account_id:choice}),onSuccess:()=>{setChoice('');void client.invalidateQueries({queryKey:['instagram-connection']});}});
 const disconnect=useMutation({mutationFn:()=>post(base+'/disconnect'),onSuccess:()=>{setConfirm(false);void client.invalidateQueries({queryKey:['instagram-connection']});}});
 const data=state.data;const busy=start.isPending||select.isPending||disconnect.isPending;
 return <section aria-label="ربط Instagram الرسمي" className="rounded-xl border bg-white p-4 space-y-3 text-sm leading-7"><h2 className="font-bold">ربط Instagram الرسمي</h2><p>تدخل أنت لدى Meta من جهازك وتراجع الحساب والصلاحيات. لا تدخل كلمة مرور Instagram في Nashr ولا ترسلها لنا. الربط ليس نشراً ولا إذناً بالتنفيذ.</p>
 {state.isLoading?<p>تحميل حالة الربط...</p>:null}
 {data?<><p role="status">{!data.configured?'غير مهيأ، إعداد تطبيق Meta مطلوب قبل إتاحة رابط الدخول.':data.connection?'يوجد ربط محفوظ، لا موصل نشر مفعّل.':'إعداد الخادم متاح، والحساب لم يُربط بعد.'}</p>
 {data.connection?<div className="rounded border p-2"><p>الحساب المحفوظ: <span dir="ltr">@{data.connection.username}</span></p><p>{data.connection.state==='RECONNECT_REQUIRED'?'يلزم إعادة الربط، الإعداد أو الصلاحية تغير.':'آخر تحقق عند الربط، وليس فحصاً حياً الآن.'}</p><p>{data.connection.caveat}</p>{data.connection.expires_at?<p>انتهاء الصلاحية المسجل: {data.connection.expires_at}</p>:<p>لا تاريخ انتهاء موثق هنا؛ قد يلغي Meta الصلاحية.</p>}</div>:null}
 {data.pending?<div className="rounded border p-3"><p>عاد Meta بالحسابات التالية. اختر حساباً صراحةً؛ لن نستبدل الربط السابق حتى تؤكد.</p><label>حساب Instagram المصرح به<select className="block w-full rounded border p-2" aria-label="حساب Instagram المصرح به" value={choice} onChange={e=>setChoice(e.target.value)}><option value="">اختر الحساب</option>{data.pending.accounts.map(a=><option key={a.account_id} value={a.account_id}>@{a.username} · {a.account_id}</option>)}</select></label><button disabled={!choice||busy} className="rounded border p-2" onClick={()=>select.mutate()}>حفظ ربط الحساب المختار دون نشر</button></div>:null}
 <button disabled={!data.configured||busy} className="rounded border p-2 disabled:opacity-50" onClick={()=>start.mutate()}>{start.isPending?'فتح Meta...':'المتابعة إلى Meta لربط حساب'}</button>
 {data.connection||data.pending?<div><label className="block"><input type="checkbox" checked={confirm} onChange={e=>setConfirm(e.target.checked)}/> أريد حذف الربط والرمز المحفوظ من Nashr فقط. لا يلغي هذا صلاحية التطبيق لدى Meta؛ يمكن إزالتها من إعدادات Meta.</label><button disabled={!confirm||busy} className="rounded border p-2" onClick={()=>disconnect.mutate()}>فصل الربط محلياً</button></div>:null}
 <details><summary>متطلبات الإعداد وحدود هذه المرحلة</summary>{data.requirements.map(x=><p key={x}>{x}</p>)}{data.missing_configuration.length?<><p>إعدادات خادم ناقصة، وليست كلمات مرور حسابك:</p><ul dir="ltr" className="break-all">{data.missing_configuration.map(x=><li key={x}>{x}</li>)}</ul></>:null}<p>لا رفع أو نشر أو تعديل حساب أو جدول في هذه المرحلة. عند انتهاء الصلاحية يلزم ربط جديد؛ لا تجديد خلفي أو ادعاء تحقق مستمر.</p><a className="break-all underline" href={data.source} target="_blank" rel="noreferrer">متطلبات Meta الرسمية</a></details></>:null}
 {state.isError||start.isError||select.isError||disconnect.isError?<p role="alert">{state.error?.message??start.error?.message??select.error?.message??disconnect.error?.message}</p>:null}
 </section>;
}
