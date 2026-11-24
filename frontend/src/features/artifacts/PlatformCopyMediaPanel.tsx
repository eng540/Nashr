import {useEffect,useState} from 'react';
import {useMutation,useQuery} from '@tanstack/react-query';
import {genericArtifactsApi,type CentralPlatformCopy,type JpegPreview} from '../../shared/api/artifactsApi';
export function PlatformCopyMediaPanel({id,copy,preview,background,disabled,onChanged}:{id:string;copy:CentralPlatformCopy;preview:JpegPreview|undefined;background:string;disabled:boolean;onChanged:()=>void}){
 const [open,setOpen]=useState(false);const [image,setImage]=useState<{url:string;source_stale:boolean}|null>(null);const [note,setNote]=useState('');
 const media=useQuery({queryKey:['copy-media',id,copy.platform,copy.version],enabled:open,queryFn:()=>genericArtifactsApi.copyMedia(id,copy.platform)});
 const changed=()=>{setImage(null);setNote('حُفظ اختيار وسيط هذه المنصة فقط وزاد إصدارها. الأصل والنص وبقية النسخ والخطط لم تتغير. لا إذن نشر.');onChanged();};
 const save=useMutation({mutationFn:()=>genericArtifactsApi.saveCopyJpeg(id,copy.platform,{source_fingerprint:copy.current_source_fingerprint,copy_version:copy.version,background,expected_sha256:preview!.sha256}),onSuccess:changed});
 const select=useMutation({mutationFn:(media_id:string|null)=>genericArtifactsApi.selectCopyMedia(id,copy.platform,{source_fingerprint:copy.current_source_fingerprint,copy_version:copy.version,media_id}),onSuccess:changed});
 const view=useMutation({mutationFn:(mediaId:string)=>genericArtifactsApi.copyMediaUrl(id,copy.platform,mediaId),onSuccess:setImage});
 const inspect=useMutation({mutationFn:()=>genericArtifactsApi.inspectSelectedMedia(id,copy.platform)});
 useEffect(()=>{setImage(null);inspect.reset();view.reset();},[copy.version,copy.current_source_fingerprint]);
 const busy=disabled||save.isPending||select.isPending||view.isPending||inspect.isPending;
 return <section className="rounded border bg-white p-2" aria-label="وسيط نسخة المنصة"><p>الاختيار الحالي: {copy.selected_media_id?'وسيط مشتق محفوظ لهذه المنصة':'الملف الأصلي'}. لا يغير هذا الاختيار جدولة Telegram القائمة.</p>
 {preview?<button type="button" disabled={busy||copy.source_stale||preview.copy_version!==copy.version} onClick={()=>save.mutate()} className="rounded border bg-violet-100 p-2">حفظ JPEG المعروضة واختيارها لهذه المنصة</button>:null}
 <button type="button" disabled={busy||copy.source_stale} onClick={()=>inspect.mutate()} className="mt-2 rounded border p-2">فحص الوسيط المختار لهذه النسخة</button>
 <details open={open} onToggle={e=>setOpen(e.currentTarget.open)}><summary>وسيط النسخة المحفوظ واختياره</summary>
 {copy.selected_media_id?<button type="button" disabled={busy} onClick={()=>select.mutate(null)} className="rounded border p-2">الرجوع للملف الأصلي لهذه المنصة</button>:null}
 <details><summary>شرح الحفظ وحدوده</summary><p>راجع المعاينة واختر الخلفية أولاً قبل حفظ JPEG. يتم التحقق من هاش النتيجة، ولا يُحفظ بديل مختلف بصمت. النص محفوظ مستقلاً.</p>{media.data?<p>{media.data.caveat}</p>:null}</details>
 <details><summary>تاريخ الوسائط والمعاينة الاختيارية</summary>
 {media.isLoading?<p>تحميل الوسائط المحفوظة...</p>:null}{media.data?.items.map(asset=><div key={asset.id} className="mt-2 space-y-2 rounded border p-2"><p>{asset.mime_type} · {String(asset.measurements.width)} × {String(asset.measurements.height)} · {asset.source_stale?'قديم، تغير الأصل':'مرتبط بالأصل الحالي'}</p><div className="flex flex-wrap gap-2"><button type="button" disabled={busy} onClick={()=>view.mutate(asset.id)} className="rounded border p-2">معاينة الملف المحفوظ</button>{copy.selected_media_id===asset.id?<span role="status">الوسيط المختار حالياً</span>:<button type="button" disabled={busy||asset.source_stale||copy.source_stale} onClick={()=>select.mutate(asset.id)} className="rounded border p-2">اختيار هذا الوسيط</button>}</div></div>)}
 {image?<div><p>{image.source_stale?'معاينة تاريخية فقط، لا يمكن اختيار وسيط قديم.':'معاينة الوسيط المحفوظ الخاص.'}</p><img src={image.url} alt="وسيط نسخة المنصة المحفوظ" className="max-h-96 max-w-full object-contain"/></div>:null}
 </details></details>
 {inspect.data?<div role="status"><p>قياسات المختار فقط، لا قبول نهائي أو إذن نشر.</p><p>{String(inspect.data.measurements.format)} · {String(inspect.data.measurements.width)} × {String(inspect.data.measurements.height)}</p>{[...inspect.data.blockers,...inspect.data.pending].map(x=><p key={x}>{x}</p>)}</div>:null}
 {media.isError||save.isError||select.isError||view.isError||inspect.isError?<p role="alert">{media.error?.message??save.error?.message??select.error?.message??view.error?.message??inspect.error?.message}</p>:null}{note?<p role="status">{note}</p>:null}
 </section>;
}
