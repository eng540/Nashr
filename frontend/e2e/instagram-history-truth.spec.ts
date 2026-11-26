import {test,expect} from '@playwright/test';
const id='12345678-1234-4123-8123-123456789ab1',jid='12345678-1234-4123-8123-123456789ab2';
for(const state of ['PUBLISHED','PUBLISHED_ID_KNOWN','DRAFT','PUBLISH_UNKNOWN','EXPIRED','REVOKED_PUBLISHED'])test('recorded Instagram result does not offer a second decision '+state,async({page},info)=>{
 const writes:string[]=[];
 const item={id,kind:'IMAGE',status:'AVAILABLE',content:null,mime_type:'image/jpeg',metadata:{title:'أصل محفوظ'},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'};
 await page.route('**/*',r=>{const p=new URL(r.request().url()).pathname;if(r.request().method()!=='GET')writes.push(p);
 if(p.endsWith('/result'))return r.fulfill({json:{id:jid,artifact_id:id,login_mode:'UNIFIED',state:state==='EXPIRED'?'DRAFT':state==='REVOKED_PUBLISHED'?'PUBLISHED':state,decision_state:state==='REVOKED_PUBLISHED'?'REVOKED':'APPROVED',approval_expired:state==='EXPIRED',dispatch_state:(state==='DRAFT'||state==='EXPIRED')?'PENDING':state==='PUBLISH_UNKNOWN'?'RECONCILE_ONLY':state==='PUBLISHED_ID_KNOWN'?'RESULT_KNOWN':'PUBLISHED',can_propose:false,username:'exact_account',caption:'نص المحاولة المحفوظ دون اختصار',permalink:(state==='PUBLISHED'||state==='REVOKED_PUBLISHED')?'https://www.instagram.com/reel/Exact123/':null,media_sha256:'b'.repeat(64),created_at:'2026-11-23T10:00:00Z'}});
 if(p==='/api/artifacts')return r.fulfill({json:{items:[item],total:1,limit:100,offset:0}});
 if(p.endsWith('/platform-copies'))return r.fulfill({json:{items:[]}});
 if(p==='/posts'||p==='/sources'||p.startsWith('/api/control/'))return r.fulfill({json:[]});if(p.startsWith('/api/'))return r.fulfill({json:{items:[],total:0}});return r.continue();});
 await page.setViewportSize({width:390,height:844});await page.goto('/bank?artifact_status=APPROVED&artifact_id='+id+'&instagram_job_id='+jid);
 const panel=page.getByLabel('عملية Instagram المرتبطة',{exact:true});await expect(panel).toContainText('نص المحاولة المحفوظ دون اختصار');
 if(state==='EXPIRED')await expect(panel).toContainText('انتهت نافذة الموافقة؛ لا تسمح بتنفيذ جديد.');
 if(state==='REVOKED_PUBLISHED'){await expect(panel).toContainText('سُحبت الموافقة محلياً؛ لا يحذف ذلك منشوراً سبق نشره.');await expect(panel).toContainText('حالة التنفيذ: نُشر مؤكداً');await expect(panel.getByRole('link')).toHaveAttribute('href','https://www.instagram.com/reel/Exact123/');}
 await panel.getByText('مراجعة قرار هذه المحاولة أو إلغاؤه صراحةً',{exact:true}).click();
 await expect(panel.getByText('لهذه المحاولة قرار أو نتيجة محفوظة.',{exact:false})).toBeVisible();
 await expect(panel.getByLabel('موعد بدء نشر Instagram',{exact:true})).toHaveCount(0);
 await expect(panel.getByRole('button',{name:'عرض قرار بدء النشر في الموعد المختار، دون موافقة',exact:true})).toHaveCount(0);
 await expect(panel.getByRole('button',{name:'تحقق من نتيجة التنفيذ',exact:true})).toBeVisible();
 await panel.screenshot({path:info.outputPath('recorded-result-mobile.png')});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();expect(writes).toEqual([]);
});

test('history shows the saved decision and permalink instead of missing approval gates',async({page},info)=>{
 const writes:string[]=[];
 const item={id:'vid',kind:'VIDEO',status:'AVAILABLE',content:null,mime_type:'video/mp4',metadata:{title:'أصل محفوظ'},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z'};
 await page.route('**/*',r=>{const p=new URL(r.request().url()).pathname;if(r.request().method()!=='GET')writes.push(p);
 if(p==='/api/artifacts')return r.fulfill({json:{items:[item],total:1}});
 if(p.endsWith('/platform-copies'))return r.fulfill({json:{items:[{platform:'instagram',label:'Instagram',fields:{title:'',description:'النص كامل',tags:[],alt_text:''},version:1,source_fingerprint:'a'.repeat(64),current_source_fingerprint:'a'.repeat(64),origin:'USER_EDITED',source_stale:false,central_approval:'APPROVED',field_status:'FIELDS_VALIDATED',blockers:[],warnings:[],media_checks_pending:[],execution_blockers:[],sources:[]}]}});
 if(p.endsWith('/execution-drafts'))return r.fulfill({json:{items:[{id:'exec',state:'PUBLISHED',dispatch_state:'PUBLISHED',decision_state:'APPROVED',approval_recorded:true,due_at:'2026-11-26T18:23:00Z',can_propose:false,permalink:'https://www.instagram.com/reel/Exact123/',caption:'النص كامل',username:'saved_account',remaining_gates:[]}]}});
 if(p.endsWith('/drafts'))return r.fulfill({json:{items:[]}});
 if(p.endsWith('/media-url'))return r.fulfill({json:{url:null}});
 if(p==='/posts'||p==='/sources'||p.startsWith('/api/control/'))return r.fulfill({json:[]});if(p.startsWith('/api/'))return r.fulfill({json:{items:[],total:0}});return r.continue();});
 await page.goto('/bank?library_view=expanded');await page.getByLabel('حالة مراجعة المخرجات').selectOption('APPROVED');const copies=page.getByLabel('نسخ المنصات vid',{exact:true});await copies.locator('summary').first().click();await copies.getByRole('button',{name:'عرض النسخ المحفوظة',exact:true}).click();await copies.getByLabel('منصة النسخة vid').selectOption('instagram');const panel=copies.getByLabel('معاينة خطة Instagram',{exact:true});await panel.locator('summary').first().click();await panel.getByText('@saved_account · نُشر مؤكداً',{exact:true}).click();
 await expect(panel.getByText('موافقة نشر محفوظة لهذا القرار؛ لا تعني صلاحية غير محدودة.',{exact:true})).toBeVisible();
 await expect(panel.getByRole('link',{name:'فتح منشور Instagram المؤكد',exact:true})).toHaveAttribute('href','https://www.instagram.com/reel/Exact123/');
 await expect(panel.getByLabel('موعد بدء نشر Instagram',{exact:true})).toHaveCount(0);
 await page.setViewportSize({width:390,height:844});await panel.screenshot({path:info.outputPath('history-published-mobile.png')});expect(writes).toEqual([]);
});
