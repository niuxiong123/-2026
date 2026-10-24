# scripts/generate_stockbond.py —— 每日生成 docs/niuxiong-zijiantai/data/stockbond.json
# 口径（与主模型逐点一致，勿随意改动阈值）：
#   股 = 中证 H00300 沪深300全收益（真实，含分红再投资）
#   债 = 二级债基模拟 = 中证全债 H11001×80% + H00300×20%，按月再平衡；
#        水平校准 alpha 使终点对齐公开二级债基指数估计值 TARGET_END（默认 5.03，每季度核对）
#   比值 R = 股/债；分位 = 2007-01-01 起全样本分位；仓位 = ★滞回阶梯（hyst_core 单一真源）
# 依赖：仅标准库 + 系统 curl（无需 akshare）；滞回逻辑在 scripts/hyst_core.py
import json, math, bisect, os, subprocess, sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "niuxiong-zijiantai", "data", "stockbond.json")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from hyst_core import step_hyst, compute_position  # noqa: E402

TARGET_END = 5.03  # 公开二级债基指数终点估计（2004-12-31=1）；每季度核对更新

def get(url):
    r = subprocess.run(["curl", "-s", "--max-time", "25", url],
                       capture_output=True, text=True, encoding="utf-8")
    return json.loads(r.stdout)

bond, stockTR = {}, {}
for y0, y1 in [(2004, 2006), (2007, 2008), (2009, 2010), (2011, 2012), (2013, 2014),
               (2015, 2016), (2017, 2018), (2019, 2020), (2021, 2022), (2023, 2024), (2025, 2026)]:
    try:
        for r in get(f"https://www.csindex.com.cn/csindex-home/perf/index-perf?indexCode=H11001"
                     f"&startDate={y0}0101&endDate={y1}1231")["data"]:
            if r.get("close") is not None:
                d = r["tradeDate"]; bond[f"{d[:4]}-{d[4:6]}-{d[6:]}"] = float(r["close"])
    except Exception as e:
        print("WARN bond", y0, y1, e)
    try:
        for r in get(f"https://www.csindex.com.cn/csindex-home/perf/index-perf?indexCode=H00300"
                     f"&startDate={y0}0101&endDate={y1}1231")["data"]:
            if r.get("close") is not None:
                d = r["tradeDate"]; stockTR[f"{d[:4]}-{d[4:6]}-{d[6:]}"] = float(r["close"])
    except Exception as e:
        print("WARN stock", y0, y1, e)
if len(stockTR) < 1000 or len(bond) < 100:
    raise SystemExit("数据拉取失败：stock=%d bond=%d" % (len(stockTR), len(bond)))
print("stockTR:", len(stockTR), "bond:", len(bond))

T0 = date(2004, 12, 31)
def yrs(ds): return (date.fromisoformat(ds) - T0).days / 365.25
def parse(d): y, m, dd = map(int, d.split("-")); return date(y, m, dd)

# 月末对齐 → 二级债基模拟（80/20 按月再平衡）+ 水平校准
def month_ends(dates):
    out = {}; last = None
    for d in dates:
        ym = d[:7]
        if last and last[:7] != ym: out[last[:7]] = last
        last = d
    out[last[:7]] = last
    return out

bm, sm = month_ends(bond), month_ends(sorted(stockTR))
months = [m for m in sorted(set(bm) & set(sm)) if m >= "2004-12"]
fund = 1000.0; nav = {months[0]: fund}; prev = months[0]
for m in months[1:]:
    rb = bond[bm[m]] / bond[bm[prev]]
    rs = stockTR[sm[m]] / stockTR[sm[prev]]
    fund *= 0.8 * rb + 0.2 * rs
    nav[m] = fund; prev = m
alpha = math.log(TARGET_END / (nav[months[-1]] / 1000.0)) / yrs(bm[months[-1]])
nav_cal = {m: nav[m] * math.exp(alpha * yrs(bm[m])) for m in months}
print("校准 alpha = %.4f/年, 终点 = %.3f" % (alpha, nav_cal[months[-1]] / 1000.0))

pts = [(bm[m], nav_cal[m]) for m in months]
def bondAt(d):
    if d <= pts[0][0]: return pts[0][1]
    if d >= pts[-1][0]: return pts[-1][1]
    for i in range(1, len(pts)):
        if d <= pts[i][0]:
            t = (parse(d) - parse(pts[i-1][0])).days / max((parse(pts[i][0]) - parse(pts[i-1][0])).days, 1)
            return pts[i-1][1] + (pts[i][1] - pts[i-1][1]) * t

sd = sorted(stockTR)
S0 = stockTR["2004-12-31"]; B0 = bondAt("2004-12-31")
warm = [d for d in sd if d >= "2007-01-01"]
G = {d: math.log(stockTR[d] / bondAt(d)) for d in warm}
gs = sorted(G.values()); n = len(gs)
def pct_of(d): return 100.0 * bisect.bisect_left(gs, G[d]) / n

posH = {}; state = 0
for d in sd:
    if d in G:
        state = step_hyst(pct_of(d), state); posH[d] = state

weekly = {}
for d in sd:
    if d not in G: continue
    y, w, _ = parse(d).isocalendar(); weekly[(y, w)] = d
wk = [weekly[k] for k in sorted(weekly)]
records = [{"date": d, "nav_hs": round(stockTR[d] / S0, 4), "nav_bond": round(bondAt(d) / B0, 4),
            "ratio_R": round(stockTR[d] / bondAt(d), 4), "pct": round(pct_of(d), 2), "pos": posH[d]}
           for d in wk]
