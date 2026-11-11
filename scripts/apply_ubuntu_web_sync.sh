#!/bin/bash
# 在 Ubuntu 上執行：從 Windows 開發機下載並套用 Web 同步套件
set -euo pipefail

WIN_HOST="${1:-192.168.1.62}"
WIN_PORT="${2:-8765}"
ZIP_URL="http://${WIN_HOST}:${WIN_PORT}/ubuntu_web_sync.zip"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT"
echo "下載: $ZIP_URL"
curl -fSL "$ZIP_URL" -o /tmp/ubuntu_web_sync.zip
echo "解壓至: $ROOT"
unzip -o /tmp/ubuntu_web_sync.zip -d "$ROOT"
rm -f /tmp/ubuntu_web_sync.zip

echo ""
echo "驗證:"
grep -c "findMenuWorkActions" web/static/app.js || true
grep "app.js" web/static/index.html
grep -c "need_attach" api/server.py || true
echo ""
echo "完成。請重啟 Web 伺服器，瀏覽器 Ctrl+Shift+R 後重新登入。"
