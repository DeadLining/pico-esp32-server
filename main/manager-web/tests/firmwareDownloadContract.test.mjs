import test from 'node:test';
import assert from 'node:assert/strict';
import { firmwareResource } from '../src/utils/firmwareDownload.mjs';

const id='6dcb4c94-fb66-45f7-afe3-3327ba021d0f';
const token=JSON.stringify({token:'test-admin-token'});
test('downloads binary using Authorization, never URL credentials',async()=>{
 const response=await firmwareResource(id,'artifact/pico.bin',{token,fetchImpl:async(url,opts)=>{
  assert.equal(url,`/pico/firmware-builder/build/${id}/artifact/pico.bin`);
  assert.equal(opts.headers.Authorization,'Bearer test-admin-token');
  return new Response(new Uint8Array([0xe9,1]),{headers:{'content-type':'application/octet-stream'}});
 }});
 assert.equal((await response.arrayBuffer()).byteLength,2);
});
test('manifest fetch also carries Authorization',async()=>{
 const r=await firmwareResource(id,'manifest',{token,fetchImpl:async(_,opts)=>{
  assert.equal(opts.headers.Authorization,'Bearer test-admin-token');
  return Response.json({schema:2,files:[]});
 }}); assert.equal((await r.json()).schema,2);
});
for(const status of [200,401]) test(`reports auth failure with HTTP ${status}`,async()=>{
 await assert.rejects(firmwareResource(id,'artifact/pico.bin',{token,fetchImpl:async()=>Response.json({code:401,msg:'未授权',data:null},{status})}),/重新登录/);
});
test('missing token fails without making a request',async()=>{
 await assert.rejects(firmwareResource(id,'manifest',{token:'',fetchImpl:()=>assert.fail('must not fetch')}),/重新登录/);
});
test('rejects path traversal',async()=>{
 await assert.rejects(firmwareResource(id,'artifact/../job.json',{token}),/路径/);
});
test('missing historical OTA is reported, not downloaded as a fake bin',async()=>{
 await assert.rejects(firmwareResource(id,'artifact/pico.bin',{token,fetchImpl:async()=>new Response('',{status:404})}),/不存在/);
});
test('JSON error with HTTP 200 is never saved as firmware',async()=>{
 await assert.rejects(firmwareResource(id,'artifact/pico.bin',{token,fetchImpl:async()=>Response.json({code:500,msg:'下载失败'})}),/下载失败/);
});
