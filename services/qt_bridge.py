from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass
from typing import Callable, Optional, TypeVar

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication

T = TypeVar("T")

_BRIDGE: Optional["QtBridge"] = None
_BRIDGE_LOCK = threading.Lock()
_QT_THREAD: Optional[threading.Thread] = None
_QT_READY = threading.Event()
_QT_START_ERROR: Optional[BaseException] = None


@dataclass
class _SyncJob:
    fn: Callable[[], T]
    result: Optional[T] = None
    error: Optional[BaseException] = None


class QtBridge(QObject):
    """將 callable 派發至 QApplication 執行緒並同步等待結果。"""

    _dispatch = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._job_lock = threading.Lock()
        self._job: Optional[_SyncJob] = None
        self._dispatch.connect(
            self._run_pending,
            Qt.ConnectionType.BlockingQueuedConnection,
        )

    @pyqtSlot()
    def _run_pending(self) -> None:
        with self._job_lock:
            job = self._job
        if job is None:
            return
        try:
            job.result = job.fn()
        except BaseException as exc:  # noqa: BLE001
            job.error = exc

    def call_sync(self, fn: Callable[[], T]) -> T:
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("QApplication 尚未初始化，無法執行列印。")
        if QThread.currentThread() is app.thread():
            return fn()

        job: _SyncJob[T] = _SyncJob(fn=fn)
        with self._job_lock:
            self._job = job
        self._dispatch.emit()
        if job.error is not None:
            raise job.error
        return job.result  # type: ignore[return-value]


def _configure_headless_qt_env() -> None:
    """Linux 無 DISPLAY 時使用 offscreen，供 Web headless 列印預覽。"""
    if sys.platform == "win32":
        return
    if not (os.environ.get("DISPLAY") or "").strip():
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _qt_background_thread_main() -> None:
    global _BRIDGE, _QT_START_ERROR  # noqa: PLW0603
    try:
        _configure_headless_qt_env()
        app = QApplication(sys.argv if sys.argv else [""])
        app.setStyle("Fusion")
        with _BRIDGE_LOCK:
            if _BRIDGE is None:
                _BRIDGE = QtBridge(app)
        _QT_READY.set()
        app.exec()
    except BaseException as exc:  # noqa: BLE001
        _QT_START_ERROR = exc
        _QT_READY.set()


def _ensure_background_qt_thread() -> None:
    """Web headless：在背景執行緒啟動 QApplication（列印預覽用）。"""
    global _QT_THREAD, _QT_START_ERROR  # noqa: PLW0603
    if QApplication.instance() is not None:
        return
    with _BRIDGE_LOCK:
        if _QT_THREAD is not None and _QT_THREAD.is_alive():
            return
        _QT_READY.clear()
        _QT_START_ERROR = None
        _QT_THREAD = threading.Thread(
            target=_qt_background_thread_main,
            name="WoleeQt",
            daemon=True,
        )
        _QT_THREAD.start()
    if not _QT_READY.wait(timeout=60.0):
        raise RuntimeError(
            "Qt 背景執行緒啟動逾時。Ubuntu 請確認已安裝 PyQt6，"
            "或改用：xvfb-run -a python3 launcher.py --mode web"
        )
    if _QT_START_ERROR is not None:
        raise RuntimeError(
            f"Qt 背景執行緒啟動失敗：{_QT_START_ERROR}"
        ) from _QT_START_ERROR


def warm_up_qt_runtime() -> None:
    """可選：伺服器啟動時預先載入 Qt，避免首次列印較慢。"""
    if QApplication.instance() is None:
        _ensure_background_qt_thread()


def install_qt_bridge(app: Optional[QApplication] = None) -> QtBridge:
    global _BRIDGE
    application = app or QApplication.instance()
    if application is None:
        _ensure_background_qt_thread()
        with _BRIDGE_LOCK:
            if _BRIDGE is None:
                raise RuntimeError("QApplication 尚未初始化。")
            return _BRIDGE
    with _BRIDGE_LOCK:
        if _BRIDGE is None:
            _BRIDGE = QtBridge(application)
        return _BRIDGE


def qt_call(fn: Callable[[], T]) -> T:
    bridge = install_qt_bridge()
    return bridge.call_sync(fn)
