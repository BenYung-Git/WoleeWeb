"""RUNQUERY 執行查詢：多資料庫連線、執行 SQL（查詢／更新）、USER_DATA.RUN_QUERY 存取。"""
from __future__ import annotations

import io
import os
import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.db_backend import AccessBackend, DbBackendBase, SQLiteBackend
from core.db_factory import get_backend_for_path, resolve_metadata_db_path

RUN_QUERY_DO_PROC = "RUNQUERY"
RUN_QUERY_PROC_ALIASES = frozenset(
    {
        "RUNQUERY",
        "DO_RUNQUERY",
        "RUN_QUERY",
        "DO_RUN_QUERY",
        "RUNQUERY",
    }
)
RUN_QUERY_TABLE = "RUN_QUERY"
RUN_QUERY_WORK_DB = "USER_DATA.MDB"
RUN_QUERY_VISIBLE_ROWS = 12
RUN_QUERY_RESULT_LIMIT = 50000

FIELD_CODE = "QRY_CODE"
FIELD_DESC = "QRY_DESC"
FIELD_COMMAND = "QRY_COMMAND"
FIELD_USER = "USER"
FIELD_DATE = "QRY_DATE"

DB_KIND_SQLITE = "SQLITE"
DB_KIND_ACCESS = "ACCESS"
DB_KIND_SQLSERVER = "SQLSERVER"
DB_KIND_MYSQL = "MYSQL"
DB_KINDS = (DB_KIND_SQLITE, DB_KIND_ACCESS, DB_KIND_SQLSERVER, DB_KIND_MYSQL)

_COLUMN_DEFS: List[Dict[str, Any]] = [
    {
        "NAME": FIELD_CODE,
        "CHN_TITLE": "查詢 #",
        "ENG_TITLE": "Query #",
        "GRID_VIEW": True,
        "GRID_INDEX": 3,
        "CTRL_EDIT": True,
        "CTRL_INDEX": 3,
        "DATA_TYPE": "S",
        "WIDTH": 12,
        "EDIT_TYPE": "K",
        "TBL_LIST": True,
        "SEARCH": True,
    },
    {
        "NAME": FIELD_DESC,
        "CHN_TITLE": "說明",
        "ENG_TITLE": "Description",
        "GRID_VIEW": True,
        "GRID_INDEX": 6,
        "CTRL_EDIT": True,
        "CTRL_INDEX": 6,
        "DATA_TYPE": "S",
        "WIDTH": 30,
        "TBL_LIST": True,
        "SEARCH": True,
    },
    {
        "NAME": FIELD_COMMAND,
        "CHN_TITLE": "指令",
        "ENG_TITLE": "Command",
        "GRID_VIEW": True,
        "GRID_INDEX": 9,
        "CTRL_EDIT": True,
        "CTRL_INDEX": 9,
        "DATA_TYPE": "S",
        "WIDTH": 60,
        "TBL_LIST": True,
        "SEARCH": True,
    },
    {
        "NAME": FIELD_USER,
        "CHN_TITLE": "使用者",
        "ENG_TITLE": "User",
        "GRID_VIEW": True,
        "GRID_INDEX": 12,
        "CTRL_EDIT": True,
        "CTRL_INDEX": 12,
        "DATA_TYPE": "S",
        "WIDTH": 12,
        "TBL_LIST": True,
        "SEARCH": True,
    },
    {
        "NAME": FIELD_DATE,
        "CHN_TITLE": "日期時間",
        "ENG_TITLE": "Date/Time",
        "GRID_VIEW": True,
        "GRID_INDEX": 15,
        "CTRL_EDIT": True,
        "CTRL_INDEX": 15,
        "DATA_TYPE": "S",
        "WIDTH": 19,
        "TBL_LIST": True,
        "SEARCH": True,
    },
]

