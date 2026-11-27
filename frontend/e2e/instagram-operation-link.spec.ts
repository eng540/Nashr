import {libraryFixture} from './libraryFixture';
import {test,expect} from '@playwright/test';
const id='12345678-1234-4123-8123-123456789ab1',jid='12345678-1234-4123-8123-123456789ab2';
for(const width of [390,1280])for(const scenario of ['exact','mismatch','failure','invalid'])test('Instagram exact operation handoff '+scenario+' '+width,async({page},info)=>{
 const writes:string[]=[];let resultReads=0;
 const item={id,kind:'IMAGE',status:'AVAILABLE',content:null,mime_type:'image/jpeg',metadata:{title:'أصل العملية'},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'};
 await page.route('**/*',r=>{const p=new URL(r.request().url()).pathname;if(r.request().method()!=='GET')writes.push(p);
 if(p.endsWith('/result')){resultReads++;if(scenario==='failure')return r.fulfill({status:503,json:{detail:'synthetic unavailable'}});return r.fulfill({json:{id:jid,artifact_id:scenario==='mismatch'?'wrong':id,login_mode:'UNIFIED',state:'PUBLISHED',dispatch_state:'PUBLISHED',username:'exact_account',caption:'نص المحاولة القديمة المحددة',permalink:'https://www.instagram.com/p/Exact123/',media_sha256:'b'.repeat(64),created_at:'2026-11-23T10:00:00Z'}});}
 if(p==='/api/artifacts'||p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return r.fulfill({json:libraryFixture(r, {items:[item],total:1,limit:100,offset:0})});
 // No current platform copy and no execution history: old result must remain reachable.
 if(p.endsWith('/platform-copies'))return r.fulfill({json:{items:[]}});
 if(p==='/posts'||p==='/sources'||p.startsWith('/api/control/'))return r.fulfill({json:[]});if(p.startsWith('/api/'))return r.fulfill({json:{items:[],total:0}});return r.continue();});
 await page.setViewportSize({width,height:844});await page.goto('/bank?artifact_status=APPROVED&artifact_id='+id+'&copy_platform=instagram&instagram_job_id='+(scenario==='invalid'?'not-a-job':jid));
 const panel=page.getByLabel('عملية Instagram المرتبطة',{exact:true});await expect(panel).toBeVisible();await expect(panel).toBeFocused();await expect(panel.getByRole('heading')).toBeInViewport();
 if(scenario==='exact'){await expect(panel).toContainText('نص المحاولة القديمة المحددة');await expect(panel).toContainText('@exact_account');await expect(panel.getByRole('link')).toHaveAttribute('href','https://www.instagram.com/p/Exact123/');await expect(panel.getByRole('button',{name:'تأكيد النشر العلني لهذا المحتوى',exact:true})).toHaveCount(0);await page.screenshot({path:info.outputPath('instagram-exact-operation-'+width+'.png')});await panel.getByRole('button',{name:'تحديث نتيجة المحاولة المحددة',exact:true}).click();await expect.poll(()=>resultReads).toBe(2);await expect(panel).not.toBeFocused();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();}
 else{await expect(panel.getByRole('alert')).toBeVisible();await expect(panel.getByText('نص المحاولة القديمة المحددة')).toHaveCount(0);await expect(panel.getByRole('link')).toHaveCount(0);await expect(panel.getByText('مراجعة قرار هذه المحاولة أو إلغاؤه صراحةً')).toHaveCount(0);}
 expect(resultReads).toBe(scenario==='invalid'?0:scenario==='exact'?2:1);expect(writes).toEqual([]);
});
