import {test,expect,type Page} from '@playwright/test';
const original='نص محفوظ', changed='تعديل تحريري غير محفوظ', note='ملاحظة لم تحفظ';
async function fixture(page:Page,mode:'fail'|'success'|'pending'='fail'){
 const writes:{path:string;body:string|null}[]=[];let release=()=>{};
 const gate=new Promise<void>(resolve=>{release=resolve;});
 const post={post_id:'editorial-safety',title:'منشور للمراجعة',content:original,content_preview:original,status:'DRAFT',source_title:'مصدر',topic_title:'محور',review_note:null};
 await page.route('**/*',async r=>{const req=r.request(),p=new URL(req.url()).pathname;if(req.method()!=='GET'){writes.push({path:p,body:req.postData()});if(mode==='pending')await gate;if(mode==='fail')return r.fulfill({status:503,json:{detail:'تعذر الحفظ'}});post.content=JSON.parse(req.postData()||'{}').content??post.content;return r.fulfill({json:post});}if(p==='/posts')return r.fulfill({json:{items:[post],total:1}});if(p.startsWith('/api/control/')||p==='/sources')return r.fulfill({json:[]});if(p.startsWith('/api/')||p.startsWith('/posts')||p.startsWith('/production-'))return r.fulfill({json:{items:[],total:0,sources:[],topics:[],kinds:[]}});return r.continue();});
 await page.goto('/bank?status=DRAFT');const opener=page.getByRole('button',{name:/منشور للمراجعة/});await opener.click();return {writes,release,opener,modal:page.getByRole('dialog'),text:page.getByLabel('محتوى المنشور'),reviewNote:page.getByLabel('ملاحظة المراجعة')};
}
for(const width of [390,1280]){
 test(`dirty Escape/Close retain text and note until explicit discard at ${width}px`,async({page},info)=>{
  await page.setViewportSize({width,height:844});const f=await fixture(page);await f.text.fill(changed);await f.reviewNote.fill(note);
  await page.keyboard.press('Escape');await expect(f.modal).toContainText('تجاهل التعديلات غير المحفوظة؟');const stay=page.getByRole('button',{name:'متابعة التحرير',exact:true});await expect(stay).toBeFocused();
  await f.modal.screenshot({path:info.outputPath(`editorial-close-confirm-${width}.png`)});await page.screenshot({path:info.outputPath(`editorial-close-full-${width}.png`)});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.keyboard.press('Tab');await expect(page.getByRole('button',{name:'تجاهل التعديلات وإغلاق',exact:true})).toBeFocused();await page.keyboard.press('Tab');await expect(stay).toBeFocused();
  await page.keyboard.press('Escape');await expect(f.text).toHaveValue(changed);await expect(f.reviewNote).toHaveValue(note);await expect(f.text).toBeFocused();
  await page.getByRole('button',{name:'إغلاق',exact:true}).click();await stay.click();await expect(f.text).toHaveValue(changed);await expect(f.reviewNote).toHaveValue(note);
  await page.getByRole('button',{name:'إغلاق',exact:true}).click();await page.getByRole('button',{name:'تجاهل التعديلات وإغلاق',exact:true}).click();await expect(f.modal).toHaveCount(0);await expect(f.opener).toBeFocused();await f.opener.click();await expect(f.text).toHaveValue(original);await expect(f.reviewNote).toHaveValue('');expect(f.writes).toEqual([]);
 });
 test(`note-only edits guarded; unchanged dialog closes immediately at ${width}px`,async({page})=>{
  await page.setViewportSize({width,height:844});const f=await fixture(page);await page.keyboard.press('Escape');await expect(f.modal).toHaveCount(0);await f.opener.click();await f.reviewNote.fill(note);await page.getByRole('button',{name:'إغلاق',exact:true}).click();await expect(f.modal).toContainText('تجاهل التعديلات غير المحفوظة؟');await page.getByRole('button',{name:'متابعة التحرير',exact:true}).click();await expect(f.reviewNote).toHaveValue(note);expect(f.writes).toEqual([]);
 });
 test(`failed save keeps edits guarded and approval disabled at ${width}px`,async({page})=>{
  await page.setViewportSize({width,height:844});const f=await fixture(page);await f.text.fill(changed);await f.reviewNote.fill(note);await page.getByRole('button',{name:'حفظ',exact:true}).click();await expect(f.modal.getByRole('alert')).toContainText('تعذر الحفظ');await page.keyboard.press('Escape');await page.getByRole('button',{name:'متابعة التحرير',exact:true}).click();await expect(f.text).toHaveValue(changed);await expect(f.reviewNote).toHaveValue(note);await expect(page.getByRole('button',{name:'اعتماد',exact:true})).toBeDisabled();expect(f.writes).toHaveLength(1);
 });
 test(`save freezes fields and preserves unsent review note at ${width}px`,async({page})=>{
  await page.setViewportSize({width,height:844});const f=await fixture(page,'pending');await f.text.fill(changed);await f.reviewNote.fill(note);await page.getByRole('button',{name:'حفظ',exact:true}).click();await expect(f.text).toBeDisabled();await expect(f.reviewNote).toBeDisabled();await page.keyboard.press('Escape');await expect(f.modal).toBeVisible();f.release();await expect(f.text).toBeEnabled();await expect(f.text).toHaveValue(changed);await expect(f.reviewNote).toHaveValue(note);await expect(page.getByRole('button',{name:'اعتماد',exact:true})).toBeEnabled();await page.getByRole('button',{name:'إغلاق',exact:true}).click();await expect(f.modal).toContainText('تجاهل التعديلات غير المحفوظة؟');expect(f.writes).toHaveLength(1);expect(JSON.parse(f.writes[0].body!)).toEqual({content:changed});
 });
 test(`successful save resets text dirtiness without closing or approval at ${width}px`,async({page})=>{
  await page.setViewportSize({width,height:844});const f=await fixture(page,'success');await f.text.fill(changed);await page.getByRole('button',{name:'حفظ',exact:true}).click();await expect(page.getByRole('button',{name:'اعتماد',exact:true})).toBeEnabled();await expect(f.text).toHaveValue(changed);await page.keyboard.press('Escape');await expect(f.modal).toHaveCount(0);expect(f.writes).toHaveLength(1);await f.opener.click();await expect(f.text).toHaveValue(changed);
 });
}