# 允許查詢與更新紀錄；禁止破壞性 DDL／系統指令
_FORBIDDEN_SQL = re.compile(
    r"\b(DROP|TRUNCATE|ALTER|CREATE|ATTACH|DETACH|PRAGMA|VACUUM|"
    r"REINDEX|GRANT|REVOKE|EXEC|EXECUTE|MERGE|CALL|BACKUP|RESTORE|"
    r"SHUTDOWN|KILL)\b",
    re.IGNORECASE,
)


@dataclass
class DbConnectionSpec:
    kind: str = DB_KIND_SQLITE
    path: str = ""
    host: str = "localhost"
    port: int = 0
    database: str = ""
    user: str = ""
    password: str = ""
    driver: str = ""

    def normalized_kind(self) -> str:
        k = str(self.kind or "").strip().upper().replace(" ", "").replace("-", "")
        if k in ("SQLITE", "SQLLITE"):
            return DB_KIND_SQLITE
        if k in ("ACCESS", "MDB", "ACCDB"):
            return DB_KIND_ACCESS
        if k in ("SQLSERVER", "MSSQL", "SQLSRV"):
            return DB_KIND_SQLSERVER
        if k in ("MYSQL", "MARIADB"):
            return DB_KIND_MYSQL
        return k


@dataclass
class SqlExecuteResult:
    columns: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)
    sql: str = ""
    total: int = 0
    rowcount: int = -1
    is_result_set: bool = True
    message: str = ""


def is_run_query_program(do_proc: str) -> bool:
    key = str(do_proc or "").strip().upper().replace("-", "_")
    if not key:
        return False
    if key in RUN_QUERY_PROC_ALIASES or key == "RUNQUERY":
        return True
    return key.endswith("RUNQUERY") or key.endswith("RUN_QUERY")


def db_kind_options(*, chn: bool = True) -> List[Dict[str, str]]:
    if chn:
        return [
            {"kind": DB_KIND_SQLITE, "label": "SQLite"},
            {"kind": DB_KIND_ACCESS, "label": "Access"},
            {"kind": DB_KIND_SQLSERVER, "label": "SQL Server"},
            {"kind": DB_KIND_MYSQL, "label": "MySQL"},
        ]
    return [{"kind": k, "label": k} for k in DB_KINDS]


def _pick(cmap: Dict[str, str], *names: str) -> Optional[str]:
    for n in names:
        hit = cmap.get(str(n).upper())
        if hit:
            return hit
    return None


def _col_map(backend: DbBackendBase, table: str) -> Dict[str, str]:
    cols = backend.list_columns(table) or []
    return {str(c).strip().upper(): str(c) for c in cols if str(c).strip()}


def _has_table(backend: DbBackendBase, table: str) -> bool:
    try:
        return bool(backend.list_columns(table))
    except Exception:
        return False


def _exec_non_query(backend: DbBackendBase, sql: str) -> Tuple[bool, str]:
    try:
        if isinstance(backend, SQLiteBackend):
            conn = backend._connect()  # noqa: SLF001
            try:
                conn.execute(sql)
                conn.commit()
            finally:
                conn.close()
            return True, ""
        if isinstance(backend, AccessBackend):
            with backend.operation() as conn:
                cur = conn.cursor()
                cur.execute(sql)
                try:
                    conn.commit()
                except Exception:
                    pass
            return True, ""
        backend.fetch_rows_sql(sql, limit=0)
        err = getattr(backend, "last_error", "") or ""
        return (not err), err
    except Exception as ex:
        return False, str(ex)


def resolve_run_query_data_path(base_dir: str) -> str:
    path = resolve_metadata_db_path(base_dir, RUN_QUERY_WORK_DB)
    if not path:
        from core.auth import resolve_user_data_path

        path = resolve_user_data_path(base_dir)
    return path or ""


