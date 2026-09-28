#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
牛熊自查 · 服务端（真正自动化的那一半）
------------------------------------------------
接口：
  GET  /                  前端页面
  GET  /api/state         一次拿全：宏观数据 + 实时行情 + 服务端算好的决策（推荐前端只调这个）
  GET  /api/macro         最新宏观/估值/资金数据
  GET  /api/quote         实时行情（服务端代理，UTF-8 JSON）
  GET  /api/decide        服务端算出的温度/四维/仓位
  GET  /api/history       历史快照（供回看校准）
  POST /api/snapshot      保存当日快照
  GET  /api/health        健康检查（不鉴权，给监控用）

安全默认：
  · 默认只监听 127.0.0.1（由 Nginx 反代对外），想直连需 BIND=0.0.0.0；
  · 未设置 NX_PASSWORD 时自动生成随机密码并打印一次 —— 绝不裸奔；
  · /api/* 限速；响应加安全头；行情代理只放行白名单域名（防 SSRF）。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import time
from functools import wraps

from flask import Flask, Response, jsonify, request, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
DB_PATH = os.path.join(BASE_DIR, "niuxiong.db")
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

import engine
import quote as quote_mod

# ---------- 读 config.env（存在时），平台注入的环境变量优先级更高 ----------
def _load_env_file(path):
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    except FileNotFoundError:
        pass


_load_env_file(os.path.join(BASE_DIR, "config.env"))

# ---------- 密码：没配就自动生成，避免裸奔 ----------
PASSWD = os.environ.get("NX_PASSWORD", "")

# ---------- 链接口令（?token=xxx） ----------
# 用途：部分发布网关/预览代理会剥离 Authorization 请求头，导致 Basic Auth 永远 401。
# 这时用查询串口令访问：  https://域名/?token=你的口令
# 正式服务器（自己配 HTTPS）仍建议只用 Basic Auth，可设 NX_ALLOW_TOKEN=0 关闭本通道。
TOKEN = os.environ.get("NX_TOKEN") or PASSWD
ALLOW_TOKEN = os.environ.get("NX_ALLOW_TOKEN", "1") not in ("0", "false", "False")

if not PASSWD:
    PASSWD = secrets.token_urlsafe(10)
    TOKEN = PASSWD
    print("=" * 60, file=sys.stderr)
    print(f"[安全] 未设置 NX_PASSWORD，已生成临时密码：{PASSWD}", file=sys.stderr)
    print("[安全] 请在环境变量里固定它：export NX_PASSWORD=你自己的密码", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

BIND = os.environ.get("BIND", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
RATE_N = int(os.environ.get("RATE_N", "120"))
RATE: dict[str, list] = {}

app = Flask(__name__, static_folder=None)


# ---------- 安全中间件 ----------
def unauthorized():
    return Response("需要登录", 401, {"WWW-Authenticate": 'Basic realm="niuxiong"'})


def limit(n=RATE_N, win=60):
    def deco(f):
        @wraps(f)
        def wrapped(*a, **kw):
            ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0]
            now = time.time()
            c, t0 = RATE.get(ip, [0, now])
            if now - t0 > win:
                c, t0 = 0, now
            c += 1
            RATE[ip] = [c, t0]
            if c > n:
                return jsonify({"ok": False, "error": "请求过于频繁"}), 429
            return f(*a, **kw)
        return wrapped
    return deco


@app.before_request
def guard():
    if request.path.startswith("/api/health"):
        return None
    auth = request.authorization
    if auth and auth.password and auth.password == PASSWD:
        return None
    # 兜底：链接口令（网关剥离 Authorization 时用）
    if ALLOW_TOKEN and TOKEN and request.args.get("token") == TOKEN:
        return None
    return unauthorized()


@app.after_request
def headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ---------- 数据访问 ----------
def latest_macro():
    if not os.path.exists(DB_PATH):
        return {}, None
    con = sqlite3.connect(DB_PATH)
    row = con.execute("SELECT ts,payload FROM macro ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    return (json.loads(row[1]), row[0]) if row else ({}, None)


# ---------- 数据新鲜度 + 过期自动补抓（Render 等无外部定时任务时用） ----------
def _data_age_days(ts):
    if not ts:
        return 999
    try:
        d = dt.datetime.strptime(ts.split(".")[0], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return 999
    return (dt.datetime.now() - d).days


_REFRESH_LOCK = False
def maybe_refresh():
    """数据过期或缺失时，现场跑一次 fetch_macro 补抓（仅一次，避免并发）"""
    if os.environ.get("NX_AUTO_REFRESH", "1") == "0":
        return
    data, ts = latest_macro()
    if data and _data_age_days(ts) <= int(os.environ.get("STALE_DAYS", "3")):
        return  # 数据还新鲜
    global _REFRESH_LOCK
    if _REFRESH_LOCK:
        return
    _REFRESH_LOCK = True
    try:
        subprocess.run([sys.executable, os.path.join(BASE_DIR, "fetch_macro.py")],
                       cwd=BASE_DIR, timeout=200, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    finally:
        _REFRESH_LOCK = False


# ---------- 页面 ----------
@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/<path:name>")
def files(name):
    if ".." in name or name.startswith("/"):
        return "bad path", 400
    return send_from_directory(WEB_DIR, name)


# ---------- API ----------
@app.get("/api/health")
def health():
    data, ts = latest_macro()
    return jsonify({"ok": True, "time": dt.datetime.now().isoformat(timespec="seconds"),
                    "has_data": bool(data), "macro_at": ts})


@app.get("/api/macro")
@limit()
def api_macro():
    data, ts = latest_macro()
    if not data:
        return jsonify({"ok": False, "error": "尚无数据，请先运行 fetch_macro.py"}), 404
    return jsonify({"ok": True, "generated_at": ts, "data": data})


@app.get("/api/quote")
@limit()
def api_quote():
    q = quote_mod.fetch_quote(force=request.args.get("force") == "1")
    return jsonify({"ok": q.get("ok", False), **q})


@app.get("/api/decide")
@limit()
def api_decide():
    maybe_refresh()
    data, ts = latest_macro()
    if not data:
        return jsonify({"ok": False, "error": "尚无数据"}), 404
    mode = request.args.get("mode", "A").upper()
    if mode not in ("A", "H"):
        mode = "A"
    q = quote_mod.fetch_quote()
    cons = float(request.args.get("conservative", os.environ.get("NX_CONSERVATIVE", "0.85")))
    return jsonify({"ok": True, "generated_at": ts, "quote": q,
                    "decision": engine.decide(data, q, mode=mode, conservative=cons)})


@app.get("/api/state")
@limit()
def api_state():
    """前端一次拿全：宏观 + 行情 + 两个市场的决策"""
    maybe_refresh()
    data, ts = latest_macro()
    q = quote_mod.fetch_quote()
    cons = float(request.args.get("conservative", os.environ.get("NX_CONSERVATIVE", "0.85")))
    out = {"ok": bool(data), "generated_at": ts, "data": data, "quote": q,
           "decisions": {"A": None, "H": None}}
    if data:
        out["decisions"] = {m: engine.decide(data, q, mode=m, conservative=cons) for m in ("A", "H")}
    return jsonify(out)


@app.post("/api/snapshot")
@limit(30)
def api_snapshot():
    body = request.get_json(silent=True) or {}
    if not body.get("date"):
        return jsonify({"ok": False, "error": "缺少 date"}), 400
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS snapshot(
        id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, mode TEXT,
        temp REAL, pos REAL, resonance REAL, quad TEXT, payload TEXT,
        UNIQUE(date, mode))""")
    con.execute("""INSERT OR REPLACE INTO snapshot(date,mode,temp,pos,resonance,quad,payload)
                   VALUES(?,?,?,?,?,?,?)""",
                (body["date"], body.get("mode", "A"), body.get("temp"), body.get("pos"),
                 body.get("resonance"), body.get("quad"), json.dumps(body, ensure_ascii=False)))
    con.commit()
    con.close()
    return jsonify({"ok": True})


@app.get("/api/history")
@limit()
def api_history():
    if not os.path.exists(DB_PATH):
        return jsonify({"ok": True, "rows": []})
    con = sqlite3.connect(DB_PATH)
    try:
        rows = con.execute("""SELECT date,mode,temp,pos,resonance,quad FROM snapshot
                              ORDER BY date DESC, mode LIMIT ?""",
                           (int(request.args.get("limit", "120")),)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    con.close()
    return jsonify({"ok": True, "rows": [dict(zip(
        ["date", "mode", "temp", "pos", "resonance", "quad"], r)) for r in rows]})


if __name__ == "__main__":
    print(f"[INFO] 监听 {BIND}:{PORT}（生产请让 Nginx 反代，别直接暴露）")
    app.run(host=BIND, port=PORT)
