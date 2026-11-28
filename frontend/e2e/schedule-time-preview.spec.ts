import {test,expect} from '@playwright/test';
test('schedule previews exact elapsed instants without activating or saving',async({page},info)=>{
 let writes=0;
 await page.route('**/*',async route=>{const r=route.request(),p=new URL(r.url()).pathname;if(r.method()!=='GET')writes++;
 if(p==='/schedules/eligibility')return route.fulfill({json:{eligible_ids:['a','b'],blocked:[]}});
 if(p==='/posts')return route.fulfill({json:{items:[{post_id:'a',title:'المادة الأولى',status:'APPROVED',content:'نص معتمد',content_preview:'نص معتمد',published:false},{post_id:'b',title:'المادة الثانية',status:'APPROVED',content:'نص معتمد',content_preview:'نص معتمد',published:false}],total:2}});
 if(p==='/api/artifacts/platform-variants')return route.fulfill({json:[]});
 if(['/posts/','/schedules','/api/artifacts','/api/publishing-queue'].some(x=>p.startsWith(x)))return route.fulfill({json:{items:[],total:0,sources:[],kinds:[]}});return route.continue();});
 await page.goto('/publishing?selected_post_ids=a,b');await page.getByTestId('create-plan').click();const panel=page.getByTestId('schedule-panel');await expect(panel).toBeVisible();
 await expect(page.getByTestId('submit-schedule')).toBeDisabled();await page.getByLabel('المنطقة الزمنية',{exact:true}).fill('America/New_York');await page.getByLabel('وقت البداية').fill('2027-03-14T01:30');await page.getByLabel('الفاصل بالدقائق').fill('30');
 const preview=page.getByLabel('معاينة مواعيد الخطة');await expect(preview).toContainText('2027-03-14T06:30:00.000Z');await expect(preview).toContainText('2027-03-14T07:00:00.000Z');await expect(preview).toContainText('2027-03-14T03:00');await expect(page.getByTestId('submit-schedule')).toBeEnabled();
 await panel.screenshot({path:info.outputPath('schedule-preview-desktop.png')});await page.setViewportSize({width:390,height:844});await panel.screenshot({path:info.outputPath('schedule-preview-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.getByLabel('وقت البداية').fill('2027-03-14T02:30');await expect(preview.getByRole('alert')).toBeVisible();await expect(page.getByTestId('submit-schedule')).toBeDisabled();expect(writes).toBe(0);
});
