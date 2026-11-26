import {test,expect} from '@playwright/test';
test('independent Sandbox consent preserves identity and has no media action',async({page},info)=>{
 let saved=false;const writes:string[]=[];const identity={open_id:'synthetic-id',display_name:'هوية تجريبية'};
 await page.route('**/api/**',async route=>{
 const r=route.request(),p=new URL(r.url()).pathname;if(!p.startsWith('/api/'))return route.continue();
 if(p==='/api/connections/tiktok-inbox')return route.fulfill({json:{configured:true,connection:saved?{...identity,state:'CONNECTED_AT_LAST_CHECK',expires_at:'2026-11-27T08:00:00Z',caveat:'إذن محفوظ، لا نقل أو نشر.'}:null,pending:saved?null:{accounts:[identity]}}});
 if(p==='/api/connections/tiktok-inbox/select'){expect(r.postDataJSON()).toEqual({open_id:identity.open_id});saved=true;writes.push(p);return route.fulfill({json:{connected:true,execution_authorized:false}});}
 if(r.method()!=='GET')throw new Error('Unexpected write '+p);
 if(p==='/api/connections/tiktok')return route.fulfill({json:{configured:true,connection:{...identity,state:'CONNECTED_AT_LAST_CHECK',expires_at:'2026-11-27T08:00:00Z',caveat:'ربط الهوية دون نشر.'},pending:null}});
 if(p==='/api/connections')return route.fulfill({json:{telegram:{items:[],credential_storage_ready:true},platforms:[{key:'tiktok',label:'TikTok',state:'CONNECTION_ONLY',requirements:'الهوية فقط'}]}});
 return route.fulfill({json:{configured:false,connection:null,pending:null,requirements:[],missing_configuration:[],items:[],modes:[],media_requirements:[],sources:[]}});
 });
 await page.setViewportSize({width:390,height:844});await page.goto('/connections#platform-tiktok-inbox');const panel=page.getByLabel('إذن مسودات TikTok التجريبي',{exact:true});await panel.scrollIntoViewIfNeeded();
 await page.addStyleTag({content:'header{position:static!important}'});
 const save=panel.getByRole('button',{name:'تحقق واحفظ إذن المسودات دون نقل',exact:true});await expect(save).toBeDisabled();await expect(panel.getByRole('button',{name:'عرض إذن مسودات TikTok التجريبي',exact:true})).toBeDisabled();
 await expect(panel.getByLabel('هوية إذن مسودات TikTok',{exact:true})).toBeFocused();await panel.screenshot({path:info.outputPath('inbox-pending-mobile.png')});
 await panel.getByLabel('هوية إذن مسودات TikTok',{exact:true}).selectOption(identity.open_id);await save.click();await expect(panel.getByText('إذن محفوظ، لا نقل أو نشر.')).toBeVisible();await expect(panel.getByText('حالة الإذن: إذن محفوظ من آخر تحقق، لا يثبت نجاح نقل مسودة',{exact:true})).toBeVisible();await expect(panel.getByText('CONNECTED_AT_LAST_CHECK',{exact:true})).toBeHidden();
 await panel.screenshot({path:info.outputPath('inbox-saved-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.setViewportSize({width:1280,height:1000});await panel.screenshot({path:info.outputPath('inbox-saved-desktop.png')});
 expect(writes).toEqual(['/api/connections/tiktok-inbox/select']);
});
