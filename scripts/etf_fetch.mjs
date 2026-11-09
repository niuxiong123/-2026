#!/usr/bin/env node
/* ETF 周线+月线 双周期买卖信号 · 实时快照生成器
 * ------------------------------------------------------------------
 * 本机与 GitHub Actions 共用同一份代码，网页运行时复算口径与此完全一致。
 * 数据源：腾讯行情 web.ifzq.gtimg.cn（qfq 前复权，允许跨域）为主，
 *         东方财富 push2his（fqt=1 前复权）为备；单只失败沿用旧快照该只数据。
 *
 * 用法：node etf_fetch.mjs
 * 环境变量：
 *   ETF_ROOT      仓库根 / 本地目录（默认 cwd）
 *   ETF_SNAPSHOT  输出快照路径（默认 $ROOT/docs/etf_snapshot.json）
 *   ETF_META      META 兜底文件（默认 $ROOT/etf_meta_block.js）
 *   ETF_SCAN      本次扫描标记：daily-1410 / friday-1430 / close-1530 / manual
 */
import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.env.ETF_ROOT || process.cwd();
const SNAP = process.env.ETF_SNAPSHOT || path.join(ROOT, 'docs', 'etf_snapshot.json');
const META_FALLBACK = process.env.ETF_META || path.join(ROOT, 'etf_meta_block.js');
const SCAN = process.env.ETF_SCAN || 'manual';
const UA = 'Mozilla/5.0 (ETF-Workbench/1.0)';

/* ---------- 1. 标的池 ---------- */
function loadMeta() {
  try {
    const j = JSON.parse(fs.readFileSync(SNAP, 'utf8'));
    if (j.META && j.META.length >= 30) return j.META;
  } catch (e) { /* 首次运行没有旧快照 */ }
  const t = fs.readFileSync(META_FALLBACK, 'utf8');
  const a = t.indexOf('['), b = t.lastIndexOf(']');
  if (a < 0 || b <= a) throw new Error('找不到 ETF_META 数组');
  return JSON.parse(t.slice(a, b + 1));
}

