"""跨平台主控台關閉 — Windows 在 Qt app.exec() 阻塞時仍可響應 Ctrl+C。"""
from __future__ import annotations

import os
import signal
import sys
import threading
from typing import Callable, List

_LOCK = threading.Lock()
_CALLED = False
_KEEPALIVE: List[object] = []
_FORCE_EXIT_TIMER: threading.Timer | None = None


def _invoke_once(callback: Callable[[], None]) -> None:
    global _CALLED
    with _LOCK:
        if _CALLED:
            return
        _CALLED = True
    print("\n正在停止伺服器…", flush=True)
    try:
        callback()
    except Exception:
        pass


def cancel_force_exit() -> None:
    """正常關閉完成後取消逾時強制結束。"""
    global _FORCE_EXIT_TIMER
    if _FORCE_EXIT_TIMER is not None:
        _FORCE_EXIT_TIMER.cancel()
        _FORCE_EXIT_TIMER = None


def schedule_force_exit(seconds: float = 2.5) -> None:
    """若正常關閉卡住，逾時後強制結束行程。"""
    global _FORCE_EXIT_TIMER
    cancel_force_exit()

    def _force() -> None:
        print("強制結束程序。", flush=True)
        os._exit(0)

    _FORCE_EXIT_TIMER = threading.Timer(seconds, _force)
    _FORCE_EXIT_TIMER.daemon = True
    _FORCE_EXIT_TIMER.start()


def install_console_shutdown(
    callback: Callable[[], None],
    *,
    force_exit_after: float = 2.5,
) -> None:
    """
    註冊 Ctrl+C / Ctrl+Break / 關閉主控台視窗。
    Windows 必須用 SetConsoleCtrlHandler（Python signal 在 Qt 事件迴圈中常無效）。
    """

    def _wrapped() -> None:
        _invoke_once(callback)
        if force_exit_after > 0:
            schedule_force_exit(force_exit_after)

    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        HANDLER_ROUTINE = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

        CTRL_C_EVENT = 0
        CTRL_BREAK_EVENT = 1
        CTRL_CLOSE_EVENT = 2

        @HANDLER_ROUTINE
        def _win_handler(ctrl_type: int) -> bool:
            if ctrl_type in (CTRL_C_EVENT, CTRL_BREAK_EVENT, CTRL_CLOSE_EVENT):
                _wrapped()
                return True
            return False

        if kernel32.SetConsoleCtrlHandler(_win_handler, True):
            _KEEPALIVE.append(_win_handler)
        return

    def _sig_handler(signum, frame) -> None:  # noqa: ARG001
        _wrapped()
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)


def quit_qt_app_safe() -> None:
    """從任意執行緒安全結束 Qt 事件迴圈。"""
    try:
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return
        QTimer.singleShot(0, app.quit)
    except Exception:
        try:
            from PyQt6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                app.quit()
        except Exception:
            pass
