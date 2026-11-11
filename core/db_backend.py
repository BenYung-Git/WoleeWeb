from __future__ import annotations

import os
import threading
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Dict, List, Any, Optional, Sequence, Tuple, Iterator

# 主檔／LOOKUP 等「顯示全部」讀取上限（避免舊預設 200／500 截斷）
FETCH_ALL_ROWS_LIMIT = 100000


def _row_matches_keyword(
    rec: List[str],
    kw: str,
    search_indices: Optional[List[int]] = None,
) -> bool:
    """關鍵字比對：有 search_indices 時僅掃指定欄，否則掃整列。"""
    if search_indices is None:
        return any(kw in c.lower() for c in rec)
    for i in search_indices:
        if 0 <= i < len(rec) and kw in str(rec[i]).lower():
            return True
    return False


def _odbc():
    """延遲載入 pyodbc；Ubuntu 僅用 SQLite 時不必安裝。"""
    try:
        import pyodbc
    except ImportError as exc:
        raise ImportError(
            "未安裝 pyodbc，無法使用 Access (.mdb)。"
            "Ubuntu: sudo apt install -y unixodbc-dev && pip install pyodbc；或改用 .sqlite。"
        ) from exc
    return pyodbc


def _access_sql_type_is_text(sql_data_type: int) -> bool:
    """Access ODBC：字元／備忘欄位；未知型別 (0) 依保守策略當文字處理。"""
    if sql_data_type == 0:
        return True
    odbc = _odbc()
    text_types = frozenset(
        {
            odbc.SQL_CHAR,
            odbc.SQL_VARCHAR,
            odbc.SQL_LONGVARCHAR,
            odbc.SQL_WCHAR,
            odbc.SQL_WVARCHAR,
            odbc.SQL_WLONGVARCHAR,
        }
    )
    return sql_data_type in text_types


def _access_bind_param(
    sql_data_type: int, value: Any, *, for_where: bool = False
) -> Any:
    """
    將寫入／WHERE 用的字串值轉成適合 Access ODBC 的繫結值。
    - SET／INSERT：非文字欄位且內容空白 → NULL（避免 '' 繫結到數值／日期／BIT 觸發 22018）
    - WHERE／DELETE：空白一律維持 ''，避免 = NULL 永遠比對不到列（No rows were updated）
    - BIT／YESNO：接受 str(True)/False、Y/N 等，改為 bool
    """
    s = "" if value is None else (value if isinstance(value, str) else str(value))
    t = (s or "").strip()

    if sql_data_type == _odbc().SQL_BIT:
        if not t:
            return "" if for_where else None
        low = t.lower()
        if low in ("y", "yes", "true", "1", "-1", "t"):
            return True
        if low in ("n", "no", "false", "0", "f"):
            return False
        return s

    if not t:
        if for_where:
            return ""
        return "" if _access_sql_type_is_text(sql_data_type) else None

    return s


def _access_coerce_row(
    types_by_col_upper: Dict[str, int],
    fields: List[str],
    values: Sequence[Any],
    *,
    for_where: bool = False,
) -> List[Any]:
    out: List[Any] = []
    for f, v in zip(fields, values):
        st = types_by_col_upper.get((f or "").strip().upper(), 0)
        out.append(_access_bind_param(st, v, for_where=for_where))
    return out


def _align_rows_to_column_order(
    select_columns: List[str],
    rows: List[List[str]],
    column_order: Optional[List[str]] = None,
) -> List[List[str]]:
    """
    ODBC metadata / SELECT * 的欄位順序可能與 list_columns 不同；
    依欄位名將每列重排為與 column_order 一致（不區分大小寫）。
    """
    if not column_order or not select_columns or not rows:
        return rows
    idx: Dict[str, int] = {}
    for i, c in enumerate(select_columns):
        key = str(c).strip().upper()
        if key not in idx:
            idx[key] = i
    out: List[List[str]] = []
    for rec in rows:
        line: List[str] = []
        for name in column_order:
            j = idx.get((name or "").strip().upper())
            if j is not None and j < len(rec):
                line.append(rec[j])
            else:
                line.append("")
        out.append(line)
    return out

