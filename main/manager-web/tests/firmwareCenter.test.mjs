import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

function assert$flash(tpl){
  if(!tpl.includes("loadHistoryForFlash(s.row)")) throw new Error('history row must offer USB flashing');
  if(!/s\.row\.complete!==false/.test(tpl)) throw new Error('USB flashing must be limited to complete builds');
  if(!tpl.includes('<section class="card usb">')) throw new Error('USB flashing section must render');
}
import { shallowMount } from '@vue/test-utils';
import fs from 'node:fs';
import compiler from 'vue-template-compiler';
import * as firmware from '../src/utils/picoFirmware.mjs';
import { firmwareResource } from '../src/utils/firmwareDownload.mjs';

// Compile with the project's Vue 2.6 compiler; Vite's Vue 3 plugin cannot parse this app.
const sfc = compiler.parseComponent(fs.readFileSync('src/views/FirmwareCenter.vue', 'utf8'));
const script = sfc.script.content.replace(/^import .*;$/mg, '').replace('export default', 'return');
const catalog = JSON.parse(fs.readFileSync('src/generated/firmwareCatalog.json', 'utf8'));
const FirmwareCenter = new Function(
  'HeaderBar', 'SparkMD5', 'validateManifest', 'prepareFirmware', 'flashPrepared', 'catalog', 'firmwareResource', 'RequestService', 'saveFirmware', script,
)(
  { render: h => h('header') }, {}, firmware.validateManifest, firmware.prepareFirmware, firmware.flashPrepared, catalog, firmwareResource, {}, vi.fn(),
);
Object.assign(FirmwareCenter, compiler.compileToFunctions(sfc.template.content));

const stubs = {
  HeaderBar: true, 'el-alert': true, 'el-button': true, 'el-checkbox': true, 'el-progress': true,
  'el-select': true, 'el-option': true, 'el-input': true, 'el-tag': true, 'el-table': true, 'el-table-column': true, 'el-dialog': true,
};
const create = () => shallowMount(FirmwareCenter, {
  stubs, mocks: { $message: { warning: vi.fn(), success: vi.fn() }, $confirm: vi.fn().mockRejectedValue('cancel') },
});

// The component anchors history on the authenticated same-origin endpoint.
const okJson = (body) => Promise.resolve({ ok: true, status: 200, json: async () => body });
const authToken = JSON.stringify({ token: 'test-admin-token' });

