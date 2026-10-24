# -*- coding: utf-8 -*-
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
