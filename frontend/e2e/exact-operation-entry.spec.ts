import {test,expect} from '@playwright/test';
import {libraryFixture} from './libraryFixture';
const id='12345678-1234-4123-8123-123456789ab1',jid='12345678-1234-4123-8123-123456789ab2';
for(const width of [390,1280])for(const scenario of ['pending','copy-error','interrupted','ordinary'])test(`exact operation landing ${scenario} ${width}`,async({page},info)=>{
 let release=()=>{};const writes:string[]=[];
 await page.route('**/*',async r=>{
  const p=new URL(r.request().url()).pathname;
  if(r.request().method()!=='GET')writes.push(p);
  if(p.endsWith('/platform-copies')){
   if(scenario==='interrupted')await new Promise<void>(resolve=>release=resolve);
   return scenario==='copy-error'?r.fulfill({status:503,json:{detail:'synthetic copy failure'}}):r.fulfill({json:{items:[]}});
  }
  if(p==='/api/artifacts'||p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return r.fulfill({json:libraryFixture(r,{items:[{id,kind:'TEXT',status:'AVAILABLE',content:'أصل محفوظ',mime_type:'text/plain',metadata:{title:'مادة الاختبار'},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'}],total:1,limit:100,offset:0})});
  if(p.startsWith('/posts')||p==='/sources'||p.startsWith('/api/control/'))return r.fulfill({json:[]});
  if(p.startsWith('/api/'))return r.fulfill({json:{items:[],total:0}});
  return r.continue();
 });
 await page.route('**/result',async r=>{if(scenario==='pending'){await new Promise<void>(resolve=>release=resolve);}return r.fulfill({status:503,json:{detail:'synthetic result failure'}});});
 await page.setViewportSize({width,height:844});
 await page.goto(`/bank?artifact_status=APPROVED&artifact_id=${id}${scenario==='ordinary'?'':`&instagram_job_id=${jid}`}`);
 const nav=page.getByLabel('تنقل مساحة المادة',{exact:true}),panel=page.getByLabel('عملية Instagram المرتبطة',{exact:true});
 if(scenario==='ordinary'){
  await expect(nav).toBeFocused();await expect(nav).toBeInViewport();await expect(panel).toHaveCount(0);
 }else if(scenario==='interrupted'){
  await expect(nav).toBeFocused();await nav.getByRole('button',{name:'المادة التالية',exact:true}).focus();await page.keyboard.press('Tab');
  const before=await page.evaluate(()=>({y:scrollY}));release();await expect(panel.getByRole('alert')).toBeVisible();
  await expect.poll(()=>page.evaluate(()=>scrollY)).toBe(before.y);await expect(panel).not.toBeFocused();
 }else{
  await expect(panel).toBeFocused();await expect(panel.getByRole('heading')).toBeInViewport();
  if(scenario==='pending'){await expect(panel.getByRole('status')).toContainText('جارٍ قراءة');await page.screenshot({path:info.outputPath(`pending-${width}.png`)});release();}
  await expect(panel.getByRole('alert')).toBeVisible();await expect(panel.getByRole('heading')).toBeInViewport();
 }
 expect(writes).toEqual([]);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
