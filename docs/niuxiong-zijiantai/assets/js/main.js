// main.js —— 入口：fetch → compute → render；刷新按钮；移动抽屉导航
// 站点：牛熊自检台（首页仪表盘）
import { fetchAll } from './fetcher.js';
import { computeAll } from './compute.js';
import * as ui from './ui.js';

function maxAsOf(data) {
  let max = null;
  for (const k in data) {
    const a = data[k] && data[k].asOf;
    if (a && (!max || a > max)) max = a;
  }
  return max;
}
function latestBacktestDate(b) {
  if (!b || !b.length) return null;
  return b[b.length - 1].date;
}

let refreshing = false;
async function run() {
  if (refreshing) return;
  const ctxRaw = await fetchAll();
  const result = computeAll(ctxRaw.macroData, ctxRaw.quotes);
  ui.renderDashboard(result, {
    ...ctxRaw,
    macroAsOf: maxAsOf(ctxRaw.macroData),
    quotesAsOf: ctxRaw.quotes ? ctxRaw.quotes.asOf : null,
    backtestAsOf: latestBacktestDate(ctxRaw.backtest),
  });
}

// 刷新按钮
function wireRefresh() {
  const btn = document.getElementById('refresh-btn');
  if (!btn) return;
  btn.addEventListener('click', async () => {
    if (refreshing) return;
    refreshing = true;
    btn.setAttribute('aria-busy', 'true');
    const label = btn.querySelector('.btn__label');
    const prev = label ? label.textContent : btn.textContent;
    if (label) label.textContent = '刷新中…';
    btn.disabled = true;
    try {
      await run();
    } finally {
      refreshing = false;
      btn.removeAttribute('aria-busy');
      btn.disabled = false;
      if (label) label.textContent = prev;
    }
  });
}

// 移动抽屉导航
function wireDrawer() {
  const menuBtn = document.getElementById('menu-btn');
  const drawer = document.getElementById('nav-drawer');
  const overlay = document.getElementById('overlay');
  if (!menuBtn || !drawer) return;
  const close = () => {
    drawer.classList.remove('open');
    if (overlay) overlay.classList.remove('open');
    menuBtn.setAttribute('aria-expanded', 'false');
    menuBtn.focus();
  };
  const open = () => {
    drawer.classList.add('open');
    if (overlay) overlay.classList.add('open');
    menuBtn.setAttribute('aria-expanded', 'true');
    const first = drawer.querySelector('a, button');
    if (first) first.focus();
  };
  menuBtn.addEventListener('click', () => {
    if (drawer.classList.contains('open')) close();
    else open();
  });
  if (overlay) overlay.addEventListener('click', close);
  const closeBtn = document.getElementById('drawer-close');
  if (closeBtn) closeBtn.addEventListener('click', close);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && drawer.classList.contains('open')) close();
  });
}

document.addEventListener('DOMContentLoaded', () => {
  ui.applySiteName();
  wireRefresh();
  wireDrawer();
  run();
});
