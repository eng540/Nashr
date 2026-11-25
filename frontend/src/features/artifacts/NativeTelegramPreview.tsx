const names:Record<string,string>={POLL:'استطلاع',LOCATION:'موقع',LIVE_LOCATION:'موقع حي محدود المدة',VENUE:'مكان',CONTACT:'جهة اتصال',DICE:'لعبة تفاعلية'};
export function NativeTelegramPreview({value}:{value:unknown}) {
 const v=value&&typeof value==='object'&&!Array.isArray(value)?value as Record<string,unknown>:{};
 const kind=String(v.type??'');
 const text=(key:string)=>typeof v[key]==='string'||typeof v[key]==='number'?String(v[key]):'غير متاح';
 const fact=(label:string,key:string)=><div key={key} className="min-w-0"><dt className="text-xs font-semibold text-slate-500">{label}</dt><dd className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]" dir="auto">{text(key)}</dd></div>;
 return <section aria-label="معاينة محتوى Telegram" className="space-y-3 rounded-lg border bg-sky-50 p-3 text-sm leading-7"><h4 className="font-bold">معاينة {names[kind]??'محتوى Telegram'}</h4>
 {kind==='POLL'?<><p className="whitespace-pre-wrap break-words" dir="auto">{text('question')}</p><ol className="list-inside list-decimal space-y-1">{Array.isArray(v.options)?v.options.map((o,i)=><li key={i} className="break-words" dir="auto">{typeof o==='string'?o:'خيار غير متاح'}</li>):<li>الخيارات غير متاحة</li>}</ol><p>مجهول الهوية · {v.allows_multiple_answers===true?'يسمح بأكثر من إجابة':'إجابة واحدة'}</p></>:null}
 <dl className="grid min-w-0 gap-3 sm:grid-cols-2">{['LOCATION','LIVE_LOCATION','VENUE'].includes(kind)?<>{fact('خط العرض','latitude')}{fact('خط الطول','longitude')}</>:null}{kind==='LIVE_LOCATION'?fact('المدة بالثواني','live_period'):null}{kind==='VENUE'?<>{fact('اسم المكان','title')}{fact('العنوان','address')}</>:null}{kind==='CONTACT'?<>{fact('الاسم الأول','first_name')}{v.last_name?fact('اسم العائلة','last_name'):null}{fact('رقم الهاتف','phone_number')}</>:null}{kind==='DICE'?fact('رمز اللعبة','emoji'):null}</dl>
 {['LOCATION','LIVE_LOCATION','VENUE'].includes(kind)?<p className="text-xs">إحداثيات محفوظة أدخلها صاحب المسودة، وليست قراءة لموقع جهازك. {kind==='LIVE_LOCATION'?'الحفظ والمراجعة لا يبدآن مشاركة حية.':''}</p>:null}
 {!names[kind]?<p role="status">تعذر عرض نوع المحتوى بحقول واضحة. راجع البيانات التقنية قبل الاعتماد.</p>:null}
 <details><summary className="cursor-pointer text-xs">بيانات تقنية اختيارية للمحتوى</summary><pre dir="ltr" className="max-w-full whitespace-pre-wrap break-all text-xs">{JSON.stringify(value,null,2)}</pre></details><p className="text-xs">هذه معاينة للبيانات المحفوظة، وليست رسالة مرسلة أو محاكاة لشكل التطبيق. الاعتماد لا يعني النشر.</p></section>;
}
