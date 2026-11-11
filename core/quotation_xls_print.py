from __future__ import annotations

"""
報價單 Quotation.xls / Quotation.xlsx 列印：
- 範本檔名：Quotation.xls / Quotation.xlsx（與程式同目錄、reports/，或 WOLEE_QUOTATION_XLS_DIR）。
- 選用 quotation_xls_map.json（與程式同目錄）指定欄位→儲存格，例如：
  {"sheet": 1, "overflow_row": 40, "cells": {"QUOTE_NO": "D4", "CUST_NAME": "B8"}}
- 需本機安裝 Microsoft Excel，以及 pywin32。
- 可依「由/至編號」「由/至日期」篩選後多筆，逐筆複製範本送印。
"""

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# 與 Crystal 報價單路徑邏輯類似：程式目錄、reports、環境變數。
_QUOTATION_XLS_NAMES = (
    "Quotation.xlsx",
    "QUOTATION.xlsx",
    "quotation.xlsx",
    "Quotation.xls",
    "QUOTATION.xls",
    "quotation.xls",
)
_MAP_JSON = "quotation_xls_map.json"


def resolve_quotation_xls_path(base_dir: str) -> Optional[str]:
    """尋找 Quotation.xlsx/Quotation.xls；可設定 WOLEE_QUOTATION_XLS_DIR。"""
    extra = (os.environ.get("WOLEE_QUOTATION_XLS_DIR") or "").strip()
    candidates: List[str] = []
    if extra:
        for name in _QUOTATION_XLS_NAMES:
            candidates.append(os.path.join(extra, name))
    bd = os.path.abspath(base_dir or "")
    for name in _QUOTATION_XLS_NAMES:
        candidates.extend(
            [
                os.path.join(bd, name),
                os.path.join(bd, "templates", name),
                os.path.join(bd, "TEMPLATES", name),
                os.path.join(bd, "reports", name),
                os.path.join(bd, "Reports", name),
            ]
        )
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def _load_map_json(base_dir: str) -> Dict[str, Any]:
    p = os.path.join(os.path.abspath(base_dir or ""), _MAP_JSON)
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


@dataclass
class _QuotationMap:
    sheet: int  # 1-based Excel
    cells: Dict[str, str]  # UPPER field name -> "D4"
    overflow_row: int  # 未對應欄位由該列起寫入 A 欄名、B 欄值
    include_unmapped_fields: bool
    trx_start_row: int
    trx_max_rows: int
    trx_columns: Dict[str, str]  # 明細欄位 -> Excel 欄/範圍（如 "A"、"B:D"、"G:H"）


def _parse_map(base_dir: str) -> _QuotationMap:
    raw = _load_map_json(base_dir)
    cells_raw = raw.get("cells") if isinstance(raw.get("cells"), dict) else {}
    cells: Dict[str, str] = {}
    for k, v in cells_raw.items():
        if k is None or v is None:
            continue
        ku = str(k).strip().upper()
        addr = str(v).strip()
        if ku and addr:
            cells[ku] = addr
    sheet = raw.get("sheet", 1)
    try:
        sheet_i = int(sheet)
    except (TypeError, ValueError):
        sheet_i = 1
    if sheet_i < 1:
        sheet_i = 1
    overflow = raw.get("overflow_row", 35)
    try:
        orow = int(overflow)
    except (TypeError, ValueError):
        orow = 35
    if orow < 1:
        orow = 35
    include_unmapped_raw = raw.get("include_unmapped_fields", False)
    include_unmapped = str(include_unmapped_raw).strip().upper() in (
        "1",
        "TRUE",
        "Y",
        "YES",
    )
    trx_start_row = raw.get("trx_start_row", 18)
    trx_max_rows = raw.get("trx_max_rows", 15)
    try:
        trx_start_row_i = int(trx_start_row)
    except (TypeError, ValueError):
        trx_start_row_i = 18
    try:
        trx_max_rows_i = int(trx_max_rows)
    except (TypeError, ValueError):
        trx_max_rows_i = 15
    if trx_start_row_i < 1:
        trx_start_row_i = 18
    if trx_max_rows_i < 1:
        trx_max_rows_i = 15

    trx_cols_default: Dict[str, str] = {
        "ITEM_NO": "A",
        "DESCRIPTION": "B:D",
        "QTY": "E",
        "UNIT_PRICE": "F",
        "AMOUNT": "G:H",
    }
    trx_cols_in = raw.get("trx_columns")
    if isinstance(trx_cols_in, dict):
        for k, v in trx_cols_in.items():
            ku = str(k or "").strip().upper()
            vv = str(v or "").strip().upper()
            if ku and vv:
                trx_cols_default[ku] = vv

    return _QuotationMap(
        sheet=sheet_i,
        cells=cells,
        overflow_row=orow,
        include_unmapped_fields=include_unmapped,
        trx_start_row=trx_start_row_i,
        trx_max_rows=trx_max_rows_i,
        trx_columns=trx_cols_default,
    )


