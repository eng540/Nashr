import {test,expect} from '@playwright/test';
test('calendar uses displayed local date and view timezone without altering plans',async({page},info)=>{
 await page.clock.install({time:new Date('2026-11-24T22:15:00Z')});let writes=0;
 await page.route('**/*',async route=>{const r=route.request(),u=new URL(r.url()),p=u.pathname;if(r.method()!=='GET')writes++;
 if(p==='/schedules/calendar')return route.fulfill({json:{date:u.searchParams.get('date'),timezone:u.searchParams.get('timezone'),items:[{id:'item',schedule_id:'plan',schedule_name:'خطة بمنطقة مختلفة',title:'مادة معتمدة',status:'PENDING',scheduled_at:'2026-11-25T00:15:00Z',timezone:'America/New_York'}]}});
 if(p==='/api/artifacts/platform-variants')return route.fulfill({json:[]});
 if(['/posts','/schedules','/api/artifacts','/api/publishing-queue'].some(x=>p.startsWith(x)))return route.fulfill({json:{items:[],total:0,sources:[],kinds:[]}});return route.continue();});
 await page.goto('/publishing');await page.getByRole('button',{name:/التقويم/}).first().click();const calendar=page.getByTestId('publishing-calendar');
 await expect(page.getByLabel('تاريخ التقويم')).toHaveValue('2026-11-25');await expect(calendar.getByText('مادة معتمدة',{exact:true})).toBeVisible();
 const response=page.waitForResponse(r=>r.url().includes('/schedules/calendar?')&&r.url().includes('Asia%2FRiyadh'));
 await page.getByLabel('منطقة عرض تقويم اليوم').fill('Asia/Riyadh');await page.getByRole('button',{name:'تطبيق منطقة العرض'}).click();await response;
 await expect(calendar).toContainText('Asia/Riyadh');await expect(calendar).toContainText(new Date('2026-11-25T00:15:00Z').toLocaleTimeString('ar',{hour:'2-digit',minute:'2-digit',timeZone:'Asia/Riyadh'}));
 await calendar.screenshot({path:info.outputPath('calendar-zone-desktop.png')});await page.setViewportSize({width:390,height:844});await calendar.screenshot({path:info.outputPath('calendar-zone-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.getByLabel('منطقة عرض تقويم اليوم').fill('invalid-zone');await page.getByRole('button',{name:'تطبيق منطقة العرض'}).click();await expect(page.getByRole('alert').filter({hasText:'منطقة زمنية غير صالحة'})).toBeVisible();expect(writes).toBe(0);
});
