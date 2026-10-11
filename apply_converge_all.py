# -*- coding: utf-8 -*-
import io, sys
src = "src/index_unobfuscated_2026-10-11.html"
data = io.open(src, encoding="utf-8").read()
orig = data

pairs = []

# E1 FanHero sig: 唯一最终数据 r.final 派生（删除展示层 55 私阈）
pairs.append((
"""var sig,cls,strongBottom=r.tb.pBottom>=70&&r.tb.pTop<=30,strongTop=r.tb.pTop>=70&&r.tb.pBottom<=30;strongBottom||low&&r.tb.pBottom>=55?(sig="偏买 🟢",cls="sig-buy"):strongTop||high&&r.tb.pTop>=55?(sig="偏卖 🔴",cls="sig-sell"):(sig="持有 🟡",cls="sig-hold"),fs&&(fs.textContent=sig,fs.className="fh-tag "+cls)""",
"""var sig,cls;r.final>=7?(sig="进攻 🟢",cls="sig-buy"):r.final<=3?(sig="防御 🔴",cls="sig-sell"):(sig="中性观察 🟡",cls="sig-hold"),fs&&(fs.textContent=sig,fs.className="fh-tag "+cls)""",
))

# E2 FanHero fn: 补充「建议仓位 + 置信区间」与顶/底挂钩
pairs.append((
"""fn&&(fn.innerHTML='底部概率 <b style="color:var(--green)">'+r.tb.pBottom+'%</b> ｜ 顶部概率 <b style="color:var(--red)">'+r.tb.pTop+"%</b> ｜ 市场温度 "+r.tempAdj.toFixed(1)+"/10。"+(!1===r.mUp?" 月线空头，只许左侧小仓。":"")+" 仅供参考，买卖与仓位由您独立判断。")""",
"""fn&&(fn.innerHTML='底部概率 <b style="color:var(--green)">'+r.tb.pBottom+'%</b> ｜ 顶部概率 <b style="color:var(--red)">'+r.tb.pTop+"%</b> ｜ 市场温度 "+r.tempAdj.toFixed(1)+"/10。 建议仓位 <b>"+r.final.toFixed(1)+"成</b>（置信区间 "+Math.max(0,r.final-Math.round(r.tb.pTop/100*2)).toFixed(1)+"–"+Math.min(9.5,r.final+Math.round(r.tb.pBottom/100*2)).toFixed(1)+"成）。"+(!1===r.mUp?" 月线空头，只许左侧小仓。":"")+" 仅供参考，买卖与仓位由您独立判断。")""",
))

# E3 bannerRegime 横幅与 FanHero 统一：final<=3 防御期
pairs.append((
"""bannerRegime").textContent=r.final<5?"防御期":r.final<7?"中性观察":"进攻期\"""",
"""bannerRegime").textContent=r.final<=3?"防御期":r.final<7?"中性观察":"进攻期\"""",
))

# E4 renderOwnerCards：删除死字段，改为真实链路 + 置信区间
pairs.append((
"""    var line1="温度仓位 "+bp+"成 → 硬约束取 min "+cap+"成（卡在："+z+"）→ 保守系数"+kons;
    var credit=(r.capCredit!=null)?r.capCredit.toFixed(1)+"成":"—（当前引擎未输出）";
    var overseas=(r.capOverseas!=null)?r.capOverseas.toFixed(1)+"成":"—（当前引擎未输出）";
    var reson=(r.cap!=null)?r.cap.toFixed(1)+"成":"—（当前引擎未输出）";
    var line2="信用约束 "+credit+" | 海外约束 "+overseas+" | 共振约束 "+reson;
    g("own_posDetail").innerHTML=line1+"<br>"+line2;""",
"""    var bandLo=(r.final!=null&&r.tb)?Math.max(0,r.final-Math.round(r.tb.pTop/100*2)):"–";
    var bandHi=(r.final!=null&&r.tb)?Math.min(9.5,r.final+Math.round(r.tb.pBottom/100*2)):"–";
    var line1="温度仓位 "+bp+"成 → 硬约束取 min "+cap+"成（卡在："+z+"）→ 保守系数"+kons;
    var line2="唯一最终数据 = 建议仓位 <b>"+((r.final!=null)?r.final.toFixed(1):"–")+"成</b> ｜ 置信区间 <b>"+bandLo+"–"+bandHi+"成</b>（与顶/底概率挂钩）";
    g("own_posDetail").innerHTML=line1+"<br>"+line2;""",
))

# E5 renderQuad：操作措辞改为「定位 → 汇入 r.final」
pairs.append((
"""items=[{t:"熊末·黄金坑",d:'趋势冷 + 估值冷<br><span style="color:var(--green)">可分批建仓，不追涨</span>'},{t:"下跌中继",d:'趋势冷 + 估值热<br><span style="color:var(--yellow)">便宜没到位，等</span>'},{t:"牛初/牛中",d:'趋势热 + 估值冷<br><span style="color:var(--green)">持有为主</span>'},{t:"牛顶/过热",d:'趋势热 + 估值热<br><span style="color:var(--red)">逐步减仓</span>'}]""",
"""items=[{t:"熊末·黄金坑",d:'趋势冷 + 估值冷<br><span style="color:var(--sub)">定位：左侧机会区 → 汇入 r.final</span>'},{t:"下跌中继",d:'趋势冷 + 估值热<br><span style="color:var(--sub)">定位：下跌途中 → 汇入 r.final</span>'},{t:"牛初/牛中",d:'趋势热 + 估值冷<br><span style="color:var(--sub)">定位：主升区 → 汇入 r.final</span>'},{t:"牛顶/过热",d:'趋势热 + 估值热<br><span style="color:var(--sub)">定位：风险区 → 汇入 r.final</span>'}]""",
))

# E6 quad 标题收敛
pairs.append((
"""<div class="k">牛熊钟定位（趋势 × 估值）</div>""",
"""<div class="k">温度与估值定位（趋势 × 估值 → 汇入顶部总仓位 r.final）</div>""",
))

# E7 renderActionList 脚注（锚点：4. 前无引号，<br> 在引号内）
pairs.append((
"""4.<b>三不原则：不重仓 · 不抄底 · 不加杠杆</b>",el=document.getElementById("actionList")""",
"""4.<b>三不原则：不重仓 · 不抄底 · 不加杠杆</b><br><span style=\\"font-size:11px;color:var(--sub)\\">板块操作均在「最终结论 r.final 成」框架内，非独立仓位指令。</span>",el=document.getElementById("actionList")""",
))

# E8 renderSectors 脚注
pairs.append((
"""x.tier}).length+" ｜ 仅供参考，不构成投资建议。"}}""",
"""x.tier}).length+" ｜ 仅供参考，不构成投资建议。 ｜ 板块信号在「最终结论 r.final 成」框架内，非独立仓位指令。"}}""",
))

for i,(old,new) in enumerate(pairs,1):
    c = data.count(old)
    if c != 1:
        sys.stderr.write("PAIR %d FAILED: expected 1 match, found %d\n" % (i, c))
        sys.exit(1)
    data = data.replace(old, new, 1)
    sys.stderr.write("OK pair %d\n" % i)

io.open(src, "w", encoding="utf-8").write(data)
sys.stderr.write("RESULT=" + ("CHANGED" if data != orig else "UNCHANGED"))
