#!/usr/bin/env bash
# 备份数据库与配置，保留 30 份
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BK="$DIR/backups"; mkdir -p "$BK"
TS="$(date +%Y%m%d_%H%M%S)"
cp "$DIR/niuxiong.db" "$BK/niuxiong_$TS.db" 2>/dev/null || true
cp "$DIR/config.env"  "$BK/config_$TS.env"  2>/dev/null || true
ls -1t "$BK"/niuxiong_*.db 2>/dev/null | tail -n +31 | xargs -r rm -f
echo "[$(date)] backup done -> $BK/niuxiong_$TS.db"
