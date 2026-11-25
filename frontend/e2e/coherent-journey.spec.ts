import {test,expect} from '@playwright/test';
test('sources to review to results share a clear shell and preserve review gates',async({page},info)=>{
 let writes=0;const id='00000000-0000-4000-8000-000000000059';
 await page.route('**/*',async route=>{const r=route.request(),p=new URL(r.url()).pathname;if(r.method()!=='GET')writes++;
 if(p==='/sources')return route.fulfill({json:[{id:'pdf',filename:'كتاب طويل بعنوان هندسي.pdf',book_title:'كتاب هندسي',mime_type:'application/pdf',status:'STORED',material_count:0},{id:'video',filename:'video.mp4',book_title:'ملف فيديو',mime_type:'video/mp4',status:'STORED',material_count:1}]});
 if(p==='/api/artifacts')return route.fulfill({json:{items:[{id,kind:'VIDEO',review_status:'DRAFT',status:'AVAILABLE',content:null,mime_type:'video/mp4',storage_uri:null,metadata:{caption:'مادة للمراجعة لا تنشر تلقائياً',source_type:'MEDIA_BANK_UPLOAD',review_notes:['راجع السلامة والمصدر قبل الاعتماد']}}],total:1}});
 if(p.endsWith('/distribution-readiness'))return route.fulfill({json:{artifact_id:id,selection_version:'1',central_approval:'DRAFT',targets:[{platform:'telegram',label:'Telegram',selected:false,copy_status:'BLOCKED',copy_blockers:['راجع الاعتماد'],execution_blockers:[]}]}});
 if(p.includes('/control/'))return route.fulfill({json:[]});
 if(p==='/api/artifacts/platform-variants')return route.fulfill({json:[]});
 if(['/posts','/schedules','/api/'].some(x=>p.startsWith(x)))return route.fulfill({json:{items:[],total:0,sources:[],topics:[],kinds:[]}});return route.continue();});
 await page.setViewportSize({width:390,height:844});await page.goto('/sources/library');await expect(page.getByTestId('source-card-pdf')).toBeVisible();await expect(page.getByTestId('source-card-video')).toHaveCount(0);await expect(page.getByText('الرفع وحده لا يبدأ التحليل.',{exact:false})).toBeVisible();
 await page.getByLabel('إظهار بقية الملفات والمصادر دون حذفها').check();await expect(page.getByTestId('source-card-video')).toBeVisible();await expect(page.getByTestId('source-card-video').getByRole('button',{name:'عرض بنية الكتاب'})).toHaveCount(0);
 await page.getByRole('navigation',{name:'رحلة المحتوى'}).getByRole('link',{name:'3.المراجعة والوجهات'}).click();await page.getByRole('button',{name:'فتح المادة والتجهيز والتتبع',exact:true}).click();await page.getByRole('link',{name:'2. قرار المراجعة',exact:true}).click();await expect(page.getByRole('button',{name:'اعتماد المادة فقط، دون نشر',exact:true})).toBeVisible();
 await page.getByRole('link',{name:'3. النسخ والوجهات والخطة',exact:true}).click();await page.getByRole('button',{name:'فحص جاهزية واختيار المنصات (1)',exact:true}).click();await expect(page.getByText('راجع المادة واعتمدها أولاً',{exact:true})).toBeVisible();await page.getByRole('link',{name:'2. قرار المراجعة',exact:true}).click();await page.getByRole('region',{name:'قرار مراجعة المادة'}).scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath('journey-review-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.setViewportSize({width:1280,height:900});await page.getByRole('region',{name:'قرار مراجعة المادة'}).scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath('journey-review-desktop.png')});await page.getByRole('navigation',{name:'رحلة المحتوى'}).getByRole('link',{name:'4.الجدولة والنتائج'}).click();await expect(page.getByTestId('publishing-workspace')).toBeVisible();expect(writes).toBe(0);
});

test('selected plan immediately reveals readable details near the viewport',async({page},info)=>{
 await page.setViewportSize({width:390,height:844});
 await page.route('**/*',async route=>{const p=new URL(route.request().url()).pathname;
 if(p==='/schedules')return route.fulfill({json:{items:Array.from({length:20},(_,i)=>({id:String(i),name:'خطة محفوظة '+i,status:'COMPLETED',timezone:'Asia/Riyadh',total_items:1,published_items:1,failed_items:0})),total:20}});
 if(p==='/schedules/0')return route.fulfill({json:{id:'0',name:'خطة محفوظة 0',status:'COMPLETED',timezone:'Asia/Riyadh',total_items:1,published_items:1,failed_items:0,items:[{id:'item',position:1,title:'مادة تاريخية',status:'PUBLISHED',content_preview:'نص قديم محفوظ',scheduled_at:'2026-01-01T00:00:00Z',attempts:1}]}});
 if(p==='/api/artifacts/platform-variants')return route.fulfill({json:[]});
 if(['/posts','/schedules/','/api/'].some(x=>p.startsWith(x)))return route.fulfill({json:{items:[],total:0,sources:[],kinds:[]}});return route.continue();});
 await page.goto('/publishing');await page.getByRole('button',{name:/خطط النشر/}).first().click();await page.getByRole('button',{name:/خطة محفوظة 0/}).click();const detail=page.getByTestId('schedule-detail');await expect(detail).toBeInViewport();await expect(detail).toContainText('مكتملة');await expect(detail).toContainText('مادة تاريخية');await detail.screenshot({path:info.outputPath('selected-plan-mobile.png')});
});
