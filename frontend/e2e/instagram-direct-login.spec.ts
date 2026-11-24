import {test,expect} from '@playwright/test';
test('direct Instagram settings and selection stay independent and private',async({page},info)=>{
 page.on('pageerror',e=>console.log('PAGEERROR',e.message));page.on('console',m=>{if(m.type()==='error')console.log('CONSOLE',m.text())});
 let configured=false,selected=false;const unexpected:string[]=[];
 const account={account_id:'789',username:'creator',app_scoped_id:'456'};
 await page.route('**/api/connections**',async route=>{const r=route.request(),p=new URL(r.url()).pathname;
 if(p==='/api/connections')return route.fulfill({json:{telegram:{credential_storage_ready:true,items:[],legacy_imported:false},platforms:[]}});
 if(p==='/api/connections/tiktok')return route.fulfill({json:{configured:false,connection:null,pending:null}});
 if(p==='/api/connections/tiktok/requirements')return route.fulfill({json:{reviewed_on:'2026-11-24',modes:[],media_requirements:[],sources:[]}});
 if(p==='/api/connections/facebook')return route.fulfill({json:{configured:false,missing_configuration:[],connection:null,pending:null,requirements:[],source:'https://developers.facebook.com'}});
 if(p==='/api/connections/instagram-direct')return route.fulfill({json:{configured,connection:selected?{...account,state:'CONNECTED_AT_LAST_CHECK',enabled:true,expires_at:'2027-01-20T10:00:00Z',last_check_at:null}:null,pending:configured&&!selected?{accounts:[account]}:null,source:'https://developers.facebook.com'}});
 if(p.endsWith('/instagram-direct/settings')){const b=r.postDataJSON();expect(b.direct_login_reviewed).toBe(true);expect(b.config_id).toBeUndefined();configured=true;return route.fulfill({json:{saved:true}});}
 if(p.endsWith('/instagram-direct/select')){expect(r.postDataJSON()).toEqual({account_id:'789'});selected=true;return route.fulfill({json:{connected:true,execution_authorized:false}});}
 if(p==='/api/connections/instagram-page'||p==='/api/connections/instagram')return route.fulfill({json:{configured:false,missing_configuration:[],connection:null,pending:null,requirements:[],source:'https://developers.facebook.com'}});
 unexpected.push(p);return route.fulfill({status:404,json:{detail:'unexpected'}});
 });
 await page.goto('/connections');await expect(page.getByText('غير متاح للتطبيقات الجديدة بحسب Meta.',{exact:true})).toBeVisible();await page.getByLabel('إقرار توفر إعداد Instagram Login قديم').check();const panel=page.getByLabel('ربط Instagram المباشر',{exact:true});await expect(panel).toBeVisible();await expect(panel.getByRole('button',{name:'المتابعة إلى Instagram مباشرة',exact:true})).toBeDisabled();
 await panel.getByText('إعداد Instagram Login المباشر',{exact:true}).click();await panel.getByLabel('Instagram App ID المباشر',{exact:true}).fill('123456');await panel.getByLabel('Instagram App Secret المباشر',{exact:true}).fill('synthetic-secret');await panel.getByRole('checkbox').last().check();await panel.getByRole('button',{name:'حفظ إعداد Instagram المباشر',exact:true}).click();await expect(panel.getByLabel('Instagram App Secret المباشر',{exact:true})).toHaveValue('');
 await expect(panel.getByRole('button',{name:'تحقق واحفظ حساب Instagram دون نشر',exact:true})).toBeDisabled();await panel.getByLabel('حساب Instagram المباشر',{exact:true}).selectOption('789');await panel.getByRole('button',{name:'تحقق واحفظ حساب Instagram دون نشر',exact:true}).click();await expect(panel.getByText('@creator · 789',{exact:true})).toBeVisible();
 await page.addStyleTag({content:'header{visibility:hidden}'});await page.setViewportSize({width:390,height:844});await panel.screenshot({path:info.outputPath('instagram-direct-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();expect(unexpected).toEqual([]);
});
