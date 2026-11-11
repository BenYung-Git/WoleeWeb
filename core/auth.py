from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple

from core.db_backend import DbBackendBase
from core.db_factory import get_backend_for_path


@dataclass
class UserSession:
    """登入成功後的使用者脈絡。"""

    user_no: str
    group_no: str
    group_level: Optional[int]
    company_key: str
    user_data_path: str
    login_date: str = ""  # 登入畫面日期（YYYY/MM/DD）
    company_currency: str = ""  # sys_co 對應貨幣（如 HKD）


_USER_DATA_CANDIDATES = (
    "user_data.sqlite",
    "USER_DATA.sqlite",
    "User_Data.sqlite",
    "user_data.mdb",
    "USER_DATA.mdb",
    "User_Data.mdb",
)


def _is_path_writable(path: str) -> bool:
    """SQLite 更新需檔案與所在目錄皆可寫（journal / WAL）。"""
    path = os.path.abspath(path)
    if os.path.isfile(path):
        if not os.access(path, os.W_OK):
            return False
        parent = os.path.dirname(path) or "."
        return os.access(parent, os.W_OK)
    parent = os.path.dirname(path) or "."
    return os.path.isdir(parent) and os.access(parent, os.W_OK)


def _local_user_data_mirror_path(source_path: str) -> str:
    source_path = os.path.abspath(source_path)
    project_name = os.path.basename(os.path.dirname(source_path)) or "wolee"
    local_dir = os.path.join(os.path.expanduser("~"), ".wolee-local", project_name)
    os.makedirs(local_dir, exist_ok=True)
    return os.path.join(local_dir, os.path.basename(source_path))


def _ensure_local_writable_user_data(source_path: str) -> str:
    """
    Samba 等唯讀來源：複製到 ~/.wolee-local/<專案>/ 供登入寫入 LAST_CO。
    本機副本已存在時沿用（保留上次登入寫入）；不存在時自來源複製一份。
    """
    source_path = os.path.abspath(source_path)
    local_path = _local_user_data_mirror_path(source_path)
    if not os.path.isfile(local_path):
        shutil.copy2(source_path, local_path)
    return local_path


def _finalize_user_data_path(path: str) -> str:
    path = os.path.abspath(path)
    if _is_path_writable(path):
        return path
    ext = os.path.splitext(path)[1].lower()
    if ext in (".sqlite", ".db", ".db3"):
        return _ensure_local_writable_user_data(path)
    return path


def resolve_user_data_path(base_dir: str) -> str:
    """
    同目錄下優先 user_data.sqlite，其次 user_data.mdb 系列。
    環境變數 WOLEE_USER_DATA_PATH 可指定完整路徑（建議 Samba 部署用本機可寫檔）。
    若專案目錄內資料庫唯讀（常見於 Samba），自動改用 ~/.wolee-local/ 可寫副本。
    """
    override = (os.environ.get("WOLEE_USER_DATA_PATH") or "").strip()
    if override:
        return _finalize_user_data_path(os.path.expanduser(override))
    base = os.path.abspath(base_dir)
    for name in _USER_DATA_CANDIDATES:
        p = os.path.join(base, name)
        if os.path.isfile(p):
            return _finalize_user_data_path(p)
    return _finalize_user_data_path(os.path.join(base, "user_data.sqlite"))


_SYS_DATA_SQLITE_NAMES = (
    "sys_data.sqlite",
    "SYS_DATA.sqlite",
    "Sys_Data.sqlite",
)
_SYS_DATA_MDB_NAMES = (
    "sys_data.mdb",
    "SYS_DATA.mdb",
    "Sys_Data.mdb",
)


