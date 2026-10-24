# -*- coding: utf-8 -*-
import math

"""滞回阶梯核心逻辑——单一真源（Python 端 + 单元测试共用）
单位约定（防 0.8>=80 类单位混用 bug）：
  p   = 历史分位，范围 0~100（%）
  pos = 仓位，  范围 0~100（成）
"""
UP   = [(5, 100), (15, 80), (35, 50), (65, 20)]   # 升档条件（分位上限% → 仓位成）
DOWN = [(15, 80), (35, 50), (65, 20), (80, 0)]    # 降档条件（分位下限% → 仓位成）
LAD  = [[10, 100], [20, 80], [40, 50], [70, 20]]  # 无滞回对照阶梯（分位% → 仓位成）

# 各档 R 阈值（股债比值 R = 沪深300全收益 / 债基净值）
TH_FULL, TH_80, TH_50, TH_20, TH_CLEAR = 1.175, 1.260, 1.380, 1.599, 1.752


def ladder_plain(p):
    """无滞回对照：分位 → 仓位（成）。"""
    for lim, pos in LAD:
        if p <= lim:
            return pos
    return 0


def step_hyst(p, state):
    """滞回一步：p=历史分位(%)，state=当前仓位(成)。带单位守卫。"""
    if not (0 <= p <= 100) or not (0 <= state <= 100):
        raise ValueError("step_hyst 单位错 p=%s state=%s（应 0~100）" % (p, state))
    new = state
    for lim, pos in DOWN:
        if state >= pos and p > lim:
            new = pos
    if new == state:
        for lim, pos in UP:
            if p <= lim and new < pos:
                new = pos
    return new


def run_hyst(pct_seq, init=0):
    """给定分位序列，回放得到带记忆的档位序列（首态 init 成）。"""
    st = init
    out = []
    for p in pct_seq:
        st = step_hyst(p, st)
        out.append(st)
    return out


def r_to_pos(r):
    """股债比值 R → 档位（成），用于快速查表与一致性自检。"""
    if r <= TH_FULL:
        return 100
    if r <= TH_80:
        return 80
    if r <= TH_50:
        return 50
    if r <= TH_20:
        return 20
    if r > TH_CLEAR:
        return 0
    return 20  # 1.599 < r <= 1.752 之间维持 20 成（不主动清仓）


# ============================================================================
# 仓位总装引擎（2026-10-24 追加；step_hyst / run_hyst / r_to_pos 保持原样勿改）
# 单位约定同前：q 与分位 0~100；pos 与 cap 0~100（成）；收益率用小数（0.05 = 5%）
# ============================================================================

# ── 动态 Kelly ──
MU0, MU1 = 0.14, 0.02      # 分位 0% → 期望年化 14%；分位 100% → 2%（由历史分位-前瞻收益回归标定）
LAM0, LAM1 = 1.00, 5.00    # 风险厌恶系数：分位 0% → 1.0；100% → 5.0
KELLY_FLOOR = 30           # Kelly 下限（成）：防熊市尾巴算出个位数仓位


def _clamp01(q):
    return min(max(q, 0.0), 100.0) / 100.0


def mu_of(q):
    """分位 → 期望年化收益 μ（线性插值，替代原硬跳档）。"""
    return MU0 + (MU1 - MU0) * _clamp01(q)


def lam_of(q):
    """分位 → 风险厌恶系数 λ（线性插值）。"""
    return LAM0 + (LAM1 - LAM0) * _clamp01(q)


def rolling_sigma(navs, win=156):
    """周频净值序列 → 年化波动率（sqrt(52)）。数据不足返回 None。"""
    n = len(navs)
    if n < 3:
        return None
    w = min(win, n - 1)
    rets = [navs[i] / navs[i - 1] - 1.0 for i in range(n - w, n)]
    m = sum(rets) / len(rets)
    var = sum((x - m) ** 2 for x in rets) / (len(rets) - 1)
    return math.sqrt(var * 52)


def kelly_cap(q, sigma, rf):
    """Kelly 上限（成）。σ 或 μ<=rf 时保守返回 None 由调用方决定。"""
    if not sigma or sigma <= 0:
        return None
    f = (mu_of(q) - rf) / (lam_of(q) * sigma * sigma)
    return max(0.0, min(1.0, f)) * 100.0


