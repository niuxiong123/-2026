// compute.js —— 计算引擎（site-spec §5.3 契约唯一实现处 / §6 算法逐字实现）
// 站点：恒福丨水木清华
//
// 纯前端、无网络请求。输入 macro.data（含降级填充）+ quotes.json，输出 PositionResult。
// 设计说明：
//   1) 温度 temp 由「先四舍五入后的四维分」合成（site-spec §6.3 公式，且保证与方法页
//      展示的 0.30×趋势 + … 手算逐位一致，便于审计）。
//   2) 陈旧参考日 ref 取自数据本身（macro 各字段 asOf、quotes.asOf、generated_at 的最大值），
//      保证「同一输入可复现」，不依赖访客本地时钟——否则静态快照每次刷新日期不同会让结果漂移。

import { BASELINE_SNAPSHOT } from './fetcher.js';

// ─────────────────────────────────────────────────────────────
// 锚点表（site-spec §6.2，逐字；erp / lpr1y 锚点原文按输入值降序书写，
// mapScore 内部会按输入值升序排序，不影响结果）
// ─────────────────────────────────────────────────────────────
const ANCHORS = {
  trend: {
    nasdaq_pct: { w: 0.4, a: [[-5, 1], [0, 3], [5, 5], [10, 7], [15, 9]] },
    breadth_up: { w: 0.3, a: [[30, 2], [50, 5], [80, 9]] },
    vix: { w: 0.3, a: [[12, 8], [20, 5], [30, 1]] },
  },
  valuation: {
    hs300_pe_pct: { w: 0.4, a: [[10, 1], [50, 5], [90, 9]] },
    hs300_pb_pct: { w: 0.3, a: [[10, 1], [50, 5], [90, 9]] },
    erp: { w: 0.2, a: [[7, 1], [5, 5], [2, 9]] },
    hsi_pe_pct: { w: 0.1, a: [[10, 1], [50, 5], [90, 9]] },
  },
  liquidity: {
    m1_yoy: { w: 0.4, a: [[0, 1], [5, 5], [15, 9]] },
    credit_yoy: { w: 0.3, a: [[8, 3], [10, 5], [13, 9]] },
    lpr1y: { w: 0.3, a: [[4.6, 2], [3.85, 5], [3.0, 8]] },
  },
  sentiment: {
    margin_yi: { w: 0.3, a: [[15000, 3], [20000, 6], [25000, 8], [30000, 10]] },
    amt_yi: { w: 0.25, a: [[6000, 2], [10000, 5], [17000, 7], [25000, 10]] },
    vix: { w: 0.25, a: [[12, 9], [20, 5], [30, 1]] },
    ah_premium: { w: 0.2, a: [[130, 5], [155, 8]] },
  },
};

// 温度→仓位映射（§6.4）
const ANCHORS_TEMP = [
  [0, 9.5], [2, 9], [4, 7], [5, 6], [6, 5], [7, 3.5], [8, 2], [9, 1], [10, 0.5],
];
// 信用约束：社融同比→上限(成)（§6.5①）
const ANCHORS_CREDIT = [
  [6, 3], [7, 4.5], [8, 6], [8.5, 10],
];

// trend/valuation 所用 7 个核心字段（§6.5③ 陈旧惩罚对象）
const CORE_FIELDS = [
  'nasdaq_pct', 'breadth_up', 'vix',
  'hs300_pe_pct', 'hs300_pb_pct', 'erp', 'hsi_pe_pct',
];

// 文件级降级时各字段视为「已降级」的上限天数
const FIELD_STALE_DAYS = 90; // 字段 asOf 超 90 天 → 基线（§6.8①）
const CORE_STALE_DAYS = 45; //  核心字段 asOf 超 45 天 → 命中保守系数惩罚（§6.5③）

// ─────────────────────────────────────────────────────────────
// 工具
// ─────────────────────────────────────────────────────────────
const round1 = (x) => Math.round(x * 10) / 10;
const round2 = (x) => Math.round(x * 100) / 100;
const clamp10 = (x) => Math.max(0, Math.min(10, x));

