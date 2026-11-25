import {test,expect} from '@playwright/test';
test('slow page transition does not invent a smaller total or show two of one',async({page},info)=>{
 let release:()=>void=()=>{};let requested=false;const delay=new Promise<void>(r=>{release=r});let writes=0;
 await page.route('**/*',async r=>{const u=new URL(r.request().url()),p=u.pathname;if(r.request().method()!=='GET')writes++;
 if(p==='/schedules'){if(u.searchParams.get('offset')==='20'){requested=true;await delay;}return r.fulfill({json:{items:[],total:24,limit:20,offset:Number(u.searchParams.get('offset'))}});}
 if(p==='/api/artifacts/platform-variants'||p.startsWith('/api/control/')||p==='/sources')return r.fulfill({json:[]});if(p==='/posts/filter-options')return r.fulfill({json:{sources:[],kinds:[]}});if(p.startsWith('/api/')||p.startsWith('/schedules/')||p==='/posts')return r.fulfill({json:{items:[],total:0}});return r.continue();});
 await page.setViewportSize({width:390,height:844});await page.goto('/publishing?view=plans&failures=1');const pagination=page.getByLabel('صفحات خطط النشر');await expect(pagination).toContainText('صفحة 1 من 2');await expect(page.getByText('مرشح نشط:',{exact:false})).toBeVisible();
 await pagination.getByRole('button',{name:'التالي'}).click();await expect.poll(()=>requested).toBe(true);await expect(pagination).toContainText('تحميل الصفحة...');await expect(pagination).not.toContainText('صفحة 2 من 1');await expect(pagination.getByRole('button',{name:'التالي'})).toBeDisabled();await expect(pagination.getByRole('button',{name:'السابق'})).toBeDisabled();await pagination.scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath('page-loading-mobile.png')});
 release();await expect(pagination).toContainText('صفحة 2 من 2');await page.screenshot({path:info.outputPath('page-loaded-mobile.png')});expect(writes).toBe(0);
});
