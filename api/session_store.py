from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from services.app_service import AppRuntime


@dataclass
class WebSession:
    token: str
    runtime: AppRuntime
    created_at: float
    last_access: float


class SessionStore:
    """記憶體 token session 儲存（桌面/Web 共用同一程序時有效）。"""

    def __init__(self, ttl_seconds: int = 86400) -> None:
        self._sessions: Dict[str, WebSession] = {}
        self._lock = threading.Lock()
        self.ttl_seconds = ttl_seconds

    def create(self, runtime: AppRuntime) -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        with self._lock:
            self._sessions[token] = WebSession(
                token=token,
                runtime=runtime,
                created_at=now,
                last_access=now,
            )
        return token

    def get(self, token: str) -> Optional[AppRuntime]:
        if not token:
            return None
        now = time.time()
        with self._lock:
            sess = self._sessions.get(token)
            if sess is None:
                return None
            if now - sess.last_access > self.ttl_seconds:
                self._remove_unlocked(token)
                return None
            sess.last_access = now
            return sess.runtime

    def remove(self, token: str) -> None:
        with self._lock:
            self._remove_unlocked(token)

    def _remove_unlocked(self, token: str) -> None:
        sess = self._sessions.pop(token, None)
        if sess is not None:
            sess.runtime.close()

    def cleanup_expired(self) -> None:
        now = time.time()
        with self._lock:
            expired = [
                t
                for t, s in self._sessions.items()
                if now - s.last_access > self.ttl_seconds
            ]
            for token in expired:
                self._remove_unlocked(token)


# 全域 session store（同一程序內 API 與桌面共用）
session_store = SessionStore()