def ensure_run_query_table(data_backend: DbBackendBase) -> Tuple[bool, str]:
    if _has_table(data_backend, RUN_QUERY_TABLE):
        return True, ""
    if isinstance(data_backend, SQLiteBackend):
        sql = (
            f'CREATE TABLE IF NOT EXISTS "{RUN_QUERY_TABLE}" ('
            f'"{FIELD_CODE}" TEXT, '
            f'"{FIELD_DESC}" TEXT, '
            f'"{FIELD_COMMAND}" TEXT, '
            f'"{FIELD_USER}" TEXT, '
            f'"{FIELD_DATE}" TEXT'
            f")"
        )
    else:
        sql = (
            f"CREATE TABLE {RUN_QUERY_TABLE} ("
            f"{FIELD_CODE} VARCHAR(40), "
            f"{FIELD_DESC} VARCHAR(120), "
            f"{FIELD_COMMAND} MEMO, "
            f"{FIELD_USER} VARCHAR(40), "
            f"{FIELD_DATE} VARCHAR(30)"
            f")"
        )
    return _exec_non_query(data_backend, sql)


def ensure_run_query_columns(sys_backend: DbBackendBase) -> Tuple[bool, str]:
    cmap = _col_map(sys_backend, "columns")
    if not cmap:
        return False, "找不到 COLUMNS 資料表。"
    dbf_col = _pick(cmap, "DBF_NAME")
    name_col = _pick(cmap, "NAME")
    if not dbf_col or not name_col:
        return False, "COLUMNS 缺少 DBF_NAME / NAME。"

    existing: set[str] = set()
    _c, rows = sys_backend.fetch_rows_sql(
        f"SELECT {name_col} FROM columns WHERE {dbf_col} = ?",
        params=[RUN_QUERY_TABLE],
        limit=500,
    )
    for r in rows or []:
        if r:
            existing.add(str(r[0] or "").strip().upper())

    bit_t, bit_f = ("1", "0")
    for defn in _COLUMN_DEFS:
        fname = str(defn["NAME"]).upper()
        if fname in existing:
            continue
        fields: List[str] = []
        values: List[str] = []

        def add(logical: str, value: Any, *aliases: str) -> None:
            col = _pick(cmap, logical, *aliases)
            if not col:
                return
            fields.append(col)
            if isinstance(value, bool):
                values.append(bit_t if value else bit_f)
            elif value is None:
                values.append("")
            else:
                values.append(str(value))

        add("DBF_NAME", RUN_QUERY_TABLE)
        add("NAME", defn["NAME"])
        add("CHN_TITLE", defn.get("CHN_TITLE") or "")
        add("ENG_TITLE", defn.get("ENG_TITLE") or "")
        add("SCHN_TITLE", defn.get("CHN_TITLE") or "")
        add("GRID_VIEW", bool(defn.get("GRID_VIEW")))
        add("GRID_INDEX", float(defn.get("GRID_INDEX") or 0))
        add("CTRL_EDIT", bool(defn.get("CTRL_EDIT")))
        add("CTRL_LABEL", True)
        add("CTRL_INDEX", float(defn.get("CTRL_INDEX") or 0))
        add("CTRL_TYPE", "TEXT")
        add("DATA_TYPE", defn.get("DATA_TYPE") or "S")
        add("WIDTH", float(defn.get("WIDTH") or 10))
        add("TBL_LIST", bool(defn.get("TBL_LIST")))
        add("LIST_SEQ", 0.0)
        add("FIELD_TOTAL", False)
        add("SEARCH", bool(defn.get("SEARCH")))
        if defn.get("EDIT_TYPE"):
            add("EDIT_TYPE", defn["EDIT_TYPE"])
        if not sys_backend.insert_one("columns", fields, values):
            return False, getattr(sys_backend, "last_error", "") or f"無法寫入 COLUMNS：{fname}"
    return True, ""


