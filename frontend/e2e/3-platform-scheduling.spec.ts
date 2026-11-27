import {test,expect} from '@playwright/test';
test('scheduled operations stay read-only with explicit state and safe exact links',async({page},info)=>{
 page.on('pageerror',e=>console.log('PAGEERROR',e.message));const writes:string[]=[];
 await page.route('**/*',r=>{const p=new URL(r.request().url()).pathname;if(r.request().method()!=='GET')writes.push(p);
 if(p==='/api/platform-operations')return r.fulfill({json:{total:2,items:[{id:'ig',artifact_id:'original',platform:'instagram',due_at:'2026-11-26T11:30:00Z',timezone:'Asia/Riyadh',state:'PENDING',execution_state:'DRAFT',destination:'creator',title:'مادة مجدولة مستقلة',permalink:null},{id:'fb',artifact_id:'original',platform:'facebook',due_at:'2026-11-26T12:00:00Z',timezone:'Asia/Riyadh',state:'OUTCOME_UNKNOWN',execution_state:'OUTCOME_UNKNOWN',destination:'الصفحة المختارة',title:'نتيجة تحتاج مراجعة دون إعادة إرسال',permalink:null}]}});
 if(p==='/api/artifacts/platform-variants'||p==='/sources')return r.fulfill({json:[]});
 if(p.startsWith('/api/')||p==='/posts'||p==='/sources'||p.startsWith('/schedules'))return r.fulfill({json:{items:[],total:0}});return r.continue();});
 await page.setViewportSize({width:390,height:844});await page.goto('/publishing?view=operations');const panel=page.getByLabel('عمليات Instagram وFacebook',{exact:true});await expect(panel.getByText('بانتظار الموعد · مسودة تنفيذ')).toBeVisible();await expect(panel).toContainText('نتيجة غير مؤكدة، لا إعادة إرسال');await expect(panel.getByRole('link').first()).toHaveAttribute('href','/bank?artifact_status=APPROVED&artifact_id=original&copy_platform=instagram&instagram_job_id=ig');await expect(panel.getByRole('link').last()).toHaveAttribute('href','/connections?reel_artifact_id=original&reel_job_id=fb#platform-facebook');await panel.screenshot({path:info.outputPath('platform-operations-mobile.png')});expect(writes).toEqual([]);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
test('Facebook scheduled preview pins chosen time, requires explicit approval, cancels pending operation',async({page},info)=>{
 page.on('pageerror',e=>console.log('PAGEERROR',e.message));let state='DRAFT';const writes:string[]=[];let timing:any;
 const job=()=>({id:'scheduled',state,snapshot_hash:'a'.repeat(64),permalink:null,snapshot:{caption:'نص مستقل كامل',media_sha256:'b'.repeat(64),connection:{page_id:'123',page_name:'الصفحة المختارة'},audience:'FACEBOOK_PAGE_PUBLIC_REEL',...timing,timezone:timing?.timezone_name,local_time:'2026-11-26T14:30:00+03:00'}});
 await page.route('**/api/**',r=>{const p=new URL(r.request().url()).pathname;if(!p.startsWith('/api/'))return r.continue();if(r.request().method()!=='GET')writes.push(p);
 if(p.endsWith('/prepare-delivery'))return r.fulfill({json:{published:false}});
 if(p.endsWith('/preview')){timing=r.request().postDataJSON();expect(timing).toEqual({due_at:'2026-11-26T11:30:00.000Z',timezone_name:'Asia/Riyadh'});return r.fulfill({json:job()});}
 if(p.endsWith('/approve')){state='APPROVED';return r.fulfill({json:job()});}
 if(p.endsWith('/cancel')){state='CANCELLED';return r.fulfill({json:job()});}
 if(p==='/api/connections')return r.fulfill({json:{telegram:{items:[],credential_storage_ready:true},platforms:[{key:'facebook',label:'Facebook',state:'CONNECTION_ONLY',requirements:'ربط'}]}});
 if(p.startsWith('/api/connections/'))return r.fulfill({json:{configured:true,connection:null,pending:null,requirements:[],missing_configuration:[]}});return r.fulfill({json:{items:[]}});});
 await page.setViewportSize({width:390,height:844});await page.goto('/connections?reel_artifact_id=12345678-1234-4123-8123-123456789abc');await page.getByLabel('موعد بدء نشر Facebook',{exact:true}).fill('2026-11-26T14:30');await page.getByRole('button',{name:'تجهيز نسخة توافق خاصة ومعاينة دون نشر',exact:true}).click();const commit=page.getByRole('button',{name:'تأكيد نشر Reel العام في الموعد المعروض',exact:true});await expect(commit).toBeDisabled();expect(writes).toHaveLength(2);await page.getByLabel('أوافق على نشر هذا الفيديو والوصف على الصفحة العامة في الموعد المعروض وإرسال الملف إلى Meta.',{exact:true}).check();await page.getByText('الحالة: DRAFT',{exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath('facebook-scheduled-mobile.png')});await commit.click();await page.getByRole('button',{name:'إلغاء محاولة Facebook قبل بدء الإرسال',exact:true}).click();await expect(page.getByText('الحالة: CANCELLED')).toBeVisible();expect(writes).toHaveLength(4);
});

test('confirmed Page history remains visible when its unbound result link is withheld',async({page},info)=>{
 const writes:string[]=[];
 await page.route('**/*',r=>{const p=new URL(r.request().url()).pathname;if(r.request().method()!=='GET')writes.push(p);
 if(p==='/api/platform-operations')return r.fulfill({json:{total:2,counts:{total:2,published:2,waiting:0,attention:0},items:[{id:'photo',artifact_id:'photo-original',platform:'facebook_photo',due_at:null,timezone:'Asia/Riyadh',state:'PUBLISHED_AT_LAST_CHECK',execution_state:'PUBLISHED_AT_LAST_CHECK',destination:'صفحة الصور',title:'صورة محفوظة بنتيجة مثبتة',permalink:null},{id:'text',artifact_id:'text-original',platform:'facebook_text',due_at:null,timezone:'Asia/Riyadh',state:'PUBLISHED_AT_LAST_CHECK',execution_state:'PUBLISHED_AT_LAST_CHECK',destination:'صفحة النصوص',title:'نص محفوظ برابط مطابق',permalink:'https://www.facebook.com/123/posts/456'}]}});
 if(p==='/api/artifacts/platform-variants'||p==='/sources')return r.fulfill({json:[]});
 if(p.startsWith('/api/')||p==='/posts'||p.startsWith('/schedules'))return r.fulfill({json:{items:[],total:0}});return r.continue();});
 await page.setViewportSize({width:390,height:844});await page.goto('/publishing?view=operations');
 const panel=page.getByLabel('عمليات Instagram وFacebook',{exact:true});
 const photo=panel.getByRole('article').filter({hasText:'صورة محفوظة بنتيجة مثبتة'});
 await expect(photo).toContainText('نُشر مؤكداً عند آخر تحقق');
 await expect(photo.getByRole('link',{name:'فتح المنشور المؤكد'})).toHaveCount(0);
 await expect(photo.getByRole('link')).toHaveAttribute('href','/bank?artifact_status=APPROVED&artifact_id=photo-original&photo_job_id=photo');
 const text=panel.getByRole('article').filter({hasText:'نص محفوظ برابط مطابق'});
 await expect(text.getByRole('link',{name:'فتح المنشور المؤكد'})).toHaveAttribute('href','https://www.facebook.com/123/posts/456');
 await panel.screenshot({path:info.outputPath('page-result-links-mobile.png')});
 expect(writes).toEqual([]);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
