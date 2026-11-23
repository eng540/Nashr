import {test,expect} from '@playwright/test';
test('central copies preserve original, edit one platform and keep execution separate',async({page},info)=>{
 let saves=0,unsafe=0;
 const item={id:'copy-source',source_knowledge_unit_id:'u',kind:'TEXT',status:'AVAILABLE',content:'الأصل المعتمد',storage_uri:null,mime_type:'text/plain',metadata:{title:'مادة مركزية'},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'};
 const copies=['telegram','youtube','instagram','x','facebook','tiktok'].map(platform=>({platform,label:platform,fields:{title:'عنوان المادة',description:item.content,tags:[],alt_text:''},version:1,source_fingerprint:'v1',current_source_fingerprint:'v1',origin:'UNCHANGED_ORIGINAL',source_stale:false,central_approval:'APPROVED',field_status:platform==='telegram'?'FIELDS_VALIDATED':'BLOCKED',blockers:platform==='telegram'?[]:['نوع المادة غير مؤهل لهذه المنصة.'],warnings:[],media_checks_pending:['فحص الوسائط النهائي لم ينفذ.'],execution_blockers:['لا إذن تنفيذ من الحفظ.'],sources:['https://core.telegram.org/bots/api']}));
 await page.route('**/*',async route=>{const req=route.request(),p=new URL(req.url()).pathname;
 if(p==='/api/artifacts')return route.fulfill({json:{items:[item],total:1,limit:100,offset:0}});
 if(p==='/api/artifacts/copy-source/platform-copies')return route.fulfill({json:{items:copies}});
 if(p==='/api/artifacts/copy-source/platform-copies/telegram'){saves++;const payload=req.postDataJSON();expect(payload.version).toBe(1);expect(payload.fields.description).toBe('نسخة Telegram مختلفة');return route.fulfill({json:{...copies[0],fields:payload.fields,version:2,origin:'USER_EDITED'}});}
 if(p.startsWith('/api/')&&req.method()!=='GET')unsafe++;
 if(['/posts','/sources','/api/control/'].some(x=>p.startsWith(x)))return route.fulfill({json:[]});return route.continue();});
 await page.goto('/bank?library_view=expanded');await page.getByLabel('حالة مراجعة المخرجات').selectOption('APPROVED');
 const panel=page.getByLabel('نسخ المنصات copy-source',{exact:true});await panel.locator('summary').first().click();
 await panel.getByRole('button',{name:'عرض النسخ المحفوظة',exact:true}).click();await expect(panel.getByLabel('وصف نسخة copy-source',{exact:true})).toHaveValue(item.content);
 await panel.getByLabel('وصف نسخة copy-source',{exact:true}).fill('نسخة Telegram مختلفة');await expect(panel.getByLabel('منصة النسخة copy-source',{exact:true})).toBeDisabled();
 await panel.getByRole('button',{name:'حفظ النسخة وفحص حقولها',exact:true}).click();await expect(panel.getByRole('status')).toContainText('حقول النسخة فقط');expect(saves).toBe(1);expect(unsafe).toBe(0);
 await panel.getByLabel('منصة النسخة copy-source',{exact:true}).selectOption('youtube');await expect(panel.getByLabel('وصف نسخة copy-source',{exact:true})).toHaveValue(item.content);
 await panel.getByLabel('منصة النسخة copy-source',{exact:true}).selectOption('telegram');
 await panel.getByRole('button',{name:'معاينة وجدولة نسخة Telegram هذه',exact:true}).click();
 await expect(page.getByLabel('معاينة دفعة Telegram',{exact:true})).toBeVisible();
 await panel.getByText('ما الذي لم يُتحقق بعد؟',{exact:true}).click();await expect(panel.getByText('لا إذن تنفيذ من الحفظ.',{exact:true})).toBeVisible();
 await page.addStyleTag({content:'header {visibility:hidden}'});
 await page.setViewportSize({width:390,height:844});await panel.screenshot({path:info.outputPath('central-copies-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.setViewportSize({width:1280,height:900});await panel.screenshot({path:info.outputPath('central-copies-desktop.png')});
});
