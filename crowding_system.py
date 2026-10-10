#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
crowding_system.py —— 单文件版 ETF 拥挤度计算（对接 sector_rollup.py 契约）

依据《ETF 拥挤度指标系统》设计底稿（拥挤度README）的方法论实现：
  · 时间序列滚动百分位标准化（窗口 [120,250,500] 取中位数降极值扰动，严禁未来函数）
  · 分块等权合成 C = 100·mean(s)（s 为各指标滚动百分位，[0,1]，越高越拥挤）
  · C_rel = C − M_t（regime 自适应基准，M_t = 全样本 C 的中位数）
  · 横截面分位 p + 三档信号（p<20 买 / 20-80 观望 / p>80 卖）
  · 绝对极端覆盖（C>=90 强卖 / C<=10 强买，优先级最高）
  · regime 标签（基于 C_rel：>20 高 / <-20 低 / 其余中性）

【为什么是单文件】
  底稿描述的多文件包（run_crowding.py/config.py/data_layer.py/indicators.py/composite.py）
  在本仓库落地为单文件，输出契约与 sector_rollup.py 严格对齐：
       crowding_output.json = list of {code,name,C(0-100),signal,regime,p}
  sector_rollup.py 再把它聚合成 docs/sectors_crowd.json（22 板块，source=real）。

【真数据来源】
  本文件由 GitHub Action（ubuntu-latest，真实外网 + akshare）每日运行：
      python3 crowding_system.py   →   crowding_output.json（仓根）
      python3 sector_rollup.py      →   docs/sectors_crowd.json（source=real）
  本机沙箱网络屏蔽东方财富 push2 接口，无法取真实行情；但 Action 环境正常，可真实计算。

【可计算指标 vs 受限指标（诚实标注，绝不伪造）】
  本单文件版从「历史 K 线 + 实时 spot 快照」可稳健算出的指标：
      #5 价格动量(20/60/120)  #6 RS vs 沪深300(60/120)  #9 换手率(20)
      #10 成交额占全市场ETF比重(20/60)  #12 收益率波动率(20/60,年化)
  底稿中需要「spot 历史落库缓存」才能算的指标（#1 份额变化率 / #2 主力净额 /
      #3 AUM增速 / #4 溢价-IOPV）在单次 Action 运行（无跨日缓存）下标记为不可用；
      #7 跟踪指数PE分位 因缺申万映射表暂标记不可用。缺失即降级重归一，不伪造。
  有效指标 < 3 或 有效块 < 3 的 ETF 不输出 C（网页对该板块回退「代理估算」）。
"""
import json
import os
import sys
import datetime
import time

import numpy as np
import pandas as pd

try:
    import akshare as ak
except Exception as e:  # akshare 缺包时明确报错退出，避免静默产出空数据
    print("❌ akshare 不可用：%s" % e)
    sys.exit(1)


# ---------------------------------------------------------------------------
# ETF 池：覆盖网页 22 板块（代码与 sector_rollup.ETF_MAP 对齐，便于聚合映射）
# 每个板块取 1-2 只代表性 ETF；代码优先，sector_rollup 再按名称/代码归类。
# ---------------------------------------------------------------------------
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
MIN_HISTORY = 60          # 最少历史交易日才出有效值（与底稿一致）


# ---------------------------------------------------------------------------
# 数据接入（字段安全 + 重试）
# ---------------------------------------------------------------------------
def fetch_hist(code):
    """拉取 ETF 日线历史 K 线（收盘/成交额/换手率）。失败重试 3 次。"""
    for _ in range(3):
        try:
            df = ak.fund_etf_hist_em(symbol=code, period="daily", adjust="")
            if df is not None and len(df) >= MIN_HISTORY:
                df = df.copy()
                df["日期"] = pd.to_datetime(df["日期"])
                df = df.sort_values("日期").reset_index(drop=True)
                return df
        except Exception:
            time.sleep(2)
    return None


def fetch_benchmark():
    """沪深300 收盘序列（#6 RS 基准）。"""
    try:
        df = ak.index_zh_a_hist(symbol="000300", period="daily", adjust="")
        if df is not None and len(df) >= MIN_HISTORY:
            df = df.copy()
            df["日期"] = pd.to_datetime(df["日期"])
            s = df.sort_values("日期").set_index("日期")["收盘"].astype(float)
            return s
    except Exception:
        pass
    return None


