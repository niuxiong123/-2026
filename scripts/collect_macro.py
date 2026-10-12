# -*- coding: utf-8 -*-
# collect_macro.py —— 用 akshare 采集 macro.json 可真实化的字段（第⑤步 item①）
# 原则：
#   1. 只覆盖有可靠来源的 13 个字段；其余 16 个字段原样保留内置基线（前端照常标灰+徽标）。
#   2. 任何单个接口失败 → 该字段保留基线，不影响其他字段（缺一不写整份：成功字段 <5 则整份不写回）。
#   3. 值都带 asOf（数据真实截至日）+ src（akshare·接口名），前端陈旧判定/来源列直接可用。
#   4. 不改 compute.js 口径：只换输入数据，温度自然随之变化（这正是本脚本的目的）。
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MACRO_PATH = ROOT / "docs" / "niuxiong-zijiantai" / "data" / "macro.json"
MIN_OK_FIELDS = 5  # 成功字段少于此数 → 整份不写回（防半残疾数据上线）


def log(msg):
    print(msg, flush=True)


def as_date(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, str):
        for fmt in ("%Y年%m月份", "%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y/%m"):
            try:
                return dt.datetime.strptime(v.strip(), fmt).date()
            except ValueError:
                continue
    return None


def month_str(d):
    return d.replace(day=1).isoformat() if d else None


def newest(df, date_col):
    if df is None or df.empty:
        return None
    df = df.copy()
    df["_d"] = df[date_col].map(as_date)
    df = df.dropna(subset=["_d"]).sort_values("_d", ascending=False)
    return None if df.empty else df.iloc[0]


def f(v, nd=2):
    try:
        if v is None or (isinstance(v, float) and v != v):  # NaN
            return None
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None


def collect_pmi(ak):
    df = ak.macro_china_pmi()
    row = newest(df, "月份")
    if row is None:
        return None
    d = as_date(row["月份"])
    v = f(row.get("制造业-指数"))
    return (v, month_str(d), "akshare·macro_china_pmi") if v is not None else None


def collect_money(ak):
    df = ak.macro_china_money_supply()
    row = newest(df, "月份")
    if row is None:
        return None
    d = as_date(row["月份"])
    m1 = f(row.get("货币(M1)-同比增长"))
    m2 = f(row.get("货币和准货币(M2)-同比增长"))
    if m1 is None or m2 is None:
        return None
    return {"m1_yoy": (m1, month_str(d), "akshare·macro_china_money_supply"),
            "m2_yoy": (m2, month_str(d), "akshare·macro_china_money_supply")}


def collect_lpr(ak):
    df = ak.macro_china_lpr()
    row = newest(df, "TRADE_DATE")
    if row is None:
        return None
    v = f(row.get("LPR1Y"))
    return (v, row["_d"].isoformat(), "akshare·macro_china_lpr") if v is not None else None


def collect_hs300_pe(ak):
    df = ak.stock_index_pe_lg(symbol="沪深300")
    row = newest(df, "日期")
    if row is None:
        return None
    pe = f(row.get("滚动市盈率"))
    d = row["_d"]
    # PE 10 年分位：近 10 年滚动市盈率序列中 <= 当前值的占比
    df = df.copy()
    df["_d"] = df["日期"].map(as_date)
    df = df.dropna(subset=["_d", "滚动市盈率"])
    win = df[df["_d"] >= d - dt.timedelta(days=3650)]
    pct = f(win["滚动市盈率"].le(row["滚动市盈率"]).mean() * 100, 1) if len(win) >= 60 else None
    if pe is None or pct is None:
        return None
    return {"hs300_pe": (pe, d.isoformat(), "akshare·stock_index_pe_lg"),
            "hs300_pe_pct": (pct, d.isoformat(), "akshare·stock_index_pe_lg·10年分位")}


