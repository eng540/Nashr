import {test,expect} from '@playwright/test';
test('stored editorial notes are visible without edits or approval',async({page},info)=>{
 const id='00000000-0000-4000-8000-000000000059';const writes:string[]=[];
 const item={id,kind:'VIDEO',review_status:'DRAFT',status:'AVAILABLE',content:null,mime_type:'video/mp4',storage_uri:'s3://private/synthetic.mp4',metadata:{caption:'نسخة قديمة',original_filename:'synthetic.mp4',source_type:'MEDIA_BANK_UPLOAD',video_library:{source_original:'/downloads/private.mp4 Charon producer main pipeline',editorial_notes:['/downloads/private.mp4 Charon producer main pipeline'],review_notes:['Civil review required before public use.','Approximate subtitles. Transcript checked, not heard by ear.','مصدر مساحة عام: https://ce.cet.ac.in/downloads/Study%20Material/Surveying/Settingout.pdf']}},created_at:'2026-11-25T00:00:00Z',updated_at:'2026-11-25T00:00:00Z'};
 await page.route('**/api/**',async route=>{
 const r=route.request(),p=new URL(r.url()).pathname;if(!p.startsWith('/api/'))return route.continue();
 if(r.method()!=='GET')throw Error('Unexpected mutation '+p);
 if(p==='/api/artifacts')return route.fulfill({json:{items:[item],total:1,limit:100,offset:0}});
 if(p==='/api/artifacts/'+id+'/media-url')return route.fulfill({status:404,json:{detail:'synthetic no media'}});
 if(p.endsWith('/publications'))return route.fulfill({json:{items:[],total:0}});
 if(p.endsWith('/readiness'))return route.fulfill({json:{targets:[],central_approval:'DRAFT'}});
 if(p.includes('organization'))return route.fulfill({json:{categories:[],series:[],items:[]}});
 if(p.includes('/control/'))return route.fulfill({json:[]});
 return route.fulfill({json:{items:[],sources:[],topics:[],kinds:[]}});
 });
 await page.goto('/bank');await page.getByRole('button',{name:'فتح المادة والتجهيز والتتبع',exact:true}).click();
 const panel=page.getByRole('region',{name:'ملاحظات الأصل قبل المراجعة'});
 await expect(panel).toBeVisible();await expect(panel).toContainText('ملاحظات المراجعة والمصادر · 3');
 await panel.getByText('قراءة ملاحظات المراجعة والمصادر (3)',{exact:true}).click();
 await expect(panel.getByText('Civil review required before public use.',{exact:true})).toBeVisible();
 await expect(panel.getByText('Approximate subtitles. Transcript checked, not heard by ear.',{exact:true})).toBeVisible();
 await expect(page.getByText('/downloads/private.mp4 Charon producer main pipeline',{exact:true})).toHaveCount(0);await expect(page.getByText('تفاصيل تقنية',{exact:true})).toHaveCount(0);expect(writes).toEqual([]);expect(item.review_status).toBe('DRAFT');
 await expect(panel.getByRole('link',{name:'https://ce.cet.ac.in/downloads/Study%20Material/Surveying/Settingout.pdf'})).toBeVisible();
 await panel.screenshot({path:info.outputPath('editorial-notes-desktop.png')});
 await page.setViewportSize({width:390,height:844});await panel.scrollIntoViewIfNeeded();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await panel.screenshot({path:info.outputPath('editorial-notes-mobile.png')});
});
