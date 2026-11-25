import { expect, test } from '@playwright/test';

test('selected approved media creates a separate reviewable album without sending', async ({page}, testInfo) => {
 const items=['a','b'].map((id,index)=>({id,source_knowledge_unit_id:'u',kind:'IMAGE',status:'AVAILABLE',content:null,storage_uri:'s3://test/'+id,mime_type:'image/png',metadata:{title:'صورة ألبوم '+index,caption:'تعليق '+index,original_filename:id+'.png'},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'}));
 let requested:any=null;
 await page.route('**/*',async route=>{
  const u=new URL(route.request().url());
  if(u.pathname==='/api/artifacts/album-draft') {requested=route.request().postDataJSON();return route.fulfill({status:201,json:{...items[0],id:'album',kind:'TEXT',content:'ألبوم',storage_uri:null,review_status:'DRAFT',metadata:{title:'ألبوم Telegram للمراجعة',telegram_album:{artifact_ids:['a','b']},album_preview:items.map(x=>({id:x.id,kind:x.kind,filename:x.metadata.original_filename,caption:x.metadata.caption}))}}});}
  if(u.pathname==='/api/artifacts') return route.fulfill({json:u.searchParams.get('review_status')==='APPROVED'?items: requested ? [{...items[0],id:'album',kind:'TEXT',content:'ألبوم',storage_uri:null,review_status:'DRAFT',metadata:{title:'ألبوم Telegram للمراجعة',telegram_album:{artifact_ids:['a','b']},album_preview:items.map(x=>({id:x.id,kind:x.kind,filename:x.metadata.original_filename,caption:x.metadata.caption}))}}] : []});
  if(items.some(x=>u.pathname==='/api/artifacts/'+x.id))return route.fulfill({json:items.find(x=>u.pathname==='/api/artifacts/'+x.id)});
  if(u.pathname.endsWith('/media-url'))return route.fulfill({json:{url:'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="purple"/></svg>',expires_in:300}});
  if(['/posts','/sources','/api/control/products','/api/control/recipes','/api/control/identities'].some(p=>u.pathname.startsWith(p)))return route.fulfill({json:[]});
  return route.continue();
 });
 await page.goto('/bank?library_view=expanded');await page.getByLabel('حالة مراجعة المخرجات').selectOption('APPROVED');
 await page.getByLabel('تحديد المخرج a',{exact:true}).check();await page.getByLabel('تحديد المخرج b',{exact:true}).check();
 await expect(page.getByRole('button',{name:'إنشاء ألبوم من المحدد (2-10)',exact:true})).toBeEnabled();
 await page.screenshot({path:testInfo.outputPath('album-selection-desktop.png'),fullPage:true});
 await page.getByRole('button',{name:'إنشاء ألبوم من المحدد (2-10)',exact:true}).click();
 await expect.poll(()=>requested).not.toBeNull();expect(requested.artifact_ids).toEqual(['a','b']);
 await expect(page.getByLabel('حالة مراجعة المخرجات')).toHaveValue('DRAFT');
 await expect(page.getByText('a.png',{exact:true}).first()).toBeVisible();
 await expect(page.locator('ol bdi').first()).toHaveAttribute('dir','ltr');
 await expect(page.locator('ol bdi')).toHaveText(['a.png','b.png']);
 await page.screenshot({path:testInfo.outputPath('album-draft-desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.getByLabel('حالة مراجعة المخرجات').selectOption('APPROVED');
 await page.screenshot({path:testInfo.outputPath('album-selection-mobile.png'),fullPage:true});
 await page.screenshot({path:testInfo.outputPath('album-selection-mobile-viewport.png')});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
});
