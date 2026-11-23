import {test,expect} from '@playwright/test';
test('central approval and untouched preview with explicit non-executing platform choice',async({page},info)=>{
 let saves=0;let unsafe=0;
 const item={id:'central',source_knowledge_unit_id:'u',kind:'TEXT',status:'AVAILABLE',content:'نص المادة الأصلي الكامل دون قص',storage_uri:null,mime_type:'text/plain',metadata:{title:'مادة مركزية تجريبية'},review_status:'APPROVED',created_at:'2026-11-23T10:00:00Z',updated_at:'2026-11-23T10:00:00Z'};
 const readiness={artifact_id:'central',source_fingerprint:'version1',central_approval:'APPROVED',original_text:item.content,selection_stale:false,targets:['telegram','instagram','x','youtube','facebook','tiktok'].map(platform=>({platform,label:platform,selected:false,copy_status:platform==='telegram'?'ORIGINAL_ELIGIBLE':'BLOCKED',copy_blockers:platform==='telegram'?[]:['يلزم التحقق من متطلبات المنصة'],execution_blockers:['لا إذن تنفيذ من الاختيار']}))};
 await page.route('**/*',async route=>{const request=route.request();const p=new URL(request.url()).pathname;
 if(p.startsWith('/api/')&&request.method()!=='GET'&&p!=='/api/artifacts/distribution-selection')unsafe++;
 if(p==='/api/artifacts')return route.fulfill({json:{items:[item],total:1,limit:100,offset:0}});
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
