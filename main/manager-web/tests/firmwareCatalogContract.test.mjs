import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const compiler=require('vue-template-compiler');
const catalog=JSON.parse(fs.readFileSync(new URL('../src/generated/firmwareCatalog.json',import.meta.url)));
const source=fs.readFileSync(new URL('../src/views/FirmwareCenter.vue',import.meta.url),'utf8');
test('hardware directory is available without a running builder',()=>{
 assert.ok(catalog.boards.length>100);assert.ok(catalog.languages.includes('zh-CN'));
 assert.ok(!source.slice(source.indexOf('async loadBoards(){'),source.indexOf('async startBuild(){')).includes('fetch('));
});
test('board ids and screen defaults match upstream variant definitions',()=>{
 const bread=catalog.boards.filter(b=>b.board==='bread-compact-wifi');
 assert.ok(bread.length>=2);
 for(const b of bread){const display=b.build_options.find(o=>o.key==='display_model');assert.ok(display.choices.some(c=>c.value===display.default));}
 assert.equal(bread.find(b=>b.name==='bread-compact-wifi').build_options.find(o=>o.key==='display_model').default,'OLED_SSD1306_128X32');
 assert.ok(catalog.boards.some(b=>b.board==='folotoy/ai-passport'&&b.target==='esp32c3'));
});
test('view has separate board type, board id and actual screen option controls',()=>{
 assert.match(source,/v-model="boardType"/);assert.match(source,/v-model="form.board"/);assert.match(source,/v-model="form.options.display_model"/);
 const template=compiler.parseComponent(source).template.content;
 assert.deepEqual(compiler.compile(template).errors,[]);
});
