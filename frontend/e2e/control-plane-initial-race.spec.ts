import {test,expect} from '@playwright/test';

for (const staleFails of [false,true]) {
 test(`stale initial read ${staleFails?'failure':'success'} cannot erase new product fields`,async({page})=>{
  const counts:Record<string,number>={};
  let release!:()=>void;
  const gate=new Promise<void>(resolve=>{release=resolve;});
  let delayed=0;
  await page.route('**/api/control/**',async route=>{
   const p=new URL(route.request().url()).pathname;
   counts[p]=(counts[p]||0)+1;
   if(counts[p]===1){
    delayed++;
    await gate;
    return route.fulfill(staleFails?{status:503,json:{detail:'stale request failed'}}:{json:[]});
   }
   return route.fulfill({json:[]});
  });
  await page.goto('/control');
  await page.getByRole('button',{name:'جديد',exact:true}).click();
  expect(delayed).toBe(6);
  await page.getByLabel('المفتاح',{exact:true}).fill('NEW_PRODUCT');
  await page.getByLabel('الاسم',{exact:true}).fill('New product');
  const staleDone=page.waitForResponse(r=>r.url().endsWith('/api/control/prompts'));
  release();
  await staleDone;
  await expect(page.getByLabel('المفتاح',{exact:true})).toHaveValue('NEW_PRODUCT');
  await expect(page.getByLabel('الاسم',{exact:true})).toHaveValue('New product');
  await expect(page.getByText('stale request failed',{exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'جديد',exact:true})).toBeEnabled();
  if (!staleFails) await page.screenshot({path:'/downloads/control-plane-read-fixed.png',fullPage:true});
 });
}
