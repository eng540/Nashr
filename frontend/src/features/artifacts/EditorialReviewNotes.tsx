import type {GenericReviewableArtifact} from '../../shared/api/artifactsApi';

export function editorialReviewNotes(metadata:Record<string,unknown>):string[]{
 const library=metadata.video_library;
 const nested=library&&typeof library==='object'&&!Array.isArray(library)?(library as Record<string,unknown>).editorial_notes:undefined;
 return [metadata.editorial_notes,nested].flatMap(value=>Array.isArray(value)?value.filter((note):note is string=>typeof note==='string'&&note.trim().length>0):typeof value==='string'&&value.trim()?[value]:[]);
}

export function EditorialReviewNotes({artifact}:{artifact:GenericReviewableArtifact}){
 const notes=editorialReviewNotes(artifact.metadata);
 if(!notes.length)return null;
 return <section aria-label="ملاحظات الأصل قبل المراجعة" className="min-w-0 space-y-2 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-7">
  <h4 className="font-bold">ملاحظات محفوظة مع الأصل · {notes.length}</h4>
  <p>راجع هذه الملاحظات قبل اتخاذ قرارك. عرضها لا يعني تحققها أو زوال قيودها، ولا يغيّر اعتماد المادة أو يسمح بالنشر.</p>
  <details className="min-w-0"><summary className="min-h-11 cursor-pointer py-2 font-semibold">قراءة ملاحظات المراجعة والمصادر ({notes.length})</summary><ol className="list-inside list-decimal space-y-3">{notes.map((note,index)=><li key={index} dir="auto" className="whitespace-pre-wrap break-words rounded-lg bg-white p-3 [overflow-wrap:anywhere]">{note}</li>)}</ol></details>
 </section>;
}
