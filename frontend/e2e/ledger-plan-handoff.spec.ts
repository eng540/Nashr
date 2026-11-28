import {test,expect} from '@playwright/test';
import {libraryFixture} from './libraryFixture';
const id='3166cc2a-fff0-4d03-93ba-a2116d871d03',plan='61aa91ab-84e5-42be-bc9c-afea40c85fcc';
for(const width of [390,1280])for(const fails of [false,true])test(`ledger opens exact existing plan without writes ${width} ${fails}`,async({page},info)=>{
 let failed=fails;const writes:string[]=[],planReads:string[]=[];
 const item={id,kind:'TEXT',status:'AVAILABLE',review_status:'APPROVED',content:'الأصل المحفوظ',metadata:{title:'مادة سجل الخطة'},created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'};
 const detail={id:plan,name:'خطة المادة المحفوظة',status:'COMPLETED',timezone:'Asia/Riyadh',total_items:1,published_items:1,failed_items:0,items:[]};
 await page.route('**/*',r=>{const u=new URL(r.request().url()),p=u.pathname;if(r.request().method()!=='GET')writes.push(p);
 if(p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return r.fulfill({json:libraryFixture(r,{items:[item]})});
 if(p===`/api/artifacts/${id}/publications`)return r.fulfill({json:{total:1,connector_items:[],items:[{id:'known-publication',platform:'telegram',status:'PUBLISHED',destination:'saved-target',external_ids:['2561'],content:item.content,published_at:'2026-11-24T05:12:44Z',schedules:[{schedule_id:plan,name:detail.name,schedule_status:'COMPLETED',item_status:'PUBLISHED',attempts:1,scheduled_at:'2026-11-24T05:11:00Z'}]}]}});
 if(p===`/schedules/${plan}`){planReads.push(p);return failed?r.fulfill({status:503,json:{detail:'تعذر قراءة الخطة المحددة'}}):r.fulfill({json:detail});}
 if(p==='/schedules')return r.fulfill({json:{items:[{...detail,id:'unrelated-plan',name:'خطة أخرى لا نفتحها'}],total:1}});
 if(p==='/sources'||p.startsWith('/api/control/')||p.startsWith('/posts'))return r.fulfill({json:[]});
 if(p.startsWith('/api/')||p.startsWith('/schedules'))return r.fulfill({json:{items:[],total:0,index:[],sources:[],kinds:[]}});return r.continue();});
 await page.setViewportSize({width,height:844});await page.goto(`/bank?artifact_status=APPROVED&artifact_id=${id}`);
 const ledger=page.getByLabel(`سجل نشر المخرج ${id}`,{exact:true});await ledger.getByRole('button',{name:'عرض وتحديث سجل النشر',exact:true}).click();
 const link=ledger.getByRole('link',{name:'فتح الخطة: '+detail.name,exact:true});await expect(link).toHaveAttribute('href',`/publishing?view=plans&schedule_id=${plan}`);await link.scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath(`ledger-plan-link-${width}-${fails}.png`)});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();await link.click();
 await expect(page).toHaveURL(new RegExp(`schedule_id=${plan}`));await expect(page.getByTestId('schedule-panel')).toHaveCount(0);
 if(fails){await expect(page.getByRole('alert').filter({hasText:'تعذر قراءة الخطة المحددة'})).toBeVisible();await expect(page.getByTestId('schedule-detail')).toHaveCount(0);failed=false;await page.getByRole('button',{name:'إعادة تحميل تفاصيل الخطة',exact:true}).click();}
 await expect(page.getByTestId('schedule-detail').getByRole('heading',{name:detail.name,exact:true})).toBeVisible();await page.goBack();await expect(page).toHaveURL(new RegExp(`artifact_id=${id}`));await page.goForward();await expect(page.getByTestId('schedule-detail').getByRole('heading',{name:detail.name,exact:true})).toBeVisible();await page.reload();await expect(page.getByTestId('schedule-detail').getByRole('heading',{name:detail.name,exact:true})).toBeVisible();await expect(page.getByTestId('schedule-panel')).toHaveCount(0);await page.getByTestId('schedule-detail').screenshot({path:info.outputPath(`ledger-plan-detail-${width}-${fails}.png`)});expect(planReads.length).toBeGreaterThan(0);expect(writes).toEqual([]);
});
