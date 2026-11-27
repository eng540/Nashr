import {libraryFixture} from './libraryFixture';
import {test,expect} from '@playwright/test';
for(const action of ['status','task'] as const)test(`library ${action} preserves preceding filter change`,async({page},info)=>{
 let writes=0;const items=['one','two'].map((id,n)=>({id,kind:'TEXT',status:'AVAILABLE',content:'أصل محفوظ '+id,mime_type:'text/plain',metadata:{title:'مادة '+id,source_type:'MEDIA_BANK_UPLOAD'},organization:{title:'مادة '+id,series:'سلسلة ألف',category:'تعليم',version:1},review_status:'APPROVED',created_at:`2026-11-${23+n}T10:00:00Z`,updated_at:'2026-11-23T10:00:00Z'}));
 await page.route('**/*',r=>{const req=r.request(),p=new URL(req.url()).pathname;if(req.method()!=='GET')writes++;if(p==='/api/artifacts'||p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return r.fulfill({json:libraryFixture(r, {items,total:2,limit:100,offset:0})});if(p.startsWith('/api/'))return r.fulfill({json:p.includes('/control/')?[]:{items:[],total:0}});if(['/posts','/sources'].some(x=>p.startsWith(x)))return r.fulfill({json:[]});return r.continue();});
 await page.goto('/bank?artifact_status=APPROVED');
 await page.getByText('تصفية وترتيب · النوع، المصدر، السلسلة، التصنيف',{exact:true}).click();
 await page.evaluate(action=>{
  const kind=document.querySelector('select[aria-label="تصفية حسب نوع المخرج"]') as HTMLSelectElement;kind.value='TEXT';kind.dispatchEvent(new Event('change',{bubbles:true}));
  if(action==='status'){const status=document.querySelector('select[aria-label="حالة مراجعة المخرجات"]') as HTMLSelectElement;status.value='REJECTED';status.dispatchEvent(new Event('change',{bubbles:true}));}
  else {const task=Array.from(document.querySelectorAll('button')).find(e=>e.textContent?.includes('＋ رفع وسيط جاهز'))!;task.click();}
 },action);
 await expect.poll(()=>{const p=new URL(page.url()).searchParams;return ['library_kind','artifact_status','library_task'].map(k=>p.get(k));}).toEqual(action==='status'?['TEXT','REJECTED',null]:['TEXT','APPROVED','upload']);await page.reload();await expect(page.getByLabel('تصفية حسب نوع المخرج',{exact:true})).toHaveValue('TEXT');await expect(page.getByLabel('حالة مراجعة المخرجات',{exact:true})).toHaveValue(action==='status'?'REJECTED':'APPROVED');await page.goBack();await expect.poll(()=>new URL(page.url()).searchParams.get('library_kind')).toBe('TEXT');await expect(page.getByLabel('حالة مراجعة المخرجات',{exact:true})).toHaveValue('APPROVED');await page.goForward();await expect.poll(()=>new URL(page.url()).searchParams.get(action==='status'?'artifact_status':'library_task')).toBe(action==='status'?'REJECTED':'upload');expect(writes).toBe(0);
});
