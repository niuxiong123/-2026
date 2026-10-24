#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stockbond.json 数据契约校验（CI 门禁，退出码非 0 即禁止部署）

专治「页面读 j.records / rec.quantile_pct，生成器输出 j.weekly / rec.pct」这类
键名漂移——它不会让页面报错，只会让页面静默降级到假数据，用户把旧数字当新的。
此前正因 CI 只测纯函数、不测数据契约，这个 bug 存活了很久。

用法: python3 tests/test_json_contract.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "docs", "niuxiong-zijiantai", "data", "stockbond.json")

fails = []


def need(cond, msg):
    if cond:
        print("  v %s" % msg)
    else:
        fails.append(msg)
        print("  x %s" % msg)


if not os.path.exists(PATH):
    print("  x 找不到 %s（先跑一次 stockbond-daily.yml 生成数据）" % PATH)
    sys.exit(1)

j = json.load(open(PATH, encoding="utf-8"))

print("=== 1) 顶层字段（页面硬读这些键）===")
for k in ["generated_at", "latest", "weekly", "recent_daily", "model",
          "thresholds", "backtest", "disclaimer", "weekly_count"]:
    need(k in j, "顶层含 %s" % k)

print("=== 2) latest 字段（计算器/徽标硬读）===")
L = j.get("latest", {})
for k in ["date", "nav_hs", "nav_bond", "ratio_R", "pct", "pos", "prev_position",
          "hs300_mom_1m", "sigma", "rf", "kelly_cap", "dk_triggered", "dk_hs20",
          "dk_bond20", "dk_cap", "mystic_open", "mystic_cap",
          "final_position", "final_reason"]:
    need(k in L, "latest 含 %s" % k)

print("=== 3) weekly 记录键（图表 tooltip 硬读）===")
wk = j.get("weekly", [])
need(len(wk) >= 200, "weekly 至少 200 点（实得 %d）" % len(wk))
for k in ["date", "nav_hs", "nav_bond", "ratio_R", "pct", "pos"]:
    need(k in wk[-1], "weekly 记录含 %s" % k)

print("=== 4) recent_daily（股债双杀熔断的数据来源，周频算不出来）===")
rd = j.get("recent_daily", [])
need(len(rd) >= 22, "recent_daily 至少 22 天（实得 %d，不足则双杀永远算不出）" % len(rd))
for k in ["date", "nav_hs", "nav_bond"]:
    need(k in rd[-1], "recent_daily 记录含 %s" % k)
need(len({r["date"] for r in rd}) == len(rd), "recent_daily 日期无重复")

print("=== 5) 数值合法性 ===")
need(0 <= L.get("pct", -1) <= 100, "pct 在 0~100（实得 %s）" % L.get("pct"))
need(0 <= L.get("pos", -1) <= 100, "pos 在 0~100")
need(0 <= L.get("final_position", -1) <= 100, "final_position 在 0~100")
need(L.get("nav_hs", 0) > 0 and L.get("nav_bond", 0) > 0, "净值均为正")
need(0 < L.get("rf", 0) < 0.10, "rf 在合理区间（实得 %s）" % L.get("rf"))
need(0 < L.get("sigma", 0) < 1.0, "sigma 在合理区间（实得 %s）" % L.get("sigma"))

print("=== 6) 约束链自洽（防页面显示与模型算出的不一致）===")
caps = {"hys": L.get("pos"), "kelly": L.get("kelly_cap"),
        "dk": L.get("dk_cap"), "mystic": L.get("mystic_cap")}
caps = {k: v for k, v in caps.items() if isinstance(v, (int, float))}
need(len(caps) == 4, "四个约束值齐全（实得 %s）" % sorted(caps))
if len(caps) == 4:
    expected = min(caps.values())
    fp = L.get("final_position")
    # 复活条款可把 20 成抬到 50 成，故允许 final >= expected
    need(fp >= expected, "final_position 不小于各约束最小值（%s >= %s）" % (fp, expected))
    need(fp <= max(caps.values()), "final_position 不超过最大约束")
    if L.get("dk_triggered"):
        if "复活" in str(L.get("final_reason", "")):
            need(L.get("final_position") <= 50,
                 "双杀+复活条款时 final_position ≤ 50 成（实得 %s）" % L.get("final_position"))
        else:
            need(L.get("final_position") <= L.get("dk_cap"),
                 "双杀触发且无复活时 final_position ≤ dk_cap")
        need("双杀" in str(L.get("final_reason", "")), "双杀触发时原因说明含「双杀」")

print("=== 7) 回测口径（旧口径 11.17%/-15.4% 不得作为主口径出现）===")
bt = str(j.get("backtest", ""))
need("10.26" in bt, "backtest 说明含无前视口径 10.26%")
need("11.17" not in bt or "废弃" in bt or "旧口径" in bt,
     "11.17%/-15.4% 若出现必须标注为已废弃旧口径")

print()
if fails:
    print("共 %d 项失败：" % len(fails))
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("JSON 契约校验通过")
