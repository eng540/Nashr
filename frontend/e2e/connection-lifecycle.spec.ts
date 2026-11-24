import {test,expect} from '@playwright/test';
test('legacy import and lifecycle keep history and hide write-only token',async({page},info)=>{
 let imported=false,enabled=true;const calls:{path:string;body:unknown}[]=[];
 const channel=()=>({id:'synthetic',label:'قناة الربط السابق',details:{destination:'-100123456',channel_title:'قناة محلية للاختبار',bot_username:'synthetic_bot'},verified_at:'2026-11-24T05:00:00Z',enabled,last_check_ok:true,last_check_at:'2026-11-24T05:00:00Z'});
 await page.route('**/api/connections**',async route=>{
  const p=new URL(route.request().url()).pathname;
  if(p==='/api/connections/instagram-direct')return route.fulfill({json:{configured:false,missing_configuration:[],connection:null,pending:null,source:'https://developers.facebook.com'}});
 if(p==='/api/connections/instagram-page')return route.fulfill({json:{configured:false,missing_configuration:[],connection:null,pending:null,requirements:[]}});
  if(p==='/api/connections/instagram')return route.fulfill({json:{configured:false,missing_configuration:['META_APP_ID'],connection:null,pending:null,requirements:[]}});
  if(p==='/api/connections'&&route.request().method()==='GET')return route.fulfill({json:{telegram:{legacy_configured:true,legacy_imported:imported,legacy_connection_id:imported?'synthetic':null,credential_storage_ready:true,items:imported?[channel()]:[]},platforms:[]}});
  if(p.endsWith('/history'))return route.fulfill({json:{plans:[{id:'old-plan',name:'الخطة القديمة المحفوظة',status:'PAUSED'}],publications:[{id:'old-publication',artifact_id:'old-material',status:'PUBLISHED'}]}});
  calls.push({path:p,body:route.request().postDataJSON()});
  if(p.endsWith('/import-legacy'))imported=true;
  if(p.endsWith('/state'))enabled=route.request().postDataJSON().enabled;
  return route.fulfill({json:{sent_messages:0,history_preserved:true,enabled}});
 });
 await page.setViewportSize({width:390,height:844});await page.goto('/connections');expect(calls).toEqual([]);
 await page.getByRole('button',{name:'استيراد الربط الحالي دون إعادة الرمز'}).click();await expect(page.getByRole('heading',{name:'قناة الربط السابق',exact:true})).toBeVisible();
 expect(calls[0].body).toBeNull();await page.getByText('إدارة الربط: التحقق · تحديث الرمز · التعطيل والتفعيل',{exact:true}).click();
 await expect(page.getByRole('button',{name:'تعطيل الربط مع حفظ السجل'})).toBeDisabled();
 await page.getByLabel('أفهم أثر التعطيل المحلي على الخطط').check();await page.getByRole('button',{name:'تعطيل الربط مع حفظ السجل'}).click();await expect(page.getByText('معطلة محلياً، لا إرسال جديد',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'سجل قناة الربط السابق',exact:true}).click();await expect(page.getByText('الخطة القديمة المحفوظة')).toBeVisible();
 await page.getByLabel('تحديث رمز قناة الربط السابق').fill('123456:synthetic-new-token-value');await page.getByRole('button',{name:'تحقق واحفظ الرمز الجديد'}).click();await expect(page.getByLabel('تحديث رمز قناة الربط السابق')).toHaveValue('');await expect(page.getByText('معطلة محلياً، لا إرسال جديد',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'تحقق الآن دون إرسال'}).click();await expect.poll(()=>calls.length).toBe(4);
 expect(calls.map(c=>c.path.split('/').at(-1))).toEqual(['import-legacy','state','token','verify']);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.getByRole('heading',{name:'قناة الربط السابق',exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath('lifecycle-mobile.png')});
 await page.setViewportSize({width:1280,height:1000});await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:info.outputPath('lifecycle-desktop.png')});
});
