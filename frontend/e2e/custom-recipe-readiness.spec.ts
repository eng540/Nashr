import {test,expect} from '@playwright/test';

for (const width of [390,1280]) for (const condition of ['missing','incompatible','read-error','refreshing']) {
 test(`custom recipe current readiness ${width} ${condition}`,async({page},info)=>{
  let changed=false;
  const bodies:unknown[]=[];
  let releaseRefresh:(()=>void)|undefined;
  const refreshGate=new Promise<void>(resolve=>{releaseRefresh=resolve;});
  const recipes=()=>[{id:'r',key:'TEXT_RECIPE',name:'مسار نصي',active_version:1,versions:[{version:1,status:'PUBLISHED',stages:[{key:'write',capability_key:changed&&condition==='incompatible'?'render_video':'produce_post'}]}]}];
  await page.route('**/*',async route=>{
   const request=route.request(),path=new URL(request.url()).pathname;
   if(path==='/production-jobs'&&request.method()==='POST'){
    bodies.push(request.postDataJSON());
    return route.fulfill({status:503,json:{detail:'Controlled ambiguous failure'}});
   }
   if(path==='/api/control/recipes'){
    if(changed&&condition==='refreshing')await refreshGate;
    if(changed&&condition==='read-error')return route.fulfill({status:503,json:{detail:'Controlled recipe read failure'}});
    return route.fulfill({json:changed&&condition==='missing'?[]:recipes()});
   }
   if(path.startsWith('/api/control/'))return route.fulfill({json:[]});
   if(path==='/sources')return route.fulfill({json:[]});
   if(path.startsWith('/api/')||path.startsWith('/posts')||path==='/production-jobs')return route.fulfill({json:{items:[],total:0,kinds:[],topics:[],sources:[]}});
   return route.continue();
  });
  await page.setViewportSize({width,height:844});
  await page.goto('/production');
  await page.getByRole('button',{name:'توجيه مخصص — دون منتج'}).click();
  await page.getByLabel('مسار الإنتاج النصي').selectOption('TEXT_RECIPE');
  await page.getByLabel('النص المدخل').fill('نص مباشر محفوظ');
  await page.getByLabel('التوجيه المخصص').fill('أعد صياغة المادة دون تغيير معناها');
  const start=page.getByTestId('start-custom-production');
  await start.click();
  await expect.poll(()=>bodies.length).toBe(1);
  const stored=await page.evaluate(()=>localStorage.getItem('nashr.pending-production-claim.v1'));
  changed=true;
  await page.reload();
  await expect(page.getByTestId('custom-production-form')).toBeVisible();
  if(condition==='refreshing')await expect(page.getByText('جارٍ التحقق من مسارات الإنتاج النصي...',{exact:true})).toBeVisible();
  if(condition==='read-error')await expect(page.getByText(/تعذر قراءة مسارات الإنتاج/)).toBeVisible({timeout:15000});
  if(condition==='missing'||condition==='incompatible')await expect(page.getByText(/المسار المحدد سابقًا غير متاح/)).toBeVisible();
  await expect(start).toBeDisabled();
  expect(bodies.length).toBe(1);
  expect(await page.evaluate(()=>localStorage.getItem('nashr.pending-production-claim.v1'))).toBe(stored);
  await page.getByLabel('مسار الإنتاج النصي').scrollIntoViewIfNeeded();
  await page.screenshot({path:info.outputPath(`recipe-${width}-${condition}.png`)});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  changed=false;
  if(condition==='refreshing')releaseRefresh!();
  else await page.getByRole('button',{name:condition==='read-error'?'إعادة قراءة مسارات الإنتاج':'إعادة فحص المسار المحفوظ',exact:true}).click();
  await expect(start).toBeEnabled();
  expect(await page.evaluate(()=>localStorage.getItem('nashr.pending-production-claim.v1'))).toBe(stored);
  await start.click();
  await expect.poll(()=>bodies.length).toBe(2);
  expect(bodies[1]).toEqual(bodies[0]);
 });
}
