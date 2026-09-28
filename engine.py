# -*- coding: utf-8 -*-
"""
打分与仓位引擎（服务端单一真相源）
------------------------------------------------
前端 JS 里有一份等价实现，用于「没后端时」降级本地计算。
调阈值时请两边一起改 —— 常量集中在本文件顶部，方便对照。

输入：macro 数据（fetch_macro.py 产出）+ 实时行情 + 定性项
输出：温度、四维分、四道约束、最终仓位、牛熊钟落点
"""
from __future__ import annotations

import datetime as dt
from typing import Any

# ---------------- 可调阈值 ----------------
W_A = {"trend": .25, "val": .25, "liq": .25, "emo": .25}      # A股四维权重
W_H = {"trend": .20, "val": .20, "liq": .30, "emo": .30}      # H股：海外/情绪权重更高
BASE_ANCHORS = [(0, 9.0), (2.5, 8.0), (5.0, 5.5), (7.5, 3.0), (10, 1.0)]  # 温度→基础仓位
ERP_ANCHORS = [(6, 0.5), (5, 1.5), (4, 3.0), (3, 4.5), (2, 6.0), (1, 7.5)]  # ERP越高越便宜
CAP_TREND_BAD = 5.5        # 跌破年线且空头排列
CAP_CREDIT_BAD = 6.0       # M1<5% 或 信贷同比<0
CAP_OVERSEA = {"A": 7.0, "H": 5.5}   # 美债10Y >= 4.5%
CAP_RESON_LOW = 5.5        # 八大信号达成 < 50%
CONSERVATIVE = 0.85        # 命理保守系数（风险厌恶 + 财杀流年）
M1_GATE = 5.0
US10Y_GATE = 4.5
AMT_3WAN = 30000.0         # 两市成交额 3 万亿（亿元）


# ---------------- 小工具 ----------------
def clamp(x: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, x))


def lerp(x, x1, y1, x2, y2):
    if x2 == x1:
        return y1
    t = (x - x1) / (x2 - x1)
    return y1 + (y2 - y1) * max(0.0, min(1.0, t))


def piece_anchor(x: float, anchors, default_low, default_high):
    """anchors: [(阈值, 分数)] 从大到小排列的插值锚点"""
    for i in range(len(anchors) - 1):
        hi, hi_s = anchors[i]
        lo, lo_s = anchors[i + 1]
        if lo <= x < hi:
            return lerp(x, lo, lo_s, hi, hi_s)
    return default_low if x >= anchors[0][0] else default_high


def val_of(item: Any):
    """macro 里的项可能是 {value,asOf,src} 或裸值"""
    if item is None:
        return None
    if isinstance(item, dict):
        v = item.get("value")
        if item.get("noData") or item.get("baseline"):
            return None          # 占位/无披露：不参与打分
        return v
    return item


def real(data: dict, key: str):
    return key in data and val_of(data[key]) is not None


# ---------------- 四维打分 ----------------
def score_trend(data: dict, quote: dict | None, mode: str):
    tech = (data.get("hs300") or {}).get("extra") or {}
    why = []
    if tech.get("pos_in_250range") is not None:
        s = 0.5 + (float(tech["pos_in_250range"]) / 100) * 8
        why.append(f"年内位置 {float(tech['pos_in_250range']):.0f}%")
        s += 1 if tech.get("above_ma250") else -0.5
        why.append("站上年线" if tech.get("above_ma250") else "跌破年线")
        s += 0.5 if tech.get("ma20_gt_ma60") else -0.5
        why.append("MA20>MA60" if tech.get("ma20_gt_ma60") else "MA20<MA60")
        if tech.get("chg_60d") is not None:
            why.append(f"60日 {float(tech['chg_60d']):.1f}%")
        if tech.get("drawdown_from_250high") is not None:
            why.append(f"距年内高点 {float(tech['drawdown_from_250high']):.1f}%")
    else:
        pct = (quote or {}).get("hs300_pct" if mode == "A" else "hsi_pct") or 0.0
        s = 5 - pct * 1.2
        why.append(f"无均线数据，按当日 {pct:+.2f}% 粗判")
    return clamp(s), " · ".join(why)


def score_val(data: dict):
    erp = val_of(data.get("erp"))
    if erp is None:
        return 5.0, "ERP 缺失→中性"
    s = piece_anchor(float(erp), ERP_ANCHORS, 0.5, 9.0)
    pe = val_of(data.get("hs300_pe"))
    why = f"ERP {float(erp):.2f}%（越高越便宜）"
    if pe is not None:
        why += f" · 沪深300 PE {pe}"
    return clamp(s), why


