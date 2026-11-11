from __future__ import annotations

import os
from typing import List, Optional, Tuple

# Crystal Reports：依安裝版本不同，COM ProgID 可能有多種字串。
_QUOTATION_RPT_NAME = "PRNQUOTATION.RPT"
_CRYSTAL_PROG_IDS = (
    # 最常見（ActiveX Designer Runtime）
    "CRAXDRT.Application",
    "CRAXDRT.Application.1",
    "CRAXDRT.Application.115",
    # Designer/Runtime 常見替代字串（含版本/後綴）
    "CrystalDesignRunTime.Application",
    "CrystalDesignRunTime.Application.1",
    "CrystalDesignRuntime.Application",
    "CrystalDesignRuntime.Application.1",
    "CrystalRuntime.Application",
    "CrystalRuntime.Application.1",
    "CrystalRuntime.Application.115",
    # 其他常見（有些版本會註冊在這些命名）
    "CrystalReportsRuntime.Application",
    "CrystalReportsRuntime.Application.1",
    "CrystalReports.Application",
)


def _join_prog_attempts(attempts: List[Tuple[str, str]]) -> str:
    # 避免訊息過長但仍保留關鍵資訊（ProgID + error）
    parts: List[str] = []
    for pid, err in attempts:
        err_s = (err or "").strip()
        parts.append(f"{pid} -> {err_s}")
    return "\n".join(parts)


def resolve_quotation_report_path(base_dir: str) -> Optional[str]:
    """尋找 PRNQUOTATION.RPT；可設定環境變數 WOLEE_CRYSTAL_RPT_DIR 指定目錄。"""
    extra = (os.environ.get("WOLEE_CRYSTAL_RPT_DIR") or "").strip()
    candidates = []
    if extra:
        candidates.append(os.path.join(extra, _QUOTATION_RPT_NAME))
    bd = os.path.abspath(base_dir or "")
    candidates.extend(
        [
            os.path.join(bd, _QUOTATION_RPT_NAME),
            os.path.join(bd, "reports", _QUOTATION_RPT_NAME),
            os.path.join(bd, "Reports", _QUOTATION_RPT_NAME),
        ]
    )
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def _escape_crystal_string(value: str) -> str:
    return (value or "").replace("'", "''")


def _pick_quotation_key(
    table_name: str, physical_fields: List[str], row: List[str]
) -> Tuple[Optional[str], Optional[str]]:
    """回傳 (實體欄位名, 值)，供 SelectionFormula 使用。"""
    preferred = (
        "QUOTE_NO",
        "QUOTATION_NO",
        "QUOT_NO",
        "TX_KEY",
        "QUO_KEY",
        "QTY_KEY",
        "ID",
    )
    upper_names = [f.strip().upper() for f in physical_fields]
    for cand in preferred:
        try:
            idx = upper_names.index(cand)
        except ValueError:
            continue
        if idx < len(row):
            v = str(row[idx]).strip()
            if v:
                return physical_fields[idx], v
    if physical_fields and row:
        return physical_fields[0], str(row[0] or "").strip()
    return None, None


def _build_selection_formula(table_name: str, field: str, value: str) -> str:
    tbl = (table_name or "QUOTATION").strip()
    fld = (field or "").strip()
    val = _escape_crystal_string(value)
    # Access / Crystal 常見：{資料表.欄位} = '值'
    return f"{{{tbl}.{fld}}} = '{val}'"


def build_print_dialog_selection_formula(
    table_name: str,
    inv_field: Optional[str],
    inv_from: str,
    inv_to: str,
    date_field: Optional[str],
    date_from: Optional[Tuple[int, int, int]],
    date_to: Optional[Tuple[int, int, int]],
    use_inv: bool,
    use_date: bool,
) -> Optional[str]:
    """
    與列印對話框「由/至編號」「由/至日期」一致之 SelectionFormula。
    編號：字串比較（與 Grid 篩選相同）；日期：Crystal Date(y,m,d)（欄位須為日期/時間型別）。

    報表 .rpt 內資料庫欄位名稱需與程式之 WORK_FILE（table_name）及實體欄位名一致，
    即公式為 {WORK_FILE.欄位名}。
    """
    tbl = (table_name or "").strip()
    if not tbl:
        return None
    parts: List[str] = []

    if use_inv and inv_field:
        fi = (inv_from or "").strip()
        ti = (inv_to or "").strip()
        inv_f = inv_field.strip()
        if fi:
            parts.append(
                f"{{{tbl}.{inv_f}}} >= '{_escape_crystal_string(fi)}'"
            )
        if ti:
            parts.append(
                f"{{{tbl}.{inv_f}}} <= '{_escape_crystal_string(ti)}'"
            )

    if use_date and date_field:
        df_f = date_field.strip()
        if date_from is not None:
            y, m, d = date_from
            parts.append(f"{{{tbl}.{df_f}}} >= Date({y}, {m}, {d})")
        if date_to is not None:
            y, m, d = date_to
            parts.append(f"{{{tbl}.{df_f}}} <= Date({y}, {m}, {d})")

    if not parts:
        return None
    return " AND ".join(parts)


def build_crystal_selection_inv_range_only(
    table_name: str,
    inv_field: Optional[str],
    inv_from: str,
    inv_to: str,
) -> Optional[str]:
    """
    Crystal 列印僅依「由/至紀錄」篩選，不含日期條件（與資料清單篩選可不同）。
    """
    use_inv = bool(inv_field and ((inv_from or "").strip() or (inv_to or "").strip()))
    return build_print_dialog_selection_formula(
        table_name,
        inv_field,
        inv_from,
        inv_to,
        None,
        None,
        None,
        use_inv,
        False,
    )


