import {libraryFixture} from './libraryFixture';
import {test,expect} from '@playwright/test';
test('explicit JPEG preview preserves fields and is download only',async({page},info)=>{
 let previews=0,unsafe=0;
 const item={id:'jpeg-source',source_knowledge_unit_id:'u',kind:'IMAGE',status:'AVAILABLE',content:null,storage_uri:'s3://private/original.png',mime_type:'image/png',metadata:{title:'صورة أصلية'},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'};
 const fields={title:'',description:'وصف نسخة محفوظ دون تعديل',tags:[],alt_text:''};
 const copy={platform:'instagram',label:'Instagram',fields,version:2,source_fingerprint:'a'.repeat(64),current_source_fingerprint:'a'.repeat(64),origin:'USER_EDITED',source_stale:false,central_approval:'APPROVED',field_status:'BLOCKED',blockers:['الأصل PNG لم يتغير.'],warnings:[],media_checks_pending:[],execution_blockers:[],sources:[]};
 await page.route('**/*',async route=>{const req=route.request(),p=new URL(req.url()).pathname;
 if(p==='/api/artifacts'||p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return route.fulfill({json:libraryFixture(route, {items:[item],total:1,limit:100,offset:0})});
 if(p==='/api/artifacts/jpeg-source/platform-copies')return route.fulfill({json:{items:[copy]}});
 if(p.endsWith('/jpeg-preview')){previews++;expect(req.postDataJSON()).toEqual({source_fingerprint:'a'.repeat(64),copy_version:2,background:'#ffffff'});return route.fulfill({json:{data_url:'data:image/svg+xml;base64,'+Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="800"><rect width="640" height="800" fill="#e9d5ff"/><circle cx="320" cy="400" r="180" fill="#7c3aed"/></svg>').toString('base64'),measurements:{width:640,height:800,size_bytes:2500},copy_version:2,blockers:[],pending:['لا إذن نشر من التحويل.']}});}
 if(p.startsWith('/api/')&&req.method()!=='GET')unsafe++;
 if(['/posts','/sources','/api/control/'].some(x=>p.startsWith(x)))return route.fulfill({json:[]});return route.continue();});
 await page.goto('/bank?library_view=expanded');await page.getByLabel('حالة مراجعة المخرجات').selectOption('APPROVED');
 const panel=page.getByLabel('نسخ المنصات jpeg-source',{exact:true});await panel.locator('summary').first().click();await panel.getByRole('button',{name:'عرض النسخ المحفوظة',exact:true}).click();await panel.getByLabel('منصة النسخة jpeg-source',{exact:true}).selectOption('instagram');
 await panel.getByText('معاينة JPEG منفصلة دون حفظ أو نشر',{exact:true}).click();
 const button=panel.getByRole('button',{name:'إنشاء معاينة JPEG محلية',exact:true});await expect(button).toBeDisabled();
 await panel.getByLabel('خلفية JPEG jpeg-source',{exact:true}).selectOption('#ffffff');await button.click();
 await expect(panel.getByAltText('معاينة JPEG المشتقة للمراجعة')).toBeVisible();await expect(panel.getByLabel('وصف نسخة jpeg-source',{exact:true})).toHaveValue(fields.description);
 await expect(panel.getByRole('link',{name:'تنزيل نسخة JPEG للمراجعة',exact:true})).toHaveAttribute('download','instagram-jpeg-source.jpg');expect(previews).toBe(1);expect(unsafe).toBe(0);
 await page.addStyleTag({content:'header {visibility:hidden}'});await page.setViewportSize({width:390,height:844});await panel.screenshot({path:info.outputPath('jpeg-preview-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.setViewportSize({width:1280,height:900});await panel.screenshot({path:info.outputPath('jpeg-preview-desktop.png')});
 await panel.getByLabel('وصف نسخة jpeg-source',{exact:true}).fill('غير محفوظ');await expect(panel.getByAltText('معاينة JPEG المشتقة للمراجعة')).toHaveCount(0);
});
