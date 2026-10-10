#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
crowding_system.py —— 单文件版 ETF 拥挤度计算（对接 sector_rollup.py 契约）

依据《ETF 拥挤度指标系统》设计底稿（拥挤度README）方法论实现；详见底稿。
关键工程现实（已实测）：GitHub Actions 美区 runner 拉东方财富(eastmoney)接口常被拦/超时。
本文件：主源用东财(fund_etf_hist_em)，失败自动兜底新浪(fund_etf_daily / stock_zh_index_daily)，
并对每个 akshare 调用打印真实异常原因（便于排查），全程线程级超时防挂死。
若两源都不可达 → 0 有效结果 → 非 0 退出，Action 不推送坏数据，网页保持 demo/代理。
"""
import json
import os
import sys
import datetime
import socket
import concurrent.futures as cf

import numpy as np
import pandas as pd

try:
    import akshare as ak
except Exception as e:
    print("❌ akshare 不可用：%s" % e)
    sys.exit(1)

socket.setdefaulttimeout(45)

ETF_POOL = [
    ("588200", "科创芯片ETF"), ("159995", "芯片ETF"), ("512760", "半导体ETF"),
    ("159928", "主要消费ETF"), ("512690", "酒ETF"),
    ("159915", "创业板ETF"), ("588000", "科创50ETF"), ("588080", "科创50ETF"),
    ("513180", "恒生科技ETF"), ("513130", "恒生科技ETF"), ("513330", "恒生科技ETF"), ("159740", "恒生科技ETF"),
    ("512100", "中证1000ETF"), ("159845", "中证1000ETF"),
    ("512000", "券商ETF"), ("512070", "保险ETF"), ("510230", "金融ETF"), ("512900", "证券ETF"),
    ("512400", "有色金属ETF"), ("515220", "煤炭ETF"), ("161226", "国证有色"),
    ("512200", "房地产ETF"), ("160218", "地产ETF"),
    ("510880", "红利ETF"), ("515080", "红利ETF"), ("561580", "央企红利ETF"), ("515180", "红利ETF"),
    ("512010", "医药ETF"), ("159938", "医药卫生ETF"), ("512170", "医疗ETF"), ("512290", "生物医药ETF"),
    ("159611", "电力ETF"), ("561700", "电力ETF"), ("561160", "绿电ETF"),
    ("518880", "黄金ETF"), ("159934", "黄金ETF"), ("518800", "黄金ETF"),
    ("511010", "国债ETF"), ("511260", "十年债ETF"), ("511880", "短融ETF"), ("511270", "城投债ETF"),
    ("512660", "军工ETF"), ("512810", "军工ETF"),
    ("510300", "沪深300ETF"), ("510310", "沪深300ETF"), ("510330", "沪深300ETF"),
    ("515790", "光伏ETF"), ("516180", "光伏ETF"), ("516850", "光伏ETF"),
    ("159840", "锂电池ETF"),
    ("515030", "新能源车ETF"), ("516390", "新能源车ETF"), ("501057", "新能源车LOF"),
    ("513100", "纳指ETF"), ("161128", "纳指LOF"), ("161130", "纳斯达克100ETF"),
    ("513060", "恒生医疗ETF"), ("513660", "恒生ETF"), ("159920", "恒生ETF"),
]

PERCENTILE_WINDOWS = [120, 250, 500]
MIN_HISTORY = 60
CALL_TIMEOUT = 25
MAX_WORKERS = 4


def call_timeout(func, timeout=CALL_TIMEOUT, label=""):
    """线程里跑 func，超时/异常都打印原因并返回 None（绝不无限挂起，且不再吞异常）。"""
    with cf.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(func)
        try:
            return fut.result(timeout=timeout)
        except cf.TimeoutError:
            print("   ⏱ 超时(%ss): %s" % (timeout, label))
            return None
        except Exception as e:
            print("   ⚠ 异常: %s | %s" % (label, repr(e)[:200]))
            return None


def _sina_symbol(code):
    """ETF 代码 → 新浪代码（51/55/56/58 沪市 sh；15/16 深市 sz）。"""
    return ("sh" if code[:1] == "5" else "sz") + code


# ---------------------------------------------------------------------------
# 历史 K 线：东财主源 + 新浪兜底
# ---------------------------------------------------------------------------
def _fetch_em(code):
    df = ak.fund_etf_hist_em(symbol=code, period="daily", adjust="")
    if df is None or len(df) < MIN_HISTORY:
        return None
    df = df.copy()
    df["日期"] = pd.to_datetime(df["日期"])
    return df.sort_values("日期").reset_index(drop=True)


def _fetch_sina(code):
    df = ak.fund_etf_daily(symbol=_sina_symbol(code))
    if df is None or len(df) < MIN_HISTORY:
        return None
    df = df.copy()
    df["日期"] = pd.to_datetime(df["日期"])
    return df.sort_values("日期").reset_index(drop=True)


def fetch_hist(code):
    for src, fn in (("em", lambda: _fetch_em(code)), ("sina", lambda: _fetch_sina(code))):
        r = call_timeout(fn, CALL_TIMEOUT + 5, "hist:%s:%s" % (src, code))
        if r is not None and len(r) >= MIN_HISTORY:
            return r
    return None


def _bench_em():
    df = ak.index_zh_a_hist(symbol="000300", period="daily", adjust="")
    if df is None or len(df) < MIN_HISTORY:
        return None
    df = df.copy()
    df["日期"] = pd.to_datetime(df["日期"])
    return df.sort_values("日期").set_index("日期")["收盘"].astype(float)


def _bench_sina():
    df = ak.stock_zh_index_daily(symbol="sh000300")
    if df is None or len(df) < MIN_HISTORY:
        return None
    df = df.copy()
    df["日期"] = pd.to_datetime(df["日期"])
    return df.sort_values("日期").set_index("日期")["close"].astype(float)


def fetch_benchmark():
    for src, fn in (("em", _bench_em), ("sina", _bench_sina)):
        r = call_timeout(fn, CALL_TIMEOUT + 5, "bench:%s" % src)
        if r is not None:
            return r
    return None


def fetch_total_amount():
    """全市场 ETF 成交额（东财 spot），失败则 None（#10 指标跳过）。"""
    def _inner():
        spot = ak.fund_etf_spot_em()
        if spot is None or "成交额" not in spot.columns:
            return None
        return float(pd.to_numeric(spot["成交额"], errors="coerce").sum())
    return call_timeout(_inner, CALL_TIMEOUT + 5, "spot_total")


