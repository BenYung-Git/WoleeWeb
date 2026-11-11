#!/bin/bash
# Ubuntu 完整重新安裝（不需從 Windows 逐檔同步）
# 用法：將「整個 WoleeWeb 資料夾」複製到 Ubuntu 後執行：
#   cd ~/WoleeWeb
#   chmod +x scripts/install_ubuntu.sh
#   ./scripts/install_ubuntu.sh
#
# 若出現 cannot execute: required file not found，為 Windows 換行造成，請執行：
#   sed -i 's/\r$//' scripts/install_ubuntu.sh
#   或：bash scripts/install_ubuntu.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PURGE_VENV=1
SKIP_VERIFY=0

usage() {
  echo "用法: $0 [--keep-venv] [--skip-verify]"
  echo "  --keep-venv     保留既有 .venv（僅升級 pip 與 requirements）"
  echo "  --skip-verify   略過安裝後檢查"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-venv) PURGE_VENV=0; shift ;;
    --skip-verify) SKIP_VERIFY=1; shift ;;
    -h|--help) usage ;;
    *) echo "未知參數: $1"; usage ;;
  esac
done

echo "=== WoleeWeb Ubuntu 重新安裝 ==="
echo "目錄: $ROOT"
echo ""

if ! command -v python3 >/dev/null 2>&1; then
  echo "[錯誤] 找不到 python3。請先執行："
  echo "  sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
  exit 1
fi

echo "Python: $(python3 --version)"

if ! python3 -m venv --help >/dev/null 2>&1; then
  echo "[提示] 需要 python3-venv：sudo apt install -y python3-venv"
  exit 1
fi

if [[ "$PURGE_VENV" -eq 1 && -d "$ROOT/.venv" ]]; then
  echo "移除舊虛擬環境 .venv ..."
  rm -rf "$ROOT/.venv"
fi

if [[ ! -d "$ROOT/.venv" ]]; then
  echo "建立虛擬環境 .venv ..."
  python3 -m venv "$ROOT/.venv"
fi

# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"

echo "升級 pip ..."
python3 -m pip install --upgrade pip wheel

echo "安裝相依套件 (requirements.txt) ..."
python3 -m pip install -r "$ROOT/requirements.txt"

echo ""
echo "=== 檢查必要檔案 ==="
missing=0
for f in \
  launcher.py \
  requirements.txt \
  api/server.py \
  web/static/app.js \
  web/static/index.html \
  services/app_service.py \
  core/data_dictionary.py
do
  if [[ ! -f "$ROOT/$f" ]]; then
    echo "  [缺少] $f"
    missing=1
  fi
done

if [[ ! -f "$ROOT/sys_data.sqlite" && ! -f "$ROOT/sys_data.mdb" && ! -f "$ROOT/SYS_DATA.mdb" ]]; then
  echo "  [警告] 找不到 sys_data.sqlite / sys_data.mdb（請一併複製資料庫檔）"
fi
if [[ ! -f "$ROOT/user_data.sqlite" && ! -f "$ROOT/user_data.mdb" ]]; then
  echo "  [警告] 找不到 user_data.sqlite / user_data.mdb"
fi

if [[ "$missing" -eq 1 ]]; then
  echo ""
  echo "[錯誤] 專案檔案不完整。請將 Windows 上「整個 WoleeWeb 資料夾」複製到本機後再執行本腳本。"
  exit 1
fi

if [[ "$SKIP_VERIFY" -eq 0 ]]; then
  echo ""
  echo "=== 程式版本檢查 ==="
  if grep -q "findMenuWorkActions" "$ROOT/web/static/app.js" 2>/dev/null; then
    echo "  web/static/app.js: 含附件／其他按鈕邏輯 OK"
  else
    echo "  [警告] web/static/app.js 可能為舊版（無 findMenuWorkActions）"
  fi
  grep "app.js" "$ROOT/web/static/index.html" || true
  if grep -q "need_attach" "$ROOT/api/server.py" 2>/dev/null; then
    echo "  api/server.py: 選單 need_attach OK"
  else
    echo "  [警告] api/server.py 可能為舊版"
  fi

  echo ""
  echo "=== 資料庫旗標檢查 ==="
  python3 -c "
import sys
sys.path.insert(0, '$ROOT')
from core.auth import resolve_sys_data_path
from core.menu_loader import ProgramRepository
mdb = resolve_sys_data_path('$ROOT')
print('sys_data:', mdb)
repo = ProgramRepository(mdb)
repo.load()
na = sum(1 for p in repo._all_items if p.need_attach)
no = sum(1 for p in repo._all_items if p.need_other)
print('need_attach=', na, 'need_other=', no)
" || echo "  [警告] 無法讀取 sys_data"
fi

echo ""
echo "=== 安裝完成 ==="
echo ""
echo "啟動 Web（Ubuntu Server 建議 headless）："
echo "  cd $ROOT"
echo "  source .venv/bin/activate"
echo "  python3 launcher.py --mode web --headless --host 0.0.0.0 --port 8080"
echo ""
echo "瀏覽器開啟: http://<本機IP>:8080"
echo "首次或更新後請 Ctrl+Shift+R 強制重新整理。"
