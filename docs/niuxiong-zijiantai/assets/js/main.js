// main.js —— 入口：fetch → compute → render；刷新按钮；移动抽屉导航
// 站点：恒福丨水木清华（首页仪表盘）
// === 2026-10-24 B1 修改 ===
// 1. 并行 fetch stockbond.json（四约束链 Python 端生成器输出）
// 2. 仓位 hero 优先显示 final_position（50.00 成），旧温度模型降级副面板
// 铁律：不动 compute.js 引擎函数、不动 fetcher.js 四 JSON 契约

import { fetchAll, loadJSON } from './fetcher.js';
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
  // 并行拉五源：四 JSON（原 fetcher）+ stockbond.json（四约束链）
  const [ctxRaw, sbRes] = await Promise.all([
    fetchAll(),
    loadJSON('data/stockbond.json'),
  ]);

  // stockbond.json 解析（文件级失败 → 后续降级处理）
  let stockbond = null;
  if (sbRes.ok && sbRes.data && sbRes.data.latest) {
    stockbond = {
      finalPosition: sbRes.data.latest.final_position,
      reason: sbRes.data.latest.final_reason,
      date: sbRes.data.latest.date,
      pct: sbRes.data.latest.pct,
      posLadder: sbRes.data.latest.pos,
      kellyCap: sbRes.data.latest.kelly_cap,
      dkTriggered: sbRes.data.latest.dk_triggered,
      mysticOpen: sbRes.data.latest.mystic_open,
      mysticCap: sbRes.data.latest.mystic_cap,
      generatedAt: sbRes.data.generated_at,
      source: sbRes.data.source,
      degraded: false,
    };
  } else {
    stockbond = { degraded: true };
  }

  // 旧温度引擎（不动，铁律）
  const result = computeAll(ctxRaw.macroData, ctxRaw.quotes);

  ui.renderDashboard(result, {
    ...ctxRaw,
    macroAsOf: maxAsOf(ctxRaw.macroData),
    quotesAsOf: ctxRaw.quotes ? ctxRaw.quotes.asOf : null,
    backtestAsOf: latestBacktestDate(ctxRaw.backtest),
    stockbond,  // B1 新增：四约束链结果，渲染层优先用
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
