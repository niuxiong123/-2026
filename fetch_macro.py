#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观 / 估值 / 资金 / 海外风险 / 危机预警 数据抓取器（服务端）
------------------------------------------------
产出两处：
  1) niuxiong.db   → 表 macro（保留 90 天，供 /api/macro 与每日任务读取）
  2) macro.json    → 静态兜底（前端没后端时也能读）

新增模块（海外风险 + 危机预警）：
  - oil_brent / dxy / us_unemploy / nasdaq_pct / re_yoy  （自动抓取）
  - ai_bubble / hormuz_risk / paths_lit / win_proximity / china_fragile  （由真实数据推导，输出0-10分）

安全与健壮：
  - 每项独立 try，一项挂了不影响其它项；
  - 抓不到时沿用上一版数值并打 stale 标记（绝不凭空造数）；
  - 数值越过合理区间自动判定为脏数据并标 noData，不参与打分；
  - 失败项写入 fetch_log 表，供告警检查。
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
import time
import warnings
import requests

# 模块级日志（main 内会按 quiet 重新绑定；fetch_* 函数统一用此兜底）
log = print
warnings.filterwarnings("ignore")
import pandas as pd
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "niuxiong.db")
# 合理区间：越界视为脏数据
RANGES = {
    "pmi": (30, 60), "m1_yoy": (-10, 30), "credit_yoy": (-100, 100),
    "lpr1y": (1, 8), "cn10y": (0, 10), "us10y": (0, 15),
    "hs300_pe": (5, 60), "erp": (-5, 20), "margin_yi": (5000, 60000),
    "northbound": (-2000, 2000), "breadth_up": (0, 100),
    "oil_brent": (20, 200), "dxy": (70, 130), "us_unemploy": (2, 20),
    "nasdaq_pct": (-15, 15), "re_yoy": (-10, 10),
    "vix": (8, 80), "trade_balance": (-500, 2000),
    "ai_bubble": (0, 10), "hormuz_risk": (0, 10),
    "paths_lit": (0, 10), "win_proximity": (0, 10), "china_fragile": (0, 10),
    "hs300_pe_pct": (0, 100), "hs300_pb_pct": (0, 100),
    "hsi_pe_pct": (0, 100), "ah_premium": (-30, 150),
}
def _d(s):
    for f in ("%Y年%m月份", "%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
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

# ---------------- 原有宏观/估值/资金抓取 ----------------
def fetch_pmi():
    r = ak.macro_china_pmi().iloc[0]
    return {"value": float(r["制造业-指数"]), "asOf": _d(r["月份"]).isoformat(),
            "src": "国家统计局/东财"}
def fetch_m1():
    r = ak.macro_china_money_supply().iloc[0]
    return {"value": float(r["货币(M1)-同比增长"]), "asOf": _d(r["月份"]).isoformat(),
            "src": "央行/东财", "extra": {"m2_yoy": float(r["货币和准货币(M2)-同比增长"])}}
def fetch_credit():
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
def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()
def _macd_line(close, fast=12, slow=26):
    return _ema(close, fast) - _ema(close, slow)

def fetch_tech(symbol="sh000300"):
    df = ak.stock_zh_index_daily(symbol=symbol).dropna().tail(750).reset_index(drop=True)
    c = df["close"].astype(float)
    last = float(c.iloc[-1])
    ma = lambda n: float(c.tail(n).mean())
    hi, lo = float(c.tail(250).max()), float(c.tail(250).min())
    extra = {"ma20": ma(20), "ma60": ma(60), "ma250": ma(250),
             "chg_5d": float((last / float(c.iloc[-6]) - 1) * 100),
             "chg_20d": float((last / float(c.iloc[-21]) - 1) * 100),
             "chg_60d": float((last / float(c.iloc[-61]) - 1) * 100),
             "drawdown_from_250high": float((last / hi - 1) * 100),
             "pos_in_250range": float((last - lo) / (hi - lo) * 100),
             "above_ma250": bool(last > ma(250)), "ma20_gt_ma60": bool(ma(20) > ma(60))}
    # ---- 月/周线（改造③）：位置 + 站MA + 金叉 + 价/MACD 新高新低，供背离检测 ----
    # 任一步失败仅跳过月周线，不影响日线主指标
    try:
        import pandas as pd
        d = df.copy()
        d["date"] = pd.to_datetime(df["date"])
        d = d.set_index("date")["close"].astype(float)
        def period_block(rule, span, n):
            p = d.resample(rule).last().dropna().astype(float)
            if len(p) < span:
                return None
            ma_s = p.rolling(span).mean()
            ma_l = p.rolling(span * 3).mean()
            macd = _macd_line(p, 12, 26)
            cur = float(p.iloc[-1])
            win = p.tail(n)
            pos = float((cur - float(win.min())) / (float(win.max()) - float(win.min())) * 100)
            return {"pos": round(pos, 1),
                    "above_ma": bool(cur > float(ma_s.iloc[-1])),
                    "ma_cross": bool(float(ma_s.iloc[-1]) > float(ma_l.iloc[-1])),
                    "price_high": bool(cur >= float(p.tail(span).max())),
                    "macd_high": bool(float(macd.iloc[-1]) >= float(macd.tail(span).max())),
                    "price_low": bool(cur <= float(p.tail(span).min())),
                    "macd_low": bool(float(macd.iloc[-1]) <= float(macd.tail(span).min()))}
        m = period_block("ME", 12, 24)   # 月线：近24个月区间、近12月高低
        w = period_block("W", 12, 52)    # 周线：近52周区间、近12周高低
        if m:
            extra.update({f"m_{k}": v for k, v in m.items()})
        if w:
            extra.update({f"w_{k}": v for k, v in w.items()})
    except Exception:
        pass
    return {"value": last, "asOf": str(df["date"].iloc[-1]), "src": "新浪/东财", "extra": extra}
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
    df = ak.stock_market_activity_legu()
    m = dict(zip(df["item"].astype(str), df["value"]))
    up = float(m.get("上涨", 0))
    down = float(m.get("下跌", 0))
    if up + down == 0:
        raise ValueError("上涨家数占比：数据为空")
    return {"value": round(up / (up + down) * 100, 2), "asOf": str(m.get("统计日期", dt.date.today()))[:10],
            "src": "乐咕乐股", "extra": {"上涨家数": up, "下跌家数": down, "涨停": float(m.get("涨停", 0))}}

# ---------------- 新增：估值历史分位 / H股锚（改造②，让顶底判断有料可算） ----------------
_HS300_HIST = None
def _hs300_hist():
    """沪深300 估值历史（滚动市盈率）→ 最近 ~10 年；缓存避免重复请求"""
    global _HS300_HIST
    if _HS300_HIST is None:
        df = ak.stock_zh_index_hist_csindex(symbol="000300").dropna(subset=["滚动市盈率"]).copy()
        try:
            df["日期"] = pd.to_datetime(df["日期"])
            cutoff = df["日期"].max() - pd.DateOffset(months=120)
            df = df[df["日期"] >= cutoff]
        except Exception:
            pass
        _HS300_HIST = df.sort_values("日期", ascending=False).reset_index(drop=True)
    return _HS300_HIST

def fetch_hs300_pe_pct():
    """沪深300 PE 近10年历史分位（0-100，越高越贵）。
    中证历史估值接口滞后约2年，故把「历史滚动PE序列」与「当前市盈率1」拼成完整序列，
    以当前值算分位，保证顶底判断用的是当下估值而非2年前。"""
    df = _hs300_hist()
    if len(df) < 60:
        raise ValueError("估值历史过短")
    series = df["滚动市盈率"].astype(float).tolist()
    asof = str(df["日期"].iloc[0])[:10]
    try:
        cur = ak.stock_zh_index_value_csindex(symbol="000300").dropna(subset=["市盈率1"])
        cur_pe = float(cur["市盈率1"].iloc[-1]); asof = str(cur["日期"].iloc[-1])[:10]
        series.append(cur_pe)
    except Exception as e:
        log("[warn] 当前PE拼接失败，用历史末点: %s" % e)
    pct = float(pd.Series(series).rank(pct=True, ascending=True).iloc[-1]) * 100
    return {"value": round(pct, 1), "asOf": asof,
            "src": "中证·滚动PE(历史+当前拼接)10年分位"}

def fetch_hs300_pb_pct():
    """沪深300 PB 近10年分位无稳定直取接口，用 PE 分位作估值代理（标注）"""
    df = _hs300_hist()
    if len(df) < 60:
        raise ValueError("估值历史过短")
    series = df["滚动市盈率"].astype(float).tolist()
    try:
        cur = ak.stock_zh_index_value_csindex(symbol="000300").dropna(subset=["市盈率1"])
        series.append(float(cur["市盈率1"].iloc[-1]))
    except Exception:
        pass
    pct = float(pd.Series(series).rank(pct=True, ascending=True).iloc[-1]) * 100
    return {"value": round(pct, 1), "asOf": str(df["日期"].iloc[0])[:10],
            "src": "滚动PE分位(作PB代理)"}

def fetch_hsi_pe_pct():
    """恒生指数 PE 历史不可直接取，用收盘价格10年分位近似估值分位（H股锚，标注为代理）"""
    df = ak.stock_hk_index_daily_sina(symbol="HSI").dropna().tail(2600)
    if len(df) < 250:
        raise ValueError("恒生历史过短")
    c = df["close"].astype(float)
    cur = float(c.iloc[-1]); hi, lo = float(c.max()), float(c.min())
    pct = (cur - lo) / (hi - lo) * 100
    return {"value": round(pct, 1), "asOf": str(df["date"].iloc[-1])[:10],
            "src": "恒生收盘10年分位(PE代理)"}

def _fetch_ah_premium_index():
    """兜底源：恒生AH溢价指数(HSAHP)，点位 X = A比H贵 (X-100)%。
    用 akshare 的港股指数日线（内部走东财 kline 接口，与比价板 clist 不同路径）。"""
    for attempt in range(3):
        try:
            df = ak.stock_hk_index_daily_em(symbol="HSAHP").dropna()
            if len(df) and "close" in df.columns:
                lvl = float(df["close"].iloc[-1])
                return lvl - 100.0   # 溢价%
        except Exception:
            time.sleep(6); continue
    return None

def fetch_ah_premium():
    """AH溢价中位数（%）：A股相对H股贵多少。H股独立估值锚核心字段。
    主源：东财 AH 比价接口（stock_zh_ah_spot_em），502等为瞬时错误→重试5次抗抖动。
    兜底：恒生AH溢价指数点位(HSAHP)-100。仍失败返回 None，由 HTML 走恒生代理，绝不写脏数。"""
    df = None
    for attempt in range(5):
        try:
            df = ak.stock_zh_ah_spot_em()
            break
        except Exception as e:
            if attempt < 4:
                time.sleep(10); continue
            log("[warn] AH溢价主源失败: %s" % e)
    if df is not None and len(df):
        prem_col = next((c for c in df.columns if "溢价" in c), None)
        if prem_col is not None:
            r = pd.to_numeric(df[prem_col], errors="coerce").dropna()
            r = r[(r > 0) & (r < 60)]
            if len(r):
                median_ratio = float(r.median())   # H/A 价格比，如 0.83
                # 比值(<3)→换算溢价%；已是百分比(>3)→直接用
                prem = (1.0 / median_ratio - 1.0) * 100 if median_ratio < 3 else median_ratio
                return {"value": round(prem, 1), "asOf": str(dt.date.today()),
                        "src": "东财·AH溢价中位数"}
    # 主源无果 → 恒生AH溢价指数兜底
    idx = _fetch_ah_premium_index()
    if idx is not None:
        return {"value": round(idx, 1), "asOf": str(dt.date.today()),
                "src": "恒生AH溢价指数(点位-100)"}
    log("[warn] AH溢价抓取失败，走兜底(None)")
    return None

# ---------------- 新增：海外风险维度自动抓取 ----------------
def fetch_oil_brent():
    """布伦特原油价（美元/桶）—— 地缘/通胀核心变量"""
    # 优先用 OIL（布伦特原油期货），CL（WTI）作为降级
    for sym, src in [("OIL", "akshare·布伦特原油期货"), ("CL", "akshare·WTI原油期货")]:
        try:
            df = ak.futures_foreign_hist(symbol=sym).dropna(subset=["close"])
            if len(df):
                v = float(df.iloc[-1]["close"])
                return {"value": round(v, 2), "asOf": str(df.iloc[-1]["date"])[:10], "src": src}
        except Exception:
            continue
    raise RuntimeError("油价抓取失败: OIL/CL 均不可用")

def fetch_dxy():
    """美元指数 DXY —— 新兴市场压力指标"""
    try:
        # 新浪行情美元指数 DINIW
        import urllib.request
        req = urllib.request.Request("https://hq.sinajs.cn/list=DINIW",
                                     headers={"Referer": "https://finance.sina.com.cn"})
        raw = urllib.request.urlopen(req, timeout=10).read().decode("gbk", errors="ignore")
        parts = raw.split('"')[1].split(",")
        # parts: [时间, 当前价, 买价, 卖价, 成交量, ..., 名称, 日期]
        if len(parts) > 1:
            v = float(parts[1])
            asOf = parts[-1] if len(parts) > 3 else str(dt.date.today())
            return {"value": round(v, 2), "asOf": asOf, "src": "新浪行情·DINIW"}
    except Exception:
        pass
    raise RuntimeError("美元指数抓取失败: 新浪DINIW不可用")

def fetch_us_unemploy():
    """美国失业率（%）—— 就业稳健度，反向指标"""
    df = ak.macro_usa_unemployment_rate()
    # 列名可能是"今值"，取最后一个非空值
    val_col = "今值" if "今值" in df.columns else "失业率"
    df = df.dropna(subset=[val_col])
    if not len(df):
        raise ValueError("美国失业率：无有效数据")
    r = df.iloc[-1]
    return {"value": float(r[val_col]), "asOf": str(r["日期"]), "src": "BLS/东财"}

def fetch_nasdaq_pct():
    """纳斯达克近20日涨跌幅（%）—— AI/科技估值代理"""
    df = ak.index_us_stock_sina(symbol=".IXIC").tail(21)
    last = float(df.iloc[-1]["close"])
    prev = float(df.iloc[-21]["close"]) if len(df) >= 21 else last
    pct = (last / prev - 1) * 100
    return {"value": round(pct, 2), "asOf": str(df.iloc[-1]["date"]),
            "src": "新浪·纳斯达克", "extra": {"nasdaq_close": last}}

def fetch_re_yoy():
    """房地产景气指数近1年涨跌幅（%）—— 中国脆弱点核心代理"""
    df = ak.macro_china_real_estate()
    r = df.iloc[-1]
    # 国房景气指数近1年涨跌幅作为地产热度代理
    return {"value": round(float(r["近1年涨跌幅"]), 2), "asOf": str(r["日期"])[:10],
            "src": "东财·国房景气指数"}

def fetch_vix():
    """CBOE VIX 恐慌指数 —— 全球风险偏好/金融传染核心指标
    数据源：腾讯行情 usVIX（与前端实时同源，保证口径一致）。
    该接口返回 CBOE 官方 VIX 指数，延迟约 15 分钟，对宏观日度判断足够准确。"""
    import urllib.request
    req = urllib.request.Request("https://qt.gtimg.cn/q=usVIX",
                                 headers={"Referer": "https://gu.qq.com"})
    raw = urllib.request.urlopen(req, timeout=10).read().decode("gbk", errors="ignore")
    # v_usVIX="200~标普500波动率指数~.VIX~21.67~...~2026-09-14 09:30:00~..."
    body = raw.split('"')[1] if '"' in raw else ""
    parts = body.split("~")
    if len(parts) < 4:
        raise ValueError("VIX 解析失败: " + raw[:80])
    v = float(parts[3])
    if v <= 0:
        raise ValueError("VIX 数值异常: " + str(v))
    asOf = parts[30] if len(parts) > 30 else str(dt.date.today())
    return {"value": round(v, 2), "asOf": str(asOf)[:10], "src": "腾讯行情·CBOE VIX"}

def fetch_trade_balance():
    """中国贸易帐（亿美元）—— 一带一路/出口回款代理：顺差越大→外汇回款越充足"""
    df = ak.macro_china_trade_balance().dropna(subset=["今值"])
    if not len(df):
        raise ValueError("贸易帐：无有效数据")
    r = df.iloc[-1]
    return {"value": float(r["今值"]), "asOf": str(r["日期"])[:10],
            "src": "海关总署/东财", "extra": {"前值": float(r["前值"]) if not _is_nan(r["前值"]) else None}}

def _is_nan(x):
    try:
        import math
        return math.isnan(float(x))
    except Exception:
        return True

# ---------------- 新增：危机预警维度推导（由真实数据算0-10分） ----------------
def score_ai_bubble(nasdaq_pct, us10y, vix=None):
    """AI泡沫风险分：纳指短期涨幅越大 + 美债越高 → 泡沫越危险"""
    s = 5.0
    # 纳指20日涨幅
    if nasdaq_pct is not None:
        s += min(max(nasdaq_pct, -10), 10) * 0.3   # +10%涨→+3分
    # 美债收益率高→融资成本高→泡沫易破
    if us10y is not None:
        s += (us10y - 4.0) * 0.8 if us10y > 4.0 else 0
    # VIX高→已在释放风险，略降
    if vix is not None and vix > 25:
        s -= 1.0
    return round(max(0, min(10, s)), 1)

def score_hormuz_risk(oil_brent, nasdaq_pct=None):
    """海峡/供应链风险分：油价越高→地缘冲突推升油价的可能性越大"""
    if oil_brent is None:
        return 5.0
    s = 2.0 + (oil_brent - 60) * 0.12   # 60美元→2分, 100→6.8分, 120→9.2分
    return round(max(0, min(10, s)), 1)

def score_paths_lit(oil_brent, ai_bubble, vix, china_fragile):
    """四路径点燃度：地缘(油价) + AI泡沫 + 金融传染(VIX) + 中国脆弱点 综合"""
    parts = []
    if oil_brent is not None:
        parts.append(min(max((oil_brent - 60) / 60 * 10, 0), 10))   # 地缘路径
    if ai_bubble is not None:
        parts.append(ai_bubble)                                        # AI泡沫路径
    if vix is not None:
        parts.append(min(max((vix - 15) / 20 * 10, 0), 10))         # 金融传染路径
    if china_fragile is not None:
        parts.append(china_fragile)                                   # 中国内部路径
    if not parts:
        return 5.0
    return round(sum(parts) / len(parts), 1)

def score_win_proximity(today=None):
    """高危窗口临近度：2026Q4-2027Q2 为高危窗，按距离算0-10分"""
    today = today or dt.date.today()
    # 高危窗口中心：2027-03-31
    center = dt.date(2027, 3, 31)
    days = abs((today - center).days)
    if days <= 90:      # 窗口内
        return 10.0
    elif days <= 270:   # 窗口前后9个月
        return round(10 - (days - 90) / 180 * 5, 1)   # 线性降到5
    else:
        return round(max(1, 5 - (days - 270) / 365 * 3), 1)   # 远离窗口降到1-2

def score_china_fragile(re_yoy):
    """中国脆弱点：国房景气指数近1年跌幅越大→越脆弱
    re_yoy 为景气指数1年涨跌幅（典型区间 -3%~+3%），负值越深越危险"""
    if re_yoy is None:
        return 5.0
    s = 5.0 - re_yoy * 1.5   # -3%→9.5分, -1.2%→6.8分, 0%→5分, +3%→0.5分
    return round(max(0, min(10, s)), 1)

# ---------------- 任务表 ----------------
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
    # 新增：海外风险
    "oil_brent": (fetch_oil_brent, "布伦特油价"),
    "dxy": (fetch_dxy, "美元指数"),
    "us_unemploy": (fetch_us_unemploy, "美国失业率"),
    "nasdaq_pct": (fetch_nasdaq_pct, "纳斯达克20日涨跌"),
    "re_yoy": (fetch_re_yoy, "国房景气指数1Y涨跌"),
    "vix": (fetch_vix, "CBOE VIX恐慌指数"),
    "trade_balance": (fetch_trade_balance, "中国贸易帐"),
    # 新增：估值历史分位 + H股锚（改造②喂料）
    "hs300_pe_pct": (fetch_hs300_pe_pct, "沪深300 PE分位"),
    "hs300_pb_pct": (fetch_hs300_pb_pct, "沪深300 PB分位"),
    "hsi_pe_pct": (fetch_hsi_pe_pct, "恒生PE分位(代理)"),
    "ah_premium": (fetch_ah_premium, "AH溢价"),
}

