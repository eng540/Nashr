import {test,expect} from '@playwright/test';
test('private Facebook review requires choices and never uploads or connects',async({page},info)=>{
 const id='facebook-review';let saved=false,cancelled=false;const unsafe:string[]=[];
 const item={id,kind:'IMAGE',source_knowledge_unit_id:'u',status:'AVAILABLE',content:null,storage_uri:'s3://private/photo.jpg',mime_type:'image/jpeg',metadata:{title:'فيديو Facebook للمراجعة'},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'};
 const copy={platform:'facebook',label:'Facebook',fields:{title:'',description:'الوصف الكامل دون قص أو تعديل',tags:[],alt_text:''},version:2,source_fingerprint:'a'.repeat(64),current_source_fingerprint:'a'.repeat(64),origin:'USER_EDITED',source_stale:false,central_approval:'APPROVED',field_status:'FIELDS_VALIDATED',blockers:[],warnings:[],media_checks_pending:[],execution_blockers:[],sources:[]};
 let snapshot:any;
 await page.route('**/*',async route=>{const r=route.request(),p=new URL(r.url()).pathname;
 if(p==='/api/artifacts')return route.fulfill({json:{items:[item],total:1,limit:100,offset:0}});
 if(p.endsWith('/platform-copies'))return route.fulfill({json:{items:[copy]}});
 if(p.endsWith('/preview')&&p.includes('/facebook/materials/')){const body=r.postDataJSON();snapshot={artifact_id:id,copy_version:2,kind:'IMAGE',fields:copy.fields,intent:body,inspection:null,blockers:['صفحة غير مرتبطة، لا نشر حي.'],preview_hash:'c'.repeat(64),can_save_draft:!!body.page_id&&body.public_page_acknowledged&&body.rights_confirmed,caveat:'تجهيز خاص فقط دون قراءة ملف أو اتصال بـMeta.'};return route.fulfill({json:snapshot});}
 if(p.endsWith('/drafts/saved/cancel')){cancelled=true;return route.fulfill({json:{state:'CANCELLED',remote_changed:false}});}
 if(p.endsWith('/drafts')&&p.includes('/facebook/materials/')){if(r.method()==='POST'){const body=r.postDataJSON();expect(body.page_id).toBe('123');expect(body.public_page_acknowledged).toBe(true);expect(body.rights_confirmed).toBe(true);expect(body).not.toHaveProperty('authorized');saved=true;}return route.fulfill({json:r.method()==='POST'?{id:'saved',snapshot,state:'DRAFT'}:{items:saved?[{id:'saved',snapshot,state:cancelled?'CANCELLED':'DRAFT',created_at:'2026-11-24T08:00:00Z',stale:false}]:[]}});}
 if(p.endsWith('/media-url'))return route.fulfill({json:{url:null}});
 if(p.startsWith('/api/')&&r.method()!=='GET')unsafe.push(p);
 if(['/posts','/sources','/api/control/'].some(x=>p.startsWith(x)))return route.fulfill({json:[]});return route.continue();});
 await page.goto('/bank?library_view=expanded');await page.getByLabel('حالة مراجعة المخرجات').selectOption('APPROVED');
 const copies=page.getByLabel('نسخ المنصات '+id,{exact:true});await copies.locator('summary').first().click();await copies.getByRole('button',{name:'عرض النسخ المحفوظة',exact:true}).click();await copies.getByLabel('منصة النسخة '+id).selectOption('facebook');
 const panel=copies.getByLabel('معاينة خطة Facebook',{exact:true});await panel.locator('summary').first().click();expect(saved).toBe(false);
 await panel.getByRole('button',{name:'عرض معاينة Facebook دون نشر',exact:true}).click();await expect(panel.getByRole('button',{name:'حفظ مسودة Facebook فقط، دون نشر',exact:true})).toBeDisabled();
 await panel.getByLabel('صفحة Facebook المقترحة',{exact:true}).fill('123');await panel.getByRole('checkbox').nth(0).check();await panel.getByRole('checkbox').nth(1).check();
 await panel.getByRole('button',{name:'عرض معاينة Facebook دون نشر',exact:true}).click();await expect(panel.getByText(copy.fields.description,{exact:true})).toBeVisible();
 await panel.getByRole('button',{name:'حفظ مسودة Facebook فقط، دون نشر',exact:true}).click();await expect(panel.getByRole('status')).toContainText('دون نشر');expect(saved).toBe(true);expect(unsafe).toEqual([]);
 await page.addStyleTag({content:'header{visibility:hidden}'});await page.setViewportSize({width:1280,height:1000});await panel.screenshot({path:info.outputPath('facebook-review-desktop.png')});await page.setViewportSize({width:390,height:844});await panel.screenshot({path:info.outputPath('facebook-review-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await panel.getByText('مسودة Facebook محفوظة، ليست خطة تنفيذ',{exact:false}).click();await panel.getByRole('button',{name:'إلغاء مسودة Facebook محلياً',exact:true}).click();await expect(panel.getByText('مسودة Facebook ملغاة محلياً',{exact:false})).toBeVisible();expect(unsafe).toEqual([]);
});
