// ui.js —— 渲染层（温度卡/仓位卡/牛熊钟/四维/行情条/明细表/状态灯/标灰）
// 站点：恒福丨水木清华。规范依据：design-spec.md + content-plan.md 首页区块顺序。
import { QUOTE_FIELDS, BASELINE_SNAPSHOT } from './fetcher.js';

export const SITE_NAME = '恒福丨水木清华';

// macro 字段中文名（明细表 / 可读标签）
const FIELD_LABELS = {
  pmi: 'PMI', m1_yoy: 'M1 同比', m2_yoy: 'M2 同比', credit_yoy: '社融存量同比',
  lpr1y: 'LPR(1年)', cn10y: '中债10年收益率', us10y: '美债10年收益率',
  hs300_pe: '沪深300 PE', hs300_pe_pct: '沪深300 PE 分位', hs300_pb_pct: '沪深300 PB 分位',
  hsi_pe_pct: '恒生 PE 分位', erp: '股债性价比 ERP', margin_yi: '两融余额',
  northbound: '北向资金', breadth_up: '上涨家数占比', ah_premium: 'AH 溢价',
  amt_yi: '两市成交额', oil_brent: '布伦特油价', dxy: '美元指数',
  us_unemploy: '美国失业率', nasdaq_pct: '纳指20日%', re_yoy: '70城二手房同比',
  vix: 'VIX 波动率', trade_balance: '贸易帐', ai_bubble: 'AI 泡沫度',
  hormuz_risk: '霍尔木兹风险', paths_lit: '地缘紧张度', win_proximity: '真实压力指数',
  china_fragile: '地产脆弱度',
};

const $ = (id) => document.getElementById(id);

function fmtNum(v) {
  if (v == null) return '--';
  if (typeof v !== 'number') return String(v);
  const abs = Math.abs(v);
  if (abs >= 1000) return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
  return (Math.round(v * 100) / 100).toString();
}
function fmtPct(v) {
  if (v == null) return '--';
  const s = v > 0 ? '+' : '';
  return s + (Math.round(v * 100) / 100).toFixed(2) + '%';
}
function dirClass(v) {
  if (v == null || Math.abs(v) < 0.005) return 'flat';
  return v > 0 ? 'up' : 'down';
}
function dirArrow(v) {
  if (v == null || Math.abs(v) < 0.005) return '—';
  return v > 0 ? '▲' : '▼';
}
function srDir(v) {
  if (v == null || Math.abs(v) < 0.005) return '平';
  return v > 0 ? '上涨' : '下跌';
}
function scoreColor(score) {
  if (score < 2.5) return 'var(--score-cold)';
  if (score < 5) return 'var(--score-mid)';
  if (score < 7.5) return 'var(--score-warm)';
  return 'var(--score-hot)';
}
function tempPill(temp) {
  if (temp <= 3) return { cls: 'pill--cold', text: '偏冷·结构性机会' };
  if (temp < 5) return { cls: 'pill--neutral', text: '中性' };
  if (temp < 7) return { cls: 'pill--warm', text: '偏热' };
  return { cls: 'pill--hot', text: '过热·减仓' };
}

// ── 站点名注入（前端不硬编码，统一常量） ──
export function applySiteName() {
  const els = document.querySelectorAll('[data-site-name]');
  els.forEach((el) => { el.textContent = el.getAttribute('data-site-name') || SITE_NAME; });
  document.title = document.title.replace('__SITE__', SITE_NAME);
}

// ── 状态灯（§2.7） ──
export function renderStatusLights(status, info) {
  setLight('light-macro', status.macro, info.macroAsOf, info.macroDegraded, '宏观');
  setLight('light-quotes', status.quotes, info.quotesAsOf, false, '行情');
  setLight('light-backtest', status.backtest, info.backtestAsOf, status.backtest === 'missing', '回测');
}
function setLight(id, state, asOf, degraded, label) {
  const el = $(id);
  if (!el) return;
  let st;
  if (state === 'missing') st = 'down';
  else if (state === 'invalid' || degraded) st = 'warn';
  else st = 'ok';
  el.dataset.state = st;
  const today = new Date().toISOString().slice(0, 10);
  let stateTxt;
  if (st === 'ok') {
    stateTxt = asOf === today ? '今日已更新' : `已更新（截至 ${asOf || '—'}）`;
  } else if (st === 'warn') {
    stateTxt = '基线值' + (asOf ? `（截至 ${asOf}）` : '');
  } else {
    stateTxt = '缺失';
  }
  // 无障碍修复：generic 角色的 span 禁止命名，读屏会忽略 aria-label；
  // 改为外层 role="img" + 可聚焦 + 完整播报文本，圆点纯装饰（aria-hidden）。
  el.setAttribute('role', 'img');
  el.setAttribute('tabindex', '0');
  el.setAttribute('aria-label', `${label}数据源：${stateTxt}`);
  const dot = el.querySelector('.dot');
  if (dot) {
    dot.setAttribute('aria-hidden', 'true');
    dot.setAttribute('title', `${label}：${stateTxt}`);
  }
}

