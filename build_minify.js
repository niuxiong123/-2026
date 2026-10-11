#!/usr/bin/env node
// 由仓内 src/ 的真源 HTML 重新生成 docs/index.html
// 仅压缩内联 <script>（compress-only，不混淆变量名），HTML 结构原样保留
// 注意：terser 5.x 的 minify 是异步的，必须用 minify_sync
//
// ⚠️ 宪法级规则（2026-10-11 #2-C 决议）：
// 1. 真源 = 仓内 src/index_unobfuscated_*.html（取 mtime 最新一个），严禁再指向仓库外的 src_backup；
// 2. 每次改动请直接改仓内 src/ 真源，再跑本脚本重新生成 docs/；
// 3. 本脚本启动时先跑硬闸：真源缺少任一关键标记（线上修复/根治层标识）立即 ABORT，
//    防止用旧快照重建而回退线上已上线的修复。
const fs = require('fs');
const path = require('path');
const terser = require('C:/Users/76751/.workbuddy/binaries/node/workspace/node_modules/terser');

// ── 1. 定位仓内最新真源 ──
const srcDir = path.resolve(__dirname, 'src');
const candidates = fs.readdirSync(srcDir)
  .filter(f => /^index_unobfuscated_.*\.html$/.test(f))
  .map(f => path.join(srcDir, f));
if (!candidates.length) {
  console.error('硬闸 ABORT：src/ 下没有任何 index_unobfuscated_*.html 真源文件');
  process.exit(1);
}
const SRC = candidates.map(f => ({ f, m: fs.statSync(f).mtimeMs }))
  .sort((a, b) => b.m - a.m)[0].f;
console.log('真源: ' + SRC);

// ── 2. 硬闸：关键标记必须齐全，缺一即 ABORT ──
const REQUIRED_MARKS = [
  '已移除',                // P0 后台口令已清除
  'macroAlarm',            // 宏观失败告警
  'CROWD_CACHE_KEY',       // B5 localStorage 缓存
  'topBottomProbTrain',    // #7 OOS walk-forward
  'loadNeoMicro',          // #8 微观情绪
  'volAdj',                // #9 波动自适应
  'scoreMicro',            // #8 评分函数
];
let html = fs.readFileSync(SRC, 'utf8');
const missing = REQUIRED_MARKS.filter(k => !html.includes(k));
if (missing.length) {
  console.error('硬闸 ABORT：真源缺少关键标记（可能用旧快照重建，会回退线上修复）→ ' + missing.join(', '));
  process.exit(1);
}
console.log('硬闸通过：' + REQUIRED_MARKS.length + ' 个关键标记全部存活');

const DOC = path.resolve(__dirname, 'docs', 'index.html');
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
for (const key of [...REQUIRED_MARKS, 'marketTemp', 'envScore', 'envAdj', '财杀年', '4.5']) {
  if (!out.includes(key)) { console.error('自检失败：压缩后丢失 ' + key); process.exit(1); }
}
console.log('自检通过：关键标识全部存活');
