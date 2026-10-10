#!/usr/bin/env node
// 由 src_backup 的未混淆 HTML 重新生成 docs/index.html
// 仅压缩内联 <script>（compress-only，不混淆变量名），HTML 结构原样保留
// 注意：terser 5.x 的 minify 是异步的，必须用 minify_sync
const fs = require('fs');
const path = require('path');
const terser = require('C:/Users/76751/.workbuddy/binaries/node/workspace/node_modules/terser');

const SRC = path.resolve(__dirname, '..', 'src_backup', 'index_unobfuscated_2026-10-10.js.html');
const DOC = path.resolve(__dirname, 'docs', 'index.html');

let html = fs.readFileSync(SRC, 'utf8');
const re = /<script([^>]*)>([\s\S]*?)<\/script>/g;
const scripts = [...html.matchAll(re)];
console.log('发现 <script> 块数量: ' + scripts.length);

let out = html;
for (const m of scripts) {
  const attrs = m[1], body = m[2];
  if (!body.trim()) continue;
  const r = terser.minify_sync(body, { compress: true, mangle: false });
  if (r.error) { console.error('terser 错误: ' + r.error); process.exit(1); }
  if (!r.code || r.code.length < 1000) { console.error('压缩结果异常(len=' + (r.code||'').length + ')，中止'); process.exit(1); }
  const block = '<script' + attrs + '>' + r.code + '</script>';
  out = out.replace(m[0], block);
  console.log('script 压缩: ' + body.length + ' -> ' + r.code.length + ' 字符');
}
fs.writeFileSync(DOC, out);
console.log('已写入 ' + DOC + '  体积 ' + (out.length / 1024).toFixed(1) + ' KB');
// 自检：关键标识必须存活（verify_site.js 的闸门依赖它们）
for (const key of ['marketTemp', 'envScore', 'envAdj', '财杀年', '4.5', 'renderAlloc', 'allocBody']) {
  if (!out.includes(key)) { console.error('自检失败：压缩后丢失 ' + key); process.exit(1); }
}
console.log('自检通过：关键标识全部存活');
