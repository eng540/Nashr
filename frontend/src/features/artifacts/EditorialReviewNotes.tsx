import type {GenericReviewableArtifact} from '../../shared/api/artifactsApi';

// Raw source records remain archived, never used as user-facing copy.
const internalPath=/(?:\/downloads\/|\/tmp\/|\/skills\/|\/memory\/|s3:\/\/|(?:^|\s)[A-Za-z]:\\)/i;
const internalProcess=/\b(?:gemini|charon|openai|anthropic|agent|handoff|pipeline|provider|producer)\b|\bmain\s*\(/i;
function isInternalRecord(note:string):boolean {
 const withoutSourceUrls=note.replace(/https:\/\/[^\s]+/g,'');
 return internalPath.test(withoutSourceUrls)||internalProcess.test(note);
}
export function editorialReviewNotes(metadata:Record<string,unknown>):string[]{
 const library=metadata.video_library;
 const value=library&&typeof library==='object'&&!Array.isArray(library)?(library as Record<string,unknown>).review_notes:undefined;
 return Array.isArray(value)?value.filter((note):note is string=>typeof note==='string'&&note.trim().length>0&&!isInternalRecord(note)):[];
}
function NoteText({text}:{text:string}){
 return <>{text.split(/(https:\/\/[^\s]+)/g).map((part,index)=>part.startsWith('https://')?<a key={index} href={part} target="_blank" rel="noreferrer" className="underline">{part}</a>:part)}</>;
}
export function EditorialReviewNotes({artifact}:{artifact:GenericReviewableArtifact}){
 const notes=editorialReviewNotes(artifact.metadata);
 const library=artifact.metadata.video_library as Record<string,unknown>|undefined;
 const pending=!notes.length&&(artifact.metadata.editorial_notes||library?.editorial_notes);
 if(!notes.length&&!pending)return null;
 return <section aria-label="ملاحظات الأصل قبل المراجعة" className="min-w-0 space-y-2 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-7">
  <h4 className="font-bold">ملاحظات المراجعة والمصادر{notes.length?` · ${notes.length}`:''}</h4>
  <p>راجع هذه الملاحظات قبل اتخاذ قرارك. عرضها لا يعني تحققها أو زوال قيودها، ولا يغيّر اعتماد المادة أو يسمح بالنشر.</p>
  {notes.length?<details className="min-w-0"><summary className="min-h-11 cursor-pointer py-2 font-semibold">قراءة ملاحظات المراجعة والمصادر ({notes.length})</summary><ol className="list-inside list-decimal space-y-3">{notes.map((note,index)=><li key={index} dir="auto" className="whitespace-pre-wrap break-words rounded-lg bg-white p-3 [overflow-wrap:anywhere]"><NoteText text={note}/></li>)}</ol></details>:<p>الملاحظات الأصلية محفوظة، وتنتظر إعداد ملخص مناسب للمراجعة. لا تُعد هذه المادة خالية من القيود أو معتمدة للنشر.</p>}
 </section>;
}