def collect_hs300_pb_pct(ak):
    df = ak.stock_index_pb_lg(symbol="沪深300")
    row = newest(df, "日期")
    if row is None:
        return None
    d = row["_d"]
    df = df.copy()
    df["_d"] = df["日期"].map(as_date)
    df = df.dropna(subset=["_d", "市净率"])
    win = df[df["_d"] >= d - dt.timedelta(days=3650)]
    pct = f(win["市净率"].le(row["市净率"]).mean() * 100, 1) if len(win) >= 60 else None
    return (pct, d.isoformat(), "akshare·stock_index_pb_lg·10年分位") if pct is not None else None


def collect_margin(ak):
    sh = newest(ak.macro_china_market_margin_sh(), "日期")
    sz = newest(ak.macro_china_market_margin_sz(), "日期")
    if sh is None or sz is None:
        return None
    # akshare 最新行单位为「元」（2010 年前老数据是万元，不采用老行）
    total_yuan = f(sh.get("融资融券余额")) + f(sz.get("融资融券余额"))
    if total_yuan is None:
        return None
    yi = f(total_yuan / 1e8, 1)
    if yi is None or not (5000 <= yi <= 100000):  # 合理性护栏：两市两融 5 千亿–10 万亿
        log(f"[warn] margin_yi 异常值 {yi}，跳过")
        return None
    d = min(sh["_d"], sz["_d"])
    return (yi, d.isoformat(), "akshare·沪深交易所两融余额合计")


def _latest_value(row, *cols):
    """依次取第一个非 NaN 的字段值（akshare 宏观序列最新行常今值 NaN、前值有值）。"""
    for c in cols:
        v = f(row.get(c), 1)
        if v is not None:
            return v
    return None


def collect_trade(ak):
    df = ak.macro_china_trade_balance()
    df = df[df["商品"].astype(str).str.contains("贸易帐", na=False)]
    row = newest(df, "日期")
    if row is None:
        return None
    v = _latest_value(row, "今值", "前值")
    return (v, month_str(row["_d"]), "akshare·macro_china_trade_balance") if v is not None else None


def collect_us_unemploy(ak):
    df = ak.macro_usa_unemployment_rate()
    row = newest(df, "日期")
    if row is None:
        return None
    v = _latest_value(row, "今值", "前值")
    return (v, month_str(row["_d"]), "akshare·macro_usa_unemployment_rate") if v is not None else None


def collect_re_yoy(ak):
    df = ak.macro_china_new_house_price()
    row = newest(df, "日期")
    if row is None:
        return None
    d = row["_d"]
    df = df[df["日期"].map(as_date) == d]
    col = "二手住宅价格指数-同比"
    vals = df[col].dropna()
    if vals.empty:
        return None
    avg = f(vals.mean() - 100.0)  # 指数(定比) → 同比%
    return (avg, month_str(d), "akshare·70城二手住宅同比(akshare·macro_china_new_house_price)") if avg is not None else None


def collect_cn10y(ak):
    """中债国债 10 年收益率；部分窗口接口返回空，逐级回退起始日。"""
    today = dt.date.today().strftime("%Y%m%d")
    for start in ("20251001", "20250101", "20240101"):
        try:
            df = ak.bond_china_yield(start_date=start, end_date=today)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        df = df[df["曲线名称"].astype(str).str.contains("国债", na=False)]
        row = newest(df, "日期")
        if row is None:
            continue
        v = f(row.get("10年"), 4)
        if v is not None:
            return (v, row["_d"].isoformat(), "akshare·bond_china_yield·中债国债10年")
    return None


def collect_erp(macro_data):
    """erp = 100/沪深300PE − 中债10年（与基线 5.291 口径一致：100/14.34−1.6822≈5.29）。
    仅当 hs300_pe 与 cn10y 均为真实值时才计算，否则保留基线（不拿半真半假骗人）。"""
    pe = macro_data.get("hs300_pe", {}).get("value")
    cn_field = macro_data.get("cn10y", {})
    cn = cn_field.get("value")
    pe_real = macro_data.get("hs300_pe", {}).get("src", "").startswith("akshare")
    cn_real = cn_field.get("src", "").startswith("akshare")
    if not (pe_real and cn_real):
        return None
    if not isinstance(pe, (int, float)) or pe <= 0 or not isinstance(cn, (int, float)):
        return None
    return (f(100.0 / pe - cn, 3), macro_data["hs300_pe"].get("asOf"), "计算(akshare·hs300_pe−cn10y)")