def score_liq(data: dict, quote: dict | None):
    parts, why = [], []
    if real(data, "m1_yoy"):
        m1 = float(val_of(data["m1_yoy"]))
        s = 8 if m1 >= 8 else (lerp(m1, 6, 6, 8, 8) if m1 >= 6 else
                               (lerp(m1, 4, 4.5, 6, 6) if m1 >= 4 else
                                (lerp(m1, 3, 3.5, 4, 4.5) if m1 >= 3 else 2.5)))
        parts.append((s, 1.2)); why.append(f"M1 {m1}%")
    if real(data, "credit_yoy"):
        cr = float(val_of(data["credit_yoy"]))
        s = 1 if cr < -20 else (lerp(cr, -20, 1, 0, 3) if cr < 0 else
                                (lerp(cr, 0, 3, 20, 5) if cr <= 20 else 7))
        parts.append((s, 1.0)); why.append(f"信贷同比 {cr:.1f}%")
    if real(data, "cn10y"):
        cn = float(val_of(data["cn10y"]))
        s = 2 if cn < 1.5 else (lerp(cn, 1.5, 2, 2.5, 4) if cn < 2.5 else
                                (lerp(cn, 2.5, 4, 3.5, 6) if cn < 3.5 else 8))
        parts.append((s, .8)); why.append(f"中债10Y {cn}%")
    if real(data, "margin_yi"):
        mg = (data["margin_yi"].get("extra") or {}).get("周变化%")
        if mg is not None:
            mg = float(mg)
            s = 8 if mg > 3 else (lerp(mg, 1, 6.5, 3, 8) if mg > 1 else
                                  (lerp(mg, -1, 5, 1, 6.5) if mg >= -1 else 3.5))
            parts.append((s, .8)); why.append(f"两融周变化 {mg:.2f}%")
    amt = (quote or {}).get("amt_yi")
    if amt:
        amt = float(amt)
        s = 8 if amt >= 30000 else (lerp(amt, 20000, 6.5, 30000, 8) if amt >= 20000 else
                                    (lerp(amt, 12000, 5, 20000, 6.5) if amt >= 12000 else
                                     (lerp(amt, 8000, 3.5, 12000, 5) if amt >= 8000 else 2.5)))
        parts.append((s, 1.2)); why.append(f"两市成交额 {amt/10000:.2f}万亿")
    if not parts:
        return 5.0, "流动性数据缺失→中性"
    sw = sum(w for _, w in parts)
    return clamp(sum(s * w for s, w in parts) / sw), " · ".join(why)


def score_emo(data: dict, quote: dict | None, mode: str):
    parts, why = [], []
    if real(data, "breadth_up"):
        bu = float(val_of(data["breadth_up"]))
        s = 8 if bu > 70 else (lerp(bu, 55, 6.5, 70, 8) if bu > 55 else
                               (lerp(bu, 45, 5, 55, 6.5) if bu >= 45 else
                                (lerp(bu, 30, 3.5, 45, 5) if bu >= 30 else 2)))
        parts.append((s, 1.3)); why.append(f"上涨家数占比 {bu:.0f}%")
    vix = (quote or {}).get("vix")
    if vix:
        vix = float(vix)
        s = 8 if vix < 15 else (lerp(vix, 15, 8, 20, 6.5) if vix < 20 else
                                (lerp(vix, 20, 6.5, 25, 5) if vix < 25 else
                                 (lerp(vix, 25, 5, 30, 3.5) if vix < 30 else 2)))
        parts.append((s, 1.0)); why.append(f"VIX {vix:.1f}")
    pct = (quote or {}).get("hs300_pct" if mode == "A" else "hsi_pct")
    if pct is not None:
        parts.append((clamp(5 - float(pct) * 1.5), .7)); why.append(f"当日 {float(pct):+.2f}%")
    if real(data, "northbound"):
        nb = float(val_of(data["northbound"]))
        s = 8 if nb > 80 else (lerp(nb, 20, 6.5, 80, 8) if nb > 20 else
                               (lerp(nb, -20, 5, 20, 6.5) if nb > -20 else 3.5))
        parts.append((s, .6)); why.append(f"北向 {nb:.0f}亿")
    if not parts:
        return 5.0, "情绪数据缺失→中性"
    sw = sum(w for _, w in parts)
    return clamp(sum(s * w for s, w in parts) / sw), " · ".join(why)


# ---------------- 八大信号 / 牛熊钟 / 仓位 ----------------
EIGHT_KEYS = ["M1回升6%+", "社融/信贷止跌", "住户存款放缓", "消费税后移试点",
              "一带一路回款", "地产降幅收窄", "A股日均3万亿", "海外贴现率缓和"]


def eight_states(data: dict, quote: dict | None):
    st = {k: 2 for k in EIGHT_KEYS}          # 默认临界
    if real(data, "m1_yoy"):
        st["M1回升6%+"] = 1 if float(val_of(data["m1_yoy"])) >= 6 else 3
    if real(data, "credit_yoy"):
        cr = float(val_of(data["credit_yoy"]))
        st["社融/信贷止跌"] = 1 if cr > 0 else (2 if cr > -10 else 3)
    amt = (quote or {}).get("amt_yi")
    if amt:
        amt = float(amt)
        st["A股日均3万亿"] = 1 if amt >= AMT_3WAN else (2 if amt >= 20000 else 3)
    if real(data, "us10y"):
        u = float(val_of(data["us10y"]))
        st["海外贴现率缓和"] = 1 if u < 4 else (2 if u < US10Y_GATE else 3)
    return st


