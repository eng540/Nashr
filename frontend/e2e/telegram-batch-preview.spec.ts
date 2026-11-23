import {test,expect} from '@playwright/test';
test('batch preflight shows actual destination, full text and blockers without writes',async({page},info)=>{
 let previews=0,unsafe=0;
 const item={id:'batch-original',source_knowledge_unit_id:'u',kind:'TEXT',status:'AVAILABLE',content:'نص المادة الأصلي الكامل دون قص',storage_uri:null,mime_type:'text/plain',metadata:{title:'مادة تجريبية'},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'};
 await page.route('**/*',async route=>{const req=route.request(),p=new URL(req.url()).pathname;
 if(p==='/api/artifacts/telegram-batch-preview'){previews++;return route.fulfill({json:{destination:'synthetic-private-target',ready_count:0,blocked_count:1,caveat:'فحص نصي أولي، لا يمنح إذن نشر.',items:[{artifact_id:item.id,title:'مادة تجريبية',kind:'TEXT',content:item.content,ready:false,blockers:['Telegram مستبعد من الوجهات المحفوظة لهذه المادة.'],publications:[],schedules:[]}]}});}
 if(p.startsWith('/api/')&&req.method()!=='GET')unsafe++;
 if(p==='/api/artifacts')return route.fulfill({json:{items:[item],total:1,limit:100,offset:0}});
 if(['/posts','/sources','/api/control/'].some(x=>p.startsWith(x)))return route.fulfill({json:[]});return route.continue();});
 await page.goto('/bank');await page.getByLabel('حالة مراجعة المخرجات').selectOption('APPROVED');
 await page.getByLabel('تحديد كل وسائط الصفحة',{exact:true}).check();
 const panel=page.getByLabel('معاينة دفعة Telegram',{exact:true});
 await panel.getByRole('button',{name:'معاينة وفحص دفعة Telegram (1)',exact:true}).click();
 await expect(panel.getByText('synthetic-private-target',{exact:true})).toBeVisible();
 await panel.locator('summary').click();await expect(panel.getByText(item.content,{exact:true})).toBeVisible();
 await expect(panel.getByText('Telegram مستبعد من الوجهات المحفوظة لهذه المادة.',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'إنشاء مسودات Telegram للمحدد (1)',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('تعذر تجهيز الدفعة');
 expect(previews).toBe(2);expect(unsafe).toBe(0);
 await panel.screenshot({path:info.outputPath('batch-desktop.png')});
 await page.setViewportSize({width:390,height:844});await panel.screenshot({path:info.outputPath('batch-mobile.png')});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});

test('reviewed batch saves a draft schedule only with Riyadh time and content fingerprints',async({page},info)=>{
 let saved=0,unsafe=0;
 const item={id:'batch-ready',source_knowledge_unit_id:'u',kind:'TEXT',status:'AVAILABLE',content:'نص معتمد لا يتغير',storage_uri:null,mime_type:'text/plain',metadata:{title:'مادة مؤهلة'},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'};
 await page.route('**/*',async route=>{const req=route.request(),p=new URL(req.url()).pathname;
 if(p==='/api/artifacts/telegram-batch-preview')return route.fulfill({json:{destination:'synthetic-target',ready_count:1,blocked_count:0,caveat:'فحص أولي.',items:[{artifact_id:item.id,title:'مادة مؤهلة',kind:'TEXT',content:item.content,source_fingerprint:'reviewed-fingerprint',ready:true,blockers:[],publications:[],schedules:[]}]}});
 if(p==='/api/artifacts/telegram-batch-schedule'){saved++;expect(req.postDataJSON()).toMatchObject({artifact_ids:[item.id],destination:'synthetic-target',fingerprints:{'batch-ready':'reviewed-fingerprint'},timezone:'Asia/Riyadh',start_at:'2030-01-01T09:00:00.000Z',interval_minutes:60});return route.fulfill({status:201,json:{id:'synthetic-draft-plan',status:'DRAFT',items:[]}});}
 if(p.startsWith('/api/')&&req.method()!=='GET')unsafe++;
 if(p==='/api/artifacts')return route.fulfill({json:{items:[item],total:1,limit:100,offset:0}});
 if(['/posts','/sources','/api/control/'].some(x=>p.startsWith(x)))return route.fulfill({json:[]});return route.continue();});
 await page.goto('/bank');await page.getByLabel('حالة مراجعة المخرجات').selectOption('APPROVED');await page.getByLabel('تحديد كل وسائط الصفحة',{exact:true}).check();
 const panel=page.getByLabel('معاينة دفعة Telegram',{exact:true});await panel.getByRole('button',{name:'معاينة وفحص دفعة Telegram (1)',exact:true}).click();
 await panel.getByText('حفظ خطة للدفعة دون تفعيل',{exact:true}).click();await page.getByLabel('بداية دفعة Telegram',{exact:true}).fill('2030-01-01T12:00');
 const save=panel.getByRole('button',{name:'حفظ خطة Telegram كمسودة',exact:true});await expect(save).toBeDisabled();await panel.getByRole('checkbox').check();await expect(save).toBeEnabled();
 await page.setViewportSize({width:390,height:844});await panel.screenshot({path:info.outputPath('batch-schedule-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await save.click();await expect(panel.getByRole('status')).toContainText('دون تفعيل');expect(saved).toBe(1);expect(unsafe).toBe(0);
});
