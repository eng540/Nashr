import {test,expect} from '@playwright/test';
test('private video preparation requires padding choice and never selects or publishes automatically',async({page},info)=>{
 const id='00000000-0000-4000-8000-000000000077',fp='a'.repeat(64);let prepared=0,unsafe=0;
 const item={id,kind:'VIDEO',status:'AVAILABLE',storage_uri:'s3://private/source.mp4',mime_type:'video/mp4',metadata:{caption:'فيديو محفوظ دون تغيير'},review_status:'APPROVED'};
 const copy={platform:'instagram',label:'Instagram',fields:{title:'',description:'فيديو محفوظ دون تغيير',tags:[],alt_text:''},version:1,current_source_fingerprint:fp,source_fingerprint:fp,origin:'UNCHANGED_ORIGINAL',source_stale:false,central_approval:'APPROVED',field_status:'FIELDS_VALIDATED',blockers:[],warnings:[],media_checks_pending:[],execution_blockers:[],sources:[]};
 await page.route('**/*',async route=>{const r=route.request(),p=new URL(r.url()).pathname;
 if(p==='/api/artifacts')return route.fulfill({json:{items:[item],total:1,limit:100,offset:0}});
 if(p===`/api/artifacts/${id}/platform-copies`)return route.fulfill({json:{items:[copy]}});
 if(p.endsWith('/media/video')){prepared++;expect(r.postDataJSON()).toEqual({source_fingerprint:fp,copy_version:1,full_frame_black_padding:true});return route.fulfill({json:{media:{id:'asset'},selected:false}});}
 if(p.endsWith('/media'))return route.fulfill({json:{items:prepared?[{id:'asset',mime_type:'video/mp4',measurements:{width:1080,height:1920},source_stale:false}]:[],selected_media_id:null,copy_version:1}});
 if(r.method()!=='GET')unsafe++;
 if(['/sources','/api/control/','/api/artifacts/platform-variants'].some(x=>p.startsWith(x)))return route.fulfill({json:[]});
 if(['/posts','/api/'].some(x=>p.startsWith(x)))return route.fulfill({json:{items:[],total:0}});return route.continue();});
 await page.setViewportSize({width:390,height:844});await page.goto(`/bank?artifact_status=APPROVED&artifact_id=${id}&copy_platform=instagram`);
 const panel=page.getByLabel('وسيط نسخة المنصة',{exact:true});const prepare=panel.getByRole('button',{name:'تجهيز فيديو خاص للمراجعة دون اختيار أو نشر',exact:true});
 await expect(prepare).toBeDisabled();await panel.getByRole('checkbox').check();await prepare.click();await expect(panel.getByRole('status')).toContainText('لم تُختر تلقائياً');
 await panel.getByText('تاريخ الوسائط والمعاينة الاختيارية',{exact:true}).click();await expect(panel.getByRole('button',{name:'اختيار هذا الوسيط',exact:true})).toBeVisible();
 expect(prepared).toBe(1);expect(unsafe).toBe(0);await expect(panel).toContainText('الملف الأصلي');
 await panel.screenshot({path:info.outputPath('private-video-mobile.png')});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.setViewportSize({width:1280,height:900});await panel.screenshot({path:info.outputPath('private-video-desktop.png')});
});