// 锚点线性插值 + 区间外 clamp 到端点分（§6.1）
function mapScore(v, anchorsRaw) {
  if (v == null || Number.isNaN(v)) return 0;
  const a = anchorsRaw.slice().sort((p, q) => p[0] - q[0]); // 按输入值升序
  const first = a[0];
  const last = a[a.length - 1];
  if (v <= first[0]) return clamp10(first[1]);
  if (v >= last[0]) return clamp10(last[1]);
  for (let i = 0; i < a.length - 1; i++) {
    const [x0, y0] = a[i];
    const [x1, y1] = a[i + 1];
    if (v >= x0 && v <= x1) {
      const t = (v - x0) / (x1 - x0);
      return clamp10(y0 + t * (y1 - y0));
    }
  }
  return clamp10(last[1]);
}

function parseDate(s) {
  if (!s) return null;
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}
function daysBetween(a, b) {
  if (!a || !b) return null;
  return Math.round((b.getTime() - a.getTime()) / 86400000);
}

// 取「陈旧参考日」：数据本身能给出的最新 asOf（确定性、可复现）
function resolveRefDate(data, quotes) {
  let max = null;
  const bump = (d) => {
    const t = parseDate(d);
    if (t && (!max || t.getTime() > max.getTime())) max = t;
  };
  for (const k in data) {
    if (data[k] && data[k].asOf) bump(data[k].asOf);
  }
  if (quotes && quotes.asOf) bump(quotes.asOf);
  return max || new Date();
}

// 取字段值（含字段级降级：缺失 / asOf 超 90 天 → 基线）。
// 注意：作为 computeAll 内的闭包实现，带 fieldCache 记忆化——同一字段只解析/标记一次，
// 避免 value 在多个维度/约束中被重复引用时（如 credit_yoy 同时用于流动性维与信用约束）
// 在 degraded[] 里出现重复记录（site-spec §6.8① 每条降级仅记一次）。
function makeFieldGetter(data, ref, degraded) {
  const cache = {};
  return function getField(key) {
    if (key in cache) return cache[key];
    const f = data[key];
    let res;
    if (!f || f.value === undefined || f.value === null) {
      degraded.push({ file: 'macro', field: key, reason: '字段缺失', usedDefault: true });
      res = { value: BASELINE_SNAPSHOT[key] != null ? BASELINE_SNAPSHOT[key] : 0, asOf: null, degraded: true };
    } else {
      const asOf = parseDate(f.asOf);
      const days = daysBetween(asOf, ref);
      if (days !== null && days > FIELD_STALE_DAYS) {
        degraded.push({ file: 'macro', field: key, reason: `asOf超${FIELD_STALE_DAYS}天`, usedDefault: true });
        res = { value: BASELINE_SNAPSHOT[key] != null ? BASELINE_SNAPSHOT[key] : f.value, asOf: f.asOf, degraded: true };
      } else {
        res = { value: f.value, asOf: f.asOf, degraded: false, days };
      }
    }
    cache[key] = res;
    return res;
  };
}

// 单维度合成（返回原始分 + 各子分，便于明细展示）
function scoreDimension(get, dimKey) {
  const def = ANCHORS[dimKey];
  let raw = 0;
  const parts = {};
  for (const fk in def) {
    const { w, a } = def[fk];
    const g = get(fk);
    const s = mapScore(g.value, a);
    parts[fk] = s;
    raw += w * s;
  }
  return { raw, rounded: round1(raw), parts };
}

// 牛熊钟定位（§6.7）
function clockOf(trend, valuation) {
  const tHot = trend >= 5;
  const vHot = valuation >= 5;
  let quadrant, advice;
  if (!tHot && !vHot) { quadrant = '熊末·黄金坑'; advice = '可分批建仓，不追涨'; }
  else if (!tHot && vHot) { quadrant = '下跌中继'; advice = '便宜没到位，等'; }
  else if (tHot && !vHot) { quadrant = '牛初/牛中'; advice = '持有为主'; }
  else { quadrant = '牛顶/过热'; advice = '逐步减仓'; }
  return { x: trend, y: valuation, quadrant, advice };
}

// 温度标签（§6.3）
function tempLabel(temp) {
  if (temp <= 3) return '偏冷·结构性机会';
  if (temp < 5) return '中性';
  if (temp < 7) return '偏热';
  return '过热·减仓';
}