now = sd[-1]

# ── 日频近况（股债双杀熔断用；周频会把债基月内插值路径磨平，导致双杀算不出来）──
recent_daily = [{"date": d, "nav_hs": round(stockTR[d] / S0, 4), "nav_bond": round(bondAt(d) / B0, 4)}
                for d in sd[-60:]]

# ── 无风险利率：取站点 macro.json 的十年国债（与主站同源），读不到退回 1.68% ──
rf = 0.0168
MACRO = os.path.join(ROOT, "docs", "niuxiong-zijiantai", "data", "macro.json")
try:
    _m = json.load(open(MACRO, encoding="utf-8"))
    _v = _m.get("data", {}).get("cn10y", {}).get("value")
    if isinstance(_v, (int, float)) and 0 < _v < 10:
        rf = _v / 100.0
except Exception as e:
    print("WARN macro.json 读取失败，rf 用默认 1.68%:", e)

# ── 命理放开状态：跨期记忆，必须持久化，否则每次重算都从"未放开"起算 ──
# 注意：字段写在 latest 里，读取也要从 latest 读（曾因读写层级不对称导致记忆永远失效）
prev_open = False
if os.path.exists(OUT):
    try:
        _old = json.load(open(OUT, encoding="utf-8"))
        prev_open = bool(_old.get("mystic_open",
                                  _old.get("latest", {}).get("mystic_open", False)))
    except Exception as e:
        print("WARN 旧 JSON 读取失败，mystic_open 视为未放开:", e)

# ── 完整约束链总装（滞回阶梯 → 动态 Kelly → 股债双杀 → 命理封顶 → 复活条款）──
# prev_pos 必须取「上一交易日」的回放档位：取上一 ISO 周会跳过中间若干交易日，
# 导致 latest.pos（全量回放）与约束链里的 hys 不一致。
prev_trade = posH.get(sd[-2], posH[wk[-2]] if len(wk) > 1 else 0)
wk_navs = [stockTR[d] / S0 for d in wk]
chain = compute_position(
    q=pct_of(now), navs=wk_navs,
    prev_pos=prev_trade,
    mystic_open=prev_open, rf=rf, daily=recent_daily, year=int(now[:4]),
)
if sd[-2] in posH:
    assert chain["hys"] == posH[now], "滞回档位不一致：回放=%s 单步=%s" % (posH[now], chain["hys"])
mom_1m = round(stockTR[wk[-1]] / stockTR[wk[-5]] - 1, 4) if len(wk) >= 5 else None

latest = {"date": now, "nav_hs": round(stockTR[now] / S0, 4), "nav_bond": round(bondAt(now) / B0, 4),
          "ratio_R": round(stockTR[now] / bondAt(now), 4), "pct": round(pct_of(now), 2), "pos": posH[now],
          "prev_position": prev_trade,
          "hs300_mom_1m": mom_1m,
          "sigma": round(chain["sigma"], 4) if chain["sigma"] else None,
          "rf": round(rf, 6),
          "kelly_cap": round(chain["kelly_cap"], 1) if chain["kelly_cap"] is not None else None,
          "dk_triggered": chain["dk_triggered"],
          "dk_hs20": round(chain["dk_hs20"], 4) if chain["dk_hs20"] is not None else None,
          "dk_bond20": round(chain["dk_bond20"], 4) if chain["dk_bond20"] is not None else None,
          "dk_cap": chain["dk_cap"],
          "mystic_open": chain["mystic_open"], "mystic_cap": chain["mystic_cap"],
          "final_position": chain["pos"], "final_reason": chain["reason"]}

out = {
    "generated_at": date.today().isoformat(),
    "source": "中证官网 H00300(沪深300全收益) + 二级债基模拟(中证全债H11001×80% + H00300×20% 按月再平衡, 终点校准" + ("%.2f" % TARGET_END) + ")",
    "base_date": "2004-12-31", "freq": "weekly",
    "model": "股债比值R=沪深300全收益/二级债基；全历史分位(2007-01起)；★滞回阶梯 → 动态Kelly(插值μ/λ+滚动σ+cn10y) → 股债双杀熔断(日频20日) → 命理纪律封顶(随分位递减+双阈值滞回) → 复活条款",
    "thresholds": {"升档(跌入才升)": "分位≤5%→100成｜≤15%→80成｜≤35%→50成｜≤65%→20成",
                   "降档(涨过才降)": ">15%→80成｜>35%→50成｜>65%→20成｜>80%→0成",
                   "股债双杀": "股20日≤-5% 且 债20日≤-1% → 压至20成（打在地板上时复活条款回补50成）",
                   "命理封顶": "分位≤5%放开｜>20%收回；阶梯 5%→100 / 10%→80 / 20%→60 / 40%→40 / 65%→20 / >65%→0；2026-2027财杀攻身年地板区只放到80成"},
    "backtest": "2007-2026 无前视1013周：年化10.26%｜最大回撤-23.9%｜夏普0.72（旧口径11.17%/-15.4%为月度再平衡乐观口径，已废弃勿混用）",
    "disclaimer": "个人研究模型，历史回测不代表未来，非投资建议",
    "weekly_count": len(records), "latest": latest, "weekly": records,
    "recent_daily": recent_daily,
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
print("saved", OUT, "weekly:", len(records), "latest:", latest)
