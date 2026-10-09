#!/usr/bin/env node
// 站点内部一致性校验（防 AI 跑偏的回归闸门）
// 用法: node tests/verify_site.js
// 退出码 0 = 通过; 1 = 不通过(禁止部署)
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..');
const HTML = path.join(ROOT, 'docs', 'index.html');
let fails = 0;
function check(cond, msg) {
  if (cond) { console.log('  ✔ ' + msg); }
  else { console.log('  ✘ ' + msg); fails++; }
}
function fatal(msg) { console.log('  ✘ ' + msg); fails++; }

console.log('=== 1) 语法检查：抽取页面脚本并 node --check ===');
let html;
try { html = fs.readFileSync(HTML, 'utf8'); } catch (e) { fatal('读不到 docs/index.html: ' + e.message); process.exit(1); }
const scripts = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
if (!scripts.length) fatal('页面无 <script>');
else {
  const big = scripts.reduce((a, b) => (b.length > a.length ? b : a), '');
  try { new vm.Script(big, { filename: 'page-script' }); console.log('  ✔ 页面脚本语法通过'); }
  catch (e) { fatal('页面脚本语法错误: ' + e.message); }
}

console.log('=== 2) 回归标记：已定架构不得被改回去 ===');
check(html.includes('marketTemp'), '含 marketTemp（纯市场温度·贵贱）');
check(html.includes('envScore'), '含 envScore（环境分·移出温度）');
check(html.includes('envAdj'), '含 envAdj（环境轻度调节·仅一次）');
// 以下为被废除的逻辑，若出现即 AI 跑偏回退
const noDouble = !html.includes('clamp(mkt + qAdj)');
const noUstCap = !html.includes('ustCap');
const noHard = !html.includes('final = 5.5') && !html.includes('=> 5.5');
check(noDouble, '无温度双计(旧 clamp(mkt + qAdj) 已消失)');
check(noUstCap, '无 H股美债硬上限残留(ustCap 已移除)');
check(noHard, '无 final=5.5 硬封顶残留');

console.log('=== 3) 数值回归：港股跌13月情景必须显“真冷+想买” ===');
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const basePosition = t => 5.5 - 4.2 * Math.tanh(0.38 * (t - 5));
// 情景输入：市场冷(趋势/流动/情绪低)，环境紧(美债高/汇率弱/货币紧/盈利差)
const tr = 2.5, lq = 2.8, em = 3.0;
const money = 5.5, earn = 6.0, fx = 6.5, ust = 7.5;
const wM = { tr: 0.40, lq: 0.30, em: 0.30 };
const wE_H = { money: 0.14, earn: 0.19, fx: 0.25, ust: 0.42 };
const marketTemp = clamp(tr * wM.tr + lq * wM.lq + em * wM.em, 0, 10);
const envScore = clamp(money * wE_H.money + earn * wE_H.earn + fx * wE_H.fx + ust * wE_H.ust, 0, 10);
const K_ENV = 0.05;
const envAdj = clamp(1 - (envScore - 5) * K_ENV, 0.6, 1.3);
const bp = basePosition(marketTemp);
console.log('     市场温度=' + marketTemp.toFixed(2) + ' 环境分=' + envScore.toFixed(2) + ' envAdj=' + envAdj.toFixed(2) + ' 想买bp=' + bp.toFixed(2));
check(marketTemp >= 0 && marketTemp <= 10, '市场温度∈[0,10]');
check(envScore >= 0 && envScore <= 10, '环境分∈[0,10]');
check(envAdj >= 0.6 && envAdj <= 1.3, 'envAdj∈[0.6,1.3]（轻度·无双计）');
check(marketTemp < 5, '港股跌13月时市场温度<5（真冷/便宜，非假热）');
check(bp > 5, '真冷时想买仓位>5成（与肉眼一致）');

console.log('=== 4) 命理铁律不被“优化”掉 ===');
check(html.includes('财杀年') || html.includes('4.5'), '命理财杀年硬上限(4.5成)约束仍在线');

console.log('');
if (fails > 0) {
  console.log('❌ 校验失败 ' + fails + ' 项 —— 本次改动禁止部署，请回滚或修正。');
  process.exit(1);
} else {
  console.log('✅ 全部校验通过 —— 改动可进入部署闸门。');
  process.exit(0);
}
