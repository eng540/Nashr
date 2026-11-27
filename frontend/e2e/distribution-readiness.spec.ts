import {libraryFixture} from './libraryFixture';
import {test,expect} from '@playwright/test';
test('central approval and untouched preview with explicit non-executing platform choice',async({page},info)=>{
 let saves=0;let unsafe=0;
 const item={id:'central',source_knowledge_unit_id:'u',kind:'TEXT',status:'AVAILABLE',content:'نص المادة الأصلي الكامل دون قص',storage_uri:null,mime_type:'text/plain',metadata:{title:'مادة مركزية تجريبية'},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'};
 const readiness={artifact_id:'central',source_fingerprint:'version1',central_approval:'APPROVED',original_text:item.content,selection_stale:false,targets:['telegram','instagram','x','youtube','facebook','tiktok'].map(platform=>({platform,label:platform,selected:false,copy_status:platform==='telegram'?'ORIGINAL_ELIGIBLE':'BLOCKED',copy_blockers:platform==='telegram'?[]:['يلزم التحقق من متطلبات المنصة'],execution_blockers:['لا إذن تنفيذ من الاختيار']}))};
 await page.route('**/*',async route=>{const request=route.request();const p=new URL(request.url()).pathname;
 if(p.startsWith('/api/')&&request.method()!=='GET'&&p!=='/api/artifacts/distribution-selection')unsafe++;
 if(p==='/api/artifacts'||p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return route.fulfill({json:libraryFixture(route, {items:[item],total:1,limit:100,offset:0})});
 if(p==='/api/artifacts/central/distribution-readiness')return route.fulfill({json:readiness});
 if(p==='/api/artifacts/distribution-selection'){saves++;const input=request.postDataJSON();expect(input.artifact_ids).toEqual(['central']);expect(input.fingerprints).toEqual({central:'version1'});expect(input.platforms).toEqual(['telegram']);return route.fulfill({json:{saved:1,items:[readiness]}});}
 if(['/posts','/sources','/api/control/'].some(x=>p.startsWith(x)))return route.fulfill({json:[]});return route.continue();});
 await page.goto('/bank?library_view=expanded');await page.getByLabel('حالة مراجعة المخرجات').selectOption('APPROVED');
 const panel=page.getByLabel('جاهزية توزيع central',{exact:true});
 await panel.getByRole('button',{name:'فحص جاهزية واختيار المنصات (1)',exact:true}).click();
 await expect(panel.getByText('اعتماد مركزي محفوظ',{exact:false})).toBeVisible();await panel.getByText('اعتماد مركزي محفوظ',{exact:false}).click();
 await panel.getByText('معاينة النص الأصلي دون تغيير',{exact:true}).click();await expect(panel.getByText(item.content,{exact:true})).toBeVisible();
 await panel.getByRole('button',{name:'تحديد جميع المنصات',exact:true}).click();await expect(panel.getByRole('checkbox',{checked:true})).toHaveCount(6);
 await panel.getByRole('button',{name:'إلغاء جميع المنصات',exact:true}).click();await panel.getByLabel('telegram',{exact:true}).check();
 await panel.getByRole('button',{name:'حفظ اختيار الوجهات فقط',exact:true}).click();await expect(panel.getByRole('status')).toContainText('لم تُنشأ مسودات');expect(saves).toBe(1);expect(unsafe).toBe(0);
 await page.addStyleTag({content:'header, body > div > header {visibility:hidden}'});await panel.getByText('اعتماد مركزي محفوظ',{exact:false}).click();await panel.screenshot({path:info.outputPath('readiness-desktop.png')});
 await page.setViewportSize({width:390,height:844});await panel.scrollIntoViewIfNeeded();await panel.screenshot({path:info.outputPath('readiness-mobile.png')});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});

test('batch add and remove preserve individual choices and expose mixed counts',async({page},info)=>{
 const writes:string[]=[];const calls:any[]=[];
 const items=['one','two'].map(id=>({id,source_knowledge_unit_id:'u',kind:'VIDEO',status:'AVAILABLE',content:'أصل '+id,storage_uri:'https://example.invalid/video.mp4',mime_type:'video/mp4',metadata:{title:'مادة '+id},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'}));
 const selections:Record<string,string[]>={one:['instagram'],two:['facebook']};let version=1;
 const readiness=(id:string)=>({artifact_id:id,source_fingerprint:'source-'+id,selection_version:'selection-'+id+'-'+version,central_approval:'APPROVED',original_text:'أصل '+id,selection_stale:false,targets:['telegram','instagram','x','youtube','facebook','tiktok'].map(platform=>({platform,label:platform,selected:selections[id].includes(platform),copy_status:'BLOCKED',copy_blockers:['يلزم تحقق'],execution_blockers:['لا إذن تنفيذ']}))});
 await page.route('**/*',async route=>{const r=route.request(),p=new URL(r.url()).pathname;
 if(p==='/api/connections')return route.fulfill({json:{telegram:{items:[]}}});
 if(p==='/api/artifacts'||p==='/api/artifacts/library'||p==='/api/artifacts/library-items')return route.fulfill({json:libraryFixture(route, {items,total:2,limit:100,offset:0})});
 if(p.endsWith('/distribution-readiness'))return route.fulfill({json:readiness(p.split('/')[3])});
 if(p==='/api/artifacts/distribution-selection'){
  const body=r.postDataJSON();calls.push(body);expect(body.selection_versions).toEqual({one:'selection-one-'+version,two:'selection-two-'+version});
  for(const id of body.artifact_ids)selections[id]=body.mode==='add'?[...new Set([...selections[id],...body.platforms])]:body.mode==='remove'?selections[id].filter(x=>!body.platforms.includes(x)):body.platforms;
  version++;return route.fulfill({json:{saved:2,items:items.map(x=>readiness(x.id))}});
 }
 if(p.startsWith('/api/')&&r.method()!=='GET')writes.push(p);
 if(['/posts','/sources','/api/control/'].some(x=>p.startsWith(x)))return route.fulfill({json:[]});
 if(p.startsWith('/api/'))return route.fulfill({json:{items:[],total:0}});return route.continue();});
 await page.goto('/bank?library_view=expanded');await page.getByLabel('حالة مراجعة المخرجات').selectOption('APPROVED');
 await page.getByRole('button',{name:'تحديد النتائج المؤهلة (حتى 100)',exact:true}).click();await expect(page.getByTestId('media-selection-count')).toHaveText('2 محدد');
 const panel=page.getByLabel('جاهزية توزيع الدفعة',{exact:true});await panel.getByRole('button',{name:'فحص جاهزية واختيار المنصات (2)',exact:true}).click();
 await expect(panel.getByLabel('طريقة تعديل وجهات الدفعة')).toHaveValue('add');
 await expect(panel.getByRole('checkbox',{checked:true})).toHaveCount(0);
 await expect(panel.getByText('مختارة حالياً 1/2',{exact:true})).toHaveCount(2);
 await panel.getByLabel('telegram',{exact:true}).check();await panel.getByRole('button',{name:'حفظ اختيار الوجهات فقط',exact:true}).click();
 await expect(panel.getByRole('status')).toContainText('حُفظ اختيار 2');expect(selections).toEqual({one:['instagram','telegram'],two:['facebook','telegram']});expect(calls[0].mode).toBe('add');
 await panel.getByLabel('طريقة تعديل وجهات الدفعة').selectOption('remove');await panel.getByLabel('telegram',{exact:true}).check();
 await panel.getByRole('button',{name:'حفظ اختيار الوجهات فقط',exact:true}).click();await expect.poll(()=>calls.length).toBe(2);expect(selections).toEqual({one:['instagram'],two:['facebook']});
 await panel.getByLabel('طريقة تعديل وجهات الدفعة').selectOption('replace');await expect(panel).toContainText('الاستبدال يمحو اختلافات الوجهات');
 expect(writes).toEqual([]);expect(calls.map(x=>x.mode)).toEqual(['add','remove']);
 await page.addStyleTag({content:'header {visibility:hidden}'});await panel.screenshot({path:info.outputPath('batch-destinations-desktop.png')});
 await page.setViewportSize({width:390,height:844});await panel.scrollIntoViewIfNeeded();await panel.screenshot({path:info.outputPath('batch-destinations-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
