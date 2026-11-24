import {test,expect} from '@playwright/test';
test('calendar failure is not shown as empty and mixed items open their plan',async({page},info)=>{
 let fail=true;
 await page.route('**/*',async route=>{const p=new URL(route.request().url()).pathname;
 if(['/schedules/calendar','/schedules/upcoming'].includes(p))return fail?route.fulfill({status:500,json:{detail:'unavailable'}}):route.fulfill({json:{timezone:'Asia/Riyadh',date:'2026-11-24',days:7,items:[{id:'image',item_id:'image',schedule_id:'mixed-plan',schedule_name:'خطة متنوعة',artifact_id:'a',post_id:null,title:'صورة معتمدة',status:'PENDING',scheduled_at:'2026-11-24T12:00:00Z',timezone:'Asia/Riyadh'},{id:'post',item_id:'post',schedule_id:'mixed-plan',schedule_name:'خطة متنوعة',artifact_id:null,post_id:'p',title:'منشور معتمد',status:'PENDING',scheduled_at:'2026-11-24T12:15:00Z',timezone:'Asia/Riyadh'}]}});
 if(p==='/api/artifacts/platform-variants')return route.fulfill({json:[]});
 if(p==='/posts/filter-options')return route.fulfill({json:{sources:[],kinds:[]}});
 if(p==='/schedules/mixed-plan')return route.fulfill({json:{id:'mixed-plan',name:'خطة متنوعة',status:'DRAFT',timezone:'Asia/Riyadh',items:[]}});
 if(['/schedules','/posts','/sources','/api/artifacts','/api/publishing-queue'].some(x=>p.startsWith(x)))return route.fulfill({json:{items:[],total:0}});return route.continue();});
 await page.goto('/publishing');await page.getByRole('button',{name:/التقويم/}).first().click();
 await expect(page.getByRole('alert').filter({hasText:'تعذر تحميل التقويم'})).toBeVisible({timeout:15000});
 await expect(page.getByText('لا توجد منشورات مجدولة لهذا اليوم.',{exact:true})).toHaveCount(0);
 await page.setViewportSize({width:390,height:844});await page.getByTestId('publishing-calendar').screenshot({path:info.outputPath('calendar-error-mobile.png')});
 fail=false;await page.reload();await page.getByRole('button',{name:/التقويم/}).first().click();
 await expect(page.getByText('صورة معتمدة',{exact:true}).first()).toBeVisible();await expect(page.getByText('منشور معتمد',{exact:true}).first()).toBeVisible();
 await page.getByTestId('publishing-calendar').screenshot({path:info.outputPath('calendar-mixed-mobile.png')});
 await page.getByRole('button').filter({hasText:'صورة معتمدة'}).first().click();await expect(page.getByRole('heading',{name:'خطة متنوعة',exact:true})).toBeVisible();
});
