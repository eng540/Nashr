import {test,expect} from '@playwright/test';
test('library bulk selection declares 100 item boundary without silently selecting the rest',async({page},info)=>{
 const items=Array.from({length:104},(_,index)=>({id:`video-${index}`,source_knowledge_unit_id:'u',kind:'VIDEO',status:'AVAILABLE',content:null,storage_uri:'s3://synthetic/video.mp4',mime_type:'video/mp4',metadata:{title:`فيديو ${index}`,caption:'وصف كامل'},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'}));
 await page.route('**/*',async route=>{const p=new URL(route.request().url()).pathname;if(p.endsWith('/media-url'))return route.fulfill({json:{url:null}});if(p==='/api/artifacts')return route.fulfill({json:{items,total:104,limit:100,offset:0}});if(['/posts','/sources','/api/control/'].some(x=>p.startsWith(x)))return route.fulfill({json:[]});return route.continue();});
 await page.goto('/bank');await page.getByLabel('حالة مراجعة المخرجات').selectOption('APPROVED');await page.getByRole('button',{name:'تحديد النتائج المؤهلة (حتى 100)',exact:true}).click();
 await expect(page.getByTestId('media-selection-count')).toHaveText('100 محدد');await expect(page.getByRole('status').filter({hasText:'لم تُحدّد بقية النتائج'})).toContainText('لم تُحدّد بقية النتائج');
 await expect(page.getByRole('button',{name:'تجهيز نسخ المنصات للمحدد (100)',exact:true})).toBeVisible();
 await page.addStyleTag({content:'header {visibility:hidden}'});await page.setViewportSize({width:390,height:844});await page.getByLabel('معاينة دفعة Telegram',{exact:true}).screenshot({path:info.outputPath('bounded-batch-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