/* ---------- 2. 指标引擎（与 index.html 逐字一致） ---------- */
function ema(a, N) { const k = 2 / (N + 1); const o = []; let p = a[0]; for (let i = 0; i < a.length; i++) { p = (i === 0 ? a[0] : k * a[i] + (1 - k) * p); o.push(p); } return o; }
function sma(a, N, M) { const o = []; let p = a[0]; for (let i = 0; i < a.length; i++) { p = (i === 0 ? a[0] : (M / N) * a[i] + ((N - M) / N) * p); o.push(p); } return o; }
function ma(a, N) { const o = []; for (let i = 0; i < a.length; i++) { let s = 0, c = 0; for (let j = Math.max(0, i - N + 1); j <= i; j++) { s += a[j]; c++; } o.push(s / c); } return o; }
function rmin(a, N) { const o = []; for (let i = 0; i < a.length; i++) { let m = Infinity; for (let j = Math.max(0, i - N + 1); j <= i; j++) if (a[j] < m) m = a[j]; o.push(m); } return o; }
function rmax(a, N) { const o = []; for (let i = 0; i < a.length; i++) { let m = -Infinity; for (let j = Math.max(0, i - N + 1); j <= i; j++) if (a[j] > m) m = a[j]; o.push(m); } return o; }
function computeIndicator(bars) {
  const C = bars.map(b => b[2]), H = bars.map(b => b[3]), L = bars.map(b => b[4]);
  const llv55 = rmin(L, 55), hhv55 = rmax(H, 55);
  const riskRaw = C.map((c, i) => { const d = hhv55[i] - llv55[i]; return d === 0 ? 50 : 100 * (c - llv55[i]) / d; });
  const 风险 = ema(riskRaw, 5);
  const llv34c = rmin(C, 34), hhv34 = rmax(H, 34);
  const k34 = C.map((c, i) => { const d = hhv34[i] - llv34c[i]; return d === 0 ? 50 : 100 * (c - llv34c[i]) / d; });
  const maK34 = sma(k34, 5, 1);
  const V1 = maK34.map(x => x - 20);
  const V2 = V1.map(x => 2 * Math.abs(x));
  const 空 = V1.map((v, i) => 30 - (v < 0 ? V2[i] : 0));
  const var1 = C.map((_, i) => C[Math.max(0, i - 2)]);
  const diff = C.map((c, i) => c - var1[i]);
  const sPos = sma(diff.map(d => Math.max(d, 0)), 7, 1), sAb = sma(diff.map(d => Math.abs(d)), 7, 1);
  const 趋势 = sPos.map((p, i) => sAb[i] === 0 ? 50 : p / sAb[i] * 100);
  const hhv34h = rmax(H, 34), llv34l = rmin(L, 34);
  const longRaw = C.map((c, i) => { const d = hhv34h[i] - llv34l[i]; return d === 0 ? 0 : -100 * (hhv34h[i] - c) / d; });
  const 长期 = ma(longRaw, 8).map(x => x + 100);
  const diff1 = C.map((c, i) => c - (i >= 1 ? C[i - 1] : C[0]));
  const sPos1 = sma(diff1.map(d => Math.max(d, 0)), 8, 1), sAb1 = sma(diff1.map(d => Math.abs(d)), 8, 1);
  const MA多 = sPos1.map((p, i) => sAb1[i] === 0 ? 50 : p / sAb1[i] * 100);
  const 多 = ema(MA多, 5);
  const 趋势线 = 趋势.map((t, i) => (t + 长期[i]) / 2);
  return { 风险, 趋势, 长期, 多, 趋势线, 空 };
}
function startOfWeek(d) { const x = new Date(d); const wd = x.getDay(); const diff = (wd === 0 ? 6 : wd - 1); x.setDate(x.getDate() - diff); x.setHours(0, 0, 0, 0); return x; }
function lastCompleteIdx(bars, tf) {
  if (!bars || !bars.length) return 0;
  if (tf === 'm') {
    let idx = -1; for (let i = 0; i < bars.length; i++) { const day = parseInt(bars[i][0].slice(8, 10), 10); if (day >= 25) idx = i; }
    if (idx < 1) idx = bars.length - 1; return idx;
  } else {
    let idx = bars.length - 1;
    const last = new Date(bars[idx][0]); const now = new Date();
    if (idx > 0 && startOfWeek(last).getTime() === startOfWeek(now).getTime() && now.getDay() < 5) idx--;
    return idx;
  }
}
function detectSignal(ind, last) {
  const r = ind.风险[last], t = ind.趋势[last], lg = ind.长期[last], d = ind.多[last], k = ind.空[last], tl = ind.趋势线[last];
  const tp = (last > 0 ? ind.趋势[last - 1] : t);
  const conds = [];
  if (t <= 4 && tp > 4) conds.push(['强买', 1]);
  if (r < 6.5) conds.push(['加', 1]);
  if (t <= 4) conds.push(['买', 1]);
  if (r < 10 && tl < 10) conds.push(['底', 1]);
  if (t > 4 && t < 10) conds.push(['定买', 1]);
  if (t < 12 && lg < 12 && d < 25 && k < 0) conds.push(['G1底', 1]);
  if (t > 92 && tp <= 92) conds.push(['顶', 2]);
  if (r > 94) conds.push(['减', 2]);
  if (t > 92) conds.push(['卖', 2]);
  if (t > 88 && t <= 92) conds.push(['定卖', 2]);
  if (t > 89 && lg > 88 && d > 78 && k > 29) conds.push(['G2顶', 2]);
  if (!conds.length) return { r, t, lg, d, k, tl, conds: [], main: '持有', type: 'hold' };
  const RANK = { '强买': 5, '加': 5, '买': 5, '底': 4, 'G1底': 4, '定买': 3, '顶': 5, '减': 5, '卖': 5, 'G2顶': 4, '定卖': 3 };
  conds.sort((a, b) => RANK[b[0]] - RANK[a[0]]);
  return { r, t, lg, d, k, tl, conds, main: conds[0][0], type: conds[0][1] === 2 ? 'sell' : 'buy' };
}
function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
function buyForce(msig, wsig, cold, chg) {
  const r = Math.min(msig.r, wsig.r), t = Math.min(msig.t, wsig.t);
  return Math.round((0.35 * clamp((100 - r) / 100, 0, 1) + 0.25 * clamp((100 - t) / 100, 0, 1)
    + 0.20 * clamp((100 - cold) / 100, 0, 1) + 0.20 * clamp(-chg / 15, 0, 1)) * 100);
}
function tierText(f) { return f >= 70 ? '🔴 加重' : f >= 45 ? '🟡 标准' : '🔵 轻仓试探'; }
function ladderText(f) { return f >= 70 ? '现在建 40% · 再跌5%加30% · 再跌10%加30%' : f >= 45 ? '现在建 25% · 再跌5%加25% · 再跌10%加25%' : '现在建 15% · 再跌5%加15% · 再跌10%加20%'; }