def _row_to_field_dict(physical_fields: List[str], row: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for i, name in enumerate(physical_fields):
        key = (name or "").strip().upper()
        if not key:
            continue
        val = str(row[i]).strip() if i < len(row) else ""
        out[key] = val
    return out


def _pick_trx_value(trx_data: Dict[str, str], logical_name: str, default: str = "") -> str:
    aliases: Dict[str, Tuple[str, ...]] = {
        "ITEM_NO": ("ITEM_NO", "SEQ", "LINE_NO"),
        "DESCRIPTION": ("DESCRIPTION", "DESC", "ITEM_DESC"),
        "QTY": ("QTY", "QUANTITY"),
        "UNIT_PRICE": ("UNIT_PRICE", "PRICE", "PRICE1"),
        "AMOUNT": ("AMOUNT", "TOTAL", "LINE_TOTAL"),
    }
    keys = aliases.get(logical_name, (logical_name,))
    for k in keys:
        v = trx_data.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return default


def _fill_trx_rows(
    ws: Any,
    qmap: _QuotationMap,
    trx_fields: Optional[List[str]],
    trx_rows: Optional[List[List[str]]],
) -> None:
    if not trx_fields or not trx_rows:
        return
    row_idx = qmap.trx_start_row
    max_rows = qmap.trx_max_rows
    for i, row in enumerate(trx_rows):
        if i >= max_rows:
            break
        data = _row_to_field_dict(trx_fields, row)
        item_no = _pick_trx_value(data, "ITEM_NO", str(i + 1))
        desc = _pick_trx_value(data, "DESCRIPTION", "")
        qty = _pick_trx_value(data, "QTY", "")
        unit_price = _pick_trx_value(data, "UNIT_PRICE", "")
        amount = _pick_trx_value(data, "AMOUNT", "")
        payload = {
            "ITEM_NO": item_no,
            "DESCRIPTION": desc,
            "QTY": qty,
            "UNIT_PRICE": unit_price,
            "AMOUNT": amount,
        }
        for k, v in payload.items():
            addr = qmap.trx_columns.get(k)
            if not addr:
                continue
            try:
                ws.Range(f"{addr}{row_idx}").Value = v
            except Exception:
                pass
        row_idx += 1


_TOKEN_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.\[\]%]+)\s*\}\}")


def _replace_template_tokens(
    ws: Any,
    physical_fields: List[str],
    row: List[str],
    trx_fields: Optional[List[str]],
    trx_rows: Optional[List[List[str]]],
) -> None:
    """
    直接替換 Excel 模板中的 {{FIELD}} / {{TRX.FIELD[n]}} token，
    讓 Quotation.xlsx 不依賴 map 也可填值。
    """
    header = _row_to_field_dict(physical_fields, row)
    trx_dict_rows: List[Dict[str, str]] = []
    if trx_fields and trx_rows:
        for tr in trx_rows:
            trx_dict_rows.append(_row_to_field_dict(trx_fields, tr))

    used = ws.UsedRange
    if used is None:
        return
    n_rows = int(getattr(used, "Rows", used).Count)
    n_cols = int(getattr(used, "Columns", used).Count)

    def _resolve_token(token: str) -> Optional[str]:
        t = (token or "").strip()
        if not t:
            return None
        up = t.upper()
        if up.startswith("TRX.") and "[" in up and up.endswith("]"):
            # 例：TRX.AMOUNT[0]
            try:
                body = up[4:]
                field = body[: body.index("[")]
                idx_text = body[body.index("[") + 1 : -1]
                idx = int(idx_text)
            except Exception:
                return None
            if idx < 0 or idx >= len(trx_dict_rows):
                return ""
            rec = trx_dict_rows[idx]
            return str(rec.get(field, ""))
        return str(header.get(up, ""))

    for r in range(1, n_rows + 1):
        for c in range(1, n_cols + 1):
            try:
                val = ws.Cells(r, c).Value
            except Exception:
                continue
            if not isinstance(val, str) or "{{" not in val:
                continue
            src = val

            def _sub(m: re.Match[str]) -> str:
                token = m.group(1)
                v = _resolve_token(token)
                return "" if v is None else v

            new_val = _TOKEN_RE.sub(_sub, src)
            if new_val != src:
                try:
                    ws.Cells(r, c).Value = new_val
                except Exception:
                    pass


