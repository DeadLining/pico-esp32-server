import test from 'node:test';
import assert from 'node:assert/strict';
import {saveFirmware} from '../src/utils/saveFirmware.mjs';
const response = () => ({blob: async () => new Blob(['firmware'])});
test('picker precedes network; success follows write and close', async () => {
  const events=[];
  const browser={showSaveFilePicker: async () => {events.push('picker');return {createWritable:async()=>({write:async()=>events.push('write'),close:async()=>events.push('close')})};}};
  assert.deepEqual(await saveFirmware('id','pico.bin',{browser,resource:async()=>{events.push('fetch');return response();}}),{saved:true});
  assert.deepEqual(events,['picker','fetch','write','close']);
});
test('cancel does not fetch or compile',async()=>{
  assert.deepEqual(await saveFirmware('id','pico.bin',{browser:{showSaveFilePicker:async()=>{throw Object.assign(new Error(),{name:'AbortError'});}},resource:()=>assert.fail()}),{cancelled:true});
});
test('fallback retains URL for visible manual save, not a false saved confirmation',async()=>{
 const link={click(){},remove(){}};
 const browser={URL:{createObjectURL:()=> 'blob:test'},document:{createElement:()=>link,body:{appendChild(){}}}};
 assert.deepEqual(await saveFirmware('id','pico.bin',{browser,resource:async()=>response()}),{url:'blob:test'});
 assert.equal(link.download,'pico.bin');
});
