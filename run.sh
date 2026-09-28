#!/usr/bin/env bash
# 本地/服务器手动启动（生产请用 systemd：deploy/setup.sh）
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
[ -f config.env ] && set -a && . ./config.env && set +a
export BIND="${BIND:-127.0.0.1}" PORT="${PORT:-8000}"
echo "启动 http://$BIND:$PORT  （生产请配 Nginx + HTTPS，见 deploy/nginx.conf）"
exec python3 app.py