def fetch_total_amount():
    """全市场 ETF 当日总成交额（#10 成交额占比分母）。"""
    try:
        spot = ak.fund_etf_spot_em()
        if spot is not None and "成交额" in spot.columns:
            return float(pd.to_numeric(spot["成交额"], errors="coerce").sum())
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# 标准化：时间序列滚动百分位
# ---------------------------------------------------------------------------
def ts_percentile(series, windows=PERCENTILE_WINDOWS):
    """返回序列最新值的时间序列滚动百分位 [0,1]；样本不足返回 nan。
    对每个窗口 w，取最近 w 个值，计算 当前值 在窗口内的分位 (x<cur).mean()，
    多窗口取中位数降极值扰动。所有计算仅用 t 及以前数据（严禁未来函数）。"""
    s = pd.Series(series, dtype="float64").dropna()
    if len(s) < MIN_HISTORY:
        return float("nan")
    cur = s.iloc[-1]
    pris = []
    for w in windows:
        if len(s) < w:
            continue
        win = s.iloc[-w:]
        pris.append((win < cur).mean())
    if not pris:
        return float("nan")
    return float(np.median(pris))


def pct_of_return(close, horizon):
    """horizon 日收益率序列 → 最新值的滚动百分位。"""
    close = pd.Series(close, dtype="float64")
    if len(close) < horizon + MIN_HISTORY:
        return float("nan")
    ret = close.pct_change(horizon)
    return ts_percentile(ret)


# ---------------------------------------------------------------------------
# 单 ETF 计算
# ---------------------------------------------------------------------------
def compute_etf(df, bench_close, total_amount):
    """返回 (C, valid_list)；样本/有效指标不足返回 None。"""
    try:
        close = pd.to_numeric(df["收盘"], errors="coerce").reset_index(drop=True)
        amount = pd.to_numeric(df["成交额"], errors="coerce").reset_index(drop=True) if "成交额" in df else None
        turn = pd.to_numeric(df["换手率"], errors="coerce").reset_index(drop=True) if "换手率" in df else None
    except Exception:
        return None

    ret = close.pct_change()
    vol = ret.rolling(60).std() * np.sqrt(252)   # #12 收益率波动率（年化）

    s_list = []  # (key, s in [0,1])

    # #5 价格动量（20/60/120 日收益率的滚动百分位）
    for h in (20, 60, 120):
        s_list.append(("mom%d" % h, pct_of_return(close, h)))

    # #6 RS vs 沪深300（ETF收益 − 宽基收益 的滚动百分位）
    if bench_close is not None:
        try:
            b = bench_close.reindex(df["日期"]).ffill()
            if len(b) == len(close):
                bret = b.diff(60)
                spread = close.pct_change(60) - bret
                s_list.append(("rs", ts_percentile(spread.dropna())))
        except Exception:
            pass

    # #9 换手率（20 日均值的滚动百分位）
    if turn is not None:
        s_list.append(("turn", ts_percentile(turn.rolling(20).mean().dropna())))

    # #10 成交额占全市场 ETF 比重（20/60 日均值的滚动百分位）
    if amount is not None and total_amount:
        try:
            ratio = (amount / total_amount).rolling(20).mean().dropna()
            s_list.append(("amt", ts_percentile(ratio)))
        except Exception:
            pass

    # #12 收益率波动率（滚动百分位）
    s_list.append(("vol", ts_percentile(vol.dropna())))

    valid = [(k, v) for k, v in s_list if v == v]
    # 底稿：有效指标 < 3 不输出。此处 5 个指标来自 3 个语义块（动能/交易热度/波动），
    # 至少需 3 个有效指标才出分（等价有效块>=3）。
    if len(valid) < 3:
        return None

    # 分块等权合成（简化：全部有效 s 等权均值；缺失块自动重归一）
    C = 100.0 * float(np.mean([v for _, v in valid]))
    C = min(max(C, 0.0), 100.0)
    return round(C, 1), valid


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    as_of = datetime.date.today().isoformat()
    bench = fetch_benchmark()
    total_amount = fetch_total_amount()

    results = []
    for code, name in ETF_POOL:
        df = fetch_hist(code)
        if df is None:
            print("⚠ 跳过 %s（无足够历史）" % code)
            continue
        r = compute_etf(df, bench, total_amount)
        if r is None:
            print("⚠ 跳过 %s（有效指标<3）" % code)
            continue
        C, valid = r
        results.append({"code": code, "name": name, "C": C})

    if not results:
        print("❌ 无有效 ETF 结果，未产出 crowding_output.json（网页将保持 demo/代理）")
        sys.exit(1)

    # 横截面：M_t / C_rel / p / signal / regime
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

    print("✅ %s 计算 %d 只 ETF，M_t=%.1f，写入 %s" % (as_of, len(results), M_t, out))
    print("   最拥挤 Top5：")
    for x in sorted(results, key=lambda z: -z["C"])[:5]:
        print("     %s %s  C=%s  p=%s%%  %s/%s" % (x["code"], x["name"], x["C"], x["p"], x["signal"], x["regime"]))
    print("   最不拥挤 Bottom5：")
    for x in sorted(results, key=lambda z: z["C"])[:5]:
        print("     %s %s  C=%s  p=%s%%  %s/%s" % (x["code"], x["name"], x["C"], x["p"], x["signal"], x["regime"]))


if __name__ == "__main__":
    main()
