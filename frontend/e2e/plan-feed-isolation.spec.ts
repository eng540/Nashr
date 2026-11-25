import {test,expect} from '@playwright/test';
test('older failed plans use global server filtering and remain visible when editorial feed fails',async({page},info)=>{
 let writes=0;let planFail=false;const seen:URL[]=[];
 await page.route('**/*',r=>{const u=new URL(r.request().url()),p=u.pathname;if(r.request().method()!=='GET')writes++;
 if(p==='/posts')return r.fulfill({status:503,json:{detail:'unavailable'}});
 if(p==='/schedules'){seen.push(u);if(planFail)return r.fulfill({status:503,json:{detail:'unavailable'}});const offset=Number(u.searchParams.get('offset'));return r.fulfill({json:{total:21,items:[{id:`old-${offset}`,name:`خطة محفوظة ${offset}`,status:'PAUSED',timezone:'Asia/Riyadh',total_items:1,failed_items:1,published_items:0,content_summary:[{title:offset?'تعثر قديم خارج أول خمسين':'مراجعة حالة متعثرة',kind:'VIDEO'}],platform:'telegram',destination_label:'قناة خاصة'}]}});}
 if(p==='/api/artifacts/platform-variants'||p.startsWith('/api/control/')||p==='/sources')return r.fulfill({json:[]});
 if(p==='/posts/filter-options')return r.fulfill({json:{sources:[],kinds:[]}});
 if(['/api/','/schedules/'].some(x=>p.startsWith(x)))return r.fulfill({json:{items:[],total:0}});return r.continue();});
 await page.setViewportSize({width:390,height:844});await page.goto('/publishing?view=plans&failures=1');await expect(page.getByRole('button',{name:/مراجعة حالة متعثرة/})).toBeVisible();expect(seen[0].searchParams.get('failed_only')).toBe('true');
 await page.getByLabel('صفحات خطط النشر').getByRole('button',{name:'التالي'}).click();await expect(page.getByRole('button',{name:/تعثر قديم خارج أول خمسين/})).toBeVisible();expect(seen.at(-1)?.searchParams.get('offset')).toBe('20');
 await page.getByLabel('بحث الخطط',{exact:true}).fill('اختبار قديم');await expect.poll(()=>seen.at(-1)?.searchParams.get('query')).toBe('اختبار قديم');expect(seen.at(-1)?.searchParams.get('offset')).toBe('0');
 await page.getByRole('button',{name:/مراجعة حالة متعثرة/}).scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath('plans-independent-mobile.png')});
 await page.getByRole('button',{name:/المحتوى والتجهيز/}).first().click();await page.getByRole('button',{name:/جدولة نصوص Telegram/}).click();await expect(page.getByRole('alert').filter({hasText:'تعذر تحميل المنشورات التحريرية'})).toBeVisible({timeout:15000});await expect(page.getByText('لا توجد منشورات جاهزة',{exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:/خطط النشر/}).first().click();planFail=true;await page.getByRole('button',{name:'تحديث',exact:true}).click();await expect(page.getByRole('alert').filter({hasText:'تعذر تحميل الخطط'})).toBeVisible({timeout:15000});await expect(page.getByText('لا توجد خطط مطابقة',{exact:true})).toHaveCount(0);await page.screenshot({path:info.outputPath('plan-error-mobile.png')});expect(writes).toBe(0);
});