// ── 全站降级黄条（§5.11） ──
export function showAllDown(show) {
  const el = $('alert-warn');
  if (el) el.style.display = show ? 'flex' : 'none';
}

// ── 行情条（§5.5） ──
export function renderQuotes(quotes, macroData) {
  const bar = $('quotes-bar');
  const amtEl = $('quotes-amt');
  if (!bar) return;
  const degraded = !quotes;
  bar.classList.toggle('quotes--degraded', degraded);

  const chips = QUOTE_FIELDS.map((f) => {
    const q = quotes && quotes[f.key] ? quotes[f.key] : null;
    if (!q) {
      return `<div class="chip"><span class="chip__name">${f.label}</span>
        <span class="chip__price tabular">--</span>
        <span class="chip__pct flat">--<span class="sr-only">无数据</span></span></div>`;
    }
    const cls = dirClass(q.pct);
    const arrow = dirArrow(q.pct);
    const sr = srDir(q.pct) + (q.pct != null ? Math.abs(q.pct).toFixed(2) + '%' : '');
    return `<div class="chip"><span class="chip__name">${f.label}</span>
      <span class="chip__price tabular">${fmtNum(q.price)}</span>
      <span class="chip__pct ${cls}">${arrow} ${fmtPct(q.pct)}<span class="sr-only">${sr}</span></span></div>`;
  }).join('');

  bar.innerHTML = chips;

  // 成交额：实时取 quotes.amtTotalYi；失败时取 macro.amt_yi 基线并标灰
  let amt = quotes && quotes.amtTotalYi != null ? quotes.amtTotalYi : null;
  if (amt == null && macroData && macroData.amt_yi) amt = macroData.amt_yi.value;
  if (amtEl) {
    amtEl.innerHTML = degraded
      ? `成交额 <b>${fmtNum(amt)}</b> 亿 <span class="badge badge--baseline">基线</span>`
      : `成交额 <b>${fmtNum(amt)}</b> 亿`;
  }
}

// ── 牛熊温度大卡（§2.5 / content-plan ③） ──
export function renderTemp(result) {
  const val = $('temp-value');
  const fill = $('temp-fill');
  const slider = $('temp-slider');
  const label = $('temp-label');
  const meter = $('temp-meter');
  if (val) val.textContent = result.temp.toFixed(2);
  const pct = Math.max(0, Math.min(100, (result.temp / 10) * 100));
  // 遮罩式渲染：渐变铺在轨道全宽，fill 从右侧盖住未达到部分（原实现把整条渐变压进左侧，读数失真）
  if (fill) fill.style.width = (100 - pct) + '%';
  if (slider) slider.style.left = pct + '%';
  const p = tempPill(result.temp);
  if (label) {
    label.className = 'pill ' + p.cls;
    label.textContent = p.text;
  }
  if (meter) {
    meter.setAttribute('aria-valuenow', result.temp.toFixed(2));
    meter.setAttribute('aria-label', `牛熊温度 ${result.temp.toFixed(2)}，满分 10，${p.text}`);
  }
}

// ── 今日建议仓位大卡（content-plan ④，固定话术模板） ──
export function renderPosition(result) {
  const val = $('position-value');
  const path = $('position-path');
  if (val) val.textContent = result.positionFinal.toFixed(1);
  if (path) {
    const capped = Math.min(result.positionTemp, result.constraints.creditCap, result.constraints.resonanceCap);
    // 归因修复：原实现只看共振约束的 reason，信用约束真正生效时会误显示「卡在：不约束」
    const caps = [
      { v: result.positionTemp, why: '温度仓位（未触硬约束）' },
      { v: result.constraints.creditCap, why: '信用约束·社融同比' },
      { v: result.constraints.resonanceCap, why: result.constraints.resonanceReason || '共振约束' },
    ];
    const binder = caps.reduce((m, x) => (x.v < m.v ? x : m), caps[0]);
    path.textContent =
      `温度仓位 ${result.positionTemp.toFixed(1)} 成 → ` +
      `硬约束取 min ${capped.toFixed(1)}（卡在：${binder.why}）→ ` +
      `保守系数 ×${result.constraints.conservativeFactor.toFixed(2)}`;
  }
}

