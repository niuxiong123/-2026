# -*- coding: utf-8 -*-
# 大白话替换：只动展示文案字符串，绝不碰 r.final 代码引用
import io, sys
src = "src/index_unobfuscated_2026-10-11.html"
data = io.open(src, encoding="utf-8").read()
orig = data

pairs = []

# P1 象限标题
pairs.append((
"""<div class="k">温度与估值定位（趋势 × 估值 → 汇入顶部总仓位 r.final）</div>""",
"""<div class="k">市场位置判断（行情冷热 × 价格贵贱 → 拿几成仓，统一看顶部「建议仓位」）</div>""",
))

# P2 象限四态文案（粉丝可见的大白话）
pairs.append((
"""定位：左侧机会区 → 汇入 r.final""",
"""便宜但冷清（底部特征区）· 拿几成仓看「建议仓位」""",
))
pairs.append((
"""定位：下跌途中 → 汇入 r.final""",
"""又冷又贵（等跌透）· 拿几成仓看「建议仓位」""",
))
pairs.append((
"""定位：主升区 → 汇入 r.final""",
"""又热又不贵（主升段）· 拿几成仓看「建议仓位」""",
))
pairs.append((
"""定位：风险区 → 汇入 r.final""",
"""又热又贵（高风险区）· 拿几成仓看「建议仓位」""",
))

# P3 QUADINFO 聚焦说明 4 条
pairs.append((
"""定位：主升区 → 以顶部总仓位 r.final 为准，不单独加仓。""",
"""行情走强、价格不贵，环境偏好；具体拿几成仓，按顶部「建议仓位」执行。""",
))
pairs.append((
"""定位：左侧机会区 → 以顶部总仓位 r.final 为准，左侧小仓亦须在其框架内。""",
"""价格便宜但行情冷清，可能离大底不远；具体拿几成仓，按顶部「建议仓位」执行。""",
))
pairs.append((
"""定位：风险区 → 以顶部总仓位 r.final 为准，控仓不追。""",
"""行情热、价格也贵，风险最高；具体拿几成仓，按顶部「建议仓位」执行。""",
))
pairs.append((
"""定位：下跌途中 → 以顶部总仓位 r.final 为准，不接飞刀。""",
"""行情冷、价格还贵，先等跌透再说；具体拿几成仓，按顶部「建议仓位」执行。""",
))

# P4 两处脚注
pairs.append((
"""板块操作均在「最终结论 r.final 成」框架内，非独立仓位指令。""",
"""以上只是板块冷热参考；实际买多少、卖多少，统一按顶部「建议仓位」执行。""",
))
pairs.append((
"""板块信号在「最终结论 r.final 成」框架内，非独立仓位指令。""",
"""板块信号只代表冷热；实际买卖多少，统一按顶部「建议仓位」执行。""",
))

# P5 站主仓位卡 line2：去「唯一最终数据」「置信区间」术语
pairs.append((
"""var line2="唯一最终数据 = 建议仓位 <b>"+((r.final!=null)?r.final.toFixed(1):"–")+"成</b> ｜ 置信区间 <b>"+bandLo+"–"+bandHi+"成</b>（与顶/底概率挂钩）";""",
"""var line2="最终建议 <b>"+((r.final!=null)?r.final.toFixed(1):"–")+"成</b> ｜ 正常浮动 <b>"+bandLo+"–"+bandHi+"成</b>（随顶/底概率自动调整）";""",
))

# P6 FanHero 备注行：置信区间→正常浮动
pairs.append((
"""+"/10。 建议仓位 <b>"+r.final.toFixed(1)+"成</b>（置信区间 "+""",
"""+"/10。 建议仓位 <b>"+r.final.toFixed(1)+"成</b>（正常浮动 "+""",
))

# P7 quadWhy 行情热度/价格贵贱 大白话
pairs.append((
""""趋势 "+r.tr.v.toFixed(1)+"（"+(coldTr?"冷":"热")+"） × 估值 "+r.va.v.toFixed(1)+"（"+(coldVa?"冷":"贵")+"）<br>当前落点：<b>"+items[idx].t+"</b>\"""",
""""行情热度 "+r.tr.v.toFixed(1)+"/10（"+(coldTr?"偏冷":"偏热")+"） × 价格贵贱 "+r.va.v.toFixed(1)+"/10（"+(coldVa?"偏便宜":"偏贵")+"）<br>当前落点：<b>"+items[idx].t+"</b>\"""",
))

for i,(old,new) in enumerate(pairs,1):
    c = data.count(old)
    if c != 1:
        sys.stderr.write("PAIR %d FAILED: expected 1, found %d | %s...\n" % (i, c, old[:50]))
        sys.exit(1)
    data = data.replace(old, new, 1)
    sys.stderr.write("OK pair %d\n" % i)

io.open(src, "w", encoding="utf-8").write(data)
sys.stderr.write("RESULT=" + ("CHANGED" if data != orig else "UNCHANGED"))
