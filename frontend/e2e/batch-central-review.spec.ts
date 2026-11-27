import {libraryFixture} from './libraryFixture';
import {test,expect} from '@playwright/test';
test('batch review requires each saved original and explicit final confirmation; stale failure clears preview',async({page},info)=>{
 const items=Array.from({length:2},(_,n)=>({id:`original-${n}`,kind:'TEXT',status:'AVAILABLE',content:`النص العربي الأصلي الكامل ${n} دون قص أو إعادة صياغة.`,storage_uri:null,mime_type:'text/plain',metadata:{title:`مادة أصلية ${n}`},review_status:'DRAFT',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z',review_fingerprint:`pin-${n}`}));
 let previews=0,approvals=0,stale=true;
 await page.route('**/*',async route=>{const path=new URL(route.request().url()).pathname;
 if(path==='/api/artifacts/batch-review/preview'){previews++;expect(route.request().postDataJSON()).toEqual({artifact_ids:items.map(i=>i.id)});return route.fulfill({json:{items,publishing_authorized:false}});}
 if(path==='/api/artifacts/batch-review/approve'){approvals++;expect(route.request().postDataJSON().fingerprints).toEqual({'original-0':'pin-0','original-1':'pin-1'});return stale?route.fulfill({status:409,json:{detail:'تغيرت إحدى المواد منذ المعاينة. لم يعتمد أي شيء.'}}):route.fulfill({json:{approved_ids:items.map(i=>i.id),publishing_authorized:false}});}
 if(path==='/api/artifacts'||path==='/api/artifacts/library'||path==='/api/artifacts/library-items')return route.fulfill({json:libraryFixture(route, {items,total:items.length,limit:100,offset:0})});
 if(['/posts','/sources','/api/control/'].some(x=>path.startsWith(x)))return route.fulfill({json:[]});return route.continue();});
 await page.setViewportSize({width:390,height:844});await page.goto('/bank');
 const panel=page.getByLabel('مراجعة واعتماد دفعة',{exact:true});
 await panel.getByRole('button',{name:'تحديد أصول الصفحة للمراجعة',exact:true}).click();expect(previews).toBe(0);expect(approvals).toBe(0);
 await panel.getByRole('button',{name:'معاينة الدفعة المحفوظة (2)',exact:true}).click();
 const commit=panel.getByRole('button',{name:'تأكيد اعتماد الدفعة فقط (2)',exact:true});await expect(commit).toBeDisabled();
 await panel.getByLabel('راجعت أصل المادة original-0',{exact:true}).check();await expect(commit).toBeDisabled();
 await panel.getByLabel('راجعت أصل المادة original-1',{exact:true}).check();await expect(commit).toBeEnabled();
 await page.addStyleTag({content:'header, a[href="#main-content"] {visibility:hidden}'});
 await panel.screenshot({path:info.outputPath('batch-review-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await commit.click();await expect(panel.getByRole('alert')).toContainText('لم يعتمد أي شيء');await expect(commit).toHaveCount(0);expect(approvals).toBe(1);
 stale=false;await panel.getByRole('button',{name:'معاينة الدفعة المحفوظة (2)',exact:true}).click();await panel.getByLabel('راجعت أصل المادة original-0',{exact:true}).check();await panel.getByLabel('راجعت أصل المادة original-1',{exact:true}).check();await commit.click();await expect(page).toHaveURL(/artifact_status=APPROVED/);await expect(page.getByLabel('متابعة الدفعة المعتمدة',{exact:true})).toBeVisible();expect(approvals).toBe(2);
});
