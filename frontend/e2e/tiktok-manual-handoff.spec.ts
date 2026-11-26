import {test,expect} from '@playwright/test';
test('manual TikTok handoff exports saved copy without upload or publication',async({page},info)=>{
 const writes:string[]=[];let downloads=0;
 const item={id:'manual-video',source_knowledge_unit_id:'u',kind:'VIDEO',status:'AVAILABLE',content:null,storage_uri:'s3://private/original.mp4',mime_type:'video/mp4',metadata:{caption:'الوصف الأصلي',title:'فيديو للمراجعة'},review_status:'APPROVED',created_at:'2026-11-26T08:00:00Z',updated_at:'2026-11-26T08:00:00Z'};
 const copy={platform:'tiktok',label:'TikTok',fields:{title:'عنوان منفصل',description:'الوصف المحفوظ دون قص',tags:['وسم'],alt_text:''},version:3,source_fingerprint:'a'.repeat(64),current_source_fingerprint:'a'.repeat(64),origin:'USER_EDITED',source_stale:false,central_approval:'APPROVED',selected_media_id:null,field_status:'BLOCKED',blockers:['متطلبات TikTok النهائية غير متحققة.'],warnings:[],media_checks_pending:[],execution_blockers:['لا إذن نشر.'],sources:[]};
 await page.route('**/*',async route=>{const r=route.request(),p=new URL(r.url()).pathname;
 if(!p.startsWith('/api/')){if(['/posts','/sources'].some(x=>p.startsWith(x)))return route.fulfill({json:[]});return route.continue();}
 if(p.startsWith('/api/control/'))return route.fulfill({json:[]});
 if(r.method()!=='GET'){writes.push(p);throw new Error('Unexpected write '+p);}
 if(p==='/api/artifacts')return route.fulfill({json:{items:[item],total:1,limit:100,offset:0}});
 if(p==='/api/artifacts/manual-video/platform-copies')return route.fulfill({json:{items:[copy]}});
 if(p.endsWith('/manual-bundle')){downloads++;expect(new URL(r.url()).searchParams.get('copy_version')).toBe('3');return route.fulfill({contentType:'application/zip',headers:{'Content-Disposition':'attachment; filename="manual.zip"'},body:'synthetic-download-fixture'});}
 if(p.endsWith('/media-inspections'))return route.fulfill({json:{items:[]}});
 return route.fulfill({json:{items:[]}});
 });
 await page.setViewportSize({width:390,height:844});await page.goto('/bank?artifact_id=manual-video&artifact_status=APPROVED&copy_platform=tiktok');
 const copies=page.getByLabel('نسخ المنصات manual-video',{exact:true});const panel=copies.getByLabel('تسليم TikTok اليدوي',{exact:true});
 await expect(panel).toBeVisible();await expect(panel).toContainText('لا تصل إلى TikTok ولا تسجل نشرًا');
 await panel.screenshot({path:info.outputPath('tiktok-manual-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 const pending=page.waitForEvent('download');await panel.getByRole('link',{name:'تنزيل حزمة TikTok خاصة دون رفع أو نشر',exact:true}).click();expect((await pending).suggestedFilename()).toBe('manual.zip');expect(downloads).toBe(1);expect(writes).toEqual([]);
 await copies.getByLabel('وصف نسخة manual-video',{exact:true}).fill('تعديل غير محفوظ');await expect(panel.getByRole('link')).toHaveCount(0);
 await page.setViewportSize({width:1280,height:900});await panel.screenshot({path:info.outputPath('tiktok-manual-unsaved-desktop.png')});
});
