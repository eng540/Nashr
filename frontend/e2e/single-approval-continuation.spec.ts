import {test,expect,type Page} from '@playwright/test';
import {libraryFixture} from './libraryFixture';
const id='12345678-1234-4123-8123-123456789abc',other='22345678-1234-4123-8123-123456789abc';
async function fixture(page:Page,{delay=false,fail=false,wrong=false}:{delay?:boolean;fail?:boolean;wrong?:boolean}={}){
 let approved=false;const writes:string[]=[];let release=()=>{};
 const gate=new Promise<void>(resolve=>release=resolve);
 const original={id,source_knowledge_unit_id:'u',kind:'TEXT',status:'AVAILABLE',content:'نص أصل كامل للمراجعة دون نشر',storage_uri:null,mime_type:'text/plain',metadata:{title:'مادة رحلة الاعتماد الفردي'},review_status:'DRAFT',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'};
 await page.route('**/*',async r=>{const u=new URL(r.request().url()),p=u.pathname;
 if(r.request().method()!=='GET')writes.push(p);
 if(p===`/api/artifacts/${id}/approve`){if(delay)await gate;if(fail)return r.fulfill({status:409,json:{detail:'تغيرت المادة؛ راجع الأصل المحفوظ'}});approved=true;return r.fulfill({json:{...original,id:wrong?other:id,review_status:'APPROVED'}});}
 const items=[{...original,review_status:approved?'APPROVED':'DRAFT'},{...original,id:other,metadata:{title:'مادة أخرى لا ننتقل منها'}}];
 if(['/api/artifacts/library','/api/artifacts/library-items','/api/artifacts'].includes(p))return r.fulfill({json:libraryFixture(r,{items:p.endsWith('/library-items')?items:items.filter(i=>i.review_status===(u.searchParams.get('review_status')??'DRAFT')),total:2})});
 if(p===`/api/artifacts/${id}/distribution-readiness`)return r.fulfill({json:{artifact_id:id,central_approval:'APPROVED',source_fingerprint:'v1',original_text:original.content,selection_stale:false,targets:[]}});
 if(p==='/sources'||p.startsWith('/posts')||p==='/api/artifacts/platform-variants'||p.startsWith('/api/control/'))return r.fulfill({json:[]});
 if(p.startsWith('/api/'))return r.fulfill({json:{items:[],total:0}});return r.continue();});
 return {writes,release};
}
for(const width of [390,1280])test(`single central approval keeps exact material ready for next step at ${width}`,async({page},info)=>{
 const f=await fixture(page);await page.setViewportSize({width,height:844});await page.goto(`/bank?artifact_id=${id}&artifact_status=DRAFT`);
 await page.getByRole('button',{name:'اعتماد المادة فقط، دون نشر',exact:true}).click();
 await expect(page).toHaveURL(/artifact_status=APPROVED/);
 const space=page.getByLabel(`مساحة المادة ${id}`,{exact:true});await expect(space).toBeVisible();
 const next=page.getByRole('heading',{name:'الخطوة التالية: المادة معتمدة، اختر وجهاتها وافحص متطلباتها',exact:true});await expect(next).toBeVisible();
 await expect(page.getByTestId('media-selection-count')).toHaveText('0 محدد');
 await next.scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath(`single-approval-${width}.png`)});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();expect(f.writes).toEqual([`/api/artifacts/${id}/approve`]);
});
for(const leave of ['return','next','state','away','return-again'])test(`late approval does not steal navigation: ${leave}`,async({page})=>{
 const f=await fixture(page,{delay:true});await page.goto(`/bank?artifact_id=${id}&artifact_status=DRAFT`);
 await page.getByRole('button',{name:'اعتماد المادة فقط، دون نشر',exact:true}).click();await expect.poll(()=>f.writes.length).toBe(1);
 if(leave==='return'||leave==='return-again')await page.getByRole('button',{name:'العودة إلى المكتبة',exact:true}).click();
 if(leave==='next')await page.getByRole('button',{name:'المادة التالية',exact:true}).click();
 if(leave==='state')await page.getByLabel('حالة مراجعة المخرجات',{exact:true}).selectOption('APPROVED');
 if(leave==='away')await page.getByRole('link',{name:'مساحة النشر',exact:true}).first().click();
 if(leave==='return-again')await page.locator(`#material-open-${id}`).click();
 const url=page.url();f.release();await page.waitForTimeout(250);await expect(page).toHaveURL(url);expect(f.writes).toHaveLength(1);
});
for(const failure of ['409','wrong'])test(`approval ${failure} leaves reviewed context with visible feedback`,async({page})=>{
 const f=await fixture(page,{fail:failure==='409',wrong:failure==='wrong'});await page.goto(`/bank?artifact_id=${id}&artifact_status=DRAFT`);
 await page.getByRole('button',{name:'اعتماد المادة فقط، دون نشر',exact:true}).click();await expect(page.getByRole('alert').filter({hasText:failure==='409'?'تغيرت المادة':'لم تتطابق نتيجة الاعتماد'})).toBeVisible();
 await expect(page).toHaveURL(/artifact_status=DRAFT/);expect(f.writes).toHaveLength(1);
});
