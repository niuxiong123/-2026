# -*- coding: utf-8 -*-
"""
告警通道：让「自动化」真的闭环 —— 数据坏了你知道，仓位该动了你也知道。
------------------------------------------------
支持三种，配了哪个用哪个（都支持时全部发送）：
  1) 邮件 SMTP：SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASS / ALERT_TO
  2) Server酱：SERVERCHAN_KEY  （sct.ftqq.com，微信推送，个人免费）
  3) 企业微信机器人：WECOM_WEBHOOK

一个都没配 → 只写 Alert 日志（logs/alert.log），不报错。
"""
from __future__ import annotations

import json
import os
import smtplib
import traceback
from email.header import Header
from email.mime.text import MIMEText
from typing import Iterable

import requests

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")


def _log(msg: str):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(os.path.join(LOG_DIR, "alert.log"), "a", encoding="utf-8") as f:
        f.write(msg.rstrip() + "\n")


def _env(*names, default=""):
    for n in names:
        v = os.environ.get(n, "")
        if v:
            return v
    return default


def channels() -> list[str]:
    out = []
    if _env("SMTP_HOST") and _env("ALERT_TO"):
        out.append("邮件")
    if _env("SERVERCHAN_KEY"):
        out.append("Server酱")
    if _env("WECOM_WEBHOOK"):
        out.append("企业微信")
    return out or ["仅日志"]


def _send_mail(title: str, body: str):
    host = _env("SMTP_HOST")
    port = int(_env("SMTP_PORT", default="465"))
    user = _env("SMTP_USER")
    pwd = _env("SMTP_PASS")
    to = [x.strip() for x in _env("ALERT_TO").split(",") if x.strip()]
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(title, "utf-8")
    msg["From"], msg["To"] = user, ",".join(to)
    if port == 465:
        s = smtplib.SMTP_SSL(host, port, timeout=15)
    else:
        s = smtplib.SMTP(host, port, timeout=15)
        s.starttls()
    s.login(user, pwd)
    s.sendmail(user, to, msg.as_string())
    s.quit()


def _send_serverchan(title: str, body: str):
    key = _env("SERVERCHAN_KEY")
    requests.post(f"https://sctapi.ftqq.com/{key}.send",
                  data={"title": title, "desp": body}, timeout=15)


def _send_wecom(title: str, body: str):
    requests.post(_env("WECOM_WEBHOOK"),
                  json={"msgtype": "text", "text": {"content": f"{title}\n\n{body}"}}, timeout=15)


def send(title: str, body: str, tags: Iterable[str] = ()):
    """返回 {"ok":bool, "channels":[...], "error":...}"""
    tag = " ".join(f"[{t}]" for t in tags)
    full = f"{tag} {title}" if tag else title
    ok, err = True, ""
    for name, fn in (("邮件", _send_mail), ("Server酱", _send_serverchan), ("企业微信", _send_wecom)):
        try:
            if name == "邮件" and not (_env("SMTP_HOST") and _env("ALERT_TO")):
                continue
            if name == "Server酱" and not _env("SERVERCHAN_KEY"):
                continue
            if name == "企业微信" and not _env("WECOM_WEBHOOK"):
                continue
            fn(full, body)
        except Exception as e:  # noqa: BLE001
            ok = False
            err += f"{name}:{type(e).__name__} {str(e)[:60]}; "
    _log(f"[{_ts()}] {full}\n{body}\n{'-'*40}")
    return {"ok": ok, "channels": channels(), "error": err}


def _ts():
    import datetime as dt
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    print(json.dumps(send("测试告警", "如果你收到这条，说明告警通道配置成功。"), ensure_ascii=False))