/* ---------- 3. 联网抓取 ---------- */
async function getJSON(url, ms = 16000) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), ms);
  try {
    const r = await fetch(url, { signal: ctl.signal, headers: { 'User-Agent': UA, 'Accept': '*/*' } });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return JSON.parse(await r.text());
  } finally { clearTimeout(timer); }
}
function prefixOf(code) { const h = code[0]; return (h === '5' || h === '6' || h === '9') ? 'sh' : 'sz'; }
function secidOf(m) { return m.secid || ((prefixOf(m.code) === 'sh' ? '1.' : '0.') + m.code); }

async function barsTX(m, tf) {
  const pre = prefixOf(m.code);
  const url = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=' + pre + m.code + ',' + tf + ',,,120,qfq&_=' + Date.now();
  const j = await getJSON(url);
  const node = j && j.data && j.data[pre + m.code];
  if (!node) throw new Error('TX 无节点');
  const arr = node['qfq' + tf] || node[tf];
  if (!arr || arr.length < 8) throw new Error('TX 无K线');
  return arr.map(r => [r[0], +r[1], +r[2], +r[3], +r[4], +r[5]]);
}
async function barsEM(m, tf) {
  const klt = tf === 'month' ? 103 : 102;
  const url = 'https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=' + secidOf(m)
    + '&ut=fa5fd1943c7b386f172d6893dbfba10b&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56,f57'
    + '&klt=' + klt + '&fqt=1&end=20500101&lmt=260';
  const j = await getJSON(url);
  const kl = j && j.data && j.data.klines;
  if (!kl || kl.length < 8) throw new Error('EM 无K线');
  return kl.map(x => { const p = x.split(','); return [p[0], +p[1], +p[2], +p[3], +p[4], +p[5]]; });
}
async function fetchBars(m, tf, stats) {
  // 腾讯偶发 501（限流）时先重试一次，再切东方财富，最后沿用旧快照
  for (let attempt = 0; attempt < 2; attempt++) {
    try { const b = await barsTX(m, tf); stats.tx++; return b; }
    catch (e1) {
      if (attempt === 0) { await new Promise(r => setTimeout(r, 250)); continue; }
      try { const b = await barsEM(m, tf); stats.em++; return b; }
      catch (e2) { stats.fail++; console.error('  ✗ ' + m.code + ' ' + tf + ' : ' + e1.message + ' / ' + e2.message); return null; }
    }
  }
  return null;
}

/* ---------- 4. 主流程 ---------- */
const META = loadMeta();
console.log('快照输出: ' + SNAP);
console.log('标的数量: ' + META.length + ' | 扫描标记: ' + SCAN);

let OLD = {};
for (const p of [process.env.ETF_OLD || path.join(ROOT, 'realtime_snapshot.json'), SNAP]) {
  try { const d = JSON.parse(fs.readFileSync(p, 'utf8')).MARKET_DATA || {}; if (Object.keys(d).length) OLD = Object.assign({}, OLD, d); } catch (e) { }
}

const stats = { tx: 0, em: 0, fail: 0 };
const pairs = [];
META.forEach(m => { pairs.push([m, 'month']); pairs.push([m, 'week']); });
const results = new Array(pairs.length);
const POOL = 8;
for (let i = 0; i < pairs.length; i += POOL) {
  const slice = pairs.slice(i, i + POOL);
  const got = await Promise.all(slice.map(([m, tf]) => fetchBars(m, tf, stats)));
  got.forEach((v, k) => { results[i + k] = v; });
  if (i + POOL < pairs.length) await new Promise(r => setTimeout(r, 120)); // 轻微限速，防 501
}

const DATA = {};
pairs.forEach(([m, tf], i) => {
  const key = tf === 'month' ? 'm' : 'w';
  const b = results[i] || (OLD[m.code] && OLD[m.code][key]);
  if (!b || b.length < 8) return;
  DATA[m.code] = DATA[m.code] || {};
  DATA[m.code][key] = b;
});
const okCount = Object.keys(DATA).filter(c => DATA[c].m && DATA[c].w).length;
console.log('抓取: 腾讯 ' + stats.tx + ' / 东财 ' + stats.em + ' / 失败 ' + stats.fail + ' | 可用 ETF ' + okCount + '/' + META.length);
if (okCount < 30) { console.error('❌ 可用 ETF 不足 30 只，拒绝覆盖快照（防止坏数据上线）'); process.exit(1); }

