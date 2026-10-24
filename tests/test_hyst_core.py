#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hyst_core.py 引擎单测（CI 门禁，退出码非 0 即禁止部署）
覆盖：冻结的滞回用例、动态 Kelly 连续性、股债双杀、命理阶梯/滞回/年份锁、复活条款、端到端。
用法: python3 tests/test_hyst_core.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import hyst_core as H  # noqa: E402

fails = []


def eq(got, want, msg):
    if got != want:
        fails.append("%s：期望 %s，实得 %s" % (msg, want, got))
        print("  x %s（期望 %s，实得 %s）" % (msg, want, got))
    else:
        print("  v %s = %s" % (msg, got))


def ok(cond, msg):
    if cond:
        print("  v %s" % msg)
    else:
        fails.append(msg)
        print("  x %s" % msg)


print("=== 1) 滞回阶梯（CI 冻结用例，改动即回归）===")
eq(H.step_hyst(40, 80), 50, "step_hyst(40,80) 该降不降的bug用例")
eq(H.step_hyst(10.6, 80), 80, "当前分位 10.6 保持 80 档")
eq(H.step_hyst(70, 80), 20, "分位 70 降到 20 档")
eq(H.step_hyst(10, 0), 80, "分位 10 升到 80 档")
eq(H.step_hyst(3, 20), 100, "极端便宜直接满仓")
eq(H.r_to_pos(1.2285), 80, "R=1.2285 查表 80 成")
for bad_p, bad_st, tag in [(150, 80, "p=150 越界"), (10, 180, "state=180 越界"), (-1, 80, "p=-1 越界")]:
    try:
        H.step_hyst(bad_p, bad_st)
        fails.append("单位守卫失效：%s 未报错" % tag)
        print("  x 单位守卫失效：%s" % tag)
    except ValueError:
        print("  v 单位守卫：%s 正确抛错" % tag)

print("=== 2) 滚动波动率 ===")
flat = [1.0] * 200
ok(H.rolling_sigma(flat) == 0.0 or H.rolling_sigma(flat) < 1e-9, "恒定序列波动率≈0")
ok(H.rolling_sigma([1.0, 2.0]) is None, "数据不足返回 None")
navs = [1.0]
for i in range(300):
    navs.append(navs[-1] * (1.0 + (0.02 if i % 2 == 0 else -0.019)))
sig = H.rolling_sigma(navs)
ok(sig is not None and 0.05 < sig < 0.60, "合成序列 σ 落在合理区间（%.3f）" % sig)

print("=== 3) 动态 Kelly：连续性 + 下限 ===")
a, b = H.kelly_cap(10.0, 0.1712, 0.016822), H.kelly_cap(10.6, 0.1712, 0.016822)
ok(abs(a - b) < 5, "分位 10.0 与 10.6 的 Kelly 差 < 5 成（%.1f vs %.1f，原硬跳档差 3.6 成）" % (a, b))
ok(H.kelly_cap(95, 0.1712, 0.016822) < 30, "高位 Kelly 应收紧到 30 成以下（实得 %.1f）"
   % H.kelly_cap(95, 0.1712, 0.016822))
ok(H.kelly_cap(10, 0.0, 0.0168) is None, "σ=0 返回 None")
ok(H.mu_of(0) > H.mu_of(100), "μ 随分位递减")

print("=== 4) 股债双杀熔断 ===")
bad = [{"nav_hs": 6.0 - i * 0.05, "nav_bond": 5.0 - i * 0.004} for i in range(25)]
t, hs, bd = H.stock_bond_kill(bad)
ok(t and hs <= H.DK_HS and bd <= H.DK_BOND, "股债齐跌触发（股 %.2f%% 债 %.2f%%）" % (hs * 100, bd * 100))
only_stock = [{"nav_hs": 6.0 - i * 0.05, "nav_bond": 5.0 + i * 0.001} for i in range(25)]
ok(not H.stock_bond_kill(only_stock)[0], "只跌股不跌债不触发")
ok(H.stock_bond_kill(bad[:10])[0] is False, "数据不足 22 天不触发")
ok(H.stock_bond_kill([])[0] is False, "空序列不触发")

