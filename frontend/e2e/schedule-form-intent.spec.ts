import {test,expect} from '@playwright/test';
for(const width of [390,1280])for(const change of ['section','task','selection','clear','filter-clear','history','close','unchanged','handoff'] as const)test(`open form stays with reviewed selection ${width} ${change}`,async({page},info)=>{
 let writes=0,reads=0;
 await page.setViewportSize({width,height:844});
 await page.route('**/*',r=>{const p=new URL(r.request().url()).pathname;if(r.request().method()!=='GET'){writes++;return r.fulfill({status:500,json:{detail:'Unexpected write'}});}if(p==='/schedules/eligibility'){reads++;return r.fulfill({json:{eligible:['one','two'],blocked:[]}});}if(p==='/posts')return r.fulfill({json:{items:[{post_id:'one',title:'المادة الأولى',status:'APPROVED'},{post_id:'two',title:'المادة الثانية',status:'APPROVED'}],total:2}});if(p==='/sources'||p.startsWith('/api/control/'))return r.fulfill({json:[]});if(p.startsWith('/api/')||p.startsWith('/posts/')||p.startsWith('/schedules'))return r.fulfill({json:{items:[],total:0,sources:[],kinds:[]}});return r.continue();});
 await page.goto('/publishing?view=ready&ready_task=editorial'+(change==='handoff'?'&selected_post_ids=one':''));
 if(change!=='handoff'){await page.getByTestId('ready-post-one').getByRole('checkbox').check();await page.getByTestId('create-plan').click();}
 await expect(page.getByTestId('schedule-panel')).toBeVisible();await page.getByLabel('وقت البداية',{exact:true}).fill('2026-12-01T12:00');await expect(page.getByTestId('submit-schedule')).toBeEnabled();
 if(change==='section')await page.getByRole('button',{name:/خطط النشر · Telegram/}).click();
 if(change==='task')await page.getByRole('button',{name:/متابعة مادة وتجهيز وجهاتها/}).click();
 if(change==='selection')await page.getByTestId('ready-post-two').getByRole('checkbox').check();
 if(change==='clear')await page.getByRole('button',{name:'مسح التحديد',exact:true}).click();
 if(change==='filter-clear')await page.getByRole('button',{name:'مسح الفلاتر',exact:true}).click();
 if(change==='history'){await page.goBack();await page.goBack();}
 if(change==='close')await page.getByTestId('schedule-panel').getByRole('button',{name:'إغلاق',exact:true}).click();
 if(change==='unchanged')await page.getByLabel('بحث المنشورات الجاهزة',{exact:true}).fill('عنوان');
 if(['unchanged','handoff'].includes(change)){await expect(page.getByTestId('schedule-panel')).toBeVisible();await expect(page.getByTestId('submit-schedule')).toBeEnabled();}
 else {await expect(page.getByTestId('schedule-panel')).toHaveCount(0);
  if(change==='selection'||change==='task'){const notice=page.getByRole('status').filter({hasText:'أُغلق نموذج الخطة'});await expect(notice).toBeVisible();await notice.scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath(`schedule-invalidated-${change}-${width}.png`)});}
  if(change==='section')await page.getByRole('button',{name:/المحتوى والتجهيز/}).click();
  if(change==='task')await page.getByRole('button',{name:/جدولة نصوص Telegram/}).click();
  await expect(page.getByTestId('schedule-panel')).toHaveCount(0);
  if(['clear','filter-clear','history'].includes(change)){await expect(page.getByTestId('selection-count')).toHaveText('0 محدد');await page.getByTestId('ready-post-one').getByRole('checkbox').check();}
  await page.getByTestId('create-plan').click();await expect(page.getByTestId('schedule-panel')).toBeVisible();expect(reads).toBe(2);
  await expect(page.getByTestId('selection-count')).toHaveText(change==='selection'?'2 محدد':'1 محدد');
 }
 if(change==='selection'||change==='task'){await page.getByTestId('schedule-panel').scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath(`schedule-rechecked-${change}-${width}.png`)});}
 expect(writes).toBe(0);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
for(const sameTurn of [false,true])test(`submit cannot include unchecked eligibility additions, same-turn=${sameTurn}`,async({page})=>{
 const posted:string[][]=[];const checked:string[][]=[];
 await page.route('**/*',async r=>{const q=r.request(),u=new URL(q.url()),p=u.pathname;if(p==='/schedules'&&q.method()==='POST'){posted.push(q.postDataJSON().post_ids);return r.fulfill({status:503,json:{detail:'Controlled save failure'}});}if(q.method()!=='GET')throw new Error('Unexpected write');if(p==='/schedules/eligibility'){checked.push(u.searchParams.getAll('post_ids'));return r.fulfill({json:{eligible:u.searchParams.getAll('post_ids'),blocked:[]}});}if(p==='/posts')return r.fulfill({json:{items:[{post_id:'one',title:'المادة الأولى',status:'APPROVED'},{post_id:'two',title:'المادة الثانية',status:'APPROVED'}],total:2}});if(p==='/sources'||p.startsWith('/api/control/'))return r.fulfill({json:[]});if(p.startsWith('/api/')||p.startsWith('/posts/')||p.startsWith('/schedules'))return r.fulfill({json:{items:[],total:0,sources:[],kinds:[]}});return r.continue();});
 await page.goto('/publishing?ready_task=editorial');await page.getByTestId('ready-post-one').getByRole('checkbox').check();await page.getByTestId('create-plan').click();await expect(page.getByTestId('schedule-panel')).toBeVisible();await page.getByLabel('وقت البداية',{exact:true}).fill('2026-12-01T12:00');
 if(sameTurn){await page.evaluate(()=>{const form=document.querySelector<HTMLFormElement>('[data-testid=schedule-panel]')!;document.querySelector<HTMLInputElement>('[data-testid=ready-post-two] input[type=checkbox]')!.click();form.requestSubmit();});await expect(page.getByTestId('schedule-panel')).toHaveCount(0);expect(posted.every(ids=>ids.join(',')==='one')).toBeTruthy();}
 else {await page.getByTestId('ready-post-two').getByRole('checkbox').check();await expect(page.getByTestId('schedule-panel')).toHaveCount(0);expect(posted).toEqual([]);await page.getByTestId('create-plan').click();await expect(page.getByTestId('schedule-panel')).toBeVisible();await page.getByTestId('submit-schedule').click();await expect.poll(()=>posted.length).toBe(1);expect(posted).toEqual([['one','two']]);expect(checked).toEqual([['one'],['one','two']]);}
});
