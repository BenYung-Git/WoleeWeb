@echo off
chcp 65001 >nul
:: 須「以系統管理員身分執行」
net session >nul 2>&1
if errorlevel 1 (
    echo [錯誤] 請在檔案上按右鍵 →「以系統管理員身分執行」
    pause
    exit /b 1
)

set PORT=8080
set RULE_NAME=WoleeWeb TCP %PORT%

echo 正在新增 Windows 防火牆規則：允許區域網路連入 TCP %PORT% ...

netsh advfirewall firewall delete rule name="%RULE_NAME%" >nul 2>&1
netsh advfirewall firewall add rule ^
    name="%RULE_NAME%" ^
    dir=in action=allow protocol=TCP localport=%PORT% ^
    profile=private,domain ^
    description="企業管理系統 Web 介面（區域網路）"

if errorlevel 1 (
    echo [錯誤] 無法新增防火牆規則。
    pause
    exit /b 1
)

echo.
echo 已允許 TCP %PORT% 連入（私人／網域網路）。
echo 請確認 Web 伺服器已啟動：
echo   python launcher.py --mode web --host 0.0.0.0 --port %PORT%
echo.
echo 其他電腦請用啟動畫面顯示的 192.168.x.x 位址（勿用 127.0.0.1）。
pause
