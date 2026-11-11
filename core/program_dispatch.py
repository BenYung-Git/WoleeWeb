"""依 PROGRAM.STD_PROC 分派標準／非標準作業。"""
from __future__ import annotations

from typing import Optional

from core.data_import_service import DATA_IMPORT_PROC, is_data_import_program
from core.menu_loader import ProgramItem
from core.run_query_service import RUN_QUERY_DO_PROC, is_run_query_program


def is_standard_program(item: Optional[ProgramItem]) -> bool:
    """STD_PROC 為 True（或欄位不存在）時走標準 Grid 作業。"""
    if item is None:
        return True
    # RUNQUERY 一律走專用介面（即使 STD_PROC 誤標為 True）
    if is_run_query_program(getattr(item, "do_proc", "") or ""):
        return False
    return bool(getattr(item, "std_proc", True))


def non_standard_program_kind(do_proc: str) -> Optional[str]:
    """回傳已實作之非標準程序代號，未知則 None。"""
    if is_data_import_program(do_proc):
        return DATA_IMPORT_PROC
    if is_run_query_program(do_proc):
        return RUN_QUERY_DO_PROC
    return None
