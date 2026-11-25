import {describe,it,expect} from 'vitest';
import {editorialReviewNotes} from './EditorialReviewNotes';
describe('curated review notes',()=>{
 it('preserves curated caveats exactly and never falls back to raw records',()=>{
  expect(editorialReviewNotes({editorial_notes:['internal raw'],video_library:{editorial_notes:['raw'],review_notes:[' Engineering review needed.\nCement plaster only. ','https://www.astm.org/']}})).toEqual([' Engineering review needed.\nCement plaster only. ','https://www.astm.org/']);
 });
 it('hides legacy raw records and malformed values',()=>{
  for(const metadata of [{},{editorial_notes:'raw'},{video_library:[]},{video_library:{editorial_notes:['raw']}},{video_library:{review_notes:[null,{},false,' ']}}])expect(editorialReviewNotes(metadata)).toEqual([]);
 });
 it('rejects internal paths and process records even in curated input',()=>{
  expect(editorialReviewNotes({video_library:{review_notes:['/downloads/private.mp4','/tmp/a','Provider pipeline','Charon WAV','agent handoff','Civil review required']}})).toEqual(['Civil review required']);
 });
});
