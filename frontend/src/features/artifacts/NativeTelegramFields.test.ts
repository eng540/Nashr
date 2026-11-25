import {describe,it,expect} from 'vitest';
import {blankNative,nativeError,nativeTypes} from './NativeTelegramFields';
describe('native content fields',()=>{
 it('does not invent coordinates contacts or poll answers',()=>{for(const kind of nativeTypes.filter(k=>k!=='DICE'))expect(nativeError(JSON.stringify(blankNative(kind)))).not.toBe('');expect(nativeError(JSON.stringify(blankNative('DICE')))).toBe('');});
 it('accepts exact bounded values and rejects wrong structured types',()=>{expect(nativeError(JSON.stringify({type:'LOCATION',latitude:0,longitude:0}))).toBe('');for(const latitude of ['',null,true,91])expect(nativeError(JSON.stringify({type:'LOCATION',latitude,longitude:39}))).not.toBe('');expect(nativeError(JSON.stringify({type:'LIVE_LOCATION',latitude:21,longitude:39,live_period:59}))).not.toBe('');expect(nativeError(JSON.stringify({type:'VENUE',latitude:21,longitude:39,title:5,address:'عنوان'}))).not.toBe('');expect(nativeError(JSON.stringify({type:'CONTACT',first_name:'اسم',phone_number:'+966500000001'}))).toBe('');expect(nativeError('null')).not.toBe('');expect(nativeError('{')).not.toBe('');});
});
