import {libraryFixture} from './libraryFixture';
import {test,expect} from '@playwright/test';
test('explicit multiple Telegram channels have separate previews and draft plans',async({page},info)=>{
 const ids=['11111111-1111-4111-8111-111111111111'];const channels=[{id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',label:'تعليم',details:{destination:'-100111'}},{id:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',label:'أخبار',details:{destination:'-100222'}}];let plans=0;
 await page.route('**/*',async route=>{const p=new URL(route.request().url()).pathname;
 if(p==='/api/connections')return route.fulfill({json:{telegram:{items:channels},platforms:[]}});
 if(p==='/api/artifacts/filter-options')return route.fulfill({json:{sources:[],kinds:[]}});
 if(p==='/api/artifacts'||p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return route.fulfill({json:libraryFixture(route, {items:[{id:ids[0],kind:'TEXT',status:'AVAILABLE',review_status:'APPROVED',content:'نص محلي معتمد',metadata:{title:'مادة تجريبية'},source_knowledge_unit_id:'synthetic-unit',storage_uri:null,mime_type:'text/plain',updated_at:'2026-11-24T04:00:00Z',created_at:'2026-11-24T04:00:00Z'}],total:1,limit:100,offset:0})});
 if(p==='/api/connections/telegram/preview'){expect(route.request().postDataJSON().connection_ids).toEqual(channels.map(c=>c.id));return route.fulfill({json:{channels:channels.map(c=>({connection_id:c.id,channel_label:c.label,destination:c.details.destination,ready_count:1,blocked_count:0,caveat:'معاينة دون إرسال',items:[{artifact_id:ids[0],title:'مادة تجريبية',kind:'TEXT',content:'نص محلي معتمد',source_fingerprint:'test-fingerprint',copy_version:null,ready:true,blockers:[],publications:[],schedules:[]}]}))}});}
 if(p==='/api/connections/telegram/plans'){const data=route.request().postDataJSON();expect(data.connection_ids).toEqual(channels.map(c=>c.id));expect(data.previews).toHaveLength(2);plans++;return route.fulfill({json:{plans:[{id:'plan-one',name:'خطة تعليم'},{id:'plan-two',name:'خطة أخبار'}],activated:false,sent_messages:0}});}
 if(p.startsWith('/api/')||p==='/sources'||p==='/schedules'||p.startsWith('/posts')||p.startsWith('/schedules/')){if(route.request().method()!=='GET')throw Error('unexpected write '+p);return route.fulfill({json:p.startsWith('/api/control/')||p.startsWith('/posts')||p==='/sources'?[]:{items:[],total:0}});}
 return route.continue();});
 await page.goto('/bank?library_view=expanded');await page.getByLabel('حالة مراجعة المخرجات').selectOption('APPROVED');
 // The panel uses exactly the approved selection, not every row/channel.
 await expect(page.getByText('مادة تجريبية',{exact:true}).first()).toBeVisible();
 const checkboxes=page.getByRole('checkbox');await checkboxes.first().check();
 const panel=page.getByRole('region',{name:'معاينة دفعة Telegram'});await expect(panel).toBeVisible();await panel.getByLabel('تعليم',{exact:false}).check();await panel.getByLabel('أخبار',{exact:false}).check();
 await panel.getByRole('button',{name:'معاينة وفحص دفعة Telegram (1)'}).click();await expect(panel.getByText('معاينة منفصلة لكل قناة')).toBeVisible();await expect(panel.getByText('تعليم · -100111 · 0 محجوب')).toBeVisible();await expect(panel.getByText('أخبار · -100222 · 0 محجوب')).toBeVisible();expect(plans).toBe(0);
 await panel.getByText('حفظ خطة للدفعة دون تفعيل',{exact:true}).click();await panel.getByLabel('بداية دفعة Telegram').fill('2027-01-15T10:00');await panel.getByRole('checkbox',{name:'راجعت النصوص والوجهة والترتيب. أحفظ خطة مسودة فقط.'}).check();await panel.getByRole('button',{name:'حفظ خطة Telegram كمسودة'}).click();await expect(panel.getByRole('status')).toBeVisible();expect(plans).toBe(1);await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:info.outputPath('multi-channel-preview.png'),fullPage:true});
});
