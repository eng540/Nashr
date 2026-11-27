import {test,expect} from '@playwright/test';
for(const width of [390,1280])test(`library reads one bounded page, preserves global identity and cross-page selection at ${width}px`,async({page},info)=>{
 const reads:URL[]=[],writes:string[]=[];

 const items=Array.from({length:27},(_,i)=>({id:`item-${i}`,kind:'TEXT',status:'AVAILABLE',review_status:'APPROVED',content:`النص الأصلي الكامل ${i}`,source_knowledge_unit_id:'unit',metadata:{title:`مادة محفوظة ${String(i).padStart(2,'0')}`,source_type:'GENERATED'},created_at:'2026-01-01T00:00:00Z',updated_at:'2026-01-01T00:00:00Z',organization:null}));
 await page.route('**/*',async r=>{const u=new URL(r.request().url()),p=u.pathname;
 if(!p.startsWith('/api/')&&!p.startsWith('/posts')&&!p.startsWith('/schedules')&&!p.startsWith('/production-')&&p!=='/sources')return r.continue();
 if(r.request().method()!=='GET')writes.push(p);else reads.push(u);
 if(p==='/api/connections')return r.fulfill({json:{telegram:{items:[]}}});
 if(p==='/api/artifacts/library'){const q=u.searchParams.get('q')||'',offset=Number(u.searchParams.get('offset')),filtered=items.filter(i=>!q||i.content.includes(q));return r.fulfill({json:{items:filtered.slice(offset,offset+12),index:filtered.map(i=>({...i,content:null})),total:filtered.length,limit:12,offset,filter_options:{series:['سلسلة بعيدة'],categories:['تصنيف بعيد']}}});}
 if(p==='/api/artifacts/library-items')return r.fulfill({json:{items:u.searchParams.getAll('ids').map(id=>items.find(i=>i.id===id))}});
 if(p==='/sources'||p==='/posts'||p==='/api/artifacts'||p==='/api/artifacts/platform-variants'||p.startsWith('/api/control/')||p.startsWith('/production-'))return r.fulfill({json:[]});
 return r.fulfill({json:{items:[],total:0,sources:[],kinds:[],counts:{waiting:0,published:0,attention:0}}});
 });
 await page.setViewportSize({width,height:900});await page.goto('/bank?artifact_status=APPROVED');
 await expect(page.locator('#material-open-item-0')).toBeVisible();await expect(page.locator('#material-open-item-12')).toHaveCount(0);
 expect(reads.filter(u=>u.pathname==='/api/artifacts')).toHaveLength(0);
 expect(reads.filter(u=>u.pathname==='/api/artifacts/library')).toHaveLength(1);
 await page.getByLabel('تحديد المخرج item-0',{exact:true}).check();
 const pagination=page.getByLabel('ترقيم صفحات المخرجات');
 await pagination.getByRole('button',{name:'التالي'}).click();await expect(page.locator('#material-open-item-12')).toBeVisible();
 await page.getByLabel('تحديد المخرج item-12',{exact:true}).check();await expect(page.getByTestId('media-selection-count')).toHaveText('2 محدد');
 await expect.poll(()=>reads.filter(u=>u.pathname==='/api/artifacts/library-items').some(u=>u.searchParams.getAll('ids').includes('item-0')&&u.searchParams.getAll('ids').includes('item-12'))).toBeTruthy();
 await pagination.getByRole('button',{name:'السابق'}).click();await expect(page.getByLabel('تحديد المخرج item-0',{exact:true})).toBeChecked();
 await page.goto('/bank?artifact_status=APPROVED&artifact_id=item-26');
 await expect(page.getByText('النص الأصلي الكامل 26',{exact:true}).first()).toBeVisible();
 await page.getByRole('button',{name:'العودة إلى المكتبة',exact:true}).click();
 await expect(page.locator('#material-open-item-26')).toBeFocused();await expect(page.locator('#material-open-item-26')).toBeInViewport();
 expect(reads.filter(u=>u.pathname==='/api/artifacts/library').at(-1)?.searchParams.get('offset')).toBe('24');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();await page.screenshot({path:info.outputPath(`library-server-${width}.png`)});expect(writes).toEqual([]);
});

