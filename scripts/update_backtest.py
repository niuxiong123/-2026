# -*- coding: utf-8 -*-
# update_backtest.py —— 回测序列向前自动追加（第⑥步 item1：回测数据源接入自动采集）
#
# 原则（诚实优先）：
#   1. 只追加，永不修改/删除既有 138 行历史（2015-01 ~ 2026-06 为首发静态回测）。
#   2. 新增行必须「双成熟」才落库：
#      a) tempAdj：该月至少 5 个日度温度记录（来自 temp_daily.json，2026-10 管线启用后才有）；
#      b) fwd21/fwd63：月末后 21/63 个交易日已走完（数据源：新浪 sh000300 日线收盘，
#         本机与 GitHub Actions 均可达）。
#   3. 新增行带 src/index 标注字段（前端只读 date/tempAdj/fwd21/fwd63，多余键无害），
#      与历史行的口径差异如实可查：tempAdj=当月日度温度均值，收益=沪深300收盘。
#   4. 任何一步数据不足 → 跳过该月，不造数。
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "docs" / "niuxiong-zijiantai"
BACKTEST = SITE / "data" / "backtest.json"
TEMP_DAILY = SITE / "data" / "temp_daily.json"
MIN_DAYS = 5  # 月内日度温度至少 5 个记录才算数


def log(msg):
    print(msg, flush=True)


def month_iter(start_ym, end_ym):
    y, m = int(start_ym[:4]), int(start_ym[5:7])
    ey, em = int(end_ym[:4]), int(end_ym[5:7])
    while (y, m) <= (ey, em):
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m > 12:
            y, m = y + 1, 1


def fetch_index_closes(ak):
    """沪深300 日度收盘（新浪 stock_zh_index_daily，本机与 GH Actions 均可达）→ [(date, close)] 升序。
    注意：乐咕 stock_index_pe_lg 的指数列是月度点位，不能用于交易日偏移，勿改回。"""
    df = ak.stock_zh_index_daily(symbol="sh000300")
    out = []
    for _, r in df.iterrows():
        d = r["date"]
        d = d.date() if hasattr(d, "date") else d
        c = r.get("close")
        if c is None or c != c:  # NaN
            continue
        out.append((d, float(c)))
    out.sort(key=lambda x: x[0])
    return out


def month_end_close(closes, ym):
    """该月最后一个交易日的 (index_in_list, close)。"""
    last = None
    for i, (d, c) in enumerate(closes):
        if d.strftime("%Y-%m") == ym:
            last = (i, c)
    return last


def fwd_return(closes, t_idx, days):
    """月末收盘后第 days 个交易日的收益率%。不足则 None。"""
    j = t_idx + days
    if j >= len(closes):
        return None
    base = closes[t_idx][1]
    if base <= 0:
        return None
    return round((closes[j][1] / base - 1.0) * 100.0, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true", help="离线结构自检（不联网）")
    args = ap.parse_args()

    rows = json.loads(BACKTEST.read_text(encoding="utf-8"))
    assert isinstance(rows, list) and len(rows) > 100, "backtest.json 异常"
    dates = {r["date"] for r in rows}
    assert all(set(("date", "tempAdj", "fwd21", "fwd63")) <= set(r) for r in rows), "字段异常"
    last_ym = max(r["date"] for r in rows)

    if args.self_test:
        log(f"[self-test] backtest.json {len(rows)} 行，末行 {last_ym}，结构 OK")
        if TEMP_DAILY.exists():
            td = json.loads(TEMP_DAILY.read_text(encoding="utf-8"))
            log(f"[self-test] temp_daily.json {len(td)} 条（{td[0]['date']} ~ {td[-1]['date']}）")
        else:
            log("[self-test] temp_daily.json 不存在（管线未启用）")
        log("[self-test] 占位结构全部通过 ✓")
        return 0

    import akshare as ak

    # 月度温度：temp_daily 按月聚合
    month_temps = {}
    if TEMP_DAILY.exists():
        for r in json.loads(TEMP_DAILY.read_text(encoding="utf-8")):
            month_temps.setdefault(r["date"][:7], []).append(float(r["temp"]))

    today = dt.date.today()
    candidates = [ym for ym in month_iter(last_ym, today.strftime("%Y-%m")) if ym != last_ym]
    if not candidates:
        log("[ok] 无待处理月份")
        return 0

    closes = fetch_index_closes(ak)
    log(f"[info] 指数点位 {len(closes)} 日（{closes[0][0]} ~ {closes[-1][0]}）")

    appended = []
    for ym in candidates:
        if ym in dates:
            continue
        temps = month_temps.get(ym, [])
        if len(temps) < MIN_DAYS:
            log(f"[skip] {ym}: 日度温度仅 {len(temps)} 天（<{MIN_DAYS}），无真实温度不造数")
            continue
        me = month_end_close(closes, ym)
        if me is None:
            log(f"[skip] {ym}: 指数序列无该月数据")
            continue
        f21 = fwd_return(closes, me[0], 21)
        f63 = fwd_return(closes, me[0], 63)
        if f21 is None or f63 is None:
            log(f"[skip] {ym}: 21/63 交易日未走完（f21={f21} f63={f63}），双成熟才落库")
            continue
        rows.append({
            "date": ym,
            "tempAdj": round(sum(temps) / len(temps), 2),
            "fwd21": f21,
            "fwd63": f63,
            "src": "pipeline",
            "index": "hs300(新浪日线)",
            "tempDays": len(temps),
        })
        appended.append(ym)
        log(f"[ok] 追加 {ym}: tempAdj={rows[-1]['tempAdj']}（{len(temps)}天均值） fwd21={f21}% fwd63={f63}%")

    if not appended:
        log("[ok] 本轮无可追加月份（温度或收益未成熟均如实跳过）")
        return 0

    rows.sort(key=lambda r: r["date"])
    tmp = BACKTEST.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(BACKTEST)
    log(f"[ok] 写回 {BACKTEST}｜新增 {len(appended)} 行：{', '.join(appended)}（现共 {len(rows)} 行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