def base_position(t: float) -> float:
    for i in range(len(BASE_ANCHORS) - 1):
        x1, y1 = BASE_ANCHORS[i]
        x2, y2 = BASE_ANCHORS[i + 1]
        if x1 <= t <= x2:
            return lerp(t, x1, y1, x2, y2)
    return BASE_ANCHORS[-1][1]


def quad_of(trend: float, val: float):
    cold_t, cold_v = trend < 5, val < 5
    idx = (0 if cold_t else 1) + (0 if cold_v else 2)
    names = ["熊末·黄金坑", "下跌中继", "牛初/牛中", "牛顶/过热"]
    advises = ["可分批建仓，不追涨", "便宜没到位，等", "持有为主", "逐步减仓"]
    return {"idx": idx, "name": names[idx], "advice": advises[idx]}


def decide(data: dict, quote: dict | None, mode: str = "A",
           qual: dict | None = None, conservative: float = CONSERVATIVE) -> dict:
    qual = qual or {}
    tr, tr_why = score_trend(data, quote, mode)
    va, va_why = score_val(data)
    lq, lq_why = score_liq(data, quote)
    em, em_why = score_emo(data, quote, mode)
    w = W_A if mode == "A" else W_H
    temp = tr * w["trend"] + va * w["val"] + lq * w["liq"] + em * w["emo"]
    # 定性项微调
    q_adj = ((qual.get("地缘波动", 5) - 5) * .06 + (qual.get("监管打压", 5) - 5) * .04 +
             (qual.get("信用风险", 5) - 5) * .05 - (qual.get("政策力度", 5) - 5) * .05)
    temp_adj = clamp(temp + q_adj)

    base = base_position(temp_adj)
    cs = []
    tech = (data.get("hs300") or {}).get("extra") or {}
    if tech.get("above_ma250") is not None:
        good = bool(tech.get("above_ma250")) and bool(tech.get("ma20_gt_ma60"))
        bad = (not tech.get("above_ma250")) and (not tech.get("ma20_gt_ma60"))
        cs.append({"name": "趋势约束", "cap": 10 if good else (CAP_TREND_BAD if bad else 7.0),
                   "reason": "站上年线+多头" if good else ("跌破年线+空头" if bad else "均线交织")})
    m1 = val_of(data.get("m1_yoy")) if real(data, "m1_yoy") else None
    cr = val_of(data.get("credit_yoy")) if real(data, "credit_yoy") else None
    credit_bad = (m1 is not None and float(m1) < M1_GATE) or (cr is not None and float(cr) < 0)
    cs.append({"name": "信用约束", "cap": CAP_CREDIT_BAD if credit_bad else 10,
               "reason": f"M1 {m1}% / 信贷 {cr}%"})
    u = val_of(data.get("us10y")) if real(data, "us10y") else None
    if u is not None:
        u = float(u)
        if u >= US10Y_GATE:
            cap = CAP_OVERSEA[mode]
        elif u >= 4.0:
            cap = 8.5 if mode == "A" else 7.0
        else:
            cap = 10
        cs.append({"name": "海外约束", "cap": cap, "reason": f"美债10Y {u}%"})
    est = eight_states(data, quote)
    p = sum(1 if v == 1 else (0.5 if v == 2 else 0) for v in est.values()) / len(est)
    cs.append({"name": "共振约束", "cap": 10 if p >= .8 else (7 if p >= .5 else CAP_RESON_LOW),
               "reason": f"八大信号达成 {p*100:.0f}%"})
    cap = min(c["cap"] for c in cs)
    tight = [c["name"] for c in cs if abs(c["cap"] - cap) < 1e-9]
    final = clamp(min(base, cap) * conservative, 1, 9)
    return {
        "mode": mode, "as_of": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "temp": round(temp_adj, 2),
        "dims": {"trend": {"v": round(tr, 2), "why": tr_why},
                 "val": {"v": round(va, 2), "why": va_why},
                 "liq": {"v": round(lq, 2), "why": lq_why},
                 "emo": {"v": round(em, 2), "why": em_why}},
        "base": round(base, 2), "cap": round(cap, 2), "final": round(final, 2),
        "constraints": cs, "tight": tight, "eight": est, "resonance": round(p, 3),
        "quad": quad_of(tr, va), "conservative": conservative,
        "tag": ("极冷·底部区间" if temp_adj < 2.5 else "偏冷·结构性机会" if temp_adj < 5
                else "偏热·风险积累" if temp_adj < 7.5 else "过热·大顶前兆"),
    }
