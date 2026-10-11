// verify_ui.mjs —— 用最小 DOM stub 跑 ui.js 渲染逻辑，确认首页关键节点会被正确填充
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dir = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dir, '..');

// ── 最小 DOM stub ──
const store = {};
function makeEl() {
  return {
    textContent: '', innerHTML: '',
    style: {}, dataset: {},
    setAttribute() {}, getAttribute() { return null; },
    classList: { toggle() {}, add() {}, remove() {}, contains() { return false; } },
    querySelector() { return null; },
    focus() {}, appendChild() {},
  };
}
global.document = {
  getElementById(id) { return store[id] || (store[id] = makeEl()); },
  querySelectorAll() { return []; },
  querySelector() { return null; },
  addEventListener() {},
  title: '__SITE__ | test',
};

const ui = await import('../docs/assets/js/ui.js');
const { computeAll } = await import('../docs/assets/js/compute.js');

const macro = JSON.parse(readFileSync(resolve(root, 'docs/data/macro.json'), 'utf8'));
const quotes = JSON.parse(readFileSync(resolve(root, 'docs/data/quotes.json'), 'utf8'));

const result = computeAll(macro, quotes);
ui.renderDashboard(result, {
  macroData: macro.data,
  quotes,
  backtest: null,
  sourceStatus: { macro: 'ok', quotes: 'ok', backtest: 'missing' },
  allDown: false,
  macroAsOf: '2026-10-06',
  quotesAsOf: quotes.asOf,
  backtestAsOf: null,
});

function check(name, got, expect) {
  const pass = String(got) === String(expect);
  console.log((pass ? 'PASS ' : 'FAIL ') + name + ' => "' + got + '"' + (pass ? '' : '  (期望 "' + expect + '")'));
  return pass;
}

let ok = true;
ok &= check('temp-value', store['temp-value'].textContent, '5.38');
ok &= check('position-value', store['position-value'].textContent, '5.3');
ok &= check('temp-label', store['temp-label'].textContent, '偏热');
ok &= check('clock has 下跌中继 active', store['clock'].innerHTML.includes('quadrant--active') && store['clock'].innerHTML.includes('下跌中继'), true);
ok &= check('scores 4 rows', (store['scores'].innerHTML.match(/class="score-row"/g) || []).length, 4);
ok &= check('quotes chips', (store['quotes-bar'].innerHTML.match(/class="chip"/g) || []).length, 9);
ok &= check('quotes amt has 亿', store['quotes-amt'].innerHTML.includes('亿'), true);
ok &= check('macro rows', (store['macro-tbody'].innerHTML.match(/<tr/g) || []).length, Object.keys(macro.data).length);
ok &= check('macro has 基线 badge (credit_yoy)', store['macro-tbody'].innerHTML.includes('基线'), true);
ok &= check('position-path template', store['position-path'].textContent.startsWith('温度仓位 5.6 成'), true);
// credit_yoy 已降级（asOf 2026-04-01 超 90 天）→ 宏观灯应为黄(降级基线)
ok &= check('light-macro state', store['light-macro'].dataset.state, 'warn');
ok &= check('last-updated', store['last-updated'].textContent, '最后更新：2026-10-11');

console.log('\nUI 渲染校验:', ok ? 'ALL PASS' : 'HAS FAIL');
process.exit(ok ? 0 : 1);
