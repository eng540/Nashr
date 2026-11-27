import {test,expect} from '@playwright/test';
test('first user chooses distribution or Telegram texts without scrolling past both workflows',async({page},info)=>{
 let writes=0;
 await page.route('**/*',async route=>{const r=route.request(),u=new URL(r.url()),p=u.pathname;
 if(p.startsWith('/api/')||p.startsWith('/posts')||p.startsWith('/schedules')){
 if(r.method()!=='GET')writes++;
 if(p==='/api/publishing-queue')return route.fulfill({json:{items:[{id:'art',origin:'ARTIFACT',kind:'VIDEO',title:'فيديو معتمد',content_preview:'مادة محفوظة',state:'APPROVED',prepared_copies:0,fields_validated:0,selected_platforms:[],selection_stale:false}],total:1}});
 if(p==='/api/artifacts/platform-variants')return route.fulfill({json:[]});
 if(p==='/posts')return route.fulfill({json:{items:[{post_id:'post',title:'نص Telegram المعتمد',source_title:'كتاب',content_preview:'نص محفوظ',status:'APPROVED'}],total:1}});
 return route.fulfill({json:{items:[],total:0,sources:[],kinds:[],counts:{waiting:0,published:0,attention:0}}});}
 return route.continue();});
 await page.setViewportSize({width:390,height:844});await page.goto('/publishing');
 const tasks=page.getByRole('navigation',{name:'ماذا تريد أن تفعل بالمحتوى؟'});
 await expect(page.getByRole('region',{name:'قائمة المحتوى الموحدة',exact:true})).toBeVisible();
 await expect(page.getByLabel('بحث المنشورات الجاهزة')).toHaveCount(0);
 await tasks.getByRole('button',{name:/جدولة نصوص Telegram/}).click();
 await expect(page.getByLabel('بحث المنشورات الجاهزة')).toBeVisible();await expect(page.getByRole('region',{name:'قائمة المحتوى الموحدة',exact:true})).toHaveCount(0);await expect(page).toHaveURL(/ready_task=editorial/);
 await page.reload();await expect(page.getByLabel('بحث المنشورات الجاهزة')).toBeVisible();
 await tasks.scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath('publishing-task-choice-mobile.png')});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await tasks.getByRole('button',{name:/متابعة مادة وتجهيز وجهاتها/}).click();await expect(page.getByText('فيديو معتمد',{exact:true})).toBeVisible();await expect(page).not.toHaveURL(/ready_task=editorial/);
 await page.goBack();await expect(page.getByLabel('بحث المنشورات الجاهزة')).toBeVisible();await page.goto('/publishing?selected_post_ids=post');await expect(page.getByLabel('بحث المنشورات الجاهزة')).toBeVisible();await expect(page.getByTestId('schedule-panel')).toBeVisible();expect(writes).toBe(0);
});
