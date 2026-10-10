#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sector_rollup.py —— 把 crowding_system 产出的「单 ETF 拥挤度」聚合成网页需要的「22 板块拥挤度」。

【为什么需要它（团队 B2：最大工程缺口）】
  网页端 22 个板块(key) 是"主题板块"；crowding_system 输出的是"单只 ETF 的 C"。
  两者之间没有映射表，系统算出的 ETF 级 C 无法直接落到网页 22 板块上。
  本脚本就是这张映射 + 聚合层：你在本机 / GitHub Action 跑完 crowding_system 拿到
  单 ETF 结果后，用本脚本聚合成 docs/sectors_crowd.json（source='real'），网页 fetch 即用。

【输入】crowding_system 的输出 JSON，形如 list of：
  {"code":"588200","name":"科创芯片ETF","C":82,"signal":"watch","regime":"high","p":88}
  （C 必填 0-100；signal/regime/p 可选，缺失时由本脚本据 C 推导）
  默认读 crowding_output.json（与脚本同目录），可用首个命令行参数覆盖。

【输出】docs/sectors_crowd.json，schema 与网页严格对齐：
  {"as_of":"YYYY-MM-DD","source":"real","M_t":<float>,"generated_by":"sector_rollup.py",
   "sectors":{"<key>":{"C":0-100,"signal":"buy|sell|watch","p":0-100,"regime":"low|neutral|high"}, ...}}

【用法】
  python sector_rollup.py                  # 读 crowding_output.json → 写 docs/sectors_crowd.json
  python sector_rollup.py my_etf.json      # 指定输入
  然后部署：ALLOW_DEMO=1 bash ../api_push.sh   （此时 source=real，B3 守卫放行）

【注意（团队 B6）】
  网页需经 http(s) 访问（GitHub Pages 或本地 http server）。file:// 双击打开时浏览器会
  拦截 fetch('./sectors_crowd.json')，拥挤度将回退为"代理估算"。本地预览请用：
      python -m http.server 8138 --directory docs
  然后打开 http://localhost:8138/

【ETF → 板块映射表】
  下表按"先具体后通用"匹配：优先比对 ETF 代码(六位)，其次按名称关键词子串。
  请按你 crowding_system 实际的 ETF 池校准本表（尤其是代码与中文名）。
