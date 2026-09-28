# -*- coding: utf-8 -*-
"""
实时行情（服务端抓取，UTF-8 输出）
------------------------------------------------
为什么要走服务端：
  1) 腾讯接口返回 GBK，浏览器直接读容易乱码；
  2) 服务端可缓存 60 秒，避免每次开页面都打上游接口（防封 IP）；
  3) 不依赖浏览器跨域策略，前端拿到就是干净 JSON。
"""
from __future__ import annotations

import re
import time
from typing import Any

import requests

QUOTE_URL = "https://qt.gtimg.cn/q="
CODES = "s_sh000300,s_sh000001,s_sz399001,s_sz399006,s_sh000688,hkHSI,hkHSTECH,usIXIC,usVIX"
TIMEOUT = 8
_CACHE: dict[str, Any] = {"ts": 0.0, "data": None}
CACHE_TTL = 60          # 秒


def _parse(raw: str) -> dict[str, list[str]]:
    out = {}
    for code, body in re.findall(r'v_(\w+)="([^"]*)"', raw):
        out[code] = body.split("~")
    return out


def fetch_quote(force: bool = False) -> dict[str, Any]:
    """返回 {ok, hs300_pct, hsi_pct, amt_yi, vix, prices, quote_time, raw_codes}"""
    now = time.time()
    if not force and _CACHE["data"] and now - _CACHE["ts"] < CACHE_TTL:
        return _CACHE["data"]

    res: dict[str, Any] = {"ok": False}
    try:
        r = requests.get(QUOTE_URL + CODES, timeout=TIMEOUT,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.encoding = "gbk"
        f = _parse(r.text)
        a = lambda c, i: (f.get(c) or [None] * 10)[i]      # noqa: E731

        def num(x):
            try:
                return float(x)
            except (TypeError, ValueError):
                return None

        hs300_pct, hsi_pct = num(a("s_sh000300", 5)), num(a("hkHSI", 32))
        sh_amt, sz_amt = num(a("s_sh000001", 7)), num(a("s_sz399001", 7))
        amt_yi = None if (sh_amt is None or sz_amt is None) else (sh_amt + sz_amt) / 10000
        res.update({
            "ok": bool(hs300_pct is not None and hsi_pct is not None and amt_yi),
            "hs300_pct": hs300_pct, "hsi_pct": hsi_pct, "amt_yi": amt_yi,
            "vix": num(a("usVIX", 3)),
            "quote_time": a("hkHSI", 30),
            "vix_time": a("usVIX", 30),
            "prices": {
                "hs300": num(a("s_sh000300", 3)), "sh": num(a("s_sh000001", 3)),
                "sz": num(a("s_sz399001", 3)), "cyb": num(a("s_sz399006", 3)),
                "hsi": num(a("hkHSI", 3)), "hstech": num(a("hkHSTECH", 3)),
                "ndx": num(a("usIXIC", 3)),
            },
            "pcts": {
                "cyb": num(a("s_sz399006", 5)), "hstech": num(a("hkHSTECH", 32)),
                "ndx": num(a("usIXIC", 32)),
            },
        })
    except Exception as e:  # noqa: BLE001
        res["error"] = f"{type(e).__name__}"
    _CACHE.update(ts=now, data=res)
    return res


if __name__ == "__main__":
    import json
    print(json.dumps(fetch_quote(force=True), ensure_ascii=False, indent=2))