def sanity(key: str, obj: dict) -> dict | None:
    lo, hi = RANGES.get(key, (None, None))
    if lo is None:
        return obj
    v = obj.get("value")
    if v is None or not (lo <= float(v) <= hi):
        obj["noData"] = True
        obj["src"] = (obj.get("src", "") + " · 数值越界已隔离").strip(" ·")
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
        except Exception:
            prev = {}
    cn10 = us10 = None
    try:
        cn10, us10 = fetch_rates()
    except Exception as e:
        log(f"  [WARN] 国债收益率失败 {str(e)[:60]}")
    data, ok_n, failed = {}, 0, []
    import time as _time
    def _retry(fn, tries=3, base=1.0):
        """可控重试单元：固定次数 + 指数退避，最终失败原因透传"""
        last_err = None
        for i in range(tries):
            try:
                return fn()
            except Exception as e:
                last_err = e
                if i < tries - 1:
                    _time.sleep(base * (2 ** i))
        raise last_err
    for key, (fn, label) in JOBS.items():
        log(f"  → {label}")
        obj = None
        try:
            if key == "cn10y" and cn10:
                obj = {"value": cn10["value"], "asOf": cn10["asOf"], "src": cn10["src"]}
            elif key == "us10y" and us10:
                obj = {"value": us10["value"], "asOf": us10["asOf"], "src": us10["src"]}
            elif fn:
                obj = _retry(fn)
        except Exception as e:
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
        except Exception:
            pass

    # ===== 新增：危机预警维度推导（由已抓取的真实数据计算）=====
    oil_v = data.get("oil_brent", {}).get("value")
    nq_v = data.get("nasdaq_pct", {}).get("value")
    us10_v = data.get("us10y", {}).get("value")
    re_v = data.get("re_yoy", {}).get("value")
    # VIX 从行情代理传入（可选），这里尝试从 macro data 取
    vix_v = data.get("vix", {}).get("value") if "vix" in data else None

    # AI泡沫
    data["ai_bubble"] = {
        "value": score_ai_bubble(nq_v, us10_v, vix_v),
        "asOf": data.get("nasdaq_pct", data.get("us10y", {})).get("asOf", str(dt.date.today())),
        "src": "推导(纳指涨跌+美债)"
    }
    # 海峡风险
    data["hormuz_risk"] = {
        "value": score_hormuz_risk(oil_v),
        "asOf": data.get("oil_brent", {}).get("asOf", str(dt.date.today())),
        "src": "推导(布伦特油价)"
    }
    # 中国脆弱点
    china_frag = score_china_fragile(re_v)
    data["china_fragile"] = {
        "value": china_frag,
        "asOf": data.get("re_yoy", {}).get("asOf", str(dt.date.today())),
        "src": "推导(国房景气指数)"
    }
    # 四路径点燃度
    ai_b = data["ai_bubble"]["value"]
    data["paths_lit"] = {
        "value": score_paths_lit(oil_v, ai_b, vix_v, china_frag),
        "asOf": str(dt.date.today()),
        "src": "推导(油价+AI泡沫+VIX+脆弱点)"
    }
    # 高危窗口临近度
    data["win_proximity"] = {
        "value": score_win_proximity(),
        "asOf": str(dt.date.today()),
        "src": "计算(日期距2027Q1)"
    }

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
