import {libraryFixture} from './libraryFixture';
import {test,expect} from '@playwright/test';
test('changed draft fields require fresh review and pending save locks exact intent',async({page},info)=>{
 let saved=0,unsafe=0,release!:()=>void;const gate=new Promise<void>(r=>{release=r});
 const item={id:'batch-ready',source_knowledge_unit_id:'u',kind:'TEXT',status:'AVAILABLE',content:'نص معتمد لا يتغير',storage_uri:null,mime_type:'text/plain',metadata:{title:'مادة مؤهلة'},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'};
 await page.route('**/*',async route=>{const req=route.request(),p=new URL(req.url()).pathname;
 if(p==='/api/artifacts/telegram-batch-preview')return route.fulfill({json:{destination:'synthetic-target',ready_count:1,blocked_count:0,caveat:'فحص أولي.',items:[{artifact_id:item.id,title:'مادة مؤهلة',kind:'TEXT',content:item.content,source_fingerprint:'reviewed-fingerprint',ready:true,blockers:[],publications:[],schedules:[]}]}});
 if(p==='/api/artifacts/telegram-batch-schedule'){saved++;expect(req.postDataJSON()).toMatchObject({artifact_ids:[item.id],destination:'synthetic-target',fingerprints:{'batch-ready':'reviewed-fingerprint'},timezone:'Asia/Riyadh',start_at:'2030-01-01T09:00:00.000Z',interval_minutes:60});await gate;return route.fulfill({status:201,json:{id:'synthetic-draft-plan',status:'DRAFT',items:[]}});}
 if(p.startsWith('/api/')&&req.method()!=='GET')unsafe++;
 if(p==='/api/artifacts'||p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return route.fulfill({json:libraryFixture(route, {items:[item],total:1,limit:100,offset:0})});
 if(['/posts','/sources','/api/control/'].some(x=>p.startsWith(x)))return route.fulfill({json:[]});return route.continue();});
 await page.goto('/bank?library_view=expanded');await page.getByLabel('حالة مراجعة المخرجات').selectOption('APPROVED');await page.getByLabel('تحديد كل وسائط الصفحة',{exact:true}).check();
 const panel=page.getByLabel('معاينة دفعة Telegram',{exact:true});await panel.getByRole('button',{name:'معاينة وفحص دفعة Telegram (1)',exact:true}).click();
 await panel.getByText('حفظ خطة للدفعة دون تفعيل',{exact:true}).click();await page.getByLabel('بداية دفعة Telegram',{exact:true}).fill('2030-01-01T12:00');
 const save=panel.getByRole('button',{name:'حفظ خطة Telegram كمسودة',exact:true});await expect(save).toBeDisabled();await panel.getByRole('checkbox').check();await expect(save).toBeEnabled();
 const confirm=panel.getByRole('checkbox');for(const [label,value] of [['اسم خطة الدفعة','خطة مراجعة'],['بداية دفعة Telegram','2030-01-01T12:30'],['فاصل دفعة Telegram','90']]){await panel.getByLabel(label,{exact:true}).fill(value);await expect(confirm).not.toBeChecked();await expect(save).toBeDisabled();await confirm.check();}
 await panel.getByLabel('بداية دفعة Telegram',{exact:true}).fill('2030-01-01T12:00');await panel.getByLabel('فاصل دفعة Telegram',{exact:true}).fill('0');await confirm.check();await expect(save).toBeDisabled();await panel.getByLabel('فاصل دفعة Telegram',{exact:true}).fill('60');await expect(confirm).not.toBeChecked();await confirm.check();
 await page.setViewportSize({width:390,height:844});await panel.screenshot({path:info.outputPath('batch-schedule-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await save.click();await expect.poll(()=>saved).toBe(1);for(const label of ['اسم خطة الدفعة','بداية دفعة Telegram','فاصل دفعة Telegram'])await expect(panel.getByLabel(label,{exact:true})).toBeDisabled();await expect(confirm).toBeDisabled();await expect(panel.getByRole('button',{name:'معاينة وفحص دفعة Telegram (1)',exact:true})).toBeDisabled();await panel.screenshot({path:info.outputPath('draft-intent-pending-mobile.png')});release();await expect(panel.getByRole('status')).toContainText('دون تفعيل');expect(saved).toBe(1);expect(unsafe).toBe(0);
});
