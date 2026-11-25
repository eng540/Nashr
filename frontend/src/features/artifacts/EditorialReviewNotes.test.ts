import {describe,it,expect} from 'vitest';
import {editorialReviewNotes} from './EditorialReviewNotes';
describe('stored editorial notes',()=>{
 it('preserves exact text/order across explicit fields',()=>{
  expect(editorialReviewNotes({editorial_notes:[' first\nline ',null,3,''],video_library:{editorial_notes:['engineering review required','not heard by ear']}})).toEqual([' first\nline ','engineering review required','not heard by ear']);
 });
 it('handles legacy strings without interpreting claims',()=>expect(editorialReviewNotes({editorial_notes:'APPROVED is only stored text'})).toEqual(['APPROVED is only stored text']));
 it('does not stringify objects or invent empty notes',()=>{
  for(const metadata of [{},{video_library:[]},{video_library:null},{editorial_notes:{claim:'approved'}},{video_library:{editorial_notes:[null,{},false,' ']}}])expect(editorialReviewNotes(metadata)).toEqual([]);
 });
});
