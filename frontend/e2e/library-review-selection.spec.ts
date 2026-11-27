import {test,expect} from '@playwright/test';
for(const width of [390,1280])test(`draft review keeps exact ordered selection through focused visits at ${width}px`,async({page},info)=>{
 test.setTimeout(60000);
 const writes:string[]=[],previews:string[][]=[];let fail=false,late:()=>void=()=>{},delay=false;
 const items=Array.from({length:25},(_,i)=>({id:`draft-${i}`,kind:'TEXT',status:'AVAILABLE',review_status:'DRAFT',content:`أصل محفوظ ${i}`,metadata:{title:`مادة ${i}`,source_type:'GENERATED'},created_at:'2026-01-01',updated_at:'2026-01-01'}));
 await page.route('**/*',async r=>{const u=new URL(r.request().url()),p=u.pathname;
 if(!p.startsWith('/api/')&&!p.startsWith('/posts')&&p!=='/sources'&&!p.startsWith('/production-'))return r.continue();
 if(r.request().method()!=='GET'&&p!=='/api/artifacts/batch-review/preview')writes.push(p);
 if(p==='/api/artifacts/library'){if(fail)return r.fulfill({status:503,json:{detail:'offline'}});const offset=Number(u.searchParams.get('offset'));return r.fulfill({json:{items:items.slice(offset,offset+12),index:items.map(i=>({...i,content:null})),total:items.length,limit:12,offset,filter_options:{series:[],categories:[]}}});}
 if(p==='/api/artifacts/library-items')return r.fulfill({json:{items:u.searchParams.getAll('ids').map(id=>items.find(i=>i.id===id))}});
 if(p==='/api/artifacts/batch-review/preview'){const ids=r.request().postDataJSON().artifact_ids;previews.push(ids);if(delay)await new Promise<void>(resolve=>late=resolve);return r.fulfill({json:{publishing_authorized:false,items:ids.map((id:string)=>({...items.find(i=>i.id===id),review_fingerprint:'v1'}))}});}
 if(p==='/sources'||p==='/posts'||p.startsWith('/api/control/')||p.startsWith('/production-'))return r.fulfill({json:[]});return r.fulfill({json:{items:[],total:0,sources:[],kinds:[]}});
 });
 await page.setViewportSize({width,height:900});await page.goto('/bank');
 const batch=page.getByLabel('مراجعة واعتماد دفعة',{exact:true});
 await batch.getByRole('button',{name:'تحديد أصول الصفحة للمراجعة',exact:true}).click();
 await page.getByLabel('ترقيم صفحات المخرجات').getByRole('button',{name:'التالي'}).click();
 await expect(page.locator('#material-open-draft-12')).toBeVisible();
 await batch.getByRole('button',{name:'تحديد أصول الصفحة للمراجعة',exact:true}).click();await expect(batch.getByRole('status')).toHaveText('24 محدد للمراجعة');
 delay=true;await batch.getByRole('button',{name:'معاينة الدفعة المحفوظة (24)',exact:true}).click();await expect.poll(()=>previews.length).toBe(1);
 await page.locator('#material-open-draft-12').click();late();await page.getByRole('button',{name:'العودة إلى المكتبة',exact:true}).click();
 await expect(page.locator('#material-open-draft-12')).toBeFocused();await expect(batch.getByRole('status')).toHaveText('24 محدد للمراجعة');await expect(page.getByLabel('معاينة الاعتماد الجماعي')).toHaveCount(0);
 delay=false;await batch.getByRole('button',{name:'معاينة الدفعة المحفوظة (24)',exact:true}).click();await expect(page.getByLabel('معاينة الاعتماد الجماعي')).toBeVisible();
 expect(previews[1]).toEqual(items.slice(0,24).map(i=>i.id));
 await page.locator('#material-open-draft-12').click();await page.getByRole('button',{name:'العودة إلى المكتبة',exact:true}).click();await expect(batch.getByRole('status')).toHaveText('24 محدد للمراجعة');await expect(page.getByLabel('معاينة الاعتماد الجماعي')).toHaveCount(0);
 await batch.scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath(`review-selection-retained-${width}.png`)});
 await page.getByText('تصفية وترتيب · النوع، المصدر، السلسلة، التصنيف',{exact:true}).click();const sorted=page.waitForResponse(response=>{const url=new URL(response.url());return url.pathname==='/api/artifacts/library'&&url.searchParams.get('sort')==='oldest'&&url.searchParams.get('offset')==='0'&&response.ok();});await page.getByLabel('ترتيب المخرجات').selectOption('oldest');await sorted;await expect(batch.getByRole('status')).toHaveText('24 محدد للمراجعة');
 await expect(batch.getByRole('button',{name:'معاينة الدفعة المحفوظة (24)',exact:true})).toBeEnabled();fail=true;await page.getByLabel('ترقيم صفحات المخرجات').getByRole('button',{name:'التالي'}).click();await expect(page.getByRole('alert').filter({hasText:'تعذر تحميل المخرجات:'})).toBeVisible({timeout:15000});await expect(batch.getByRole('status')).toHaveText('24 محدد للمراجعة');await expect(batch.getByRole('button',{name:'معاينة الدفعة المحفوظة (24)',exact:true})).toBeDisabled();
 fail=false;await page.getByRole('button',{name:'إعادة قراءة مكتبة المحتوى',exact:true}).click();await expect(batch.getByRole('button',{name:'معاينة الدفعة المحفوظة (24)',exact:true})).toBeEnabled();
 await page.getByLabel('بحث في المخرجات',{exact:true}).fill('مادة');await expect(batch.getByRole('status')).toHaveText('0 محدد للمراجعة');
 expect(writes).toEqual([]);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();await page.screenshot({path:info.outputPath(`review-selection-${width}.png`)});
});
