// fetcher.js —— 三 JSON 拉取 + 降级 + 内置基线快照常量
// 站点：牛熊自检台（docs/ 根，GitHub Pages）
// 规范依据：site-spec.md §5.1 / §5.4 / §6.8 ；design-spec.md §2.7
//
// 职责边界（与 compute.js 分工，避免重复逻辑）：
//   - 本文件负责「文件级可用性」：每个 JSON 是否拿到（含 ?t 时间戳防缓存、5s 超时、
//     404/解析失败降级），以及内置基线快照常量（用 macro.json 当前 29 个 value 作为基线）。
//   - compute.js 负责「字段级降级 + 全部数学 + 陈旧惩罚」，字段级基线值取自本文件的
//     BASELINE_SNAPSHOT，常量单一来源，不重复定义。

// ─────────────────────────────────────────────────────────────
// 内置基线快照：macro.json 当前 29 个 value（site-spec §5.1 / §6.8③）
// 字段名与现有 macro.json 完全一致，一个字符都不许改。
// ─────────────────────────────────────────────────────────────
export const BASELINE_SNAPSHOT = {
  pmi: 50.1,
  m1_yoy: 4.1,
  m2_yoy: 8,
  credit_yoy: 8.18,
  lpr1y: 3,
  cn10y: 1.6822,
  us10y: 5.31,
  hs300_pe: 14.34,
  hs300_pe_pct: 82.5,
  hs300_pb_pct: 37.8,
  hsi_pe_pct: 50.6,
  erp: 5.291,
  margin_yi: 25485,
  northbound: 0,
  breadth_up: 46.4,
  ah_premium: 140,
  amt_yi: 17028,
  oil_brent: 97.82,
  dxy: 101.87,
  us_unemploy: 4.2,
  nasdaq_pct: 3.66,
  re_yoy: -2.15,
  vix: 21.67,
  trade_balance: 982.4,
  ai_bubble: 7.1,
  hormuz_risk: 6.5,
  paths_lit: 6.2,
  win_proximity: 4.1,
  china_fragile: 8.2,
};

// macro.json 全部字段顺序（用于明细表渲染与基线填充，保证 29 项齐全）
export const MACRO_KEYS = Object.keys(BASELINE_SNAPSHOT);

// 行情条所用的 9 个指数 + 成交额映射（quotes.json 消费约定，site-spec §5.1）
export const QUOTE_FIELDS = [
  { key: 'hs300', label: '沪深300' },
  { key: 'sh', label: '上证' },
  { key: 'sz', label: '深成指' },
  { key: 'cyb', label: '创业板' },
  { key: 'kc', label: '科创50' },
  { key: 'hsi', label: '恒生' },
  { key: 'hstech', label: '恒生科技' },
  { key: 'ndx', label: '纳指' },
  { key: 'vix', label: 'VIX' },
];

// ─────────────────────────────────────────────────────────────
// 工具
// ─────────────────────────────────────────────────────────────
function cacheBust() {
  return '?t=' + Date.now();
}

async function loadJSON(path, timeoutMs = 5000) {
  const ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
  let timer = null;
  if (ctrl) timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(path + cacheBust(), {
      signal: ctrl ? ctrl.signal : undefined,
      cache: 'no-store',
    });
    if (!res.ok) throw new Error('E_FETCH_404');
    const json = await res.json();
    return { ok: true, data: json, error: null };
  } catch (e) {
    return {
      ok: false,
      data: null,
      error: e && e.name === 'AbortError' ? 'E_TIMEOUT' : 'E_PARSE',
    };
  } finally {
    if (timer) clearTimeout(timer);
  }
}

// 文件级失败 → 用基线快照填满整份 macro.data（逐项标记 degraded）
export function baselineMacroData() {
  const data = {};
  for (const k of MACRO_KEYS) {
    data[k] = {
      value: BASELINE_SNAPSHOT[k],
      asOf: null,
      src: '基线(内置快照)',
      degraded: true,
    };
  }
  return data;
}

// ─────────────────────────────────────────────────────────────
// 入口：并行拉取三 JSON，返回已解析（含文件级降级）的结果
// ─────────────────────────────────────────────────────────────
export async function fetchAll() {
  const [m, q, b] = await Promise.all([
    loadJSON('data/macro.json'),
    loadJSON('data/quotes.json'),
    loadJSON('data/backtest.json'),
  ]);

  const sourceStatus = {
    macro: m.ok ? 'ok' : 'missing',
    quotes: q.ok ? 'ok' : 'missing',
    backtest: b.ok ? 'ok' : 'missing',
  };

  // macro：文件级失败 → 基线填满；否则取 data 内层
  let macroData;
  if (m.ok && m.data && m.data.data && typeof m.data.data === 'object') {
    macroData = m.data.data;
  } else {
    macroData = baselineMacroData();
    sourceStatus.macro = 'missing';
  }

  // quotes：文件级失败 → null（compute/ui 走基线降级，P1 可接腾讯 JSONP 兜底）
  const quotes = q.ok && q.data ? q.data : null;

  // backtest：失败 → null（首页不依赖；history 页显示空态）
  const backtest = b.ok && Array.isArray(b.data) ? b.data : null;

  const allDown = !m.ok && !q.ok && !b.ok;

  return {
    macroData,
    quotes,
    backtest,
    sourceStatus,
    allDown,
    raw: { m, q, b },
  };
}

// 给「刷新按钮」复用：仅重新拉取，不重复定义逻辑
export { loadJSON };
