import {test,expect} from '@playwright/test';
test('read only publication ledger shows destination all message ids and attempts',async({page},info)=>{
 let writes=0;
 const item={id:'audit',source_knowledge_unit_id:'u',kind:'TEXT',status:'AVAILABLE',content:'نص اصطناعي',storage_uri:null,mime_type:'text/plain',metadata:{title:'عنصر الاختبار'},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'};
 await page.route('**/*',async route=>{const request=route.request();const p=new URL(request.url()).pathname;
 if(p.startsWith('/api/')&&request.method()!=='GET')writes++;
 if(p==='/api/artifacts')return route.fulfill({json:{items:[item],total:1,limit:100,offset:0}});
 if(p==='/api/artifacts/audit/publications')return route.fulfill({json:{connector_items:[{id:'ig-result',record_type:'INSTAGRAM_EXECUTION',platform:'instagram',destination:'123456',status:'PUBLISHED',content:'النص المحفوظ للموصل',external_id:'7890',permalink:'https://www.instagram.com/reel/Verified_1/',confirmed:true,updated_at:'2026-11-25T03:00:00Z'}],total:1,items:[{id:'ledger-id',platform:'telegram',destination:'synthetic-private-channel',status:'PUBLISHED',content:'النص المرسل',external_ids:['test-1','test-2'],error_message:null,published_at:'2026-11-23T20:00:00Z',schedules:[{schedule_id:'test-schedule',name:'جدول تجريبي',schedule_status:'COMPLETED',item_status:'PUBLISHED',attempts:1,scheduled_at:'2026-11-23T20:00:00Z'}]}]}});
 if(['/posts','/sources','/api/control/'].some(x=>p.startsWith(x)))return route.fulfill({json:[]});return route.continue();});
 await page.goto('/bank?library_view=expanded');await page.getByLabel('حالة مراجعة المخرجات').selectOption('APPROVED');
 await page.getByRole('button',{name:'عرض وتحديث سجل النشر',exact:true}).click();
 const ledger=page.getByLabel('سجل نشر المخرج audit',{exact:true});
 await expect(ledger.getByText('synthetic-private-channel',{exact:true})).toBeVisible();
 await expect(ledger.getByText('test-1, test-2',{exact:true})).toBeVisible();
 await ledger.getByText('النص المحفوظ في سجل النشر',{exact:true}).click();await expect(ledger.getByText('النص المرسل',{exact:true})).toBeVisible();
 await expect(ledger.getByRole('link',{name:'فتح نتيجة النشر المثبتة'})).toHaveAttribute('href','https://www.instagram.com/reel/Verified_1/');await expect(ledger).toContainText('سجل الموصل المستقل');
 await ledger.screenshot({path:info.outputPath('ledger-desktop.png')});
 await page.setViewportSize({width:390,height:844});await ledger.scrollIntoViewIfNeeded();await ledger.screenshot({path:info.outputPath('ledger-mobile.png')});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.getByRole('button',{name:'عرض وتحديث سجل النشر',exact:true}).click();expect(writes).toBe(0);
});

 test('connector-only publication history never labels the proven result as missing',async({page})=>{
 const item={id:'connector-only',kind:'TEXT',status:'AVAILABLE',content:'أصل',metadata:{title:'مادة'},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'};
 await page.route('**/*',async route=>{const r=route.request(),p=new URL(r.url()).pathname;expect(r.method()).toBe('GET');
 if(p==='/api/artifacts')return route.fulfill({json:{items:[item],total:1,limit:100,offset:0}});
 if(p==='/api/artifacts/connector-only/publications')return route.fulfill({json:{total:0,items:[],connector_items:[{id:'ig',record_type:'INSTAGRAM_EXECUTION',platform:'instagram',destination:'synthetic',status:'PUBLISHED',content:'أصل',external_id:'123',permalink:null,confirmed:true,updated_at:'2026-11-23T20:00:00Z'}]}});
 if(p.startsWith('/api/'))return route.fulfill({json:p.includes('/control/')?[]:{items:[],total:0}});if(['/posts','/sources'].some(x=>p.startsWith(x)))return route.fulfill({json:[]});return route.continue();});
 await page.goto('/bank?artifact_status=APPROVED&library_view=expanded');const ledger=page.getByLabel('سجل نشر المخرج connector-only',{exact:true});await ledger.getByRole('button',{name:'عرض وتحديث سجل النشر',exact:true}).click();await expect(ledger).toContainText('نتائج الموصلات المستقلة: 1 نتيجة');await expect(ledger).toContainText('لا سجلات نشر عامة في هذه الصفحة');await expect(ledger.getByText('لا سجلات في هذه الصفحة',{exact:true})).toHaveCount(0);await expect(ledger).toContainText('نتيجة مثبتة');
 });
