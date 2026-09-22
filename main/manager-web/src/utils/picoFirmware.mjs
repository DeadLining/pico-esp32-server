// Initial supported hardware is deliberately narrow: chip identity is not board identity.
export function validateManifest(m) {
  if (!m || ![1, 2].includes(m.schema) || m.product !== 'Pico' || typeof m.board !== 'string' || typeof m.chip !== 'string' || !Array.isArray(m.files) || !m.files.length || m.files.length > 16) throw new Error('Pico 固件清单格式不正确');
  if (m.schema === 1 && (m.board !== 'folotoy/ai-passport' || m.chip !== 'ESP32-C3' || m.flashSize !== 8388608)) throw new Error('旧版清单仅支持 FoloToy AI Passport / ESP32-C3 / 8MB');
  const names = new Set(); const ranges = [];
  for (const p of m.files) {
    if (!p || typeof p.name !== 'string' || !/^[a-zA-Z0-9_.-]+\.bin$/.test(p.name) || names.has(p.name) || !Number.isSafeInteger(p.address) || p.address < 0 || p.address % 4096 || !Number.isSafeInteger(p.size) || p.size < 1 || (m.schema === 1 && p.address + p.size > m.flashSize) || !/^[a-f0-9]{64}$/.test(p.sha256)) throw new Error('固件分段名称、地址、大小或 SHA-256 无效');
    names.add(p.name); ranges.push([p.address, p.address + Math.ceil(p.size / 4096) * 4096]);
  }
  ranges.sort((a,b)=>a[0]-b[0]); if (ranges.some((r,i)=>i > 0 && r[0] < ranges[i-1][1])) throw new Error('固件分段擦写区域重叠'); return m;
}
export async function prepareFirmware(manifest, files, cryptoProvider = globalThis.crypto) {
  validateManifest(manifest);
  const local = new Map();
  for (const file of files) {
    if (local.has(file.name)) throw new Error('存在重复文件名');
    local.set(file.name,file);
  }
  const result = [];
  for (const part of manifest.files) {
    const file = local.get(part.name);
    if (!file || file.size !== part.size) throw new Error(`缺少文件或大小错误：${part.name}`);
    const data = new Uint8Array(await file.arrayBuffer());
    const digest = await cryptoProvider.subtle.digest('SHA-256',data);
    const hash = Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('');
    if (hash !== part.sha256) throw new Error(`文件校验失败：${part.name}`);
    result.push({address:part.address,data});
  }
  return result;
}
export async function flashPrepared(loader, manifest, fileArray, options = {}) {
  validateManifest(manifest);
  if (!options.confirmed) throw new Error('需要用户确认刷写');
  if (loader.chip?.CHIP_NAME !== manifest.chip) throw new Error('已连接芯片与固件不匹配，已阻止写入');
  if (typeof options.calculateMD5Hash !== 'function') throw new Error('缺少写入校验器');
  if (fileArray.length !== manifest.files.length || fileArray.some((p,i)=>p.address !== manifest.files[i].address || p.data.length !== manifest.files[i].size)) throw new Error('刷写分段与清单不一致');
  if (await loader.detectFlashSize() !== '8MB') throw new Error('Flash 容量不是 8MB 或无法识别，已阻止写入');
  options.onStage?.('writing');
  await loader.writeFlash({fileArray, flashSize:'keep', flashMode:'keep', flashFreq:'keep', eraseAll:false, compress:true, reportProgress:options.reportProgress, calculateMD5Hash:options.calculateMD5Hash});
  options.onStage?.('resetting');
  try {
    // Release the boot strap, then pulse EN. Do not use UsbJtagSerialReset:
    // that sequence deliberately enters the ROM download mode.
    // esptool-js 0.6.1 HardReset only releases RTS, so assert it explicitly.
    await loader.transport.setDTR(false);
    await loader.transport.setRTS(true);
    await new Promise(resolve => setTimeout(resolve, 100));
    await loader.transport.setRTS(false);
    return { resetRequested: true };
  } catch (error) {
    return { resetRequested: false, resetError: error.message || String(error) };
  }
}
