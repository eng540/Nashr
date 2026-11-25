import {test,expect} from '@playwright/test';
test('YouTube read-only connection chooses returned channel explicitly without uploads',async({page},info)=>{
 let selected=false;const writes:string[]=[];const channel={channel_id:'UC'+'a'.repeat(22),title:'القناة الهندسية التجريبية'};
 await page.route('**/api/**',async route=>{
 const r=route.request(),p=new URL(r.url()).pathname;if(!p.startsWith('/api/'))return route.continue();
 if(p==='/api/connections/youtube')return route.fulfill({json:{configured:true,connection:selected?{...channel,state:'SAVED_NOT_LIVE',last_check_at:'2026-11-25T08:00:00Z',last_check_ok:true,caveat:'قراءة فقط دون رفع أو تعديل.'}:null,pending:selected?null:{accounts:[channel]}}});
 if(p==='/api/connections/youtube/select'){expect(r.postDataJSON()).toEqual({channel_id:channel.channel_id});selected=true;writes.push(p);return route.fulfill({json:{connected:true}});}
 if(p==='/api/connections/youtube/verify'){writes.push(p);return route.fulfill({json:{connection:channel}});}
 if(r.method()!=='GET')throw new Error('Unexpected write '+p);
 if(p==='/api/connections')return route.fulfill({json:{telegram:{items:[],credential_storage_ready:true},platforms:[{key:'youtube',label:'YouTube',state:'READONLY_CHANNEL_CONNECTION',requirements:'القراءة فقط'}]}});
 if(p==='/api/connections/tiktok/requirements')return route.fulfill({json:{reviewed_on:'2026-11-25',modes:[],media_requirements:[],sources:[]}});
 if(p.startsWith('/api/connections/'))return route.fulfill({json:{configured:false,connection:null,pending:null,requirements:[],missing_configuration:[]}});
 return route.fulfill({json:{items:[]}});
 });
 await page.goto('/connections');const panel=page.getByLabel('ربط قناة YouTube',{exact:true});await panel.scrollIntoViewIfNeeded();
 const save=panel.getByRole('button',{name:'تحقق واحفظ قناة YouTube دون رفع',exact:true});await expect(save).toBeDisabled();expect(writes).toEqual([]);
 await panel.getByLabel('قناة YouTube',{exact:true}).selectOption(channel.channel_id);await save.click();await expect(panel.getByText('القناة المحفوظة: '+channel.title,{exact:true})).toBeVisible();
 await panel.getByRole('button',{name:'تحقق من قناة YouTube دون رفع',exact:true}).click();await expect.poll(()=>writes.length).toBe(2);
 await expect(panel.getByRole('button',{name:'حذف ربط YouTube المحلي',exact:true})).toBeDisabled();
 await panel.getByText('إعداد تطبيق Google لقناة YouTube',{exact:true}).click();await expect(panel.getByLabel('حالة موافقة YouTube')).toHaveValue('');
 await page.setViewportSize({width:1280,height:1000});await panel.screenshot({path:info.outputPath('youtube-desktop.png')});
 await page.setViewportSize({width:390,height:844});await panel.screenshot({path:info.outputPath('youtube-mobile.png'),style:'header{visibility:hidden}'});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 expect(writes).toEqual(['/api/connections/youtube/select','/api/connections/youtube/verify']);
});
