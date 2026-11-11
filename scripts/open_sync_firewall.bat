@echo off
chcp 65001 >nul
:: 須「以系統管理員身分執行」— 允許 Ubuntu 下載同步套件 (TCP 8765)
net session >nul 2>&1
if errorlevel 1 (
    echo [錯誤] 請右鍵「以系統管理員身分執行」
    pause
    exit /b 1
)
netsh advfirewall firewall delete rule name="WoleeWeb Sync TCP 8765" >nul 2>&1
netsh advfirewall firewall add rule name="WoleeWeb Sync TCP 8765" dir=in action=allow protocol=TCP localport=8765 profile=private,domain
echo 已開放 TCP 8765（同步下載用）
pause
