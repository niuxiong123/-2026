// ui.js —— 渲染层（温度卡/仓位卡/牛熊钟/四维/行情条/明细表/状态灯/标灰）
// 站点：牛熊自检台。规范依据：design-spec.md + content-plan.md 首页区块顺序。
import { QUOTE_FIELDS, BASELINE_SNAPSHOT } from './fetcher.js';

export const SITE_NAME = '牛熊自检台';

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
  els.forEach((el) => { el.textContent = SITE_NAME; });
  document.title = document.title.replace('__SITE__', SITE_NAME);
}

// ── 状态灯（§2.7） ──
export function renderStatusLights(status, info) {
  setLight('light-macro', status.macro, info.macroAsOf, info.macroDegraded, '宏观');
  setLight('light-quotes', status.quotes, info.quotesAsOf, status.quotes === 'missing', '行情');
  setLight('light-backtest', status.backtest, info.backtestAsOf, status.backtest === 'missing', '回测');
}
function setLight(id, state, asOf, degraded, label) {
  const el = $(id);
  if (!el) return;
  let st = state === 'missing' ? 'down' : (degraded ? 'warn' : 'ok');
  el.dataset.state = st;
  const dateTxt = asOf ? `，截至 ${asOf}` : '';
  const stateTxt = st === 'ok' ? '实时' : (st === 'warn' ? '降级基线' : '缺失');
  el.setAttribute('aria-label', `${label}数据源：${stateTxt}${dateTxt}`);
  const dot = el.querySelector('.dot');
  if (dot) dot.setAttribute('role', 'img');
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
  if (fill) fill.style.width = pct + '%';
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
    const reason = result.constraints.resonanceReason || '不约束';
    path.textContent =
      `温度仓位 ${result.positionTemp.toFixed(1)} 成 → ` +
      `硬约束取 min ${capped.toFixed(1)}（卡在：${reason}）→ ` +
      `保守系数 ×${result.constraints.conservativeFactor.toFixed(2)}`;
  }
}

// ── 实时温度走势折线图（首页新增） ──
export function renderTempTrendChart(backtest, currentTemp, currentDateStr) {
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
      datasets: [{
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
      }]
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
export function renderDetail(macroData, degraded) {
  const tbody = $('macro-tbody');
  if (!tbody) return;
  const degradedSet = new Set(degraded.map((d) => d.field));
  const rows = Object.keys(macroData).map((key) => {
    const f = macroData[key];
    const isDeg = degradedSet.has(key) || f.degraded === true;
    const label = FIELD_LABELS[key] || key;
    const badge = isDeg ? `<span class="badge badge--baseline">基线</span>` : '';
    return `<tr class="${isDeg ? 'row--degraded' : ''}">
      <td>${label}${badge ? ' ' + badge : ''}</td>
      <td class="num">${fmtNum(f.value)}</td>
      <td class="num">${f.asOf || '—'}</td>
      <td>${f.src || '—'}</td>
    </tr>`;
  }).join('');
  tbody.innerHTML = rows;
}

// 汇总调用（首页）
export function renderDashboard(result, ctx) {
  applySiteName();
  renderStatusLights(ctx.sourceStatus, {
    macroAsOf: ctx.macroAsOf,
    quotesAsOf: ctx.quotesAsOf,
    backtestAsOf: ctx.backtestAsOf,
    macroDegraded: result.degraded.length > 0,
  });
  showAllDown(ctx.allDown);
  renderQuotes(ctx.quotes, ctx.macroData);
  renderTemp(result);
  renderPosition(result);
  renderTempTrendChart(ctx.backtest, result.temp, ctx.quotesAsOf || ctx.macroAsOf);
  renderClock(result);
  renderScores(result);
  renderDetail(ctx.macroData, result.degraded);
  const up = $('last-updated');
  if (up) up.textContent = '最后更新：' + (ctx.quotesAsOf || ctx.macroAsOf || '—');
}
