import {test,expect} from '@playwright/test';
test('list selection recovers exact plan on reload back and forward without writes',async({page},info)=>{
 let writes=0,fail=false;const plan=(id:string)=>({id,name:'خطة '+id,status:'COMPLETED',timezone:'Asia/Riyadh',total_items:1,published_items:1,failed_items:0,items:[{id:'item-'+id,position:1,title:'مادة '+id,status:'PUBLISHED',scheduled_at:'2026-11-25T12:00:00Z',content_preview:'النص المحفوظ',publication_external_id:'2559',artifact_id:'artifact-'+id}]});
 await page.route('**/*',route=>{const r=route.request(),p=new URL(r.url()).pathname;if(r.method()!=='GET')writes++;
 if(p==='/schedules')return route.fulfill({json:{items:[plan('A'),plan('B')],total:2}});
 if(p==='/schedules/A'||p==='/schedules/B')return fail?route.fulfill({status:503,json:{detail:'read unavailable'}}):route.fulfill({json:plan(p.endsWith('A')?'A':'B')});
 if(p==='/api/artifacts/platform-variants')return route.fulfill({json:[]});
 if(['/api/','/posts','/sources','/schedules/'].some(x=>p.startsWith(x)))return route.fulfill({json:{items:[],total:0,sources:[],kinds:[],counts:{waiting:0,published:0,attention:0}}});return route.continue();});
 await page.setViewportSize({width:390,height:844});await page.goto('/publishing?view=plans&failures=1');
 await page.getByRole('button',{name:/خطة A/}).click();await expect(page).toHaveURL(/schedule_id=A/);await expect(page).toHaveURL(/failures=1/);await expect(page.getByTestId('schedule-detail')).toContainText('خطة A');
 await page.reload();await expect(page.getByTestId('schedule-detail')).toContainText('خطة A');await page.getByRole('button',{name:/خطة B/}).click();await expect(page).toHaveURL(/schedule_id=B/);await expect(page.getByTestId('schedule-detail')).toContainText('خطة B');
 await page.goBack();await expect(page.getByTestId('schedule-detail')).toContainText('خطة A');await page.goForward();await expect(page.getByTestId('schedule-detail')).toContainText('خطة B');
 await page.getByRole('button',{name:/التقويم · كل المنصات/}).click();await expect(page).toHaveURL(/view=calendar/);await expect(page).not.toHaveURL(/schedule_id/);await page.reload();await expect(page.getByTestId('publishing-calendar')).toBeVisible();
 await page.goBack();await expect(page.getByTestId('schedule-detail')).toContainText('خطة B');fail=true;await page.reload();await expect(page.getByRole('alert').filter({hasText:'تعذر تحميل تفاصيل الخطة المختارة'})).toBeVisible();await expect(page).toHaveURL(/schedule_id=B/);await expect(page.getByTestId('schedule-detail')).toHaveCount(0);fail=false;await page.getByRole('button',{name:'إعادة تحميل تفاصيل الخطة'}).click();await expect(page.getByTestId('schedule-detail')).toContainText('خطة B');
 await page.getByTestId('schedule-detail').scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath('exact-plan-reload-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();expect(writes).toBe(0);
});
