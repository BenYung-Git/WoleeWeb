@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   企業管理系統 - Web 介面（區域網路）
echo ========================================
echo.
echo 此腳本須在存有 .mdb 資料庫的 Windows 電腦執行。
echo 其他電腦只需用瀏覽器連線，無需安裝 Python。
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [錯誤] 找不到 Python，請先安裝 Python 3 並加入 PATH。
    pause
    exit /b 1
)

echo 正在檢查依賴...
python -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo [錯誤] 安裝依賴失敗。
    pause
    exit /b 1
)

echo.
echo 停止伺服器：在此視窗按 Ctrl+C 或 Ctrl+Break
echo.
echo 若其他電腦無法連線，請以系統管理員執行：scripts\open_web_firewall.bat
echo.
python launcher.py --mode web --host 0.0.0.0 --port 8080
pause
