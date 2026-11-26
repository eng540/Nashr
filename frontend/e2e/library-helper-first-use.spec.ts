import {test,expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
const templates=JSON.parse(execFileSync('python3',['-c',`import ast,json
p=ast.parse(open('../app/api/library_import.py').read())
r={}
for n in p.body:
 if isinstance(n,ast.AsyncFunctionDef) and n.name in ('library_import_page','video_metadata_page'):
  r[n.name]=ast.literal_eval(n.body[0].value.args[0])
print(json.dumps(r))`],{encoding:'utf8'}));
for(const width of [320,390,1280])for(const metadata of [false,true])test(`actual ${metadata?'metadata':'ZIP'} helper retries safely and fits ${width}px`,async({page},info)=>{
 const path=metadata?'/library/video-metadata':'/library/import';let posts=0;
 await page.route('**/*',route=>{if(route.request().method()==='POST'){posts++;expect(route.request().url()).toContain(metadata?'/api/library/video-metadata':'/api/library/import');return route.fulfill(posts===1?{status:metadata?422:409,json:{detail:'تعذر اختباري مؤقت'}}:{status:201,json:metadata?{updated:['new'],skipped:['old']}:{collections:{topics:{imported:['new'],skipped:['old'],failed:[]}},review_status:'DRAFT',published:false}});}return route.fulfill({contentType:'text/html',body:templates[metadata?'video_metadata_page':'library_import_page']});});
 await page.setViewportSize({width,height:844});await page.goto(path);
 await expect(page.getByRole('navigation',{name:'تنقل أدوات المكتبة'}).getByRole('link',{name:'المصادر والمكتبة'})).toHaveAttribute('href','/sources/library');
 const input=page.getByLabel(metadata?'ملف البيانات':'حزم المكتبة',{exact:true});const button=page.getByRole('button',{name:metadata?'استعادة البيانات':'بدء الاستيراد',exact:true});
 await button.click();await expect(page.getByRole('status')).toContainText(metadata?'اختر ملفاً':'اختر حزمة');expect(posts).toBe(0);
 await input.setInputFiles({name:metadata?'video.json':'bundle.zip',mimeType:metadata?'application/json':'application/zip',buffer:Buffer.from(metadata?'[]':'synthetic')});await button.click();await expect(page.getByRole('status')).toContainText('توقف:');await expect(button).toBeEnabled();await expect(input).not.toHaveValue('');await button.click();await expect(page.getByRole('status')).toContainText(metadata?'لم يتم نشر شيء':'جميع المواد مسودات');expect(posts).toBe(2);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();await page.screenshot({path:info.outputPath(`helper-${metadata?'metadata':'zip'}-${width}.png`),fullPage:true});
});
for(const width of [320,390,1280])test(`source tools are explicit, collapsed and read-only at ${width}px`,async({page},info)=>{
 let writes=0;await page.route('**/*',route=>{const p=new URL(route.request().url()).pathname;if(route.request().method()!=='GET')writes++;if(p==='/sources'||p.startsWith('/api/'))return route.fulfill({json:[]});return route.continue();});await page.setViewportSize({width,height:844});await page.goto('/sources/library');const tools=page.getByLabel('أدوات المكتبة المتقدمة',{exact:true});await expect(tools).not.toHaveAttribute('open','');await tools.locator('summary').click();await expect(tools.getByRole('link',{name:'استيراد حزم المكتبة ZIP',exact:false})).toHaveAttribute('href','/library/import');await expect(tools.getByRole('link',{name:'استعادة بيانات الفيديوهات JSON',exact:false})).toHaveAttribute('href','/library/video-metadata');await expect(tools).toContainText('لا يرفع أو يغيّر شيئاً');expect(writes).toBe(0);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();await tools.scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath(`source-tools-${width}.png`)});
});
