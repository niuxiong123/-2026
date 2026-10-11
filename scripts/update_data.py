#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_data.py —— 牛熊自检台 每日数据自动更新（GitHub Actions 触发）
=========================================================================

职责
----
1) quotes.json  —— 【真实源】腾讯行情接口 qt.gtimg.cn
   抓取 A股 5 大指数（沪深300 / 上证 / 深成指 / 创业板 / 科创50）的
   点位、涨跌幅、成交额，写回 docs/niuxiong-zijiantai/data/quotes.json。
   字段布局（已对照接口实测，GBK 编码，~ 分隔）：
     [0] 市场类型  [1] 名称  [2] 代码
     [3] 当前点位(price)   [5] 涨跌幅%(pct)
     [7] 成交额(万元)  → amtYi(亿元) = [7] / 10000
   （经验证：49617913 / 10000 = 4961.7913，与现有 quotes.json 完全吻合）

2) macro.json / backtest.json —— 【占位 / 待接入真实源】
   当前仅生成「基线 / 占位」版本，结构同 docs/niuxiong-zijiantai/data/*，但数值为 null 并标注
   【占位·真实数据源待接入】。真实数据源（统计局 / 央行 / FRED / CBOE / 港交所
   等）后续接入，详见 MACRO_TODO / BACKTEST_TODO。
   ★ 生产环境默认【不覆盖】这两个文件；加 --seed 才生成占位版（仅用于初始化仓库）。

用法
----
    python update_data.py            # 抓行情 → 写回 quotes.json（失败则优雅跳过）
    python update_data.py --demo     # 离线演示：无论网络是否可用都写一份占位 quotes.json
    python update_data.py --seed     # 额外生成 macro.json / backtest.json 占位版（会覆盖！）
    python update_data.py --dry-run  # 只打印将要写出的内容，不落盘（用于自检，不覆盖任何文件）
    python update_data.py --self-test# 内置断言：校验占位生成器的结构与 JSON 合法性后退出

退出码：0=成功或已优雅跳过；2=致命错误（不应发生）。
"""

import argparse
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

# ── 路径（脚本位于 <repo>/scripts/，数据位于 <repo>/niuxiong-zijiantai/data/） ──
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "docs" / "niuxiong-zijiantai" / "data"
QUOTES_PATH = DATA_DIR / "quotes.json"
MACRO_PATH = DATA_DIR / "macro.json"
BACKTEST_PATH = DATA_DIR / "backtest.json"

# ── 腾讯行情接口 ────────────────────────────────────────────────────────────
TENCENT_URL = "https://qt.gtimg.cn/q=" + ",".join([
    "s_sh000300", "s_sh000001", "s_sz399001", "s_sz399006", "s_sh000688",
])
# 请求代码 → quotes.json 顶层 key
KEY_BY_CODE = {
    "s_sh000300": "hs300",
    "s_sh000001": "sh",
    "s_sz399001": "sz",
    "s_sz399006": "cyb",
    "s_sh000688": "kc",
}

# ── macro / backtest 真实数据源接入 TODO ──────────────────────────────────────
MACRO_TODO = (
    "macro.json 真实数据源待接入：PMI/社融/M2(央行)、LPR(央行)、"
    "中债/美债10年(中债/FRED)、沪深300 PE/PB分位(中证/乐咕)、"
    "恒生分位(恒生)、两融(交易所)、北向(港交所)、VIX(CBOE)、"
    "失业率(BLS/FRED)、纳指(纳斯达克) 等。当前为 null 占位，前端会回退内置基线快照。"
)
BACKTEST_TODO = (
    "backtest.json 真实数据源待接入：需按 2015 至今月度温度 × 其后 21/63 天指数收益"
    "回测计算产出（温度由 compute.js 同口径得出）。当前为占位空序列，history 页会显示空态。"
)

# macro 占位所需的 29 个字段（与 fetcher.BASELINE_SNAPSHOT 字段名一致，值留 null）
MACRO_FIELDS = [
    "pmi", "m1_yoy", "m2_yoy", "credit_yoy", "lpr1y", "cn10y", "us10y",
    "hs300_pe", "hs300_pe_pct", "hs300_pb_pct", "hsi_pe_pct", "erp",
    "margin_yi", "northbound", "breadth_up", "ah_premium", "amt_yi",
    "oil_brent", "dxy", "us_unemploy", "nasdaq_pct", "re_yoy", "vix",
    "trade_balance", "ai_bubble", "hormuz_risk", "paths_lit",
    "win_proximity", "china_fragile",
]


# ── 行情抓取与解析 ──────────────────────────────────────────────────────────
def fetch_tencent(url=TENCENT_URL, timeout=10):
    """返回腾讯接口原始文本；失败抛异常。"""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        # 接口返回 GBK；ignore 容错避免个别字节解码失败
        return resp.read().decode("gbk", "ignore")


def parse_tencent(text):
    """解析腾讯接口文本 → {key: {price, pct, amtYi}}。只解析请求到的 5 个指数。"""
    out = {}
    # 形如  v_s_sh000300="1~沪深300~...~";
    for line in text.split(";"):
        line = line.strip()
        if not line.startswith("v_"):
            continue
        name, _, val = line.partition("=")
        code = name[2:]                      # 去掉前缀 "v_"
        key = KEY_BY_CODE.get(code)
        if not key or not val:
            continue
        parts = val.strip('"').split("~")
        try:
            price = float(parts[3])
            pct = float(parts[5])
            # [7] 成交额(万元) → 亿元
            amt_yi = round(float(parts[7]) / 10000.0, 4)
        except (IndexError, ValueError):
            # 单条解析失败不致命，跳过该指数
            sys.stderr.write(f"[warn] 解析失败，跳过 {code}\n")
            continue
        out[key] = {"price": price, "pct": pct, "amtYi": amt_yi}
    return out


def build_quotes(parsed, as_of, ok=True):
    """由解析结果构造 quotes.json 顶层结构。"""
    quotes = {}
    for key in KEY_BY_CODE.values():
        quotes[key] = parsed.get(key, {"price": None, "pct": None, "amtYi": None})
    quotes["amtTotalYi"] = round(
        sum((q["amtYi"] or 0) for q in quotes.values()
            if isinstance(q, dict)), 4
    )
    quotes["ok"] = ok and all(
        isinstance(q, dict) and q.get("price") is not None for q in quotes.values()
        if isinstance(q, dict)
    )
    quotes["asOf"] = as_of
    return quotes


def build_demo_quotes(as_of):
    """离线演示占位 quotes.json（数值非真实，仅保证结构合法、脚本可跑通）。"""
    demo = {
        "hs300": {"price": 4317.25, "pct": 0.16, "amtYi": 4961.7913},
        "sh": {"price": 3813.79, "pct": 0.05, "amtYi": 8885.612},
        "sz": {"price": 12641.86, "pct": 0.17, "amtYi": 10119.9422},
        "cyb": {"price": 3043.33, "pct": 0.22, "amtYi": 4920.454},
        "kc": {"price": 1457.27, "pct": 0.07, "amtYi": 919.7294},
    }
    quotes = dict(demo)
    quotes["amtTotalYi"] = round(sum(v["amtYi"] for v in demo.values()), 4)
    quotes["ok"] = False            # 演示数据，标记不可用
    quotes["demo"] = True
    quotes["asOf"] = as_of
    return quotes


# ── macro / backtest 占位生成器 ───────────────────────────────────────────────
def build_macro_placeholder(as_of):
    data = {}
    for f in MACRO_FIELDS:
        data[f] = {"value": None, "asOf": None,
                   "src": "【占位·真实数据源待接入】"}
    return {"data": data, "generated_at": as_of + "T00:00:00+08:00",
            "_todo": MACRO_TODO}


def build_backtest_placeholder():
    return {"_todo": BACKTEST_TODO, "rows": []}


# ── 写盘 ────────────────────────────────────────────────────────────────────
def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def update_quotes(demo=False, dry_run=False):
    as_of = date.today().isoformat()
    if demo:
        quotes = build_demo_quotes(as_of)
        sys.stderr.write("[info] 使用 --demo 占位行情（非真实数据）\n")
    else:
        try:
            text = fetch_tencent()
            parsed = parse_tencent(text)
            if not parsed:
                raise ValueError("接口返回为空或字段布局变化")
            quotes = build_quotes(parsed, as_of, ok=True)
            sys.stderr.write(f"[info] 已抓取 {len(parsed)} 个指数行情\n")
        except Exception as e:  # 网络/解析失败：优雅跳过，不覆盖现有文件
            sys.stderr.write(f"[warn] 行情抓取失败：{type(e).__name__}: {e}\n")
            sys.stderr.write("[warn] 保留现有 quotes.json，本次不更新（exit 0）\n")
            return False
    if dry_run:
        print(json.dumps(quotes, ensure_ascii=False, indent=2))
    else:
        write_json(QUOTES_PATH, quotes)
        sys.stderr.write(f"[ok] 写回 {QUOTES_PATH}\n")
    return True


def seed_macro_backtest(dry_run=False):
    as_of = date.today().isoformat()
    macro = build_macro_placeholder(as_of)
    backtest = build_backtest_placeholder()
    if dry_run:
        print("--- macro.json (placeholder) ---")
        print(json.dumps(macro, ensure_ascii=False, indent=2))
        print("--- backtest.json (placeholder) ---")
        print(json.dumps(backtest, ensure_ascii=False, indent=2))
    else:
        write_json(MACRO_PATH, macro)
        write_json(BACKTEST_PATH, backtest)
        sys.stderr.write(f"[ok] 写回占位 {MACRO_PATH} / {BACKTEST_PATH}\n")


def self_test():
    """内置断言：校验占位生成器结构与 JSON 合法性。"""
    as_of = date.today().isoformat()
    q = build_demo_quotes(as_of)
    assert set(q.keys()) >= {"hs300", "sh", "sz", "cyb", "kc", "amtTotalYi", "ok", "asOf"}
    for k in ("hs300", "sh", "sz", "cyb", "kc"):
        assert set(q[k].keys()) == {"price", "pct", "amtYi"}
    assert isinstance(q["amtTotalYi"], (int, float))
    m = build_macro_placeholder(as_of)
    assert len(m["data"]) == len(MACRO_FIELDS)
    b = build_backtest_placeholder()
    assert "rows" in b
    # 真实抓取路径（联网时）也能解析
    try:
        parsed = parse_tencent(fetch_tencent())
        rq = build_quotes(parsed, as_of)
        assert rq["ok"] is True
        sys.stderr.write(f"[self-test] 实时抓取解析 OK，{len(parsed)} 个指数\n")
    except Exception as e:
        sys.stderr.write(f"[self-test] 实时抓取不可用（跳过，不影响占位自检）：{e}\n")
    sys.stderr.write("[self-test] 占位结构全部通过 ✓\n")


def main():
    ap = argparse.ArgumentParser(description="牛熊自检台 数据更新")
    ap.add_argument("--demo", action="store_true", help="离线演示占位 quotes.json")
    ap.add_argument("--seed", action="store_true", help="额外生成 macro/backtest 占位版（会覆盖）")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不落盘")
    ap.add_argument("--self-test", action="store_true", help="内置结构断言后退出")
    args = ap.parse_args()

    if args.self_test:
        self_test()
        return

    ok = update_quotes(demo=args.demo, dry_run=args.dry_run)
    if args.seed:
        seed_macro_backtest(dry_run=args.dry_run)
    # ok=False 表示实时抓取失败且未用 demo：优雅跳过（exit 0），不阻断 Actions
    sys.exit(0)


if __name__ == "__main__":
    main()
