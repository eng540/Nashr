import {test,expect} from '@playwright/test';
for(const width of [390,1280])for(const initial of ['DRAFT','APPROVED'] as const)test(`saved production result continues exact reviewed post ${width} ${initial}`,async({page},info)=>{
 let status:string=initial,reads=0,eligibility=0;const writes:string[]=[];const post=()=>({post_id:'exact-post',title:'مخرج المصدر نفسه',content:'النص الأصلي الكامل',status,source_title:'المصدر المحفوظ'});
 await page.setViewportSize({width,height:844});await page.route('**/*',async r=>{const q=r.request(),p=new URL(q.url()).pathname;
 if(q.method()!=='GET'){writes.push(p);if(p==='/posts/exact-post/approve'){status='APPROVED';return r.fulfill({json:post()});}throw Error('Unexpected write');}
 if(p==='/posts/exact-post'){reads++;return r.fulfill({json:post()});}
 if(p==='/schedules/eligibility'){eligibility++;expect(new URL(q.url()).searchParams.getAll('post_ids')).toEqual(['exact-post']);return r.fulfill({json:{eligible_ids:['exact-post'],blocked:[]}});}
 if(p==='/production-jobs/saved')return r.fulfill({json:{job_id:'saved',status:'COMPLETED',total_items:1,completed_items:1,progress_percent:100,resolved_prompt:{available:false},resolved_context:{available:false}}});
 if(p==='/production-jobs/saved/items')return r.fulfill({json:{items:[{item_id:'i',title:'مادة',position:1,status:'COMPLETED',post_id:'exact-post'}],total:1}});
 if(p==='/sources'||p.startsWith('/api/control/'))return r.fulfill({json:[]});
 if(p.startsWith('/api/')||p.startsWith('/posts')||p.startsWith('/schedules')||p==='/production-jobs')return r.fulfill({json:{items:[],total:0,kinds:[],topics:[],sources:[]}});return r.continue();});
 await page.goto('/production?job_id=saved');await page.getByRole('link',{name:'فتح المنشور في بنك المحتوى',exact:true}).click();const linked=page.getByRole('region',{name:'المنشور المرتبط بمهمة الإنتاج'});await expect(linked).toContainText('النص الأصلي الكامل');
 if(initial==='DRAFT'){await expect(linked.getByTestId('linked-post-publishing')).toHaveCount(0);await linked.getByRole('button',{name:'فتح مراجعة المنشور',exact:true}).click();await page.getByRole('button',{name:'اعتماد',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);}
 await expect(linked.getByTestId('linked-post-publishing')).toBeVisible();await linked.scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath(`linked-continuation-${width}-${initial}.png`)});const before=reads;await linked.getByTestId('linked-post-publishing').click();
 await expect.poll(()=>new URL(page.url()).searchParams.get('selected_post_ids')).toBe('exact-post');expect(reads).toBe(before+1);await expect(page.getByTestId('selection-count')).toHaveText('1 محدد');await expect(page.getByTestId('schedule-panel')).toHaveCount(0);expect(eligibility).toBe(0);
 await page.getByTestId('create-plan').click();await expect(page.getByTestId('schedule-panel')).toBeVisible();expect(eligibility).toBe(1);expect(writes).toEqual(initial==='DRAFT'?['/posts/exact-post/approve']:[]);
});

for(const width of [390,1280])for(const scenario of ['draft','rejected','wrong-id','error','cancel','navigation'] as const)test(`linked continuation revalidates ${width} ${scenario}`,async({page})=>{
 let changed=false,fail=true,reads=0,release=()=>{};const gate=new Promise<void>(r=>release=r);let writes=0;
 await page.setViewportSize({width,height:844});await page.route('**/*',async r=>{const q=r.request(),p=new URL(q.url()).pathname;if(q.method()!=='GET'){writes++;throw Error('Unexpected write');}
 if(p==='/posts/exact-post'){reads++;if(changed&&fail){if(scenario==='cancel'||scenario==='navigation')await gate;if(scenario==='error')return r.fulfill({status:503,json:{detail:'unavailable'}});}return r.fulfill({json:{post_id:changed&&fail&&scenario==='wrong-id'?'other':'exact-post',title:'مخرج محفوظ',content:'أصل محفوظ',status:changed&&fail&&scenario==='draft'?'DRAFT':changed&&fail&&scenario==='rejected'?'REJECTED':'APPROVED'}});}
 if(p==='/sources'||p.startsWith('/api/control/'))return r.fulfill({json:[]});if(p.startsWith('/api/')||p.startsWith('/posts')||p.startsWith('/schedules')||p==='/production-jobs')return r.fulfill({json:{items:[],total:0,kinds:[],topics:[],sources:[]}});return r.continue();});
 await page.goto('/bank?post_id=exact-post');const linked=page.getByRole('region',{name:'المنشور المرتبط بمهمة الإنتاج'});await expect(linked.getByTestId('linked-post-publishing')).toBeEnabled();changed=true;await linked.getByTestId('linked-post-publishing').click();
 if(scenario==='cancel'){await expect(linked.getByRole('status')).toContainText('جارٍ فحص');await linked.getByRole('button',{name:'إلغاء الفحص',exact:true}).click();release();}
 else if(scenario==='navigation'){await expect(linked.getByRole('status')).toBeVisible();await page.getByRole('link',{name:'مساحة النشر',exact:true}).click();release();await expect.poll(()=>new URL(page.url()).pathname).toBe('/publishing');expect(new URL(page.url()).searchParams.has('selected_post_ids')).toBe(false);expect(writes).toBe(0);return;}
 await expect(linked.getByRole('alert')).toContainText('لم يُنقل أي منشور');await expect(page).toHaveURL(/bank\?post_id=exact-post/);expect(reads).toBe(2);expect(writes).toBe(0);fail=false;await linked.getByTestId('linked-post-publishing').click();await expect.poll(()=>new URL(page.url()).searchParams.get('selected_post_ids')).toBe('exact-post');expect(writes).toBe(0);
});
