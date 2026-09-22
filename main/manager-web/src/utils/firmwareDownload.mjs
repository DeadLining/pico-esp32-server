/** Authenticated same-origin firmware requests. Tokens never enter download URLs. */
export async function firmwareResource(id, resource, {token, fetchImpl = globalThis.fetch} = {}) {
  if (!/^[a-f0-9-]+$/.test(id) || !/^(manifest|artifact\/[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*)$/.test(resource)) {
    throw new Error('无效的固件资源路径');
  }
  let value;
  try { value = JSON.parse(token || '{}').token; } catch (_) { value = token; }
  if (typeof value !== 'string' || !value.trim()) throw new Error('登录状态已失效，请重新登录');
  const response = await fetchImpl(`/pico/firmware-builder/build/${id}/${resource}`, {
    headers: {Authorization: `Bearer ${value}`}, cache: 'no-store'
  });
  if (response.status === 401) throw new Error('登录状态已失效，请重新登录');
  if (response.status === 404) throw new Error('固件文件不存在：此历史任务可能未保存 OTA 文件，请先下载完整固件');
  const type = response.headers.get('content-type') || '';
  if (type.includes('json')) {
    const payload = await response.clone().json();
    if (payload.code === 401) throw new Error('登录状态已失效，请重新登录');
    if (!response.ok || (payload.code !== undefined && payload.code !== 0 && payload.code !== 'success') || resource !== 'manifest') {
      throw new Error(payload.msg || payload.error || '固件下载失败');
    }
  } else if (!response.ok || !type.includes('application/octet-stream')) {
    throw new Error(`固件下载失败（HTTP ${response.status}），未返回有效固件文件`);
  }
  return response;
}
