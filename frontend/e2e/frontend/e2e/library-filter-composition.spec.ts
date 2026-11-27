import {libraryFixture} from './libraryFixture';
import {test,expect} from '@playwright/test';
test('same-render library filter changes compose without dropping prior choices',async({page},info)=>{
 let writes=0;const items=['one','two'].map((id,n)=>({id,kind:'TEXT',status:'AVAILABLE',content:'أصل محفوظ '+id,mime_type:'text/plain',metadata:{title:'مادة '+id,source_type:'MEDIA_BANK_UPLOAD'},organization:{title:'مادة '+id,series:'سلسلة ألف',category:'تعليم',version:1},review_status:'APPROVED',created_at:`2026-11-${23+n}T10:00:00Z`,updated_at:'2026-11-23T10:00:00Z'}));
 await page.route('**/*',r=>{const req=r.request(),p=new URL(req.url()).pathname;if(req.method()!=='GET')writes++;if(p==='/api/artifacts'||p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return r.fulfill({json:libraryFixture(r, {items,total:2,limit:100,offset:0})});if(p.startsWith('/api/'))return r.fulfill({json:p.includes('/control/')?[]:{items:[],total:0}});if(['/posts','/sources'].some(x=>p.startsWith(x)))return r.fulfill({json:[]});return r.continue();});
 await page.goto('/bank?artifact_status=APPROVED');
 await page.getByText('تصفية وترتيب · النوع، المصدر، السلسلة، التصنيف',{exact:true}).click();
 await page.evaluate(()=>{
  for(const [label,value] of [['تصفية حسب نوع المخرج','TEXT'],['تصفية حسب مصدر المخرج','MEDIA_BANK_UPLOAD'],['تصفية حسب السلسلة','سلسلة ألف']]){
   const select=document.querySelector(`select[aria-label="${label}"]`) as HTMLSelectElement;
   select.value=value;select.dispatchEvent(new Event('change',{bubbles:true}));
  }
 });
 await expect.poll(()=>{const p=new URL(page.url()).searchParams;return ['library_kind','library_source','library_series'].map(k=>p.get(k));}).toEqual(['TEXT','MEDIA_BANK_UPLOAD','سلسلة ألف']);
 await page.reload();await expect(page.getByLabel('تصفية حسب مصدر المخرج',{exact:true})).toHaveValue('MEDIA_BANK_UPLOAD');expect(writes).toBe(0);
});
