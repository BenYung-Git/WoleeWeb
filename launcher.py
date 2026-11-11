#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企業管理系統統一啟動器 — 支援桌面 / Web / 雙模式切換。

用法：
  python launcher.py                    # Windows 桌面介面（預設）
  python launcher.py --mode web         # 僅 Web 介面
  python launcher.py --mode web --headless   # Ubuntu：Ctrl+C 可正常停止
  python launcher.py --mode both        # 同時啟動桌面 + Web
  python launcher.py --mode web --port 9000
"""
from __future__ import annotations

import argparse
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from api.console_shutdown import (
    cancel_force_exit,
    install_console_shutdown,
    quit_qt_app_safe,
)
from api.network import print_web_startup_banner, web_access_urls


def _shutdown_web_server(mgr) -> None:
    mgr.request_shutdown()
    mgr.stop(timeout=3.0)


def _shutdown_web_with_qt(mgr) -> None:
    _shutdown_web_server(mgr)
    quit_qt_app_safe()


def run_web_headless(host: str, port: int) -> int:
    """
    Linux / Ubuntu 建議：主執行緒執行 uvicorn，Ctrl+C 可正常結束。
    列印預覽等需 Qt 的功能請改用一般 web 模式（xvfb-run）。
    """
    from api.server import WebServerManager

    mgr = WebServerManager.instance()
    mgr.configure(host=host, port=port, base_dir=_ROOT)
    os.environ["WOLEE_WEB_MODE"] = "web"
    os.environ["WOLEE_WEB_HOST"] = host
    os.environ["WOLEE_WEB_PORT"] = str(port)
    install_console_shutdown(lambda: _shutdown_web_server(mgr), force_exit_after=3.0)
    print("Web 模式（headless）：按 Ctrl+C 停止伺服器。")
    print("列印預覽將自動啟動背景 Qt（offscreen）；若失敗可改用：")
    print("  xvfb-run -a python3 launcher.py --mode web")
    try:
        from services.qt_bridge import warm_up_qt_runtime

        warm_up_qt_runtime()
        print("背景 Qt 已就緒（列印預覽）。")
    except Exception as exc:
        print(f"背景 Qt 預載略過（首次列印時再試）：{exc}")
        if "PyQt6" in str(exc):
            print("列印／匯出需安裝 PyQt6：")
            print("  source .venv/bin/activate")
            print("  pip install -r requirements.txt")
            print("  # 或僅：pip install PyQt6")
            print("安裝後請重新啟動；有 xvfb 時可用：")
            print("  xvfb-run -a python3 launcher.py --mode web --headless")
    try:
        mgr.start(blocking=True)
    except KeyboardInterrupt:
        print("\n已停止。", flush=True)
    finally:
        mgr.stop()
        cancel_force_exit()
        print("已停止。", flush=True)
    return 0


def run_web(host: str, port: int) -> int:
    from PyQt6.QtWidgets import QApplication

    from api.server import WebServerManager
    from services.qt_bridge import install_qt_bridge

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    install_qt_bridge(app)

    mgr = WebServerManager.instance()
    mgr.configure(
        host=host,
        port=port,
        base_dir=_ROOT,
        shutdown_hook=quit_qt_app_safe,
    )
    os.environ["WOLEE_WEB_MODE"] = "web"
    os.environ["WOLEE_WEB_HOST"] = host
    os.environ["WOLEE_WEB_PORT"] = str(port)
    install_console_shutdown(lambda: _shutdown_web_with_qt(mgr), force_exit_after=3.0)
    mgr.start(blocking=False)

    print("Web 伺服器必須在存有 .mdb 資料庫的 Windows 電腦上執行。")
    print("其他電腦只需用瀏覽器連線，無需安裝 Python。")
    print("按 Ctrl+C 或 Ctrl+Break 停止伺服器。")
    try:
        return app.exec()
    except KeyboardInterrupt:
        return 0
    finally:
        _shutdown_web_with_qt(mgr)
        cancel_force_exit()
        print("已停止。", flush=True)


def run_desktop() -> int:
    from main import main as desktop_main

    return desktop_main()


def run_both(host: str, port: int) -> int:
    from PyQt6.QtWidgets import QApplication

    from api.server import WebServerManager
    from main import run_with_app
    from services.qt_bridge import install_qt_bridge

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    install_qt_bridge(app)

    mgr = WebServerManager.instance()
    mgr.configure(
        host=host,
        port=port,
        base_dir=_ROOT,
        shutdown_hook=quit_qt_app_safe,
    )
    install_console_shutdown(lambda: _shutdown_web_with_qt(mgr), force_exit_after=3.0)
    mgr.start(blocking=False)
    urls = web_access_urls(host, port)
    os.environ["WOLEE_WEB_URL"] = urls[0]
    os.environ["WOLEE_WEB_HOST"] = host
    os.environ["WOLEE_WEB_PORT"] = str(port)
    os.environ["WOLEE_WEB_MODE"] = "both"
    print("Web 伺服器必須在存有 .mdb 的 Windows 電腦上執行；其他電腦用瀏覽器連線即可。")
    print_web_startup_banner(host, port)
    print("桌面介面即將開啟；可從選單「介面」切換至 Web。")
    try:
        return run_with_app(app)
    except KeyboardInterrupt:
        return 0
    finally:
        _shutdown_web_with_qt(mgr)
        cancel_force_exit()
        print("已停止。", flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="企業管理系統 — 桌面 / Web 介面啟動器",
    )
    parser.add_argument(
        "--mode",
        choices=["desktop", "web", "both"],
        default="desktop",
        help="desktop=Windows 桌面, web=瀏覽器, both=同時啟動（預設 desktop）",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Web 伺服器綁定位址（預設 0.0.0.0=允許區域網路其他電腦連線；僅本機請用 127.0.0.1）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Web 伺服器埠（預設 8080）",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Web 模式：主執行緒跑 uvicorn；列印預覽用背景 Qt（Ubuntu 建議，Ctrl+C 可正常停止）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "web":
        if args.headless:
            return run_web_headless(args.host, args.port)
        return run_web(args.host, args.port)
    if args.mode == "both":
        return run_both(args.host, args.port)
    return run_desktop()


if __name__ == "__main__":
    raise SystemExit(main())
