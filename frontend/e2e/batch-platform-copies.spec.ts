import {libraryFixture} from './libraryFixture';
import {test,expect} from '@playwright/test';
test('platform-neutral batch read, missing-only preparation and same-original saved copy link',async({page},info)=>{
 const ids=['12345678-1234-4123-8123-123456789ab1','12345678-1234-4123-8123-123456789ab2'];
 const items=ids.map((id,i)=>({id,kind:'TEXT',status:'AVAILABLE',content:'أصل محفوظ '+i,mime_type:'text/plain',metadata:{title:'مادة '+(i+1)},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'}));
 const copy=(id:string,platform:string)=>({platform,label:platform,fields:{title:'',description:'تعديل محفوظ '+id,tags:[],alt_text:''},version:3,source_fingerprint:'v1',current_source_fingerprint:'v1',origin:'USER_EDITED',source_stale:false,central_approval:'APPROVED',field_status:platform==='telegram'?'FIELDS_VALIDATED':'BLOCKED',blockers:platform==='telegram'?[]:['يلزم عنوان'],warnings:[],media_checks_pending:[],execution_blockers:[],sources:[]});
 let prepares=0;const writes:string[]=[];
 await page.route('**/*',async r=>{const p=new URL(r.request().url()).pathname;
  if(p==='/api/artifacts'||p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return r.fulfill({json:libraryFixture(r, {items,total:2,limit:100,offset:0})});
  if(p.endsWith('/platform-copies')){const id=p.split('/')[3];return r.fulfill({json:{items:id===ids[0]?[copy(id,'telegram'),copy(id,'youtube')]:[]}});}
  if(p==='/api/artifacts/platform-copies/prepare-batch'){prepares++;expect(r.request().postDataJSON()).toEqual({artifact_ids:ids});return r.fulfill({json:{prepared:2,items:[...ids].reverse().map(id=>({artifact_id:id,items:[copy(id,'telegram'),copy(id,'youtube')]}))}});}
  if(r.request().method()!=='GET')writes.push(p);
  if(p==='/api/connections')return r.fulfill({json:{telegram:{items:[]}}});
  if(p==='/posts'||p==='/sources'||p.startsWith('/api/control/'))return r.fulfill({json:[]});
  if(p.startsWith('/api/'))return r.fulfill({json:{items:[],total:0}});return r.continue();
 });
 await page.setViewportSize({width:390,height:844});await page.goto('/bank?artifact_status=APPROVED');await page.getByRole('button',{name:'تحديد النتائج المؤهلة (حتى 100)',exact:true}).click();
 const panel=page.getByLabel('نسخ منصات الدفعة',{exact:true});await panel.getByRole('button',{name:'عرض نسخ الدفعة المحفوظة (2)',exact:true}).click();await expect(panel).toContainText('Telegram · 1/2 حقول مقبولة');await expect(panel).toContainText('1 بلا نسخة محفوظة');expect(prepares).toBe(0);expect(writes).toEqual([]);
 await panel.getByRole('button',{name:'تجهيز نسخ المنصات للمحدد (2)',exact:true}).click();await expect(panel).toContainText('Telegram · 2/2 حقول مقبولة');await expect(panel).toContainText('YouTube · 0/2 حقول مقبولة');
 await panel.getByText('YouTube · 0/2 حقول مقبولة',{exact:true}).click();const links=panel.getByRole('link',{name:'فتح نسخة YouTube لهذه المادة في نافذة جديدة',exact:true});await expect(links).toHaveCount(2);expect(await links.first().getAttribute('href')).toContain('artifact_id='+ids[0]+'&copy_platform=youtube');
 await panel.screenshot({path:info.outputPath('platform-batch-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 const href=await links.first().getAttribute('href');await page.goto(href!);const saved=page.getByLabel('نسخ المنصات '+ids[0],{exact:true});await expect(saved.getByLabel('منصة النسخة '+ids[0],{exact:true})).toHaveValue('youtube');await expect(saved.getByLabel('وصف نسخة '+ids[0],{exact:true})).toHaveValue('تعديل محفوظ '+ids[0]);expect(prepares).toBe(1);expect(writes).toEqual([]);
});

test('late batch reads and incomplete responses never describe a different selected batch',async({page})=>{
 const ids=['one','two'];let release:(()=>void)|undefined;let calls=0;
 const items=ids.map(id=>({id,kind:'TEXT',status:'AVAILABLE',content:id,mime_type:'text/plain',metadata:{title:id},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'}));
 await page.route('**/*',async r=>{const p=new URL(r.request().url()).pathname;
  if(p==='/api/artifacts'||p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return r.fulfill({json:libraryFixture(r, {items,total:2,limit:100,offset:0})});
  if(p.endsWith('/platform-copies')){calls++;if(calls===1)await new Promise<void>(resolve=>{release=resolve;});return r.fulfill({json:{items:[]}});}
  if(p==='/api/artifacts/platform-copies/prepare-batch')return r.fulfill({json:{prepared:1,items:[]}});
  if(p==='/api/connections')return r.fulfill({json:{telegram:{items:[]}}});if(p==='/posts'||p.startsWith('/posts/')||p==='/sources'||p.startsWith('/api/control/'))return r.fulfill({json:[]});if(p.startsWith('/api/'))return r.fulfill({json:{items:[],total:0}});return r.continue();
 });
 await page.goto('/bank?artifact_status=APPROVED');await page.getByLabel('تحديد المخرج one',{exact:true}).check();const panel=page.getByLabel('نسخ منصات الدفعة',{exact:true});await panel.getByRole('button',{name:'عرض نسخ الدفعة المحفوظة (1)',exact:true}).click();await expect.poll(()=>calls).toBe(1);await page.getByLabel('تحديد المخرج two',{exact:true}).check();release!();await expect(panel.getByText('جارٍ قراءة أو تجهيز نسخ الدفعة...', {exact:true})).toHaveCount(0);await expect(panel.locator('details')).toHaveCount(0);
 await page.getByLabel('تحديد المخرج one',{exact:true}).uncheck();await expect(panel.locator('details')).toHaveCount(0);await panel.getByRole('button',{name:'تجهيز نسخ المنصات للمحدد (1)',exact:true}).click();await expect(panel.getByRole('alert')).toContainText('لم تكتمل قراءة');await expect(panel.locator('details')).toHaveCount(0);
});
