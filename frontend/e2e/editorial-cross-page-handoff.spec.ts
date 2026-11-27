import {test,expect,type Page} from '@playwright/test';
async function setup(page:Page){let writes=0;const statuses:Record<string,string>={first:'APPROVED',second:'APPROVED'};let fail='',mismatch='',delay=false,reads:string[]=[],release=()=>{};const gate=new Promise<void>(r=>release=r);await page.route('**/*',async route=>{const r=route.request(),u=new URL(r.url()),p=u.pathname;if(r.method()!=='GET'){writes++;const id=p.split('/')[2];statuses[id]=p.endsWith('/reject')?'REJECTED':'APPROVED';return route.fulfill({json:{post_id:id,title:id,content:'نص محفوظ',status:statuses[id]}});}if(p==='/posts'){const id=u.searchParams.get('offset')==='30'?'second':'first';return route.fulfill({json:{items:[{post_id:id,title:id,content:'نص محفوظ',content_preview:'نص محفوظ',status:statuses[id]}],total:31}});}if(p==='/posts/first'||p==='/posts/second'){const id=p.split('/')[2];reads.push(id);if(delay)await gate;if(fail===id)return route.fulfill({status:503,json:{detail:'Read failed'}});return route.fulfill({json:{post_id:mismatch===id?'wrong':id,title:id,content:'نص محفوظ',status:statuses[id]}});}if(p==='/api/artifacts/library')return route.fulfill({json:{items:[],index:[],total:0,filter_options:{series:[],categories:[]}}});if(p==='/sources'||p.startsWith('/api/control/'))return route.fulfill({json:[]});if(p.startsWith('/api/')||p.startsWith('/posts')||p.startsWith('/schedules'))return route.fulfill({json:{items:[],total:0,sources:[],topics:[],kinds:[]}});return route.continue();});await page.goto('/bank?status=APPROVED');const results=page.getByRole('region',{name:'نتائج بنك المنشورات'});await page.getByLabel('تحديد first',{exact:true}).check();await results.getByRole('button',{name:'التالي',exact:true}).click();await page.getByLabel('تحديد second',{exact:true}).check();return{statuses,reads,results,writes:()=>writes,fail:(id:string)=>fail=id,mismatch:(id:string)=>mismatch=id,delay:()=>delay=true,release};}
for(const width of [390,1280]){
 test(`all selected approved IDs survive page changes and handoff ${width}`,async({page},info)=>{await page.setViewportSize({width,height:844});const f=await setup(page);await expect(f.results).toContainText('2 محدد');await f.results.getByRole('button',{name:'السابق',exact:true}).click();await expect(page.getByLabel('تحديد first',{exact:true})).toBeChecked();await page.getByLabel('تحديد first',{exact:true}).uncheck();await expect(f.results).toContainText('1 محدد');await page.getByLabel('تحديد first',{exact:true}).check();await page.getByTestId('go-publishing').scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath(`cross-page-${width}.png`)});await page.getByTestId('go-publishing').click();await expect.poll(()=>new URL(page.url()).searchParams.get('selected_post_ids')?.split(',').sort()).toEqual(['first','second']);expect(f.reads.sort()).toEqual(['first','second']);expect(f.writes()).toBe(0);});
 for(const scenario of ['offpage-rejected','offpage-draft','failed-read','wrong-id'])test(`handoff blocks entire selection on ${scenario} and retries ${width}`,async({page},info)=>{await page.setViewportSize({width,height:844});const f=await setup(page);if(scenario==='offpage-rejected')f.statuses.first='REJECTED';if(scenario==='offpage-draft')f.statuses.first='DRAFT';if(scenario==='failed-read')f.fail('first');if(scenario==='wrong-id')f.mismatch('first');await page.getByTestId('go-publishing').click();const error=page.getByRole('alert').filter({hasText:'لم يُنقل أي منشور'});await expect(error).toBeVisible();await expect(page).toHaveURL(/\/bank\?/);await expect(f.results).toContainText('2 محدد');if(scenario.startsWith('offpage'))await expect(error).toContainText('1 من 2 منشور محدد غير معتمد حالياً');await error.scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath(`${scenario}-${width}.png`)});f.statuses.first='APPROVED';f.fail('');f.mismatch('');await page.getByTestId('go-publishing').click();await expect.poll(()=>new URL(page.url()).searchParams.get('selected_post_ids')?.split(',')).toEqual(['first','second']);expect(f.writes()).toBe(0);});
 test(`pending handoff can cancel without losing selection ${width}`,async({page})=>{await page.setViewportSize({width,height:844});const f=await setup(page);f.delay();await page.getByTestId('go-publishing').click();await expect(f.results.locator('[inert]')).toHaveCount(1);await expect(page.locator('#editorial-posts')).toHaveAttribute('inert','');await page.getByRole('button',{name:'إلغاء الفحص',exact:true}).click();await expect(page.getByRole('alert').filter({hasText:'لم يُنقل أي منشور'})).toBeVisible();await expect(f.results).toContainText('2 محدد');f.release();await expect(page).toHaveURL(/\/bank\?/);expect(f.writes()).toBe(0);});
}
test('saved rejection is re-read before handoff even while old selection persists',async({page})=>{const f=await setup(page);await f.results.getByRole('button',{name:/second.*APPROVED/}).click();await page.getByLabel('ملاحظة المراجعة').fill('يحتاج مراجعة');await page.getByRole('button',{name:'رفض',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);await page.getByTestId('go-publishing').click();await expect(page.getByRole('alert').filter({hasText:'1 من 2 منشور محدد غير معتمد حالياً'})).toBeVisible();await expect(page).toHaveURL(/\/bank\?/);expect(f.reads.sort()).toEqual(['first','second','second']);expect(f.writes()).toBe(1);});

test('handoff bounds concurrent reads, cancels and rejects more than100 IDs without requests',async({page})=>{
 let reads=0,active=0,maxActive=0,release=()=>{};let block=true;const gate=new Promise<void>(r=>release=r);const row=(i:number)=>({post_id:`id-${i}`,title:`عنوان ${i}`,status:'APPROVED',content:'نص',content_preview:'نص'});
 await page.route('**/*',async route=>{const r=route.request(),u=new URL(r.url()),p=u.pathname;if(r.method()!=='GET')throw new Error('Unexpected write');if(p==='/posts'){const offset=Number(u.searchParams.get('offset')||0);return route.fulfill({json:{items:Array.from({length:30},(_,i)=>row(offset+i)),total:120}});}if(/^\/posts\/id-\d+$/.test(p)){reads++;active++;maxActive=Math.max(active,maxActive);if(block)await gate;active--;return route.fulfill({json:row(Number(p.split('-').pop()))});}if(p==='/api/artifacts/library')return route.fulfill({json:{items:[],index:[],total:0,filter_options:{series:[],categories:[]}}});if(p==='/sources'||p.startsWith('/api/control/'))return route.fulfill({json:[]});if(p.startsWith('/api/')||p.startsWith('/posts')||p.startsWith('/schedules'))return route.fulfill({json:{items:[],total:0,sources:[],topics:[],kinds:[]}});return route.continue();});await page.goto('/bank?status=APPROVED');const results=page.getByRole('region',{name:'نتائج بنك المنشورات'});await results.getByRole('button',{name:'تحديد الصفحة',exact:true}).click();await page.getByTestId('go-publishing').click();await expect.poll(()=>reads).toBe(4);expect(maxActive).toBe(4);await page.getByRole('button',{name:'إلغاء الفحص',exact:true}).click();await expect(page.getByRole('alert')).toContainText('بقي التحديد كما هو');release();block=false;for(let i=0;i<3;i++){await results.getByRole('button',{name:'التالي',exact:true}).click();await expect(results).toContainText(`صفحة ${i+2} من 4`);await results.getByRole('button',{name:'تحديد الصفحة',exact:true}).click();}await expect(results).toContainText('120 محدد');const before=reads;await page.getByTestId('go-publishing').click();await expect(page.getByRole('alert')).toContainText('يمكن فحص 100 منشور');expect(reads).toBe(before);await expect(page).toHaveURL(/\/bank\?/);
});

async function holdSearchDebounce(page: Page) {
 await page.addInitScript(() => {
  const originalSet = window.setTimeout.bind(window);
  const originalClear = window.clearTimeout.bind(window);
  const held = new Map<number, () => void>();
  let nextId = -1;
  (window as any).releaseSearchDebounce = () => {
   const callbacks = [...held.values()]; held.clear(); callbacks.forEach(callback => callback());
  };
  window.setTimeout = ((handler: TimerHandler, delay?: number, ...args: any[]) => {
   if (delay !== 300 || typeof handler !== 'function') return originalSet(handler, delay, ...args);
   const id = nextId--; held.set(id, () => handler(...args)); return id;
  }) as typeof window.setTimeout;
  window.clearTimeout = (id?: number) => { if (id !== undefined && held.delete(id)) return; originalClear(id); };
 });
}
for (const width of [390, 1280]) {
 test(`unchanged query never resets pagination, changed trimmed query does ${width}`, async ({page}) => {
  await page.setViewportSize({width, height: 844});
  await holdSearchDebounce(page);
  const f = await setup(page);
  await expect(f.results).toContainText('صفحة 2 من 2');
  await page.evaluate(() => (window as any).releaseSearchDebounce());
  await expect(f.results).toContainText('صفحة 2 من 2');
  await page.getByLabel('بحث المنشورات', {exact: true}).fill('   ');
  await page.evaluate(() => (window as any).releaseSearchDebounce());
  await expect(f.results).toContainText('صفحة 2 من 2');
  await page.getByLabel('بحث المنشورات', {exact: true}).fill(' new query ');
  await expect(f.results).toContainText('صفحة 2 من 2');
  const changed = page.waitForRequest(request => {const url = new URL(request.url()); return url.pathname === '/posts' && url.searchParams.get('q') === 'new query' && url.searchParams.get('offset') === '0';});
  await page.evaluate(() => (window as any).releaseSearchDebounce());
  await changed;
  await expect(f.results).toContainText('صفحة 1 من 2');
  expect(f.writes()).toBe(0);
 });
}
