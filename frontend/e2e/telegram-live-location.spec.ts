import {expect,test} from '@playwright/test';

test('live location update and stop require a separate reviewed operation',async({page},testInfo)=>{
 let operations:any[]=[];let executed=0;let active=true;
 const item={id:'live',kind:'TEXT',status:'AVAILABLE',content:'Synthetic live point',storage_uri:null,mime_type:'text/plain',metadata:{title:'موقع حي اصطناعي',telegram_native:{type:'LIVE_LOCATION',latitude:0,longitude:0,live_period:60}},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'};
 await page.route('**/*',async route=>{
  const u=new URL(route.request().url());
  if(u.pathname==='/api/artifacts')return route.fulfill({json:[item]});
  if(u.pathname==='/api/artifacts/live/live-locations')return route.fulfill({json:[{publication_id:'pub',message_id:'123',destination:'private-fixture',expires_at:'2026-11-23T11:00:00Z',active,operations}]});
  if(u.pathname==='/api/artifacts/live-locations/pub/operations'){
   const body=route.request().postDataJSON();operations=[{id:'op'+operations.length,publication_id:'pub',action:body.action,payload:body.action==='STOP'?{}:{latitude:body.latitude,longitude:body.longitude},status:'DRAFT',error_message:null}];return route.fulfill({status:201,json:operations[0]});
  }
  if(u.pathname.endsWith('/execute')){executed++;operations[0].status='COMPLETED';if(operations[0].action==='STOP')active=false;return route.fulfill({json:operations[0]});}
  if(['/posts','/sources','/api/control/'].some(p=>u.pathname.startsWith(p)))return route.fulfill({json:[]});
  return route.continue();
 });
 await page.goto('/bank?library_view=expanded');await page.getByLabel('حالة مراجعة المخرجات').selectOption('APPROVED');
 await page.getByLabel('خط عرض التحديث').fill('0.001');await page.getByLabel('خط طول التحديث').fill('0.002');
 await page.getByRole('button',{name:'تجهيز تحديث الموقع للمراجعة',exact:true}).click();
 await expect(page.getByText('UPDATE · DRAFT',{exact:true})).toBeVisible();expect(executed).toBe(0);
 await page.getByRole('button',{name:'اعتماد وتنفيذ تحديث الموقع',exact:true}).click();
 await expect(page.getByText('UPDATE · COMPLETED',{exact:true})).toBeVisible();expect(executed).toBe(1);
 await page.getByRole('button',{name:'تجهيز إيقاف الموقع للمراجعة',exact:true}).click();
 await expect(page.getByText('STOP · DRAFT',{exact:true})).toBeVisible();expect(executed).toBe(1);
 await page.screenshot({path:testInfo.outputPath('live-location-review-desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await page.getByRole('button',{name:'اعتماد وتنفيذ إيقاف الموقع',exact:true}).scrollIntoViewIfNeeded();
 await page.screenshot({path:testInfo.outputPath('live-location-review-mobile.png')});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.getByRole('button',{name:'اعتماد وتنفيذ إيقاف الموقع',exact:true}).click();
 await expect(page.getByText('STOP · COMPLETED',{exact:true})).toBeVisible();expect(executed).toBe(2);
});

test('completed location operation details wrap on mobile and remain collapsed by default',async({page},info)=>{
 const id='location-wrap';const item={id,kind:'TEXT',status:'AVAILABLE',content:'موقع اصطناعي',storage_uri:null,mime_type:'text/plain',metadata:{title:'موقع اختبار',telegram_native:{type:'LIVE_LOCATION',latitude:0,longitude:0,live_period:300}},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'};
 await page.route('**/*',async route=>{const p=new URL(route.request().url()).pathname;if(p==='/api/artifacts')return route.fulfill({json:[item]});if(p==='/api/artifacts/location-wrap/live-locations')return route.fulfill({json:[{publication_id:'pub',message_id:'2556',active:false,expires_at:'2026-11-23T20:33:11Z',operations:[{id:'op',action:'UPDATE',status:'COMPLETED',payload:{latitude:0.001,longitude:0.002},error_message:null}]}]});if(['/posts','/sources','/api/control/'].some(x=>p.startsWith(x)))return route.fulfill({json:[]});return route.continue();});
 await page.setViewportSize({width:390,height:844});await page.goto('/bank?artifact_status=APPROVED&artifact_id=location-wrap');const summary=page.getByText('تفاصيل العملية التقنية',{exact:true});await expect(summary).toBeVisible();const details=summary.locator('..');await expect(details).not.toHaveAttribute('open','');await summary.click();const pre=details.locator('pre');await expect(pre).toBeVisible();expect(await pre.evaluate(e=>e.scrollWidth<=e.clientWidth)).toBeTruthy();await page.locator('article').screenshot({path:info.outputPath('location-wrap-mobile.png')});
});
