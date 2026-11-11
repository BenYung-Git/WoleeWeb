from __future__ import annotations

import os
import threading
from typing import Dict, Optional

from core.db_backend import AccessBackend

_pool_lock = threading.Lock()
_backend_pool: Dict[str, AccessBackend] = {}


def get_access_backend(db_path: str) -> AccessBackend:
    """
    程序內共用 AccessBackend（每個 .mdb 路徑一個 ODBC 連線）。
    避免 Web 多用戶／多請求反覆 connect 觸發「太多用戶端工作」。
    """
    key = os.path.abspath(db_path)
    with _pool_lock:
        backend = _backend_pool.get(key)
        if backend is None:
            backend = AccessBackend(key)
            _backend_pool[key] = backend
        return backend