# SQLite 可選
try:
    import sqlite3
    _HAS_SQLITE = True
except ImportError:
    _HAS_SQLITE = False


def resolve_sqlite_table_name(db_path: str, table_name: str) -> str:
    """SQLite 表名大小寫容錯：WorkDay → 實際表 WORKDAY 等。"""
    if not _HAS_SQLITE or not table_name or not os.path.isfile(db_path):
        return table_name
    want = (table_name or "").strip().upper()
    if not want:
        return table_name
    try:
        conn = sqlite3.connect(db_path)
        try:
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                t = str(row[0] or "").strip()
                if t.upper() == want:
                    return t
        finally:
            conn.close()
    except Exception:
        pass
    return table_name


class DbBackendBase(ABC):
    """資料庫後端抽象：欄位列表、查詢、新增、更新、刪除。"""

    @abstractmethod
    def list_columns(self, table_name: str) -> List[str]:
        pass

    @abstractmethod
    def fetch_rows(
        self,
        table_name: str,
        keyword: str,
        as_filter: bool,
        limit: int = FETCH_ALL_ROWS_LIMIT,
        column_order: Optional[List[str]] = None,
        search_indices: Optional[List[int]] = None,
    ) -> List[List[str]]:
        pass

    @abstractmethod
    def fetch_rows_where(
        self,
        table_name: str,
        field_name: str,
        value: str,
        limit: int = 200,
        column_order: Optional[List[str]] = None,
    ) -> List[List[str]]:
        """依欄位精準過濾：WHERE field_name = value。"""
        pass

    @abstractmethod
    def insert_one(self, table_name: str, field_names: List[str], values: List[str]) -> bool:
        pass

    @abstractmethod
    def update_one(
        self,
        table_name: str,
        set_fields: List[str],
        new_values: List[str],
        where_fields: List[str],
        old_row: List[str],
    ) -> bool:
        """SET set_fields；WHERE 依 where_fields 與 old_row 對應值。"""
        pass

    @abstractmethod
    def delete_one(self, table_name: str, where_fields: List[str], old_row: List[str]) -> bool:
        pass

    def fetch_rows_sql(
        self,
        sql: str,
        params: Optional[Sequence[Any]] = None,
        limit: int = 5000,
        column_order: Optional[List[str]] = None,
    ) -> Tuple[List[str], List[List[str]]]:
        """
        執行任意 SELECT SQL，回傳 (select_columns, rows)。
        - limit: 僅作為保護上限（實作端可能以 fetchmany 截斷）
        - column_order: 若提供，會依欄位名重排每列回傳（不分大小寫）
        """
        raise NotImplementedError("fetch_rows_sql is not implemented for this backend")

    def refresh_for_read(self) -> None:
        """查詢前刷新讀取狀態（Access 長連線需重開；SQLite 每次新連線已戳破快取）。"""
        return