// ── 实时温度走势折线图（首页新增；第⑤步 item⑤：叠加真实日度序列） ──
export function renderTempTrendChart(backtest, currentTemp, currentDateStr, daily) {
  const canvas = $('tempTrendChart');
  if (!canvas || typeof window.Chart === 'undefined') return;
  if (canvas._chart) { canvas._chart.destroy(); canvas._chart = null; }
  const ctx = canvas.getContext('2d');

  const points = [];
  if (Array.isArray(backtest)) {
    backtest.forEach((r) => {
      if (r && typeof r.tempAdj === 'number') {
        points.push({ x: r.date, y: r.tempAdj });
      }
    });
  }
  const today = currentDateStr || new Date().toISOString().slice(0, 10);
  if (typeof currentTemp === 'number') {
    points.push({ x: today, y: currentTemp });
  }

  // 真实日度温度（akshare 管线启用后每日追加；≥2 点才画，否则只画月度历史）
  let dailyDataset = null;
  if (Array.isArray(daily) && daily.length >= 2) {
    dailyDataset = {
      label: '真实日度温度（akshare 管线）',
      data: daily.map((r) => ({ x: r.date, y: r.temp })),
      borderColor: '#da3633',
      backgroundColor: '#da3633',
      borderWidth: 2,
      pointRadius: 2.5,
      pointHoverRadius: 5,
      tension: 0.2,
      fill: false,
      order: 0,
    };
  }

  const cold = '#3fb950';
  const mid = '#d29922';
  const warm = '#db6d28';
  const hot = '#da3633';
  const pointColor = (context) => {
    const v = context.raw && typeof context.raw.y === 'number' ? context.raw.y : context.raw;
    if (v == null) return '#8b949e';
    if (v < 2.5) return cold;
    if (v < 5) return mid;
    if (v < 7.5) return warm;
    return hot;
  };

  const chart = new window.Chart(ctx, {
    type: 'line',
    data: {
      datasets: (dailyDataset ? [dailyDataset] : []).concat([{
        label: '温度',
        data: points,
        borderWidth: 2,
        tension: 0.3,
        fill: true,
        pointRadius: 3,
        pointHoverRadius: 6,
        pointBackgroundColor: pointColor,
        pointBorderColor: '#ffffff',
        pointBorderWidth: 1,
        borderColor: hot,
        backgroundColor: (context) => {
          const c = context.chart;
          const { ctx: c2, chartArea } = c;
          if (!chartArea) return null;
          const g = c2.createLinearGradient(0, chartArea.bottom, 0, chartArea.top);
          g.addColorStop(0, 'rgba(63,185,80,0.12)');
          g.addColorStop(0.35, 'rgba(210,153,34,0.15)');
          g.addColorStop(0.65, 'rgba(219,109,40,0.18)');
          g.addColorStop(1, 'rgba(218,54,51,0.22)');
          return g;
        },
        segment: {
          borderColor: (seg) => {
            const v = (seg.p0.parsed.y + seg.p1.parsed.y) / 2;
            if (v < 2.5) return cold;
            if (v < 5) return mid;
            if (v < 7.5) return warm;
            return hot;
          }
        }
      }])
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: (items) => items[0].raw.x,
            label: (item) => `温度 ${item.parsed.y.toFixed(2)}`
          }
        }
      },
      scales: {
        x: {
          type: 'category',
          ticks: { maxTicksLimit: 12, color: '#656d76' },
          grid: { display: false }
        },
        y: {
          min: 0,
          max: 10,
          title: { display: true, text: '温度 (0-10)', color: '#656d76' },
          ticks: { stepSize: 1, color: '#656d76' },
          grid: { color: 'rgba(208,215,222,0.5)' }
        }
      }
    }
  });
  canvas._chart = chart;
}

// ── 牛熊钟（§6.7 / content-plan ⑤） ──
export function renderClock(result) {
  const wrap = $('clock');
  if (!wrap) return;
  const q = result.clock;
  const cells = [
    { id: '熊末·黄金坑', cond: '趋势冷 + 估值冷', advice: '可分批建仓，不追涨', cls: 'cold' },
    { id: '下跌中继', cond: '趋势冷 + 估值热', advice: '便宜没到位，等', cls: 'wait' },
    { id: '牛初/牛中', cond: '趋势热 + 估值冷', advice: '持有为主', cls: 'hold' },
    { id: '牛顶/过热', cond: '趋势热 + 估值热', advice: '逐步减仓', cls: 'hot' },
  ];
  wrap.innerHTML = cells.map((c) => {
    const active = c.id === q.quadrant ? ' quadrant--active' : '';
    return `<div class="quadrant${active}">
      <div class="quadrant__title">${c.id}</div>
      <div class="quadrant__cond">${c.cond}</div>
      <div class="quadrant__advice ${c.cls}">${c.advice}</div>
    </div>`;
  }).join('') + `<div class="clock__readout" style="grid-column:1/3">趋势 ${q.x.toFixed(1)}（${q.x >= 5 ? '热' : '冷'}） × 估值 ${q.y.toFixed(1)}（${q.y >= 5 ? '热' : '冷'}）</div>`;
}