# ── 股债双杀熔断（日频 20 交易日口径）──
DK_HS, DK_BOND, DK_CAP = -0.05, -0.01, 20   # 股 20 日 ≤ −5% 且 债 20 日 ≤ −1% → 压到 20 成


def stock_bond_kill(daily):
    """daily = [{'nav_hs':..,'nav_bond':..}, ...] 至少 22 点（日频）。
    返回 (triggered, hs20, bd20)。数据不足返回 (False, None, None)。"""
    if not daily or len(daily) < 22:
        return False, None, None
    n = len(daily)
    hs = daily[n - 1]["nav_hs"] / daily[n - 21]["nav_hs"] - 1.0
    bd = daily[n - 1]["nav_bond"] / daily[n - 21]["nav_bond"] - 1.0
    return (hs <= DK_HS and bd <= DK_BOND), hs, bd


# ── 条件式命理封顶（乙木身弱·财旺杀强；随分位递减，双阈值滞回）──
MYSTIC_LADDER = [(5, 100), (10, 80), (20, 60), (40, 40), (65, 20), (float("inf"), 0)]
MYSTIC_OPEN_Q, MYSTIC_CLOSE_Q = 5, 20      # ≤5% 放开；涨过 20% 收回
SOFEN_YEARS = (2026, 2027)                 # 财杀攻身年：地板区也只放到 80 成
SOFEN_CAP = 80


def mystic_cap_plain(q):
    """命理阶梯（无滞回查表）：分位 → 封顶（成）。"""
    for lim, cap in MYSTIC_LADDER:
        if q <= lim:
            return cap
    return 0


def mystic_step(q, was_open, year=None):
    """双阈值滞回 + 年份锁。返回 (open, cap)。"""
    if was_open:
        if q > MYSTIC_CLOSE_Q:
            open_, cap = False, mystic_cap_plain(q)
        else:
            open_, cap = True, 100
    else:
        if q <= MYSTIC_OPEN_Q:
            open_, cap = True, 100
        else:
            open_, cap = False, mystic_cap_plain(q)
    if open_ and year in SOFEN_YEARS:
        cap = min(cap, SOFEN_CAP)
    return open_, cap


def revive(dk_trig, q, hys, pos, floor=50):
    """双杀复活条款：打在地板上（分位仍极便宜且阶梯档位未降）时回补，不一刀切关死。"""
    if dk_trig and q <= 15 and hys >= 50:
        return max(pos, floor)
    return pos


def compute_position(q, navs, prev_pos, mystic_open, rf, daily=None, year=None):
    """总装：一次算完，返回完整链路（供页面展示每一步）。

    prev_pos   = 上一期「滞回阶梯档位」（不是上一期最终仓位，否则阶梯会被 Kelly 污染）
    mystic_open= 上一期命理是否处于放开区（跨期记忆）
    """
    sigma = rolling_sigma(navs)
    hys = step_hyst(q, prev_pos)
    k_raw = kelly_cap(q, sigma, rf) if sigma else None
    k_cap = max(KELLY_FLOOR, k_raw) if k_raw is not None else None
    dk_trig, hs20, bd20 = stock_bond_kill(daily)
    dk_cap = DK_CAP if dk_trig else 100
    m_open, m_cap = mystic_step(q, mystic_open, year)

    caps = [hys] + [c for c in (k_cap, dk_cap, m_cap) if c is not None]
    pos = min(caps)
    pos = revive(dk_trig, q, hys, pos)

    if dk_trig:
        if pos > dk_cap:
            reason = ("股债双杀熔断触发（压至 %d 成），但分位仍极便宜且阶梯档位未降，"
                      "复活条款回补至 %d 成" % (dk_cap, pos))
        else:
            reason = "股债双杀熔断触发，强制 ≤ %d 成" % dk_cap
    elif pos == m_cap and m_cap <= hys:
        reason = "命理纪律封顶（非极便宜区）"
    elif k_cap is not None and pos == k_cap:
        reason = "动态 Kelly 封顶（半凯利）"
    else:
        reason = "取滞回阶梯档位"

    return {
        "pos": pos, "hys": hys, "kelly_raw": k_raw, "kelly_cap": k_cap,
        "sigma": sigma, "dk_triggered": dk_trig, "dk_hs20": hs20, "dk_bond20": bd20,
        "dk_cap": dk_cap, "mystic_open": m_open, "mystic_cap": m_cap, "reason": reason,
    }
