import type {Route} from '@playwright/test';
// Existing workflow fixtures supply originals. Apply the new read contract to them,
// including real page boundaries and exact-ID reads, rather than a fetch-all fallback.
export function libraryFixture(route:Route, body:any):any {
 const u=new URL(route.request().url());if(!['/api/artifacts/library','/api/artifacts/library-items'].includes(u.pathname))return body;
 const all=Array.isArray(body)?body:body.items??[];
 if(u.pathname.endsWith('/library-items'))return {items:u.searchParams.getAll('ids').map(id=>all.find((i:any)=>i.id===id)).filter(Boolean)};
 const series=(i:any)=>i.organization?.series||i.metadata?.series||'غير مصنف';
 const category=(i:any)=>i.organization?.category||'غير مصنف';
 const q=(u.searchParams.get('q')??'').toLowerCase();
 const items=all.filter((i:any)=>['kind','source','series','category'].every(k=>{const v=u.searchParams.get(k);return !v||v==='ALL'||v===(k==='kind'?i.kind:k==='source'?i.metadata?.source_type??'GENERATED':k==='series'?series(i):category(i));})&&(!q||JSON.stringify(i).toLowerCase().includes(q)));
 // Existing workflow fixtures retain their declared order. Server sorting has integration coverage.
 const offset=Number(u.searchParams.get('offset')??0),limit=Number(u.searchParams.get('limit')??12);
 return {items:u.searchParams.get('include_items')==='false'?[]:items.slice(offset,offset+limit),index:items.map((i:any)=>({id:i.id,kind:i.kind,status:i.status,review_status:i.review_status,created_at:i.created_at,metadata:{title:i.organization?.title||i.metadata?.title||i.metadata?.caption?.trim().split("\n")[0]||i.kind,source_type:i.metadata?.source_type??"GENERATED",telegram_album:i.metadata?.telegram_album!=null?true:null,telegram_live_photo:i.metadata?.telegram_live_photo!=null?true:null}})),total:items.length,offset,limit,filter_options:{series:[...new Set(all.map(series))],categories:[...new Set(all.map(category))]}};
}
