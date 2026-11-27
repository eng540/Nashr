import {test,expect} from '@playwright/test';
for (const width of [390,1280]) test(`cross-page source handoff starts at setup, same-page focus survives at ${width}`,async({page},info)=>{
 let writes=0;
 await page.setViewportSize({width,height:844});
 await page.route('**/*',route=>{
  const r=route.request(),p=new URL(r.url()).pathname;
  if(r.method()!=='GET')writes++;
  if(p==='/sources')return route.fulfill({json:[{id:'book',filename:'book.pdf',book_title:'كتاب هندسي محفوظ',mime_type:'application/pdf',status:'READY',material_count:1,produced_count:0,pending_count:1}]});
  if(p==='/sources/book-analysis')return route.fulfill({contentType:'text/html',body:'<main dir="rtl" style="height:4000px"><h1>مواد الكتاب</h1></main>'});
  if(p.startsWith('/api/control/')||p.startsWith('/posts')||p==='/production-jobs')return route.fulfill({json:[]});
  if(p.startsWith('/api/')||p.startsWith('/production-')||p.includes('/book-map'))return route.fulfill({json:{items:[],total:0,topics:[],materials:[],count:0}});
  return route.continue();
 });
 await page.goto('/sources/library');
 await page.getByRole('button',{name:'فتح تحليل هذا الكتاب',exact:true}).click();
 const analysis=page.getByRole('heading',{name:'تحليل الكتاب واستخراج المواد',exact:true});
 await expect(analysis).toBeFocused();await expect(analysis).toBeInViewport();
 await expect.poll(()=>page.locator('iframe').evaluate(e=>e.clientHeight)).toBeGreaterThan(3900);
 await page.getByTestId('source-card-book').getByRole('link',{name:'الإنتاج من هذا المصدر',exact:true}).click();
 await expect(page).toHaveURL(/\/production\?source_id=book/);
 await expect.poll(()=>page.evaluate(()=>scrollY)).toBe(0);
 await expect(page.locator('#main-content')).toBeFocused();
 await expect(page.getByRole('heading',{name:'الإنتاج من المصادر',exact:true})).toBeInViewport();
 await page.screenshot({path:info.outputPath(`route-entry-${width}.png`)});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 expect(writes).toBe(0);
});
