import {libraryFixture} from './libraryFixture';
import {test,expect} from '@playwright/test';
const items=['المراجعة الأولى','دليل صناعة المحتوى','تخطيط أسبوع جديد','الكتابة بوضوح'].map((title,i)=>({id:'design-'+i,kind:'TEXT',status:'AVAILABLE',content:'ابدأ بفكرة واضحة، ثم اختر الصيغة التي تخدمها. المحتوى الجيد يبدأ من فهم الجمهور وينتهي برسالة تستحق المشاركة.\n\nخطوات عملية تساعدك على إنتاج محتوى مؤثر دون أن تفقد صوتك.',storage_uri:null,mime_type:'text/plain',source_knowledge_unit_id:'u',metadata:{title},review_status:'DRAFT',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'}));
test('named library task entries preserve every creation workflow without navigation writes',async({page},info)=>{
 let writes=0;
 await page.route('**/*',async route=>{const r=route.request(),p=new URL(r.url()).pathname;if(p.startsWith('/api/')&&r.method()!=='GET')writes++;if(p==='/api/artifacts'||p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return route.fulfill({json:libraryFixture(route, {items,total:4,limit:100,offset:0})});if(['/posts','/sources','/api/control/'].some(x=>p.startsWith(x)))return route.fulfill({json:[]});return route.continue();});
 await page.goto('/bank');await expect(page.getByRole('navigation',{name:'مهام بنك المحتوى'})).toBeVisible();
 await page.screenshot({path:info.outputPath('bank-desktop.png'),fullPage:false});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:info.outputPath('bank-mobile.png'),fullPage:false});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.getByRole('button',{name:'＋ إنشاء نص أو اختبار',exact:true}).click();await expect(page.getByLabel('نوع المسودة اليدوية',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'＋ رفع وسيط جاهز',exact:true}).click();await expect(page.getByLabel('ملف الوسيط الجاهز',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'＋ اشتقاق نسخة منصة',exact:true}).click();await expect(page.getByLabel('منصة نسخة المنشور',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'＋ إنتاج بطاقة تصميم',exact:true}).click();await expect(page.getByLabel('منتج التصميم من المنشور',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'قائمة التنقل',exact:true}).click();await expect(page.getByRole('navigation',{name:'التنقل الرئيسي للجوال'})).toBeVisible();expect(writes).toBe(0);
});

test('publishing overview and platform settings keep visible task hierarchy',async({page},info)=>{
 await page.route('**/*',async route=>{const p=new URL(route.request().url()).pathname;if(p==='/api/publishing-queue')return route.fulfill({json:{items:[{id:'sample',origin:'ARTIFACT',kind:'VIDEO',title:'فكرة تستحق المشاركة',content_preview:'الأصل محفوظ، ونسخ المنصات مستقلة للمراجعة.',state:'APPROVED',prepared_copies:4,fields_validated:2,selected_platforms:['telegram','instagram'],selection_stale:false}],total:1,caveat:'الاعتماد لا يعني النشر. يُراجع الحساب والوسائط ووقت التنفيذ قبل كل خطة.'}});if(p.startsWith('/posts'))return route.fulfill({json:{items:[],total:0,sources:[],kinds:[]}});if(p==='/api/artifacts'||p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return route.fulfill({json:libraryFixture(route, {items:[],total:0})});if(p.startsWith('/schedules'))return route.fulfill({json:{items:[],total:0}});if(p==='/api/artifacts/platform-variants')return route.fulfill({json:[]});return route.continue();});
 await page.goto('/publishing');await expect(page.getByRole('heading',{name:'فكرة تستحق المشاركة',exact:true})).toBeVisible();await page.screenshot({path:info.outputPath('publishing-desktop.png')});await page.setViewportSize({width:390,height:844});await page.screenshot({path:info.outputPath('publishing-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
