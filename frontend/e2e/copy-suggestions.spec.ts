import {libraryFixture} from './libraryFixture';
import {test,expect} from '@playwright/test';
test('optional suggestions show disabled live provider and require reviewed isolated application',async({page},info)=>{
 const id='suggestion-original';let proposed=false,applied=false;const calls:string[]=[];
 const original='نص أصلي كامل لا يستبدل بالتوليد';
 const fields={title:'',description:original,tags:[],alt_text:''};
 const copy=()=>({platform:'telegram',label:'Telegram',fields:{...fields,description:applied?'اقتراح اصطناعي للنسخة':original},version:applied?2:1,source_fingerprint:'a'.repeat(64),current_source_fingerprint:'a'.repeat(64),source_stale:false,central_approval:'APPROVED',origin:'UNCHANGED_ORIGINAL',field_status:'FIELDS_VALIDATED',blockers:[],warnings:[],media_checks_pending:[],execution_blockers:[],sources:[]});
 await page.route('**/*',async route=>{const r=route.request(),p=new URL(r.url()).pathname;
 if(p.endsWith('/suggestions/apply')){calls.push(p);expect(r.postDataJSON().confirmed).toBe(true);applied=true;return route.fulfill({json:copy()});}
 if(p.endsWith('/suggestions')){calls.push(p);return route.fulfill({json:{state:proposed?'PROPOSED':'SERVICE_DISABLED',reason:proposed?'اقتراح اصطناعي للاختبار فقط':'التوليد الحي غير مفعل. بقي الأصل كما هو.',fields:{...fields,description:proposed?'اقتراح اصطناعي للنسخة':original},copy_version:1,source_fingerprint:'a'.repeat(64),...(proposed?{suggestion_id:'synthetic-suggestion'}:{})}});}
 if(p.endsWith('/platform-copies'))return route.fulfill({json:{items:[copy()]}});
 if(p==='/api/artifacts'||p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return route.fulfill({json:libraryFixture(route, {items:[{id,source_knowledge_unit_id:'u',kind:'TEXT',status:'AVAILABLE',content:original,storage_uri:null,mime_type:'text/plain',metadata:{title:'مادة اقتراحات'},review_status:'APPROVED',created_at:'2026-11-24',updated_at:'2026-11-24'}],total:1,limit:100,offset:0})});
 if(['/posts','/sources','/api/control/'].some(x=>p.startsWith(x)))return route.fulfill({json:[]});return route.continue();});
 await page.setViewportSize({width:390,height:844});await page.goto('/bank');await page.getByLabel('حالة مراجعة المخرجات').selectOption('APPROVED');await page.getByRole('button',{name:'فتح المادة والتجهيز والتتبع',exact:true}).click();
 const copies=page.getByLabel(`نسخ المنصات ${id}`,{exact:true});await copies.locator('summary').first().click();await copies.getByRole('button',{name:'عرض النسخ المحفوظة',exact:true}).click();
 const panel=copies.getByLabel('اقتراحات النسخة الاختيارية',{exact:true});await panel.locator('summary').click();const check=panel.getByRole('button',{name:'التحقق من إتاحة الاقتراحات دون توليد حي',exact:true});await check.click();await expect(panel.getByRole('status')).toContainText('التوليد الحي غير مفعل');await expect(panel.getByRole('button',{name:'تطبيق الاقتراح على النسخة فقط',exact:true})).toHaveCount(0);await expect(copies.getByLabel(`وصف نسخة ${id}`,{exact:true})).toHaveValue(original);
 proposed=true;await check.click();const apply=panel.getByRole('button',{name:'تطبيق الاقتراح على النسخة فقط',exact:true});await expect(apply).toBeDisabled();await panel.scrollIntoViewIfNeeded();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();await page.screenshot({path:info.outputPath('suggestions-mobile.png')});
 await panel.getByRole('checkbox').check();await apply.click();await expect(copies.getByLabel(`وصف نسخة ${id}`,{exact:true})).toHaveValue('اقتراح اصطناعي للنسخة');expect(calls.filter(x=>x.endsWith('/apply'))).toHaveLength(1);
});