# ---------------------------------------------------------------------------
# 标准化 + 计算（与底稿一致：时间序列滚动百分位、分块等权、C_rel/p/三档信号）
# ---------------------------------------------------------------------------
def ts_percentile(series, windows=PERCENTILE_WINDOWS):
    s = pd.Series(series, dtype="float64").dropna()
    if len(s) < MIN_HISTORY:
        return float("nan")
    cur = s.iloc[-1]
    pris = []
    for w in windows:
        if len(s) < w:
            continue
        pris.append((s.iloc[-w:] < cur).mean())
    return float(np.median(pris)) if pris else float("nan")


def pct_of_return(close, horizon):
    close = pd.Series(close, dtype="float64")
    if len(close) < horizon + MIN_HISTORY:
        return float("nan")
    return ts_percentile(close.pct_change(horizon))


def compute_etf(df, bench_close, total_amount):
    try:
        close = pd.to_numeric(df["收盘"], errors="coerce").reset_index(drop=True)
        amount = pd.to_numeric(df["成交额"], errors="coerce").reset_index(drop=True) if "成交额" in df else None
        turn = pd.to_numeric(df["换手率"], errors="coerce").reset_index(drop=True) if "换手率" in df else None
    except Exception:
        return None

    ret = close.pct_change()
    vol = ret.rolling(60).std() * np.sqrt(252)

    s_list = []
    for h in (20, 60, 120):
        s_list.append(pct_of_return(close, h))
    if bench_close is not None:
        try:
            b = bench_close.reindex(df["日期"]).ffill()
            if len(b) == len(close):
                spread = close.pct_change(60) - b.diff(60)
                s_list.append(ts_percentile(spread.dropna()))
        except Exception:
            pass
    if turn is not None:
        s_list.append(ts_percentile(turn.rolling(20).mean().dropna()))
    if amount is not None and total_amount:
        try:
            s_list.append(ts_percentile((amount / total_amount).rolling(20).mean().dropna()))
        except Exception:
            pass
    s_list.append(ts_percentile(vol.dropna()))

    valid = [v for v in s_list if v == v]
    if len(valid) < 3:
        return None
    C = 100.0 * float(np.mean(valid))
    return round(min(max(C, 0.0), 100.0), 1)


def compute_one(args, bench_close, total_amount):
    code, name = args
    df = fetch_hist(code)
    if df is None:
        return None
    C = compute_etf(df, bench_close, total_amount)
    return {"code": code, "name": name, "C": C} if C is not None else None


def main():
    as_of = datetime.date.today().isoformat()
    bench = fetch_benchmark()
    total_amount = fetch_total_amount()
    print("ℹ 基准沪深300：%s | 全市场ETF成交额：%s" % (
        "OK" if bench is not None else "缺失(降级)",
        ("%.0f" % total_amount) if total_amount else "缺失(降级)"))

    results = []
    done = 0
    with cf.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(compute_one, a, bench, total_amount): a for a in ETF_POOL}
        for fut in cf.as_completed(futs):
            done += 1
            r = fut.result()
            if r:
                results.append(r)
            if done % 10 == 0 or done == len(ETF_POOL):
                print("   进度 %d/%d，已得有效 %d 只" % (done, len(ETF_POOL), len(results)))

    if not results:
        print("❌ 无有效 ETF 结果（两数据源可能均不可达），未产出 crowding_output.json；网页保持 demo/代理")
        sys.exit(1)

    Cs = np.array([x["C"] for x in results], dtype=float)
    M_t = float(np.median(Cs))
    for x in results:
        c = x["C"]
        crel = c - M_t
        p = float((Cs <= c).mean() * 100)
        regime = "high" if crel > 20 else ("low" if crel < -20 else "neutral")
        if c >= 90:
            signal = "sell"
        elif c <= 10:
            signal = "buy"
        elif p > 80:
            signal = "sell"
        elif p < 20:
            signal = "buy"
        else:
            signal = "watch"
        x["signal"] = signal
        x["regime"] = regime
        x["p"] = round(p, 1)

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crowding_output.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("✅ %s 计算 %d 只 ETF（候选 %d），M_t=%.1f，写入 %s" % (
        as_of, len(results), len(ETF_POOL), M_t, out))
    for x in sorted(results, key=lambda z: -z["C"])[:5]:
        print("     最拥挤 %s %s C=%s p=%s%% %s/%s" % (x["code"], x["name"], x["C"], x["p"], x["signal"], x["regime"]))
    for x in sorted(results, key=lambda z: z["C"])[:5]:
        print("     最不拥挤 %s %s C=%s p=%s%% %s/%s" % (x["code"], x["name"], x["C"], x["p"], x["signal"], x["regime"]))


if __name__ == "__main__":
    main()
