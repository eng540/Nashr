import {test,expect} from '@playwright/test';
test('Reel exact preview and explicit public approval, never sends on preview',async({page},info)=>{
 const writes:string[]=[];let state='DRAFT';const job=()=>({id:'job1',state,snapshot_hash:'a'.repeat(64),permalink:null,snapshot:{caption:'الوصف المعتمد\n\nكما نُشر على Instagram',media_sha256:'b'.repeat(64),connection:{page_id:'100318492875156',page_name:'Engineering Creativity'},audience:'FACEBOOK_PAGE_PUBLIC_REEL'}});
 await page.route('**/api/**',async route=>{const r=route.request(),p=new URL(r.url()).pathname;if(!p.startsWith('/api/'))return route.continue();
 if(r.method()!=='GET')writes.push(p);
 if(p.endsWith('/prepare-delivery'))return route.fulfill({json:{published:false}});
 if(p.endsWith('/preview'))return route.fulfill({json:job()});
 if(p.endsWith('/job1/approve')){expect(r.postDataJSON()).toEqual({snapshot_hash:'a'.repeat(64),exact_words_approved:true,public_page_approved:true,media_transfer_approved:true});state='APPROVED';return route.fulfill({json:job()});}
 if(p==='/api/connections')return route.fulfill({json:{telegram:{items:[],credential_storage_ready:true},platforms:[{key:'facebook',label:'Facebook',state:'CONNECTION_ONLY',requirements:'ربط مستقل'}]}});
 if(p==='/api/connections/facebook')return route.fulfill({json:{configured:true,connection:null,pending:null,requirements:[],source:'https://developers.facebook.com/'}});
 if(p.startsWith('/api/connections/instagram'))return route.fulfill({json:{configured:false,connection:null,pending:null,requirements:[],missing_configuration:[]}});
 return route.fulfill({json:{items:[]}});
 });
 await page.goto('/connections');const panel=page.getByLabel('ربط صفحة Facebook',{exact:true});await panel.getByText('نشر Reel على صفحة Facebook، قرار مستقل',{exact:true}).click();
 await panel.getByLabel('مادة Facebook Reel',{exact:true}).fill('artifact1');await panel.getByRole('button',{name:'تجهيز نسخة توافق خاصة ومعاينة دون نشر'}).click();
 const approve=panel.getByRole('button',{name:'اعتماد نشر Reel العام الآن'});await expect(approve).toBeDisabled();expect(writes.every(p=>!p.endsWith('/approve'))).toBeTruthy();
 await page.setViewportSize({width:1280,height:1000});await panel.screenshot({path:info.outputPath('reel-desktop.png')});
 await page.setViewportSize({width:390,height:844});await panel.screenshot({path:info.outputPath('reel-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await panel.getByRole('checkbox',{name:'أوافق على نشر هذا الفيديو والوصف على الصفحة العامة الآن وإرسال الملف إلى Meta.'}).check();await approve.click();await expect(panel.getByText('الحالة: APPROVED')).toBeVisible();expect(writes).toHaveLength(3);
});
