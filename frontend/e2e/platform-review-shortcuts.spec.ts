import {libraryFixture} from './libraryFixture';
import {test,expect} from '@playwright/test';
test('single-material platform review is visible without changing destinations or writing',async({page},info)=>{
 const id='12345678-1234-4123-8123-123456789abc';const writes:string[]=[];let reads=0;let approved=true;
 const item={id,source_knowledge_unit_id:'u',kind:'VIDEO',status:'AVAILABLE',content:null,storage_uri:'s3://test/video.mp4',mime_type:'video/mp4',metadata:{title:'مادة مراجعة مسار محفوظ',caption:'وصف محفوظ كامل'},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'};
 const copies=['telegram','instagram','youtube','facebook','tiktok','x'].map(platform=>({platform,label:platform,fields:{title:'عنوان محفوظ',description:'وصف محفوظ كامل',tags:[],alt_text:''},version:1,source_fingerprint:'v1',current_source_fingerprint:'v1',origin:'UNCHANGED_ORIGINAL',source_stale:false,central_approval:'APPROVED',field_status:'FIELDS_VALIDATED',blockers:[],warnings:[],media_checks_pending:['فحص الوسيط مستقل'],execution_blockers:['لا إذن تنفيذ'],sources:[]}));
 const readiness={artifact_id:id,source_fingerprint:'v1',central_approval:'APPROVED',original_text:'وصف محفوظ كامل',selection_stale:false,targets:copies.map(c=>({platform:c.platform,label:c.label,selected:false,copy_status:'FIELDS_VALIDATED',copy_blockers:[],execution_blockers:['يلزم فحص حساب ووسيط مستقل']}))};
 await page.route('**/*',r=>{const p=new URL(r.request().url()).pathname;if(r.request().method()!=='GET')writes.push(p);
 if(p==='/api/artifacts'||p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return r.fulfill({json:libraryFixture(r, {items:[item],total:1,limit:100,offset:0})});
 if(p===`/api/artifacts/${id}/platform-copies`){reads++;return r.fulfill({json:{items:copies}});}
 if(p===`/api/artifacts/${id}/distribution-readiness`)return r.fulfill({json:{...readiness,central_approval:approved?'APPROVED':'DRAFT'}});
 if(p==='/api/connections')return r.fulfill({json:{telegram:{items:[],credential_storage_ready:true},platforms:[{key:'facebook',label:'Facebook',state:'CONNECTION_ONLY',requirements:'ربط مستقل'}]}});
 if(p==='/api/connections/facebook')return r.fulfill({json:{configured:false,connection:null,pending:null,requirements:[],missing_configuration:[],source:'https://developers.facebook.com/'}});
 if(p.startsWith('/api/connections/instagram'))return r.fulfill({json:{configured:false,connection:null,pending:null,requirements:[],missing_configuration:[]}});
 if(p.startsWith('/posts')||p==='/sources'||p.startsWith('/api/control/')||p==='/posts'||p==='/api/artifacts/platform-variants')return r.fulfill({json:[]});
 if(p.startsWith('/api/'))return r.fulfill({json:{items:[],total:0}});return r.continue();});
 for(const width of [390,1280]){
 await page.setViewportSize({width,height:844});await page.goto('/bank?artifact_status=APPROVED&library_view=expanded');
 const readinessPanel=page.getByLabel(`جاهزية توزيع ${id}`,{exact:true});await readinessPanel.getByRole('button',{name:'فحص جاهزية واختيار المنصات (1)',exact:true}).click();await expect(readinessPanel.getByRole('button',{name:'حفظ اختيار الوجهات فقط',exact:true})).toBeVisible();
 const strip=readinessPanel.getByRole('navigation',{name:'مراجعة نسخ المادة دون تغيير الوجهات',exact:true});await expect(strip).toBeVisible();await expect(strip).toContainText('قبول الحقول لا يثبت ربط الحساب');const shortcut=strip.getByRole('button',{name:'مراجعة نسخة facebook',exact:true});await expect(shortcut).toBeVisible();
 await readinessPanel.screenshot({path:info.outputPath('readiness-'+width+'.png'),style:'header,a[href="#main-content"]{visibility:hidden}'});
 await shortcut.focus();await expect(shortcut).toBeFocused();await shortcut.press('Enter');const panel=page.getByLabel(`نسخ المنصات ${id}`,{exact:true});await expect(panel.getByLabel(`منصة النسخة ${id}`,{exact:true})).toHaveValue('facebook');expect(reads).toBe(width===390?1:2);await expect(readinessPanel.getByRole('checkbox',{checked:true})).toHaveCount(0);expect(writes).toEqual([]);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();

 }
 approved=false;await page.reload();const blocked=page.getByLabel(`جاهزية توزيع ${id}`,{exact:true});await blocked.getByRole('button',{name:'فحص جاهزية واختيار المنصات (1)',exact:true}).click();await expect(blocked.getByText('ابدأ بقرار مراجعة المادة أعلاه.',{exact:false})).toBeVisible();await expect(blocked.getByRole('navigation',{name:'مراجعة نسخ المادة دون تغيير الوجهات',exact:true})).toHaveCount(0);expect(writes).toEqual([]);
});