def print_crystal_quotation(
    base_dir: str,
    table_name: str,
    physical_fields: List[str],
    row: List[str],
) -> Tuple[bool, str]:
    """
    以 Crystal Reports 列印報價單（PRNQUOTATION.RPT）。
    若本機已註冊 COM 列印引擎則直接 PrintOut；否則回傳錯誤說明。

    回傳 (成功與否, 訊息)。
    """
    try:
        import win32com.client  # type: ignore[import-untyped]
    except ImportError:
        return False, "列印報價單需安裝 pywin32（pip install pywin32）與 Crystal Runtime。"

    rpt = resolve_quotation_report_path(base_dir)
    if not rpt:
        return False, (
            f"找不到 {_QUOTATION_RPT_NAME}。"
            f"請放在程式目錄、reports 子目錄，或設定環境變數 WOLEE_CRYSTAL_RPT_DIR。"
        )

    field, value = _pick_quotation_key(table_name, physical_fields, row)
    if not field or not value:
        return False, "無法取得報價單鍵值欄位，請確認 Grid 已選取一筆且主鍵欄位有值。"

    sel = _build_selection_formula(table_name, field, value)
    last_err: Optional[Exception] = None
    attempts: List[Tuple[str, str]] = []

    for progid in _CRYSTAL_PROG_IDS:
        try:
            app = win32com.client.Dispatch(progid)
            rep = None
            try:
                rep = app.OpenReport(rpt, 1)
            except Exception:
                try:
                    rep = app.OpenReport(rpt)
                except Exception:
                    pass
            if rep is None:
                raise RuntimeError("OpenReport 失敗")

            try:
                rep.SelectionFormula = sel
            except Exception:
                pass

            try:
                rep.DiscardSavedData()
            except Exception:
                pass

            # False：視版本可能為「不顯示對話框」；若仍跳出 Crystal 對話框屬正常
            try:
                rep.PrintOut(False)
            except Exception:
                rep.PrintOut()

            return True, f"已透過 Crystal 列印報價單（{os.path.basename(rpt)}）\n條件：{sel}"
        except Exception as e:  # noqa: BLE001
            last_err = e
            attempts.append((progid, str(e)))
            continue

    detail = str(last_err) if last_err else "未知錯誤"
    return False, (
        "無法呼叫 Crystal Reports COM 列印。\n"
        "你可能只安裝了 Crystal Reports .NET Framework runtime engine；\n"
        "但程式需要的是可註冊 COM/ActiveX 的 Crystal Reports runtime（CRAXDRT/ProgID）。\n"
        "請確認已安裝與 RPT 相容的 Crystal Reports COM/ActiveX runtime，且 ProgID 可用。\n"
        f"詳情：{detail}\n\n嘗試過的 ProgID 錯誤明細：\n{_join_prog_attempts(attempts)}"
    )


def print_crystal_report_file(
    rpt_path: str, selection_formula: Optional[str] = None
) -> Tuple[bool, str]:
    """
    直接以 Crystal 開啟指定 .rpt 並 PrintOut。
    selection_formula 非空時設為 Report.SelectionFormula（與列印對話框篩選一致）。
    供 SYS_DATA.REPORT 內指定報表檔案時使用。
    """
    rpt = (rpt_path or "").strip()
    if not rpt or not os.path.isfile(rpt):
        return False, f"找不到報表檔：{rpt_path}"

    try:
        import win32com.client  # type: ignore[import-untyped]
    except ImportError:
        return False, "Crystal 列印需安裝 pywin32 與 Crystal Runtime。"

    last_err: Optional[Exception] = None
    attempts: List[Tuple[str, str]] = []
    for progid in _CRYSTAL_PROG_IDS:
        try:
            app = win32com.client.Dispatch(progid)
            rep = None
            try:
                rep = app.OpenReport(rpt, 1)
            except Exception:
                try:
                    rep = app.OpenReport(rpt)
                except Exception:
                    pass
            if rep is None:
                raise RuntimeError("OpenReport 失敗")
            if selection_formula and str(selection_formula).strip():
                try:
                    rep.SelectionFormula = str(selection_formula).strip()
                except Exception:
                    pass
            try:
                rep.DiscardSavedData()
            except Exception:
                pass
            try:
                rep.PrintOut(False)
            except Exception:
                rep.PrintOut()
            sf = (selection_formula or "").strip()
            if sf:
                return True, f"已透過 Crystal 列印：{os.path.basename(rpt)}\n條件：{sf}"
            return True, f"已透過 Crystal 列印：{os.path.basename(rpt)}"
        except Exception as e:  # noqa: BLE001
            last_err = e
            attempts.append((progid, str(e)))
            continue

    detail = str(last_err) if last_err else "未知錯誤"
    return False, (
        "無法呼叫 Crystal Reports 列印此報表。\n"
        "你可能只安裝了 Crystal Reports .NET Framework runtime engine；\n"
        "但程式需要的是可註冊 COM/ActiveX 的 Crystal Reports runtime（CRAXDRT/ProgID）。\n"
        f"詳情：{detail}\n\n嘗試過的 ProgID 錯誤明細：\n{_join_prog_attempts(attempts)}"
    )