def enumerate_sys_data_paths(base_dir: str) -> List[str]:
    """
    依平台列出 sys_data 候選路徑（去重、依優先順序）。
    非 Windows：優先 .sqlite（Linux Web 無 Access ODBC，不可讀 .mdb）。
    Windows：優先 .mdb，其次 .sqlite。
    """
    base = os.path.abspath(base_dir)
    order = (
        list(_SYS_DATA_SQLITE_NAMES) + list(_SYS_DATA_MDB_NAMES)
        if sys.platform != "win32"
        else list(_SYS_DATA_MDB_NAMES) + list(_SYS_DATA_SQLITE_NAMES)
    )
    out: List[str] = []
    seen: set[str] = set()
    for name in order:
        full = os.path.join(base, name)
        key = os.path.normcase(full)
        if key in seen or not os.path.isfile(full):
            continue
        seen.add(key)
        out.append(full)
    return out


def resolve_sys_data_path(base_dir: str) -> str:
    """
    同目錄下解析 sys_data 路徑。
    Linux／macOS：優先可讀的 .sqlite（與 user_data 一致，避免選到無法讀取的 .mdb）。
    Windows：若同時存在 .mdb 與 .sqlite，取修改時間較新者。
    """
    base = os.path.abspath(base_dir)
    candidates = enumerate_sys_data_paths(base)
    if not candidates:
        return os.path.join(base, "sys_data.sqlite")
    if len(candidates) == 1:
        return candidates[0]
    if sys.platform != "win32":
        return candidates[0]
    return max(candidates, key=lambda p: os.path.getmtime(p))


def _read_first_row(
    backend: DbBackendBase,
    sql: str,
    params: Optional[Sequence[Any]] = None,
) -> Optional[List[str]]:
    _cols, rows = backend.fetch_rows_sql(sql, params=params, limit=1)
    if not rows:
        return None
    return rows[0]


def _backend_error(backend: DbBackendBase) -> str:
    return (getattr(backend, "last_error", "") or "").strip()


def _norm_key(value: object) -> str:
    return str(value or "").strip().upper()


def parse_level_value(val: object) -> Optional[int]:
    """
    將 GROUP_LEVEL / PROGRAM.LEVEL 轉成整數。
    SQLite 遷移後常見 '4.0'、'True' 等字串，不可直接用 int()。
    """
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _list_user_records(backend: DbBackendBase) -> List[List[str]]:
    cols, rows = backend.fetch_rows_sql(
        "SELECT USER_NO, PASSWORD, GROUP_NO, LAST_CO, LOGIN_TIMES FROM USERS",
        limit=20000,
    )
    if rows:
        return rows
    cols, rows = backend.fetch_rows_sql(
        "SELECT USER_NO, PASSWORD, GROUP_NO, LAST_CO FROM USERS",
        limit=20000,
    )
    return rows or []


def _find_user_record(backend: DbBackendBase, user_no: str) -> Optional[List[str]]:
    """
    先走 USER_NO 精準查詢；若查不到，退回 Python 端做 trim + 不分大小寫比對。
    回傳格式：[USER_NO, PASSWORD, GROUP_NO, LAST_CO, LOGIN_TIMES?]
    """
    row = _read_first_row(
        backend,
        "SELECT USER_NO, PASSWORD, GROUP_NO, LAST_CO, LOGIN_TIMES FROM USERS WHERE USER_NO = ?",
        [user_no],
    )
    if row is None:
        row = _read_first_row(
            backend,
            "SELECT USER_NO, PASSWORD, GROUP_NO, LAST_CO FROM USERS WHERE USER_NO = ?",
            [user_no],
        )
    if row is not None:
        return row
    want = _norm_key(user_no)
    for r in _list_user_records(backend):
        if r and _norm_key(r[0] if len(r) > 0 else "") == want:
            return r
    return None


def _fetch_group_level(backend: DbBackendBase, group_no: str) -> Optional[int]:
    if not group_no:
        return None
    row = _read_first_row(
        backend,
        "SELECT GROUP_LEVEL FROM SYS_GROUP WHERE GROUP_NO = ?",
        [group_no],
    )
    if row is None:
        row = _read_first_row(
            backend,
            "SELECT GROUP_LEVEL FROM sys_group WHERE GROUP_NO = ?",
            [group_no],
        )
    if not row or row[0] is None:
        return None
    return parse_level_value(row[0])


