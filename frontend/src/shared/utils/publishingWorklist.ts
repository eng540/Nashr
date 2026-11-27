const fields=['queue_q','queue_origin','queue_state','queue_series','queue_category','queue_platform','queue_page','queue_focus'] as const;
export function worklistParams(params:URLSearchParams){
 const out=new URLSearchParams();
 for(const key of fields){const value=params.get(key);if(value&&value.length<=500)out.set(key,value);}
 if(!['POST','ARTIFACT'].includes(out.get('queue_origin')??''))out.delete('queue_origin');
 if(!['APPROVED','PLANNED','PUBLISHED','ATTENTION'].includes(out.get('queue_state')??''))out.delete('queue_state');
 if(!['NONE','telegram','instagram','x','youtube','facebook','tiktok'].includes(out.get('queue_platform')??''))out.delete('queue_platform');
 const page=Number(out.get('queue_page'));if(!Number.isSafeInteger(page)||page<1||page>100000)out.delete('queue_page');
 return out;
}
export function worklistUrl(params:URLSearchParams){const p=worklistParams(params);return '/publishing'+(p.size?'?'+p.toString():'');}
export function worklistReturn(value:string|null){
 if(!value||!value.startsWith('/publishing?')||value.length>5000)return null;
 try{const url=new URL(value,'https://local.invalid');if(url.origin!=='https://local.invalid'||url.pathname!=='/publishing')return null;return worklistUrl(url.searchParams);}catch{return null;}
}