def ensure_run_query_program(sys_backend: DbBackendBase) -> Tuple[bool, str]:
    """確保 PROGRAM.DO_PROC=RUNQUERY、STD_PROC=False、Need_Do=True。"""
    cmap = _col_map(sys_backend, "program")
    if not cmap:
        return False, "找不到 PROGRAM 資料表。"
    do_col = _pick(cmap, "DO_PROC")
    if not do_col:
        return False, "找不到 PROGRAM.DO_PROC。"
    need_col = _pick(cmap, "Need_Do", "NEED_DO")
    std_col = _pick(cmap, "STD_PROC", "Std_Proc", "STD_PORC")

    target = ""
    for cand in ("RUNQUERY", "RunQuery", "DO_RUNQUERY", "RUN_QUERY"):
        _c, rows = sys_backend.fetch_rows_sql(
            f"SELECT {do_col} FROM program WHERE {do_col} = ?",
            params=[cand],
            limit=3,
        )
        if rows:
            target = str(rows[0][0] or "").strip()
            break

    if target:
        set_fields: List[str] = []
        set_vals: List[str] = []
        if need_col:
            set_fields.append(need_col)
            set_vals.append("1")
        if std_col:
            set_fields.append(std_col)
            set_vals.append("0")
        # 正規化 DO_PROC 為 RUNQUERY（若原為 RunQuery 則改名）
        if target.upper() != RUN_QUERY_DO_PROC and do_col:
            set_fields.append(do_col)
            set_vals.append(RUN_QUERY_DO_PROC)
        for logical, val in (
            ("WORK_FILE", RUN_QUERY_TABLE),
            ("WORK_DB", RUN_QUERY_WORK_DB),
            ("WORK_PROC", RUN_QUERY_TABLE),
            ("KEY_CODE", FIELD_CODE),
            ("Proc_Name", "DO_RUNQUERY"),
            ("ENG_TITLE", "Execute Query"),
            ("CHN_TITLE", "執行查詢"),
        ):
            col = _pick(cmap, logical, "PROC_NAME" if logical == "Proc_Name" else logical)
            if col and col not in set_fields:
                set_fields.append(col)
                set_vals.append(val)
        if set_fields:
            sys_backend.update_one("program", set_fields, set_vals, [do_col], [target])
        return True, ""

    fields: List[str] = []
    values: List[str] = []
    bit_t, bit_f = ("1", "0")

    def add(logical: str, value: Any, *aliases: str) -> None:
        col = _pick(cmap, logical, *aliases)
        if not col:
            return
        fields.append(col)
        if isinstance(value, bool):
            values.append(bit_t if value else bit_f)
        elif value is None:
            values.append("")
        else:
            values.append(str(value))

    add("PRG_GROUP", "UTL")
    add("ItemNumber", 88.0, "ITEMNUMBER")
    add("Proc_Name", "DO_RUNQUERY", "PROC_NAME")
    add("Level", 99.0)
    add("STD_PROC", False, "Std_Proc", "STD_PORC")
    add("DO_PROC", RUN_QUERY_DO_PROC)
    add("Need_Do", True, "NEED_DO")
    add("NEED_ATTACH", False)
    add("NEED_OTHER", False)
    add("WORK_PROC", RUN_QUERY_TABLE)
    add("WORK_DB", RUN_QUERY_WORK_DB)
    add("WORK_FILE", RUN_QUERY_TABLE)
    add("KEY_CODE", FIELD_CODE)
    add("ENG_TITLE", "Execute Query")
    add("CHN_TITLE", "執行查詢")
    add("SCHN_TITLE", "执行查询")
    add("Need_TxLog", False, "NEED_TXLOG")

    if not sys_backend.insert_one("program", fields, values):
        return False, getattr(sys_backend, "last_error", "") or "無法寫入 PROGRAM。"
    return True, ""


def ensure_run_query_infra(base_dir: str, sys_mdb_path: str) -> Tuple[bool, str]:
    from core.auth import enumerate_sys_data_paths

    data_path = resolve_run_query_data_path(base_dir)
    if not data_path or not os.path.isfile(data_path):
        return False, f"找不到 USER_DATA：{data_path or '(empty)'}"

    data_be = get_backend_for_path(data_path)
    ok, err = ensure_run_query_table(data_be)
    if not ok:
        return False, err or "無法建立 RUN_QUERY 資料表。"

    sys_paths: List[str] = []
    seen: set[str] = set()
    for p in [sys_mdb_path, *enumerate_sys_data_paths(base_dir)]:
        ap = os.path.abspath(p) if p else ""
        if ap and ap not in seen and os.path.isfile(ap):
            seen.add(ap)
            sys_paths.append(ap)
    if not sys_paths:
        return False, "找不到 sys_data。"

    last_err = ""
    any_ok = False
    for sp in sys_paths:
        be = get_backend_for_path(sp)
        ok, err = ensure_run_query_columns(be)
        if not ok:
            last_err = err or last_err
            continue
        ok, err = ensure_run_query_program(be)
        if not ok:
            last_err = err or last_err
            continue
        any_ok = True
    if not any_ok:
        return False, last_err or "無法準備 PROGRAM／COLUMNS。"
    return True, ""