print("=== 5) 命理阶梯（随分位递减）===")
eq(H.mystic_cap_plain(2), 100, "q=2 放开")
eq(H.mystic_cap_plain(8), 80, "q=8 → 80")
eq(H.mystic_cap_plain(15), 60, "q=15 → 60")
eq(H.mystic_cap_plain(30), 40, "q=30 → 40")
eq(H.mystic_cap_plain(70), 0, "q=70 → 0（高位清仓，旧设计此处仍给 60）")
eq(H.mystic_cap_plain(95), 0, "q=95 → 0")

print("=== 6) 命理双阈值滞回（防 10~20 之间反复开关）===")
seq = [(3, True), (8, True), (15, True), (22, False), (12, False), (6, False), (4, True)]
state = False
for q, want_open in seq:
    state, cap = H.mystic_step(q, state, 2029)
    eq(state, want_open, "q=%s 后 open 状态" % q)

print("=== 7) 财杀攻身年时间锁 ===")
eq(H.mystic_step(3.0, False, 2026)[1], 80, "2026 年地板区只放到 80")
eq(H.mystic_step(3.0, False, 2027)[1], 80, "2027 年地板区只放到 80")
eq(H.mystic_step(3.0, False, 2029)[1], 100, "2029 年起全放 100")
eq(H.mystic_step(50.0, False, 2026)[1], 20, "年份锁不影响非放开区（q=50 → 阶梯 20 成）")

print("=== 8) 复活条款 ===")
eq(H.revive(True, 10, 80, 20), 50, "双杀打在地板上回补 50")
eq(H.revive(True, 40, 20, 20), 20, "分位不便宜不回补")
eq(H.revive(False, 10, 80, 80), 80, "未触发不动")

print("=== 9) 端到端 compute_position ===")
navs = [1.0]
for i in range(400):
    navs.append(navs[-1] * (1.0 + (0.0015 if i % 3 else -0.001)))
calm = [{"nav_hs": 6.0 + i * 0.01, "nav_bond": 5.0 + i * 0.002} for i in range(25)]
r = H.compute_position(q=10.6, navs=navs, prev_pos=80, mystic_open=False,
                       rf=0.016822, daily=calm, year=2026)
ok(r["hys"] == 80, "滞回档位 80")
ok(r["dk_triggered"] is False, "平稳期双杀不触发")
ok(r["mystic_cap"] == 60, "命理封顶 60")
eq(r["pos"], 60, "平稳期最终 60 成（命理封顶生效）")

r2 = H.compute_position(q=10.6, navs=navs, prev_pos=80, mystic_open=False,
                        rf=0.016822, daily=bad, year=2026)
eq(r2["dk_triggered"], True, "双杀触发")
eq(r2["pos"], 50, "q=10.6 且阶梯 80 未降 → 复活条款回补到 50 成")
ok("复活" in r2["reason"], "原因说明含复活条款（实得：%s）" % r2["reason"])
r2b = H.compute_position(q=25, navs=navs, prev_pos=80, mystic_open=False,
                         rf=0.016822, daily=bad, year=2026)
eq(r2b["pos"], 20, "q=25 分位不便宜 → 复活不生效，压到 20 成")
ok("复活" not in r2b["reason"], "q=25 原因说明不含复活")

r3 = H.compute_position(q=70, navs=navs, prev_pos=80, mystic_open=False,
                        rf=0.016822, daily=calm, year=2029)
ok(r3["mystic_cap"] == 0, "高位命理封顶 0")
ok(r3["pos"] == 0, "高位最终 0 成（旧设计此处仍 60）")

r4 = H.compute_position(q=10.6, navs=navs, prev_pos=80, mystic_open=False,
                        rf=0.016822, daily=None, year=2026)
ok(r4["dk_triggered"] is False, "无日频数据时双杀不触发（降级可用）")
eq(r4["pos"], 60, "无日频数据仍能算出 60 成")

print()
if fails:
    print("共 %d 项失败：" % len(fails))
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("全部通过")
