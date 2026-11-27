import {libraryFixture} from './libraryFixture';
import {test,expect} from '@playwright/test';
for(const width of [390,1280])for(const shortcut of [true,false])test(`library ${shortcut?"shortcut and ":""}return restores visible keyboard focus at ${width}px`,async({page},info)=>{
 let writes=0;
 const items=Array.from({length:14},(_,i)=>({id:'focus-'+i,kind:'TEXT',status:'AVAILABLE',content:'أصل محفوظ '+i,mime_type:'text/plain',metadata:{title:'مادة '+i},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'}));
 await page.route('**/*',r=>{const req=r.request(),p=new URL(req.url()).pathname;if(req.method()!=='GET')writes++;if(p==='/api/artifacts'||p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return r.fulfill({json:libraryFixture(r, {items,total:14,limit:100,offset:0})});if(p.startsWith('/api/control/')||p==='/sources')return r.fulfill({json:[]});if(p.startsWith('/api/')||p.startsWith('/posts')||p.startsWith('/schedules'))return r.fulfill({json:{items:[],total:0,sources:[],topics:[],kinds:[]}});return r.continue();});
 await page.setViewportSize({width,height:844});await page.goto('/bank?artifact_status=APPROVED');
 const search=page.getByLabel('بحث في المخرجات',{exact:true});
 if(shortcut){await page.getByRole('link',{name:'البحث في مكتبة المواد',exact:true}).click();await expect(search).toBeFocused();}
 await search.fill('مادة');
 const first=page.getByRole('button',{name:'فتح المادة والتجهيز والتتبع',exact:true}).first();await first.click();
 await expect(page.getByRole('region',{name:'تنقل مساحة المادة'})).toBeFocused();
 await page.getByRole('button',{name:'المادة التالية',exact:true}).click();
 await expect(page).toHaveURL(/artifact_id=focus-1/);
 await page.getByRole('button',{name:'العودة إلى المكتبة',exact:true}).click();
 const target=page.locator('#material-open-focus-1');await expect(target).toBeFocused();await expect(search).toHaveValue('مادة');
 await expect.poll(()=>target.evaluate(e=>{const r=e.getBoundingClientRect();return r.top>=72&&r.bottom<=innerHeight;})).toBeTruthy();
 await page.screenshot({path:info.outputPath(`library-return-${width}.png`)});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();expect(writes).toBe(0);
 await target.click();await page.getByRole('button',{name:'إغلاق مساحة المادة',exact:true}).click();await expect(target).toBeFocused();
});
