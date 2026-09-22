import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const view = fs.readFileSync('src/views/FirmwareCenter.vue', 'utf8');

test('history panel fetches the authenticated /builds endpoint', () => {
  assert.match(view, /\/pico\/firmware-builder\/builds/);
  assert.match(view, /Authorization:'Bearer '\+token/);
});

test('history exposes download for both full and OTA firmware', () => {
  assert.match(view, /downloadBuild\(s\.row,'full'\)/);
  assert.match(view, /downloadBuild\(s\.row,'ota'\)/);
  assert.match(view, /merged-binary\.bin/);
  assert.match(view, /'pico\.bin'/);
});

test('history never renders raw local filesystem paths', () => {
  assert.doesNotMatch(view, /\/Users\/shengzhoukong/);
  assert.doesNotMatch(view, /firmware-builds/);
});

test('failed builds show an error rather than a download button', () => {
  assert.match(view, /s\.row\.status==='failed'/);
});

test('ambiguous OTA availability is guarded by per-file availability', () => {
  assert.match(view, /hasFile\(s\.row,'pico\.bin'\)/);
});

test('history refreshes after a successful build', () => {
  assert.match(view, /this\.job\.status==='success'\)\{await this\.loadManifestForJob\(\);this\.loadHistory\(\)/);
});