def _fill_sheet(
    ws: Any,
    qmap: _QuotationMap,
    physical_fields: List[str],
    row: List[str],
    trx_fields: Optional[List[str]] = None,
    trx_rows: Optional[List[List[str]]] = None,
) -> None:
    data = _row_to_field_dict(physical_fields, row)
    mapped_keys: set = set()
    for fname, addr in qmap.cells.items():
        if fname not in data:
            continue
        try:
            ws.Range(addr).Value = data[fname]
        except Exception:
            try:
                ws.Range(addr).Value = str(data[fname])
            except Exception:
                pass
        mapped_keys.add(fname)

    if qmap.include_unmapped_fields and qmap.overflow_row > 0:
        idx_map = {(n or "").strip().upper(): n for n in physical_fields}
        r = qmap.overflow_row
        for fn_upper in sorted(data.keys()):
            if fn_upper in mapped_keys:
                continue
            label = idx_map.get(fn_upper, fn_upper)
            try:
                ws.Cells(r, 1).Value = label
                ws.Cells(r, 2).Value = data[fn_upper]
            except Exception:
                pass
            r += 1
    _fill_trx_rows(ws, qmap, trx_fields, trx_rows)
    _replace_template_tokens(ws, physical_fields, row, trx_fields, trx_rows)


def print_quotation_xls_batch(
    base_dir: str,
    physical_fields: List[str],
    rows: List[List[str]],
    trx_fields: Optional[List[str]] = None,
    trx_rows: Optional[List[List[str]]] = None,
    lang: str = "CHN",
) -> Tuple[bool, str]:
    """
    篩選後之多筆資料：逐筆以 Quotation.xls 範本填寫並送印（每筆一次 PrintOut）。
    """
    is_chn = (lang or "").strip().upper() == "CHN"
    if not rows:
        msg = "無資料可列印。" if is_chn else "Nothing to print."
        return False, msg

    tpl = resolve_quotation_xls_path(base_dir)
    if not tpl:
        msg = (
            "找不到 Quotation.xls。請放在程式目錄、reports 子目錄，或設定環境變數 WOLEE_QUOTATION_XLS_DIR。"
            if is_chn
            else "Quotation.xls not found. Place it in the app folder, reports/, or set WOLEE_QUOTATION_XLS_DIR."
        )
        return False, msg

    try:
        import win32com.client  # type: ignore[import-untyped]
    except ImportError:
        msg = (
            "列印 Quotation.xls 需要 pywin32（pip install pywin32）與 Microsoft Excel。"
            if is_chn
            else "Printing Quotation.xls requires pywin32 and Microsoft Excel."
        )
        return False, msg

    qmap = _parse_map(base_dir)
    tpl_name = os.path.basename(tpl)
    excel = None
    try:
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False

        for _idx, row in enumerate(rows):
            ext = os.path.splitext(tpl)[1] or ".xlsx"
            fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="wolee_quot_")
            os.close(fd)
            wb = None
            try:
                shutil.copy2(tpl, tmp_path)
                wb = excel.Workbooks.Open(tmp_path, ReadOnly=False)
                if wb.Sheets.Count < qmap.sheet:
                    return (
                        False,
                        (
                            f"quotation_xls_map.json 的 sheet={qmap.sheet} 超出工作表數量。"
                            if is_chn
                            else f"sheet={qmap.sheet} is out of range."
                        ),
                    )
                ws = wb.Sheets(qmap.sheet)
                _fill_sheet(ws, qmap, physical_fields, row, trx_fields, trx_rows)
                ws.PrintOut()
            finally:
                try:
                    if wb is not None:
                        wb.Close(SaveChanges=False)
                except Exception:
                    pass
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        n = len(rows)
        ok_msg = (
            f"已以 Quotation 模板列印 {n} 筆：{tpl_name}"
            if is_chn
            else f"Printed {n} quotation template sheet(s): {tpl_name}"
        )
        return True, ok_msg
    except Exception as e:  # noqa: BLE001
        detail = str(e)
        msg = (
            "無法以 Excel 列印 Quotation.xls。\n"
            "請確認已安裝 Microsoft Excel，且 Quotation.xls 未被其他程式鎖定。\n"
            f"詳情：{detail}"
            if is_chn
            else f"Could not print Quotation.xls via Excel.\nDetails: {detail}"
        )
        return False, msg
    finally:
        try:
            if excel is not None:
                excel.Quit()
        except Exception:
            pass


