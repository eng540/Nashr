import {test,expect} from '@playwright/test';
test('Facebook exact photo needs separate public approval and can cancel before send',async({page},info)=>{
 const id='12345678-1234-4123-8123-123456789abc',jid='abcdef12-1234-4123-8123-123456789abc';const writes:string[]=[];let job:any=null;
 const item={id,source_knowledge_unit_id:'u',kind:'IMAGE',status:'AVAILABLE',content:'الأصل كامل',storage_uri:'s3://test/photo',mime_type:'image/jpeg',metadata:{title:'نص هندسي معتمد'},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'};
 const copies=['telegram','facebook'].map(platform=>({platform,label:platform,fields:{title:'',description:'نص كامل غير مختصر',tags:[],alt_text:''},version:1,source_fingerprint:'v1',current_source_fingerprint:'v1',origin:'USER_EDITED',source_stale:false,central_approval:'APPROVED',field_status:'FIELDS_VALIDATED',blockers:[],warnings:[],media_checks_pending:[],execution_blockers:['يلزم قرار مستقل'],sources:[]}));
 await page.route('**/*',route=>{const req=route.request(),p=new URL(req.url()).pathname;
 if(p.startsWith('/api/connections/facebook/photo-posts')){
  if(req.method()==='GET')return route.fulfill({json:job});writes.push(p);
  if(p.endsWith('/preview')){expect(req.postDataJSON()).toEqual({due_at:'2026-11-26T09:30:00.000Z',timezone_name:'Asia/Riyadh'});job={id:jid,artifact_id:id,state:'DRAFT',snapshot_hash:'a'.repeat(64),snapshot:{message:'نص كامل غير مختصر',connection:{page_id:'123',page_name:'صفحة هندسية تجريبية'},due_at:'2026-11-26T09:30:00Z',timezone:'Asia/Riyadh'},post_id:null,permalink:null,error_code:null};}
  if(p.endsWith('/approve')){expect(req.postDataJSON()).toEqual({snapshot_hash:'a'.repeat(64),exact_words_approved:true,public_page_approved:true,rights_confirmed:true,exact_image_approved:true,private_bytes_disclosure_approved:true});job={...job,state:'APPROVED'};}
  if(p.endsWith('/cancel'))job={...job,state:'CANCELLED'};
  return route.fulfill({json:job});
 }
 if(req.method()!=='GET')throw new Error('Unexpected write '+p);
 if(p==='/api/artifacts')return route.fulfill({json:{items:[item],total:1,limit:100,offset:0}});
 if(p===`/api/artifacts/${id}/platform-copies`)return route.fulfill({json:{items:copies}});
 if(p==='/sources'||p.startsWith('/api/control/')||p==='/posts')return route.fulfill({json:[]});
 if(p.startsWith('/api/'))return route.fulfill({json:{items:[],total:0}});return route.continue();
 });
 await page.goto('/bank?artifact_status=APPROVED&library_view=expanded');const copiesPanel=page.getByLabel(`نسخ المنصات ${id}`,{exact:true});await copiesPanel.getByText('نسخ المنصات · حقول مرتبطة بالأصل',{exact:true}).click();await copiesPanel.getByRole('button',{name:'عرض النسخ المحفوظة',exact:true}).click();await copiesPanel.getByLabel(`منصة النسخة ${id}`,{exact:true}).selectOption('facebook');
 const panel=page.getByLabel('تنفيذ صورة Facebook',{exact:true});await expect(panel).toBeVisible();expect(writes).toEqual([]);
 await panel.getByLabel('موعد نص Facebook',{exact:true}).fill('2026-11-26T12:30');await panel.getByRole('button',{name:'معاينة صورة Facebook والنص والصفحة دون نشر',exact:true}).click();
 const approve=panel.getByRole('button',{name:'اعتماد تنفيذ صورة Facebook المحددة',exact:true});await expect(approve).toBeDisabled();
 await panel.getByRole('checkbox').nth(0).check();await panel.getByRole('checkbox').nth(1).check();await expect(approve).toBeDisabled();await panel.getByRole('checkbox').nth(2).check();
 await expect(approve).toBeDisabled();await panel.getByRole('checkbox').nth(3).check();await expect(approve).toBeDisabled();await panel.getByRole('checkbox').nth(4).check();
 await page.setViewportSize({width:390,height:844});await panel.screenshot({path:info.outputPath('facebook-photo-mobile.png'),style:'header{visibility:hidden}'});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await approve.click();await expect(panel.getByText('الحالة: معتمد بانتظار التنفيذ',{exact:true})).toBeVisible();await panel.getByRole('button',{name:'إلغاء القرار قبل بدء الإرسال',exact:true}).click();await expect(panel.getByText('الحالة: ملغى محلياً',{exact:true})).toBeVisible();
 expect(writes).toEqual([`/api/connections/facebook/photo-posts/materials/${id}/preview`,`/api/connections/facebook/photo-posts/${jid}/approve`,`/api/connections/facebook/photo-posts/${jid}/cancel`]);
});
