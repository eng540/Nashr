import {test,expect} from '@playwright/test';
const ids=['12345678-1234-4123-8123-123456789ab1','12345678-1234-4123-8123-123456789ab2'];
test('review the saved selected Meta batch together without preparing or scheduling anything',async({page})=>{
 const writes:string[]=[];
 const items=ids.map((id,i)=>({id,kind:'VIDEO',status:'AVAILABLE',content:'أصل '+i,mime_type:'video/mp4',metadata:{title:'فيديو '+(i+1)},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'}));
 await page.route('**/*',r=>{const p=new URL(r.request().url()).pathname;
 if(r.request().method()!=='GET')writes.push(p);
 if(p==='/api/artifacts')return r.fulfill({json:{items,total:2,limit:100,offset:0}});
 if(p.endsWith('/distribution-readiness')){const id=p.split('/')[3];return r.fulfill({json:{artifact_id:id,source_fingerprint:'fp-'+id,selection_version:'sel-'+id,central_approval:'APPROVED',original_text:'أصل كامل '+id,selection_stale:false,targets:['instagram','facebook'].map(platform=>({platform,label:platform,selected:id===ids[0]?platform==='instagram':platform==='facebook',copy_status:'FIELDS_VALIDATED',copy_blockers:[],execution_blockers:['فحص الحساب والتنفيذ منفصل']}))}});}
 if(p.endsWith('/platform-copies'))return r.fulfill({json:{items:[{platform:p.includes(ids[0])?'instagram':'facebook',version:4,source_stale:false,field_status:'FIELDS_VALIDATED',fields:{description:'نص محفوظ كامل دون قص'}}]}});
 if(p==='/api/connections')return r.fulfill({json:{telegram:{items:[]}}});
 if(p==='/posts'||p.startsWith('/posts/')||p==='/sources'||p.startsWith('/api/control/'))return r.fulfill({json:[]});
 if(p.startsWith('/api/'))return r.fulfill({json:{items:[],total:0}});return r.continue();});
 await page.goto('/bank?artifact_status=APPROVED');await page.getByRole('button',{name:'تحديد النتائج المؤهلة (حتى 100)',exact:true}).click();
 const panel=page.getByLabel('مراجعة دفعة Meta',{exact:true});
 await panel.getByRole('button',{name:'مراجعة وجهات Meta المحفوظة للمحدد (2)',exact:true}).click();
 await expect(panel.getByRole('article')).toHaveCount(2);
 await expect(panel.getByRole('article').first()).toContainText('Instagram');
 await expect(panel.getByRole('article').first()).not.toContainText('Facebook Reel');
 await expect(panel.getByRole('article').last()).toContainText('Facebook Reel');
 await expect(panel).toContainText('لا خطة محفوظة ولا إذن تنفيذ');
 await expect(panel.getByText('حقول النسخة المحفوظة مقبولة مبدئياً · إصدار 4',{exact:true})).toHaveCount(2);
 await panel.getByText('النص المحفوظ لهذه المنصة دون قص',{exact:true}).first().click();
 await expect(panel.getByText('نص محفوظ كامل دون قص',{exact:true}).first()).toBeVisible();
 await panel.getByText('اقتراح مواعيد محلي دون حفظ',{exact:true}).click();
 await panel.getByLabel('بداية مراجعة دفعة Meta').fill('2030-01-01T14:00');
 await panel.getByLabel('منطقة مراجعة دفعة Meta').fill('Asia/Riyadh');
 await panel.getByLabel('فاصل مراجعة دفعة Meta').fill('30');
 await expect(panel.getByRole('article').first()).toContainText('2030-01-01T11:00:00.000Z');
 await expect(panel.getByRole('article').last()).toContainText('2030-01-01T11:30:00.000Z');
 await page.setViewportSize({width:390,height:844});
 await page.addStyleTag({content:'header{visibility:hidden}'});
 await panel.screenshot({path:'test-results/meta-batch-review-mobile.png'});
 await page.setViewportSize({width:1280,height:960});await panel.screenshot({path:'test-results/meta-batch-review-desktop.png'});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 expect(writes).toEqual([]);
});

for(const mode of ['missing','mismatch','failure','stale','incomplete'] as const)test(`Meta batch review handles ${mode} without silently replacing a material or destination`,async({page})=>{
 const writes:string[]=[];
 const items=ids.map((id,i)=>({id,kind:'VIDEO',status:'AVAILABLE',content:'أصل '+i,mime_type:'video/mp4',metadata:{title:'فيديو '+(i+1)},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'}));
 await page.route('**/*',r=>{const p=new URL(r.request().url()).pathname;if(r.request().method()!=='GET')writes.push(p);
 if(p==='/api/artifacts')return r.fulfill({json:{items,total:2,limit:100,offset:0}});
 if(p.endsWith('/distribution-readiness')){const id=p.split('/')[3];if(mode==='failure'&&id===ids[1])return r.fulfill({status:503,json:{detail:'unavailable'}});return r.fulfill({json:{artifact_id:mode==='mismatch'&&id===ids[1]?ids[0]:id,central_approval:'APPROVED',selection_stale:mode==='stale',targets:(mode==='incomplete'?['instagram']:['instagram','facebook','telegram']).map(platform=>({platform,label:platform==='instagram'?'Instagram':'Telegram',selected:mode!=='missing'&&platform!=='facebook',copy_status:'BLOCKED',copy_blockers:['عائق نسخة واضح'],execution_blockers:['لا تنفيذ']}))}});}
 if(p.endsWith('/platform-copies'))return r.fulfill({json:{items:[]}});
 if(p==='/api/connections')return r.fulfill({json:{telegram:{items:[]}}});if(p==='/posts'||p.startsWith('/posts/')||p==='/sources'||p.startsWith('/api/control/'))return r.fulfill({json:[]});if(p.startsWith('/api/'))return r.fulfill({json:{items:[],total:0}});return r.continue();});
 await page.goto('/bank?artifact_status=APPROVED');await page.getByRole('button',{name:'تحديد النتائج المؤهلة (حتى 100)',exact:true}).click();const panel=page.getByLabel('مراجعة دفعة Meta',{exact:true});await panel.getByRole('button').click();
 if(mode==='failure'||mode==='mismatch'||mode==='incomplete'){await expect(panel.getByRole('alert')).toBeVisible();await expect(panel.getByRole('article')).toHaveCount(0);}
 else if(mode==='missing'){await expect(panel.getByText('لم تُحفظ وجهة Meta لهذه المادة. لا نختارها تلقائياً.',{exact:true})).toHaveCount(2);await expect(panel.getByRole('link')).toHaveCount(0);}
 else{await expect(panel.getByRole('alert')).toHaveCount(2);await expect(panel).toContainText('وجهات محفوظة خارج هذه المراجعة: Telegram');await expect(panel).toContainText('لا نسخة محفوظة');}
 expect(writes).toEqual([]);
});

test('late response and local times do not follow a changed selected batch',async({page})=>{
 let release:()=>void=()=>{};let reads=0;
 const items=ids.map((id,i)=>({id,kind:'VIDEO',status:'AVAILABLE',content:'أصل '+i,mime_type:'video/mp4',metadata:{title:'فيديو '+(i+1)},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'}));
 await page.route('**/*',async r=>{const p=new URL(r.request().url()).pathname;
 if(p==='/api/artifacts')return r.fulfill({json:{items,total:2,limit:100,offset:0}});
 if(p.endsWith('/distribution-readiness')){reads++;const id=p.split('/')[3];if(reads===1)await new Promise<void>(resolve=>{release=resolve;});return r.fulfill({json:{artifact_id:id,central_approval:'APPROVED',targets:['instagram','facebook'].map(platform=>({platform,label:platform,selected:false,copy_blockers:[],execution_blockers:[]})),selection_stale:false}});}
 if(p.endsWith('/platform-copies'))return r.fulfill({json:{items:[]}});if(p==='/api/connections')return r.fulfill({json:{telegram:{items:[]}}});if(p==='/posts'||p.startsWith('/posts/')||p==='/sources'||p.startsWith('/api/control/'))return r.fulfill({json:[]});if(p.startsWith('/api/'))return r.fulfill({json:{items:[],total:0}});return r.continue();});
 await page.goto('/bank?artifact_status=APPROVED');await page.getByLabel('تحديد المخرج '+ids[0],{exact:true}).check();const panel=page.getByLabel('مراجعة دفعة Meta',{exact:true});await panel.getByRole('button').click();await expect.poll(()=>reads).toBe(1);await page.getByLabel('تحديد المخرج '+ids[1],{exact:true}).check();release();await expect(panel.getByRole('status')).toHaveCount(0);await expect(panel.getByRole('article')).toHaveCount(0);await panel.getByRole('button').click();await expect(panel.getByRole('article')).toHaveCount(2);
 await panel.getByText('اقتراح مواعيد محلي دون حفظ',{exact:true}).click();await panel.getByLabel('بداية مراجعة دفعة Meta').fill('2030-11-03T01:30');await panel.getByLabel('منطقة مراجعة دفعة Meta').fill('America/New_York');await panel.getByLabel('فاصل مراجعة دفعة Meta').fill('30');await expect(panel.getByRole('alert')).toContainText('يتكرر');await expect(panel.getByText('مقترح محلي، غير محفوظ:',{exact:false})).toHaveCount(0);
});
