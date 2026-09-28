#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观 / 估值 / 资金数据抓取器（服务端）
------------------------------------------------
产出两处：
  1) niuxiong.db   → 表 macro（保留 90 天，供 /api/macro 与每日任务读取）
  2) macro.json    → 静态兜底（前端没后端时也能读）

安全与健壮：
  - 每项独立 try，一项挂了不影响其它项；
  - 抓不到时沿用上一版数值并打 stale 标记（绝不凭空造数）；
  - 数值越过合理区间（如 PMI 130）自动判定为脏数据并标 noData，不参与打分；
  - 失败项写入 fetch_log 表，供告警检查。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
import warnings

warnings.filterwarnings("ignore")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "niuxiong.db")

# 合理区间：越界视为脏数据（数据源改版/口径变化时会触发）
RANGES = {
    "pmi": (30, 60), "m1_yoy": (-10, 30), "credit_yoy": (-100, 100),
    "lpr1y": (1, 8), "cn10y": (0, 10), "us10y": (0, 15),
    "hs300_pe": (5, 60), "erp": (-5, 20), "margin_yi": (5000, 60000),
    "northbound": (-2000, 2000), "breadth_up": (0, 100),
}


def _d(s):
    for f in ("%Y年%m月份", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(str(s), f).date()
        except ValueError:
            continue
    return None


def _ak():
    try:
        import akshare as ak
        return ak
    except ImportError:
        print("[FATAL] 缺少 akshare：pip3 install akshare")
        sys.exit(2)


ak = _ak()


def fetch_pmi():
    r = ak.macro_china_pmi().iloc[0]
    return {"value": float(r["制造业-指数"]), "asOf": _d(r["月份"]).isoformat(),
            "src": "国家统计局/东财"}


def fetch_m1():
    r = ak.macro_china_money_supply().iloc[0]
    return {"value": float(r["货币(M1)-同比增长"]), "asOf": _d(r["月份"]).isoformat(),
            "src": "央行/东财", "extra": {"m2_yoy": float(r["货币和准货币(M2)-同比增长"])}}


def fetch_credit():
    """用「累计同比」更稳：当月值季节性极大"""
    r = ak.macro_china_new_financial_credit().iloc[0]
    return {"value": float(r["累计-同比增长"]), "asOf": _d(r["月份"]).isoformat(),
            "src": "央行/东财·累计同比",
            "extra": {"当月亿元": float(r["当月"]), "当月同比": float(r["当月-同比增长"])}}


def fetch_lpr():
    r = ak.macro_china_lpr().iloc[-1]
    return {"value": float(r["LPR1Y"]), "asOf": str(r["TRADE_DATE"]),
            "src": "全国银行间同业拆借中心", "extra": {"LPR5Y": float(r["LPR5Y"])}}


def fetch_rates():
    df = ak.bond_zh_us_rate()
    cn = df.dropna(subset=["中国国债收益率10年"]).iloc[-1]
    us = df.dropna(subset=["美国国债收益率10年"])
    cn_o = {"value": float(cn["中国国债收益率10年"]), "asOf": str(cn["日期"]), "src": "中债/东财"}
    us_o = {"value": float(us.iloc[-1]["美国国债收益率10年"]), "asOf": str(us.iloc[-1]["日期"]),
            "src": "FRED/东财"} if len(us) else None
    return cn_o, us_o


def fetch_tech(symbol="sh000300"):
    df = ak.stock_zh_index_daily(symbol=symbol).dropna().tail(300).reset_index(drop=True)
    c = df["close"].astype(float)
    last = float(c.iloc[-1])
    ma = lambda n: float(c.tail(n).mean())            # noqa: E731
    hi, lo = float(c.tail(250).max()), float(c.tail(250).min())
    return {"value": last, "asOf": str(df["date"].iloc[-1]), "src": "新浪/东财",
            "extra": {"ma20": ma(20), "ma60": ma(60), "ma250": ma(250),
                      "chg_5d": float((last / float(c.iloc[-6]) - 1) * 100),
                      "chg_20d": float((last / float(c.iloc[-21]) - 1) * 100),
                      "chg_60d": float((last / float(c.iloc[-61]) - 1) * 100),
                      "drawdown_from_250high": float((last / hi - 1) * 100),
                      "pos_in_250range": float((last - lo) / (hi - lo) * 100),
                      "above_ma250": bool(last > ma(250)), "ma20_gt_ma60": bool(ma(20) > ma(60))}}


def fetch_valuation(code="000300"):
    r = ak.stock_zh_index_value_csindex(symbol=code).iloc[0]
    return {"value": float(r["市盈率1"]), "asOf": str(r["日期"]), "src": "中证指数官网",
            "extra": {"股息率": float(r["股息率1"])}}


def fetch_margin():
    sh, sz = ak.macro_china_market_margin_sh(), ak.macro_china_market_margin_sz()
    total = (float(sh.iloc[-1]["融资余额"]) + float(sz.iloc[-1]["融资余额"])) / 1e8
    prev = (float(sh.iloc[-6]["融资余额"]) + float(sz.iloc[-6]["融资余额"])) / 1e8
    return {"value": total, "asOf": str(sh.iloc[-1]["日期"]), "src": "沪深交易所",
            "extra": {"周变化%": float((total / prev - 1) * 100)}}


def fetch_northbound():
    df = ak.stock_hsgt_fund_flow_summary_em()
    nb = df[df["资金方向"] == "北向"]
    if not len(nb):
        raise ValueError("无北向数据")
    return {"value": float(nb["成交净买额"].sum()), "asOf": str(nb["交易日"].iloc[0]),
            "src": "沪深港通"}


def fetch_breadth():
    r = ak.stock_market_activity_legu().iloc[-1]
    up, down = float(r["上涨"]), float(r["下跌"])
    return {"value": up / (up + down) * 100, "asOf": str(r["日期"]), "src": "乐咕乐股",
            "extra": {"上涨家数": up, "下跌家数": down, "涨停": float(r.get("涨停", 0))}}


JOBS = {
    "pmi": (fetch_pmi, "制造业PMI"),
    "m1_yoy": (fetch_m1, "M1同比"),
    "credit_yoy": (fetch_credit, "新增信贷累计同比"),
    "lpr1y": (fetch_lpr, "LPR 1年期"),
    "cn10y": (None, "中债10Y"),
    "us10y": (None, "美债10Y"),
    "hs300": (fetch_tech, "沪深300技术面"),
    "hs300_pe": (fetch_valuation, "沪深300 PE"),
    "margin_yi": (fetch_margin, "两市融资余额"),
    "northbound": (fetch_northbound, "北向净买入"),
    "breadth_up": (fetch_breadth, "上涨家数占比"),
}


def sanity(key: str, obj: dict) -> dict | None:
    """越界 → 标 noData（保留原值供人工核对，但不参与打分）"""
    lo, hi = RANGES.get(key, (None, None))
    if lo is None:
        return obj
    v = obj.get("value")
    if v is None or not (lo <= float(v) <= hi):
        obj["noData"] = True
        obj["src"] = (obj.get("src", "") + " · 数值越界已隔离").strip(" ·")
        return obj
    return obj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(BASE_DIR, "macro.json"))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    log = print if not args.quiet else (lambda *a, **k: None)

    log(f"[INFO] 抓取开始 {dt.datetime.now():%Y-%m-%d %H:%M}")

    prev = {}
    if os.path.exists(args.out):
        try:
            prev = json.load(open(args.out, encoding="utf-8")).get("data", {})
        except Exception:  # noqa: BLE001
            prev = {}

    cn10 = us10 = None
    try:
        cn10, us10 = fetch_rates()
    except Exception as e:  # noqa: BLE001
        log(f"  [WARN] 国债收益率失败 {str(e)[:60]}")

    data, ok_n, failed = {}, 0, []
    for key, (fn, label) in JOBS.items():
        log(f"  → {label}")
        obj = None
        try:
            obj = ({"value": cn10["value"], "asOf": cn10["asOf"], "src": cn10["src"]}
                   if key == "cn10y" and cn10 else
                   {"value": us10["value"], "asOf": us10["asOf"], "src": us10["src"]}
                   if key == "us10y" and us10 else (fn() if fn else None))
        except Exception as e:  # noqa: BLE001
            log(f"    [WARN] {label} 失败：{type(e).__name__} {str(e)[:60]}")
        if obj is None:
            if key in prev:
                data[key] = dict(prev[key], stale=True)
            failed.append(label)
            continue
        data[key] = sanity(key, obj)
        ok_n += 1

    # 北向自 2024-08 起无实时披露，0 值等同缺失
    if data.get("northbound", {}).get("value") == 0:
        data["northbound"]["noData"] = True

    # ERP = 1/PE − 中债10Y
    if "hs300_pe" in data and "cn10y" in data:
        try:
            pe = float(data["hs300_pe"]["value"])
            cn = float(data["cn10y"]["value"])
            data["erp"] = {"value": round(100.0 / pe - cn, 3), "asOf": data["hs300_pe"]["asOf"],
                           "src": "计算值(1/PE − 中债10Y)", "extra": {"pe": pe, "cn10y": cn}}
        except Exception:  # noqa: BLE001
            pass

    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    json.dump({"generated_at": ts, "ok_count": ok_n, "total": len(JOBS), "failed": failed,
               "data": data}, open(args.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS macro(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, payload TEXT)""")
    con.execute("INSERT INTO macro(ts,payload) VALUES(?,?)", (ts, json.dumps(data, ensure_ascii=False)))
    con.execute("DELETE FROM macro WHERE id NOT IN (SELECT id FROM macro ORDER BY id DESC LIMIT 90)")
    con.execute("""CREATE TABLE IF NOT EXISTS fetch_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, ok INTEGER, total INTEGER, failed TEXT)""")
    con.execute("INSERT INTO fetch_log(ts,ok,total,failed) VALUES(?,?,?,?)",
                (ts, ok_n, len(JOBS), ",".join(failed)))
    con.execute("DELETE FROM fetch_log WHERE id NOT IN (SELECT id FROM fetch_log ORDER BY id DESC LIMIT 200)")
    con.commit()
    con.close()

    log(f"[DONE] 成功 {ok_n}/{len(JOBS)}｜失败 {failed or '无'} → {args.out} + {DB_PATH}")
    return 0 if ok_n >= len(JOBS) // 2 else 1


if __name__ == "__main__":
    sys.exit(main())
