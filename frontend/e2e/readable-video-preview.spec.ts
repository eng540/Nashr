import {libraryFixture} from './libraryFixture';
import {test,expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {mkdtempSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
for(const shape of ['portrait','landscape'])test(`original ${shape} video uses readable responsive inline preview without writes`,async({page},info)=>{
 const dir=mkdtempSync(join(tmpdir(),'video-review-')),path=join(dir,'preview.mp4');
 try{
 execFileSync('ffmpeg',['-loglevel','error','-f','lavfi','-i',`testsrc2=size=${shape==='portrait'?'540x960':'960x540'}:rate=1`,'-t','1','-pix_fmt','yuv420p',path]);
 const bytes=readFileSync(path),id='preview-'+shape;
 const item={id,kind:'VIDEO',review_status:'DRAFT',status:'AVAILABLE',content:null,mime_type:'video/mp4',storage_uri:'s3://private/review.mp4',metadata:{caption:'نسخة خاصة للمراجعة فقط',title:'مراجعة فيديو',source_type:'MEDIA_BANK_UPLOAD'},created_at:'2026-11-25T00:00:00Z',updated_at:'2026-11-25T00:00:00Z'};
 let writes=0;
 await page.route('**/*',async route=>{
 const r=route.request(),p=new URL(r.url()).pathname;
 if(p==='/synthetic-preview.mp4')return route.fulfill({body:bytes,contentType:'video/mp4'});
 if(p.startsWith('/api/')&&r.method()!=='GET'){writes++;throw Error('Unexpected write');}
 if(p==='/api/artifacts'||p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return route.fulfill({json:libraryFixture(route, {items:[item],total:1})});
 if(p.endsWith('/media-url'))return route.fulfill({json:{url:'http://127.0.0.1:5173/synthetic-preview.mp4'}});
 if(p==='/sources')return route.fulfill({json:[]});
 if(p.includes('/control/'))return route.fulfill({json:[]});
 if(p.startsWith('/api/')||['/posts','/sources'].some(v=>p.startsWith(v)))return route.fulfill({json:{items:[],total:0}});
 return route.continue();
 });
 await page.goto('/bank');await page.getByRole('button',{name:'فتح المادة والتجهيز والتتبع',exact:true}).click();
 const video=page.getByLabel('معاينة الفيديو الأصلي',{exact:true});
 await expect.poll(()=>video.evaluate((v:HTMLVideoElement)=>v.readyState)).toBeGreaterThan(0);
 await expect(video).toHaveAttribute('playsinline','');expect(await video.evaluate((v:HTMLVideoElement)=>v.autoplay)).toBeFalsy();
 for(const width of [1280,390]){
 await page.setViewportSize({width,height:844});await video.scrollIntoViewIfNeeded();
 const b=(await video.boundingBox())!;
 expect(b.height).toBeGreaterThan(shape==='portrait'?500:140);expect(b.height).toBeLessThanOrEqual(844*.8+1);expect(b.width).toBeLessThan(width);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await video.screenshot({path:info.outputPath(`${shape}-${width}.png`)});
 }
 expect(writes).toBe(0);expect(item.review_status).toBe('DRAFT');
 }finally{rmSync(dir,{recursive:true,force:true});}
});
