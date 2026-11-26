import {describe,it,expect} from 'vitest';
import {arabicDefinition} from './arabicDefinition';
describe('Arabic definition display',()=>{
 it('translates exact known seed labels without changing the source value',()=>{const original='Arabic Literature Text';expect(arabicDefinition(original)).toBe('نص أدبي');expect(original).toBe('Arabic Literature Text');});
 it('does not infer from keys, near matches or custom values',()=>{for(const value of ['MY_PRODUCT','Arabic Literature Text custom','اسم مخصص','__proto__','toString',''])expect(arabicDefinition(value)).toBe(value);});
 it('translates descriptions and audience without claiming automatic publication',()=>{expect(arabicDefinition('Readers of Arabic literature and culture')).toBe('قراء الأدب العربي والثقافة');expect(arabicDefinition('A source-grounded text artifact ready for independent human review')).toContain('لمراجعة بشرية مستقلة');});
});