/* ---------- 5. 复算信号 ---------- */
const STATE = [];
for (const m of META) {
  const d = DATA[m.code]; if (!d || !d.m || !d.w) continue;
  const mInd = computeIndicator(d.m), mLast = lastCompleteIdx(d.m, 'm'), mSig = detectSignal(mInd, mLast);
  const wInd = computeIndicator(d.w), wLast = lastCompleteIdx(d.w, 'w'), wSig = detectSignal(wInd, wLast);
  const mClose = d.m[mLast][2], mPrev = d.m[Math.max(0, mLast - 1)][2];
  const mChg = mPrev ? (mClose / mPrev - 1) * 100 : 0;
  const wClose = d.w[wLast][2], wPrev = d.w[Math.max(0, wLast - 1)][2];
  const wChg = wPrev ? (wClose / wPrev - 1) * 100 : 0;
  const reso = (mSig.type === 'buy' && wSig.type === 'buy');
  const force = reso ? buyForce(mSig, wSig, m.cold, mChg) : 0;
  STATE.push({ meta: m, mSig, wSig, mChg, wChg, reso, force, mBarDate: d.m[mLast][0], wBarDate: d.w[wLast][0] });
}
function mode(arr) { const c = {}; let best = arr[0] || '', n = 0; arr.forEach(x => { c[x] = (c[x] || 0) + 1; if (c[x] > n) { n = c[x]; best = x; } }); return best; }
const resoList = STATE.filter(s => s.reso).sort((a, b) => b.force - a.force).map(s => ({
  code: s.meta.code, name: s.meta.name, sector: s.meta.sector, force: s.force,
  tier: tierText(s.force), ladder: ladderText(s.force),
  mR: +s.mSig.r.toFixed(1), mT: +s.mSig.t.toFixed(1), wR: +s.wSig.r.toFixed(1), wT: +s.wSig.t.toFixed(1),
  mMain: s.mSig.main, wMain: s.wSig.main, mChg: +s.mChg.toFixed(1)
}));
const summary = {
  total: STATE.length,
  monthBuy: STATE.filter(s => s.mSig.type === 'buy').length,
  monthSell: STATE.filter(s => s.mSig.type === 'sell').length,
  weekBuy: STATE.filter(s => s.wSig.type === 'buy').length,
  weekSell: STATE.filter(s => s.wSig.type === 'sell').length,
  reso: STATE.filter(s => s.reso).length,
  resoSell: STATE.filter(s => s.mSig.type === 'sell' && s.wSig.type === 'sell').length,
  coldAvg: Math.round(STATE.reduce((a, s) => a + (Number(s.meta.cold) || 0), 0) / (STATE.length || 1)),
  resoList: resoList
};
const compactMeta = META.map(m => ({ code: m.code, name: m.name, secid: secidOf(m), sector: m.sector, note: m.note, m2: m.m2, cold: m.cold, chg: m.chg, hk: m.hk }));
function bjISO() { return new Date(Date.now() + 8 * 3600 * 1000).toISOString().replace('Z', '+08:00'); }
const out = {
  generated: bjISO(), generatedTS: Date.now(), scanKind: SCAN,
  source: '腾讯行情 ifzq(qfq) 主 / 东方财富 push2his(fqt=1) 备',
  dataDate: { month: mode(STATE.map(s => s.mBarDate)), week: mode(STATE.map(s => s.wBarDate)), monthEnd: '', weekEnd: '' },
  summary, META: compactMeta, MARKET_DATA: DATA
};
fs.writeFileSync(SNAP, JSON.stringify(out));
console.log('✅ 快照已写入: ' + SNAP + ' (' + Math.round(fs.statSync(SNAP).size / 1024) + ' KB)');
console.log('数据周期: 月线 ' + out.dataDate.month + ' | 周线 ' + out.dataDate.week);
console.log('信号汇总: 月买 ' + summary.monthBuy + ' / 周买 ' + summary.weekBuy + ' / 共振 ' + summary.reso + ' / 月卖 ' + summary.monthSell + ' / 周卖 ' + summary.weekSell + ' / 估值分位均值 ' + summary.coldAvg + '%');
if (resoList.length) console.log('共振标的: ' + resoList.map(r => r.code + ' ' + r.name + ' 力度' + r.force + ' ' + r.tier).join(' | '));
