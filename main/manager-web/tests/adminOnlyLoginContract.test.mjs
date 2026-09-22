import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import compiler from 'vue-template-compiler';
const source=fs.readFileSync(new URL('../src/views/login.vue',import.meta.url),'utf8');
test('admin login template compiles without registration and mobile routes',()=>{
 const sfc=compiler.parseComponent(source); const compiled=compiler.compile(sfc.template.content);
 assert.deepEqual(compiled.errors,[]);assert.match(sfc.template.content,/Pico 管理员登录/);
 assert.doesNotMatch(source,/goToRegister|goToForgetPassword|isMobileLogin|switchLoginType/);
});
test('old registration and recovery routes redirect to login',()=>{
 const router=fs.readFileSync(new URL('../src/router/index.js',import.meta.url),'utf8');
 for(const path of ['/register','/retrieve-password']) assert.match(router,new RegExp(`path: '${path}',[\\s\\S]*?redirect: '/login'`));
 assert.doesNotMatch(router,/import\('\.\.\/views\/(register|retrievePassword)\.vue'\)/);
});