# 每个采集器：返回 {字段: (值, asOf, src)} 或 None（失败）
COLLECTORS = {
    "pmi": lambda ak: wrap("pmi", collect_pmi(ak)),
    "money": lambda ak: collect_money(ak),
    "lpr1y": lambda ak: wrap("lpr1y", collect_lpr(ak)),
    "hs300_pe": lambda ak: collect_hs300_pe(ak),
    "hs300_pb_pct": lambda ak: wrap("hs300_pb_pct", collect_hs300_pb_pct(ak)),
    "margin_yi": lambda ak: wrap("margin_yi", collect_margin(ak)),
    "trade_balance": lambda ak: wrap("trade_balance", collect_trade(ak)),
    "us_unemploy": lambda ak: wrap("us_unemploy", collect_us_unemploy(ak)),
    "re_yoy": lambda ak: wrap("re_yoy", collect_re_yoy(ak)),
    "cn10y": lambda ak: wrap("cn10y", collect_cn10y(ak)),
}


def wrap(key, res):
    return {key: res} if res else None


def run_collect():
    import akshare as ak  # 延迟导入：--self-test 无需 akshare
    results = {}
    for name, fn in COLLECTORS.items():
        try:
            out = fn(ak)
        except Exception as e:  # 单接口失败不致命
            log(f"[warn] {name} 采集失败：{type(e).__name__}: {str(e)[:100]}")
            out = None
        if out:
            results.update(out)
            for k, (v, d, s) in out.items():
                log(f"[ok] {k} = {v}（截至 {d}，{s}）")
        else:
            log(f"[skip] {name} 无数据，保留基线")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true", help="离线结构自检（不联网）")
    args = ap.parse_args()

    if args.self_test:
        m = json.loads(MACRO_PATH.read_text(encoding="utf-8"))
        data = m.get("data", {})
        assert len(data) == 29, f"字段数应为 29，实际 {len(data)}"
        for k, v in data.items():
            assert set(v.keys()) == {"value", "asOf", "src"}, f"{k} 结构异常: {v}"
        log(f"[self-test] 现有 macro.json 结构 OK（29 字段）")
        log(f"[self-test] 采集器 {len(COLLECTORS)} 个，最小成功数 {MIN_OK_FIELDS}")
        log("[self-test] 占位结构全部通过 ✓")
        return 0

    import akshare as ak
    m = json.loads(MACRO_PATH.read_text(encoding="utf-8"))
    data = m["data"]

    got = run_collect()
    if len(got) < MIN_OK_FIELDS:
        log(f"[abort] 成功字段仅 {len(got)} < {MIN_OK_FIELDS}，整份不写回（保留现有基线）")
        return 1

    for k, (v, d, s) in got.items():
        data[k] = {"value": v, "asOf": d, "src": s}

    # erp 依赖 hs300_pe + cn10y，两者都真实时才算（在 got 合并后再算）
    erp = collect_erp(data)
    if erp:
        v, d, s = erp
        data["erp"] = {"value": v, "asOf": d, "src": s}
        log(f"[ok] erp = {v}（截至 {d}，{s}）")
    else:
        log("[skip] erp 条件不足（hs300_pe/cn10y 非真实），保留基线")

    m["generated_at"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    m["real_fields"] = sorted(list(got.keys()) + (["erp"] if erp else []))
    m["source"] = "akshare（GitHub Actions 每日采集）+ 内置基线兜底"
    tmp = MACRO_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(MACRO_PATH)
    log(f"[ok] 写回 {MACRO_PATH}｜真实字段 {len(m['real_fields'])} 个：{', '.join(m['real_fields'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