// ─────────────────────────────────────────────────────────────
// 对外唯一入口（site-spec §5.3）
// ─────────────────────────────────────────────────────────────
export function computeAll(macro, quotes) {
  const data = macro && macro.data ? macro.data : macro; // 兼容传整体或内层
  const ref = resolveRefDate(data, quotes || null);

  const degraded = [];

  // ① 四维打分（原始分 → 1 位小数）
  const get = makeFieldGetter(data, ref, degraded);
  const trendR = scoreDimension(get, 'trend');
  const valuationR = scoreDimension(get, 'valuation');
  const liquidityR = scoreDimension(get, 'liquidity');
  const sentimentR = scoreDimension(get, 'sentiment');

  // ② 温度合成（用四舍五入后的四维分，保证与方法页手算逐位一致）
  const temp = round2(
    0.3 * trendR.rounded + 0.3 * valuationR.rounded + 0.2 * liquidityR.rounded + 0.2 * sentimentR.rounded
  );
  const tempLabelStr = tempLabel(temp);

  // ③ 温度仓位（§6.4）
  const positionTemp = round1(mapScore(temp, ANCHORS_TEMP));

  // ④ 硬约束（§6.5）
  // 信用约束：社融同比
  const creditCap = round1(mapScore(get('credit_yoy').value, ANCHORS_CREDIT));

  // 共振约束：阶跃规则
  let resonanceCap = 10;
  let resonanceReason = null;
  if (trendR.rounded >= 7 && valuationR.rounded >= 7) {
    resonanceCap = 3; resonanceReason = '双热共振·牛顶减仓';
  } else if (valuationR.rounded >= 7.5 && sentimentR.rounded >= 8) {
    resonanceCap = 4; resonanceReason = '估值情绪双极端';
  } else if (trendR.rounded <= 3 && valuationR.rounded <= 3) {
    resonanceCap = 10; resonanceReason = null; // 双冷共振·黄金坑（允许高仓）
  }

  // 保守系数（§6.5③）
  const triggers = [];
  const v = get('vix').value;
  const chinaFragile = get('china_fragile').value;
  const hormuz = get('hormuz_risk').value;
  const win = get('win_proximity').value;
  if (chinaFragile >= 8) triggers.push('china_fragile≥8');
  if (v >= 25) triggers.push('vix≥25');
  if (hormuz >= 7) triggers.push('hormuz_risk≥7');
  if (win >= 6) triggers.push('win_proximity≥6');
  // 核心字段 asOf 超 45 天（仅统计未降级项，避免与字段级降级重复计罚）
  for (const cf of CORE_FIELDS) {
    const f = data[cf];
    if (f && f.value != null && f.asOf) {
      const d = daysBetween(parseDate(f.asOf), ref);
      if (d !== null && d > CORE_STALE_DAYS) triggers.push(`${cf}数据陈旧(${d}天)`);
    }
  }
  const conservativeFactor = Math.max(0.8, 1.0 - 0.05 * triggers.length);

  // ⑤ 最终仓位（§6.6）
  const capped = Math.min(positionTemp, creditCap, resonanceCap);
  const positionFinal = round1(capped * conservativeFactor);

  // 牛熊钟
  const clock = clockOf(trendR.rounded, valuationR.rounded);

  return {
    scores: {
      trend: trendR.rounded,
      valuation: valuationR.rounded,
      liquidity: liquidityR.rounded,
      sentiment: sentimentR.rounded,
    },
    scoresRaw: {
      trend: trendR.parts,
      valuation: valuationR.parts,
      liquidity: liquidityR.parts,
      sentiment: sentimentR.parts,
    },
    temp,
    tempLabel: tempLabelStr,
    positionTemp,
    constraints: {
      creditCap,
      resonanceCap,
      resonanceReason,
      conservativeFactor,
      triggers,
    },
    positionFinal,
    clock,
    degraded,
    refDate: ref.toISOString().slice(0, 10),
  };
}

export { ANCHORS, ANCHORS_TEMP, ANCHORS_CREDIT, CORE_FIELDS, mapScore, round1, round2 };