// ── 四维打分条（§2.6 / content-plan ⑥） ──
export function renderScores(result) {
  const wrap = $('scores');
  if (!wrap) return;
  const dims = [
    { key: 'trend', name: '趋势' },
    { key: 'valuation', name: '估值' },
    { key: 'liquidity', name: '流动性' },
    { key: 'sentiment', name: '情绪' },
  ];
  wrap.innerHTML = dims.map((d) => {
    const s = result.scores[d.key];
    const color = scoreColor(s);
    return `<div class="score-row">
      <span class="score-row__name">${d.name}</span>
      <span class="score-bar" role="meter" aria-valuemin="0" aria-valuemax="10"
            aria-valuenow="${s.toFixed(1)}" aria-label="${d.name} ${s.toFixed(1)} 分（满分10，${s >= 5 ? '偏热危险' : '偏冷安全'}）">
        <span class="score-fill" style="width:${(s * 10).toFixed(1)}%;background:${color}"></span>
      </span>
      <span class="score-row__val" style="color:${color}">${s.toFixed(1)}</span>
    </div>`;
  }).join('');
}

// ── 数据明细表（content-plan ⑦，降级整行标灰 + 基线徽标） ──
export function renderDetail(macroData, degraded, refDate) {
  const tbody = $('macro-tbody');
  if (!tbody) return;
  const degradedSet = new Set(degraded.map((d) => d.field));
  // 渲染层兜底：对全部字段做 90 天陈旧判定（引擎只对打分用到的字段判定，
  // 原实现有 13/29 个字段游离在判定外，如 trade_balance 425 天无任何徽标）
  const ref = refDate ? new Date(refDate + 'T00:00:00') : new Date();
  const daysOld = (s) => {
    if (!s || typeof s !== 'string') return null;
    const iso = s.length === 4 ? s + '-01-01' : s.length === 7 ? s + '-01' : s;
    const d = new Date(iso + (iso.length === 10 ? 'T00:00:00' : ''));
    return isNaN(d.getTime()) ? null : Math.round((ref.getTime() - d.getTime()) / 86400000);
  };
  const rows = Object.keys(macroData).map((key) => {
    const f = macroData[key];
    const age = daysOld(f.asOf);
    const isDeg = degradedSet.has(key) || f.degraded === true || (age !== null && age > 90);
    const label = FIELD_LABELS[key] || key;
    const badge = isDeg ? `<span class="badge badge--baseline">基线${age !== null && age > 90 ? '·' + age + '天' : ''}</span>` : '';
    // 北向资金：港交所 2024 年起停止实时披露，显示 0 会被误读为「今日净流入 0」
    const valueTxt = key === 'northbound' ? '已停止披露' : fmtNum(f.value);
    const srcTxt = key === 'northbound' ? (f.src || '—') + '（港交所2024年起停止实时披露北向数据）' : (f.src || '—');
    return `<tr class="${isDeg ? 'row--degraded' : ''}">
      <td>${label}${badge ? ' ' + badge : ''}</td>
      <td class="num">${valueTxt}</td>
      <td class="num">${f.asOf || '—'}</td>
      <td>${srcTxt}</td>
    </tr>`;
  }).join('');
  tbody.innerHTML = rows;
}

// 汇总调用（首页）
export function renderDashboard(result, ctx) {
  applySiteName();
  // 宏观全字段都是基线值时，即使没触发引擎的陈旧降级，灯也要亮黄（不假装实时）
  const macroVals = Object.values(ctx.macroData || {});
  const allBaseline = macroVals.length > 0 && macroVals.every(
    (f) => f && typeof f.src === 'string' && f.src.startsWith('基线')
  );
  renderStatusLights(ctx.sourceStatus, {
    macroAsOf: ctx.macroAsOf,
    quotesAsOf: ctx.quotesAsOf,
    backtestAsOf: ctx.backtestAsOf,
    macroDegraded: result.degraded.length > 0 || allBaseline,
  });
  showAllDown(ctx.allDown);
  renderQuotes(ctx.quotes, ctx.macroData);
  renderTemp(result);
  renderPosition(result);
  renderTempTrendChart(ctx.backtest, result.temp, ctx.quotesAsOf || ctx.macroAsOf, ctx.daily);
  renderClock(result);
  renderScores(result);
  renderDetail(ctx.macroData, result.degraded, result.refDate);
  const up = $('last-updated');
  if (up) up.textContent = `最后更新：行情 ${ctx.quotesAsOf || '—'} ｜ 宏观 ${ctx.macroAsOf || '—'}`;
}
