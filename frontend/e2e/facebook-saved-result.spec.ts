import {test,expect} from '@playwright/test';
import {libraryFixture} from './libraryFixture';
const id='12345678-1234-4123-8123-123456789abc',jid='abcdef12-1234-4123-8123-123456789abc';
for(const width of [390,1280])for(const photo of [false,true])for(const state of ['published','mismatch','failure'])test(`saved Facebook result first ${photo?'photo':'text'} ${state} ${width}`,async({page},info)=>{
 const segment=photo?'photo':'text',writes:string[]=[];let reads=0;
 await page.route('**/*',r=>{
  const p=new URL(r.request().url()).pathname;
  if(r.request().method()!=='GET')writes.push(p);
  if(p.endsWith(`/${segment}-posts/${jid}`)){
   reads++;if(state==='failure')return r.fulfill({status:503,json:{detail:'synthetic unavailable'}});
   return r.fulfill({json:{id:jid,artifact_id:state==='mismatch'?'wrong':id,state:'PUBLISHED_AT_LAST_CHECK',snapshot_hash:'a'.repeat(64),snapshot:{message:'النص المحفوظ الكامل '.repeat(90),due_at:'2026-11-25T12:00:00Z',timezone:'Asia/Riyadh',connection:{page_id:'123',page_name:'صفحة الاختبار'},mime_type:'image/jpeg',total_bytes:100560,media_sha256:'b'.repeat(64)},post_id:'123_456',permalink:'https://www.facebook.com/123/posts/456',error_code:null}});
  }
  if(p==='/api/artifacts'||p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return r.fulfill({json:libraryFixture(r,{items:[{id,kind:photo?'IMAGE':'TEXT',status:'AVAILABLE',content:'أصل محفوظ',mime_type:photo?'image/jpeg':'text/plain',metadata:{title:'أصل المحاولة'},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'}],total:1,limit:100,offset:0})});
  if(p.endsWith('/platform-copies'))return r.fulfill({json:{items:[{platform:'facebook',label:'Facebook',fields:{title:'',description:'نص محفوظ',tags:[],alt_text:''},version:1,source_fingerprint:'v1',current_source_fingerprint:'v1',source_stale:false,central_approval:'APPROVED',field_status:'FIELDS_VALIDATED',blockers:[],warnings:[],media_checks_pending:[],execution_blockers:[],sources:[]}]}});
  if(p==='/sources'||p.startsWith('/posts')||p.startsWith('/api/control/'))return r.fulfill({json:[]});if(p.startsWith('/api/'))return r.fulfill({json:{items:[],total:0}});return r.continue();
 });
 await page.setViewportSize({width,height:844});await page.goto(`/bank?artifact_status=APPROVED&artifact_id=${id}&${segment}_job_id=${jid}`);
 const panel=page.getByLabel(photo?'تنفيذ صورة Facebook':'تنفيذ نص Facebook',{exact:true}),result=panel.getByLabel('نتيجة محاولة Facebook المحفوظة',{exact:true});
 await expect(panel).toBeFocused();await expect(panel.getByRole('heading')).toBeInViewport();
 await expect(panel.getByLabel('موعد نص Facebook')).toHaveCount(0);await expect(panel.getByLabel('منطقة نص Facebook')).toHaveCount(0);await expect(panel).not.toContainText('فارغ يعني بعد الاعتماد الآن');
 if(state==='published'){
  await expect(result.getByText('الحالة: نُشر مؤكداً عند آخر تحقق',{exact:true})).toBeInViewport();
  await expect(result.getByText('الصفحة العامة:',{exact:false})).toBeInViewport();await expect(result.getByText('الموعد:',{exact:false})).toBeInViewport();
  await expect(result).toContainText('Asia/Riyadh');await expect(result).toContainText('نتيجة محفوظة، وليست تحققاً جديداً');
  const link=result.getByRole('link',{name:'فتح المنشور المؤكد',exact:true});await expect(link).toBeInViewport();await expect(link).toHaveAttribute('href','https://www.facebook.com/123/posts/456');
  await page.screenshot({path:info.outputPath(`saved-result-${segment}-${width}.png`)});
 }else{
  await expect(panel.getByRole('alert')).toBeVisible();await expect(result).toHaveCount(0);await expect(panel.getByRole('link')).toHaveCount(0);await expect(panel.getByRole('button',{name:'إعادة قراءة المحاولة المرتبطة',exact:true})).toBeVisible();
 }
 // Development StrictMode mounts this existing effect twice.
 expect(reads).toBe(2);expect(writes).toEqual([]);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
