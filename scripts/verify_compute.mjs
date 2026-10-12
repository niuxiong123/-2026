// verify_compute.mjs —— 用真实数据跑 compute.js，打印关键数值并校验可复现
// 用法：node scripts/verify_compute.mjs
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { computeAll } from '../docs/assets/js/compute.js';

const __dir = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dir, '..');

function loadJson(p) {
  return JSON.parse(readFileSync(resolve(root, p), 'utf8'));
}

const macro = loadJson('docs/data/macro.json');
const quotes = loadJson('docs/data/quotes.json');

const run = () => computeAll(macro, quotes);

const a = run();
const b = run(); // 复现性：同一输入两次应逐位一致

console.log('=== 恒福丨水木清华 · compute.js 真数据验证 ===');
console.log('参考日 refDate      :', a.refDate);
console.log('四维分:');
console.log('  trend     :', a.scores.trend, '(子分:', JSON.stringify(a.scoresRaw.trend), ')');
console.log('  valuation :', a.scores.valuation, '(子分:', JSON.stringify(a.scoresRaw.valuation), ')');
console.log('  liquidity :', a.scores.liquidity, '(子分:', JSON.stringify(a.scoresRaw.liquidity), ')');
console.log('  sentiment :', a.scores.sentiment, '(子分:', JSON.stringify(a.scoresRaw.sentiment), ')');
console.log('temp              :', a.temp, '→', a.tempLabel);
console.log('positionTemp(成)  :', a.positionTemp);
console.log('硬约束:');
console.log('  creditCap       :', a.constraints.creditCap);
console.log('  resonanceCap    :', a.constraints.resonanceCap, 'reason=', a.constraints.resonanceReason);
console.log('  conservative ×  :', a.constraints.conservativeFactor, 'triggers=', JSON.stringify(a.constraints.triggers));
console.log('positionFinal(成) :', a.positionFinal);
console.log('牛熊钟            :', a.clock.quadrant, '—', a.clock.advice, `(x=${a.clock.x}, y=${a.clock.y})`);
console.log('降级字段数        :', a.degraded.length, a.degraded.length ? JSON.stringify(a.degraded) : '(无)');

// 复现校验
const same =
  a.temp === b.temp &&
  a.scores.trend === b.scores.trend &&
  a.scores.valuation === b.scores.valuation &&
  a.positionTemp === b.positionTemp &&
  a.positionFinal === b.positionFinal;
console.log('\n可复现性 (两次结果逐位一致):', same ? 'PASS' : 'FAIL');

// 合理性断言
const checks = [];
checks.push(['temp∈[0,10]', a.temp >= 0 && a.temp <= 10]);
checks.push(['四维∈[0,10]', [a.scores.trend, a.scores.valuation, a.scores.liquidity, a.scores.sentiment].every((x) => x >= 0 && x <= 10)]);
checks.push(['positionFinal∈[0,10]', a.positionFinal >= 0 && a.positionFinal <= 10]);
checks.push(['positionFinal≤positionTemp', a.positionFinal <= a.positionTemp + 1e-9]);
const allPass = checks.every((c) => c[1]);
console.log('合理性校验:', allPass ? 'PASS' : 'FAIL', JSON.stringify(checks));

console.log('\n摘要: temp=' + a.temp + ' / positionFinal=' + a.positionFinal + ' 成 / ' + a.clock.quadrant);
