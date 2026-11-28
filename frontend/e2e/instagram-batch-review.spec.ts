import {libraryFixture} from './libraryFixture';
import {test,expect} from '@playwright/test';
const ids=['12345678-1234-4123-8123-123456789ab1','12345678-1234-4123-8123-123456789ab2'];
const base='/api/connections/instagram/batch-reviews';
const items=ids.map((id,i)=>({id,kind:'VIDEO',status:'AVAILABLE',content:'أصل مستقل '+i,mime_type:'video/mp4',metadata:{title:'المادة المعتمدة '+(i+1)},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'}));
async function fixture(page:any,mode='ready'){
 const requests:{path:string;body:any}[]=[];let snapshot:any;
 await page.route('**/*',async(r:any)=>{const req=r.request(),p=new URL(req.url()).pathname;
 if(req.method()!=='GET')requests.push({path:p,body:req.postDataJSON()});
 if(p===base+'/preview'){
 if(mode==='failure')return r.fulfill({status:409,json:{detail:'تغيرت المادة الثانية، راجع الدفعة كاملة'}});
 const body=req.postDataJSON();snapshot={items:body.items.map((i:any,n:number)=>({...i,artifact_id:mode==='mismatch'?ids[0]:i.artifact_id,kind:'VIDEO',copy_version:3,selected_platforms:n?['facebook']:['instagram','facebook'],selection_stale:false,caption:'نص محفوظ كامل '+(n+1),alt_text:'',account:{username:'selected_creator',account_id:'100',last_check_at:'2026-11-28T11:00:00Z'},inspection:{id:'inspection-'+n,sha256:'a'.repeat(64)},pending:['فحص الوسيط الحالي مستقل'],blockers:n?['Instagram مستبعد لهذه المادة، لم نغير اختيارك']:[],history:n?[{id:'old-unknown',state:'PUBLISH_UNKNOWN',dispatch_state:null,due_at:null,permalink:null}]:[],history_total:n?1:0,history_truncated:false})),preview_hash:'a'.repeat(64),can_save_draft:true,blocked_count:1,execution_enabled:false,scheduled:false,approval_recorded:false,media_exposure_enabled:false,caveat:'مراجعة خاصة، لا تحقق جديد من Meta أو بايتات الوسيط.'};return r.fulfill({json:snapshot});}
 if(p===base&&req.method()==='POST')return r.fulfill({json:{id:'saved-review',state:'DRAFT',snapshot_hash:'a'.repeat(64),snapshot,created_at:'2026-11-28T11:01:00Z',execution_enabled:false,scheduled:false}});
 if(p===base)return r.fulfill({json:{items:snapshot?[{id:'saved-review',state:'DRAFT',snapshot_hash:'a'.repeat(64),snapshot,stale:false,created_at:'2026-11-28T11:01:00Z',execution_enabled:false,scheduled:false}]:[]}});
 if(p===base+'/saved-review')return r.fulfill({json:{id:'saved-review',state:'DRAFT',snapshot_hash:'a'.repeat(64),snapshot,stale:true,created_at:'2026-11-28T11:01:00Z',execution_enabled:false,scheduled:false}});
 if(p===base+'/saved-review/cancel')return r.fulfill({json:{state:'CANCELLED'}});
 if(p==='/api/artifacts'||p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return r.fulfill({json:libraryFixture(r,{items,total:2,limit:100,offset:0})});
 if(p==='/api/connections')return r.fulfill({json:{telegram:{items:[]}}});
 if(p==='/posts'||p.startsWith('/posts/')||p==='/sources'||p.startsWith('/api/control/'))return r.fulfill({json:[]});
 if(p.startsWith('/api/'))return r.fulfill({json:{items:[],total:0}});return r.continue();});
 await page.goto('/bank?artifact_status=APPROVED');await page.getByRole('button',{name:'تحديد النتائج المؤهلة (حتى 100)',exact:true}).click();
 const panel=page.getByLabel('مسودة مراجعة دفعة Instagram',{exact:true});
 await panel.getByLabel('بداية مسودة Instagram').fill('2030-01-01T14:00');await panel.getByLabel('منطقة مسودة Instagram').fill('Asia/Riyadh');await panel.getByLabel('فاصل مسودة Instagram').fill('30');
 return {panel,requests};
}
test('exact selected review save history and cancellation remain private at390/1280',async({page})=>{
 const {panel,requests}=await fixture(page);
 await panel.getByRole('button',{name:'مراجعة الدفعة والحساب والسجل دون حفظ',exact:true}).click();await expect(panel.getByRole('alert')).toContainText('كل Reel');expect(requests).toEqual([]);
 for(const id of ids)await panel.getByLabel('خلاصة Reel '+id).selectOption('yes');
 await panel.getByRole('button',{name:'مراجعة الدفعة والحساب والسجل دون حفظ',exact:true}).click();await expect(panel.getByRole('article')).toHaveCount(2);
 expect(requests[0].body.items.map((i:any)=>i.artifact_id)).toEqual(ids);expect(requests[0].body.items[1].due_at).toBe('2030-01-01T11:30:00.000Z');
 await expect(panel).toContainText('selected_creator');await expect(panel).toContainText('Instagram مستبعد');await panel.getByText('النص والوسيط والسجل لهذه المادة',{exact:true}).last().click();await expect(panel).toContainText('PUBLISH_UNKNOWN');
 await expect(panel.getByRole('button',{name:'حفظ مسودة المراجعة فقط',exact:true})).toBeDisabled();
 await panel.getByRole('checkbox').check();await panel.getByRole('button',{name:'حفظ مسودة المراجعة فقط',exact:true}).click();await expect(panel).toContainText('حُفظت المراجعة بحالة');
 await panel.getByText('مسودات مراجعة Instagram المحفوظة',{exact:true}).click();await panel.getByRole('button',{name:'قراءة أحدث20مسودة مراجعة',exact:true}).click();await expect(panel).toContainText('تطابق القراءة الحالية');await panel.getByRole('button',{name:'إعادة فحص حداثة هذه المسودة دون تغيير',exact:true}).click();await expect(panel).toContainText('تغيرت البيانات أو مضى الوقت');
 await page.setViewportSize({width:390,height:844});await panel.getByRole('heading').first().click();await page.addStyleTag({content:'header{visibility:hidden}'});await panel.screenshot({path:'test-results/instagram-private-batch-390.png'});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.setViewportSize({width:1280,height:900});await panel.screenshot({path:'test-results/instagram-private-batch-1280.png'});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await panel.getByRole('button',{name:'إلغاء مسودة المراجعة محلياً',exact:true}).click();await expect(panel).toContainText('CANCELLED');
 expect(requests.map(r=>r.path)).toEqual([base+'/preview',base,base+'/saved-review/cancel']);
});
for(const mode of ['failure','mismatch'])test('private batch fails closed on '+mode,async({page})=>{
 const {panel,requests}=await fixture(page,mode);for(const id of ids)await panel.getByLabel('خلاصة Reel '+id).selectOption('no');await panel.getByRole('button',{name:'مراجعة الدفعة والحساب والسجل دون حفظ',exact:true}).click();await expect(panel.getByRole('alert')).toBeVisible();await expect(panel.getByRole('article')).toHaveCount(0);expect(requests.map(r=>r.path)).toEqual([base+'/preview']);
});
test('changing local times invalidates reviewed save and confirmation',async({page})=>{
 const {panel}=await fixture(page);for(const id of ids)await panel.getByLabel('خلاصة Reel '+id).selectOption('no');await panel.getByRole('button',{name:'مراجعة الدفعة والحساب والسجل دون حفظ',exact:true}).click();await expect(panel.getByRole('article')).toHaveCount(2);await panel.getByRole('checkbox').check();await panel.getByLabel('فاصل مسودة Instagram').fill('60');await expect(panel.getByRole('button',{name:'حفظ مسودة المراجعة فقط',exact:true})).toHaveCount(0);await expect(panel.getByRole('article')).toHaveCount(0);
});
test('returning to same selection does not revive its late preview',async({page})=>{
 const {panel,requests}=await fixture(page);for(const id of ids)await panel.getByLabel('خلاصة Reel '+id).selectOption('yes');
 let release:()=>void=()=>{};
 await page.route('**'+base+'/preview',async route=>{await new Promise<void>(resolve=>{release=resolve;});return route.fallback();});
 await panel.getByRole('button',{name:'مراجعة الدفعة والحساب والسجل دون حفظ',exact:true}).click();
 await expect(panel.getByRole('status')).toBeVisible();
 await page.getByLabel('تحديد المخرج '+ids[1],{exact:true}).uncheck();await page.getByLabel('تحديد المخرج '+ids[1],{exact:true}).check();
 release();await expect.poll(()=>requests.length).toBe(1);await expect(panel.getByRole('article')).toHaveCount(0);await expect(panel.getByRole('button',{name:'حفظ مسودة المراجعة فقط',exact:true})).toHaveCount(0);
});
