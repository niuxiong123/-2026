#!/usr/bin/env bash
# 一键发布到 GitHub（需先：gh auth login）
# 作用：建公开仓库 → 推送代码 → 开启 GitHub Pages(/docs) → 打印永久网址
set -euo pipefail
REPO="${1:-niuxiong}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

gh auth status >/dev/null 2>&1 || { echo "请先运行: gh auth login"; exit 1; }
USER="$(gh api user --jq .login)"
echo "当前 GitHub 账号: $USER"

# 建仓库（已存在则忽略）
gh repo create "$REPO" --public --description "牛熊每日自查 · 自动数据版" 2>/dev/null || echo "仓库已存在，继续…"

git init -q 2>/dev/null || true
git add -A
git -c user.email="bot@users.noreply.github.com" -c user.name="niuxiong" commit -qm "init: 牛熊每日自查 v2" 2>/dev/null || echo "无新提交"
git branch -M main
git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/$USER/$REPO.git"
git push -u origin main --force

# 开启 Pages（用 /docs 目录）
gh api "repos/$USER/$REPO/pages" -f source='{"branch":"main","path":"/docs"}' -X POST >/dev/null 2>&1 \
  || echo "Pages 可能已开启，或去 Settings→Pages 手动选 main /docs"

echo "----------------------------------------------------------------"
echo "完成！等 1-2 分钟，打开你的永久网址："
echo "  https://$USER.github.io/$REPO/"
echo "Actions 标签里能看到每天 18:30 自动抓数据的任务。"
echo "----------------------------------------------------------------"
