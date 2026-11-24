import {test,expect} from '@playwright/test';
test('official Instagram connection is honest when unconfigured and explicit when selecting',async({page},info)=>{
 let configured=false,selected=false,pending=false;const writes:string[]=[];
 const status=()=>({configured,missing_configuration:configured?[]:['META_APP_ID','META_INSTAGRAM_CONFIG_ID'],connection:selected?{username:'test_owner',state:'CONNECTED_AT_LAST_CHECK',expires_at:null,caveat:'لا موصل نشر أو إذن تنفيذ من هذا الربط.'}:null,pending:pending?{accounts:[{account_id:'123',username:'test_owner'},{account_id:'456',username:'another'}]}:null,requirements:['حساب احترافي وإعداد تطبيق Meta مطلوبان.'],source:'https://developers.facebook.com/documentation/instagram-platform/overview/'});
 await page.route('**/*',async route=>{const path=new URL(route.request().url()).pathname;
 if(path==='/api/connections')return route.fulfill({json:{telegram:{source:'ENVIRONMENT',legacy_configured:true,credential_storage_ready:true,items:[]},platforms:[]}});
 if(path==='/api/connections/facebook')return route.fulfill({json:{configured:false,missing_configuration:[],connection:null,pending:null,requirements:[],source:'https://developers.facebook.com'}});
 if(path==='/api/connections/instagram-direct')return route.fulfill({json:{configured:false,missing_configuration:[],connection:null,pending:null,source:'https://developers.facebook.com'}});
 if(path==='/api/connections/instagram-page')return route.fulfill({json:{configured:false,missing_configuration:[],connection:null,pending:null,requirements:[],source:'https://developers.facebook.com'}});
 if(path==='/api/connections/instagram')return route.fulfill({json:status()});
 if(path==='/api/connections/instagram/select'){writes.push('select');expect(route.request().postDataJSON()).toEqual({account_id:'123'});selected=true;pending=false;return route.fulfill({json:{connected:true,execution_authorized:false}});}
 if(path==='/api/connections/instagram/disconnect'){writes.push('disconnect');selected=false;return route.fulfill({json:{disconnected_locally:true,remote_revoked:false}});}
 if(path.startsWith('/api/')||path.startsWith('/posts')||path==='/schedules'||path==='/sources'||path.startsWith('/schedules/')){if(route.request().method()!=='GET')throw Error('unexpected write '+path);return route.fulfill({json:path.includes('platform-variants')||path==='/sources'?[]:path.includes('filter-options')?{sources:[],kinds:[]}: {items:[],total:0}});}
 return route.continue();});
 await page.goto('/connections');const panel=page.getByRole('region',{name:'ربط Instagram الرسمي'});
 await expect(panel.getByText('غير مهيأ، إعداد تطبيق Meta مطلوب قبل إتاحة رابط الدخول.',{exact:true})).toBeVisible();await expect(panel.getByRole('button',{name:'المتابعة إلى Meta لربط حساب'})).toBeDisabled();expect(writes).toEqual([]);
 await page.setViewportSize({width:390,height:844});await panel.screenshot({path:info.outputPath('instagram-unconfigured-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 configured=true;pending=true;await page.reload();await expect(panel.getByRole('button',{name:'حفظ ربط الحساب المختار دون نشر'})).toBeDisabled();await panel.getByLabel('حساب Instagram المصرح به').selectOption('123');await panel.getByRole('button',{name:'حفظ ربط الحساب المختار دون نشر'}).click();await expect(panel.getByText('@test_owner',{exact:true})).toBeVisible();expect(writes).toEqual(['select']);
 await expect(panel.getByRole('button',{name:'فصل الربط محلياً'})).toBeDisabled();await panel.getByRole('checkbox').check();await panel.getByRole('button',{name:'فصل الربط محلياً'}).click();await expect(panel.getByText('@test_owner',{exact:true})).toHaveCount(0);expect(writes).toEqual(['select','disconnect']);
});