describe('Pico firmware history UI', () => {
  let realFetch;
  beforeEach(() => {
    realFetch = globalThis.fetch;
    localStorage.setItem('token', authToken);
    window.scrollTo = vi.fn();
  });
  afterEach(() => { globalThis.fetch = realFetch; localStorage.clear(); });

  it('keeps verified results visible after serial disconnect without claiming boot success', async () => {
    globalThis.fetch = vi.fn(() => okJson({ builds: [] }));
    const wrapper = create();
    wrapper.vm.flashStage='done'; wrapper.vm.progress=100;
    await wrapper.vm.disconnect();
    expect(wrapper.vm.flashStatusText).toContain('尚未确认设备启动');
    expect(wrapper.vm.flashStage).toBe('done');
    wrapper.vm.flashStage='manual-reset';
    expect(wrapper.vm.flashStatusText).toContain('自动复位未完成');
    wrapper.destroy();
  });

  it('cancelling flash leaves the existing result and connection intact', async () => {
    globalThis.fetch = vi.fn(() => okJson({ builds: [] }));
    const wrapper = create();
    wrapper.vm.connected=true;wrapper.vm.progress=100;wrapper.vm.flashStage='done';
    await wrapper.vm.flash();
    expect(wrapper.vm.busy).toBe(false);
    expect(wrapper.vm.connected).toBe(true);
    expect(wrapper.vm.flashStage).toBe('done');
    wrapper.destroy();
  });

  it('loads history with the admin bearer token, never a query credential', async () => {
    let seen;
    globalThis.fetch = vi.fn((url, opts) => { seen = { url, opts }; return okJson({ code: 0, data: { builds: [] } }); });
    const wrapper = create();
    await wrapper.vm.loadHistory();
    expect(seen.url).toBe('/pico/firmware-builder/builds');
    expect(seen.opts.headers.Authorization).toBe('Bearer test-admin-token');
    expect(seen.url).not.toContain('token');
    expect(wrapper.vm.historyLoading).toBe(false);
    wrapper.destroy();
  });

  it('stores the builds array from the wrapped Result payload', async () => {
    globalThis.fetch = vi.fn(() => okJson({ code: 0, data: { builds: [{ id: 'a', status: 'success' }] } }));
    const wrapper = create();
    await wrapper.vm.loadHistory();
    expect(wrapper.vm.history).toHaveLength(1);
    expect(wrapper.vm.history[0].id).toBe('a');
    wrapper.destroy();
  });

  it('degrades to an empty history instead of throwing when the builder is down', async () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new Error('ECONNREFUSED')));
    const wrapper = create();
    await wrapper.vm.loadHistory();
    expect(wrapper.vm.history).toEqual([]);
    expect(wrapper.vm.historyLoading).toBe(false);
    wrapper.destroy();
  });

  it('only offers a download for files the builder reports as available', () => {
    const wrapper = create();
    const ok = { files: [{ name: 'merged-binary.bin', available: true }] };
    const gone = { files: [{ name: 'pico.bin', available: false }] };
    expect(wrapper.vm.hasFile(ok, 'merged-binary.bin')).toBe(true);
    expect(wrapper.vm.hasFile(gone, 'pico.bin')).toBe(false);
    expect(wrapper.vm.hasFile({ files: [] }, 'pico.bin')).toBe(false);
    wrapper.destroy();
  });

  it('reuseBuild restores brick selection from a history row', async () => {
    const wrapper = create();
    await wrapper.vm.loadBoards();
    const board = wrapper.vm.boards.find(b => b.target === 'esp32c3');
    expect(board, 'catalog must expose an esp32c3 board').toBeTruthy();
    wrapper.vm.reuseBuild({ request: { board: board.board, name: board.name, target: 'esp32c3', language: 'zh-CN', wake_word: 'wn9s_hiesp', build_options: {} } });
    expect(wrapper.vm.form.target).toBe('esp32c3');
    expect(wrapper.vm.form.board).toBe(board.board + '#' + board.name);
    expect(wrapper.vm.form.language).toBe('zh-CN');
    wrapper.destroy();
  });

  it('reuseBuild ignores an unknown board rather than corrupting the form', async () => {
    const wrapper = create();
    await wrapper.vm.loadBoards();
    const before = wrapper.vm.form.board;
    wrapper.vm.reuseBuild({ request: { board: 'does/not-exist', name: 'nope', target: 'esp32c8', language: 'xx-XX', wake_word: 'w' } });
    expect(wrapper.vm.form.board).toBe(before);
    expect(wrapper.vm.form.target).not.toBe('esp32c8');
    wrapper.destroy();
  });

  it('maps build status to a human label', () => {
    const wrapper = create();
    expect(wrapper.vm.statusText('success')).toBe('成功');
    expect(wrapper.vm.statusText('failed')).toBe('失败');
    expect(wrapper.vm.statusText('running')).toBe('编译中');
    wrapper.destroy();
  });

  it('history exposes a USB flash entry point only for complete builds', async () => {
    const tpl=compiler.parseComponent(fs.readFileSync('src/views/FirmwareCenter.vue','utf8')).template.content;
    assert$flash(tpl);
    const wrapper=create();
    await wrapper.vm.loadHistoryForFlash({id:'64bf56cb-72ad-49ad-ab2b-f7ab89d04c24',files:[]});
    expect(wrapper.vm.error).toContain('固件载入失败');
    wrapper.destroy();
  });

  it('renders a history row with board, chip and both firmware actions', async () => {
    globalThis.fetch = vi.fn(() => okJson({ code: 0, data: { builds: [{
      id: '64bf56cb-72ad-49ad-ab2b-f7ab89d04c24', status: 'success', chip: 'ESP32-C3',
      created_at: '2026-09-21T11:28:55Z',
      request: { board: 'folotoy/ai-passport', name: 'ai-passport', target: 'esp32c3', language: 'zh-CN', wake_word: 'wn9s_hiesp' },
      files: [{ name: 'merged-binary.bin', available: true }, { name: 'pico.bin', available: true }],
    }] } }));
    const wrapper = create();
    await wrapper.vm.loadHistory();
    wrapper.vm.$forceUpdate(); await wrapper.vm.$nextTick();
    // el-table renders cells through scoped slots, which the stub does not expand,
    // so assert the observable state plus the static contract of the row actions.
    expect(wrapper.html()).toContain('固件历史');
    const row = wrapper.vm.history[0];
    expect(row.request.board).toBe('folotoy/ai-passport');
    expect(row.chip).toBe('ESP32-C3');
    expect(wrapper.vm.hasFile(row, 'merged-binary.bin')).toBe(true);
    expect(wrapper.vm.hasFile(row, 'pico.bin')).toBe(true);
    const tpl = compiler.parseComponent(fs.readFileSync('src/views/FirmwareCenter.vue', 'utf8')).template.content;
    expect(tpl).toContain("downloadBuild(s.row,'full')");
    expect(tpl).toContain("downloadBuild(s.row,'ota')");
    wrapper.destroy();
  });

  it('offers a delete action and calls the DELETE endpoint after confirmation', async () => {
    const tpl = compiler.parseComponent(fs.readFileSync('src/views/FirmwareCenter.vue', 'utf8')).template.content;
    expect(tpl).toContain('removeBuild(s.row)');
    expect(tpl).toContain('history-delete');
    // Delete must be the first child in the action group so it stays leftmost.
    const group = tpl.slice(tpl.indexOf('history-actions'), tpl.indexOf('history-note'));
    expect(group.indexOf('history-delete')).toBeLessThan(group.indexOf('merged-binary.bin'));

    const calls = [];
    globalThis.fetch = vi.fn((url, opts = {}) => {
      calls.push({ url, method: opts.method || 'GET' });
      if ((opts.method || 'GET') === 'DELETE') return Promise.resolve({ ok: true, status: 200, json: async () => ({ code: 0, data: { deleted: 'x', freed_bytes: 2097152 } }) });
      return okJson({ code: 0, data: { builds: [] } });
    });
    const wrapper = create();
    wrapper.vm.$confirm = vi.fn().mockResolvedValue('confirm');
    await wrapper.vm.removeBuild({ id: '64bf56cb-72ad-49ad-ab2b-f7ab89d04c24' });
    const del = calls.find(c => c.method === 'DELETE');
    expect(del).toBeTruthy();
    expect(del.url).toBe('/pico/firmware-builder/build/64bf56cb-72ad-49ad-ab2b-f7ab89d04c24');
    expect(wrapper.vm.$message.success).toHaveBeenCalled();
    wrapper.destroy();
  });

  it('does not delete when the confirmation is cancelled', async () => {
    const calls = [];
    globalThis.fetch = vi.fn((url, opts = {}) => { calls.push(opts.method || 'GET'); return okJson({ code: 0, data: { builds: [] } }); });
    const wrapper = create();
    wrapper.vm.$confirm = vi.fn().mockRejectedValue('cancel');
    await wrapper.vm.removeBuild({ id: '64bf56cb-72ad-49ad-ab2b-f7ab89d04c24' });
    expect(calls).not.toContain('DELETE');
    expect(wrapper.vm.deletingId).toBe('');
    wrapper.destroy();
  });

  it('renders a structured log panel instead of a raw <pre>', () => {
    const tpl = compiler.parseComponent(fs.readFileSync('src/views/FirmwareCenter.vue', 'utf8')).template.content;
    expect(tpl).toContain('class="logpanel"');
    expect(tpl).toContain('logVisible');
    expect(tpl).toContain('copyBuildLog');
    expect(tpl).not.toMatch(/<pre[^>]*job\.log/);
  });

  it('classifies compiler lines so errors and warnings stand out', () => {
    const wrapper = create();
    const c = (s) => wrapper.vm.classifyLog(s);
    expect(c("/opt/x/main/a.cc:42:15: error: undefined reference to `x'")).toBe('error');
    expect(c('FAILED: esp-idf/main/CMakeFiles/app.dir/a.obj')).toBe('error');
    expect(c('ninja: build stopped: subcommand failed.')).toBe('error');
    expect(c('CMake Warning at cmake/x.cmake:10 (message):')).toBe('warn');
    expect(c('  deprecated option BUILD_OLD is obsolete')).toBe('warn');
    expect(c('NOTE: [28/62] espressif/esp_lcd_ili9341 (2.1.0)')).toBe('step');
    expect(c('[716/2110] Linking CXX static library libx.a')).toBe('step');
    expect(c('Successfully generated language config file: x')).toBe('ok');
    expect(c('python -m esptool --chip esp32c3 write_flash x')).toBe('cmd');
    expect(c('-- Found Git: /usr/bin/git')).toBe('info');
    expect(c('')).toBe('dim');
    wrapper.destroy();
  });

  it('issues-only filter keeps warnings/errors and drops routine lines', () => {
    const wrapper = create();
    wrapper.vm.job = { status: 'failed', progress: 100, log: [
      'NOTE: [1/62] pkg', '[12/148] Building C object a.obj',
      'warning: deprecated', 'error: boom', 'Successfully generated x',
    ].join('\n') };
    wrapper.vm.logFilter = 'all';
    expect(wrapper.vm.logVisible.length).toBe(5);
    wrapper.vm.logFilter = 'issues';
    const kinds = wrapper.vm.logVisible.map(l => l.kind);
    expect(kinds).toContain('error');
    expect(kinds).toContain('warn');
    expect(kinds).not.toContain('step');
    expect(kinds).not.toContain('info');
    wrapper.destroy();
  });

  it('releases its serial handle on disconnect', async () => {
    const wrapper = create();
    const transport = { disconnect: vi.fn().mockResolvedValue() };
    wrapper.vm.transport = transport; wrapper.vm.connected = true;
    await wrapper.vm.disconnect();
    expect(transport.disconnect).toHaveBeenCalledOnce();
    expect(wrapper.vm.connected).toBe(false); expect(wrapper.vm.loader).toBeNull();
    wrapper.destroy();
  });
});