for(const action of ['اعتماد','رفض'])test(`pending ${action} blocks edits/close and success closes without extra write`,async({page})=>{
 const f=await fixture(page,'pending');await f.reviewNote.fill(note);await page.getByRole('button',{name:action,exact:true}).click();await expect(f.text).toBeDisabled();await expect(f.reviewNote).toBeDisabled();await expect(page.getByRole('button',{name:'إغلاق',exact:true})).toBeDisabled();await page.keyboard.press('Escape');await expect(f.modal).toBeVisible();expect(f.writes).toHaveLength(1);expect(f.writes[0].path).toMatch(action==='اعتماد'?/approve$/:/reject$/);expect(JSON.parse(f.writes[0].body!)).toEqual(action==='اعتماد'?{note}:{reason:note});f.release();await expect(f.modal).toHaveCount(0);expect(f.writes).toHaveLength(1);
});
test('successful note-only text save does not mark note saved or close',async({page})=>{
 const f=await fixture(page,'success');await f.reviewNote.fill(note);await page.getByRole('button',{name:'حفظ',exact:true}).click();await expect(f.modal).toContainText('تم حفظ النص');await expect(f.reviewNote).toHaveValue(note);await page.keyboard.press('Escape');await expect(f.modal).toContainText('تجاهل التعديلات غير المحفوظة؟');expect(f.writes).toHaveLength(1);expect(JSON.parse(f.writes[0].body!)).toEqual({content:original});
});
