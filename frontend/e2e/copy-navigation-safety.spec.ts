import {test,expect,type Page} from '@playwright/test';
import {libraryFixture} from './libraryFixture';
const editA='تحرير خاص لم يحفظ';
async function setup(page:Page,options:{failRead?:boolean;failSave?:boolean;delaySave?:boolean}={}){
 let writes=0,failReads=false,saves=0;let releaseSave:()=>void=()=>{};const pending=new Promise<void>(r=>{releaseSave=r});
 const items=Array.from({length:14},(_,n)=>({id:`copy-${n}`,kind:'TEXT',status:'AVAILABLE',review_status:'APPROVED',content:`أصل محفوظ ${n}`,metadata:{title:`مادة ${n}`},created_at:'2026-11-01',updated_at:'2026-11-01'}));
 const saved=new Map<string,any>();
 const copy=(id:string)=>saved.get(id)??{platform:'telegram',label:'Telegram',fields:{title:'',description:`نسخة محفوظة ${id}`,tags:[],alt_text:''},version:1,source_fingerprint:'v1',current_source_fingerprint:'v1',origin:'USER_EDITED',source_stale:false,central_approval:'APPROVED',field_status:'FIELDS_VALIDATED',blockers:[],warnings:[],media_checks_pending:[],execution_blockers:[],sources:[]};
 await page.route('**/*',async r=>{const p=new URL(r.request().url()).pathname,method=r.request().method();
 if(!p.startsWith('/api/')&&!p.startsWith('/posts')&&p!=='/sources'&&!p.startsWith('/production-'))return r.continue();
 if(method!=='GET')writes++;
 if(['/api/artifacts/library','/api/artifacts/library-items'].includes(p))return r.fulfill({json:libraryFixture(r,{items})});
 const match=p.match(/^\/api\/artifacts\/(copy-\d+)\/platform-copies(\/telegram)?$/);
 if(match){const id=match[1];if(method==='GET'){if(id==='copy-0'&&failReads&&options.failRead)return r.fulfill({status:503,json:{detail:'تعذر تحديث النسخ'}});return r.fulfill({json:{items:[copy(id)]}});}
 saves++;if(options.delaySave)await pending;if(options.failSave)return r.fulfill({status:409,json:{detail:'تغير إصدار النسخة؛ راجعها'}});const body=r.request().postDataJSON();const result={...copy(id),fields:body.fields,version:2};saved.set(id,result);return r.fulfill({json:result});}
 if(p==='/sources'||p==='/posts'||p.startsWith('/api/control/')||p.startsWith('/production-'))return r.fulfill({json:[]});
 return r.fulfill({json:{items:[],total:0,sources:[],kinds:[]}});
 });
 await page.goto('/bank?artifact_status=APPROVED&artifact_id=copy-0&copy_platform=telegram');
 await expect(page.getByLabel('وصف نسخة copy-0',{exact:true})).toHaveValue('نسخة محفوظة copy-0');
 return {count:()=>({writes,saves}),releaseSave,failNextReads:()=>{failReads=true}};
}
const field=(page:Page,id='copy-0')=>page.getByLabel(`وصف نسخة ${id}`,{exact:true});
async function nextBack(page:Page){await page.getByRole('button',{name:'المادة التالية',exact:true}).click();await expect(page.getByRole('button',{name:'المادة السابقة',exact:true})).toBeEnabled();await page.getByRole('button',{name:'المادة السابقة',exact:true}).click();}
for(const width of [390,1280]){
 test(`unsaved copy survives navigation, close, filter and pagination at ${width}px`,async({page},info)=>{
 await page.setViewportSize({width,height:900});const state=await setup(page);await field(page).fill(editA);
 await nextBack(page);await expect(field(page)).toHaveValue(editA);
 await page.getByRole('button',{name:'المادة التالية',exact:true}).click();const b=page.getByLabel('نسخ المنصات copy-1',{exact:true});if(!await field(page,'copy-1').isVisible())await b.locator('summary').first().click();await field(page,'copy-1').fill('مسودة المادة الثانية');await page.getByRole('button',{name:'المادة السابقة',exact:true}).click();await expect(field(page)).toHaveValue(editA);
 await page.getByRole('button',{name:'إغلاق مساحة المادة',exact:true}).click();await page.locator('#material-open-copy-0').click();await expect(field(page)).toHaveValue(editA);
 await page.getByLabel('بحث في المخرجات').fill('مادة 1');await page.getByLabel('بحث في المخرجات').fill('');await page.locator('#material-open-copy-0').click();await expect(field(page)).toHaveValue(editA);
 await page.getByRole('button',{name:'العودة إلى المكتبة',exact:true}).click();await page.getByRole('button',{name:'التالي',exact:true}).click();await page.getByRole('button',{name:'السابق',exact:true}).click();await page.locator('#material-open-copy-0').click();await expect(field(page)).toHaveValue(editA);
 await field(page).scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath(`copy-navigation-${width}.png`)});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.getByRole('button',{name:'تجاهل التعديلات غير المحفوظة',exact:true}).click();await nextBack(page);await expect(field(page)).toHaveValue('نسخة محفوظة copy-0');expect(state.count()).toEqual({writes:0,saves:0});
 });
 test(`restored draft survives saved-copy read failure at ${width}px`,async({page})=>{await page.setViewportSize({width,height:900});const state=await setup(page,{failRead:true});await field(page).fill(editA);state.failNextReads();await nextBack(page);await expect(field(page)).toHaveValue(editA);await expect(page.getByRole('alert')).toContainText('تعذر تحديث النسخ');expect(state.count().writes).toBe(0);});
 test(`save after navigation clears draft and reload uses saved fields at ${width}px`,async({page})=>{await page.setViewportSize({width,height:900});const state=await setup(page);await field(page).fill(editA);await nextBack(page);await page.getByRole('button',{name:'حفظ النسخة وفحص حقولها',exact:true}).click();await expect(page.getByLabel('نسخ المنصات copy-0',{exact:true}).getByLabel('منصة النسخة copy-0',{exact:true})).toBeEnabled();await nextBack(page);await expect(field(page)).toHaveValue(editA);await expect(page.getByRole('button',{name:'تجاهل التعديلات غير المحفوظة',exact:true})).toHaveCount(0);await page.reload();await expect(field(page)).toHaveValue(editA);expect(state.count()).toEqual({writes:1,saves:1});});
 for(const failSave of [false,true])test(`pending save is single flight across unmount and ${failSave?'failure retains':'success clears'} draft at ${width}px`,async({page})=>{await page.setViewportSize({width,height:900});const state=await setup(page,{delaySave:true,failSave});await field(page).fill(editA);await page.getByRole('button',{name:'حفظ النسخة وفحص حقولها',exact:true}).click();await expect.poll(()=>state.count().saves).toBe(1);await nextBack(page);await expect(field(page)).toHaveValue(editA);await expect(field(page)).toBeDisabled();await expect(page.getByRole('button',{name:'حفظ النسخة وفحص حقولها',exact:true})).toBeDisabled();state.releaseSave();await expect(field(page)).toBeEnabled();if(failSave){await expect(page.getByRole('alert')).toContainText('تغير إصدار النسخة');await expect(field(page)).toHaveValue(editA);await nextBack(page);await expect(page.getByRole('alert')).toContainText('تغير إصدار النسخة');await expect(field(page)).toHaveValue(editA);}else{await expect(page.getByRole('button',{name:'تجاهل التعديلات غير المحفوظة',exact:true})).toHaveCount(0);await expect(field(page)).toHaveValue(editA);}expect(state.count()).toEqual({writes:1,saves:1});});
 test(`reload drops unsaved draft without writing at ${width}px`,async({page})=>{await page.setViewportSize({width,height:900});const state=await setup(page);await field(page).fill(editA);await nextBack(page);await expect(field(page)).toHaveValue(editA);await page.reload();await expect(field(page)).toHaveValue('نسخة محفوظة copy-0');expect(state.count().writes).toBe(0);});
}
