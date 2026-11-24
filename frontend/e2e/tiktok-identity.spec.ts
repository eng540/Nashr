import {test,expect} from '@playwright/test';
test('TikTok identity requires explicit choice and no publishing',async({page},info)=>{
 let selected=false;const writes:string[]=[];const identity={open_id:'synthetic-app-specific-id',display_name:'اسم عرض تجريبي'};
 await page.route('**/api/**',async route=>{
 const r=route.request(),p=new URL(r.url()).pathname;if(!p.startsWith('/api/'))return route.continue();
 if(p==='/api/connections/tiktok/requirements')return route.fulfill({json:{reviewed_on:'2026-11-24',modes:[],media_requirements:[],sources:[]}});
 if(p==='/api/connections/tiktok')return route.fulfill({json:{configured:true,connection:selected?{...identity,state:'CONNECTED_AT_LAST_CHECK',expires_at:'2026-11-25T23:00:00Z',caveat:'اسم العرض ليس اسم المستخدم @. لا رفع أو نشر. التجديد التلقائي غير مفعّل.'}:null,pending:selected?null:{accounts:[identity]}}});
 if(p==='/api/connections/tiktok/select'){expect(r.postDataJSON()).toEqual({open_id:identity.open_id});selected=true;writes.push(p);return route.fulfill({json:{connected:true}});}
 if(p==='/api/connections/tiktok/verify'){writes.push(p);return route.fulfill({json:{connection:identity}});}
 if(r.method()!=='GET')throw new Error('Unexpected write '+p);
 if(p==='/api/connections')return route.fulfill({json:{telegram:{items:[],credential_storage_ready:true},platforms:[{key:'tiktok',label:'TikTok',state:'CONNECTION_ONLY',requirements:'الهوية فقط'}]}});
 if(p.startsWith('/api/connections/'))return route.fulfill({json:{configured:false,connection:null,pending:null,requirements:[],missing_configuration:[]}});
 return route.fulfill({json:{items:[]}});
 });
 await page.goto('/connections');const panel=page.getByLabel('ربط هوية TikTok',{exact:true});await panel.scrollIntoViewIfNeeded();
 const save=panel.getByRole('button',{name:'تحقق واحفظ هوية TikTok دون نشر',exact:true});await expect(save).toBeDisabled();expect(writes).toEqual([]);
 await panel.getByLabel('هوية TikTok',{exact:true}).selectOption(identity.open_id);await save.click();await expect(panel.getByText('اسم العرض: اسم عرض تجريبي',{exact:true})).toBeVisible();
 await panel.getByRole('button',{name:'تحقق من هوية TikTok دون نشر',exact:true}).click();await expect.poll(()=>writes.length).toBe(2);
 await expect(panel.getByRole('button',{name:'حذف الربط المحلي',exact:true})).toBeDisabled();
 await page.setViewportSize({width:1280,height:1000});await panel.screenshot({path:info.outputPath('tiktok-desktop.png')});
 await page.setViewportSize({width:390,height:844});await panel.screenshot({path:info.outputPath('tiktok-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 expect(writes).toEqual(['/api/connections/tiktok/select','/api/connections/tiktok/verify']);
});
