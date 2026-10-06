#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日任务：真正把「自动」跑完一圈
------------------------------------------------
  抓数据 → 拉行情 → 算仓位 → 存快照 → 判断要不要提醒你

告警触发条件（阈值可在环境变量调）：
  1) 抓取失败项 ≥ FETCH_FAIL_ALERT（默认 2）；
  2) 建议仓位较上一交易日变动 ≥ POS_DELTA_ALERT（默认 1.0 成）；
  3) 数据整体陈旧 > STALE_DAYS（默认 3 天）—— 说明脚本好几天没跑成功。

用法：
    python3 daily_job.py             # 正常跑（cron 每天 18:30）
    python3 daily_job.py --dry-run   # 只算不存不告警（调试用）
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "niuxiong.db")

import engine
import quote as quote_mod
import fetch_macro
import alert


def latest_macro() -> dict:
    if not os.path.exists(DB_PATH):
        return {}
    con = sqlite3.connect(DB_PATH)
    row = con.execute("SELECT payload FROM macro ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    return json.loads(row[0]) if row else {}


def save_snapshot(day: str, res: dict):
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS snapshot(
        id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, mode TEXT,
        temp REAL, pos REAL, resonance REAL, quad TEXT, payload TEXT,
        UNIQUE(date, mode))""")
    con.execute("""INSERT OR REPLACE INTO snapshot(date,mode,temp,pos,resonance,quad,payload)
                   VALUES(?,?,?,?,?,?,?)""",
                (day, res["mode"], res["temp"], res["final"], res["resonance"],
                 res["quad"]["name"], json.dumps(res, ensure_ascii=False)))
    con.commit()
    con.close()


def prev_snapshot(mode: str, before: str):
    con = sqlite3.connect(DB_PATH)
    row = con.execute("SELECT date,pos,temp FROM snapshot WHERE mode=? AND date<? ORDER BY date DESC LIMIT 1",
                      (mode, before)).fetchone()
    con.close()
    return row


def data_age_days(data: dict) -> int:
    """用最新一项的 asOf 估算数据陈旧天数"""
    best = None
    for v in data.values():
        if isinstance(v, dict) and v.get("asOf"):
            best = max(best or v["asOf"], v["asOf"])
    if not best:
        return 999
    try:
        d = dt.datetime.strptime(str(best)[:10], "%Y-%m-%d").date()
        return (dt.date.today() - d).days
    except ValueError:
        return 999


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-fetch", action="store_true", help="跳过抓取，只用库里现有数据")
    args = ap.parse_args()

    failed = []
    if not args.no_fetch:
        import sys as _sys
        _sys.argv = ["fetch_macro.py", "--out", os.path.join(BASE_DIR, "docs", "macro.json")]
        rc = fetch_macro.main()
        if rc != 0:
            failed.append("抓取整体异常")
    data = latest_macro()
    if not data:
        print("[FATAL] 无数据，先跑 python3 fetch_macro.py")
        return 2

    q = quote_mod.fetch_quote(force=True)
    if not q.get("ok"):
        failed.append("实时行情获取失败")

    results = {}
    for mode in ("A", "H"):
        results[mode] = engine.decide(data, q, mode=mode,
                                      conservative=float(os.environ.get("NX_CONSERVATIVE", "0.85")))
    day = dt.date.today().isoformat()

    print(f"\n=== {day} 计算结果 ===")
    for mode, r in results.items():
        print(f"[{mode}股] 温度 {r['temp']}（{r['tag']}） 基础 {r['base']}成 → 约束 {r['cap']}成 "
              f"→ 建议 {r['final']}成｜{r['quad']['name']}（{r['quad']['advice']}）")
        print(f"        卡在：{'/'.join(r['tight'])}｜共振 {r['resonance']*100:.0f}%")

    if args.dry_run:
        print("\n[DRY-RUN] 未写入、未告警")
        return 0

    for mode, r in results.items():
        save_snapshot(day, r)

    # ---------- 告警判断 ----------
    fail_n = len([k for k, v in data.items() if isinstance(v, dict) and v.get("stale")]) + len(failed)
    pos_delta_alert = float(os.environ.get("POS_DELTA_ALERT", "1.0"))
    stale_days = int(os.environ.get("STALE_DAYS", "3"))

    msgs = []
    if fail_n >= int(os.environ.get("FETCH_FAIL_ALERT", "2")):
        msgs.append(("数据抓取异常", f"今日异常项 {fail_n} 个：{failed}；"
                                     f"陈旧字段：{[k for k,v in data.items() if isinstance(v,dict) and v.get('stale')]}\n"
                                     f"处理：登录服务器跑 `cd {BASE_DIR} && python3 fetch_macro.py` 看报错。"))
    if data_age_days(data) > stale_days:
        msgs.append(("数据已陈旧", f"最新宏观数据距今 {data_age_days(data)} 天，定时任务可能没跑。"))

    for mode, r in results.items():
        prev = prev_snapshot(mode, day)
        if prev and abs(float(prev[1]) - r["final"]) >= pos_delta_alert:
            msgs.append((f"{mode}股仓位变动提醒",
                         f"{prev[0]} 建议 {prev[1]}成 → 今日 {r['final']}成（{r['tag']}）\n"
                         f"温度 {r['temp']}｜基础 {r['base']}成｜约束 {r['cap']}成（卡在 {'/'.join(r['tight'])}）\n"
                         f"落点：{r['quad']['name']} —— {r['quad']['advice']}\n"
                         f"共振 {r['resonance']*100:.0f}%｜四维 "
                         f"趋势{r['dims']['trend']['v']} 估值{r['dims']['val']['v']} "
                         f"流动性{r['dims']['liq']['v']} 情绪{r['dims']['emo']['v']}"))

    if msgs:
        for title, body in msgs:
            print(f"[ALERT] {title}")
            print(alert.send(title, body, tags=["牛熊自查"]))
    else:
        print("[OK] 无需告警")
    return 0


if __name__ == "__main__":
    sys.exit(main())