def load_company_keys(user_data_path: str) -> Tuple[List[str], Optional[str]]:
    """
    讀取 sys_co.CO_KEY。若失敗回傳空清單與錯誤訊息。
    """
    if not os.path.isfile(user_data_path):
        return [], f"找不到使用者資料庫：{user_data_path}"
    backend = get_backend_for_path(user_data_path)
    _cols, rows = backend.fetch_rows_sql("SELECT CO_KEY FROM sys_co", limit=1000)
    if not rows:
        _cols, rows = backend.fetch_rows_sql("SELECT CO_KEY FROM SYS_CO", limit=1000)
    if not rows:
        msg = _backend_error(backend)
        if msg:
            return [], f"無法連線或讀取 sys_co：{msg}"
        return [], None
    keys: List[str] = []
    for row in rows:
        if row and row[0] is not None:
            k = str(row[0]).strip()
            if k:
                keys.append(k)
    return keys, None


_SYS_CO_CURRENCY_FIELDS = (
    "CURRENCY",
    "CO_CURR",
    "TX_CURR",
    "CURR",
    "BASE_CURR",
    "HOME_CURR",
)
_DEFAULT_COMPANY_CURRENCY = "HKD"


def load_company_currency(user_data_path: str, company_key: str) -> str:
    """
    自 user_data.sys_co 讀取登入公司對應貨幣。
    依常見欄名嘗試；找不到則回傳 HKD。
    """
    path = (user_data_path or "").strip()
    ck = (company_key or "").strip()
    if not path or not os.path.isfile(path) or not ck:
        return _DEFAULT_COMPANY_CURRENCY
    backend = get_backend_for_path(path)
    want = ck.upper()
    for tbl in ("sys_co", "SYS_CO"):
        cols, rows = backend.fetch_rows_sql(f"SELECT * FROM {tbl}", limit=500)
        if not rows or not cols:
            continue
        col_u = [str(c or "").strip().upper() for c in cols]
        try:
            ki = next(i for i, n in enumerate(col_u) if n == "CO_KEY")
        except StopIteration:
            continue
        hit = None
        for row in rows:
            if not row or ki >= len(row):
                continue
            if str(row[ki] or "").strip().upper() == want:
                hit = row
                break
        if hit is None:
            continue
        for name in _SYS_CO_CURRENCY_FIELDS:
            try:
                ci = next(i for i, n in enumerate(col_u) if n == name)
            except StopIteration:
                continue
            if ci < len(hit) and hit[ci] is not None:
                val = str(hit[ci]).strip()
                if val:
                    return val
    return _DEFAULT_COMPANY_CURRENCY


def load_available_company_keys(
    base_dir: str, user_data_path: str
) -> Tuple[List[str], Optional[str], List[str]]:
    """
    讀取 sys_co.CO_KEY，僅保留同目錄有對應資料庫檔的公司。
    回傳 (可用清單, sys_co 讀取錯誤, 缺少檔案的公司鍵)。
    若 sys_co 皆無檔案，改掃描目錄內 *.sqlite / *.mdb。
    """
    from core.db_factory import (
        discover_company_db_keys,
        filter_companies_with_db,
    )

    keys, err = load_company_keys(user_data_path)
    available, missing = filter_companies_with_db(base_dir, keys)
    if not available:
        discovered = discover_company_db_keys(base_dir)
        if discovered:
            available = discovered
    return available, err, missing


def fetch_group_level(user_data_path: str, group_no: str) -> Optional[int]:
    if not group_no or not os.path.isfile(user_data_path):
        return None
    return _fetch_group_level(get_backend_for_path(user_data_path), group_no)


