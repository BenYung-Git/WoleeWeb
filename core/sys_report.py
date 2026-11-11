from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from core.db_factory import get_backend_for_path


def _read_report_rows(path: str) -> List[Dict[str, Any]]:
    """
    以通用 backend 讀取 REPORT 全表。
    欄名保留資料庫原始大小寫，回傳 dict list。
    """
    backend = get_backend_for_path(path)
    cols, rows = backend.fetch_rows_sql("SELECT * FROM REPORT", limit=20000)
    if not rows:
        cols, rows = backend.fetch_rows_sql("SELECT * FROM [REPORT]", limit=20000)
    if not cols or not rows:
        return []
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(_normalize_row(cols, tuple(r)))
    return out


def _normalize_row(
    col_names: List[str], row: tuple
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for i, name in enumerate(col_names):
        key = (name or f"COL{i}").strip()
        if i < len(row):
            out[key] = row[i]
        else:
            out[key] = None
    return out


def _report_need_do_true(val: Any) -> bool:
    """NEED_DO 為假（0/FALSE/N 等）則不列入下拉。"""
    if val is None:
        return True
    s = str(val).strip().upper()
    if s in ("0", "FALSE", "F", "N", "NO"):
        return False
    return True


def _report_row_proc_name_upper(row: Dict[str, Any]) -> str:
    for k, v in row.items():
        if str(k).strip().upper() == "PROC_NAME":
            return str(v or "").strip().upper()
    return ""


def _report_row_need_do_value(row: Dict[str, Any]) -> Any:
    for k, v in row.items():
        if str(k).strip().upper() == "NEED_DO":
            return v
    return None


def _report_row_rpt_index(row: Dict[str, Any]) -> int:
    for k, v in row.items():
        if str(k).strip().upper() != "RPT_INDEX":
            continue
        try:
            return int(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0
    return 0


def _report_row_value_ci(row: Dict[str, Any], key_upper: str) -> str:
    for k, v in row.items():
        if str(k).strip().upper() == key_upper:
            return str(v or "").strip()
    return ""


def _report_row_dedupe_key(row: Dict[str, Any]) -> tuple[str, str, int, str, str, str]:
    """
    供 proc candidate 合併時去重：
    不能只靠 (PROC_NAME, RPT_INDEX)，否則多筆同 index 的報表會被吞掉。
    """
    return (
        _report_row_proc_name_upper(row),
        _report_row_value_ci(row, "RPT_PROC").upper(),
        _report_row_rpt_index(row),
        _report_row_value_ci(row, "RPT_FILE"),
        _report_row_value_ci(row, "CHN_TITLE"),
        _report_row_value_ci(row, "ENG_TITLE"),
    )


def fetch_report_rows_by_proc_candidates(
    sys_mdb_path: str, proc_names: List[str]
) -> List[Dict[str, Any]]:
    """
    依多個 PROC_NAME 候選值讀取 REPORT，合併去重後回傳。
    用於 DO_PROC / WORK_PROC / PROGRAM.PROC_NAME 可能不一致時。
    """
    seen: set[tuple[str, str, int, str, str, str]] = set()
    out: List[Dict[str, Any]] = []
    for proc in proc_names or []:
        proc_s = (proc or "").strip()
        if not proc_s:
            continue
        for row in fetch_report_rows_by_proc(sys_mdb_path, proc_s):
            key = _report_row_dedupe_key(row)
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
    out.sort(
        key=lambda rw: (
            _report_row_proc_name_upper(rw),
            _report_row_rpt_index(rw),
        )
    )
    return out


def fetch_report_rows_by_proc(
    sys_mdb_path: str, proc_name: str
) -> List[Dict[str, Any]]:
    """
    讀取 SYS_DATA 內 REPORT 表（表名大小寫不敏感嘗試），
    REPORT.PROC_NAME 與 PROGRAM.PROC_NAME 比對（不分大小寫）；
    傳入值通常為 PROGRAM.PROC_NAME，若資料庫無 PROC_NAME 欄則為 DO_PROC。
    回傳每筆為欄名→值；欄名保留資料庫原始名稱。
    """
    path = (sys_mdb_path or "").strip()
    proc = (proc_name or "").strip()
    if not path or not os.path.isfile(path) or not proc:
        return []
    proc_u = proc.upper()
    rows_out = []
    for rw in _read_report_rows(path):
        if _report_row_proc_name_upper(rw) != proc_u:
            continue
        if not _report_need_do_true(_report_row_need_do_value(rw)):
            continue
        rows_out.append(rw)
    rows_out.sort(
        key=lambda rw: (
            _report_row_proc_name_upper(rw),
            _report_row_rpt_index(rw),
        )
    )
    return rows_out


def report_entry_display_title(row: Dict[str, Any], lang: str) -> str:
    """依語系取 CHN_TITLE / ENG_TITLE；皆空則取第一個非 PROC_NAME 的文字欄。"""
    if lang == "CHN":
        t = row.get("CHN_TITLE") or row.get("chn_title")
        if t is not None and str(t).strip():
            return str(t).strip()
        t2 = row.get("ENG_TITLE") or row.get("eng_title")
        if t2 is not None and str(t2).strip():
            return str(t2).strip()
    else:
        t = row.get("ENG_TITLE") or row.get("eng_title")
        if t is not None and str(t).strip():
            return str(t).strip()
        t2 = row.get("CHN_TITLE") or row.get("chn_title")
        if t2 is not None and str(t2).strip():
            return str(t2).strip()
    skip = {"PROC_NAME", "proc_name"}
    for k, v in row.items():
        if k in skip:
            continue
        if v is not None and str(v).strip():
            return str(v).strip()
    return "Report"


def report_entry_rpt_path(row: Dict[str, Any]) -> Optional[str]:
    for key in (
        "RPT_FILE",
        "REPORT_FILE",
        "FILE_NAME",
        "FILENAME",
        "RPT_PATH",
        "REPORT_PATH",
        "PATH",
        "rpt_file",
        "report_file",
    ):
        v = row.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


def fetch_report_row_by_rpt_proc(
    sys_mdb_path: str, rpt_proc: str
) -> Optional[Dict[str, Any]]:
    """
    讀取 SYS_DATA.REPORT 中 RPT_PROC = 指定值（不分大小寫）的第一筆。
    """
    path = (sys_mdb_path or "").strip()
    proc = (rpt_proc or "").strip()
    if not path or not os.path.isfile(path) or not proc:
        return None
    proc_u = proc.upper()
    for row in _read_report_rows(path):
        v = ""
        for k, rv in row.items():
            if str(k).strip().upper() == "RPT_PROC":
                v = str(rv or "").strip().upper()
                break
        if v == proc_u:
            return row
    return None
