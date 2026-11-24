import {test,expect} from '@playwright/test';
test('explicit catalog labels organize originals without publishing or editing their content',async({page},info)=>{
 const items=['one','two'].map(id=>({id,source_knowledge_unit_id:'u',kind:'TEXT',status:'AVAILABLE',content:'الأصل الكامل '+id,storage_uri:null,mime_type:'text/plain',metadata:{title:'مادة '+id,original_filename:'b3v4-'+id},organization:null as null|{title:string;series:string;category:string;version:number;updated_at:string},review_status:'DRAFT',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'}));
 const writes:string[]=[];
 await page.route('**/*',async route=>{const r=route.request(),p=new URL(r.url()).pathname;
 if(p==='/api/artifacts/organization'){
  writes.push(p);const b=r.postDataJSON();expect(b.artifact_ids).toEqual(['one','two']);expect(b.fields).toEqual({series:'حملة صريحة'});expect(b.versions).toEqual({one:0,two:0});
  items.forEach(i=>i.organization={title:'',series:'حملة صريحة',category:'',version:1,updated_at:'2026-11-24T10:00:00Z'});return route.fulfill({json:{updated:2,content_changed:false,schedules_changed:false}});
 }
 if(p==='/api/artifacts')return route.fulfill({json:{items,total:2,limit:100,offset:0}});
 if(['/posts','/sources','/api/control/'].some(x=>p.startsWith(x)))return route.fulfill({json:[]});return route.continue();});
 await page.setViewportSize({width:390,height:844});await page.goto('/bank');
 await page.getByText('تنظيم جماعي · تحديد الفهرسة والسلاسل والتصنيفات',{exact:true}).click();await page.getByRole('button',{name:'تحديد صفحة الفهرسة',exact:true}).click();const batch=page.getByLabel('تنظيم الدفعة',{exact:true});await batch.locator('summary').click();
 await batch.getByLabel('تطبيق السلسلة على المحدد',{exact:true}).check();await batch.getByLabel('سلسلة الفهرسة',{exact:true}).fill('حملة صريحة');
 await expect(batch.getByRole('button',{name:'حفظ بيانات الفهرسة',exact:true})).toBeDisabled();await batch.getByLabel('راجعت تنظيم 2 مادة، دون تغيير المحتوى أو النشر',{exact:true}).check();await batch.getByRole('button',{name:'حفظ بيانات الفهرسة',exact:true}).click();
 await expect(batch.getByRole('status')).toContainText('حُفظ تنظيم 2 مادة');expect(writes).toEqual(['/api/artifacts/organization']);
 await page.getByText('تصفية وترتيب · النوع، المصدر، السلسلة، التصنيف',{exact:true}).click();await page.getByLabel('تصفية حسب السلسلة',{exact:true}).selectOption('حملة صريحة');await expect(page.getByRole('heading',{name:'مادة one',exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'مادة two',exact:true})).toBeVisible();
 await expect(page.getByLabel('حالة مراجعة المخرجات')).toHaveValue('DRAFT');expect(items.map(i=>i.content)).toEqual(['الأصل الكامل one','الأصل الكامل two']);
 await batch.scrollIntoViewIfNeeded();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();await page.screenshot({path:info.outputPath('organization-mobile.png')});
 await page.getByRole('button',{name:'إلغاء تحديد الفهرسة',exact:true}).click();await page.getByRole('button',{name:'فتح المادة والتجهيز والتتبع',exact:true}).first().click();
 const single=page.getByLabel('تنظيم المادة',{exact:true});await single.locator('summary').click();await expect(single.getByLabel('عنوان الفهرسة',{exact:true})).toBeVisible();await expect(single.getByLabel('سلسلة الفهرسة',{exact:true})).toHaveValue('حملة صريحة');
 await page.setViewportSize({width:1280,height:1000});await single.scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath('organization-desktop.png')});
});