class AccessBackend(DbBackendBase):
    """
    Access (.mdb/.accdb) 簡易資料後端：
    - 列出資料表欄位
    - 讀取資料列（簡單搜尋：先抓取前 N 筆再於記憶體過濾）
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._conn: Optional[Any] = None
        self.last_error: str = ""
        self._lock = threading.Lock()
        # 資料表欄位名(大寫) -> ODBC sql_data_type，供 INSERT/UPDATE/DELETE 繫結前修正型別
        self._access_col_sql_types: Dict[str, Dict[str, int]] = {}

    @property
    def lock(self) -> threading.Lock:
        return self._lock

    @contextmanager
    def operation(self) -> Iterator[Any]:
        """執行 ODBC 操作時的執行緒安全鎖 + 共用連線。"""
        with self._lock:
            conn = self._get_conn()
            if conn is None:
                raise _odbc().Error(self.last_error or f"無法連線 Access：{self.db_path}")
            yield conn

    def _connect(self) -> Any:
        conn_str = (
            r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
            rf"DBQ={self.db_path};"
        )
        return _odbc().connect(conn_str)

    def _reset_conn(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def refresh_for_read(self) -> None:
        """關閉長連線，下次讀取會重連以看到剛寫入／他端更新的資料。"""
        with self._lock:
            self._reset_conn()
            self._access_col_sql_types.clear()

    def _load_access_column_sql_types(
        self, conn: Any, table_name: str
    ) -> Dict[str, int]:
        tkey = (table_name or "").strip().upper()
        if tkey in self._access_col_sql_types:
            return self._access_col_sql_types[tkey]
        types: Dict[str, int] = {}
        try:
            cur = conn.cursor()
            for row in cur.columns(table=table_name):
                cn = (getattr(row, "column_name", None) or "").strip()
                if not cn:
                    continue
                st = getattr(row, "sql_data_type", None)
                if st is not None:
                    types[cn.upper()] = int(st)
        except Exception:
            pass
        self._access_col_sql_types[tkey] = types
        return types

    def _get_conn(self) -> Optional[Any]:
        if self._conn is not None:
            try:
                cur = self._conn.cursor()
                cur.execute("SELECT 1")
                cur.fetchone()
                return self._conn
            except Exception:
                self._reset_conn()
        try:
            self._conn = self._connect()
            self.last_error = ""
            return self._conn
        except Exception as ex:
            self._conn = None
            self.last_error = str(ex)
            return None

    def close(self) -> None:
        """釋放共用 ODBC 連線（通常應使用 access_pool，勿隨意 close）。"""
        with self._lock:
            self._reset_conn()

    def list_columns(self, table_name: str) -> List[str]:
        if not os.path.exists(self.db_path):
            return []
        with self._lock:
            conn = self._get_conn()
            if conn is None:
                return []
            try:
                cur = conn.cursor()
                # 使用 ODBC metadata 取得欄位名稱
                cols: List[str] = []
                for row in cur.columns(table=table_name):
                    col_name = row.column_name
                    if col_name:
                        cols.append(str(col_name))
                # 若 metadata 取不到，退回用 SELECT TOP 1 * 嘗試推斷
                if not cols:
                    try:
                        cur.execute(f"SELECT TOP 1 * FROM [{table_name}]")
                        cols = [d[0] for d in cur.description] if cur.description else []
                    except Exception:
                        cols = []
                return cols
            except Exception:
                self._reset_conn()
                return []

    def fetch_rows(
        self,
        table_name: str,
        keyword: str,
        as_filter: bool,
        limit: int = FETCH_ALL_ROWS_LIMIT,
        column_order: Optional[List[str]] = None,
        search_indices: Optional[List[int]] = None,
    ) -> List[List[str]]:
        with self._lock:
            if not os.path.exists(self.db_path):
                return []
            conn = self._get_conn()
            if conn is None:
                return []
            try:
                cur = conn.cursor()
                try:
                    cur.execute(f"SELECT TOP {limit} * FROM [{table_name}]")
                except Exception:
                    return []
                rows_raw = cur.fetchall()
                cols = [d[0] for d in cur.description] if cur.description else []

                # 轉成字串二維陣列
                data: List[List[str]] = []
                for r in rows_raw:
                    rec = []
                    for v in r:
                        rec.append("" if v is None else str(v))
                    data.append(rec)

                data = _align_rows_to_column_order(cols, data, column_order)

                if not keyword:
                    return data

                # 若為過濾：保留匹配列；若不是過濾：回傳全部（讓前端只移動游標）
                if as_filter:
                    kw = keyword.lower()
                    return [
                        rec
                        for rec in data
                        if _row_matches_keyword(rec, kw, search_indices)
                    ]
                return data
            except Exception:
                self._reset_conn()
                return []

    def fetch_rows_where(
        self,
        table_name: str,
        field_name: str,
        value: str,
        limit: int = 200,
        column_order: Optional[List[str]] = None,
    ) -> List[List[str]]:
        if not os.path.exists(self.db_path) or not table_name or not field_name:
            return []
        conn = self._get_conn()
        if conn is None:
            return []
        try:
            cur = conn.cursor()
            types = self._load_access_column_sql_types(conn, table_name)
            vparam = _access_bind_param(
                types.get((field_name or "").strip().upper(), 0), value, for_where=True
            )
            sql = f"SELECT TOP {limit} * FROM [{table_name}] WHERE [{field_name}] = ?"
            cur.execute(sql, (vparam,))
            rows_raw = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
            data: List[List[str]] = []
            for r in rows_raw:
                rec = []
                for v in r:
                    rec.append("" if v is None else str(v))
                data.append(rec)
            return _align_rows_to_column_order(cols, data, column_order)
        except Exception:
            self._reset_conn()
            return []

    def fetch_rows_sql(
        self,
        sql: str,
        params: Optional[Sequence[Any]] = None,
        limit: int = 5000,
        column_order: Optional[List[str]] = None,
    ) -> Tuple[List[str], List[List[str]]]:
        self.last_error = ""
        if not os.path.exists(self.db_path):
            self.last_error = "Database path does not exist."
            return [], []
        conn = self._get_conn()
        if conn is None:
            if not self.last_error:
                self.last_error = "Database connection is not available."
            return [], []
        s = (sql or "").strip()
        if not s:
            self.last_error = "SQL is empty."
            return [], []
        try:
            cur = conn.cursor()
            if params:
                cur.execute(s, list(params))
            else:
                cur.execute(s)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows_raw = cur.fetchmany(max(0, int(limit)))
            data: List[List[str]] = []
            for r in rows_raw:
                rec: List[str] = []
                for v in r:
                    rec.append("" if v is None else str(v))
                data.append(rec)
            data = _align_rows_to_column_order(cols, data, column_order)
            # 若有重排，回傳欄位名必須與列值順序一致
            if column_order:
                return list(column_order), data
            return cols, data
        except Exception as ex:
            self.last_error = str(ex)
            self._reset_conn()
            return [], []

    def insert_one(self, table_name: str, field_names: List[str], values: List[str]) -> bool:
        self.last_error = ""
        if not os.path.exists(self.db_path) or not field_names:
            self.last_error = "Invalid insert parameters or database path does not exist."
            return False
        conn = self._get_conn()
        if conn is None:
            if not self.last_error:
                self.last_error = "Database connection is not available."
            return False
        try:
            cur = conn.cursor()
            types = self._load_access_column_sql_types(conn, table_name)
            bound = _access_coerce_row(types, field_names, values, for_where=False)
            cols = ", ".join(f"[{c}]" for c in field_names)
            placeholders = ", ".join("?" for _ in field_names)
            sql = f"INSERT INTO [{table_name}] ({cols}) VALUES ({placeholders})"
            cur.execute(sql, bound)
            conn.commit()
            return True
        except Exception as ex:
            base_err = str(ex)
            # 常見於 Access 自動編號欄位：空白值插入失敗，改成略過空白欄位重試。
            try:
                trimmed_pairs = [
                    (f, v)
                    for f, v in zip(field_names, values)
                    if str(v).strip() != ""
                ]
                if trimmed_pairs and len(trimmed_pairs) < len(field_names):
                    cols2 = ", ".join(f"[{f}]" for f, _v in trimmed_pairs)
                    placeholders2 = ", ".join("?" for _f, _v in trimmed_pairs)
                    sql2 = f"INSERT INTO [{table_name}] ({cols2}) VALUES ({placeholders2})"
                    cur = conn.cursor()
                    types = self._load_access_column_sql_types(conn, table_name)
                    tfields = [f for f, _v in trimmed_pairs]
                    tvals = [v for _f, v in trimmed_pairs]
                    cur.execute(sql2, _access_coerce_row(types, tfields, tvals, for_where=False))
                    conn.commit()
                    self.last_error = ""
                    return True
            except Exception as ex2:
                self.last_error = f"{base_err}; retry_without_empty_columns: {ex2}"
                self._reset_conn()
                return False
            self.last_error = base_err
            self._reset_conn()
            return False

    def update_one(
        self,
        table_name: str,
        set_fields: List[str],
        new_values: List[str],
        where_fields: List[str],
        old_row: List[str],
    ) -> bool:
        self.last_error = ""
        if (
            not os.path.exists(self.db_path)
            or not set_fields
            or len(new_values) != len(set_fields)
            or len(old_row) != len(where_fields)
        ):
            self.last_error = "Invalid update parameters or database path does not exist."
            return False
        conn = self._get_conn()
        if conn is None:
            if not self.last_error:
                self.last_error = "Database connection is not available."
            return False
        try:
            cur = conn.cursor()
            types = self._load_access_column_sql_types(conn, table_name)
            set_bound = _access_coerce_row(types, set_fields, new_values, for_where=False)
            where_bound = _access_coerce_row(types, where_fields, old_row, for_where=True)
            set_parts = ", ".join(f"[{c}] = ?" for c in set_fields)
            where_parts = " AND ".join(f"[{c}] = ?" for c in where_fields)
            sql = f"UPDATE [{table_name}] SET {set_parts} WHERE {where_parts}"
            cur.execute(sql, set_bound + where_bound)
            conn.commit()
            if cur.rowcount <= 0:
                self.last_error = "No rows were updated (WHERE condition did not match)."
                return False
            return True
        except Exception as ex:
            self._reset_conn()
            self.last_error = str(ex)
            return False

    def delete_one(self, table_name: str, where_fields: List[str], old_row: List[str]) -> bool:
        self.last_error = ""
        if not os.path.exists(self.db_path) or not where_fields or len(old_row) != len(where_fields):
            self.last_error = "Invalid delete parameters or database path does not exist."
            return False
        conn = self._get_conn()
        if conn is None:
            if not self.last_error:
                self.last_error = "Database connection is not available."
            return False
        try:
            cur = conn.cursor()
            types = self._load_access_column_sql_types(conn, table_name)
            where_bound = _access_coerce_row(types, where_fields, old_row, for_where=True)
            where_parts = " AND ".join(f"[{c}] = ?" for c in where_fields)
            sql = f"DELETE FROM [{table_name}] WHERE {where_parts}"
            cur.execute(sql, where_bound)
            conn.commit()
            if cur.rowcount <= 0:
                self.last_error = "No rows were deleted (WHERE condition did not match)."
                return False
            return True
        except Exception as ex:
            self._reset_conn()
            self.last_error = str(ex)
            return False


class SQLiteBackend(DbBackendBase):
    """SQLite 後端：欄位列表、查詢、新增、更新、刪除。"""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.last_error: str = ""

    def refresh_for_read(self) -> None:
        """戳破 OS／Samba 頁面快取，避免讀到更新前的 SQLite 檔。"""
        try:
            from core.db_factory import bust_sqlite_os_cache

            bust_sqlite_os_cache(os.path.abspath(self.db_path))
        except Exception:
            try:
                os.stat(self.db_path)
            except OSError:
                pass

    def _connect(self, *, for_write: bool = False) -> "sqlite3.Connection":
        """
        每次新開連線；對 Samba／NFS 共用檔：
        - 小檔整檔讀過以戳破 OS／Samba 頁面快取
        - URI cache=private + mmap_size=0，避免 SQLite 讀到舊頁面
        - 寫入時 mode=rw；網路碟改 DELETE journal，降低 readonly／損毀
        """
        path = os.path.abspath(self.db_path)
        try:
            from core.db_factory import bust_sqlite_os_cache, is_likely_network_db_path

            bust_sqlite_os_cache(path)
            network = is_likely_network_db_path(path)
        except Exception:
            network = False
            try:
                os.stat(path)
            except OSError:
                pass
        conn = None
        try:
            uri_path = path.replace("\\", "/")
            # Windows：file:///S:/Share/... ；POSIX：file:///home/...
            if len(uri_path) >= 2 and uri_path[1] == ":":
                uri_path = "/" + uri_path
            q = "mode=rw&cache=private" if for_write else "cache=private"
            conn = sqlite3.connect(
                f"file:{uri_path}?{q}",
                uri=True,
                timeout=30,
            )
        except Exception:
            conn = sqlite3.connect(path, timeout=30)
        try:
            conn.execute("PRAGMA mmap_size=0")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA schema_version")
            if for_write:
                if network:
                    try:
                        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    except Exception:
                        pass
                    try:
                        conn.execute("PRAGMA journal_mode=DELETE")
                    except Exception:
                        pass
                else:
                    try:
                        conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
                    except Exception:
                        pass
        except Exception:
            pass
        return conn

    def _connect_write_fallback(self) -> "sqlite3.Connection":
        """唯讀錯誤後備：不用 URI，強制 DELETE journal。"""
        path = os.path.abspath(self.db_path)
        conn = sqlite3.connect(path, timeout=30)
        try:
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("PRAGMA busy_timeout=30000")
        except Exception:
            pass
        return conn

    @staticmethod
    def _is_readonly_error(ex: BaseException) -> bool:
        msg = str(ex or "").lower()
        return "readonly" in msg or "read-only" in msg or "read only" in msg

    def _table(self, table_name: str) -> str:
        return resolve_sqlite_table_name(self.db_path, table_name)

    def list_columns(self, table_name: str) -> List[str]:
        if not _HAS_SQLITE or not os.path.exists(self.db_path):
            return []
        table_name = self._table(table_name)
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(f'PRAGMA table_info("{table_name}")')
            rows = cur.fetchall()
            conn.close()
            return [str(r[1]) for r in rows if len(r) > 1]
        except Exception:
            return []

    def fetch_rows(
        self,
        table_name: str,
        keyword: str,
        as_filter: bool,
        limit: int = FETCH_ALL_ROWS_LIMIT,
        column_order: Optional[List[str]] = None,
        search_indices: Optional[List[int]] = None,
    ) -> List[List[str]]:
        if not _HAS_SQLITE or not os.path.exists(self.db_path):
            return []
        table_name = self._table(table_name)
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(f'SELECT * FROM "{table_name}" LIMIT {limit}')
            rows_raw = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
            conn.close()
            data = [["" if v is None else str(v) for v in r] for r in rows_raw]
            data = _align_rows_to_column_order(cols, data, column_order)
            if not keyword:
                return data
            if as_filter:
                kw = keyword.lower()
                return [
                    rec
                    for rec in data
                    if _row_matches_keyword(rec, kw, search_indices)
                ]
            return data
        except Exception:
            return []

    def fetch_rows_where(
        self,
        table_name: str,
        field_name: str,
        value: str,
        limit: int = 200,
        column_order: Optional[List[str]] = None,
    ) -> List[List[str]]:
        self.last_error = ""
        if not _HAS_SQLITE or not os.path.exists(self.db_path) or not table_name or not field_name:
            self.last_error = "Invalid fetch_rows_where parameters or sqlite is unavailable."
            return []
        table_name = self._table(table_name)
        try:
            conn = self._connect()
            cur = conn.cursor()
            sql = f'SELECT * FROM "{table_name}" WHERE "{field_name}" = ? LIMIT {limit}'
            cur.execute(sql, (value,))
            rows_raw = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
            conn.close()
            data = [["" if v is None else str(v) for v in r] for r in rows_raw]
            return _align_rows_to_column_order(cols, data, column_order)
        except Exception as ex:
            self.last_error = str(ex)
            return []

    def fetch_rows_sql(
        self,
        sql: str,
        params: Optional[Sequence[Any]] = None,
        limit: int = 5000,
        column_order: Optional[List[str]] = None,
    ) -> Tuple[List[str], List[List[str]]]:
        self.last_error = ""
        if not _HAS_SQLITE or not os.path.exists(self.db_path):
            self.last_error = "SQLite is unavailable or database path does not exist."
            return [], []
        s = (sql or "").strip()
        if not s:
            self.last_error = "SQL is empty."
            return [], []
        try:
            conn = self._connect()
            cur = conn.cursor()
            if params:
                cur.execute(s, tuple(params))
            else:
                cur.execute(s)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows_raw = cur.fetchmany(max(0, int(limit)))
            conn.close()
            data = [["" if v is None else str(v) for v in r] for r in rows_raw]
            data = _align_rows_to_column_order(cols, data, column_order)
            if column_order:
                return list(column_order), data
            return cols, data
        except Exception as ex:
            self.last_error = str(ex)
            return [], []

    def insert_one(self, table_name: str, field_names: List[str], values: List[str]) -> bool:
        self.last_error = ""
        if not _HAS_SQLITE or not os.path.exists(self.db_path) or not field_names:
            self.last_error = "Invalid insert parameters or sqlite is unavailable."
            return False
        table_name = self._table(table_name)

        def _do(conn: "sqlite3.Connection") -> None:
            from core.row_insert_defaults import fill_sqlite_not_null_defaults

            cur = conn.cursor()
            cur.execute(f'PRAGMA table_info("{table_name}")')
            col_infos = cur.fetchall()
            use_fields, use_values = fill_sqlite_not_null_defaults(
                col_infos, list(field_names), list(values)
            )
            cols = ", ".join(f'"{c}"' for c in use_fields)
            placeholders = ", ".join("?" for _ in use_fields)
            cur.execute(
                f'INSERT INTO "{table_name}" ({cols}) VALUES ({placeholders})',
                use_values,
            )
            conn.commit()

        try:
            conn = self._connect(for_write=True)
            try:
                _do(conn)
            finally:
                conn.close()
            return True
        except Exception as ex:
            if self._is_readonly_error(ex):
                try:
                    conn2 = self._connect_write_fallback()
                    try:
                        _do(conn2)
                    finally:
                        conn2.close()
                    return True
                except Exception as ex2:
                    self.last_error = str(ex2)
                    return False
            self.last_error = str(ex)
            return False

    def update_one(
        self,
        table_name: str,
        set_fields: List[str],
        new_values: List[str],
        where_fields: List[str],
        old_row: List[str],
    ) -> bool:
        self.last_error = ""
        if (
            not _HAS_SQLITE
            or not set_fields
            or len(new_values) != len(set_fields)
            or len(old_row) != len(where_fields)
        ):
            self.last_error = "Invalid update parameters or sqlite is unavailable."
            return False
        table_name = self._table(table_name)

        def _do(conn: "sqlite3.Connection") -> int:
            cur = conn.cursor()
            set_parts = ", ".join(f'"{c}" = ?' for c in set_fields)
            where_parts = " AND ".join(f'"{c}" = ?' for c in where_fields)
            cur.execute(
                f'UPDATE "{table_name}" SET {set_parts} WHERE {where_parts}',
                new_values + old_row,
            )
            conn.commit()
            return int(cur.rowcount)

        try:
            conn = self._connect(for_write=True)
            try:
                n = _do(conn)
            finally:
                conn.close()
            if n <= 0:
                self.last_error = "No rows were updated (WHERE condition did not match)."
                return False
            return True
        except Exception as ex:
            if self._is_readonly_error(ex):
                try:
                    conn2 = self._connect_write_fallback()
                    try:
                        n = _do(conn2)
                    finally:
                        conn2.close()
                    if n <= 0:
                        self.last_error = (
                            "No rows were updated (WHERE condition did not match)."
                        )
                        return False
                    return True
                except Exception as ex2:
                    self.last_error = str(ex2)
                    return False
            self.last_error = str(ex)
            return False

    def delete_one(self, table_name: str, where_fields: List[str], old_row: List[str]) -> bool:
        self.last_error = ""
        if not _HAS_SQLITE or not where_fields or len(old_row) != len(where_fields):
            self.last_error = "Invalid delete parameters or sqlite is unavailable."
            return False
        table_name = self._table(table_name)

        def _do(conn: "sqlite3.Connection") -> int:
            cur = conn.cursor()
            where_parts = " AND ".join(f'"{c}" = ?' for c in where_fields)
            cur.execute(f'DELETE FROM "{table_name}" WHERE {where_parts}', old_row)
            conn.commit()
            return int(cur.rowcount)

        try:
            conn = self._connect(for_write=True)
            try:
                n = _do(conn)
            finally:
                conn.close()
            if n <= 0:
                self.last_error = "No rows were deleted (WHERE condition did not match)."
                return False
            return True
        except Exception as ex:
            if self._is_readonly_error(ex):
                try:
                    conn2 = self._connect_write_fallback()
                    try:
                        n = _do(conn2)
                    finally:
                        conn2.close()
                    if n <= 0:
                        self.last_error = (
                            "No rows were deleted (WHERE condition did not match)."
                        )
                        return False
                    return True
                except Exception as ex2:
                    self.last_error = str(ex2)
                    return False
            self.last_error = str(ex)
            return False

