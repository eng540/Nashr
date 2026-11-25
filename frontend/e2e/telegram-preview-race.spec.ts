import {test,expect} from '@playwright/test';

test('late Telegram preview never becomes review or scheduling authority for a different selection',async({page},info)=>{
 let release!:()=>void,requested=false;const writes:string[]=[];const gate=new Promise<void>(resolve=>{release=resolve;});
 const items=['one','two'].map(id=>({id,kind:'TEXT',status:'AVAILABLE',content:'أصل '+id,storage_uri:null,mime_type:'text/plain',metadata:{title:'مادة '+id},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'}));
 await page.route('**/*',async route=>{const r=route.request(),p=new URL(r.url()).pathname;
  if(p==='/api/artifacts/telegram-batch-preview'){const id=r.postDataJSON().artifact_ids[0];if(id==='one'){requested=true;await gate;}return route.fulfill({json:{destination:'synthetic-target-'+id,ready_count:1,blocked_count:0,caveat:'فحص أولي',items:[{artifact_id:id,title:'مادة '+id,kind:'TEXT',content:'أصل '+id,source_fingerprint:'pin-'+id,ready:true,blockers:[],publications:[],schedules:[]}]}});}
  if(r.method()!=='GET')writes.push(p);
  if(p==='/api/artifacts')return route.fulfill({json:{items,total:2,limit:100,offset:0}});
  if(p.startsWith('/api/'))return route.fulfill({json:p.includes('/control/')?[]:{items:[],total:0,telegram:{items:[]}}});
  if(['/posts','/sources'].some(x=>p.startsWith(x)))return route.fulfill({json:[]});return route.continue();});
 await page.goto('/bank?artifact_status=APPROVED');await page.getByLabel('تحديد المخرج one',{exact:true}).check();const panel=page.getByLabel('معاينة دفعة Telegram',{exact:true});
 await panel.getByRole('button',{name:'معاينة وفحص دفعة Telegram (1)',exact:true}).click();await expect.poll(()=>requested).toBe(true);
 await page.getByLabel('تحديد المخرج two',{exact:true}).check();await page.getByLabel('تحديد المخرج one',{exact:true}).uncheck();release();
 await expect(panel.getByRole('button',{name:'معاينة وفحص دفعة Telegram (1)',exact:true})).toBeEnabled();
 await expect(panel.getByText('synthetic-target-one',{exact:true})).toHaveCount(0);await expect(panel.getByText('حفظ خطة للدفعة دون تفعيل',{exact:true})).toHaveCount(0);
 await panel.getByRole('button',{name:'معاينة وفحص دفعة Telegram (1)',exact:true}).click();await expect(panel.getByText('synthetic-target-two',{exact:true})).toBeVisible();
 await page.getByLabel('تحديد المخرج one',{exact:true}).check();await page.getByLabel('تحديد المخرج two',{exact:true}).uncheck();await page.getByLabel('تحديد المخرج two',{exact:true}).check();await page.getByLabel('تحديد المخرج one',{exact:true}).uncheck();
 await expect(panel.getByText('synthetic-target-two',{exact:true})).toHaveCount(0);await expect(panel.getByText('حفظ خطة للدفعة دون تفعيل',{exact:true})).toHaveCount(0);await panel.getByRole('button',{name:'معاينة وفحص دفعة Telegram (1)',exact:true}).click();await expect(panel.getByText('synthetic-target-two',{exact:true})).toBeVisible();
 await page.setViewportSize({width:390,height:844});await panel.scrollIntoViewIfNeeded();await panel.screenshot({path:info.outputPath('current-telegram-preview-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();expect(writes).toEqual([]);
});

test('late channel preview and mismatched channel responses never expose a draft plan form',async({page})=>{
 let release!:()=>void,requested=false,mismatch=false;const gate=new Promise<void>(resolve=>{release=resolve;});
 const channels=[{id:'channel-a',label:'تعليم',details:{destination:'-100111'}},{id:'channel-b',label:'أخبار',details:{destination:'-100222'}}];
 await page.route('**/*',async route=>{const r=route.request(),p=new URL(r.url()).pathname;
  if(p==='/api/connections')return route.fulfill({json:{telegram:{items:channels}}});
  if(p==='/api/artifacts')return route.fulfill({json:{items:[{id:'one',kind:'TEXT',status:'AVAILABLE',review_status:'APPROVED',content:'أصل',metadata:{title:'مادة'},storage_uri:null,mime_type:'text/plain',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'}],total:1,limit:100,offset:0}});
  if(p==='/api/connections/telegram/preview'){const id=r.postDataJSON().connection_ids[0];if(id==='channel-a'){requested=true;await gate;}return route.fulfill({json:{channels:[{connection_id:mismatch?'channel-a':id,destination:'synthetic-'+id,ready_count:1,blocked_count:0,caveat:'معاينة',items:[{artifact_id:'one',kind:'TEXT',title:'مادة',content:'أصل',ready:true,blockers:[],publications:[],schedules:[]}]}]}});}
  if(p.startsWith('/api/')){expect(r.method()).toBe('GET');return route.fulfill({json:p.includes('/control/')?[]:{items:[],total:0}});}
  if(['/posts','/sources'].some(x=>p.startsWith(x)))return route.fulfill({json:[]});return route.continue();});
 await page.goto('/bank?artifact_status=APPROVED');await page.getByLabel('تحديد المخرج one',{exact:true}).check();const panel=page.getByLabel('معاينة دفعة Telegram',{exact:true});await panel.getByLabel('تعليم',{exact:false}).check();await panel.getByRole('button',{name:'معاينة وفحص دفعة Telegram (1)',exact:true}).click();await expect.poll(()=>requested).toBe(true);
 await panel.getByLabel('تعليم',{exact:false}).uncheck();await panel.getByLabel('أخبار',{exact:false}).check();release();await expect(panel.getByRole('button',{name:'معاينة وفحص دفعة Telegram (1)',exact:true})).toBeEnabled();await expect(panel.getByText('synthetic-channel-a',{exact:true})).toHaveCount(0);await expect(panel.getByText('حفظ خطة للدفعة دون تفعيل',{exact:true})).toHaveCount(0);
 mismatch=true;await panel.getByRole('button',{name:'معاينة وفحص دفعة Telegram (1)',exact:true}).click();await expect(panel.getByRole('alert')).toContainText('تغير نطاق المعاينة');await expect(panel.getByText('حفظ خطة للدفعة دون تفعيل',{exact:true})).toHaveCount(0);
});
