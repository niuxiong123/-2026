// compute_temp.mjs —— 每日温度序列记录（第⑤步 item⑤）
// 铁律：不复制计算逻辑，直接 import 线上同一个 compute.js 跑分，保证与前端同源。
// 产物：docs/niuxiong-zijiantai/data/temp_daily.json —— [{date, temp}]，按日追加、去重、保留最近 400 条。
// 用法：node compute_temp.mjs [--dry]
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SITE = path.join(ROOT, 'docs', 'niuxiong-zijiantai');
const MACRO = path.join(SITE, 'data', 'macro.json');
const QUOTES = path.join(SITE, 'data', 'quotes.json');
const OUT = path.join(SITE, 'data', 'temp_daily.json');
const KEEP = 400;

const dry = process.argv.includes('--dry');

const macroDoc = JSON.parse(fs.readFileSync(MACRO, 'utf8'));
const macroData = macroDoc.data || {};
const quotesDoc = JSON.parse(fs.readFileSync(QUOTES, 'utf8'));
const quotes = quotesDoc && quotesDoc.ok === false ? null : quotesDoc;

const { computeAll } = await import(pathToFileURL(path.join(SITE, 'assets', 'js', 'compute.js')).href);
const result = computeAll(macroData, quotes);

const today = new Date().toISOString().slice(0, 10);
const entry = { date: today, temp: result.temp, position: result.positionFinal };

let series = [];
if (fs.existsSync(OUT)) {
  try { series = JSON.parse(fs.readFileSync(OUT, 'utf8')); } catch { series = []; }
}
if (!Array.isArray(series)) series = [];
series = series.filter((r) => r && r.date !== today);
series.push(entry);
series.sort((a, b) => (a.date < b.date ? -1 : 1));
series = series.slice(-KEEP);

console.log(`[temp] ${today}: temp=${result.temp} position=${result.positionFinal} degraded=${result.degraded.length}`);
if (dry) {
  console.log('[temp] --dry 模式，不写文件');
} else {
  fs.writeFileSync(OUT, JSON.stringify(series, null, 1));
  console.log(`[temp] 写回 ${OUT}（共 ${series.length} 条，区间 ${series[0].date} ~ ${series[series.length - 1].date}）`);
}
