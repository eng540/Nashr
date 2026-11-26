import {TikTokRequirementsPanel} from './TikTokRequirementsPanel';
import {useEffect,useRef,useState} from 'react';
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {get,post} from '../../shared/api/client';
type Identity={open_id:string;display_name:string};
type Status={configured:boolean;connection:null|Identity&{state:string;expires_at:string;caveat:string};pending:null|{accounts:Identity[]}};
const base='/api/connections/tiktok';
export function TikTokConnectionPanel(){
 const qc=useQueryClient(),[client,setClient]=useState(''),[secret,setSecret]=useState(''),[reviewed,setReviewed]=useState(false),[choice,setChoice]=useState(''),[remove,setRemove]=useState(false);
 const identitySelect=useRef<HTMLSelectElement>(null);
 const state=useQuery({queryKey:['tiktok-identity'],queryFn:()=>get<Status>(base),retry:false});
 useEffect(()=>{if(state.data?.pending){identitySelect.current?.scrollIntoView({block:'center'});identitySelect.current?.focus({preventScroll:true});}},[state.data?.pending]);
 const refresh=()=>void qc.invalidateQueries({queryKey:['tiktok-identity']});
 const save=useMutation({mutationFn:()=>post(base+'/settings',{client_key:client,client_secret:secret,redirect_uri:window.location.origin+base+'/callback',config_reviewed:reviewed}),onSettled:()=>setSecret(''),onSuccess:refresh});
 const start=useMutation({mutationFn:()=>post<{authorization_url:string}>(base+'/start'),onSuccess:d=>window.location.assign(d.authorization_url)});
 const select=useMutation({mutationFn:()=>post(base+'/select',{open_id:choice}),onSuccess:refresh});
 const action=useMutation({mutationFn:(kind:string)=>post(base+'/'+kind,{}),onSuccess:()=>{setRemove(false);refresh();}});
 const busy=save.isPending||start.isPending||select.isPending||action.isPending,d=state.data;
 return <section id="platform-tiktok" aria-label="ربط هوية TikTok" className="workspace-surface space-y-4 p-5 text-sm leading-7"><h2 className="workspace-section-title">TikTok · ربط الهوية فقط</h2><p>Login Kit بصلاحية user.info.basic. لا رفع أو نشر أو قراءة مقاطع. اسم العرض ليس اسم المستخدم @. قبول التطبيق أو Sandbox لدى TikTok مطلوب؛ الربط لا يثبت أهلية النشر.</p>
 <details><summary>إعداد تطبيق TikTok</summary><p dir="ltr" className="break-all">{window.location.origin+base+'/callback'}</p><form autoComplete="off" className="grid gap-3 md:grid-cols-2" onSubmit={e=>{e.preventDefault();save.mutate();}}><label>Client key<input aria-label="TikTok client key" required value={client} onChange={e=>setClient(e.target.value)} className="block w-full rounded border p-2" dir="ltr"/></label><label>Client secret، كتابة فقط<input aria-label="TikTok client secret" required type="password" autoComplete="new-password" value={secret} onChange={e=>setSecret(e.target.value)} className="block w-full rounded border p-2"/></label><label className="md:col-span-2"><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/> راجعت Web Login Kit وعنوان العودة وصلاحية الهوية فقط. لا أنشئ تطبيقاً أو أقبل شروطاً من هذا الحفظ.</label><button disabled={busy||!reviewed} className="workspace-secondary">حفظ إعداد TikTok مشفراً</button></form></details>
 {d?<><p>{d.configured?'إعداد محفوظ، تابع الإذن لدى TikTok.':'لم يكتمل إعداد التطبيق.'}</p>{d.connection?<div className="rounded border p-3"><p>اسم العرض: {d.connection.display_name}</p><p dir="ltr" className="break-all">open_id: {d.connection.open_id}</p><p>الحالة: {d.connection.state}</p><p>انتهاء رمز الوصول: {new Date(d.connection.expires_at).toLocaleString('ar-SA')}</p><p>{d.connection.caveat}</p><button disabled={busy} className="workspace-secondary" onClick={()=>action.mutate('verify')}>تحقق من هوية TikTok دون نشر</button><label className="block"><input type="checkbox" checked={remove} onChange={e=>setRemove(e.target.checked)}/> أحذف الربط المحلي فقط، لا ألغي إذن TikTok خارج Nashr.</label><button disabled={!remove||busy} onClick={()=>action.mutate('disconnect')}>حذف الربط المحلي</button></div>:null}
 {d.pending?<div><p role="status">وصل إذن الهوية من TikTok. الربط لم يُحفظ بعد: اختر الحساب ثم اضغط التحقق والحفظ. لا رفع أو نشر.</p><label>اختر الهوية التي أذن بها TikTok<select ref={identitySelect} aria-label="هوية TikTok" value={choice} onChange={e=>setChoice(e.target.value)} className="block w-full rounded border p-2"><option value="">اختر صراحةً</option>{d.pending.accounts.map(x=><option key={x.open_id} value={x.open_id}>{x.display_name} · {x.open_id}</option>)}</select></label><button disabled={!choice||busy} className="workspace-secondary" onClick={()=>select.mutate()}>تحقق واحفظ هوية TikTok دون نشر</button></div>:null}
 <button disabled={!d.configured||busy} className="workspace-secondary" onClick={()=>start.mutate()}>المتابعة إلى TikTok لربط الهوية فقط</button></>:null}
 {state.error||save.error||start.error||select.error||action.error?<p role="alert">{state.error?.message??save.error?.message??start.error?.message??select.error?.message??action.error?.message}</p>:null}
 <TikTokRequirementsPanel/>
 </section>;
}
