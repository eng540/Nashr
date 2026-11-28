import {test,expect} from '@playwright/test';
for(const width of [390,1280]) test(`failed plan create is visible and preserves input ${width}`,async({page},info)=>{
 let writes=0;
 await page.setViewportSize({width,height:844});
 await page.route('**/*',async r=>{const q=r.request(),p=new URL(q.url()).pathname;
 if(p==='/schedules'&&q.method()==='POST'){writes++;return r.fulfill({status:409,json:{detail:'تعارض حجز المادة. أعد فحص الأهلية.'}});}
 if(p==='/schedules/eligibility')return r.fulfill({json:{eligible_ids:['one'],blocked:[]}});
 if(q.method()!=='GET')return r.fulfill({status:500,json:{}});
 if(p==='/sources'||p.startsWith('/api/control/'))return r.fulfill({json:[]});
 if(p.startsWith('/api/')||p.startsWith('/posts')||p.startsWith('/schedules'))return r.fulfill({json:{items:[],total:0,sources:[],kinds:[]}});
 return r.continue();});
 await page.goto('/publishing?selected_post_ids=one');await page.getByTestId('create-plan').click();
 await expect(page.getByTestId('schedule-panel')).toBeVisible();await page.getByLabel('اسم الخطة',{exact:true}).fill('خطة محفوظة الاختيار');await page.getByLabel('وقت البداية',{exact:true}).fill('2026-12-05T10:00');await page.getByTestId('submit-schedule').click();
 await expect.poll(()=>writes).toBe(1);
 await expect(page.getByRole('alert').filter({hasText:'تعارض حجز المادة'})).toBeVisible();await page.getByTestId('submit-schedule').scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath(`create-failure-${width}.png`)});
 await expect(page.getByLabel('اسم الخطة',{exact:true})).toHaveValue('خطة محفوظة الاختيار');await expect(page.getByLabel('وقت البداية',{exact:true})).toHaveValue('2026-12-05T10:00');await expect(page.getByTestId('submit-schedule')).toBeEnabled();
});

for(const width of [390,1280])for(const failure of ['network','validation','server'] as const)test(`create feedback retry ${width} ${failure}`,async({page})=>{
 let writes=0,fail=true,release=()=>{};const gate=new Promise<void>(r=>release=r);const bodies:any[]=[];
 await page.setViewportSize({width,height:844});
 const detail={id:'saved',name:'خطة نشر',status:'DRAFT',timezone:'Asia/Aden',total_items:1,published_items:0,failed_items:0,items:[]};
 await page.route('**/*',async r=>{const q=r.request(),p=new URL(q.url()).pathname;
 if(p==='/schedules'&&q.method()==='POST'){writes++;bodies.push(q.postDataJSON());if(fail){if(failure==='network')return r.abort('failed');return r.fulfill({status:failure==='validation'?422:503,json:{detail:'تعذر حفظ الطلب التجريبي'}});}await gate;return r.fulfill({json:detail});}
 if(p==='/schedules/saved')return r.fulfill({json:detail});
 if(p==='/schedules/eligibility')return r.fulfill({json:{eligible_ids:['one'],blocked:[]}});
 if(q.method()!=='GET')throw Error('Unexpected write');
 if(p==='/sources'||p.startsWith('/api/control/'))return r.fulfill({json:[]});
 if(p.startsWith('/api/')||p.startsWith('/posts')||p.startsWith('/schedules'))return r.fulfill({json:{items:[],total:0,sources:[],kinds:[]}});
 return r.continue();});
 await page.goto('/publishing?selected_post_ids=one');await page.getByTestId('create-plan').click();await page.getByLabel('وقت البداية',{exact:true}).fill('2026-12-05T10:00');await page.getByTestId('submit-schedule').click();
 await expect(page.getByTestId('schedule-panel').getByRole('alert')).toBeVisible();await expect(page.getByLabel('وقت البداية',{exact:true})).toHaveValue('2026-12-05T10:00');expect(writes).toBe(1);
 await page.getByRole('button',{name:'إغلاق',exact:true}).click();await page.getByTestId('create-plan').click();await expect(page.getByTestId('schedule-panel').getByRole('alert')).toHaveCount(0);
 fail=false;await page.getByTestId('submit-schedule').click();await expect(page.getByTestId('submit-schedule')).toHaveText('جارٍ حفظ الخطة...');await expect(page.getByTestId('submit-schedule')).toBeDisabled();expect(writes).toBe(2);release();
 await expect(page.getByTestId('schedule-panel')).toHaveCount(0);await expect.poll(()=>new URL(page.url()).searchParams.get('schedule_id')).toBe('saved');expect(bodies[1].post_ids).toEqual(['one']);
});