for(const mode of ['delayed','failed','changed','malformed'] as const)test(`exact selected read ${mode} blocks preparation without losing selection`,async({page})=>{
 let release:()=>void=()=>{};let calls=0;const writes:string[]=[];
 const item={id:'one',kind:'TEXT',status:'AVAILABLE',review_status:'APPROVED',content:'أصل كامل لا نسخة مختصرة',metadata:{title:'عنوان'},created_at:'2026-01-01',updated_at:'2026-01-01'};
 await page.route('**/*',async r=>{const p=new URL(r.request().url()).pathname;if(r.request().method()!=='GET')writes.push(p);
 if(p==='/api/artifacts/library')return r.fulfill({json:{items:[item],index:[{...item,content:null}],total:1,limit:12,offset:0,filter_options:{series:[],categories:[]}}});
 if(p==='/api/artifacts/library-items'){calls++;if(mode==='delayed')await new Promise<void>(resolve=>{release=resolve});if(mode==='failed')return r.fulfill({status:503,json:{detail:'unavailable'}});return r.fulfill({json:{items:mode==='malformed'?[item,item]:[{...item,review_status:mode==='changed'?'REJECTED':'APPROVED'}]}});}
 if(p==='/api/connections')return r.fulfill({json:{telegram:{items:[]}}});
 if(p.startsWith('/api/control/')||p.startsWith('/production-')||p==='/posts'||p==='/sources')return r.fulfill({json:[]});if(p.startsWith('/api/'))return r.fulfill({json:{items:[],total:0}});return r.continue();});
 await page.goto('/bank?artifact_status=APPROVED');await page.getByLabel('تحديد المخرج one',{exact:true}).check();await expect.poll(()=>calls).toBeGreaterThan(0);
 const create=page.getByTestId('create-telegram-media-drafts');await expect(create).toBeDisabled();
 if(mode==='delayed'){await expect(page.getByTestId('media-selection-count')).toHaveText('1 محدد');release();await expect(create).toBeEnabled();}
 if(mode==='failed'){await expect(page.getByText('تعذر تحميل المواد المحددة أو المرتبطة. لا نستخدم بيانات مختصرة للمراجعة.')).toBeVisible({timeout:15000});await expect(page.getByTestId('media-selection-count')).toHaveText('1 محدد');await expect(create).toBeDisabled();}
 if(mode==='malformed'){await expect(page.getByText('تعذر تحميل المواد المحددة أو المرتبطة. لا نستخدم بيانات مختصرة للمراجعة.')).toBeVisible({timeout:15000});await expect(create).toBeDisabled();}
 if(mode==='changed')await expect(page.getByTestId('media-selection-count')).toHaveText('0 محدد');expect(writes).toEqual([]);
});

test('Arabic title ordering uses compact identities and fetches only its ordered 12 originals',async({page})=>{

 const items=Array.from({length:15},(_,i)=>({id:'t'+i,kind:'TEXT',status:'AVAILABLE',review_status:'DRAFT',content:'أصل '+i,metadata:{title:['ي','أ','ب','ت','ث','ج','ح','خ','د','ذ','ر','ز','س','ش','ص'][i]},created_at:'2026-01-01',updated_at:'2026-01-01'}));const ids:string[][]=[];
 await page.route('**/*',r=>{const u=new URL(r.request().url()),p=u.pathname;if(p==='/api/artifacts/library'){expect(u.searchParams.get('include_items')).toBe('false');return r.fulfill({json:{items:[],index:items.map(i=>({...i,content:null})),total:15,limit:12,offset:0,filter_options:{series:[],categories:[]}}});}if(p==='/api/artifacts/library-items'){const requested=u.searchParams.getAll('ids');ids.push(requested);return r.fulfill({json:{items:requested.map(id=>items.find(i=>i.id===id))}});}if(p.startsWith('/api/control/')||p.startsWith('/production-')||p==='/posts'||p==='/sources')return r.fulfill({json:[]});if(p.startsWith('/api/'))return r.fulfill({json:{items:[],total:0}});return r.continue();});
 await page.goto('/bank?library_sort=title');await expect(page.locator('[id^="material-open-t"]')).toHaveCount(12);const expected=[...items].sort((a,b)=>a.metadata.title.localeCompare(b.metadata.title,'ar')).map(i=>i.id);expect(ids[0]).toEqual(expected.slice(0,12));expect(await page.locator('[id^="material-open-t"]').evaluateAll(nodes=>nodes.map(n=>n.id.replace('material-open-','')))).toEqual(expected.slice(0,12));
});
