import {useState} from 'react';
export const nativeTypes=['POLL','LOCATION','LIVE_LOCATION','VENUE','CONTACT','DICE'];
export const blankNative=(type:string)=>({type,...(type==='POLL'?{question:'',options:['',''],allows_multiple_answers:false}:['LOCATION','LIVE_LOCATION','VENUE'].includes(type)?{latitude:'',longitude:'',...(type==='LIVE_LOCATION'?{live_period:60}:{}),...(type==='VENUE'?{title:'',address:''}:{})}:type==='CONTACT'?{phone_number:'',first_name:''}:{emoji:'🎲'})});
export function nativeError(json:string):string {
 try{const v=JSON.parse(json),type=v.type;
 if(!v||typeof v!=='object'||!nativeTypes.includes(type))return 'اختر نوع محتوى Telegram صالحًا.';
 if(['LOCATION','LIVE_LOCATION','VENUE'].includes(type)&&(!Number.isFinite(v.latitude)||!Number.isFinite(v.longitude)||Math.abs(v.latitude)>90||Math.abs(v.longitude)>180))return 'أدخل خط عرض بين -90 و90 وخط طول بين -180 و180. لا نستخدم موقعك تلقائيًا.';
 if(type==='LIVE_LOCATION'&&(!Number.isInteger(v.live_period)||v.live_period<60||v.live_period>86400))return 'مدة الموقع الحي من60إلى86400ثانية.';
 if(type==='POLL'&&(typeof v.question!=='string'||!v.question.trim()||v.question.length>300||!Array.isArray(v.options)||v.options.length<2||v.options.length>12||v.options.some((x:unknown)=>typeof x!=='string'||!x.trim()||x.length>100)))return 'أدخل سؤالًا حتى300حرف وخيارين إلى12خيارًا، كل خيار حتى100حرف.';
 if(type==='VENUE'&&(['title','address'].some(key=>typeof v[key]!=='string'||!v[key].trim()||v[key].length>256)))return 'أدخل اسم المكان وعنوانه.';
 if(type==='CONTACT'&&(['first_name','phone_number'].some(key=>typeof v[key]!=='string'||!v[key].trim()||v[key].length>(key==='phone_number'?32:64))||(v.last_name!==undefined&&(typeof v.last_name!=='string'||v.last_name.length>64))))return 'أدخل اسم جهة الاتصال ورقمها مع مفتاح الدولة.';
 if(type==='DICE'&&!['🎲','🎯','🏀','⚽','🎳','🎰'].includes(v.emoji))return 'اختر لعبة من القائمة.';
 return '';
 }catch{return 'بيانات المحتوى غير صالحة. صحّح الحقول أو صيغةJSONالمتقدمة.';}
}
export function NativeTelegramFields({kind,value,onChange}:{kind:string;value:string;onChange:(value:string)=>void}){
 const [advanced,setAdvanced]=useState(false);let data:Record<string,unknown>;try{const parsed=JSON.parse(value);data=parsed&&typeof parsed==='object'&&!Array.isArray(parsed)?parsed:{type:kind};}catch{data={type:kind};}
 const set=(key:string,v:unknown)=>onChange(JSON.stringify({...data,[key]:v},null,2));
 const input=(key:string,label:string,type='text',maxLength?:number)=><label className="block text-sm font-semibold" key={key}>{label}<input aria-label={label} type={type} maxLength={maxLength} step={type==='number'?'any':undefined} value={String(data[key]??'')} onChange={e=>set(key,type==='number'?(e.target.value===''?'':Number(e.target.value)):e.target.value)} className="mt-1 block w-full min-w-0 rounded border p-2 font-normal"/></label>;
 return <div className="space-y-3 rounded border bg-white p-3" aria-label="حقول محتوى Telegram"><p className="text-sm leading-7">املأ تفاصيل المحتوى. الحفظ ينشئ مسودة للمراجعة فقط، ولا يرسل رسالة. لا نختار موقعًا أو جهة اتصال بدلًا عنك.</p>
 {kind==='POLL'?<>{input('question','سؤال الاستطلاع','text',300)}<label className="block text-sm font-semibold">خيارات الاستطلاع، كل خيار في سطر<textarea aria-label="خيارات الاستطلاع، كل خيار في سطر" value={Array.isArray(data.options)?data.options.map(x=>typeof x==='string'?x:'').join('\n'):''} onChange={e=>set('options',e.target.value.split('\n'))} className="mt-1 block min-h-28 w-full rounded border p-2 font-normal"/></label><label className="block text-sm"><input type="checkbox" checked={data.allows_multiple_answers===true} onChange={e=>set('allows_multiple_answers',e.target.checked)}/> السماح بأكثر من إجابة</label><p className="text-xs leading-6">استطلاع مجهول الهوية، من2إلى12خيارًا. للاختبار بإجابة صحيحة اختر «اختبار» من نوع المسودة.</p></>:null}
 {['LOCATION','LIVE_LOCATION','VENUE'].includes(kind)?<><div className="grid gap-3 sm:grid-cols-2">{input('latitude','خط العرض','number')}{input('longitude','خط الطول','number')}</div><p className="text-xs leading-6">استخدم إحداثيات المكان المقصود. هذه ليست قراءة لموقع جهازك.</p></>:null}
 {kind==='LIVE_LOCATION'?<>{input('live_period','مدة الموقع الحي بالثواني','number')}<p className="text-xs leading-6">من60ثانية إلى24ساعة. حفظ المسودة لا يبدأ مشاركة حية؛ التحديث والإيقاف لهما قرار منفصل بعد الإرسال.</p></>:null}
 {kind==='VENUE'?<>{input('title','اسم المكان','text',256)}{input('address','عنوان المكان','text',256)}</>:null}
 {kind==='CONTACT'?<>{input('first_name','الاسم الأول لجهة الاتصال','text',64)}{input('last_name','اسم العائلة لجهة الاتصال، اختياري','text',64)}{input('phone_number','رقم جهة الاتصال مع مفتاح الدولة','tel',32)}</>:null}
 {kind==='DICE'?<label className="block text-sm font-semibold">نوع اللعبة<select aria-label="نوع اللعبة" value={String(data.emoji??'🎲')} onChange={e=>set('emoji',e.target.value)} className="block w-full rounded border p-2">{[['🎲','نرد'],['🎯','تصويب'],['🏀','كرة سلة'],['⚽','كرة قدم'],['🎳','بولينغ'],['🎰','آلة حظ']].map(([v,label])=><option key={v} value={v}>{v} {label}</option>)}</select></label>:null}
 <label className="block text-xs"><input type="checkbox" checked={advanced} onChange={e=>setAdvanced(e.target.checked)}/> تحريرJSONالمتقدم بدل الحقول</label>
 {advanced?<label className="block text-sm">البيانات المنظمة، التعديل ينعكس على الحقول<textarea aria-label="بيانات Telegram المنظمة" value={value} onChange={e=>onChange(e.target.value)} dir="ltr" className="min-h-48 w-full rounded border p-3 font-mono text-xs"/></label>:null}
 {nativeError(value)?<p role="status" className="text-sm text-amber-800">{nativeError(value)}</p>:null}
 </div>;
}
