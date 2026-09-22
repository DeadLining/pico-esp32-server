import test from 'node:test';
import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import { validateManifest, prepareFirmware, flashPrepared } from '../src/utils/picoFirmware.mjs';
const bytes = new Uint8Array(32).fill(7);
const sha = Buffer.from(await webcrypto.subtle.digest('SHA-256', bytes)).toString('hex');
const manifest = () => ({schema: 1, product: 'Pico', board: 'folotoy/ai-passport', chip: 'ESP32-C3', flashSize: 8388608, version: 'test', files: [{name: 'bootloader.bin', address: 0, size: bytes.length, sha256: sha}]});
const files = () => [{name: 'bootloader.bin', size: bytes.length, arrayBuffer: async () => bytes.slice().buffer}];
test('accepts Pico manifest without inventing offsets', () => assert.equal(validateManifest(manifest()).files[0].address, 0));
test('rejects other product, chip and board', () => {for (const key of ['product','chip','board']) assert.throws(() => validateManifest({...manifest(), [key]: 'wrong'}));});
test('rejects traversal, overlaps, bounds and empty parts', () => {
 for(const patch of [{name: '../app.bin'}, {address: -1}, {address: 1}, {address: 8388608}, {size: 0}, {size: 8388609}, {sha256: 'invalid'}]) {const m=manifest(); Object.assign(m.files[0],patch); assert.throws(()=>validateManifest(m));}
 const m=manifest(); m.files.push({...m.files[0],name:'other.bin'}); assert.throws(()=>validateManifest(m));
});
test('rejects incomplete/mismatched/duplicated local files', async () => {
 await assert.rejects(prepareFirmware(manifest(), [], webcrypto));
 await assert.rejects(prepareFirmware(manifest(), [...files(), ...files()], webcrypto));
 const m=manifest(); m.files[0].sha256='0'.repeat(64); await assert.rejects(prepareFirmware(m,files(),webcrypto));
});
test('hash verifies every part', async () => {const p=await prepareFirmware(manifest(),files(),webcrypto); assert.deepEqual(p[0].data,bytes);});
test('wrong chip or missing explicit confirmation never writes', async () => {
 let writes=0; const loader={chip:{CHIP_NAME:'ESP32-S3'},writeFlash:async()=>writes++};
 const prepared=await prepareFirmware(manifest(),files(),webcrypto);
 await assert.rejects(flashPrepared(loader,manifest(),prepared,{confirmed:true}));
 loader.chip.CHIP_NAME='ESP32-C3'; await assert.rejects(flashPrepared(loader,manifest(),prepared,{confirmed:false})); assert.equal(writes,0);
});
test('writes only supplied segments, no chip erase, MD5 enabled', async () => {
 let args; const loader={chip:{CHIP_NAME:'ESP32-C3'},detectFlashSize:async()=>'8MB',writeFlash:async a=>{args=a;}};
 const prepared=await prepareFirmware(manifest(),files(),webcrypto); const md5=()=>'';
 await flashPrepared(loader,manifest(),prepared,{confirmed:true,calculateMD5Hash:md5});
 assert.equal(args.eraseAll,false); assert.equal(args.fileArray[0].address,0); assert.equal(args.calculateMD5Hash,md5);
});

test('rejects smaller or unknown physical flash before writing', async () => {
 let writes=0;const loader={chip:{CHIP_NAME:'ESP32-C3'},detectFlashSize:async()=>'4MB',writeFlash:async()=>writes++};
 const prepared=await prepareFirmware(manifest(),files(),webcrypto);
 await assert.rejects(flashPrepared(loader,manifest(),prepared,{confirmed:true,calculateMD5Hash:()=>''})); assert.equal(writes,0);
});

test('verified writes reset into application, never use the download-mode reset', async () => {
 const events=[];
 const loader={chip:{CHIP_NAME:'ESP32-C3'},detectFlashSize:async()=>'8MB',writeFlash:async()=>events.push('verified'),transport:{setDTR:async x=>events.push(['DTR',x]),setRTS:async x=>events.push(['RTS',x])}};
 const prepared=await prepareFirmware(manifest(),files(),webcrypto);
 const result=await flashPrepared(loader,manifest(),prepared,{confirmed:true,calculateMD5Hash:()=>'',onStage:x=>events.push(x)});
 assert.deepEqual(events,['writing','verified','resetting',['DTR',false],['RTS',true],['RTS',false]]);
 assert.equal(result.resetRequested,true);
});
test('reset failure preserves verified-write outcome and requests manual restart', async () => {
 const loader={chip:{CHIP_NAME:'ESP32-C3'},detectFlashSize:async()=>'8MB',writeFlash:async()=>{},transport:{setDTR:async()=>{throw new Error('port lost')}}};
 const result=await flashPrepared(loader,manifest(),await prepareFirmware(manifest(),files(),webcrypto),{confirmed:true,calculateMD5Hash:()=>''});
 assert.equal(result.resetRequested,false);assert.match(result.resetError,/port lost/);
});
test('failed verification never resets or returns success', async () => {
 let reset=false;
 const loader={chip:{CHIP_NAME:'ESP32-C3'},detectFlashSize:async()=>'8MB',writeFlash:async()=>{throw new Error('MD5 mismatch')},transport:{setDTR:async()=>{reset=true}}};
 await assert.rejects(flashPrepared(loader,manifest(),await prepareFirmware(manifest(),files(),webcrypto),{confirmed:true,calculateMD5Hash:()=>''}),/MD5 mismatch/);
 assert.equal(reset,false);
});
