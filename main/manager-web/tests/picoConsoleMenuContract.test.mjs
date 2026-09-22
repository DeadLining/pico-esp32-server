import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import compiler from 'vue-template-compiler';

const read = (p) => fs.readFileSync(new URL(`../src/${p}`, import.meta.url), 'utf8');

const header = read('components/HeaderBar.vue');
const router = read('router/index.js');
const modelConfig = read('views/ModelConfig.vue');
const knowledgeBase = read('views/KnowledgeBaseManagement.vue');

const headerTemplate = header.slice(0, header.indexOf('</template>'));
const navStart = headerTemplate.indexOf('header-center');
const navEnd = headerTemplate.indexOf('header-right');
const nav = headerTemplate.slice(navStart, navEnd);

test('console navigation keeps only the approved entries', () => {
  for (const key of [
    'header.deviceManagement',
    'header.voiceCloneManagement',
    'header.modelConfig',
    'header.knowledgeBase',
    'header.addressBook',
    'header.agentTemplate',
    'header.systemSettings',
  ]) {
    assert.match(nav, new RegExp(key.replace('.', '\\.')), `missing nav entry ${key}`);
  }
  assert.match(nav, /固件中心/);
  assert.doesNotMatch(nav, /paramDictionary/, 'param dictionary dropdown must be removed');
});

test('removed console menus are no longer routable pages', () => {
  for (const path of [
    '/user-management',
    '/params-management',
    '/server-side-management',
    '/ota-management',
    '/dict-management',
    '/provider-management',
    '/feature-management',
    '/replacement-word-management',
  ]) {
    const importPattern = new RegExp(`import\\('\\.\\.\\/views\\/[A-Za-z]+\\.vue'\\)`);
    assert.doesNotMatch(router, new RegExp(`path: '${path}'[\\s\\S]{0,80}?${importPattern.source}`));
    assert.match(router, new RegExp(`path: '${path}', redirect`), `missing redirect for ${path}`);
  }
});

test('model configuration keeps exactly the six approved model types', () => {
  const menu = modelConfig.slice(modelConfig.indexOf('nav-panel'), modelConfig.indexOf('content-area'));
  const tabs = [...menu.matchAll(/el-menu-item index="(\w+)"/g)].map((m) => m[1]);
  assert.deepEqual(tabs, ['vad', 'asr', 'llm', 'intent', 'tts', 'memory']);
  assert.doesNotMatch(menu, /index="vllm"/);
  assert.doesNotMatch(menu, /index="rag"/);
});

test('RAG model configuration lives under knowledge base management', () => {
  assert.match(knowledgeBase, /knowledgeBaseManagement\.ragConfig/);
  assert.match(knowledgeBase, /getRAGModels/);
  assert.match(knowledgeBase, /ModelEditDialog/);
  const sfc = compiler.parseComponent(knowledgeBase);
  assert.deepEqual(compiler.compile(sfc.template.content).errors, []);
});

test('effective model follows agent binding rather than is_default', () => {
  assert.match(modelConfig, /boundModelId\(\)/);
  assert.match(modelConfig, /fieldByType/);
  for (const field of ['vadModelId', 'asrModelId', 'llmModelId', 'intentModelId', 'ttsModelId', 'memModelId']) {
    assert.match(modelConfig, new RegExp(field), `missing binding field ${field}`);
  }
  // 绑定优先：先按 boundModelId 查找，未命中才回退 is_default
  const effective = modelConfig.slice(modelConfig.indexOf('effectiveModel()'), modelConfig.indexOf('presetModels()'));
  assert.match(effective, /this\.boundModelId/);
  assert.ok(
    effective.indexOf('this.boundModelId') < effective.indexOf('isDefault === 1'),
    'agent binding must be consulted before is_default fallback',
  );
  // 必须通过 /agent/{id} 拿完整绑定，而不是只用 /agent/list 的名称
  assert.match(modelConfig, /getDeviceConfig/);
});

test('preset models are collapsed behind an explicit toggle', () => {
  assert.match(modelConfig, /showAll: false/);
  assert.match(modelConfig, /showPresets/);
  assert.match(modelConfig, /hidePresets/);
  assert.match(modelConfig, /presetModels\(\)/);
});

test('role config routes vision and chat summary through the main LLM', () => {
  const roleConfig = read('views/roleConfig.vue');
  const templateQuickConfig = read('views/TemplateQuickConfig.vue');
  const agentTemplateManagement = read('views/AgentTemplateManagement.vue');
  const snapshotDialog = read('components/AgentSnapshotDialog.vue');

  // 角色配置只暴露 VAD/ASR/LLM/Intent/Memory/TTS 六个槽位
  const models = roleConfig.slice(
    roleConfig.indexOf('models: ['),
    roleConfig.indexOf('],', roleConfig.indexOf('models: [')),
  );
  for (const field of ['vadModelId', 'asrModelId', 'llmModelId', 'intentModelId', 'memModelId', 'ttsModelId']) {
    assert.match(models, new RegExp(field), `missing model slot ${field}`);
  }
  assert.doesNotMatch(models, /slmModelId/, 'SLM slot must not be user-configurable');
  assert.doesNotMatch(models, /vllmModelId/, 'VLLM slot must not be user-configurable');

  // 保存时会话总结固定复用主语言模型
  assert.match(roleConfig, /slmModelId:\s*this\.form\.model\.llmModelId/);

  // 模板页不再写死独立的视觉模型
  for (const sfc of [templateQuickConfig, agentTemplateManagement]) {
    assert.doesNotMatch(sfc, /VLLM_ChatGLMVLLM/, 'template must not pin a separate vision model');
    assert.doesNotMatch(sfc, /vllmModelId/);
  }

  // 快照展示：会话总结按 LLM 解析，视觉字段不再单独解析
  assert.match(snapshotDialog, /slmModelId:\s*"LLM"/);
  assert.doesNotMatch(snapshotDialog, /vllmModelId:\s*"VLLM"/);
});
