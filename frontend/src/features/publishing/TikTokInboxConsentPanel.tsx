import {useEffect,useRef,useState} from 'react';
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {get,post} from '../../shared/api/client';
type Identity={open_id:string;display_name:string};
type Status={configured:boolean;connection:null|Identity&{state:string;expires_at:string|null;caveat:string};pending:null|{accounts:Identity[]}};
const base='/api/connections/tiktok-inbox';
const stateLabel=(value:string)=>value==='CONNECTED_AT_LAST_CHECK'?'إذن محفوظ من آخر تحقق، لا يثبت نجاح نقل مسودة':value==='RECONNECT_REQUIRED'?'يلزم مراجعة الإذن أو ربطه مجددًا':value==='DISABLED'?'معطل محليًا':'حالة الإذن غير متحققة';
export function TikTokInboxConsentPanel(){
 const qc=useQueryClient(),[reviewed,setReviewed]=useState(false),[choice,setChoice]=useState(''),[remove,setRemove]=useState(false);
 const picker=useRef<HTMLSelectElement>(null);
 const state=useQuery({queryKey:['tiktok-inbox-consent'],queryFn:()=>get<Status>(base),retry:false});
 useEffect(()=>{if(state.data?.pending){picker.current?.scrollIntoView({block:'center'});picker.current?.focus({preventScroll:true});}},[state.data?.pending]);
 const refresh=()=>void qc.invalidateQueries({queryKey:['tiktok-inbox-consent']});
 const start=useMutation({mutationFn:()=>post<{authorization_url:string}>(base+'/start',{reviewed}),onSuccess:d=>window.location.assign(d.authorization_url)});
 const save=useMutation({mutationFn:()=>post(base+'/select',{open_id:choice}),onSuccess:()=>{setChoice('');refresh();}});
 const disconnect=useMutation({mutationFn:()=>post(base+'/disconnect',{}),onSuccess:()=>{setRemove(false);refresh();}});
 const busy=start.isPending||save.isPending||disconnect.isPending,d=state.data;
 return <section id="platform-tiktok-inbox" aria-label="إذن مسودات TikTok التجريبي" className="space-y-3 rounded border p-3"><h3>إذن مسودات TikTok · Sandbox</h3>
 <p>مسار منفصل عن ربط الهوية. الصلاحيتان user.info.basic وvideo.upload تسمحان بالهوية وإرسال محتوى كمسودة عند توافر التنفيذ لاحقًا. هذا الإصدار يحفظ الإذن فقط، ولا ينقل فيديو أو ينشر أو يجدّد رمزًا تلقائيًا. لا يثبت أهلية النشر العام.</p>
 <p>عند تفعيل نقل المسودات لاحقًا، تكمل التحرير والنشر من إشعار الوارد داخل TikTok. لا موافقة على فيديو من هذا الزر، واتصال الهوية السابق لا يُستبدل.</p>
 {d?<><p>{d.configured?'إعداد الإذن التجريبي متاح. يبقى إرسال الفيديو غير متاح.':'إعداد Sandbox للمسودات وعنوان العودة المستقل لم يُراجعا بعد. لا حاجة لإعادة ربط الهوية.'}</p>
 <details><summary>عنوان العودة المستقل</summary><p dir="ltr" className="break-all">{window.location.origin+base+'/callback'}</p></details>
 <label className="block"><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/> أفهم الإذن الجديد وحدود Sandbox. أتابع لعرض موافقة TikTok دون إرسال أي فيديو.</label>
 <button disabled={!reviewed||!d.configured||busy} className="workspace-secondary" onClick={()=>start.mutate()}>عرض إذن مسودات TikTok التجريبي</button>
 {d.pending?<div><p role="status">عاد إذن TikTok ولم يُحفظ بعد. اختر الهوية المطابقة لربطك الأساسي صراحةً ثم احفظ.</p><label>هوية إذن المسودات<select ref={picker} aria-label="هوية إذن مسودات TikTok" value={choice} onChange={e=>setChoice(e.target.value)} className="block w-full rounded border p-2"><option value="">اختر صراحةً</option>{d.pending.accounts.map(x=><option key={x.open_id} value={x.open_id}>{x.display_name} · {x.open_id}</option>)}</select></label><button disabled={!choice||busy} onClick={()=>save.mutate()}>تحقق واحفظ إذن المسودات دون نقل</button></div>:null}
 {d.connection?<div><p>اسم العرض: {d.connection.display_name}</p><p dir="ltr" className="break-all">open_id: {d.connection.open_id}</p><p>حالة الإذن: {stateLabel(d.connection.state)}</p><details><summary>القيمة التقنية للحالة</summary><p dir="ltr">{d.connection.state}</p></details><p>انتهاء الوصول: {d.connection.expires_at?new Date(d.connection.expires_at).toLocaleString('ar-SA'):'غير متحقق'}</p><p>{d.connection.caveat}</p><label className="block"><input type="checkbox" checked={remove} onChange={e=>setRemove(e.target.checked)}/> حذف إذن المسودات المحلي فقط. لا ألغي إذن TikTok ولا أمس ربط الهوية.</label><button disabled={!remove||busy} onClick={()=>disconnect.mutate()}>حذف إذن المسودات المحلي</button></div>:null}</>:null}
 {state.error||start.error||save.error||disconnect.error?<p role="alert">{state.error?.message??start.error?.message??save.error?.message??disconnect.error?.message}</p>:null}
 </section>;
}
