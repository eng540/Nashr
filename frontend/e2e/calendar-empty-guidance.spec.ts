import {test,expect} from '@playwright/test';
for(const width of [320,390,1280])test(`empty Telegram calendar points to the actual Meta views at ${width}px`,async({page},info)=>{
 const writes:string[]=[];let upcomingFail=false;
 await page.route('**/*',r=>{const u=new URL(r.request().url()),p=u.pathname;if(r.request().method()!=='GET'){writes.push(p);return r.abort();}
 if(p==='/schedules/upcoming')return upcomingFail?r.fulfill({status:503,json:{detail:'unavailable'}}):r.fulfill({json:{items:[],total:0}});
 if(p==='/schedules/calendar')return r.fulfill({json:{items:[],total:0,date:'2032-01-02',timezone:'Asia/Riyadh'}});
 if(p==='/api/platform-operations')return r.fulfill({json:{items:[],total:0,counts:{waiting:0,published:0,attention:0,total:0}}});
 if(p.startsWith('/api/')||p.startsWith('/schedules')||p.startsWith('/posts'))return r.fulfill({json:{items:[],total:0}});return r.continue();});
 await page.setViewportSize({width,height:844});await page.goto('/publishing?view=calendar&calendar_date=2032-01-02&calendar_timezone=Asia%2FRiyadh');
 const upcoming=page.getByLabel('قادم Telegram المقسم',{exact:true}),day=page.getByLabel('تقويم Telegram المقسم',{exact:true});
 await expect(upcoming).toContainText('لا توجد عناصر Telegram في قائمة الأيام السبعة القادمة.');
 for(const panel of [upcoming,day]){await expect(panel).toContainText('مواعيد Instagram وFacebook لليوم المختار تظهر في تقويم Meta أدناه، وسجلها الكامل في قسم «عمليات Meta».');await expect(panel).not.toContainText('تظهر في خطط النشر');}
 await expect(page.getByLabel('تقويم Instagram وFacebook',{exact:true})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.getByTestId('publishing-calendar').screenshot({path:info.outputPath('calendar-guidance-'+width+'.png'),style:'header,a[href$="#main-content"]{visibility:hidden}'});
 await page.getByRole('button',{name:/^عمليات Meta 0/}).click();await expect(page).toHaveURL(/view=operations/);await expect(page.getByTestId('publishing-operations')).toBeVisible();
 upcomingFail=true;await page.goto('/publishing?view=calendar&calendar_date=2032-01-02&calendar_timezone=Asia%2FRiyadh');await expect(upcoming.getByRole('alert')).toContainText('تعذر تحميل القادم');await expect(upcoming).not.toContainText('لا توجد عناصر Telegram');expect(writes).toEqual([]);
});
