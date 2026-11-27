import {test,expect} from '@playwright/test';
const bindings=[
 {key:'instagram_unified',identity:'saved_unified',saved_connection_present:true,enabled_locally:true,last_check_at:'2026-11-27T17:00:00Z',last_check_ok:true,stored_expires_at:null,scope_status:'MISSING_FROM_SAVED_EVIDENCE',granted_scopes_at_saved_evidence:['instagram_basic','instagram_content_publish'],scope_evidence_source:'stored_token_debug_scopes',documented_core_scopes:['instagram_basic','instagram_manage_insights'],missing_from_saved_scope_evidence:['instagram_manage_insights'],core_source_url:'https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/insights'},
 {key:'instagram_direct',identity:null,saved_connection_present:false,scope_status:'NO_SAVED_CONNECTION',granted_scopes_at_saved_evidence:null,documented_core_scopes:['instagram_business_basic','instagram_business_manage_insights'],missing_from_saved_scope_evidence:null},
 {key:'instagram_page',identity:'page_linked',saved_connection_present:true,enabled_locally:false,last_check_ok:false,stored_expires_at:'2026-01-01T00:00:00Z',scope_status:'GRANT_EVIDENCE_UNKNOWN',granted_scopes_at_saved_evidence:null,documented_core_scopes:['instagram_basic','instagram_manage_insights','pages_read_engagement'],missing_from_saved_scope_evidence:null},
 {key:'facebook_page',identity:'صفحة محفوظة',saved_connection_present:true,enabled_locally:true,scope_status:'REQUIREMENTS_NOT_MAPPED',granted_scopes_at_saved_evidence:['pages_read_engagement'],scope_evidence_source:'stored_token_debug_scopes',documented_core_scopes:null,missing_from_saved_scope_evidence:null},
];
for(const width of [390,1280])for(const mode of ['report','error','empty','loading'])test(`Insights stored evidence ${mode} ${width}`,async({page},info)=>{
 await page.setViewportSize({width,height:844});let writes=0,external=0;
 await page.route('**/*',async route=>{const r=route.request(),u=new URL(r.url()),p=u.pathname;if(r.method()!=='GET')writes++;if(/(^|\.)(facebook|instagram)\.com$/.test(u.hostname))external++;
 if(p==='/api/analytics/capabilities'){
 if(mode==='loading')return;
 if(mode==='error')return route.fulfill({status:503,json:{detail:'unavailable'}});
 return route.fulfill({json:{mode:'STORED_EVIDENCE_ONLY',metrics_fetched:false,bindings:mode==='empty'?[]:bindings}});}
 if(p==='/api/connections')return route.fulfill({json:{telegram:{items:[],credential_storage_ready:true},platforms:[]}});
 if(p==='/api/connections/tiktok/requirements')return route.fulfill({json:{modes:[],media_requirements:[],sources:[]}});
 if(p.startsWith('/api/connections/'))return route.fulfill({json:{configured:false,connection:null,pending:null,requirements:[],missing_configuration:[]}});
 if(p.startsWith('/api/'))return route.fulfill({json:{items:[],total:0}});return route.continue();});
 await page.goto('/connections');const section=page.getByRole('region',{name:'حدود الإحصاءات'});await section.scrollIntoViewIfNeeded();await expect(section).toContainText('لم نجلب مشاهدات');await expect(section).toContainText('أوقات نشاط الجمهور غير مؤكدة');
 if(mode==='report'){
 await expect(section).toContainText('صلاحيات أولية غائبة');await expect(section).toContainText('دليل الصلاحيات الممنوحة غير محفوظ');await expect(section).toContainText('متطلبات المقاييس لم');await section.locator('summary').first().click();await expect(section).toContainText('instagram_manage_insights');
 expect(await section.getByRole('button').count()).toBe(0);expect(await section.locator('input').count()).toBe(0);
 }else if(mode==='error'){await expect(section.getByRole('alert')).toContainText('لا يعني ذلك غياب الحساب');await section.getByRole('button').click();}else if(mode==='loading'){await expect(section.getByRole('status')).toContainText('دون الاتصال');}else await expect(section).toContainText('لا نستنتج منها حالة الربط');
 expect(writes).toBe(0);expect(external).toBe(0);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();await section.screenshot({path:info.outputPath(`insights-${mode}-${width}.png`)});await section.scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath(`viewport-${mode}-${width}.png`)});
});
