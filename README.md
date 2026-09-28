# 牛熊自查 · 后端（真正自动化的那一半）

一句话：**服务器每天自己抓数据、自己算仓位、该动手时主动通知你**；你打开网页只看结论。

## 一、它解决了什么问题

以前那版是「静态页面」：浏览器最多能直接拉到腾讯行情，PMI / M1 / 社融 / 估值 / 两融这些**没有跨域接口**，浏览器拉不到（实测资料库托管时 `macro.json` 直接 404）。所以宏观数据只能靠你手动跑脚本再上传 —— 那不叫自动化。

现在补上后端之后：

```
腾讯行情 ─┐
          ├─→ 服务器定时抓取 → SQLite(90天留档) → 引擎打分 → 网页 / 告警
宏观数据 ─┘        ↑                                  ↓
              fetch_macro.py                    daily_job.py（每天18:30）
```

| 环节 | 谁做 | 什么时候 |
|---|---|---|
| 抓宏观/估值/资金 | `fetch_macro.py` | 工作日 18:30（systemd timer / cron） |
| 拉实时行情 | `quote.py`（服务端代理，缓存 60 秒） | 打开页面时 |
| 算温度/仓位 | `engine.py`（单一真相源） | 打开页面时 + 每日任务 |
| 存快照、判断告警 | `daily_job.py` | 每天 18:30 |
| 推送提醒 | `alert.py`（邮件 / Server酱 / 企微） | 触发条件满足时 |

## 二、目录

```
niuxiong-server/
├── app.py            Web 服务（API + 页面 + 鉴权 + 限流）
├── engine.py         打分与仓位引擎 —— 调阈值改这里
├── fetch_macro.py    抓宏观/估值/资金 → SQLite + macro.json
├── quote.py          实时行情（服务端代理腾讯，UTF-8）
├── daily_job.py      每日任务：抓数→算→存→告警
├── alert.py          告警通道
├── web/index.html    前端页面
├── deploy/           systemd / nginx / cron / 备份 / 一键部署
├── requirements.txt
└── config.example.env
```

## 三、三种跑法

### ① 本机先试试（2 分钟）

```bash
pip3 install -r requirements.txt
python3 fetch_macro.py                       # 抓一次数据
NX_PASSWORD=123456 BIND=127.0.0.1 PORT=8000 python3 app.py
# 浏览器打开 http://127.0.0.1:8000，弹窗用户名随便填、密码 123456
```

### ② 服务器一键部署（推荐，Ubuntu 22.04）

```bash
sudo bash deploy/setup.sh            # 默认装到 /opt/niuxiong
```

脚本会自动：建专用账号 `niuxiong`（不用 root 跑）→ 建 venv 装依赖 → **生成随机密码**并写入 `config.env` → 装 systemd 服务与定时器 → 首轮抓数据 → 生成 nginx 配置。

装完看状态：

```bash
systemctl status niuxiong.service
systemctl list-timers niuxiong-fetch.timer
curl -u 任意用户名:你的密码 http://127.0.0.1:8000/api/health
```

有域名后上 HTTPS（**别让页面裸奔在 http 上**，你的持仓金额在上面）：

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d 你的域名      # 国内服务器需先完成 ICP 备案
```

### ③ 不用 systemd 也行（cron）

见 `deploy/crontab.example`。

## 四、安全清单（默认已开的）

| 项 | 做法 |
|---|---|
| 登录鉴权 | 全站 Basic Auth；**没设密码时自动生成随机密码并打印**，绝不裸奔 |
| 链接口令（兜底） | 某些发布网关/预览代理会**剥掉 `Authorization` 请求头**，导致 Basic Auth 永远 401。此时用 `https://域名/?token=你的口令` 访问即可（口令默认等于 `NX_PASSWORD`；也可用 `NX_TOKEN` 单设；正式服务器上设 `NX_ALLOW_TOKEN=0` 关掉这条通道） |
| 不直接暴露端口 | 服务默认只听 `127.0.0.1`，由 Nginx 反代对外（想直连才 `BIND=0.0.0.0`） |
| 防 SSRF | 行情代理只请求白名单域名 `qt.gtimg.cn` |
| 防刷 | `/api/*` 每分钟限次（默认 120，POST 30） |
| 服务降权 | systemd 里 `NoNewPrivileges / ProtectSystem=strict / PrivateTmp`，专用账号运行 |
| 响应头 | `nosniff / DENY 嵌套 / no-referrer / no-store` |
| 密钥 | 只从环境变量读，**不下发到前端** |
| 备份 | `deploy/backup.sh` 保留 30 份，建议每周跑 |

## 五、告警（自动化闭环的关键）

触发条件（可在 `config.env` 调）：

1. 抓取异常项 ≥ 2 → 「数据抓取异常」
2. 宏观数据陈旧 > 3 天 → 「定时任务可能没跑」
3. 建议仓位比上一交易日变动 ≥ 1 成 → 「仓位变动提醒」

通道三选一（都填就都发，都不填只写 `logs/alert.log`）：

- **Server酱**（最省事，微信推送）：[sct.ftqq.com](https://sct.ftqq.com/) 拿 SendKey → `SERVERCHAN_KEY=`
- **企业微信机器人**：群设置里加机器人 → `WECOM_WEBHOOK=`
- **邮件**：`SMTP_HOST/PORT/USER/PASS/ALERT_TO`（QQ 邮箱要用**授权码**不是登录密码）

测一下通不通：

```bash
python3 alert.py     # 收到「测试告警」即成功
```

## 六、日常运维

```bash
# 看服务日志
journalctl -u niuxiong.service -f
# 看每日任务
journalctl -u niuxiong-fetch.service -n 50
# 手动补跑一次（数据没更新时）
sudo -u niuxiong /opt/niuxiong/venv/bin/python /opt/niuxiong/daily_job.py
# 看历史仓位（校准用）
curl -u u:密码 http://127.0.0.1:8000/api/history
```

## 七、已知限制（必须知道）

- **上涨家数占比**依赖乐咕接口，抓不到就是缺项（不参与打分，不会假装中性）——不会因此算错，但情绪维会少一个输入。
- **北向资金**自 2024-08 起不再实时披露，取到 0 一律按"无数据"处理。
- 定性项（地缘 / 监管 / 信用 / 政策力度）机器判不了，仍要你手动滑块。
- 权重与阈值是经验值。**跑满 1 个月**后导 `/api/history` 回看：如果"提示减仓时市场还在涨"说明权重偏保守，再来 `engine.py` 顶部调常量。
- 前端 JS 里还有一份等价算法，用于**没后端时降级**；改 `engine.py` 的阈值时记得同步 `web/index.html`（有后端时页面直接用服务端结果，不受影响）。

## 八、今天的实测结果（2026-09-29）

```
[A股] 温度 3.04（偏冷） 基础 7.5成 → 约束 5.5成 → 建议 4.7成
      卡在：趋势约束 + 共振约束｜牛熊钟：熊末·黄金坑｜共振 25%
      32万可投资产 → 目标权益 14.9 万
```

趋势已跌破年线且处年内最低分位（趋势 0.0），但 ERP 5.32% 说明估值确实便宜（估值 1.2）；M1 仅 4.1%、信贷累计 -20.9%、美债 5.18%，八大信号只集齐 25% —— 所以硬约束把仓位按在 5 成以下。便宜可以分批捡，但不能重仓赌底。
