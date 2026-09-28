#!/usr/bin/env bash
# 一键部署（Ubuntu 22.04 / Debian，需 root）
# 用法： sudo bash deploy/setup.sh [安装目录]  默认 /opt/niuxiong
set -euo pipefail

DST="${1:-/opt/niuxiong}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_NX="niuxiong"

echo "== 牛熊自查后端 · 一键部署 =="
echo "源目录：$SRC  安装到：$DST"

if [ "$(id -u)" -ne 0 ]; then echo "请用 sudo 运行"; exit 1; fi

# 1. 系统依赖
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip nginx >/dev/null

# 2. 建专用账号（不能用 root 跑服务）
id -u "$USER_NX" >/dev/null 2>&1 || useradd -r -m -s /usr/sbin/nologin "$USER_NX"

# 3. 拷贝代码
mkdir -p "$DST"
cp -r "$SRC"/. "$DST"/
chown -R "$USER_NX":"$USER_NX" "$DST"

# 4. 虚拟环境 + 依赖
sudo -u "$USER_NX" python3 -m venv "$DST/venv"
sudo -u "$USER_NX" "$DST/venv/bin/pip" install -q --upgrade pip
sudo -u "$USER_NX" "$DST/venv/bin/pip" install -q -r "$DST/requirements.txt"

# 5. 密码（不设置就拒绝裸奔）
ENVFILE="$DST/config.env"
if [ ! -f "$ENVFILE" ]; then
  PASS="$(openssl rand -base64 12)"
  cat > "$ENVFILE" <<EOF
# 登录密码（浏览器弹窗时输入，用户名随意）
NX_PASSWORD=$PASS
# 保守系数（0.85=风险厌恶；想更激进改 1.0）
NX_CONSERVATIVE=0.85
# 行情/宏观告警阈值
POS_DELTA_ALERT=1.0
STALE_DAYS=3
FETCH_FAIL_ALERT=2
# 告警通道（三选一或都填；都不填则只写日志）
# Server酱：https://sct.ftqq.com/ 申请 SendKey
# SERVERCHAN_KEY=你的key
# 企业微信机器人 webhook
# WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx
# 邮件（QQ邮箱用授权码，不是登录密码）
# SMTP_HOST=smtp.qq.com
# SMTP_PORT=465
# SMTP_USER=xxx@qq.com
# SMTP_PASS=授权码
# ALERT_TO=收件人@xx.com
EOF
  chmod 600 "$ENVFILE"
  echo "已生成配置：$ENVFILE"
  echo ">>> 登录密码：$PASS  <<< 请保存（也可自行修改该文件）"
fi

# 6. systemd 服务 + 定时器
sed "s#__DIR__#$DST#g; s#__USER__#$USER_NX#g" "$SRC/deploy/niuxiong.service" > /etc/systemd/system/niuxiong.service
sed "s#__DIR__#$DST#g; s#__USER__#$USER_NX#g" "$SRC/deploy/niuxiong-fetch.service" > /etc/systemd/system/niuxiong-fetch.service
sed "s#__DIR__#$DST#g; s#__USER__#$USER_NX#g" "$SRC/deploy/niuxiong-fetch.timer" > /etc/systemd/system/niuxiong-fetch.timer

systemctl daemon-reload
systemctl enable --now niuxiong.service
systemctl enable --now niuxiong-fetch.timer

# 7. 首次抓数据（不抓的话页面是空的）
sudo -u "$USER_NX" env $(grep -v '^#' "$ENVFILE" | grep -v '^$' | xargs) "$DST/venv/bin/python" "$DST/fetch_macro.py" || true

# 8. nginx
if [ ! -f /etc/nginx/sites-available/niuxiong ]; then
  sed "s#__DIR__#$DST#g" "$SRC/deploy/nginx.conf" > /etc/nginx/sites-available/niuxiong
  ln -sf /etc/nginx/sites-available/niuxiong /etc/nginx/sites-enabled/niuxiong
  nginx -t && systemctl reload nginx
fi

echo
echo "== 完成 =="
systemctl --no-pager status niuxiong.service | head -3 || true
echo "本地自检： curl -u 任意用户名:你的密码 http://127.0.0.1:8000/api/health"
echo "下一步（有域名时）： apt install certbot python3-certbot-nginx && certbot --nginx -d 你的域名"
echo "定时任务： systemctl list-timers niuxiong-fetch.timer"
