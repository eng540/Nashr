import {test,expect} from '@playwright/test';
for(const width of [390,1280])for(const change of ['clear','filters','section','selection','history','params','task','late-error','current','blocked','mixed','error'] as const)test(`eligibility respects current intent ${width} ${change}`,async({page},info)=>{
 let release=()=>{};const gate=new Promise<void>(r=>release=r);let pending=false,settled=false,writes=0;const requested:string[][]=[];
 await page.setViewportSize({width,height:844});
 await page.route('**/*',async route=>{const r=route.request(),u=new URL(r.url()),p=u.pathname;
 if(p==='/schedules/eligibility'){requested.push(u.searchParams.getAll('post_ids'));pending=true;await gate;await (change==='error'||change==='late-error'?route.fulfill({status:503,json:{detail:'تعذر فحص الأهلية التجريبي'}}):route.fulfill({json:{eligible:change==='blocked'?[]:['old'],blocked:change==='blocked'?[{post_id:'old',reason:'not eligible'}]:change==='mixed'?[{post_id:'new',reason:'not eligible'}]:[]}}));settled=true;return;}
 if(r.method()!=='GET'){writes++;return route.fulfill({json:{}});}
 if(p==='/posts')return route.fulfill({json:{items:[{post_id:'old',title:'المادة الأولى',status:'APPROVED',content_preview:'نص'},{post_id:'new',title:'المادة الثانية',status:'APPROVED',content_preview:'نص'}],total:2}});
 if(p==='/sources'||p.startsWith('/api/control/'))return route.fulfill({json:[]});
 if(p.startsWith('/api/')||p.startsWith('/schedules')||p.startsWith('/posts/'))return route.fulfill({json:{items:[],total:0,sources:[],kinds:[]}});return route.continue();});
 await page.goto('/publishing?view=ready&ready_task=editorial');await page.getByTestId('ready-post-old').getByRole('checkbox').check();if(change==='mixed')await page.getByTestId('ready-post-new').getByRole('checkbox').check();await page.getByTestId('create-plan').click();await expect(page.getByRole('status').filter({hasText:'تغيير التحديد أو مغادرة هذا العرض'})).toBeVisible();await expect.poll(()=>pending).toBe(true);
 if(change==='clear'||change==='late-error')await page.getByRole('button',{name:'مسح التحديد',exact:true}).click();
 if(change==='filters')await page.getByRole('button',{name:'مسح الفلاتر',exact:true}).click();
 if(change==='selection')await page.getByTestId('ready-post-new').getByRole('checkbox').check();
 if(change==='section')await page.getByRole('button',{name:/خطط النشر · Telegram/}).click();
 if(change==='history')await page.goBack();
 if(change==='params')await page.evaluate(()=>{history.pushState({},'',location.href+'&calendar_date=2026-11-28');dispatchEvent(new PopStateEvent('popstate'));});
 if(change==='task')await page.getByRole('button',{name:/متابعة مادة وتجهيز وجهاتها/}).click();
 release();await expect.poll(()=>settled).toBe(true);
 // Wait for the request's UI settlement as well, without depending on a fixed delay.
 if(['selection','current','mixed','error'].includes(change))await expect(page.getByTestId('create-plan')).toBeEnabled();
 if(['clear','filters','late-error','history','blocked'].includes(change)){await expect(page.getByTestId('selection-count')).toHaveText('0 محدد');await expect(page.getByTestId('schedule-panel')).toHaveCount(0);expect(new URL(page.url()).searchParams.has('selected_post_ids')).toBe(false);}
 if(change==='selection'){await expect(page.getByTestId('selection-count')).toHaveText('2 محدد');await expect(page.getByTestId('schedule-panel')).toHaveCount(0);}
 if(change==='section'){await expect(page.getByTestId('publishing-plans')).toBeVisible();await expect(page.getByTestId('schedule-panel')).toHaveCount(0);expect(new URL(page.url()).searchParams.get('view')).toBe('plans');}
 if(change==='params'){await expect(page.getByTestId('schedule-panel')).toHaveCount(0);expect(new URL(page.url()).searchParams.get('calendar_date')).toBe('2026-11-28');}
 if(change==='task'){await expect(page.getByTestId('schedule-panel')).toHaveCount(0);await expect(page.getByTestId('publishing-ready').getByRole('button',{name:/متابعة مادة وتجهيز وجهاتها/})).toHaveAttribute('aria-pressed','true');}
 if(change==='mixed'){await expect(page.getByTestId('schedule-panel')).toBeVisible();await expect(page.getByTestId('selection-count')).toHaveText('1 محدد');expect(new URL(page.url()).searchParams.get('selected_post_ids')).toBe('old');}
 if(change==='current'){await expect(page.getByTestId('schedule-panel')).toBeVisible();await expect(page.getByTestId('selection-count')).toHaveText('1 محدد');}
 if(change==='blocked')await expect(page.getByRole('status').filter({hasText:'تم استبعاد 1'})).toBeVisible();
 if(change==='error'){await expect(page.getByRole('status').filter({hasText:'تعذر فحص الأهلية التجريبي'})).toBeVisible();await expect(page.getByTestId('schedule-panel')).toHaveCount(0);await expect(page.getByTestId('selection-count')).toHaveText('1 محدد');}
 if(change==='late-error')await expect(page.getByText('تعذر فحص الأهلية التجريبي',{exact:true})).toHaveCount(0);
 if(change==='selection'||change==='current'){await page.getByTestId(change==='selection'?'selection-count':'schedule-panel').scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath(`eligibility-${change}-${width}.png`)});}
 expect(requested).toEqual([change==='mixed'?['old','new']:['old']]);if(change==='selection'){await page.getByTestId('create-plan').click();await expect(page.getByTestId('schedule-panel')).toBeVisible();await expect(page.getByTestId('selection-count')).toHaveText('2 محدد');expect(requested).toEqual([['old'],['old','new']]);}expect(writes).toBe(0);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
