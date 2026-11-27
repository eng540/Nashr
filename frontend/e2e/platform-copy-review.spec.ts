import {libraryFixture} from './libraryFixture';
import {expect,test} from '@playwright/test';
test('media copy saves its own caption and blocks approval while unsaved',async({page},info)=>{
 let item:any={id:'copy',source_knowledge_unit_id:'u',kind:'IMAGE',status:'AVAILABLE',content:null,storage_uri:'s3://test/image.png',mime_type:'image/png',review_status:'DRAFT',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z',metadata:{source_type:'PLATFORM_VARIANT',platform:'x',platform_label_ar:'إكس',caption:'تعليق مستقل',source_artifact_id:'original',needs_review:true,constraints:{max_text:280,measure:'x_weighted',measured_length:12}}};
 let patch:any=null;let approved=0;
 await page.route('**/*',async route=>{let p=new URL(route.request().url()).pathname;
 if(p==='/api/artifacts'||p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return route.fulfill({json:libraryFixture(route, {items:[item],total:1,limit:100,offset:0})});
 if(p==='/api/artifacts/copy'&&route.request().method()==='PATCH'){patch=route.request().postDataJSON();item={...item,metadata:patch.metadata};return route.fulfill({json:item});}
 if(p==='/api/artifacts/copy/approve'){approved++;item={...item,review_status:'APPROVED'};return route.fulfill({json:item});}
 if(p.endsWith('/media-url'))return route.fulfill({json:{url:'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="120" height="80"><rect width="120" height="80" fill="teal"/></svg>',expires_in:300}});
 if(['/posts','/sources','/api/control/'].some(x=>p.startsWith(x)))return route.fulfill({json:[]});return route.continue();});
 await page.goto('/bank?library_view=expanded');await page.getByLabel('تعليق نسخة المنصة copy').fill('نص جديد محفوظ للنسخة');
 await expect(page.getByRole('button',{name:'اعتماد المادة فقط، دون نشر',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'حفظ تعليق النسخة',exact:true}).click();
 await expect.poll(()=>patch?.metadata?.caption).toBe('نص جديد محفوظ للنسخة');
 expect(patch.content).toBeUndefined();expect(patch.metadata.source_artifact_id).toBe('original');
 await expect(page.getByRole('button',{name:'اعتماد المادة فقط، دون نشر',exact:true})).toBeEnabled();
 await page.screenshot({path:info.outputPath('platform-copy-desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:info.outputPath('platform-copy-mobile.png'),fullPage:true});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 expect(approved).toBe(0);
});
