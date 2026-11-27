import {libraryFixture} from './libraryFixture';
import {test,expect} from '@playwright/test';
test('private inspection history reloads and separates stale evidence from permission',async({page},info)=>{
 let writes=0,reads=0;const id='history-source';
 const item={id,kind:'VIDEO',source_knowledge_unit_id:'u',status:'AVAILABLE',content:null,storage_uri:'s3://private/video.mp4',mime_type:'video/mp4',metadata:{title:'فيديو للفحص'},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'};
 const copy={platform:'instagram',label:'Instagram',fields:{title:'',description:'نص محفوظ','tags':[],alt_text:''},version:2,source_fingerprint:'a'.repeat(64),current_source_fingerprint:'a'.repeat(64),origin:'USER_EDITED',source_stale:false,central_approval:'APPROVED',field_status:'FIELDS_VALIDATED',blockers:[],warnings:[],media_checks_pending:[],execution_blockers:[],sources:[]};
 const result={source_fingerprint:'a'.repeat(64),copy_version:2,status:'MEASURED_WITH_PENDING_CHECKS',measurements:{format:'MOV/MP4',width:1080,height:1920},blockers:[],pending:['VBR غير متحقق.']};
 const record={id:'inspection1',created_at:'2026-11-24T02:00:00Z',selected:true,media_id:null,sha256:'b'.repeat(64),copy_version:2,probe_version:'test',stale:false,stale_reasons:[],result,caveat:'لا يعيد السجل قراءة الملف ولا يمنح إذن نشر.'};
 await page.route('**/*',async route=>{const req=route.request(),path=new URL(req.url()).pathname;
 if(path==='/api/artifacts'||path==='/api/artifacts/library'||path==='/api/artifacts/library-items')return route.fulfill({json:libraryFixture(route, {items:[item],total:1,limit:100,offset:0})});
 if(path.endsWith('/platform-copies'))return route.fulfill({json:{items:[copy]}});
 if(path.endsWith('/media-inspections')){if(req.method()==='POST'){writes++;expect(req.postDataJSON()).toEqual({source_fingerprint:'a'.repeat(64),copy_version:2,selected:true});return route.fulfill({json:record});}reads++;return route.fulfill({json:{items:writes?[record,{...record,id:'old',copy_version:1,stale:true,stale_reasons:['تغير إصدار نسخة المنصة.']}]:[]}});}
 if(path.endsWith('/media-url'))return route.fulfill({json:{url:null}});
 if(path.startsWith('/api/')&&req.method()!=='GET')throw new Error('unexpected write '+path);
 if(['/posts','/sources','/api/control/'].some(x=>path.startsWith(x)))return route.fulfill({json:[]});return route.continue();});
 async function open(){await page.goto('/bank?library_view=expanded');await page.getByLabel('حالة مراجعة المخرجات').selectOption('APPROVED');const panel=page.getByLabel('نسخ المنصات '+id,{exact:true});await panel.locator('summary').first().click();await panel.getByRole('button',{name:'عرض النسخ المحفوظة',exact:true}).click();await panel.getByLabel('منصة النسخة '+id).selectOption('instagram');await panel.getByText('سجل فحوص الوسيط المرتبط بالإصدار',{exact:true}).click();return panel;}
 let panel=await open();await expect(panel.getByText('لا فحوص محفوظة لهذه المنصة.',{exact:true})).toBeVisible();await panel.getByRole('button',{name:'فحص الوسيط الحالي وحفظ سجل خاص',exact:true}).click();await expect(panel.getByText('مرتبط بالإصدار الحالي، لا قبول نهائي',{exact:false})).toBeVisible();expect(writes).toBe(1);
 panel=await open();await expect(panel.getByText('قديم، يحتاج فحصاً جديداً',{exact:false})).toBeVisible();expect(writes).toBe(1);expect(reads).toBeGreaterThan(1);
 await panel.getByText('مرتبط بالإصدار الحالي، لا قبول نهائي',{exact:false}).click();await expect(panel.getByText('VBR غير متحقق.',{exact:true}).first()).toBeVisible();await expect(panel.getByLabel('وصف نسخة '+id)).toHaveValue('نص محفوظ');
 await page.addStyleTag({content:'header{visibility:hidden}'});await page.setViewportSize({width:390,height:844});await panel.screenshot({path:info.outputPath('inspection-history-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
