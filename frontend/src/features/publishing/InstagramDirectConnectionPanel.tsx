import {useState} from 'react';
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {get,post} from '../../shared/api/client';
type Account={account_id:string;username:string};
type Status={configured:boolean;missing_configuration:string[];connection:null|Account&{state:string;enabled:boolean;expires_at:string;last_check_at:string|null};pending:null|{accounts:Account[]};source:string};
const base='/api/connections/instagram-direct';
export function InstagramDirectConnectionPanel({ready}:{ready:boolean}){
 const qc=useQueryClient(),[legacy,setLegacy]=useState(false),[app,setApp]=useState(''),[secret,setSecret]=useState(''),[reviewed,setReviewed]=useState(false),[choice,setChoice]=useState(''),[remove,setRemove]=useState(false),[stateConfirm,setStateConfirm]=useState(false);
 const redirect=window.location.origin+base+'/callback';
 const state=useQuery({queryKey:['instagram-direct-connection'],queryFn:()=>get<Status>(base),retry:false});
 const refresh=()=>void qc.invalidateQueries({queryKey:['instagram-direct-connection']});
 const save=useMutation({mutationFn:()=>post(base+'/settings',{app_id:app,app_secret:secret,redirect_uri:redirect,direct_login_reviewed:reviewed}),onSettled:()=>setSecret(''),onSuccess:refresh});
 const start=useMutation({mutationFn:()=>post<{authorization_url:string}>(base+'/start'),onSuccess:d=>window.location.assign(d.authorization_url)});
 const select=useMutation({mutationFn:()=>post(base+'/select',{account_id:choice}),onSuccess:()=>{setChoice('');refresh();}});
 const verify=useMutation({mutationFn:()=>post(base+'/verify'),onSettled:refresh});
 const disconnect=useMutation({mutationFn:()=>post(base+'/disconnect'),onSuccess:()=>{setRemove(false);refresh();}});
 const toggle=useMutation({mutationFn:()=>post(base+'/state',{enabled:state.data?.connection?.enabled===false}),onSuccess:()=>{setStateConfirm(false);refresh();}});
 const busy=[save,start,select,verify,disconnect,toggle].some(x=>x.isPending),data=state.data;
 const error=save.error??state.error??start.error??select.error??verify.error??disconnect.error??toggle.error;
 return <section aria-label="ربط Instagram المباشر" className="space-y-4 rounded-xl border bg-white p-4 text-sm leading-7">
 <h2 className="font-bold">Instagram Login المباشر، للتكاملات القديمة فقط</h2>
 <div role="note" className="rounded border border-amber-300 bg-amber-50 p-3"><p className="font-bold">غير متاح للتطبيقات الجديدة بحسب Meta.</p><p>وجود هذا القسم في Nashr لا يعني أن تطبيقك مؤهل. لا تنشئ تطبيقاً جديداً لحل ذلك، ولا تستخدم إعداد Facebook أو Unified مكانه. للتطبيقات الجديدة راجع Unified ونطاق صلاحياته أولاً.</p><a className="underline" target="_blank" rel="noreferrer" href="https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/migration-guide">قيد Meta الرسمي على التطبيقات الجديدة</a></div>
 <label className="flex items-start gap-2"><input aria-label="إقرار توفر إعداد Instagram Login قديم" type="checkbox" checked={legacy} onChange={e=>setLegacy(e.target.checked)}/> لدي تكامل قديم ويظهر فيه API setup with Instagram login فعلاً، وليس Facebook Login أو Unified.</label>
 <p>دخول عبر Instagram للحساب الاحترافي، دون اكتشاف صفحات Facebook أو إذن إدارة الأعمال والإعلانات. يحفظ هذا المسار هوية مستقلة ولا يستبدل المسارات السابقة. الربط لا ينشر أي مادة.</p>
 <details className="rounded border p-3"><summary className="cursor-pointer font-bold">إعداد Instagram Login المباشر</summary>
 <p>من Meta App Dashboard: Instagram ثم API setup with Instagram login ثم Set up Instagram business login. استخدم Instagram App ID وInstagram App Secret الخاصين بهذا المنتج، لا إعداد Facebook Login أو Unified.</p>
 <form autoComplete="off" className="grid gap-3 md:grid-cols-2" onSubmit={e=>{e.preventDefault();if(legacy)save.mutate();}}>
 <label>Instagram App ID<input aria-label="Instagram App ID المباشر" required dir="ltr" className="block w-full rounded border p-2" value={app} onChange={e=>setApp(e.target.value)}/></label>
 <label>Instagram App Secret، كتابة فقط<input aria-label="Instagram App Secret المباشر" required type="password" autoComplete="new-password" className="block w-full rounded border p-2" value={secret} onChange={e=>setSecret(e.target.value)}/></label>
 <label className="md:col-span-2">عنوان العودة للمسار المباشر<p aria-label="عنوان عودة Instagram المباشر" dir="ltr" className="break-all rounded border p-2">{redirect}</p></label>
 <label className="md:col-span-2 flex items-start gap-2"><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/><span>راجعت إعداد Instagram Login وصلاحيتي instagram_business_basic وinstagram_business_content_publish. أحفظ الإعداد مشفراً دون نشر أو تغيير الربط السابق.</span></label>
 <button className="workspace-secondary" disabled={!legacy||!ready||!reviewed||busy}>حفظ إعداد Instagram المباشر</button></form>
 {save.isSuccess?<p role="status">حُفظ الإعداد مشفراً. لم يُربط حساب ولم يُنشر محتوى.</p>:null}</details>
 {state.isLoading?<p>جارٍ تحميل الربط المباشر...</p>:null}
 {data?<><p role="status">{!data.configured?'إعداد Instagram Login المباشر مطلوب قبل المتابعة.':data.connection?'يوجد حساب محفوظ من آخر تحقق، وليس إذن نشر.':'الإعداد متاح، ولم يُربط حساب بعد.'}</p>
 {data.connection?<div className="space-y-2 rounded border p-3"><p dir="ltr" className="break-all">@{data.connection.username} · {data.connection.account_id}</p><p>{data.connection.state==='DISABLED'?'معطل محلياً':data.connection.state==='RECONNECT_REQUIRED'?'يلزم إعادة الربط':'متصل من آخر تحقق'}</p><p>انتهاء الرمز: <span dir="ltr" className="inline-block">{data.connection.expires_at}</span></p><p>لا تحديث رموز تلقائي ولا تحقق مستمر. لا موصل نشر مفعّل لهذا المسار بعد.</p><button className="workspace-secondary" disabled={busy} onClick={()=>verify.mutate()}>تحقق من الحساب دون نشر</button><label className="block"><input type="checkbox" checked={stateConfirm} onChange={e=>setStateConfirm(e.target.checked)}/> أؤكد {data.connection.enabled?'تعطيل':'تفعيل'} الربط محلياً دون تغيير لدى Instagram.</label><button className="workspace-secondary" disabled={!stateConfirm||busy} onClick={()=>toggle.mutate()}>{data.connection.enabled?'تعطيل الربط محلياً':'تفعيل الربط بعد تحقق حديث'}</button></div>:null}
 {data.pending?<div className="space-y-2 rounded border p-3"><p>راجع الحساب العائد من Instagram ثم أكّد حفظه. لا نختاره تلقائياً.</p><label>الحساب العائد من Instagram<select aria-label="حساب Instagram المباشر" className="block w-full rounded border p-2" value={choice} onChange={e=>setChoice(e.target.value)}><option value="">اختر صراحةً</option>{data.pending.accounts.map(a=><option key={a.account_id} value={a.account_id}>@{a.username} · {a.account_id}</option>)}</select></label><button className="workspace-secondary" disabled={!choice||busy} onClick={()=>select.mutate()}>تحقق واحفظ حساب Instagram دون نشر</button></div>:null}
 <button className="workspace-secondary" disabled={!legacy||!data.configured||busy} onClick={()=>start.mutate()}>المتابعة إلى Instagram مباشرة</button>
 {data.connection||data.pending?<div><label className="block"><input type="checkbox" checked={remove} onChange={e=>setRemove(e.target.checked)}/> حذف الربط المباشر من Nashr فقط، دون إلغاء إذن Instagram أو تغيير المسارات السابقة.</label><button className="workspace-secondary" disabled={!remove||busy} onClick={()=>disconnect.mutate()}>فصل Instagram المباشر محلياً</button></div>:null}
 <a href={data.source} target="_blank" rel="noreferrer" className="underline">متطلبات Instagram Login الرسمية</a></>:null}
 {verify.isSuccess?<p role="status">نجح التحقق من هوية الحساب دون نشر.</p>:null}{select.isSuccess?<p role="status">حُفظ الحساب المختار مشفراً دون نشر أو تغيير المسارات السابقة.</p>:null}{error?<p role="alert">{error.message}</p>:null}
 </section>;
}
