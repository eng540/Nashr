import {test,expect} from '@playwright/test';
test.use({timezoneId:'Asia/Riyadh'});
test('calendar reads Meta by selected day and timezone, preserves uncertain states and exact review links',async({page},info)=>{
 const writes:string[]=[];const reads:string[]=[];let fail=false;
 await page.route('**/*',r=>{const u=new URL(r.request().url()),p=u.pathname;if(r.request().method()!=='GET')writes.push(p);
  if(p==='/api/platform-operations'){
   if(!u.searchParams.has('date'))return r.fulfill({json:{items:[],total:0,counts:{waiting:0,published:0,attention:0,total:0}}});
   reads.push(u.search);if(fail)return r.fulfill({status:503,json:{detail:'synthetic unavailable'}});
   const second=u.searchParams.get('date')==='2030-01-02';return r.fulfill({json:{total:second?1:2,items:second?[{id:'later',artifact_id:'later-original',platform:'facebook_photo',due_at:'2030-01-01T22:30:00Z',timezone:'UTC',state:'APPROVED',execution_state:'APPROVED',destination:'صفحة ثانية',title:'صورة اليوم التالي',permalink:null}]:[{id:'ig',artifact_id:'original',platform:'instagram',due_at:'2030-01-01T11:30:00Z',timezone:'UTC',state:'PENDING',execution_state:'DRAFT',destination:'creator',title:'موعد Instagram',permalink:null},{id:'fb',artifact_id:'original',platform:'facebook',due_at:'2030-01-01T12:00:00Z',timezone:'UTC',state:'OUTCOME_UNKNOWN',execution_state:'OUTCOME_UNKNOWN',destination:'الصفحة المختارة',title:'نتيجة غير محسومة',permalink:null}]}});
  }
  if(p==='/api/artifacts/platform-variants'||p==='/sources')return r.fulfill({json:[]});if(p.startsWith('/api/')||p.startsWith('/posts')||p.startsWith('/schedules'))return r.fulfill({json:{items:[],total:0,sources:[],kinds:[]}});return r.continue();
 });
 await page.setViewportSize({width:390,height:844});await page.goto('/publishing');await page.getByRole('button',{name:/التقويم/}).first().click();await page.getByLabel('تاريخ التقويم').fill('2030-01-01');const panel=page.getByLabel('تقويم Instagram وFacebook',{exact:true});await expect(panel).toContainText('موعد Instagram');await expect(panel).toContainText('نتيجة غير مؤكدة، لا إعادة إرسال');await expect(panel.getByRole('link').last()).toHaveAttribute('href','/connections?reel_artifact_id=original&reel_job_id=fb#platform-facebook');await expect(panel).toContainText('منطقة القرار المحفوظة: UTC');expect(reads.some(x=>x.includes('date=2030-01-01')&&x.includes('timezone=Asia%2FRiyadh'))).toBeTruthy();
 await panel.screenshot({path:info.outputPath('meta-day-calendar-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();await page.getByLabel('تاريخ التقويم').fill('2030-01-02');await expect(panel).toContainText('صورة اليوم التالي');await expect(panel).not.toContainText('موعد Instagram');await expect(panel.getByRole('link')).toHaveAttribute('href','/bank?artifact_status=APPROVED&artifact_id=later-original&photo_job_id=later');
 fail=true;await panel.getByRole('button',{name:'تحديث عمليات المنصات',exact:true}).click();await expect(panel.getByRole('alert')).toContainText('لا نعتبرها قائمة فارغة');expect(writes).toEqual([]);
});
