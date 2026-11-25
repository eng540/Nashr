import {test,expect} from '@playwright/test';
test('connection overview separates saved identity, disabled, read failure and incomplete setup without writes',async({page},info)=>{
 let writes=0;
 await page.route('**/*',route=>{const r=route.request(),p=new URL(r.url()).pathname;if(r.method()!=='GET')writes++;
 if(p==='/api/connections')return route.fulfill({json:{telegram:{items:[],credential_storage_ready:true},platforms:[]}});
 if(p==='/api/connections/instagram')return route.fulfill({json:{configured:true,connection:{username:'saved_account',state:'CONNECTED',enabled:true,last_check_at:'2026-11-25T10:00:00Z',last_check_ok:true},pending:null,requirements:[],missing_configuration:[]}});
 if(p==='/api/connections/facebook')return route.fulfill({json:{configured:true,connection:{page_name:'صفحة تعليم هندسي',page_id:'123',state:'DISABLED',enabled:false,last_check_at:'2026-11-25T10:00:00Z',tasks:[],caveat:'حالة محفوظة'},pending:null,requirements:[],missing_configuration:[]}});
 if(p==='/api/connections/youtube')return route.fulfill({status:503,json:{detail:'unavailable'}});
 if(p==='/api/connections/tiktok')return route.fulfill({json:{configured:false,connection:null,pending:null}});
 if(p==='/api/connections/tiktok/requirements')return route.fulfill({json:{modes:[],media_requirements:[],sources:[]}});
 if(p.startsWith('/api/connections/'))return route.fulfill({json:{configured:false,connection:null,pending:null,requirements:[],missing_configuration:[]}});
 if(p.startsWith('/api/'))return route.fulfill({json:{items:[],total:0}});return route.continue();});
 await page.goto('/connections');const overview=page.getByRole('region',{name:'ملخص الحسابات المحفوظة'});await expect(overview).toContainText('@saved_account');await expect(overview).toContainText('صفحة تعليم هندسي');await expect(overview).toContainText('معطل محلياً');await expect(overview).toContainText('تعذر قراءة الحالة');await expect(overview).toContainText('الإعداد غير مكتمل');await expect(overview).not.toContainText('الكل جاهز');expect(writes).toBe(0);
 await overview.screenshot({path:info.outputPath('connection-overview-desktop.png')});await page.setViewportSize({width:390,height:844});await overview.screenshot({path:info.outputPath('connection-overview-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
