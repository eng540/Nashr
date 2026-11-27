import {describe,it,expect} from 'vitest';
import {worklistParams,worklistReturn} from './publishingWorklist';
describe('publishing worklist read-only return scope',()=>{
 it('accepts only known display controls, never execution/selection/preview fields',()=>{
  const p=worklistParams(new URLSearchParams('queue_q=title&queue_state=PUBLISHED&queue_page=2&selected_post_ids=secret&preview_hash=secret&schedule_id=secret&view=operations'));
  expect(p.toString()).toBe('queue_q=title&queue_state=PUBLISHED&queue_page=2');
 });
 it('rejects external, protocol-relative and non-worklist destinations',()=>{
  for(const value of [null,'https://other.invalid/publishing?queue_q=a','//other.invalid/publishing?queue_q=a','/connections?queue_q=a','/publishing/../connections?queue_q=a','/publishing?'.repeat(1000)])expect(worklistReturn(value)).toBeNull();
 });
 it('normalizes invalid controls and strips unrelated parameters',()=>{
  expect(worklistReturn('/publishing?queue_state=bad&queue_page=-1&queue_origin=bad&queue_platform=bad&selected_post_ids=secret&queue_focus=abc')).toBe('/publishing?queue_focus=abc');
  for(const page of ['0','2.5','Infinity','100001','no'])expect(worklistParams(new URLSearchParams({queue_page:page})).has('queue_page')).toBe(false);
 });
});
