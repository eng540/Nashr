import {test,expect} from '@playwright/test';
for(const width of [390,1280])test(`large saved job shows result summary before provenance at ${width}`,async({page},info)=>{
 let writes=0;
 await page.setViewportSize({width,height:900});
 const materials=Array.from({length:97},(_,i)=>({id:'material-'+i,title:`مادة مصدر موثقة رقم ${i+1}`}));
 await page.route('**/*',route=>{
  const r=route.request(),p=new URL(r.url()).pathname;if(r.method()!=='GET')writes++;
  if(p==='/production-jobs/saved')return route.fulfill({json:{job_id:'saved',status:'COMPLETED',progress_percent:100,total_items:97,completed_items:97,pending_items:0,failed_items:0,attempts:1,resolved_prompt:{available:false},resolved_context:{available:false},request_details:{production_mode:'PRODUCT_WITH_INSTRUCTIONS',product_key:'ARABIC_LITERATURE_BRIEF_TELEGRAM_POST',materials,custom_instructions:'تعليمات محفوظة لا تُحذف',effective_prompt_preview:'سياق التنفيذ المحفوظ لا يُحذف'}}});
  if(p==='/production-jobs/saved/items')return route.fulfill({json:{items:[{item_id:'first',position:1,title:'المخرج الأول',status:'COMPLETED',post_id:'post-one',source_title:'الكتاب',knowledge_unit_id:'material-0'}],total:1}});
  if(p==='/sources'||p.startsWith('/api/control/'))return route.fulfill({json:[]});
  if(p.startsWith('/production-')||p.startsWith('/posts')||p.startsWith('/api/'))return route.fulfill({json:{items:[],total:0}});
  return route.continue();
 });
 await page.goto('/production?job_id=saved');
 const details=page.getByTestId('production-job-details'),request=page.getByTestId('production-request-details'),progress=page.getByRole('progressbar');
 await expect(progress).toHaveAttribute('aria-valuenow','100');
 expect(await progress.evaluate(e=>e.getBoundingClientRect().top)).toBeLessThan(await request.evaluate(e=>e.getBoundingClientRect().top));
 const toggle=request.locator('summary').filter({hasText:'المواد المستخدمة (97)'});
 await expect(toggle).toBeVisible();await expect(request.getByText(materials[96].title,{exact:true})).not.toBeVisible();
 await expect(details.getByRole('link',{name:'فتح المنشور في بنك المحتوى'})).toHaveAttribute('href','/bank?post_id=post-one');
 await details.evaluate(e=>window.scrollTo({top:e.getBoundingClientRect().top+scrollY-96,behavior:'instant'}));await page.screenshot({path:info.outputPath(`job-summary-${width}.png`)});
 await toggle.click();await expect(request.getByRole('listitem')).toHaveCount(97);await expect(request.getByText(materials[96].title,{exact:true})).toBeVisible();
 await expect(request).toContainText('تعليمات محفوظة لا تُحذف');await expect(page.getByTestId('effective-production-prompt')).toContainText('سياق التنفيذ المحفوظ لا يُحذف');
 await toggle.click();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 expect(writes).toBe(0);
});
