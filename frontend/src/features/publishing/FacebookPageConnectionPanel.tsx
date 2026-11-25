import {FacebookReelPanel} from './FacebookReelPanel';
import {useState} from 'react';
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {get,post} from '../../shared/api/client';
type Page={page_id:string;page_name:string;tasks:string[];token_type:string};
type Status={configured:boolean;missing_configuration:string[];connection:null|Page&{state:string;enabled:boolean;expires_at:string|null;last_check_at:string|null;caveat:string};pending:null|{accounts:Page[]};requirements:string[];source:string};
const base='/api/connections/facebook';
export function FacebookPageConnectionPanel({ready}:{ready:boolean}){
 const qc=useQueryClient();
 const [app,setApp]=useState(''),[secret,setSecret]=useState(''),[config,setConfig]=useState(''),[mode,setMode]=useState(''),[reviewed,setReviewed]=useState(false),[choice,setChoice]=useState(''),[confirm,setConfirm]=useState(false);
 const state=useQuery({queryKey:['facebook-page-connection'],queryFn:()=>get<Status>(base),retry:false});
 const refresh=()=>void qc.invalidateQueries({queryKey:['facebook-page-connection']});
 const save=useMutation({mutationFn:()=>post(base+'/settings',{app_id:app,app_secret:secret,config_id:config,redirect_uri:window.location.origin+base+'/callback',token_mode:mode,config_reviewed:reviewed}),onSettled:()=>setSecret(''),onSuccess:refresh});
 const start=useMutation({mutationFn:()=>post<{authorization_url:string}>(base+'/start'),onSuccess:d=>window.location.assign(d.authorization_url)});
 const select=useMutation({mutationFn:()=>post(base+'/select',{page_id:choice}),onSuccess:()=>{setChoice('');refresh();}});
 const action=useMutation({mutationFn:({kind,body}:{kind:string;body?:object})=>post(base+'/'+kind,body??{}),onSuccess:()=>{setConfirm(false);refresh();},onSettled:refresh});
 const data=state.data,busy=save.isPending||start.isPending||select.isPending||action.isPending;
 return <section id="platform-facebook" aria-label="ربط صفحة Facebook" className="workspace-surface space-y-4 p-5 text-sm leading-7 scroll-mt-24">
 <h2 className="workspace-section-title">Facebook · ربط الصفحة والنشر بقرار منفصل</h2>
 <p>ربط مستقل عن Instagram. اختر صفحة من نتيجة Meta، لا ملفاً شخصياً. لا رسائل اختبار ولا رفع وسائط ولا تفعيل نشر من هذا الربط. تتوفر مسارات النص والصورة وReels من المادة المعتمدة بمراجعة وموافقة مستقلة لكل عملية، ولا يعني وجوده أن الصفحة مربوطة أو جاهزة الآن.</p>
 <details className="workspace-disclosure"><summary>إعداد Facebook Login for Business</summary><div className="space-y-3 p-4"><p>على تطبيق Meta الموجود، استخدم إعداداً منفصلاً للصفحات وصلاحيات pages_show_list وpages_read_engagement وpages_manage_posts. لا تغيّر إعداد Instagram. راجع نوع الرمز الذي اخترته لدى Meta، لا تفترضه من معرف الإعداد.</p><p dir="ltr" className="break-all">{window.location.origin+base+'/callback'}</p><form autoComplete="off" className="grid gap-3 md:grid-cols-2" onSubmit={e=>{e.preventDefault();save.mutate();}}>
 <label>معرف تطبيق Meta<input aria-label="معرف تطبيق Facebook" required dir="ltr" className="block w-full rounded border p-2" value={app} onChange={e=>setApp(e.target.value)}/></label>
 <label>معرف إعداد الصفحات<input aria-label="معرف إعداد Facebook" required dir="ltr" className="block w-full rounded border p-2" value={config} onChange={e=>setConfig(e.target.value)}/></label>
 <label>سر التطبيق، كتابة فقط<input aria-label="سر تطبيق Facebook" type="password" autoComplete="new-password" required className="block w-full rounded border p-2" value={secret} onChange={e=>setSecret(e.target.value)}/></label>
 <label>نوع الرمز لدى Meta<select aria-label="نوع رمز Facebook" required className="block w-full rounded border p-2" value={mode} onChange={e=>setMode(e.target.value)}><option value="">اختر النوع الفعلي</option><option value="USER">User access token</option><option value="SYSTEM_USER">Business Integration System User</option></select></label>
 <label className="md:col-span-2"><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/> راجعت إعداد الصفحات والأذونات ونوع الرمز لدى Meta. حفظ مستقل مشفر، دون تغيير Instagram أو نشر.</label>
 <button className="workspace-secondary" disabled={!ready||!reviewed||!mode||busy}>حفظ إعداد Facebook فقط</button></form></div></details>
 {state.isLoading?<p>جارٍ تحميل ربط Facebook...</p>:null}
 {data?<><p role="status">{!data.configured?'إعداد Facebook مطلوب قبل الدخول.':data.connection?'يوجد ربط صفحة محفوظ من آخر تحقق.':'الإعداد جاهز، لم تُربط صفحة بعد.'}</p>
 {data.connection?<div className="rounded border p-3 space-y-2"><p>الصفحة: {data.connection.page_name} · <span dir="ltr">{data.connection.page_id}</span></p><p>الحالة: {data.connection.state==='DISABLED'?'معطل محلياً':data.connection.state==='RECONNECT_REQUIRED'?'يلزم إعادة تحقق أو ربط':'نجح آخر تحقق، ليست مراقبة مستمرة'}</p><p>{data.connection.caveat}</p><p>آخر تحقق: {data.connection.last_check_at?new Date(data.connection.last_check_at).toLocaleString('ar-SA'):'غير موثق'}</p><p>الانتهاء: {data.connection.expires_at??'لا تاريخ انتهاء موثق، يمكن إلغاء الإذن لدى Meta'}</p><button className="workspace-secondary" disabled={busy} onClick={()=>action.mutate({kind:'verify'})}>تحقق من الصفحة دون نشر</button><label className="block"><input type="checkbox" checked={confirm} onChange={e=>setConfirm(e.target.checked)}/> أفهم أثر تغيير الربط محلياً فقط، دون تغيير Instagram أو إلغاء إذن Meta.</label><button className="workspace-secondary" disabled={!confirm||busy} onClick={()=>action.mutate({kind:'state',body:{enabled:!data.connection?.enabled}})}>{data.connection.enabled?'تعطيل Facebook محلياً':'تفعيل Facebook بعد تحقق حديث'}</button><button className="workspace-secondary" disabled={!confirm||busy} onClick={()=>action.mutate({kind:'disconnect'})}>حذف ربط Facebook المحلي فقط</button></div>:null}
 {data.pending?<div className="rounded border p-3 space-y-2"><label>اختر صفحة Facebook<select aria-label="صفحة Facebook" className="block w-full rounded border p-2" value={choice} onChange={e=>setChoice(e.target.value)}><option value="">اختر صراحةً</option>{data.pending.accounts.map(p=><option key={p.page_id} value={p.page_id}>{p.page_name} · {p.page_id}</option>)}</select></label><p>التحقق يعيد فحص هوية الصفحة ومهمة CREATE_CONTENT. لن نستبدل ربطاً قبل اختيارك.</p><button className="workspace-secondary" disabled={!choice||busy} onClick={()=>select.mutate()}>تحقق واحفظ الصفحة دون نشر</button></div>:null}
 <button className="workspace-secondary" disabled={!data.configured||busy} onClick={()=>start.mutate()}>المتابعة إلى Meta لربط Facebook</button>
 <details><summary>المتطلبات والحدود</summary>{data.requirements.map(p=><p key={p}>{p}</p>)}<a className="underline" href={data.source} target="_blank" rel="noreferrer">مصدر Meta الرسمي</a></details></>:null}
 {save.isSuccess?<p role="status">حُفظ إعداد Facebook مشفراً، لم يتغير Instagram ولم تُربط صفحة بعد.</p>:null}
 {select.isSuccess||action.isSuccess?<p role="status">اكتملت العملية دون نشر أو رسائل أو رفع وسائط.</p>:null}
 {state.error||save.error||start.error||select.error||action.error?<p role="alert">{state.error?.message??save.error?.message??start.error?.message??select.error?.message??action.error?.message}</p>:null}
 <FacebookReelPanel/>
 </section>;
}
