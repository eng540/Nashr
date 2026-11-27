import {test,expect} from '@playwright/test';
import {libraryFixture} from './libraryFixture';
const id='55000000-0000-4000-8000-000000000021';
for(const width of [390,1280])test(`worklist restores filtered page and exact row after material visit at ${width}px without writes`,async({page},info)=>{
 await page.setViewportSize({width,height:900});
 let writes=0;let held=false;let release!:()=>void;const gate=new Promise<void>(r=>release=r);const offsets:number[]=[];
 const artifact={id,kind:'TEXT',status:'AVAILABLE',review_status:'APPROVED',content:'نص المادة المحفوظ',metadata:{title:'مادة القائمة'},created_at:'2026-11-20T00:00:00Z',mime_type:'text/plain'};
 await page.route('**/*',async route=>{const r=route.request(),u=new URL(r.url()),p=u.pathname;
 if(p.startsWith('/api/')||p.startsWith('/posts')||p.startsWith('/schedules')||p.startsWith('/sources')||p.startsWith('/production-')){
 if(r.method()!=='GET')writes++;
 if(p==='/api/publishing-queue'){const offset=Number(u.searchParams.get('offset')||0);offsets.push(offset);if(u.searchParams.get('platform')==='instagram'&&offset===0&&!held){held=true;await gate;}return route.fulfill({json:{items:[{id:offset>=20?id:'first',origin:'ARTIFACT',kind:'TEXT',title:offset>=20?'مادة القائمة':'المادة الأولى',content_preview:'نص محفوظ',state:'PUBLISHED',prepared_copies:0,fields_validated:0,selected_platforms:[],selection_stale:false}],total:21,caveat:'قراءة فقط'}});}
 if(p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return route.fulfill({json:libraryFixture(route,{items:[artifact]})});
 if(p===`/api/artifacts/${id}`)return route.fulfill({json:artifact});
 if(p==='/sources'||p.startsWith('/api/control/')||p.startsWith('/production-'))return route.fulfill({json:[]});
 if(p==='/api/artifacts/platform-variants')return route.fulfill({json:[]});
 return route.fulfill({json:{items:[],total:0,index:[],sources:[],kinds:[],counts:{waiting:0,published:0,attention:0,total:0}}});}
 return route.continue();});
 await page.goto('/publishing');const queue=page.getByRole('region',{name:'قائمة المحتوى الموحدة',exact:true});
 await page.getByLabel('بحث قائمة المحتوى الموحدة').fill('مادة');await expect.poll(()=>new URL(page.url()).searchParams.get('queue_q')).toBe('مادة');await page.getByLabel('حالة قائمة المحتوى الموحدة').selectOption('PUBLISHED');await page.getByLabel('مصدر قائمة المحتوى الموحدة').selectOption('ARTIFACT');await page.getByLabel('سلسلة قائمة التوزيع').fill('سلسلة المواد');await page.getByLabel('تصنيف قائمة التوزيع').fill('تصنيف محفوظ');await page.getByLabel('وجهة قائمة التوزيع').selectOption('instagram');
 await expect.poll(()=>{const p=new URL(page.url()).searchParams;return ['queue_q','queue_state','queue_origin','queue_series','queue_category','queue_platform'].map(k=>p.get(k));}).toEqual(['مادة','PUBLISHED','ARTIFACT','سلسلة المواد','تصنيف محفوظ','instagram']);
 await expect.poll(()=>held).toBe(true);await expect(queue).toHaveAttribute('aria-busy','true');await expect(queue.getByRole('button',{name:'التالي',exact:true})).toBeDisabled();expect(offsets).not.toContain(20);release();await expect(queue).toHaveAttribute('aria-busy','false');await expect(queue.getByRole('button',{name:'التالي',exact:true})).toBeEnabled();await expect(queue.getByText('المادة الأولى',{exact:true})).toBeVisible();await queue.getByRole('button',{name:'التالي',exact:true}).click();await expect(queue.getByText('مادة القائمة',{exact:true})).toBeVisible();expect(offsets).toContain(20);
 await queue.getByRole('link',{name:'فتح المادة والتجهيز والخطة والسجل'}).click();await expect(page.getByRole('button',{name:'إغلاق مساحة المادة'})).toBeVisible();
 await page.getByRole('link',{name:'العودة إلى قائمة التوزيع السابقة',exact:true}).click();
 await expect(page.getByLabel('بحث قائمة المحتوى الموحدة')).toHaveValue('مادة');await expect(page.getByLabel('حالة قائمة المحتوى الموحدة')).toHaveValue('PUBLISHED');await expect(queue.getByText('صفحة 2 من 2')).toBeVisible();await expect(queue.getByRole('link',{name:'فتح المادة والتجهيز والخطة والسجل'})).toBeFocused();
 await queue.getByRole('link',{name:'فتح المادة والتجهيز والخطة والسجل'}).scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath('worklist-return-'+width+'.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.goBack();await expect(page.getByRole('button',{name:'إغلاق مساحة المادة'})).toBeVisible();await page.goForward();await expect(page.getByLabel('حالة قائمة المحتوى الموحدة')).toHaveValue('PUBLISHED');
 await queue.getByRole('button',{name:'تحديث قائمة المحتوى'}).click();await expect(queue.getByRole('button',{name:'تحديث قائمة المحتوى'})).toBeFocused();
 await page.reload();await expect(page.getByLabel('مصدر قائمة المحتوى الموحدة')).toHaveValue('ARTIFACT');await expect(page.getByLabel('سلسلة قائمة التوزيع')).toHaveValue('سلسلة المواد');await expect(page.getByLabel('تصنيف قائمة التوزيع')).toHaveValue('تصنيف محفوظ');await expect(page.getByLabel('وجهة قائمة التوزيع')).toHaveValue('instagram');await expect(page.getByLabel('بحث قائمة المحتوى الموحدة')).toHaveValue('مادة');await expect(queue.getByText('صفحة 2 من 2')).toBeVisible();expect(writes).toBe(0);
});
