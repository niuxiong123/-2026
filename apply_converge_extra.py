# -*- coding: utf-8 -*-
import io, sys
src = "src/index_unobfuscated_2026-10-11.html"
data = io.open(src, encoding="utf-8").read()
orig = data

pairs = []

# E9 QUADINFO 聚焦说明：去掉独立买卖措辞，全部汇入 r.final
pairs.append((
"""const QUADINFO={LU:{t:"牛初 / 牛中（趋势热 + 估值冷）",d:"持有为主，可随盈利加仓；不追高。"},LD:{t:"熊末·黄金坑（趋势冷 + 估值冷）",d:"可分批建仓，左侧小仓，不追涨。"},HU:{t:"牛顶 / 过热（趋势热 + 估值热）",d:"逐步减仓，警惕反转。"},HD:{t:"下跌中继（趋势冷 + 估值热）",d:"便宜没到位，等；不接飞刀。"}};""",
"""const QUADINFO={LU:{t:"牛初 / 牛中（趋势热 + 估值冷）",d:"定位：主升区 → 以顶部总仓位 r.final 为准，不单独加仓。"},LD:{t:"熊末·黄金坑（趋势冷 + 估值冷）",d:"定位：左侧机会区 → 以顶部总仓位 r.final 为准，左侧小仓亦须在其框架内。"},HU:{t:"牛顶 / 过热（趋势热 + 估值热）",d:"定位：风险区 → 以顶部总仓位 r.final 为准，控仓不追。"},HD:{t:"下跌中继（趋势冷 + 估值热）",d:"定位：下跌途中 → 以顶部总仓位 r.final 为准，不接飞刀。"}};""",
))

# E10 恐惧贪婪仪表：风险区措辞统一为「控仓」
pairs.append((
"""极度贪婪 · 风险区（逐步减仓）""",
"""极度贪婪 · 风险区（控仓）""",
))

# E11/E12 probRead 顶底带标签：去掉独立买卖区措辞
pairs.append((
"""底部信号强（底'+sb+"/顶"+st+"）：分批建仓区""",
"""底部信号强（底'+sb+"/顶"+st+"）：左侧布局区""",
))
pairs.append((
"""顶部信号强（顶'+st+"/底"+sb+"）：逐步减仓区""",
"""顶部信号强（顶'+st+"/底"+sb+"）：防御控仓区""",
))

for i,(old,new) in enumerate(pairs,9):
    c = data.count(old)
    if c != 1:
        sys.stderr.write("PAIR %d FAILED: expected 1 match, found %d\n" % (i, c))
        sys.exit(1)
    data = data.replace(old, new, 1)
    sys.stderr.write("OK pair %d\n" % i)

io.open(src, "w", encoding="utf-8").write(data)
sys.stderr.write("RESULT=" + ("CHANGED" if data != orig else "UNCHANGED"))
