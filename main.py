#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企業管理系統 — 啟動入口：Fusion 介面、登入後載入主視窗。
"""
from __future__ import annotations

import os
import sys

# 專案根目錄加入 path（可直接 python main.py 執行）
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from PyQt6.QtWidgets import QApplication, QDialog

from services.qt_bridge import install_qt_bridge
from ui.login_dialog import LoginDialog
from ui.main_window import MainWindow


def run_with_app(app: QApplication) -> int:
    login = LoginDialog(_ROOT)
    if login.exec() != QDialog.DialogCode.Accepted:
        return 0
    session = login.session()
    if session is None:
        return 0

    win = MainWindow(_ROOT, session)
    win.show()
    return app.exec()


def main(existing_app: QApplication | None = None) -> int:
    app = existing_app or QApplication(sys.argv)
    app.setStyle("Fusion")
    install_qt_bridge(app)
    return run_with_app(app)


if __name__ == "__main__":
    # 帶參數時委派給 launcher（--mode desktop|web|both）
    if len(sys.argv) > 1 and sys.argv[1].startswith("-"):
        from launcher import main as launcher_main

        raise SystemExit(launcher_main())
    raise SystemExit(main())
