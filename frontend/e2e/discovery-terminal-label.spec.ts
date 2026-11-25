import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
test('saved terminal discovery state wins over historical processing stage',async({page})=>{
 const source=readFileSync('../app/api/console.py','utf8');const stage=source.split('\n').find(x=>x.startsWith('function stageLabel'))!;const label=source.split('\n').find(x=>x.startsWith('function discoveryLabel'))!;
 await page.goto('about:blank');const result=await page.evaluate(({stage,label})=>{const f=new Function(stage+'\n'+label+'\nreturn discoveryLabel;')();return ['COMPLETED','FAILED','RUNNING','QUEUED'].map(status=>f({status,stage:'FINALIZING'}));},{stage,label});expect(result).toEqual(['اكتمل تحليل الكتاب','تعذّر إكمال تحليل الكتاب','جاري إنهاء المخزون','جاري إنهاء المخزون']);expect(source).not.toContain('stageLabel(d.job.stage||d.job.status)');expect(source).not.toContain('stageLabel(d.stage||d.status)');
});