def sanitize_sql(sql: str) -> Tuple[Optional[str], Optional[str]]:
    """允許單一 SELECT／WITH／INSERT／UPDATE／DELETE；禁止破壞性 DDL。"""
    raw = (sql or "").strip()
    if not raw:
        return None, "請輸入 SQL 指令。"
    no_block = re.sub(r"/\*.*?\*/", " ", raw, flags=re.DOTALL)
    lines = []
    for ln in no_block.splitlines():
        if "--" in ln:
            ln = ln[: ln.index("--")]
        lines.append(ln)
    cleaned = re.sub(r"\s+", " ", " ".join(lines)).strip()
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].strip()
    if ";" in cleaned:
        return None, "僅允許單一 SQL 語句。"
    if not cleaned:
        return None, "請輸入 SQL 指令。"
    if _FORBIDDEN_SQL.search(cleaned):
        return None, "不允許 DROP／ALTER／CREATE 等破壞性指令。"
    head = cleaned.lstrip("(").lstrip().upper()
    allowed = ("SELECT", "WITH", "INSERT", "UPDATE", "DELETE")
    if not any(head.startswith(a) for a in allowed):
        return None, "僅允許 SELECT／WITH／INSERT／UPDATE／DELETE。"
    return cleaned, None


def _cell_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v)


def _connect_sqlite(spec: DbConnectionSpec) -> Tuple[Any, Optional[str]]:
    path = (spec.path or "").strip()
    if not path:
        return None, "請指定 SQLite 檔案路徑。"
    if not os.path.isfile(path):
        return None, f"找不到 SQLite 檔：{path}"
    try:
        conn = sqlite3.connect(path, timeout=30)
        return conn, None
    except Exception as ex:
        return None, str(ex)


def _connect_access(spec: DbConnectionSpec) -> Tuple[Any, Optional[str]]:
    path = (spec.path or "").strip()
    if not path:
        return None, "請指定 Access 檔案路徑。"
    if not os.path.isfile(path):
        return None, f"找不到 Access 檔：{path}"
    try:
        import pyodbc
    except ImportError:
        return None, "未安裝 pyodbc，無法連線 Access。"
    try:
        conn_str = (
            r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
            rf"DBQ={path};"
        )
        return pyodbc.connect(conn_str), None
    except Exception as ex:
        return None, str(ex)


def _connect_sqlserver(spec: DbConnectionSpec) -> Tuple[Any, Optional[str]]:
    try:
        import pyodbc
    except ImportError:
        return None, "未安裝 pyodbc，無法連線 SQL Server。"
    host = (spec.host or "localhost").strip() or "localhost"
    port = int(spec.port or 0)
    database = (spec.database or "").strip()
    user = (spec.user or "").strip()
    password = spec.password or ""
    driver = (spec.driver or "").strip() or "ODBC Driver 17 for SQL Server"
    server = f"{host},{port}" if port > 0 else host
    try:
        if user:
            conn_str = (
                f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
                f"UID={user};PWD={password};TrustServerCertificate=yes;"
            )
        else:
            conn_str = (
                f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
                f"Trusted_Connection=yes;TrustServerCertificate=yes;"
            )
        return pyodbc.connect(conn_str, timeout=30), None
    except Exception as ex:
        # 嘗試較舊驅動
        if "ODBC Driver 17" in driver:
            try:
                driver2 = "SQL Server"
                if user:
                    conn_str = (
                        f"DRIVER={{{driver2}}};SERVER={server};DATABASE={database};"
                        f"UID={user};PWD={password};"
                    )
                else:
                    conn_str = (
                        f"DRIVER={{{driver2}}};SERVER={server};DATABASE={database};"
                        f"Trusted_Connection=yes;"
                    )
                return pyodbc.connect(conn_str, timeout=30), None
            except Exception as ex2:
                return None, f"{ex}; fallback: {ex2}"
        return None, str(ex)


