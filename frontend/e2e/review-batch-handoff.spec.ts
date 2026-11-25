import {test,expect} from '@playwright/test';
const ids=['f1111111-1111-4111-8111-111111111111','f2222222-2222-4222-8222-222222222222'];
test('successful review preserves only its exact batch through approved continuation and reload without writes',async({page},info)=>{
 let approved=false,missing=false,writes:string[]=[];
 const item=(id:string,n:number,status:string)=>({id,kind:'TEXT',status:'AVAILABLE',content:`نص محفوظ ${n}`,storage_uri:null,mime_type:'text/plain',metadata:{title:`مادة دفعة ${n}`},review_status:status,created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z',review_fingerprint:`pin-${n}`});
 await page.route('**/*',async route=>{const r=route.request(),p=new URL(r.url()).pathname;
 if(r.method()!=='GET')writes.push(p);
 if(p==='/api/artifacts/batch-review/preview')return route.fulfill({json:{items:ids.map((id,n)=>item(id,n,'DRAFT'))}});
 if(p==='/api/artifacts/batch-review/approve'){approved=true;return route.fulfill({json:{approved_ids:ids,publishing_authorized:false}});}
 if(p==='/api/artifacts'){const status=new URL(r.url()).searchParams.get('review_status');let items=status==='APPROVED'&&approved?[...ids.map((id,n)=>item(id,n,'APPROVED')),item('f3333333-3333-4333-8333-333333333333',3,'APPROVED')]:!approved?ids.map((id,n)=>item(id,n,'DRAFT')):[];if(missing)items=items.filter(i=>i.id!==ids[1]);return route.fulfill({json:{items,total:items.length,limit:100,offset:0}});}
 if(p.startsWith('/api/'))return route.fulfill({json:p.includes('/control/')?[]:{items:[],total:0,telegram:{items:[]}}});
 if(['/posts','/sources'].some(x=>p.startsWith(x)))return route.fulfill({json:[]});return route.continue();});
 await page.goto('/bank');const review=page.getByLabel('مراجعة واعتماد دفعة',{exact:true});await review.getByRole('button',{name:'تحديد أصول الصفحة للمراجعة',exact:true}).click();await review.getByRole('button',{name:'معاينة الدفعة المحفوظة (2)',exact:true}).click();for(const id of ids)await review.getByLabel(`راجعت أصل المادة ${id}`,{exact:true}).check();await review.getByRole('button',{name:'تأكيد اعتماد الدفعة فقط (2)',exact:true}).click();
 await expect(page).toHaveURL(/review_batch=/);await expect(page.getByLabel('حالة مراجعة المخرجات')).toHaveValue('APPROVED');
 const handoff=page.getByLabel('متابعة الدفعة المعتمدة',{exact:true});const next=handoff.getByRole('button',{name:'تحديد الدفعة نفسها للتجهيز (2)',exact:true});await expect(next).toBeEnabled();await expect(page.getByTestId('media-selection-count')).toHaveText('0 محدد');await next.click();await expect(page.getByTestId('media-selection-count')).toHaveText('2 محدد');await expect(page.getByLabel('تحديد المخرج f3333333-3333-4333-8333-333333333333',{exact:true})).not.toBeChecked();expect(writes).toEqual(['/api/artifacts/batch-review/preview','/api/artifacts/batch-review/approve']);
 await page.reload();await expect(next).toBeEnabled();await expect(page.getByTestId('media-selection-count')).toHaveText('0 محدد');
 await page.setViewportSize({width:390,height:844});await page.addStyleTag({content:'header,a[href="#main-content"]{visibility:hidden}'});await handoff.screenshot({path:info.outputPath('batch-handoff-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 missing=true;await page.reload();await expect(next).toBeDisabled();await expect(handoff.getByRole('alert')).toContainText('لم نحدد جزءاً');await expect(page.getByTestId('media-selection-count')).toHaveText('0 محدد');expect(writes).toHaveLength(2);
 await handoff.getByRole('button',{name:'مسح متابعة الدفعة',exact:true}).click();await expect(handoff).toHaveCount(0);await expect(page).not.toHaveURL(/review_batch=/);
});

test('changing the handoff identity never preserves the preceding batch selection',async({page})=>{
 const extra='f4444444-4444-4444-8444-444444444444';
 const items=[...ids,extra].map(id=>({id,kind:'TEXT',status:'AVAILABLE',content:'أصل',storage_uri:null,mime_type:'text/plain',metadata:{},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'}));
 let writes=0;
 await page.route('**/*',async route=>{const r=route.request(),p=new URL(r.url()).pathname;if(r.method()!=='GET')writes++;if(p==='/api/artifacts')return route.fulfill({json:{items,total:3,limit:100,offset:0}});if(p.startsWith('/api/'))return route.fulfill({json:p.includes('/control/')?[]:{items:[],total:0,telegram:{items:[]}}});if(['/posts','/sources'].some(x=>p.startsWith(x)))return route.fulfill({json:[]});return route.continue();});
 await page.goto('/bank?artifact_status=APPROVED&review_batch='+ids.join(','));await page.getByText('المواد المحددة في رابط المتابعة (2)',{exact:true}).click();await expect(page.getByText('TEXT · f1111111',{exact:true})).toBeVisible();await expect(page.getByText('مادة غير متاحة في القراءة الحالية',{exact:true})).toHaveCount(0);await page.getByRole('button',{name:'تحديد الدفعة نفسها للتجهيز (2)',exact:true}).click();await expect(page.getByTestId('media-selection-count')).toHaveText('2 محدد');
 await page.goto('/bank?artifact_status=APPROVED&review_batch='+extra);await expect(page.getByTestId('media-selection-count')).toHaveText('0 محدد');await page.getByRole('button',{name:'تحديد الدفعة نفسها للتجهيز (1)',exact:true}).click();await expect(page.getByTestId('media-selection-count')).toHaveText('1 محدد');for(const id of ids)await expect(page.getByLabel(`تحديد المخرج ${id}`,{exact:true})).not.toBeChecked();expect(writes).toBe(0);
});
