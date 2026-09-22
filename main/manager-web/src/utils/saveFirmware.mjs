import { firmwareResource } from './firmwareDownload.mjs';

/** Invoke the picker BEFORE awaiting network I/O, while user activation is live. */
export async function saveFirmware(id, name, {token, browser = globalThis, resource = firmwareResource} = {}) {
  let handle;
  if (typeof browser.showSaveFilePicker === 'function') {
    try {
      handle = await browser.showSaveFilePicker({suggestedName: name,
        types: [{description: 'Pico 固件', accept: {'application/octet-stream': ['.bin']}}]});
    } catch (error) {
      if (error.name === 'AbortError') return {cancelled: true};
      // Embedded browsers may expose but prohibit the picker; retain a visible fallback.
      if (!['SecurityError', 'NotAllowedError', 'NotSupportedError'].includes(error.name)) throw error;
    }
  }
  const response = await resource(id, 'artifact/' + name, {token});
  const blob = await response.blob();
  if (!blob.size) throw new Error('固件文件为空，已停止保存');
  if (handle) {
    const stream = await handle.createWritable();
    try { await stream.write(blob); await stream.close(); }
    catch (error) { await stream.abort().catch(() => {}); throw error; }
    return {saved: true};
  }
  const url = browser.URL.createObjectURL(blob);
  const link = browser.document.createElement('a');
  link.href = url; link.download = name;
  browser.document.body.appendChild(link); link.click(); link.remove();
  // Caller owns URL lifetime and exposes a persistent, user-clickable save link.
  return {url};
}