def _connect_mysql(spec: DbConnectionSpec) -> Tuple[Any, Optional[str]]:
    host = (spec.host or "localhost").strip() or "localhost"
    port = int(spec.port or 0) or 3306
    database = (spec.database or "").strip()
    user = (spec.user or "").strip()
    password = spec.password or ""
    # 優先 pymysql，其次 pyodbc
    try:
        import pymysql  # type: ignore

        conn = pymysql.connect(
            host=host,
            port=port,
            user=user or None,
            password=password,
            database=database or None,
            charset="utf8mb4",
            connect_timeout=30,
            autocommit=False,
        )
        return conn, None
    except ImportError:
        pass
    except Exception as ex:
        return None, str(ex)
    try:
        import pyodbc
    except ImportError:
        return None, "未安裝 pymysql 或 pyodbc，無法連線 MySQL。"
    driver = (spec.driver or "").strip() or "MySQL ODBC 8.0 Unicode Driver"
    try:
        conn_str = (
            f"DRIVER={{{driver}}};SERVER={host};PORT={port};DATABASE={database};"
            f"USER={user};PASSWORD={password};"
        )
        return pyodbc.connect(conn_str, timeout=30), None
    except Exception as ex:
        return None, str(ex)


def open_connection(spec: DbConnectionSpec) -> Tuple[Any, Optional[str]]:
    kind = spec.normalized_kind()
    if kind == DB_KIND_SQLITE:
        return _connect_sqlite(spec)
    if kind == DB_KIND_ACCESS:
        return _connect_access(spec)
    if kind == DB_KIND_SQLSERVER:
        return _connect_sqlserver(spec)
    if kind == DB_KIND_MYSQL:
        return _connect_mysql(spec)
    return None, f"不支援的資料庫類型：{spec.kind}"


def test_connection(spec: DbConnectionSpec) -> Tuple[bool, str]:
    conn, err = open_connection(spec)
    if err or conn is None:
        return False, err or "連線失敗。"
    try:
        conn.close()
    except Exception:
        pass
    return True, "連線成功。"


def execute_sql(
    spec: DbConnectionSpec,
    sql: str,
    *,
    limit: int = RUN_QUERY_RESULT_LIMIT,
) -> Tuple[Optional[SqlExecuteResult], Optional[str]]:
    safe, err = sanitize_sql(sql)
    if err or not safe:
        return None, err or "SQL 無效。"
    conn, cerr = open_connection(spec)
    if cerr or conn is None:
        return None, cerr or "連線失敗。"
    try:
        cur = conn.cursor()
        cur.execute(safe)
        if cur.description:
            cols = [str(d[0]) for d in cur.description]
            raw = cur.fetchmany(max(1, int(limit)))
            rows = [[_cell_str(v) for v in r] for r in raw]
            try:
                conn.commit()
            except Exception:
                pass
            return (
                SqlExecuteResult(
                    columns=cols,
                    rows=rows,
                    sql=safe,
                    total=len(rows),
                    rowcount=len(rows),
                    is_result_set=True,
                    message=f"查詢完成，共 {len(rows)} 筆。",
                ),
                None,
            )
        # DML
        try:
            rc = int(cur.rowcount if cur.rowcount is not None else -1)
        except Exception:
            rc = -1
        try:
            conn.commit()
        except Exception:
            pass
        msg = f"執行完成，影響 {rc} 筆。" if rc >= 0 else "執行完成。"
        return (
            SqlExecuteResult(
                columns=[],
                rows=[],
                sql=safe,
                total=0,
                rowcount=rc,
                is_result_set=False,
                message=msg,
            ),
            None,
        )
    except Exception as ex:
        try:
            conn.rollback()
        except Exception:
            pass
        return None, str(ex)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def filter_result_rows(
    columns: Sequence[str],
    rows: Sequence[Sequence[str]],
    keyword: str,
) -> List[List[str]]:
    kw = (keyword or "").strip().lower()
    if not kw:
        return [list(r) for r in rows]
    out: List[List[str]] = []
    for r in rows:
        cells = ["" if v is None else str(v) for v in r]
        if any(kw in c.lower() for c in cells):
            out.append(cells)
    return out


