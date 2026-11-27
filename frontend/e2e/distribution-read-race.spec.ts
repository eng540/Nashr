import {libraryFixture} from './libraryFixture';
import {test,expect} from '@playwright/test';

test('late readiness for an earlier selection cannot become the current batch or feed save',async({page})=>{
 const ids=['one','two'];let release!:()=>void;let requested=false;let writes=0;
 const gate=new Promise<void>(resolve=>{release=resolve;});
 const items=ids.map(id=>({id,source_knowledge_unit_id:'u',kind:'TEXT',status:'AVAILABLE',content:'أصل '+id,storage_uri:null,mime_type:'text/plain',metadata:{title:'مادة '+id},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'}));
 const readiness=(id:string)=>({artifact_id:id,source_fingerprint:'source-'+id,selection_version:'selection-'+id,central_approval:'APPROVED',original_text:'أصل '+id,selection_stale:false,targets:[{platform:'telegram',label:'telegram',selected:false,copy_status:'ORIGINAL_ELIGIBLE',copy_blockers:[],execution_blockers:['لا إذن تنفيذ']}]});
 await page.route('**/*',async route=>{const r=route.request(),p=new URL(r.url()).pathname;
  if(r.method()!=='GET')writes++;
  if(p==='/api/artifacts'||p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return route.fulfill({json:libraryFixture(route, {items,total:2,limit:100,offset:0})});
  if(p.endsWith('/distribution-readiness')){const id=p.split('/')[3];if(id==='one'){requested=true;await gate;}return route.fulfill({json:readiness(id)});}
  if(p.startsWith('/api/'))return route.fulfill({json:p.includes('/control/')?[]:{items:[],total:0,telegram:{items:[]}}});
  if(['/posts','/sources'].some(x=>p.startsWith(x)))return route.fulfill({json:[]});return route.continue();
 });
 await page.goto('/bank?artifact_status=APPROVED');
 await page.getByLabel('تحديد المخرج one',{exact:true}).check();
 const panel=page.getByLabel('جاهزية توزيع one',{exact:true});
 // The batch panel for a single selected item shares the individual label; compact mode keeps only the batch mounted.
 await panel.getByRole('button',{name:'فحص جاهزية واختيار المنصات (1)',exact:true}).click();
 await expect.poll(()=>requested).toBe(true);
 await page.getByLabel('تحديد المخرج two',{exact:true}).check();await page.getByLabel('تحديد المخرج one',{exact:true}).uncheck();
 release();
 const current=page.getByLabel('جاهزية توزيع two',{exact:true});
 await expect(current.getByRole('button',{name:'فحص جاهزية واختيار المنصات (1)',exact:true})).toBeEnabled();
 await expect(current.getByRole('button',{name:'حفظ اختيار الوجهات فقط',exact:true})).toHaveCount(0);
 await expect(current.getByText('معاينة النص الأصلي دون تغيير',{exact:true})).toHaveCount(0);
 await current.getByRole('button',{name:'فحص جاهزية واختيار المنصات (1)',exact:true}).click();
 await expect(current.getByRole('button',{name:'حفظ اختيار الوجهات فقط',exact:true})).toBeVisible();
 await current.getByText('اعتماد مركزي محفوظ',{exact:false}).click();await current.getByText('معاينة النص الأصلي دون تغيير',{exact:true}).click();
 await expect(current.getByText('أصل two',{exact:true})).toBeVisible();await expect(current.getByText('أصل one',{exact:true})).toHaveCount(0);expect(writes).toBe(0);
});

test('late save stays attached to submitted originals while the selection changes',async({page},info)=>{
 const ids=['one','two'];let release!:()=>void;let submitted:any=null;
 const gate=new Promise<void>(resolve=>{release=resolve;});
 const items=ids.map(id=>({id,kind:'TEXT',status:'AVAILABLE',content:'أصل '+id,storage_uri:null,mime_type:'text/plain',metadata:{title:'مادة '+id},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'}));
 const readiness=(id:string)=>({artifact_id:id,source_fingerprint:'source-'+id,selection_version:'selection-'+id,central_approval:'APPROVED',original_text:'أصل '+id,selection_stale:false,targets:[{platform:'telegram',label:'telegram',selected:false,copy_status:'ORIGINAL_ELIGIBLE',copy_blockers:[],execution_blockers:['لا إذن تنفيذ']}]});
 await page.route('**/*',async route=>{const r=route.request(),p=new URL(r.url()).pathname;
  if(p==='/api/artifacts'||p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return route.fulfill({json:libraryFixture(route, {items,total:2,limit:100,offset:0})});
  if(p.endsWith('/distribution-readiness'))return route.fulfill({json:readiness(p.split('/')[3])});
  if(p==='/api/artifacts/distribution-selection'){submitted=r.postDataJSON();await gate;return route.fulfill({json:{saved:1,items:[readiness('one')]}});}
  if(p.startsWith('/api/'))return route.fulfill({json:p.includes('/control/')?[]:{items:[],total:0,telegram:{items:[]}}});
  if(['/posts','/sources'].some(x=>p.startsWith(x)))return route.fulfill({json:[]});return route.continue();
 });
 await page.goto('/bank?artifact_status=APPROVED');await page.getByLabel('تحديد المخرج one',{exact:true}).check();
 const first=page.getByLabel('جاهزية توزيع one',{exact:true});await first.getByRole('button',{name:'فحص جاهزية واختيار المنصات (1)',exact:true}).click();await first.getByLabel('telegram',{exact:true}).check();await first.getByRole('button',{name:'حفظ اختيار الوجهات فقط',exact:true}).click();
 await expect.poll(()=>submitted).not.toBeNull();await page.getByLabel('تحديد المخرج two',{exact:true}).check();await page.getByLabel('تحديد المخرج one',{exact:true}).uncheck();release();
 const current=page.getByLabel('جاهزية توزيع two',{exact:true});await expect(current.getByRole('button',{name:'فحص جاهزية واختيار المنصات (1)',exact:true})).toBeEnabled();await expect(current.getByRole('status')).toHaveCount(0);await expect(current.getByRole('button',{name:'حفظ اختيار الوجهات فقط',exact:true})).toHaveCount(0);
 expect(submitted).toMatchObject({artifact_ids:['one'],platforms:['telegram'],fingerprints:{one:'source-one'},selection_versions:{one:'selection-one'}});
 await current.getByRole('button',{name:'فحص جاهزية واختيار المنصات (1)',exact:true}).click();await expect(current.getByLabel('telegram',{exact:true})).not.toBeChecked();
 await page.setViewportSize({width:390,height:844});await current.scrollIntoViewIfNeeded();await current.screenshot({path:info.outputPath('selection-after-old-save-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