def print_quotation_xls(
    base_dir: str,
    physical_fields: List[str],
    row: List[str],
    trx_fields: Optional[List[str]] = None,
    trx_rows: Optional[List[List[str]]] = None,
    lang: str = "CHN",
) -> Tuple[bool, str]:
    """單筆列印（相容舊呼叫）。"""
    return print_quotation_xls_batch(
        base_dir, physical_fields, [row], trx_fields, trx_rows, lang
    )


def preview_quotation_xls(
    base_dir: str,
    physical_fields: List[str],
    row: List[str],
    trx_fields: Optional[List[str]] = None,
    trx_rows: Optional[List[List[str]]] = None,
    lang: str = "CHN",
) -> Tuple[bool, str]:
    """
    單筆預覽：以 Quotation.xlsx/Quotation.xls 套版後開啟 Excel 列印預覽。
    """
    is_chn = (lang or "").strip().upper() == "CHN"
    if not row:
        return (False, "無資料可預覽。" if is_chn else "Nothing to preview.")
    tpl = resolve_quotation_xls_path(base_dir)
    if not tpl:
        return (
            False,
            "找不到 Quotation.xlsx。請放在 templates/、程式目錄或 reports。"
            if is_chn
            else "Quotation.xlsx not found. Put it in templates/, app folder, or reports.",
        )
    try:
        import win32com.client  # type: ignore[import-untyped]
    except ImportError:
        return (
            False,
            "預覽 Quotation.xlsx 需要 pywin32 與 Microsoft Excel。"
            if is_chn
            else "Preview requires pywin32 and Microsoft Excel.",
        )

    ok, msg, _pdf = generate_quotation_pdf_from_template(
        base_dir, physical_fields, row, trx_fields, trx_rows, lang
    )
    return ok, msg


def generate_quotation_pdf_from_template(
    base_dir: str,
    physical_fields: List[str],
    row: List[str],
    trx_fields: Optional[List[str]] = None,
    trx_rows: Optional[List[List[str]]] = None,
    lang: str = "CHN",
) -> Tuple[bool, str, Optional[str]]:
    """
    由 Quotation.xlsx/Quotation.xls 模板生成單筆 PDF 報表，供預覽。
    回傳 (ok, msg, pdf_path)；ok=False 時 pdf_path 為 None。
    """
    is_chn = (lang or "").strip().upper() == "CHN"
    if not row:
        return (
            False,
            "無資料可預覽。" if is_chn else "Nothing to preview.",
            None,
        )
    tpl = resolve_quotation_xls_path(base_dir)
    if not tpl:
        return (
            False,
            "找不到 Quotation.xlsx。請放在 templates/、程式目錄或 reports。"
            if is_chn
            else "Quotation.xlsx not found. Put it in templates/, app folder, or reports.",
            None,
        )
    try:
        import win32com.client  # type: ignore[import-untyped]
    except ImportError:
        return (
            False,
            "預覽 Quotation 報表需要 pywin32 與 Microsoft Excel。"
            if is_chn
            else "Preview requires pywin32 and Microsoft Excel.",
            None,
        )

    qmap = _parse_map(base_dir)
    excel = None
    tmp_path = ""
    pdf_path = ""
    try:
        ext = os.path.splitext(tpl)[1] or ".xlsx"
        fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="wolee_quot_preview_")
        os.close(fd)
        shutil.copy2(tpl, tmp_path)
        fd2, pdf_path = tempfile.mkstemp(suffix=".pdf", prefix="wolee_quotation_report_")
        os.close(fd2)

        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        wb = excel.Workbooks.Open(tmp_path, ReadOnly=False)
        if wb.Sheets.Count < qmap.sheet:
            wb.Close(SaveChanges=False)
            return (
                False,
                f"quotation_xls_map.json 的 sheet={qmap.sheet} 超出工作表數量。"
                if is_chn
                else f"sheet={qmap.sheet} is out of range.",
                None,
            )
        ws = wb.Sheets(qmap.sheet)
        _fill_sheet(ws, qmap, physical_fields, row, trx_fields, trx_rows)
        # 0 = xlTypePDF
        wb.ExportAsFixedFormat(0, pdf_path)
        wb.Close(SaveChanges=False)
        return (
            True,
            "已生成 Quotation 報表預覽。"
            if is_chn
            else "Quotation report preview generated.",
            pdf_path,
        )
    except Exception as e:  # noqa: BLE001
        return (
            False,
            f"無法生成 Quotation 報表預覽：{e}"
            if is_chn
            else f"Could not generate quotation report preview: {e}",
            None,
        )
    finally:
        try:
            if excel is not None:
                excel.Quit()
        except Exception:
            pass
        try:
            if tmp_path:
                os.remove(tmp_path)
        except OSError:
            pass