def authenticate(
    user_data_path: str,
    user_no: str,
    password: str,
    company_key: str,
) -> Tuple[Optional[UserSession], Optional[str]]:
    """
    驗證 USERS：USER_NO + PASSWORD，回傳 UserSession。
    company_key 為登入畫面選取之公司（對應 sys_co.CO_KEY）。
    """
    user_no = (user_no or "").strip()
    password = (password or "").strip()
    company_key = (company_key or "").strip()
    if not user_no:
        return None, "請輸入使用者編號。"
    if not os.path.isfile(user_data_path):
        return None, f"找不到使用者資料庫：{user_data_path}"
    backend = get_backend_for_path(user_data_path)
    row = _find_user_record(backend, user_no)
    if row is None:
        msg = _backend_error(backend)
        if msg:
            return None, f"登入驗證失敗：{msg}"
        return None, "使用者編號或密碼錯誤。"
    matched_user_no = str(row[0]).strip() if len(row) > 0 and row[0] is not None else user_no
    db_pw = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
    if db_pw != password:
        return None, "使用者編號或密碼錯誤。"
    group_no = str(row[2]).strip() if len(row) > 2 and row[2] is not None else ""
    gl = _fetch_group_level(backend, group_no)
    co = company_key or (str(row[3]).strip() if len(row) > 3 and row[3] else "")
    return (
        UserSession(
            user_no=matched_user_no or user_no,
            group_no=group_no,
            group_level=gl,
            company_key=co,
            user_data_path=user_data_path,
            company_currency=load_company_currency(user_data_path, co),
        ),
        None,
    )


def record_login_success(
    user_data_path: str,
    user_no: str,
    company_key: str,
) -> Optional[str]:
    """
    登入成功後更新 USERS：
    - LAST_CO = 本次登入公司
    - LOGIN_TIMES = LOGIN_TIMES + 1（NULL 視為 0）
    回傳 None 代表成功；失敗回傳錯誤字串。
    """
    user_no = (user_no or "").strip()
    company_key = (company_key or "").strip()
    if not user_no:
        return "缺少使用者編號。"
    if not os.path.isfile(user_data_path):
        return f"找不到使用者資料庫：{user_data_path}"
    backend = get_backend_for_path(user_data_path)
    row = _find_user_record(backend, user_no)
    current_times = 0
    matched_user_no = user_no
    if row and len(row) > 0 and row[0] is not None:
        matched_user_no = str(row[0]).strip() or user_no
    login_times_idx = 4
    if row and len(row) > login_times_idx and row[login_times_idx] not in (None, ""):
        try:
            current_times = int(row[login_times_idx])
        except (TypeError, ValueError):
            current_times = 0
    ok = backend.update_one(
        "USERS",
        ["LAST_CO", "LOGIN_TIMES"],
        [company_key, str(current_times + 1)],
        ["USER_NO"],
        [matched_user_no],
    )
    if ok:
        return None
    msg = _backend_error(backend) or "Unknown error"
    return f"更新登入資訊失敗：{msg}"


def detect_last_company_by_credentials(
    user_data_path: str,
    user_no: str,
    password: str,
) -> Tuple[Optional[str], Optional[str]]:
    """
    依 USER_NO/PASSWORD 取得該帳號 LAST_CO。
    成功回傳 (last_co, None)；查無/密碼錯誤/無 last_co 則回傳 (None, None)。
    只有連線或 SQL 例外才回傳錯誤訊息。
    """
    user_no = (user_no or "").strip()
    password = (password or "").strip()
    if not user_no or not password:
        return None, None
    if not os.path.isfile(user_data_path):
        return None, f"找不到使用者資料庫：{user_data_path}"
    backend = get_backend_for_path(user_data_path)
    row = _find_user_record(backend, user_no)
    if row is None:
        msg = _backend_error(backend)
        if msg:
            return None, f"讀取 LAST_CO 失敗：{msg}"
        return None, None
    db_pw = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
    if db_pw != password:
        return None, None
    last_co = str(row[3]).strip() if len(row) > 3 and row[3] is not None else ""
    return (last_co or None), None
