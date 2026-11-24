import {test,expect} from '@playwright/test';
test('Facebook explicit Page choice and read-only verify preserve Instagram',async({page},info)=>{
 let selected='',checks=0;const writes:string[]=[];
 const candidate={page_id:'123456',page_name:'EngineeringCreativity',tasks:['CREATE_CONTENT'],token_type:'PAGE'};
 await page.route('**/api/**',async route=>{
 const r=route.request(),p=new URL(r.url()).pathname;if(!p.startsWith('/api/'))return route.continue();
 if(p==='/api/connections/facebook')return route.fulfill({json:{configured:true,missing_configuration:[],connection:selected?{...candidate,state:'CONNECTED_AT_LAST_CHECK',enabled:true,expires_at:null,last_check_at:'2026-11-24T20:00:00Z',caveat:'آخر تحقق فقط، لا نشر.'}:null,pending:selected?null:{accounts:[candidate]},requirements:['CREATE_CONTENT'],source:'https://developers.facebook.com/documentation/facebook-login/facebook-login-for-business'}});
 if(p==='/api/connections/facebook/select'){expect(r.postDataJSON()).toEqual({page_id:candidate.page_id});selected=candidate.page_id;writes.push(p);return route.fulfill({json:{connected:true}});}
 if(p==='/api/connections/facebook/verify'){checks++;writes.push(p);return route.fulfill({json:{posts_created:0}});}
 if(r.method()!=='GET')throw new Error('Unexpected mutation '+p);
 if(p==='/api/connections')return route.fulfill({json:{telegram:{items:[],credential_storage_ready:true},platforms:[{key:'facebook',label:'Facebook',state:'CONNECTION_ONLY',requirements:'ربط فقط'}]}});
 if(p.startsWith('/api/connections/instagram'))return route.fulfill({json:{configured:false,connection:null,pending:null,requirements:[],missing_configuration:[]}});
 return route.fulfill({json:{items:[]}});
 });
 await page.goto('/connections');
 const panel=page.getByLabel('ربط صفحة Facebook',{exact:true});await panel.scrollIntoViewIfNeeded();
 const save=panel.getByRole('button',{name:'تحقق واحفظ الصفحة دون نشر',exact:true});await expect(save).toBeDisabled();expect(writes).toEqual([]);
 await panel.getByLabel('صفحة Facebook',{exact:true}).selectOption('123456');await save.click();
 await expect(panel.getByText('الصفحة: EngineeringCreativity ·',{exact:false})).toBeVisible();
 await panel.getByRole('button',{name:'تحقق من الصفحة دون نشر',exact:true}).click();expect(checks).toBe(1);
 await page.setViewportSize({width:1280,height:1000});await panel.screenshot({path:info.outputPath('facebook-desktop.png')});
 await page.setViewportSize({width:390,height:844});await panel.screenshot({path:info.outputPath('facebook-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 expect(writes).toEqual(['/api/connections/facebook/select','/api/connections/facebook/verify']);
});