def save_run_query(
    base_dir: str,
    sys_mdb_path: str,
    *,
    sql: str,
    description: str = "",
    user_no: str = "",
    code: str = "",
) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    ok, err = ensure_run_query_infra(base_dir, sys_mdb_path)
    if not ok:
        return None, err
    cmd = (sql or "").strip()
    if not cmd:
        return None, "沒有可儲存的 SQL 指令。"

    data_path = resolve_run_query_data_path(base_dir)
    backend = get_backend_for_path(data_path)
    cmap = _col_map(backend, RUN_QUERY_TABLE)
    if not cmap:
        return None, "RUN_QUERY 資料表無法讀取。"

    qry_code = (code or "").strip() or (
        datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6].upper()
    )
    when = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    desc = (description or "").strip() or re.sub(r"\s+", " ", cmd)[:60]

    payload = {
        FIELD_CODE: qry_code,
        FIELD_DESC: desc,
        FIELD_COMMAND: cmd,
        FIELD_USER: str(user_no or "").strip(),
        FIELD_DATE: when,
    }
    fields: List[str] = []
    values: List[str] = []
    for logical, val in payload.items():
        col = cmap.get(logical.upper())
        if col:
            fields.append(col)
            values.append(val)
    if not fields:
        return None, "RUN_QUERY 無可寫入欄位。"
    if not backend.insert_one(RUN_QUERY_TABLE, fields, values):
        return None, getattr(backend, "last_error", "") or "儲存失敗。"
    return {
        "qry_code": qry_code,
        "qry_desc": desc,
        "qry_date": when,
        "do_proc": RUN_QUERY_DO_PROC,
    }, None


def export_query_result_xlsx(
    columns: Sequence[str],
    rows: Sequence[Sequence[str]],
    *,
    sheet_title: str = "QueryResult",
    filename_stem: str = "run_query",
) -> Tuple[bool, str, bytes]:
    try:
        from openpyxl import Workbook
    except Exception as ex:
        return False, f"無法載入 Excel 匯出元件：{ex}", b""
    wb = Workbook()
    ws = wb.active
    title = (sheet_title or "QueryResult").strip() or "QueryResult"
    ws.title = title[:31]
    headers = [str(c or "") for c in columns] or ["(no columns)"]
    ws.append(headers)
    for r in rows:
        ws.append([("" if v is None else str(v)) for v in r])
    for col in ws.columns:
        letter = col[0].column_letter
        max_len = max(len(str(c.value or "")) for c in col)
        ws.column_dimensions[letter].width = min(max(max_len + 2, 10), 40)
    bio = io.BytesIO()
    wb.save(bio)
    stem = re.sub(r"[^\w\-]+", "_", (filename_stem or "run_query").strip()) or "run_query"
    return True, f"{stem}.xlsx", bio.getvalue()


def default_company_sqlite_spec(base_dir: str, company_key: str) -> DbConnectionSpec:
    from core.db_factory import resolve_company_db_path

    co = (company_key or "").strip() or "GS"
    path = resolve_company_db_path(base_dir, co) or ""
    kind = DB_KIND_SQLITE
    if path.lower().endswith((".mdb", ".accdb")):
        kind = DB_KIND_ACCESS
    return DbConnectionSpec(kind=kind, path=path)
