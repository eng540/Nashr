import {libraryFixture} from './libraryFixture';
import {test,expect} from '@playwright/test';
test('multiline draft media captions preserve paragraphs without approval',async({page},info)=>{
 const id='00000000-0000-4000-8000-000000000059',caption='الفقرة الأولى\n\nالفقرة الثانية\nسطر أخير';const writes:string[]=[];
 let item={id,kind:'VIDEO',review_status:'DRAFT',status:'AVAILABLE',content:null,mime_type:'video/mp4',storage_uri:'s3://private/synthetic.mp4',metadata:{caption:'نسخة قديمة',original_filename:'synthetic.mp4',source_type:'MEDIA_BANK_UPLOAD',editorial_notes:['private review only']},created_at:'2026-11-25T00:00:00Z',updated_at:'2026-11-25T00:00:00Z'};
 await page.route('**/api/**',async route=>{
 const r=route.request(),p=new URL(r.url()).pathname;if(!p.startsWith('/api/'))return route.continue();
 if(p==='/api/artifacts/'+id&&r.method()==='PATCH'){const b=r.postDataJSON();expect(b.metadata.caption).toBe(caption);expect(b.metadata.editorial_notes).toEqual(['private review only']);item={...item,metadata:b.metadata};writes.push(p);return route.fulfill({json:item});}
 if(r.method()!=='GET')throw Error('Unexpected mutation '+p);
 if(p==='/api/artifacts'||p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return route.fulfill({json:libraryFixture(route, {items:[item],total:1,limit:100,offset:0})});
 if(p==='/api/artifacts/'+id+'/media-url')return route.fulfill({status:404,json:{detail:'synthetic no media'}});
 if(p.endsWith('/publications'))return route.fulfill({json:{items:[],total:0}});
 if(p.endsWith('/readiness'))return route.fulfill({json:{targets:[],central_approval:'DRAFT'}});
 if(p.includes('organization'))return route.fulfill({json:{categories:[],series:[],items:[]}});
 if(p.includes('/control/'))return route.fulfill({json:[]});
 return route.fulfill({json:{items:[],sources:[],topics:[],kinds:[]}});
 });
 await page.route('**/sources',r=>r.fulfill({json:[]}));
 await page.goto('/bank');await page.getByRole('button',{name:'فتح المادة والتجهيز والتتبع',exact:true}).click();
 await page.getByLabel('تعليق الوسيط '+id,{exact:true}).fill(caption);await expect(page.getByRole('button',{name:'اعتماد المادة فقط، دون نشر',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'حفظ التعديل',exact:true}).click();await expect.poll(()=>writes.length).toBe(1);await expect(page.getByLabel('تعليق الوسيط '+id,{exact:true})).toHaveValue(caption);
 expect(item.review_status).toBe('DRAFT');await page.getByRole('button',{name:'＋ رفع وسيط جاهز',exact:true}).click();const upload=page.getByLabel('تعليق الوسيط الجاهز',{exact:true});await upload.fill(caption);await expect(upload).toHaveValue(caption);expect(await upload.evaluate(x=>x.tagName)).toBe('TEXTAREA');
 await page.setViewportSize({width:390,height:844});await upload.screenshot({path:info.outputPath('multiline-upload.png')});
});
