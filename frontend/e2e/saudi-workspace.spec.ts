import {test,expect} from '@playwright/test';
const id='12345678-1234-4123-8123-123456789abc';
test('Saudi service workspace shows truthful platform scopes and accessible mobile navigation',async({page},info)=>{
 let writes=0;
 await page.route('**/*',async route=>{const r=route.request(),p=new URL(r.url()).pathname;if(r.method()!=='GET')writes++;
 if(p==='/api/platform-operations')return route.fulfill({json:{items:[{id,artifact_id:id,platform:'facebook_photo',title:'التقرير المساحي يبدأ بتحديد الغرض منه',destination:'Engineering Creativity',state:'APPROVED',execution_state:'APPROVED',due_at:'2026-11-25T12:00:00Z',timezone:'Asia/Riyadh',permalink:null}],total:10,counts:{waiting:6,published:4,attention:0,total:10}}});
 if(p==='/api/artifacts/platform-variants')return route.fulfill({json:[]});
 if(p==='/sources'||p.startsWith('/api/control/'))return route.fulfill({json:[]});
 if(p.startsWith('/api/')||p.startsWith('/schedules')||p.startsWith('/posts'))return route.fulfill({json:{items:[],total:0,sources:[],kinds:[]}});return route.continue();});
 await page.goto('/publishing?view=plans');await expect(page.getByLabel('ملخص النشر')).toContainText('عمليات Meta القادمة أو الجارية');await expect(page.getByLabel('ملخص النشر')).toContainText('قائمة منفصلة، لا تشمل Meta');await expect(page.getByLabel('ملخص النشر').locator('strong').first()).toHaveText('6');await expect(page.getByText('التقرير المساحي يبدأ بتحديد الغرض منه',{exact:true})).toBeVisible();
 await page.screenshot({path:info.outputPath('saudi-workspace-desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:info.outputPath('saudi-workspace-mobile.png'),fullPage:true});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.getByRole('button',{name:'قائمة التنقل',exact:true}).click();await expect(page.getByRole('navigation',{name:'التنقل الرئيسي للجوال'})).toBeVisible();await page.keyboard.press('Escape');await expect(page.getByRole('button',{name:'قائمة التنقل',exact:true})).toBeFocused();await expect(page.getByRole('navigation',{name:'التنقل الرئيسي للجوال'})).toHaveCount(0);expect(writes).toBe(0);
});
test('failed Meta summary never implies zero and offers recovery',async({page})=>{
 await page.route('**/*',route=>{const p=new URL(route.request().url()).pathname;if(p==='/api/platform-operations')return route.fulfill({status:503,json:{detail:'unavailable'}});if(p==='/api/artifacts/platform-variants'||p==='/sources')return route.fulfill({json:[]});if(p.startsWith('/api/')||p.startsWith('/schedules')||p.startsWith('/posts'))return route.fulfill({json:{items:[],total:0}});return route.continue();});
 await page.goto('/publishing');await expect(page.getByRole('alert')).toContainText('لا نستنتج أن العدد صفر');await expect(page.getByRole('button',{name:'إعادة المحاولة',exact:true})).toBeVisible();await expect(page.getByLabel('ملخص النشر').locator('strong').first()).toHaveText('—');
});

test('slow platform summary stays unknown until the response lands',async({page})=>{
 let release:()=>void=()=>{};const gate=new Promise<void>(r=>{release=r;});
 await page.route('**/*',async route=>{const p=new URL(route.request().url()).pathname;
 if(p==='/api/platform-operations'){await gate;return route.fulfill({json:{items:[],total:0,counts:{waiting:0,published:0,attention:0,total:0}}});}
 if(p==='/api/artifacts/platform-variants'||p==='/sources')return route.fulfill({json:[]});if(p.startsWith('/api/')||p.startsWith('/schedules')||p.startsWith('/posts'))return route.fulfill({json:{items:[],total:0}});return route.continue();});
 await page.goto('/publishing');await expect(page.getByLabel('ملخص النشر').locator('strong').first()).toHaveText('—');release();await expect(page.getByLabel('ملخص النشر').locator('strong').first()).toHaveText('0');
});