"""
import json, os, sys, datetime

# 网页端 22 个板块 key（顺序无关，仅用于自洽校验）
SECTOR_KEYS = ['tech','hk_growth','small','fin','resource','realestate','dividend',
               'cons_def','util','gold','cash','fx','baijiu','semi','med_etf','hstech',
               'mil','hs300','pv','li','nev','nasdaq']

# ETF 代码(六位) 或 名称关键词 → 板块 key
ETF_MAP = {
    'semi':      ['588200','588290','159995','半导体','芯片','科创芯片'],
    'baijiu':    ['512690','白酒','酒ETF'],
    'tech':      ['159915','159949','588000','588080','创业板','科创50','科技'],
    'hk_growth': ['513060','港股成长','香港成长','恒生医疗'],  # 港股成长单列（非恒生科技）
    'hstech':    ['513180','513130','513330','159740','恒生科技','恒科'],
    'small':     ['159845','512100','161039','小盘','中证1000','1000ETF'],
    'fin':       ['512000','512070','510230','512900','券商','保险','金融'],
    'resource':  ['512400','515220','161226','有色','煤炭','资源'],
    'realestate':['512200','160218','地产','房地产'],
    'dividend':  ['510880','515080','561580','515180','红利','高股息','股息'],
    'cons_def':  ['159928','消费','食品饮料'],
    'med_etf':   ['512010','159938','512170','512290','医药','医疗','生物'],
    'util':      ['159611','561700','561160','公用事业','电力','绿电'],
    'gold':      ['518880','159934','518800','黄金','金ETF'],
    'cash':      ['511010','511260','511880','511270','国债','利率债','货币','货基','短债'],
    'fx':        ['美元','外汇','美债?','511890?'],
    'mil':       ['512660','512810','军工'],
    'hs300':     ['510300','510310','510330','沪深300','300ETF'],
    'pv':        ['515790','516180','516850','光伏'],
    'li':        ['159840','161033','锂电池','锂电'],
    'nev':       ['515030','516390','501057','516580','新能源车','新能车'],
    'nasdaq':    ['513100','161128','161130','纳指','纳斯达克','美股','标普'],
}

def map_etf(code, name):
    """返回板块 key；无法归类返回 None。"""
    c = str(code or '').strip()
    n = str(name or '').strip()
    # 1) 代码精确匹配
    for key, toks in ETF_MAP.items():
        if c and c in toks and (len(c) >= 6):  # 六位代码精确
            return key
    # 2) 名称关键词子串匹配（先具体后通用，按 SECTOR_KEYS 顺序保证 semi 优先于 tech）
    for key in SECTOR_KEYS:
        for tok in ETF_MAP.get(key, []):
            if len(tok) >= 2 and tok in n:
                return key
    return None

def regime_from_c(c):
    if c >= 70: return 'high'
    if c <= 40: return 'low'
    return 'neutral'

def signal_from_regime(regime):
    if regime == 'high': return 'sell'
    if regime == 'low': return 'buy'
    return 'watch'

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    inp = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, 'crowding_output.json')
    out = os.path.join(here, 'docs', 'sectors_crowd.json')
    if not os.path.exists(inp):
        print('❌ 输入不存在：%s' % inp)
        print('   请先在本机/GitHub Action 跑 crowding_system，把单 ETF 结果存为 crowding_output.json（或作为参数传入）。')
        sys.exit(1)

    with open(inp, 'r', encoding='utf-8') as f:
        etfs = json.load(f)
    if not isinstance(etfs, list):
        print('❌ 输入应为 list[{code,name,C,...}]，实际：%s' % type(etfs))
        sys.exit(1)

    # 按板块归 ETF
    buckets = {}
    unmapped = []
    for e in etfs:
        c = e.get('C')
        if not isinstance(c, (int, float)) or not (0 <= c <= 100):
            print('⚠ 跳过：C 非法 -> %s' % json.dumps(e, ensure_ascii=False))
            continue
        key = map_etf(e.get('code'), e.get('name'))
        if not key:
            unmapped.append(e.get('name') or e.get('code'))
            continue
        buckets.setdefault(key, []).append(e)

    if unmapped:
        print('⚠ 未匹配板块（将不在 JSON 中输出，网页对该板块回退"代理估算"）：%s' % '、'.join(map(str, unmapped[:20])))

    # 聚合每个板块
    sectors = {}
    all_c = []
    for key in buckets:
        items = buckets[key]
        cs = [i['C'] for i in items]
        avg = sum(cs) / len(cs)
        all_c.append(avg)
        # regime：优先用各 ETF 的 regime 多数；否则由均值 C 推导
        regimes = [i.get('regime') for i in items if i.get('regime') in ('low','neutral','high')]
        if regimes:
            from collections import Counter
            regime = Counter(regimes).most_common(1)[0][0]
        else:
            regime = regime_from_c(avg)
        # signal：优先用各 ETF 的 signal 多数；否则由 regime 推导
        sigs = [i.get('signal') for i in items if i.get('signal') in ('buy','sell','watch')]
        if sigs:
            from collections import Counter
            signal = Counter(sigs).most_common(1)[0][0]
        else:
            signal = signal_from_regime(regime)
        sectors[key] = {
            'C': round(avg, 1),
            'signal': signal,
            'p': 50,   # 占位，下面用横截面分位重算
            'regime': regime,
        }

    # 横截面分位 p：各板块 avgC 在全部板块中的百分位排名
    if all_c:
        sorted_c = sorted(all_c)
        for key, val in sectors.items():
            rank = sum(1 for x in sorted_c if x <= val['C'])
            val['p'] = round(rank / len(sorted_c) * 100, 1)

    M_t = round(sum(all_c) / len(all_c), 1) if all_c else 50
    doc = {
        'as_of': datetime.date.today().isoformat(),
        'source': 'real',
        'M_t': M_t,
        'generated_by': 'sector_rollup.py',
        'note': '由 crowding_system 单 ETF 输出聚合而成（真实拥挤度）。ETF→板块映射见脚本顶部 ETF_MAP，请按你的 ETF 池校准。网页需经 http(s) 访问。',
        'sectors': sectors,
    }
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print('✅ 已聚合 %d 只 ETF → %d 个板块，写入 %s' % (sum(len(v) for v in buckets.values()), len(sectors), out))
    print('   M_t=%.1f  板块：%s' % (M_t, '、'.join(sorted(sectors.keys()))))

if __name__ == '__main__':
    main()
