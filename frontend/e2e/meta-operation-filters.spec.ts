import {test,expect} from '@playwright/test';
test('Meta summary cards open exact read-only group, platform filters reset pagination and calendar stays discoverable',async({page},info)=>{
 const reads:string[]=[];const writes:string[]=[];
 await page.route('**/*',r=>{const u=new URL(r.request().url()),p=u.pathname;if(r.request().method()!=='GET')writes.push(p);
 if(p==='/api/platform-operations'){
  reads.push(u.search);const group=u.searchParams.get('state_group')||'all',platform=u.searchParams.get('platform')||'all';const offset=Number(u.searchParams.get('offset')||0);const state=group==='attention'?'OUTCOME_UNKNOWN':group==='published'?'PUBLISHED':'PENDING';
  return r.fulfill({json:{total:group==='all'?21:1,counts:{waiting:1,published:1,attention:1,total:3},items:u.searchParams.get('limit')==='1'?[]:[{id:String(offset),artifact_id:'original',platform:platform==='all'?'instagram':platform,due_at:'2030-01-01T11:30:00Z',timezone:'Asia/Riyadh',state,execution_state:state,title:group+'-'+offset,destination:'synthetic',permalink:null}]}});
 }
 if(p==='/sources'||p==='/api/artifacts/platform-variants')return r.fulfill({json:[]});if(p.startsWith('/api/')||p.startsWith('/posts')||p.startsWith('/schedules'))return r.fulfill({json:{items:[],total:0}});return r.continue();});
 await page.setViewportSize({width:390,height:844});await page.goto('/publishing');await page.getByRole('button',{name:/عمليات Meta القادمة أو الجارية/}).click();const panel=page.getByLabel('عمليات Instagram وFacebook',{exact:true});await expect(panel.getByLabel('حالة عمليات Meta')).toHaveValue('waiting');await expect(panel).toContainText('waiting-0');
 await page.getByRole('button',{name:/نشر Meta المؤكد/}).click();await expect(panel.getByLabel('حالة عمليات Meta')).toHaveValue('published');await expect(panel).toContainText('published-0');
 await page.getByRole('button',{name:/عمليات تحتاج مراجعة/}).click();await expect(panel).toContainText('نتيجة غير مؤكدة، لا إعادة إرسال');await expect(panel.getByLabel('حالة عمليات Meta')).toHaveValue('attention');
 await panel.getByLabel('حالة عمليات Meta').selectOption('all');await expect(panel).toContainText('all-0');await panel.getByRole('button',{name:'التالي',exact:true}).click();await expect(panel).toContainText('all-20');await panel.getByLabel('مسار عمليات Meta').selectOption('facebook_photo');await expect(panel).toContainText('all-0');await expect(panel).toContainText('Facebook صورة');expect(reads.some(x=>x.includes('platform=facebook_photo')&&x.includes('offset=0'))).toBeTruthy();
 await panel.screenshot({path:info.outputPath('meta-filters-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();await page.getByRole('button',{name:/التقويم · كل المنصات/}).click();await expect(page.getByLabel('تقويم Instagram وFacebook',{exact:true})).toBeVisible();expect(writes).toEqual([]);
});
