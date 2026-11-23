import {test,expect} from '@playwright/test';
test('schedule time changes require explicit save and survive a failed save',async({page},info)=>{
 let updates=0;let fail=true;
 const detail={id:'plan',name:'خطة اصطناعية',status:'DRAFT',timezone:'Asia/Riyadh',total_items:1,published_items:0,failed_items:0,items:[{id:'item',post_id:null,artifact_id:'artifact',position:1,title:'مادة الاختبار',status:'PENDING',content_preview:'معاينة النص',scheduled_at:'2026-12-05T10:00:00Z'}]};
 await page.route('**/*',async route=>{const request=route.request();const p=new URL(request.url()).pathname;
 if(p==='/schedules/plan/items/item'){updates++;if(fail)return route.fulfill({status:409,json:{detail:'اختبار تعارض'}});return route.fulfill({json:detail});}
 if(p==='/schedules/plan')return route.fulfill({json:detail});
 if(p==='/schedules')return route.fulfill({json:{items:[detail]}});
 if(p==='/schedules/upcoming'||p==='/schedules/calendar')return route.fulfill({json:{items:[]}});
 if(p==='/api/artifacts')return route.fulfill({json:{items:[],total:0}});
 if(p==='/api/artifacts/platform-variants')return route.fulfill({json:[]});
 if(p.startsWith('/posts'))return route.fulfill({json:{items:[],total:0,kinds:[],topics:[],sources:[]}});
 return route.continue();});
 await page.goto('/publishing');await page.getByRole('button',{name:/خطط النشر/}).click();await page.getByRole('button',{name:/خطة اصطناعية/}).click();
 const input=page.getByLabel('وقت نشر مادة الاختبار');await input.fill('2026-12-06T14:00');await input.blur();expect(updates).toBe(0);
 await page.getByRole('button',{name:'حفظ الموعد',exact:true}).click();await expect(page.getByText('اختبار تعارض',{exact:true})).toBeVisible();await expect(input).toHaveValue('2026-12-06T14:00');expect(updates).toBe(1);
 await page.setViewportSize({width:390,height:844});await input.scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath('explicit-save-mobile.png')});
});
