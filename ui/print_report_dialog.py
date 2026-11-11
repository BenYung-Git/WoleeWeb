from __future__ import annotations

import base64
import io
import math
import os
import re
import urllib.parse
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PyQt6.QtCore import QDate, QPointF, QSize, QSizeF, Qt, QTimer, QUrl, QRectF
from PyQt6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QGuiApplication,
    QPageLayout,
    QPainter,
    QTextDocument,
)
from PyQt6.QtPrintSupport import (
    QPrintDialog,
    QPrinter,
    QPrinterInfo,
    QPrintPreviewDialog,
    QPrintPreviewWidget,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCalendarWidget,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.data_dictionary import DataDictionary, LanguageCode, ReportColumnSpec
from core.display_format import (
    APP_DATE_QT_FORMAT,
    format_cell_display,
    format_date_display,
    format_numeric_display,
    guess_number_kind,
    is_boolean_data_type,
    is_date_data_type,
    is_date_field,
    is_numeric_data_type,
    is_string_data_type,
    normalize_boolean_yn,
    parse_qdate,
)
from core.db_backend import DbBackendBase
from core.sys_report import (
    fetch_report_row_by_rpt_proc,
    fetch_report_rows_by_proc,
    fetch_report_rows_by_proc_candidates,
    report_entry_display_title,
)
from core.quotation_html_print import render_quotation_html
from core.quotation_xls_print import (
    generate_quotation_pdf_from_template,
    print_quotation_xls,
)
from core.quotation1_xls_print import (
    generate_quotation1_pdf_from_template,
    print_quotation1_xls,
)
from core.invoice_xls_print import (
    generate_invoice_pdf_from_template,
    print_invoice_xls,
)

_INV_HINTS = (
    "INV_NO",
    "INVOICE",
    "INVOICE_NO",
    "INVNO",
    "BILL_NO",
    "DOC_NO",
    "VOUCHER",
    "發票",
)


def _guess_invoice_col(physical: Sequence[str]) -> Optional[int]:
    up = [p.strip().upper() for p in physical]
    for hint in _INV_HINTS:
        for i, name in enumerate(up):
            if hint in name or name.endswith(hint):
                return i
    for i, name in enumerate(up):
        if name == "NO" or name.endswith("_NO"):
            return i
    return None


def _guess_date_col(
    table_name: str, physical: Sequence[str], data_dict: DataDictionary
) -> Optional[int]:
    for i, fname in enumerate(physical):
        u = fname.upper()
        if "DATE" in u or u.endswith("_DT"):
            return i
        fmt = (data_dict.get_data_format(table_name, fname) or "").upper()
        if any(x in fmt for x in ("YYYY", "YY", "MM", "DD")):
            return i
    return None


def _parse_cell_date(
    text: str, qt_fmt: str
) -> Optional[QDate]:
    """與資料字典／Access 等來源一致，優先使用 parse_qdate 以支援日期時間字串。"""
    t = (text or "").strip()
    if not t:
        return None
    d0 = parse_qdate(t, qt_fmt or APP_DATE_QT_FORMAT)
    if d0 is not None:
        return QDate(d0.year, d0.month, d0.day)
    for pat in (qt_fmt, APP_DATE_QT_FORMAT, "yyyy/MM/dd", "yyyy-MM-dd", "dd/MM/yyyy", "M/d/yyyy"):
        if not pat:
            continue
        d2 = QDate.fromString(t, pat)
        if d2.isValid():
            return d2
    return None


def _cell_to_float(text: str) -> Optional[float]:
    s = (text or "").strip()
    if not s:
        return None
    s = s.replace(",", "")
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1].strip()
    for ch in ("NT$", "HK$", "$", "¥", "€", "£"):
        if s.upper().startswith(ch.upper()):
            s = s[len(ch) :].strip()
            break
    try:
        v = float(s)
        return -v if neg else v
    except ValueError:
        return None


def _build_specs_from_grid(
    table_name: str,
    grid_fields: Sequence[str],
    data_dict: DataDictionary,
    lang: LanguageCode,
) -> List[ReportColumnSpec]:
    return [
        ReportColumnSpec(
            physical_name=f,
            display_title=data_dict.get_title(table_name, f, lang),
            field_total=False,
        )
        for f in grid_fields
    ]


def _filter_rows(
    rows: List[List[str]],
    physical: Sequence[str],
    inv_i: Optional[int],
    date_i: Optional[int],
    date_qfmt: str,
    from_inv: str,
    to_inv: str,
    from_date: Optional[QDate],
    to_date: Optional[QDate],
    use_inv: bool,
    use_date: bool,
) -> List[List[str]]:
    out: List[List[str]] = []
    fi = (from_inv or "").strip()
    ti = (to_inv or "").strip()
    for rec in rows:
        if use_inv and inv_i is not None and 0 <= inv_i < len(rec):
            v = (rec[inv_i] or "").strip()
            if fi and v < fi:
                continue
            if ti and v > ti:
                continue
        if use_date and date_i is not None:
            if not (0 <= date_i < len(rec)):
                continue
            rd = _parse_cell_date(str(rec[date_i] or ""), date_qfmt)
            if rd is None or not rd.isValid():
                continue
            if from_date is not None and from_date.isValid() and rd < from_date:
                continue
            if to_date is not None and to_date.isValid() and rd > to_date:
                continue
        out.append(rec)
    return out


def _escape_html(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _report_column_align_right(field_name: str, data_type: str) -> bool:
    """
    報表欄對齊：文字／日期靠左；數字（金額、匯率、整數、百分比等）靠右。
    與 _format_report_value 規則一致。
    """
    if is_string_data_type(data_type) or is_boolean_data_type(data_type):
        return False
    if is_date_data_type(data_type) or is_date_field(field_name):
        return False
    if is_numeric_data_type(data_type):
        return True
    kind = guess_number_kind(field_name, "", data_type)
    if kind in ("amount", "rate", "percent", "int"):
        return True
    return False


# 資料清單欄數超過此值時，依欄切多頁／多工作表（HTML、PDF、XLSX、DOCX）。
LIST_PRINT_COLS_PER_PAGE = 11


def _finance_col_widths(field_names: Sequence[str]) -> List[str]:
    """
    FINANCE 報表欄寬：賬戶編號較短、賬戶名稱較長，金額欄均分其餘空間。
    """
    names = [str(n or "").strip().upper() for n in field_names]
    if not names:
        return []
    widths: List[Optional[float]] = [None] * len(names)
    for i, n in enumerate(names):
        if n in ("AC_KEY", "AC_NO", "KEY", "ACCOUNT", "ACCOUNT_NO"):
            widths[i] = 12.0
        elif n in ("AC_NAME", "NAME", "DESC", "DESCRIPTION"):
            widths[i] = 40.0
    fixed = sum(w for w in widths if w is not None)
    free_idx = [i for i, w in enumerate(widths) if w is None]
    remain = max(0.0, 100.0 - fixed)
    if free_idx:
        each = remain / len(free_idx)
        for i in free_idx:
            widths[i] = each
    elif fixed <= 0:
        each = 100.0 / len(names)
        widths = [each] * len(names)
    return [f"{float(w or 0):.2f}%" for w in widths]


def _html_colgroup(col_widths: Optional[Sequence[str]]) -> str:
    if not col_widths:
        return ""
    parts = []
    for w in col_widths:
        ww = str(w or "").strip()
        if ww:
            parts.append(f'<col style="width:{_escape_html(ww)};"/>')
        else:
            parts.append("<col/>")
    return f"<colgroup>{''.join(parts)}</colgroup>"


def _html_table_fragment(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    totals: Optional[Sequence[str]],
    right_align_cols: Optional[Sequence[int]] = None,
    col_widths: Optional[Sequence[str]] = None,
) -> str:
    """僅 <table>…</table>，供單頁或多欄分頁組裝。"""
    if not headers:
        return "<table border=\"1\" cellspacing=\"0\" cellpadding=\"4\" width=\"100%\"></table>"
    right_set = set(right_align_cols or [])
    colgroup = _html_colgroup(col_widths)
    th_parts: List[str] = []
    for i, h in enumerate(headers):
        ta = "right" if i in right_set else "left"
        th_parts.append(f'<th style="text-align:{ta};">{_escape_html(h)}</th>')
    th = "".join(th_parts)
    body_rows: List[str] = []
    for r in rows:
        cell_parts: List[str] = []
        for i, c in enumerate(r):
            ta = "right" if i in right_set else "left"
            cell_parts.append(f'<td style="text-align:{ta};">{_escape_html(str(c))}</td>')
        tds = "".join(cell_parts)
        body_rows.append(f"<tr>{tds}</tr>")
    total_row = ""
    if totals is not None:
        tr = list(totals)
        while len(tr) < len(headers):
            tr.append("")
        tr = tr[: len(headers)]
        tds = "".join(
            f'<td style="border-top:1px solid #000;border-bottom:3px double #000;text-align:{"right" if i in right_set else "left"};"><b>{_escape_html(str(c))}</b></td>'
            for i, c in enumerate(tr)
        )
        total_row = f"<tr>{tds}</tr>"
    return f"""<table border="1" cellspacing="0" cellpadding="4" width="100%" style="table-layout:fixed;">
{colgroup}
<thead><tr>{th}</tr></thead>
<tbody>{"".join(body_rows)}{total_row}</tbody>
</table>"""


def _html_styled_rows_fragment(
    headers: Sequence[str],
    styled_rows: Sequence[Tuple[str, Sequence[str]]],
    totals: Optional[Sequence[str]],
    right_align_cols: Optional[Sequence[int]] = None,
    col_widths: Optional[Sequence[str]] = None,
) -> str:
    """財務結構化報表：支援 group / detail / subtotal / summary / all_total 列樣式。"""
    if not headers:
        return "<table border=\"1\" cellspacing=\"0\" cellpadding=\"4\" width=\"100%\"></table>"
    right_set = set(right_align_cols or [])
    widths = [str(w or "").strip() for w in (col_widths or [])]
    while len(widths) < len(headers):
        widths.append("")
    widths = widths[: len(headers)]
    colgroup = _html_colgroup(widths if any(widths) else None)

    def _cell_width_style(i: int) -> str:
        w = widths[i] if i < len(widths) else ""
        return f"width:{w};" if w else ""

    th_parts: List[str] = []
    for i, h in enumerate(headers):
        ta = "right" if i in right_set else "left"
        th_parts.append(
            f'<th style="text-align:{ta};{_cell_width_style(i)}">{_escape_html(h)}</th>'
        )
    th = "".join(th_parts)
    body_rows: List[str] = []
    for kind, cells in styled_rows:
        row = list(cells)
        while len(row) < len(headers):
            row.append("")
        row = row[: len(headers)]
        k = str(kind or "").strip().lower()
        cell_parts: List[str] = []
        for i, c in enumerate(row):
            ta = "right" if i in right_set else "left"
            style = f"text-align:{ta};{_cell_width_style(i)}"
            text = _escape_html(str(c))
            if k == "group":
                style += "font-weight:bold;"
            elif k in ("subtotal", "summary"):
                style += "border-top:1px solid #000;font-weight:bold;"
                text = f"<b>{text}</b>"
            elif k == "all_total":
                style += (
                    "border-top:1px solid #000;border-bottom:3px double #000;font-weight:bold;"
                )
                text = f"<b>{text}</b>"
            cell_parts.append(f'<td style="{style}">{text}</td>')
        body_rows.append(f"<tr>{''.join(cell_parts)}</tr>")
    total_row = ""
    if totals is not None:
        tr = list(totals)
        while len(tr) < len(headers):
            tr.append("")
        tr = tr[: len(headers)]
        tds = "".join(
            f'<td style="border-top:1px solid #000;border-bottom:3px double #000;text-align:{"right" if i in right_set else "left"};{_cell_width_style(i)}"><b>{_escape_html(str(c))}</b></td>'
            for i, c in enumerate(tr)
        )
        total_row = f"<tr>{tds}</tr>"
    return f"""<table border="1" cellspacing="0" cellpadding="4" width="100%" style="table-layout:fixed;">
{colgroup}
<thead><tr>{th}</tr></thead>
<tbody>{"".join(body_rows)}{total_row}</tbody>
</table>"""


def _html_report(
    title: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    totals: Optional[Sequence[str]],
    right_align_cols: Optional[Sequence[int]] = None,
    header_center_html: Optional[str] = None,
    omit_title_block: bool = False,
    col_widths: Optional[Sequence[str]] = None,
) -> str:
    frag = _html_table_fragment(headers, rows, totals, right_align_cols, col_widths)
    if header_center_html:
        top = header_center_html
    elif omit_title_block:
        top = ""
    else:
        top = f'<h2 style="margin-bottom:8px;">{_escape_html(title)}</h2>'
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"/></head>
<body style="font-family: sans-serif;">
{top}
{frag}
</body></html>"""


def _html_group_report(
    title: str,
    headers: Sequence[str],
    body_rows: Sequence[Sequence[str]],
    group_total_rows: Sequence[Sequence[str]],
    grand_total_row: Optional[Sequence[str]],
) -> str:
    if not headers:
        return _html_report(title, [], [], None)
    th = "".join(f"<th>{_escape_html(h)}</th>" for h in headers)
    parts: List[str] = []
    for r in body_rows:
        tds = "".join(f"<td>{_escape_html(str(c))}</td>" for c in r)
        parts.append(f"<tr>{tds}</tr>")
    # 組別小計列：上方單線與明細區隔（GROUP 總數）
    for r in group_total_rows:
        cells = []
        for c in r:
            cells.append(
                f'<td style="border-top:1px solid #000;"><b>{_escape_html(str(c))}</b></td>'
            )
        parts.append(f"<tr>{''.join(cells)}</tr>")
    # 合計總數列：上方單線與組別區隔，底部雙線為全表結尾
    if grand_total_row is not None:
        cells = []
        for c in grand_total_row:
            cells.append(
                f'<td style="border-top:1px solid #000;border-bottom:3px double #000;"><b>{_escape_html(str(c))}</b></td>'
            )
        parts.append(f"<tr>{''.join(cells)}</tr>")
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"/></head>
<body style="font-family: sans-serif;">
<h2 style="margin-bottom:8px;">{_escape_html(title)}</h2>
<table border="1" cellspacing="0" cellpadding="4" width="100%">
<thead><tr>{th}</tr></thead>
<tbody>{''.join(parts)}</tbody>
</table>
</body></html>"""


def _chunk_report_columns(
    headers: Sequence[str],
    body: Sequence[Sequence[str]],
    totals: Optional[Sequence[str]],
    chunk_size: int,
) -> List[Tuple[List[str], List[List[str]], Optional[List[str]]]]:
    """將欄位切成每段最多 chunk_size 欄（列數不變）。"""
    nh = len(headers)
    if nh == 0 or nh <= chunk_size:
        return [
            (
                list(headers),
                [list(r) for r in body],
                list(totals) if totals is not None else None,
            )
        ]
    out: List[Tuple[List[str], List[List[str]], Optional[List[str]]]] = []
    for start in range(0, nh, chunk_size):
        end = min(start + chunk_size, nh)
        h = list(headers[start:end])
        b = [list(r[start:end]) for r in body]
        t: Optional[List[str]] = None
        if totals is not None:
            t = list(totals[start:end])
        out.append((h, b, t))
    return out


def _dict_get_ci(row: Dict[str, Any], key: str, default: Any = "") -> Any:
    """字典欄位讀取（不分大小寫）；用於 REPORT 欄位映射。"""
    if key in row:
        return row.get(key, default)
    ku = (key or "").strip().upper()
    if not ku:
        return default
    ku_canon = ku.replace("[", "").replace("]", "").replace("`", "").replace(" ", "").replace("_", "")
    for k, v in row.items():
        ks = str(k or "").strip().upper()
        if ks == ku:
            return v
        ks_canon = ks.replace("[", "").replace("]", "").replace("`", "").replace(" ", "").replace("_", "")
        if ks_canon == ku_canon:
            return v
    return default


def _dict_row_key_canonical(name: str) -> str:
    """Access 欄名可能含 []、`、空白、底線；正規化後比對 GROUP_SUM 等。"""
    s = str(name or "").strip().upper()
    for ch in ("[", "]", "`", "\"", "'", "\ufeff"):
        s = s.replace(ch, "")
    return s.replace(" ", "").replace("_", "").replace("-", "")


def _dict_get_report_group_sum(row: Dict[str, Any]) -> str:
    """
    REPORT.GROUP_SUM：欄名在 Access 可能為 GROUP_SUM、[GROUP_SUM]、GROUP SUM、GroupSum 等。
    """
    if not isinstance(row, dict):
        return ""
    for key in ("GROUP_SUM", "GROUP SUM", "GROUPSUM", "Group_Sum", "GroupSum", "Groupsum"):
        v = _dict_get_ci(row, key, "")
        s = str(v or "").strip().strip("\ufeff\u200b\u00a0")
        if s:
            return s
    want = "GROUPSUM"
    for k, v in row.items():
        if _dict_row_key_canonical(str(k)) != want:
            continue
        s = str(v or "").strip().strip("\ufeff\u200b\u00a0")
        if s:
            return s
    return ""


def _fetch_sys_co_company_name(user_mdb_path: str, co_key: str) -> str:
    """
    自 USER_DATA 等資料庫之 sys_co 依 CO_KEY 讀取 NAME（欄名不分大小寫）。
    """
    path = (user_mdb_path or "").strip()
    ck = (co_key or "").strip()
    if not path or not os.path.isfile(path) or not ck:
        return ""
    try:
        import pyodbc
    except ImportError:
        return ""
    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        rf"DBQ={path};"
    )
    for tbl in ("[sys_co]", "sys_co", "[SYS_CO]", "SYS_CO"):
        try:
            conn = pyodbc.connect(conn_str)
            try:
                cur = conn.cursor()
                cur.execute(
                    f"SELECT TOP 1 * FROM {tbl} WHERE UCase([CO_KEY]) = UCase(?)",
                    (ck,),
                )
                row = cur.fetchone()
                if row is None:
                    continue
                desc = cur.description or ()
                col_names = [str(d[0]) for d in desc]
                dct: Dict[str, Any] = {
                    col_names[i]: row[i] for i in range(min(len(col_names), len(row)))
                }
                nm = _dict_get_ci(dct, "NAME", "")
                if str(nm or "").strip():
                    return str(nm).strip()
            finally:
                conn.close()
        except Exception:
            continue
    return ""


def _html_report_column_pages(
    title: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    totals: Optional[Sequence[str]],
    cols_per_page: int,
    lang: str,
    right_align_cols: Optional[Sequence[int]] = None,
    header_center_html: Optional[str] = None,
    omit_title_block: bool = False,
) -> str:
    """
    欄位數 > cols_per_page 時，每頁最多 cols_per_page 欄；後續區塊以分頁樣式緊接下一頁開頭（列印／預覽）。
    """
    chunks = _chunk_report_columns(headers, rows, totals, cols_per_page)
    if len(chunks) <= 1:
        return _html_report(
            title,
            headers,
            rows,
            totals,
            right_align_cols,
            header_center_html,
            omit_title_block,
        )
    is_chn = (lang or "").strip().upper() == "CHN"
    parts: List[str] = []
    offset = 0
    for i, (h, b, t) in enumerate(chunks):
        end = offset + len(h)
        right_sub: Optional[List[int]] = None
        if right_align_cols:
            right_sub = [ri - offset for ri in right_align_cols if offset <= ri < end]
        tbl = _html_table_fragment(h, b, t, right_sub)
        if i > 0:
            # 僅插入一次分頁分隔，避免 Qt HTML 對 before/after 重複套用造成跳頁。
            parts.append(
                '<div style="height:0; line-height:0; page-break-before: always;"></div>'
            )
        if i == 0:
            if header_center_html:
                head = header_center_html
            elif omit_title_block:
                head = ""
            else:
                head = f'<h2 style="margin-bottom:8px;">{_escape_html(title)}</h2>'
            parts.append(f"<div>{head}{tbl}</div>")
        else:
            lab = f"欄 {offset + 1}–{end}" if is_chn else f"Columns {offset + 1}-{end}"
            parts.append(
                f'<div><h3 style="margin-top:0;margin-bottom:6px;text-align:center;">{_escape_html(lab)}</h3>{tbl}</div>'
            )
        offset = end
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"/></head>
<body style="font-family: sans-serif;">
{"".join(parts)}
</body></html>"""


class PrintReportDialog(QDialog):
    """
    按「列印」後檢查 SYS_DATA.REPORT（REPORT.PROC_NAME = PROGRAM.PROC_NAME；無 PROC_NAME 欄時比對 DO_PROC）。

    (a) 無相符 REPORT 紀錄：提示「沒有報表可列印」並關閉，不進入列印介面。

    (b) 有 REPORT 紀錄：讀 NEED_DO、RPT_PROC、RPT_FILE、RPT_CO 等（列為 dict）；NEED_DO 為假者不列入；
        依 PROC_NAME、RPT_INDEX 排序；依語系將 CHN_TITLE／ENG_TITLE 加入「報表」下拉（userData 為整筆 REPORT）。
        列印介面：印表機、報表、由／至紀錄（GRID 選取）、由／至日期（空白表全部，可按 × 清空）、
        預覽／列印／匯出 PDF·XLSX·DOCX／電郵／離開。
        清單／GROUP／RPT_SQL 等所有報表：凡使用者輸入「由/至編號」或「由/至日期」條件，皆據以篩選後列印；
        日期欄若主檔未偵測到，會自目前資料列推斷可解析為 yyyy/MM/dd 的欄位。
        清單預覽／表格列印：依主編號欄（與由／至紀錄同欄）字串升冪；欄數 >8 橫印、其餘直印；
        欄數 >11 時 HTML 以每 11 欄分段換頁（列多時同組仍可能跨多頁，可讀性優先）。
        RPT_TYPE=GROUP（或「組合明細」）：依 REPORT 之 GROUP_BY、RPT_FIELD、FIELD_LABEL、GROUP_SUM；
        標題列優先 FIELD_LABEL；組頭為 GROUP_BY 各欄值（以「 - 」分隔）；明細為 RPT_FIELD；
        GROUP 小計與表尾合計僅針對 GROUP_SUM 指定欄位累加並顯示數字；GROUP_SUM 空白（或清理後無欄名）或對不到欄位時不顯示小計與合計列；
        非 GROUP_SUM 欄位在 GROUP 總數／合計總數列一律留白。
        小計列之總數欄上方單線，合計列底雙線。

    由／至編號：WorkPage 依 PROGRAM.KEY_CODE 對應實體欄帶入預設（必要時可退回 TX_KEY）；RPT_TYPE 為 LIST／清單時預設空白；
    為單據類時預設帶入該欄目前列值；其餘類型預設空白。
    由／至日期：LIST 與單據類預設空白（空白表全部）；其餘預設本月第一日／最後一日；
    非 LIST 且非單據時，若「由日期」之年／月變更，「至日期」自動改為該月最後一日。
    非單據類報表：列印／預覽／匯出 PDF 時每頁頂部置中繪製頁首（公司名稱自 sys_co.NAME、報表名稱、由/至編號與日期條件）；
    RPT_TYPE 為單據者不在每頁重繪頁首（內容仍保留原 HTML 標題）。每頁底部置中顯示「頁數: 目前頁/總頁數」。

    QUOTATION：列印可走 Excel 模板（DO_PRNQUOTATION / DO_PRNQUOTATION1）。
    """

    def __init__(
        self,
        parent: Optional[QWidget],
        lang: LanguageCode,
        table_name: str,
        physical_fields: List[str],
        grid_field_names: List[str],
        data_dict: DataDictionary,
        backend: Optional[DbBackendBase],
        report_proc_name: str,
        sys_mdb_path: str,
        app_base_dir: Optional[str],
        menu_item_title: str = "",
        quotation_xls_mode: bool = False,
        quotation_current_row: Optional[List[str]] = None,
        inv_column_index: Optional[int] = None,
        default_inv_text: Optional[str] = None,
        user_data_mdb_path: str = "",
        company_co_key: str = "",
        auto_list_on_empty: bool = True,
        report_proc_candidates: Optional[List[str]] = None,
    ) -> None:
        super().__init__(parent)
        self.lang: LanguageCode = lang
        self.table_name = table_name
        self.physical_fields = list(physical_fields)
        self.grid_field_names = list(grid_field_names)
        self.data_dict = data_dict
        self.backend = backend
        self.report_proc_name = (report_proc_name or "").strip()
        self.sys_mdb_path = sys_mdb_path
        self.app_base_dir = (app_base_dir or "").strip() or None
        self.menu_item_title = (menu_item_title or "").strip()
        # QUOTATION：若有傳 current row，僅列印該筆。
        self._quotation_xls_mode = bool(quotation_xls_mode)
        self._quotation_current_row = (
            list(quotation_current_row) if quotation_current_row is not None else None
        )
        # 開啟對話框時由 WorkPage 依 PROGRAM.KEY_CODE 帶入之「由/至編號」預設（單據類報表用）。
        self._default_inv_snapshot = (default_inv_text or "").strip()
        self._user_data_mdb_path = (user_data_mdb_path or "").strip()
        self._company_co_key = (company_co_key or "").strip()
        nm = _fetch_sys_co_company_name(self._user_data_mdb_path, self._company_co_key)
        if not nm:
            nm = _fetch_sys_co_company_name(self.sys_mdb_path, self._company_co_key)
        self._company_display_name = nm
        # RPT_SQL 執行期 token -> physical_fields index 對照（每次取數即時重建）
        self._runtime_token_index_map: Dict[str, int] = {}
        # 執行期動態欄位索引 -> 欄位名稱（供格式與標題回退）
        self._runtime_index_field_name: Dict[int, str] = {}
        # 嚴格模式映射錯誤清單
        self._strict_mapping_errors: List[str] = []
        # 最近一次 RPT_SQL 查詢欄位（供嚴格模式錯誤頁顯示）
        self._last_sql_columns: List[str] = []
        # RPT_SQL：mapped 列 target_i -> SQL 結果欄索引（供 GROUP_SUM 與 SQL 欄名對應）
        self._sql_src_index_by_target: Dict[int, int] = {}

        # 開啟時自 REPORT 讀入欄位至 _report_entries；選取變更時再以 RPT_PROC 即時回查同步。
        proc_candidates = list(report_proc_candidates or [])
        seen_proc = {p.strip().upper() for p in proc_candidates if (p or "").strip()}
        if self.report_proc_name:
            key = self.report_proc_name.upper()
            if key not in seen_proc:
                proc_candidates.insert(0, self.report_proc_name)
        if proc_candidates:
            rows_for_combo = fetch_report_rows_by_proc_candidates(
                sys_mdb_path, proc_candidates
            )
        else:
            rows_for_combo = fetch_report_rows_by_proc(
                sys_mdb_path, self.report_proc_name
            )
        self._report_entries: List[Dict[str, Any]] = []
        for row in rows_for_combo:
            self._report_entries.append(
                {
                    "PROC_NAME": _dict_get_ci(row, "PROC_NAME", ""),
                    "RPT_INDEX": _dict_get_ci(row, "RPT_INDEX", 0),
                    "CHN_TITLE": _dict_get_ci(row, "CHN_TITLE", ""),
                    "ENG_TITLE": _dict_get_ci(row, "ENG_TITLE", ""),
                    "NEED_DO": _dict_get_ci(row, "NEED_DO", True),
                    "RPT_PROC": _dict_get_ci(row, "RPT_PROC", ""),
                    "RPT_TYPE": _dict_get_ci(row, "RPT_TYPE", ""),
                    "GROUP_BY": _dict_get_ci(row, "GROUP_BY", ""),
                    "RPT_FILE": _dict_get_ci(row, "RPT_FILE", ""),
                    "RPT_FIELD": str(_dict_get_ci(row, "RPT_FIELD", "") or "").strip(),
                    "RPT_CO": _dict_get_ci(row, "RPT_CO", ""),
                    "RPT_SQL": _dict_get_ci(row, "RPT_SQL", ""),
                    "FIELD_LABEL": _dict_get_ci(row, "FIELD_LABEL", ""),
                    "GROUP_SUM": _dict_get_report_group_sum(row),
                    "_raw": row,
                }
            )
        self._no_report = len(self._report_entries) == 0
        self._specs_builtin: List[ReportColumnSpec] = data_dict.report_column_specs(
            table_name, physical_fields, lang
        )
        if not self._specs_builtin:
            self._specs_builtin = _build_specs_from_grid(
                table_name, grid_field_names, data_dict, lang
            )

        self._inv_i = _guess_invoice_col(physical_fields)
        if (
            inv_column_index is not None
            and 0 <= inv_column_index < len(self.physical_fields)
        ):
            self._inv_i = inv_column_index
        self._date_i = _guess_date_col(table_name, physical_fields, data_dict)

        t = "列印報表" if lang == "CHN" else "Print Report"
        self.setWindowTitle(t)
        self.resize(520, 420)
        if self._no_report:
            self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)

        from ui.work_page import apply_work_action_button_style

        self._apply_btn_style = apply_work_action_button_style

        main = QVBoxLayout(self)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        r = 0

        lp = QLabel("印表機:" if lang == "CHN" else "Printer:")
        self._cmb_printer = QComboBox()
        for name in QPrinterInfo.availablePrinterNames():
            self._cmb_printer.addItem(name)
        def_printer = QPrinterInfo.defaultPrinter().printerName()
        idx = self._cmb_printer.findText(def_printer)
        if idx >= 0:
            self._cmb_printer.setCurrentIndex(idx)
        grid.addWidget(lp, r, 0)
        grid.addWidget(self._cmb_printer, r, 1)
        r += 1

        lr = QLabel("報表:" if lang == "CHN" else "Report:")
        self._cmb_report = QComboBox()
        if self._no_report:
            self._cmb_report.addItem("資料清單" if lang == "CHN" else "Data list", None)
        else:
            for ent in self._report_entries:
                title = str(ent.get("CHN_TITLE" if lang == "CHN" else "ENG_TITLE") or "").strip()
                if not title:
                    raw = ent.get("_raw")
                    if isinstance(raw, dict):
                        title = report_entry_display_title(raw, lang)
                if not title:
                    title = "Report"
                self._cmb_report.addItem(title, ent)
        grid.addWidget(lr, r, 0)
        grid.addWidget(self._cmb_report, r, 1)
        r += 1

        no_label = self._doc_no_label()
        li1 = QLabel(
            f"由{no_label}編號:" if lang == "CHN" else f"From {no_label} no.:"
        )
        li2 = QLabel(
            f"至{no_label}編號:" if lang == "CHN" else f"To {no_label} no.:"
        )
        self._ed_inv_from = QLineEdit()
        self._ed_inv_to = QLineEdit()
        self._btn_pick_inv_from = QPushButton("..." if lang == "CHN" else "...")
        self._btn_pick_inv_to = QPushButton("..." if lang == "CHN" else "...")
        self._btn_pick_inv_from.setFixedWidth(34)
        self._btn_pick_inv_to.setFixedWidth(34)
        self._btn_pick_inv_from.clicked.connect(
            lambda: self._pick_doc_no_into(self._ed_inv_from)
        )
        self._btn_pick_inv_to.clicked.connect(
            lambda: self._pick_doc_no_into(self._ed_inv_to)
        )
        inv_from_row = QWidget()
        inv_from_lay = QHBoxLayout(inv_from_row)
        inv_from_lay.setContentsMargins(0, 0, 0, 0)
        inv_from_lay.setSpacing(4)
        inv_from_lay.addWidget(self._ed_inv_from)
        inv_from_lay.addWidget(self._btn_pick_inv_from)

        inv_to_row = QWidget()
        inv_to_lay = QHBoxLayout(inv_to_row)
        inv_to_lay.setContentsMargins(0, 0, 0, 0)
        inv_to_lay.setSpacing(4)
        inv_to_lay.addWidget(self._ed_inv_to)
        inv_to_lay.addWidget(self._btn_pick_inv_to)
        dv = (default_inv_text or "").strip()
        if dv:
            self._ed_inv_from.setText(dv)
            self._ed_inv_to.setText(dv)
        grid.addWidget(li1, r, 0)
        grid.addWidget(inv_from_row, r, 1)
        r += 1
        grid.addWidget(li2, r, 0)
        grid.addWidget(inv_to_row, r, 1)
        r += 1

        ld1 = QLabel("由日期:" if lang == "CHN" else "From date:")
        ld2 = QLabel("至日期:" if lang == "CHN" else "To date:")
        self._ed_date_from = QLineEdit()
        self._ed_date_to = QLineEdit()
        self._ed_date_from.setPlaceholderText("yyyy/MM/dd")
        self._ed_date_to.setPlaceholderText("yyyy/MM/dd")
        self._btn_pick_date_from = QPushButton("...")
        self._btn_pick_date_to = QPushButton("...")
        self._btn_pick_date_from.setFixedWidth(34)
        self._btn_pick_date_to.setFixedWidth(34)
        self._btn_pick_date_from.clicked.connect(
            lambda: self._pick_date_into(self._ed_date_from)
        )
        self._btn_pick_date_to.clicked.connect(
            lambda: self._pick_date_into(self._ed_date_to)
        )
        self._btn_clear_date_from = QPushButton("×")
        self._btn_clear_date_to = QPushButton("×")
        self._btn_clear_date_from.setFixedWidth(28)
        self._btn_clear_date_to.setFixedWidth(28)
        self._btn_clear_date_from.clicked.connect(self._clear_print_date_from)
        self._btn_clear_date_to.clicked.connect(lambda: self._ed_date_to.clear())
        date_from_row = QWidget()
        date_from_lay = QHBoxLayout(date_from_row)
        date_from_lay.setContentsMargins(0, 0, 0, 0)
        date_from_lay.setSpacing(4)
        date_from_lay.addWidget(self._ed_date_from)
        date_from_lay.addWidget(self._btn_pick_date_from)
        date_from_lay.addWidget(self._btn_clear_date_from)
        date_to_row = QWidget()
        date_to_lay = QHBoxLayout(date_to_row)
        date_to_lay.setContentsMargins(0, 0, 0, 0)
        date_to_lay.setSpacing(4)
        date_to_lay.addWidget(self._ed_date_to)
        date_to_lay.addWidget(self._btn_pick_date_to)
        date_to_lay.addWidget(self._btn_clear_date_to)
        self._cmb_report.currentIndexChanged.connect(self._on_report_changed)
        grid.addWidget(ld1, r, 0)
        grid.addWidget(date_from_row, r, 1)
        r += 1
        grid.addWidget(ld2, r, 0)
        grid.addWidget(date_to_row, r, 1)
        r += 1

        # 「由日期」年/月變更時（非 LIST、非單據）：「至日期」自動改為該月最後一日。
        self._print_date_from_ym: Optional[Tuple[int, int]] = None
        self._ed_date_from.textChanged.connect(self._on_print_date_from_changed)

        main.addLayout(grid)

        if not self._no_report:
            self._apply_print_defaults_for_current_report(force=True)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        def mk(txt: str) -> QPushButton:
            b = QPushButton(txt)
            self._apply_btn_style(b)
            return b

        self._btn_preview = mk("預覽" if lang == "CHN" else "Preview")
        self._btn_print = mk("列印" if lang == "CHN" else "Print")
        self._btn_pdf = mk("匯出 PDF" if lang == "CHN" else "Export PDF")
        self._btn_xlsx = mk("匯出 XLSX" if lang == "CHN" else "Export XLSX")
        self._btn_docx = mk("匯出 DOCX" if lang == "CHN" else "Export DOCX")
        self._btn_mail = mk("電郵" if lang == "CHN" else "Email")
        self._btn_exit = mk("離開" if lang == "CHN" else "Exit")

        self._btn_preview.clicked.connect(self._on_preview)
        self._btn_print.clicked.connect(self._on_print)
        self._btn_pdf.clicked.connect(self._on_export_pdf)
        self._btn_xlsx.clicked.connect(self._on_export_xlsx)
        self._btn_docx.clicked.connect(self._on_export_docx)
        self._btn_mail.clicked.connect(self._on_email)
        self._btn_exit.clicked.connect(self.reject)

        for b in (
            self._btn_preview,
            self._btn_print,
            self._btn_pdf,
            self._btn_xlsx,
            self._btn_docx,
            self._btn_mail,
            self._btn_exit,
        ):
            btn_row.addWidget(b)
        main.addLayout(btn_row)

        if self._no_report and auto_list_on_empty:
            QTimer.singleShot(0, self._run_list_only_preview_then_close)

    def _run_list_only_preview_then_close(self) -> None:
        """PROC_NAME 無 REPORT 設定時：不顯示列印介面，直接開資料清單預覽。"""
        try:
            QMessageBox.information(
                self,
                "列印" if self.lang == "CHN" else "Print",
                "沒有可列印的報表 !\nNo Report Print !",
            )
            self._on_preview()
        finally:
            self.reject()

    def _doc_no_label(self) -> str:
        """
        優先使用 MENUITEM 標籤；無則退回主單據編號欄位推斷：
        例如「發票」「送貨單」「報價單」。
        """
        if self.menu_item_title:
            return self.menu_item_title
        if self._inv_i is None or not (0 <= self._inv_i < len(self.physical_fields)):
            return "記錄" if self.lang == "CHN" else "record"
        fname = self.physical_fields[self._inv_i]
        title = (self.data_dict.get_title(self.table_name, fname, self.lang) or "").strip()
        if not title:
            return "記錄" if self.lang == "CHN" else "record"
        up = title.upper()
        for suffix in ("編號", "#", "NO.", "NO", "_NO", "-NO"):
            if title.endswith(suffix) or up.endswith(suffix):
                title = title[: -len(suffix)].strip()
                break
        return title or ("記錄" if self.lang == "CHN" else "record")

    def _clear_print_date_from(self) -> None:
        """清除由日期時一併清除至日期與月份追蹤。"""
        self._ed_date_from.clear()
        self._print_date_from_ym = None
        self._ed_date_to.blockSignals(True)
        self._ed_date_to.clear()
        self._ed_date_to.blockSignals(False)

    def _on_print_date_from_changed(self, _text: str) -> None:
        if self._selected_report_is_list() or self._selected_report_is_document():
            return
        d = self._parse_user_date_text(self._ed_date_from.text())
        if d is None or not d.isValid():
            self._print_date_from_ym = None
            return
        ym = (d.year(), d.month())
        if ym == self._print_date_from_ym:
            return
        self._print_date_from_ym = ym
        d_first = QDate(d.year(), d.month(), 1)
        last = QDate(d.year(), d.month(), d_first.daysInMonth())
        self._ed_date_to.blockSignals(True)
        self._set_date_text(self._ed_date_to, last)
        self._ed_date_to.blockSignals(False)

    def _sync_print_date_from_ym_from_field(self) -> None:
        d = self._parse_user_date_text(self._ed_date_from.text())
        if d is None or not d.isValid():
            self._print_date_from_ym = None
        else:
            self._print_date_from_ym = (d.year(), d.month())

    def _apply_print_defaults_for_current_report(self, force: bool = False) -> None:
        """
        依目前選取之 REPORT（RPT_TYPE）設定「由/至編號」「由/至日期」預設。
        force 保留供呼叫端語意一致（皆為切換報表或開啟時重設）。
        """
        _ = force
        if self._no_report:
            return
        self._refresh_selected_report_entry_from_db()
        is_list = self._selected_report_is_list()
        is_doc = self._selected_report_is_document()
        self._ed_inv_from.blockSignals(True)
        self._ed_inv_to.blockSignals(True)
        self._ed_date_from.blockSignals(True)
        self._ed_date_to.blockSignals(True)
        try:
            if is_list:
                self._ed_inv_from.clear()
                self._ed_inv_to.clear()
                self._ed_date_from.clear()
                self._ed_date_to.clear()
            elif is_doc:
                dv = self._default_inv_snapshot
                if dv:
                    self._ed_inv_from.setText(dv)
                    self._ed_inv_to.setText(dv)
                else:
                    self._ed_inv_from.clear()
                    self._ed_inv_to.clear()
                self._ed_date_from.clear()
                self._ed_date_to.clear()
            else:
                self._ed_inv_from.clear()
                self._ed_inv_to.clear()
                today = QDate.currentDate()
                d_first = QDate(today.year(), today.month(), 1)
                d_last = QDate(today.year(), today.month(), d_first.daysInMonth())
                self._set_date_text(self._ed_date_from, d_first)
                self._set_date_text(self._ed_date_to, d_last)
        finally:
            self._ed_inv_from.blockSignals(False)
            self._ed_inv_to.blockSignals(False)
            self._ed_date_from.blockSignals(False)
            self._ed_date_to.blockSignals(False)
        self._sync_print_date_from_ym_from_field()

    def _selected_report_is_document(self) -> bool:
        ent = self._cmb_report.currentData()
        if not isinstance(ent, dict):
            return False
        rt = str(ent.get("RPT_TYPE") or "").strip().upper()
        if not rt:
            return False
        if "單據" in rt:
            return True
        return rt in ("DOC", "DOCUMENT", "SLIP", "FORM")

    def _selected_report_is_list(self) -> bool:
        ent = self._cmb_report.currentData()
        if not isinstance(ent, dict):
            return False
        rt = str(ent.get("RPT_TYPE") or "").strip().upper()
        if not rt:
            return False
        if "清單" in rt:
            return True
        return rt in ("LIST",)

    def _on_report_changed(self, _idx: int) -> None:
        self._apply_print_defaults_for_current_report(force=True)

    def _refresh_selected_report_entry_from_db(self) -> None:
        """
        使用目前選取項目的 RPT_PROC 即時回查 SYS_DATA.REPORT，
        同步 RPT_TYPE / RPT_SQL / GROUP_BY / GROUP_SUM / RPT_FIELD / FIELD_LABEL 等欄位。
        """
        idx = self._cmb_report.currentIndex()
        if idx < 0:
            return
        ent = self._cmb_report.itemData(idx)
        if not isinstance(ent, dict):
            return
        rpt_proc = str(ent.get("RPT_PROC") or "").strip()
        if not rpt_proc:
            return
        row = fetch_report_row_by_rpt_proc(self.sys_mdb_path, rpt_proc)
        if not isinstance(row, dict):
            return
        ent2 = dict(ent)
        for k in (
            "PROC_NAME",
            "RPT_INDEX",
            "CHN_TITLE",
            "ENG_TITLE",
            "NEED_DO",
            "RPT_PROC",
            "RPT_TYPE",
            "GROUP_BY",
            "RPT_FILE",
            "RPT_FIELD",
            "RPT_CO",
            "RPT_SQL",
            "FIELD_LABEL",
        ):
            ent2[k] = _dict_get_ci(row, k, ent2.get(k, ""))
        ent2["GROUP_SUM"] = _dict_get_report_group_sum(row)
        ent2["_raw"] = row
        self._cmb_report.setItemData(idx, ent2)

    def _set_date_text(self, target: QLineEdit, d: QDate) -> None:
        if d.isValid():
            target.setText(d.toString("yyyy/MM/dd"))
        else:
            target.clear()

    def _parse_user_date_text(self, text: str) -> Optional[QDate]:
        t = (text or "").strip()
        if not t:
            return None
        d0 = parse_qdate(t, APP_DATE_QT_FORMAT)
        if d0 is not None:
            return QDate(d0.year, d0.month, d0.day)
        for pat in ("yyyy/MM/dd", "yyyy-M-d", "yyyy-MM-dd", APP_DATE_QT_FORMAT):
            d = QDate.fromString(t, pat)
            if d.isValid():
                return d
        return None

    def _pick_date_into(self, target: QLineEdit) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("選擇日期" if self.lang == "CHN" else "Select Date")
        lay = QVBoxLayout(dlg)
        cal = QCalendarWidget(dlg)
        d0 = self._parse_user_date_text(target.text())
        if d0 is not None and d0.isValid():
            cal.setSelectedDate(d0)
        else:
            cal.setSelectedDate(QDate.currentDate())
        lay.addWidget(cal)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        lay.addWidget(btns)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._set_date_text(target, cal.selectedDate())

    def _pick_doc_no_into(self, target: QLineEdit) -> None:
        if self._inv_i is None:
            QMessageBox.information(
                self,
                "提示" if self.lang == "CHN" else "Info",
                "找不到可選擇的主編號欄位。"
                if self.lang == "CHN"
                else "Cannot find a key number column.",
            )
            return
        cols, src_idx = self.data_dict.grid_display_projection(
            self.table_name, self.physical_fields
        )
        if not cols:
            cols = list(self.physical_fields)
            src_idx = list(range(len(cols)))
        rows = [list(r) for r in self._rows_for_selected_report()]
        if not rows:
            QMessageBox.information(
                self,
                "提示" if self.lang == "CHN" else "Info",
                "目前沒有可選擇的資料。"
                if self.lang == "CHN"
                else "No records available.",
            )
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("選擇記錄" if self.lang == "CHN" else "Select record")
        dlg.resize(980, 560)
        lay = QVBoxLayout(dlg)
        ed = QLineEdit()
        ed.setPlaceholderText("輸入關鍵字過濾（GRID）" if self.lang == "CHN" else "Type to filter (grid)")
        tbl = QTableWidget()
        tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.setAlternatingRowColors(True)
        tbl.verticalHeader().setVisible(False)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        lay.addWidget(ed)
        lay.addWidget(tbl)
        lay.addWidget(btns)

        # 與 GRID 列索引對應的完整實體列（不依賴 QTableWidgetItem.UserRole，避免 clear/欄位異常時取錯）
        filtered_snapshot: List[List[str]] = []

        def reload_grid() -> None:
            filtered_snapshot.clear()
            kw = (ed.text() or "").strip().lower()
            for rec in rows:
                rendered = []
                for c, pi in enumerate(src_idx):
                    raw = rec[pi] if pi < len(rec) else ""
                    fname = cols[c] if c < len(cols) else ""
                    dfmt = self.data_dict.get_data_format(self.table_name, fname)
                    dtyp = self.data_dict.get_data_type(self.table_name, fname)
                    rendered.append(format_cell_display(fname, raw, dfmt, dtyp))
                if (not kw) or any(kw in str(x).lower() for x in rendered):
                    filtered_snapshot.append(rec)

            headers = [self.data_dict.get_title(self.table_name, c, self.lang) for c in cols]
            tbl.clear()
            tbl.setColumnCount(len(cols))
            tbl.setHorizontalHeaderLabels(headers)
            tbl.setRowCount(len(filtered_snapshot))
            for r, rec in enumerate(filtered_snapshot):
                for c, pi in enumerate(src_idx):
                    raw = rec[pi] if pi < len(rec) else ""
                    fname = cols[c] if c < len(cols) else ""
                    dfmt = self.data_dict.get_data_format(self.table_name, fname)
                    dtyp = self.data_dict.get_data_type(self.table_name, fname)
                    text = format_cell_display(fname, raw, dfmt, dtyp)
                    tbl.setItem(r, c, QTableWidgetItem(text))
            tbl.resizeColumnsToContents()
            if tbl.rowCount() > 0:
                tbl.selectRow(0)

        def accept_row(row: int) -> None:
            if row < 0 or row >= len(filtered_snapshot):
                return
            rec = filtered_snapshot[row]
            key_val = self._pick_key_from_rec(rec)
            if key_val:
                target.setText(key_val)
                dlg.accept()

        def accept_selected_row() -> None:
            accept_row(tbl.currentRow())

        def on_item_double_clicked(it: QTableWidgetItem) -> None:
            # 雙擊當下列，避免 currentRow 尚未與點擊列同步
            accept_row(it.row())

        ed.textChanged.connect(lambda _t: reload_grid())
        tbl.itemDoubleClicked.connect(on_item_double_clicked)
        btns.accepted.connect(accept_selected_row)
        btns.rejected.connect(dlg.reject)
        reload_grid()
        dlg.exec()

    def _active_specs(self) -> List[ReportColumnSpec]:
        row = self._cmb_report.currentData()
        if row is None:
            return list(self._specs_builtin)
        return list(self._specs_builtin)

    def _selected_report_entry(self) -> Dict[str, Any]:
        row = self._cmb_report.currentData()
        if isinstance(row, dict):
            return row
        return {}

    def _is_group_report(self) -> bool:
        ent = self._selected_report_entry()
        rt = str(ent.get("RPT_TYPE") or "").strip().upper()
        if not rt:
            return False
        return ("組合明細" in rt) or ("GROUP" in rt)

    def _is_finance_report(self) -> bool:
        ent = self._selected_report_entry()
        rt = str(ent.get("RPT_TYPE") or "").strip().upper()
        if not rt:
            return False
        if "財務" in rt:
            return True
        return rt == "FINANCE"

    def _selected_report_is_finance(self) -> bool:
        return self._is_finance_report()

    def _finance_structure_table_name(self) -> Optional[str]:
        """DO_PL → PL_RPT；DO_BS → BS_RPT；其餘（如試算表）無架構表。"""
        proc = self._selected_rpt_proc().upper()
        if proc == "DO_PL":
            return "PL_RPT"
        if proc == "DO_BS":
            return "BS_RPT"
        return None

    def _finance_filtered_account_rows(self) -> List[List[str]]:
        """財務報表：依由/至編號篩選賬戶主檔（日期僅用於期間計算）。"""
        src_rows = self._rows_for_selected_report()
        use_inv = bool(
            (self._ed_inv_from.text() or self._ed_inv_to.text()).strip()
        )
        fi = (self._ed_inv_from.text() or "").strip()
        ti = (self._ed_inv_to.text() or "").strip()
        inv_i = self._inv_i
        out: List[List[str]] = []
        for rec in src_rows:
            if use_inv and inv_i is not None and 0 <= inv_i < len(rec):
                v = (rec[inv_i] or "").strip()
                if fi and v < fi:
                    continue
                if ti and v > ti:
                    continue
            out.append(list(rec))
        if inv_i is not None:
            i = inv_i
            out.sort(key=lambda r: (r[i] if i < len(r) else "").strip())
        return out

    def _finance_report_html(
        self, title: str, omit_embedded_header: bool = False
    ) -> Optional[str]:
        """RPT_TYPE=FINANCE：FIELD_LABEL 標題、RPT_FIELD 資料、表尾合計雙線。"""
        from core.finance_report_service import (
            build_finance_table,
            build_structured_finance_table,
            finance_totals_row,
            load_finance_structure_rows,
            resolve_period_range,
        )

        ent = self._selected_report_entry()
        field_names = self._split_field_names(str(ent.get("RPT_FIELD") or ""))
        labels = self._split_field_names(str(ent.get("FIELD_LABEL") or ""))
        if not field_names:
            field_names = ["AC_KEY", "AC_NAME", "OPEN_AMT", "PERIOD_AMT", "YTD_AMT"]
        headers = labels if labels and len(labels) >= len(field_names) else field_names
        if len(headers) < len(field_names):
            headers = list(headers) + field_names[len(headers) :]
        headers = headers[: len(field_names)]
        if self.backend is None:
            return None
        from_p, to_p, perr = resolve_period_range(
            self.backend,
            self._ed_date_from.text(),
            self._ed_date_to.text(),
        )
        hdr = None if omit_embedded_header else self._report_center_header_html(title)
        if perr:
            msg = perr if self.lang == "CHN" else perr
            return _html_report(title, [""], [[msg]], None, None, hdr, omit_embedded_header)

        rows = self._finance_filtered_account_rows()
        col_widths = _finance_col_widths(field_names)
        struct_table = self._finance_structure_table_name()
        rpt_proc = self._selected_rpt_proc().upper()
        if struct_table:
            sfields, srows = load_finance_structure_rows(self.backend, struct_table)
            if not srows:
                msg = (
                    f"找不到 {struct_table} 架構資料。"
                    if self.lang == "CHN"
                    else f"Structure table {struct_table} has no rows."
                )
                return _html_report(
                    title, [""], [[msg]], None, None, hdr, omit_embedded_header
                )
            styled, align_right, totals = build_structured_finance_table(
                self.physical_fields,
                rows,
                sfields,
                srows,
                field_names,
                from_p,
                to_p,
                lang=self.lang,
            )
            if rpt_proc == "DO_BS":
                totals = None
            frag = _html_styled_rows_fragment(
                headers, styled, totals, align_right, col_widths
            )
            if hdr:
                top = hdr
            elif omit_embedded_header:
                top = ""
            else:
                top = f'<h2 style="margin-bottom:8px;">{_escape_html(title)}</h2>'
            return f"""<!DOCTYPE html><html><head><meta charset="utf-8"/></head>
<body style="font-family: sans-serif;">
{top}
{frag}
</body></html>"""

        body, align_right = build_finance_table(
            self.physical_fields,
            rows,
            field_names,
            from_p,
            to_p,
        )
        totals = finance_totals_row(
            self.physical_fields,
            rows,
            field_names,
            from_p,
            to_p,
        )
        if self.lang != "CHN" and totals and not str(totals[0]).strip():
            totals[0] = "Total"
        return _html_report(
            title,
            headers,
            body,
            totals,
            align_right,
            hdr,
            omit_embedded_header,
            col_widths,
        )

    @staticmethod
    def _split_field_names(raw: str) -> List[str]:
        s = (raw or "").strip()
        if not s:
            return []
        # 支援常見分隔：半形/全形逗號、分號、直線、換行、Tab、頓號
        for sep in ("、", "；", "，", ";", "|", "\r", "\n", "\t"):
            s = s.replace(sep, ",")
        out: List[str] = []
        for p in s.split(","):
            t = p.strip().strip('"').strip("'").strip("「").strip("」").strip()
            if t:
                out.append(t)
        return out

    @staticmethod
    def _normalize_report_field_token(token: str) -> str:
        s = (token or "").strip()
        if not s:
            return ""
        # 移除中括號/大括號/反引號
        for ch in ("[", "]", "{", "}", "`"):
            s = s.replace(ch, "")
        # 支援 TABLE.FIELD -> FIELD
        if "." in s:
            s = s.split(".")[-1]
        return s.strip().upper()

    @staticmethod
    def _candidate_report_field_tokens(token: str) -> List[str]:
        """
        產生 REPORT 欄位可能的比對 token。
        例如 `VOUTRX.ITEM_NO` -> [`VOUTRX.ITEM_NO`, `ITEM_NO`]
        """
        raw = (token or "").strip()
        if not raw:
            return []
        norm_full = raw
        for ch in ("[", "]", "{", "}", "`"):
            norm_full = norm_full.replace(ch, "")
        norm_full = norm_full.strip().upper()
        out: List[str] = []
        if norm_full:
            out.append(norm_full)
        tail = norm_full.split(".")[-1].strip() if "." in norm_full else norm_full
        if tail and tail not in out:
            out.append(tail)
        return out

    def _resolve_field_index(self, name_or_title: str) -> Optional[int]:
        """將 REPORT 欄位設定轉成 physical_fields 索引（支援實體名/中英標題）。"""
        tokens = self._candidate_report_field_tokens(name_or_title)
        if not tokens:
            return None
        compact_tokens = [t.replace("_", "").replace(" ", "").replace(".", "") for t in tokens]

        def _matches(value: str) -> bool:
            v = self._candidate_report_field_tokens(value)
            if not v:
                return False
            v_compact = [x.replace("_", "").replace(" ", "").replace(".", "") for x in v]
            for tok in tokens:
                if tok in v:
                    return True
            for tok in compact_tokens:
                if tok in v_compact:
                    return True
            # 寬鬆：`VOUTRX_ITEM_NO` 也可對到 `ITEM_NO`
            for vv in v:
                for tok in tokens:
                    if vv.endswith(tok):
                        return True
            for vv in v_compact:
                for tok in compact_tokens:
                    if vv.endswith(tok):
                        return True
            return False

        # 1) 先以實體欄位名比對（大小寫不敏感）
        for i, fn in enumerate(self.physical_fields):
            if _matches(str(fn or "")):
                return i
        # 2) 再以欄位標題比對（中/英，大小寫不敏感）
        for i, fn in enumerate(self.physical_fields):
            chn = str(self.data_dict.get_title(self.table_name, fn, "CHN") or "").strip()
            eng = str(self.data_dict.get_title(self.table_name, fn, "ENG") or "").strip()
            if chn and _matches(chn):
                return i
            if eng and _matches(eng):
                return i
        return None

    def _report_center_header_html(self, report_title: str) -> Optional[str]:
        """
        非單據報表頁首（置中）：公司名稱、報表名稱、由/至編號與由/至日期條件。
        條件空白時顯示「全部」與「全部日期」。
        """
        if self._selected_report_is_document():
            return None
        parts: List[str] = []
        co_nm = (getattr(self, "_company_display_name", None) or "").strip()
        if co_nm:
            parts.append(
                f'<div style="text-align:center;font-weight:700;font-size:14pt;">'
                f"{_escape_html(co_nm)}</div>"
            )
        parts.append(
            f'<div style="text-align:center;font-weight:700;font-size:12pt;margin-top:4px;">'
            f"{_escape_html(report_title)}</div>"
        )
        inv_from = (self._ed_inv_from.text() or "").strip()
        inv_to = (self._ed_inv_to.text() or "").strip()
        d_from = (self._ed_date_from.text() or "").strip()
        d_to = (self._ed_date_to.text() or "").strip()
        lab = self._doc_no_label()
        if not inv_from and not inv_to:
            if self.lang == "CHN":
                line = f"全部{lab}編號"
            else:
                line = f"ALL {lab} no."
        else:
            inv_from_disp = inv_from if inv_from else ("全部" if self.lang == "CHN" else "ALL")
            inv_to_disp = inv_to if inv_to else ("全部" if self.lang == "CHN" else "ALL")
            if self.lang == "CHN":
                line = f"由{lab}編號：{inv_from_disp}　　至{lab}編號：{inv_to_disp}"
            else:
                line = f"From {lab} no.: {inv_from_disp}    To {lab} no.: {inv_to_disp}"
        parts.append(
            f'<div style="text-align:center;font-size:10pt;margin-top:6px;">'
            f"{_escape_html(line)}</div>"
        )
        if d_from or d_to:
            d_from_disp = d_from if d_from else ("全部" if self.lang == "CHN" else "ALL")
            d_to_disp = d_to if d_to else ("全部" if self.lang == "CHN" else "ALL")
            if self.lang == "CHN":
                line = f"由日期：{d_from_disp}　　至日期：{d_to_disp}"
            else:
                line = f"From date: {d_from_disp}    To date: {d_to_disp}"
            parts.append(
                f'<div style="text-align:center;font-size:10pt;margin-top:4px;">'
                f"{_escape_html(line)}</div>"
            )
        parts.append('<div style="margin-bottom:10px;"></div>')
        return "".join(parts)

    def _report_center_header_plain_lines(self, report_title: str) -> List[str]:
        """與 _report_center_header_html 相同內容之純文字行，供每頁頁首繪製。"""
        if self._selected_report_is_document():
            return []
        lines: List[str] = []
        co_nm = (getattr(self, "_company_display_name", None) or "").strip()
        if co_nm:
            lines.append(co_nm)
        lines.append(report_title)
        inv_from = (self._ed_inv_from.text() or "").strip()
        inv_to = (self._ed_inv_to.text() or "").strip()
        d_from = (self._ed_date_from.text() or "").strip()
        d_to = (self._ed_date_to.text() or "").strip()
        lab = self._doc_no_label()
        if not inv_from and not inv_to:
            if self.lang == "CHN":
                lines.append(f"全部{lab}編號")
            else:
                lines.append(f"ALL {lab} no.")
        else:
            inv_from_disp = inv_from if inv_from else ("全部" if self.lang == "CHN" else "ALL")
            inv_to_disp = inv_to if inv_to else ("全部" if self.lang == "CHN" else "ALL")
            if self.lang == "CHN":
                lines.append(f"由{lab}編號：{inv_from_disp}　　至{lab}編號：{inv_to_disp}")
            else:
                lines.append(f"From {lab} no.: {inv_from_disp}    To {lab} no.: {inv_to_disp}")
        if d_from or d_to:
            d_from_disp = d_from if d_from else ("全部" if self.lang == "CHN" else "ALL")
            d_to_disp = d_to if d_to else ("全部" if self.lang == "CHN" else "ALL")
            if self.lang == "CHN":
                lines.append(f"由日期：{d_from_disp}　　至日期：{d_to_disp}")
            else:
                lines.append(f"From date: {d_from_disp}    To date: {d_to_disp}")
        return lines

    @staticmethod
    def _header_block_height_pt(header_lines: Sequence[str]) -> float:
        """預留頁首區高度（pt），須與 _print_document_with_page_footer 繪製行高一致。"""
        if not header_lines:
            return 0.0
        h = 6.0
        for i, _ln in enumerate(header_lines):
            if i == 0:
                h += 20.0
            elif i == 1:
                h += 17.0
            else:
                h += 13.0
        return h + 8.0

    def _group_report_html(
        self, title: str, rows: Sequence[Sequence[str]], omit_embedded_header: bool = False
    ) -> Optional[str]:
        """
        RPT_TYPE=GROUP（或含「組合明細」）：
        標題列：REPORT.FIELD_LABEL 對應之欄位標題（不足則回退資料字典標題）。
        GROUP HEADER：REPORT.GROUP_BY 對應欄位值，欄位間以「 - 」分隔。
        DETAIL LIST：REPORT.RPT_FIELD 對應之明細欄位。
        GROUP 總數列：REPORT.GROUP_SUM **空白**時不顯示；**非空白**時僅在 GROUP_SUM 命中之欄位顯示小計，
        其餘欄位在該列一律空白（不累加、不顯示數字）。
        表尾合計總數列：同上，僅 GROUP_SUM 命中欄位顯示全表合計，列底雙線。
        """
        ent = self._selected_report_entry()
        group_names = self._split_field_names(str(ent.get("GROUP_BY") or ""))
        detail_names = self._split_field_names(str(ent.get("RPT_FIELD") or ""))
        field_labels = self._split_field_names(str(ent.get("FIELD_LABEL") or ""))
        group_sum_tokens = self._selected_group_sum_field_tokens()
        if not group_names or not detail_names:
            return None
        resolved_gnames: List[str] = []
        gidxs: List[int] = []
        for gname in group_names:
            gi = self._resolve_runtime_field_index(gname)
            if gi is None:
                self._add_strict_mapping_error("GROUP_BY 對不到", gname)
                continue
            gidxs.append(gi)
            if 0 <= gi < len(self.physical_fields):
                resolved_gnames.append(self.physical_fields[gi])
            else:
                resolved_gnames.append(str(gname or "").strip())
        if not gidxs:
            return None
        table_up = (self.table_name or "").strip().upper()
        tx_table = ""
        tx_cols: List[str] = []
        tx_norm_cols: List[Tuple[str, str]] = []
        detail_specs: List[Tuple[str, str, Optional[int], Optional[int]]] = []
        # (raw_token, source["main"|"tx"], main_idx, tx_idx)
        detail_header_labels: List[str] = []
        for pos, n in enumerate(detail_names):
            raw = (n or "").strip()
            label_from_cfg = (
                str(field_labels[pos]).strip()
                if pos < len(field_labels) and str(field_labels[pos]).strip()
                else ""
            )
            resolved_this_field = False
            full = self._candidate_report_field_tokens(raw)
            full_name = full[0] if full else raw.upper()
            prefix = ""
            tail = full_name
            if "." in full_name:
                prefix, tail = full_name.split(".", 1)
                prefix = prefix.strip().upper()
                tail = tail.strip().upper()
            i_main = self._resolve_runtime_field_index(raw)
            if i_main is not None and (not prefix or prefix == table_up):
                if 0 <= i_main < len(self.physical_fields):
                    physical_name = self.physical_fields[i_main]
                    ttl = str(
                        self.data_dict.get_title(self.table_name, physical_name, self.lang) or ""
                    ).strip()
                    head_name = physical_name
                else:
                    # 執行期動態索引：不可直接回索 physical_fields，避免越界。
                    head_name = str(self._runtime_index_field_name.get(i_main, raw or tail) or "")
                    ttl = ""
                detail_header_labels.append(label_from_cfg or ttl or raw or head_name)
                detail_specs.append((raw, "main", i_main, None))
                resolved_this_field = True
                continue
            if prefix and prefix != table_up and self.backend is not None:
                if not tx_table:
                    tx_table = prefix
                    tx_cols = self.backend.list_columns(tx_table)
                    tx_norm_cols = [
                        (
                            self._normalize_report_field_token(c),
                            self._normalize_report_field_token(c).replace("_", "").replace(" ", ""),
                        )
                        for c in tx_cols
                    ]
                if tx_table == prefix and tx_cols:
                    tnorm = self._normalize_report_field_token(tail)
                    tcmp = tnorm.replace("_", "").replace(" ", "")
                    tx_idx: Optional[int] = None
                    # 1) 完全命中
                    for ci, (n1, n2) in enumerate(tx_norm_cols):
                        if n1 == tnorm or n2 == tcmp:
                            tx_idx = ci
                            break
                    if tx_idx is not None:
                        tx_phys = str(tx_cols[tx_idx] or "").strip()
                        ttl = str(
                            self.data_dict.get_title(tx_table, tx_phys, self.lang) or ""
                        ).strip()
                        detail_header_labels.append(label_from_cfg or ttl or tx_phys or raw or tail)
                        detail_specs.append((raw, "tx", None, tx_idx))
                        resolved_this_field = True
                        continue
            if not resolved_this_field:
                self._add_strict_mapping_error("RPT_FIELD 對不到", raw or tail)
                continue
        if not detail_specs:
            return None
        n_d = len(detail_specs)
        detail_right_align: List[bool] = []
        for _raw_tok, src, i_main, i_tx in detail_specs:
            if src == "main" and i_main is not None:
                if i_main < len(self.physical_fields):
                    fn = self.physical_fields[i_main]
                    dtyp = self.data_dict.get_data_type(self.table_name, fn)
                else:
                    fn = str(self._runtime_index_field_name.get(i_main, _raw_tok) or "").strip()
                    dtyp = ""
                detail_right_align.append(_report_column_align_right(fn, dtyp))
            elif src == "tx" and tx_table and i_tx is not None and i_tx < len(tx_cols):
                tx_name = str(tx_cols[i_tx] or "").strip()
                dtyp = self.data_dict.get_data_type(tx_table, tx_name)
                detail_right_align.append(_report_column_align_right(tx_name, dtyp))
            else:
                detail_right_align.append(False)
        # GROUP_SUM：空白（或清理後無 token）→ 不顯示 GROUP 總數／合計總數列，且不累加。
        # 非空白 → 僅 sum_mask 欄累加並顯示；其餘欄在該等列強制空白。
        sum_mask = [False] * n_d

        def _spec_matches_group_sum(col_hint: str, sum_tok: str) -> bool:
            """
            GROUP_SUM token 與欄位識別字比對（僅實體／SQL 名，不含標題）。
            禁止「SUM 較長欄較短」的 endswith（例如 DR_HK 誤配欄名 HK、標題「港幣」等）。
            """
            sum_n = self._normalize_report_field_token(str(sum_tok or ""))
            if not sum_n:
                return False
            sum2 = sum_n.replace("_", "").replace(" ", "")
            col_n = self._normalize_report_field_token(str(col_hint or ""))
            col2 = col_n.replace("_", "").replace(" ", "")
            if col_n == sum_n or (col2 and col2 == sum2):
                return True
            # 欄位名以完整 SUM token 為後綴，且前一字元為表／別名分隔（T.DR_HK、SUM_DR_HK）
            if len(col_n) > len(sum_n) and col_n.endswith(sum_n):
                if col_n[-len(sum_n) - 1] in "._":
                    return True
            for cc in self._candidate_report_field_tokens(str(col_hint or "")):
                cn = self._normalize_report_field_token(cc)
                if not cn:
                    continue
                if cn == sum_n:
                    return True
                if len(cn) > len(sum_n) and cn.endswith(sum_n):
                    if cn[-len(sum_n) - 1] in "._":
                        return True
            return False

        if group_sum_tokens:
            gst_clean: List[str] = []
            for g in group_sum_tokens:
                t = str(g or "").strip().strip("\ufeff\u200b\u00a0")
                if t:
                    gst_clean.append(t)
            group_sum_tokens = gst_clean
        if group_sum_tokens:
            for j in range(n_d):
                raw_j = str(detail_specs[j][0] or "")
                names_try: List[str] = [raw_j]
                _rt, src_j, i_main_j, i_tx_j = detail_specs[j]
                if src_j == "main" and i_main_j is not None:
                    if 0 <= i_main_j < len(self.physical_fields):
                        names_try.append(str(self.physical_fields[i_main_j] or ""))
                    else:
                        rn = str(
                            self._runtime_index_field_name.get(i_main_j, "") or ""
                        ).strip()
                        if rn:
                            names_try.append(rn)
                        sql_src = self._sql_src_index_by_target.get(i_main_j)
                        lcols = self._last_sql_columns or []
                        if (
                            sql_src is not None
                            and 0 <= sql_src < len(lcols)
                        ):
                            names_try.append(str(lcols[sql_src] or "").strip())
                elif (
                    src_j == "tx"
                    and tx_cols
                    and i_tx_j is not None
                    and i_tx_j < len(tx_cols)
                ):
                    names_try.append(str(tx_cols[i_tx_j] or ""))
                seen_nm: set[str] = set()
                for nm in names_try:
                    nm2 = str(nm or "").strip()
                    if not nm2 or nm2 in seen_nm:
                        continue
                    seen_nm.add(nm2)
                    for gst in group_sum_tokens:
                        if _spec_matches_group_sum(nm2, gst):
                            sum_mask[j] = True
                            break
                    if sum_mask[j]:
                        break

        has_group_sum_cols = any(sum_mask)
        group_headers = [
            self.data_dict.get_title(self.table_name, resolved_gnames[k], self.lang)
            for k in range(len(gidxs))
        ]
        detail_headers = detail_header_labels

        def group_key(rec: Sequence[str]) -> Tuple[str, ...]:
            return tuple(str(rec[i] if i < len(rec) else "") for i in gidxs)

        sorted_rows = sorted(rows, key=group_key)
        grand_acc = [0.0] * n_d
        grand_ok = [False] * n_d
        cur_key: Optional[Tuple[str, ...]] = None
        g_acc = [0.0] * n_d
        g_ok = [False] * n_d
        lbl_group = "GROUP總數" if self.lang == "CHN" else "Group total"
        lbl_grand = "合計總數" if self.lang == "CHN" else "Grand total"
        rows_html: List[str] = []
        tx_row_cache: Dict[str, List[List[str]]] = {}

        def _pick_main_key_candidates(rec: Sequence[str]) -> List[Tuple[str, str]]:
            out: List[Tuple[str, str]] = []
            preferred = ("TX_KEY", "VOU_KEY", "QUOTE_NO", "QUOTATION_NO", "QUOT_NO", "INV_NO", "INVOICE_NO", "ID")
            up_fields = [str(f or "").strip().upper() for f in self.physical_fields]
            for p in preferred:
                for i, upn in enumerate(up_fields):
                    if upn == p and i < len(rec):
                        v = str(rec[i] or "").strip()
                        if v:
                            out.append((self.physical_fields[i], v))
            for i, upn in enumerate(up_fields):
                if upn.endswith("_KEY") and i < len(rec):
                    v = str(rec[i] or "").strip()
                    if v:
                        out.append((self.physical_fields[i], v))
            # 主檔欄位與 TX 欄位同名（或去底線後同名）者，視為可關聯鍵
            tx_key_norm: Dict[str, str] = {}
            for tc in tx_cols:
                n = self._normalize_report_field_token(tc)
                tx_key_norm[n] = tc
                tx_key_norm[n.replace("_", "").replace(" ", "")] = tc
            for i, mf in enumerate(self.physical_fields):
                if i >= len(rec):
                    continue
                v = str(rec[i] or "").strip()
                if not v:
                    continue
                mn = self._normalize_report_field_token(mf)
                m2 = mn.replace("_", "").replace(" ", "")
                if mn in tx_key_norm or m2 in tx_key_norm:
                    out.append((mf, v))
            # 去重
            seen = set()
            uniq: List[Tuple[str, str]] = []
            for f, v in out:
                k = (f.upper(), v)
                if k in seen:
                    continue
                seen.add(k)
                uniq.append((f, v))
            return uniq

        def _load_tx_rows_for_rec(rec: Sequence[str]) -> List[List[str]]:
            if not tx_table or self.backend is None or not tx_cols:
                return []
            key_pairs = _pick_main_key_candidates(rec)
            if not key_pairs:
                return []
            for _mf, mv in key_pairs:
                ck = f"{tx_table}|{mv}"
                if ck in tx_row_cache:
                    rs = tx_row_cache[ck]
                    if rs:
                        return rs
                    continue
                for tc in tx_cols:
                    upc = str(tc or "").strip().upper()
                    if (
                        upc not in ("TX_KEY", "VOU_KEY", "QUOTE_NO", "QUOTATION_NO", "QUOT_NO", "INV_NO", "INVOICE_NO", "ID")
                        and not upc.endswith("_KEY")
                        and upc not in (str(_mf or "").strip().upper(),)
                    ):
                        continue
                    try:
                        rs = self.backend.fetch_rows_where(
                            tx_table, tc, mv, limit=2000, column_order=tx_cols
                        )
                    except Exception:
                        rs = []
                    if rs:
                        tx_row_cache[ck] = rs
                        return rs
                tx_row_cache[ck] = []
            return []

        def group_header_text(key: Tuple[str, ...]) -> str:
            vals = [str(v or "").strip() for v in key]
            return " - ".join(vals)

        def flush_group(key_for_flush: Optional[Tuple[str, ...]]) -> None:
            if cur_key is None:
                return
            if has_group_sum_cols:
                has_visible_group_total = any(sum_mask[j] and g_ok[j] for j in range(n_d))
                if has_visible_group_total:
                    detail_cells: List[str] = []
                    for j in range(n_d):
                        if sum_mask[j] and g_ok[j]:
                            detail_cells.append(
                                format_numeric_display(str(g_acc[j]), "amount")
                            )
                        else:
                            detail_cells.append("")
                    group_top0 = "1px solid #000" if sum_mask[0] else "none"
                    cells = [
                        f'<td style="border-top:{group_top0};text-align:left;"><b>{_escape_html(lbl_group)}</b></td>'
                    ]
                    for j, c in enumerate(detail_cells[1:], start=1):
                        top = "1px solid #000" if sum_mask[j] else "none"
                        style = f"border-top:{top};"
                        ta = (
                            "right"
                            if j < len(detail_right_align) and detail_right_align[j]
                            else "left"
                        )
                        style += f"text-align:{ta};"
                        disp = ""
                        if sum_mask[j]:
                            disp = str(c)
                        cells.append(f'<td style="{style}"><b>{_escape_html(disp)}</b></td>')
                    rows_html.append(f"<tr>{''.join(cells)}</tr>")
            if key_for_flush is not None:
                gh = group_header_text(key_for_flush)
                rows_html.append(
                    f'<tr><td colspan="{n_d}" style="font-weight:700;border-top:1px solid #000;">'
                    f'{_escape_html(gh)}</td></tr>'
                )

        for rec in sorted_rows:
            key = group_key(rec)
            if cur_key is None:
                cur_key = key
                rows_html.append(
                    f'<tr><td colspan="{n_d}" style="font-weight:700;border-top:1px solid #000;">'
                    f'{_escape_html(group_header_text(key))}</td></tr>'
                )
            elif key != cur_key:
                flush_group(key)
                cur_key = key
                g_acc = [0.0] * n_d
                g_ok = [False] * n_d
            tx_rows = _load_tx_rows_for_rec(rec)
            if not tx_rows:
                tx_rows = [[]]
            for txr in tx_rows:
                line: List[str] = []
                for j, (_raw_tok, src, i_main, i_tx) in enumerate(detail_specs):
                    raw = ""
                    if src == "main" and i_main is not None:
                        raw = rec[i_main] if i_main < len(rec) else ""
                        if 0 <= i_main < len(self.physical_fields):
                            fname = self.physical_fields[i_main]
                            dtyp = self.data_dict.get_data_type(self.table_name, fname)
                        else:
                            fname = self._runtime_index_field_name.get(i_main, _raw_tok)
                            dtyp = ""
                        disp = self._format_report_value(fname, raw, dtyp)
                    elif src == "tx" and i_tx is not None and i_tx < len(txr):
                        raw = txr[i_tx]
                        tx_name = tx_cols[i_tx] if i_tx < len(tx_cols) else ""
                        tx_dtyp = (
                            self.data_dict.get_data_type(tx_table, tx_name)
                            if tx_table and tx_name
                            else ""
                        )
                        disp = self._format_report_value(tx_name, raw, tx_dtyp)
                    else:
                        disp = ""
                    line.append(disp)
                    v = _cell_to_float(str(raw))
                    if v is not None and sum_mask[j]:
                        g_acc[j] += v
                        g_ok[j] = True
                        grand_acc[j] += v
                        grand_ok[j] = True
                cell_parts: List[str] = []
                for j, c in enumerate(line):
                    ta = (
                        "right"
                        if j < len(detail_right_align) and detail_right_align[j]
                        else "left"
                    )
                    cell_parts.append(
                        f'<td style="text-align:{ta};">{_escape_html(str(c))}</td>'
                    )
                tds = "".join(cell_parts)
                rows_html.append(f"<tr>{tds}</tr>")
        flush_group(None)

        has_visible_grand_total = (
            has_group_sum_cols
            and any(grand_ok[j] and sum_mask[j] for j in range(n_d))
        )
        if has_visible_grand_total:
            detail_cells = []
            for j in range(n_d):
                if sum_mask[j] and grand_ok[j]:
                    detail_cells.append(
                        format_numeric_display(str(grand_acc[j]), "amount")
                    )
                else:
                    detail_cells.append("")
        else:
            detail_cells = []

        if detail_cells:
            grand_top0 = "1px solid #000" if sum_mask[0] else "none"
            gcells = [
                f'<td style="border-top:{grand_top0};border-bottom:none;text-align:left;"><b>{_escape_html(lbl_grand)}</b></td>'
            ]
            for j, c in enumerate(detail_cells[1:], start=1):
                top = "1px solid #000" if sum_mask[j] else "none"
                bottom = "3px double #000" if sum_mask[j] else "none"
                style = f"border-top:{top};border-bottom:{bottom};"
                ta = (
                    "right"
                    if j < len(detail_right_align) and detail_right_align[j]
                    else "left"
                )
                style += f"text-align:{ta};"
                disp = ""
                if sum_mask[j]:
                    disp = str(c)
                gcells.append(f'<td style="{style}"><b>{_escape_html(disp)}</b></td>')
            rows_html.append(f"<tr>{''.join(gcells)}</tr>")

        hs_parts: List[str] = []
        for j, h in enumerate(detail_headers):
            ta = (
                "right"
                if j < len(detail_right_align) and detail_right_align[j]
                else "left"
            )
            hs_parts.append(f'<th style="text-align:{ta};">{_escape_html(h)}</th>')
        hs = "".join(hs_parts)
        if omit_embedded_header:
            top = ""
        else:
            hdr = self._report_center_header_html(title)
            top = hdr if hdr else f'<h2 style="margin-bottom:8px;">{_escape_html(title)}</h2>'
        return f"""<!DOCTYPE html><html><head><meta charset="utf-8"/></head>
<body style="font-family: sans-serif;">
{top}
<table border="1" cellspacing="0" cellpadding="4" width="100%">
<thead><tr>{hs}</tr></thead>
<tbody>{''.join(rows_html)}</tbody>
</table>
</body></html>"""

    def _date_qfmt_for_col(self) -> str:
        return APP_DATE_QT_FORMAT

    def _format_report_value(self, field_name: str, raw: str, data_type: str) -> str:
        """
        報表固定格式：
        - 日期：yyyy/MM/dd
        - 金額／借項／貸項：#,###.##（兩位小數）
        - 匯率：#,###.####（四位小數）
        - 百分比：#,###.#（一位小數）
        - 其他數字：僅非文字型欄位套整數千分位；文字型不格式化
        """
        s = "" if raw is None else str(raw)
        if is_string_data_type(data_type):
            return (s or "").strip()
        if is_boolean_data_type(data_type):
            return normalize_boolean_yn(s)
        if is_date_data_type(data_type) or is_date_field(field_name):
            return format_date_display(s, APP_DATE_QT_FORMAT)
        v = _cell_to_float(s)
        if v is None:
            return (s or "").strip()
        kind = guess_number_kind(field_name, "", data_type)
        if kind == "amount":
            return format_numeric_display(s, "amount")
        if kind == "rate":
            return format_numeric_display(s, "rate")
        if kind == "percent":
            return format_numeric_display(s, "percent")
        if is_numeric_data_type(data_type):
            return format_numeric_display(s, "int")
        return (s or "").strip()

    def _infer_date_column_index(self, rows: List[List[str]]) -> Optional[int]:
        """
        使用者已輸入日期區間，但主檔未偵測到日期欄時，由目前報表資料列推斷日期欄索引
        （利於 RPT_SQL 等回傳欄位與主畫面 Grid 不完全相同時仍可依日期篩選）。
        """
        if not rows:
            return None
        qfmt = self._date_qfmt_for_col()
        max_c = max((len(r) for r in rows), default=0)
        if max_c <= 0:
            return None
        sample = rows[: min(100, len(rows))]
        best_i: Optional[int] = None
        best_ok = 0
        best_ratio = -1.0
        for ci in range(max_c):
            non_empty = 0
            ok = 0
            for r in sample:
                if ci >= len(r):
                    continue
                t = str(r[ci] or "").strip()
                if not t:
                    continue
                non_empty += 1
                d = _parse_cell_date(t, qfmt)
                if d is not None and d.isValid():
                    ok += 1
            if non_empty < 1 or ok < 1:
                continue
            ratio = ok / float(non_empty)
            if ok > best_ok or (ok == best_ok and ratio > best_ratio):
                best_ok = ok
                best_ratio = ratio
                best_i = ci
        return best_i

    def _infer_date_column_from_schema(self, rows: List[List[str]]) -> Optional[int]:
        """依 DATA_DICTIONARY 日期型／欄名含 DATE 者，對照列索引找第一個可解析出日期的欄。"""
        if not rows:
            return None
        qfmt = self._date_qfmt_for_col()
        sample = rows[: min(100, len(rows))]
        for pi, fname in enumerate(self.physical_fields):
            dtyp = self.data_dict.get_data_type(self.table_name, fname)
            if not (is_date_data_type(dtyp) or is_date_field(fname)):
                continue
            for r in sample:
                if pi >= len(r):
                    continue
                t = str(r[pi] or "").strip()
                if not t:
                    continue
                d = _parse_cell_date(t, qfmt)
                if d is not None and d.isValid():
                    return pi
        return None

    def _filtered_rows(self) -> List[List[str]]:
        if self._is_finance_report():
            return self._finance_filtered_account_rows()
        use_inv = bool(
            (self._ed_inv_from.text() or self._ed_inv_to.text()).strip()
        )
        df = self._parse_user_date_text(self._ed_date_from.text())
        dt = self._parse_user_date_text(self._ed_date_to.text())
        src_rows = self._rows_for_selected_report()
        want_date = df is not None or dt is not None
        date_i_eff: Optional[int] = self._date_i
        if want_date:
            if date_i_eff is None:
                date_i_eff = self._infer_date_column_index(src_rows)
            if date_i_eff is None:
                date_i_eff = self._infer_date_column_from_schema(src_rows)
        use_date = date_i_eff is not None and want_date
        rows = _filter_rows(
            src_rows,
            self.physical_fields,
            self._inv_i,
            date_i_eff,
            self._date_qfmt_for_col(),
            self._ed_inv_from.text(),
            self._ed_inv_to.text(),
            df,
            dt,
            use_inv,
            use_date,
        )
        # 資料清單預設依「由/至紀錄」同一主編號欄位排序（由小到大）。
        if self._inv_i is not None:
            i = self._inv_i
            rows.sort(key=lambda r: (r[i] if i < len(r) else "").strip())
        return rows

    def _project_rows(
        self, specs: Sequence[ReportColumnSpec], rows: Sequence[Sequence[str]]
    ) -> Tuple[List[str], List[List[str]], List[str], List[int]]:
        pairs: List[Tuple[ReportColumnSpec, int]] = []
        for sp in specs:
            try:
                idx = self.physical_fields.index(sp.physical_name)
            except ValueError:
                continue
            pairs.append((sp, idx))
        if not pairs:
            return [], [], [], []
        headers = [sp.display_title for sp, _ in pairs]
        idxs = [i for _, i in pairs]
        align_right_cols: List[int] = []
        for ci, (_sp, src_i) in enumerate(pairs):
            fname = self.physical_fields[src_i] if src_i < len(self.physical_fields) else ""
            dtyp = self.data_dict.get_data_type(self.table_name, fname)
            if _report_column_align_right(fname, dtyp):
                align_right_cols.append(ci)
        out: List[List[str]] = []
        for rec in rows:
            line: List[str] = []
            for i in idxs:
                raw = rec[i] if i < len(rec) else ""
                fname = self.physical_fields[i] if i < len(self.physical_fields) else ""
                dtyp = self.data_dict.get_data_type(self.table_name, fname)
                line.append(self._format_report_value(fname, raw, dtyp))
            out.append(line)
        totals: List[str] = []
        for sp, col_i in pairs:
            if not sp.field_total:
                totals.append("")
                continue
            s = 0.0
            ok = False
            for rec in rows:
                if col_i < len(rec):
                    v = _cell_to_float(rec[col_i])
                    if v is not None:
                        s += v
                        ok = True
            if ok:
                df_tot = self.data_dict.get_data_format(self.table_name, sp.physical_name)
                dtyp = self.data_dict.get_data_type(self.table_name, sp.physical_name)
                k = guess_number_kind(sp.physical_name, df_tot, dtyp)
                totals.append(format_numeric_display(str(s), k if k is not None else "amount"))
            else:
                totals.append("")
        if not any(str(t).strip() for t in totals):
            return headers, out, [], align_right_cols
        return headers, out, totals, align_right_cols

    def _doc_html(self, for_print_per_page_header: bool = False) -> Tuple[QTextDocument, str]:
        specs = self._active_specs()
        rows = self._filtered_rows()
        title = self._cmb_report.currentText()
        use_strip = for_print_per_page_header and not self._selected_report_is_document()
        hdr = None if use_strip else self._report_center_header_html(title)
        omit = use_strip
        if self._strict_mapping_errors:
            lines: List[List[str]] = []
            if self.lang == "CHN":
                lines.append(["嚴格模式欄位對應失敗："])
                lines.append([f"RPT_FIELD 欄位：{self._selected_rpt_field()}"])
                lines.append([f"GROUP_BY 欄位：{self._selected_group_by()}"])
                lines.append([f"報表欄位（RPT_SQL）：{', '.join(self._last_sql_columns)}"])
            else:
                lines.append(["Strict mapping failed:"])
                lines.append([f"RPT_FIELD: {self._selected_rpt_field()}"])
                lines.append([f"GROUP_BY: {self._selected_group_by()}"])
                lines.append([f"Report columns (RPT_SQL): {', '.join(self._last_sql_columns)}"])
            lines.append([""])
            for err in self._strict_mapping_errors:
                lines.append([f"- {err}"])
            html_err = _html_report(title, [""], lines, None, None, hdr, omit)
            doc_e = QTextDocument()
            doc_e.setHtml(html_err)
            return doc_e, html_err
        if self._is_group_report():
            gh = self._group_report_html(title, rows, omit_embedded_header=omit)
            if gh:
                doc_g = QTextDocument()
                doc_g.setHtml(gh)
                return doc_g, gh
            # GROUP 報表設定異常時不要靜默退回 LIST，直接提示設定問題。
            msg = (
                "GROUP 報表設定無效：請檢查 REPORT.GROUP_BY 與 REPORT.RPT_FIELD 是否對應到資料欄位。"
                if self.lang == "CHN"
                else "Invalid GROUP report settings: check REPORT.GROUP_BY and REPORT.RPT_FIELD mapping."
            )
            html_err = _html_report(title, [""], [[msg]], None, None, hdr, omit)
            doc_e = QTextDocument()
            doc_e.setHtml(html_err)
            return doc_e, html_err
        if self._is_finance_report():
            fh = self._finance_report_html(title, omit_embedded_header=omit)
            if fh:
                doc_f = QTextDocument()
                doc_f.setHtml(fh)
                return doc_f, fh
            msg = (
                "財務報表無法產生：請檢查 ACCOUNT 與 PERIOD 資料。"
                if self.lang == "CHN"
                else "Cannot build finance report: check ACCOUNT and PERIOD data."
            )
            html_err = _html_report(title, [""], [[msg]], None, None, hdr, omit)
            doc_e = QTextDocument()
            doc_e.setHtml(html_err)
            return doc_e, html_err
        headers, body, totals, align_right_cols = self._project_rows(specs, rows)
        tr_or_none: Optional[List[str]] = None
        if totals:
            tr = list(totals)
            label = "合計" if self.lang == "CHN" else "Total"
            if tr and not str(tr[0]).strip():
                tr[0] = label
            elif tr:
                tr[0] = label
            tr_or_none = tr
        nh = len(headers)
        if nh > LIST_PRINT_COLS_PER_PAGE:
            html = _html_report_column_pages(
                title,
                headers,
                body,
                tr_or_none,
                LIST_PRINT_COLS_PER_PAGE,
                self.lang,
                align_right_cols,
                hdr,
                omit,
            )
        else:
            html = _html_report(
                title, headers, body, tr_or_none, align_right_cols, hdr, omit
            )
        doc = QTextDocument()
        doc.setHtml(html)
        return doc, html

    def _make_printer(self) -> QPrinter:
        pr = QPrinter(QPrinter.PrinterMode.HighResolution)
        name = self._cmb_printer.currentText()
        if name:
            pr.setPrinterName(name)
        # FINANCE 財務報表預設直印；清單超過 8 欄橫印，其餘直印。
        if self._is_finance_report():
            pr.setPageOrientation(QPageLayout.Orientation.Portrait)
            return pr
        col_count = 0
        for sp in self._active_specs():
            if sp.physical_name in self.physical_fields:
                col_count += 1
        if col_count > 8:
            pr.setPageOrientation(QPageLayout.Orientation.Landscape)
        else:
            pr.setPageOrientation(QPageLayout.Orientation.Portrait)
        return pr

    @staticmethod
    def _printer_page_rect_points(printer: QPrinter) -> QRectF:
        """
        可列印區域（點，與 QPainter on QPrinter 的邏輯座標一致）。
        勿混用 DevicePixel／viewport 像素當作 painter 座標，否則頁首／頁尾會畫在頁外而不可見。
        """
        r = printer.pageRect(QPrinter.Unit.Point)
        if r.width() > 10 and r.height() > 10:
            return QRectF(r)
        try:
            land = (
                printer.pageLayout().orientation()
                == QPageLayout.Orientation.Landscape
            )
        except Exception:
            land = False
        if land:
            return QRectF(0, 0, 842.0, 595.0)
        return QRectF(0, 0, 595.0, 842.0)

    def _print_document_with_page_footer(self, doc: QTextDocument, printer: QPrinter) -> None:
        """
        將 QTextDocument 列印至 printer。
        非單據：每頁頂部繪製公司名／報表名／條件（與畫面頁首一致），底部置中「第 x 頁，共 y 頁」。
        單據：僅底部同上頁尾（內容仍含原 HTML 標題）。
        以 QTextDocument 逐頁繪製內容，不依賴 QtPdf 或第三方 PDF 模組。
        """
        painter: Optional[QPainter] = None
        painter_began = False
        try:
            title = self._cmb_report.currentText()
            header_lines = self._report_center_header_plain_lines(title)
            header_pt = self._header_block_height_pt(header_lines)
            footer_pt_use = 26.0
            painter = QPainter()
            painter_began = painter.begin(printer)
            if not painter_began:
                doc.print(printer)
                return

            full = self._printer_page_rect_points(printer)
            header_h_pt = float(header_pt) if header_lines else 0.0
            footer_h_pt = float(footer_pt_use)
            content_left_pad_pt = 6.0
            content_right_pad_pt = 20.0
            body_rect = QRectF(
                full.adjusted(
                    content_left_pad_pt,
                    header_h_pt,
                    -content_right_pad_pt,
                    -footer_h_pt,
                )
            )
            if body_rect.width() <= 0.0 or body_rect.height() <= 0.0:
                doc.print(printer)
                return

            # 使用副本避免污染呼叫端文件設定。
            # Qt rich text 內容在列印裝置上通常接近 96DPI 邏輯單位，這裡轉回 point 尺度避免字體偏大。
            content_scale = 72.0 / 96.0
            doc_page_w = body_rect.width() / content_scale
            doc_page_h = body_rect.height() / content_scale
            doc_print = QTextDocument()
            doc_print.setDefaultFont(doc.defaultFont())
            doc_print.setHtml(doc.toHtml())
            doc_print.setPageSize(QSizeF(doc_page_w, doc_page_h))
            doc_h = float(doc_print.documentLayout().documentSize().height())
            page_h = max(1.0, doc_page_h)
            n = max(1, int(math.ceil(doc_h / page_h)))

            chn = self.lang == "CHN"
            fam = "Microsoft JhengHei" if chn else "Segoe UI"
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            for i in range(n):
                if i > 0:
                    printer.newPage()
                full_pt = self._printer_page_rect_points(printer)
                body_rect = QRectF(
                    full_pt.adjusted(
                        content_left_pad_pt,
                        header_h_pt,
                        -content_right_pad_pt,
                        -footer_h_pt,
                    )
                )
                painter.save()
                vp = painter.viewport()
                if vp.width() > 2 and vp.height() > 2:
                    painter.setWindow(0, 0, max(1, int(full_pt.width())), max(1, int(full_pt.height())))
                painter.setClipRect(body_rect)
                painter.translate(body_rect.left(), body_rect.top())
                painter.scale(content_scale, content_scale)
                painter.translate(0.0, -(i * page_h))
                doc_print.drawContents(painter)
                painter.restore()

                # 頁首/頁尾文字使用裝置像素座標，避免受 setWindow 影響而字體失真。
                full_dev = QRectF(painter.viewport())
                if full_dev.width() <= 2.0 or full_dev.height() <= 2.0:
                    full_dev = QRectF(full_pt)
                sx = full_dev.width() / max(1.0, full_pt.width())
                sy = full_dev.height() / max(1.0, full_pt.height())
                if header_lines:
                    y = full_dev.top() + 4.0 * sy
                    for li, htext in enumerate(header_lines):
                        fz = 12 if li == 0 else (11 if li == 1 else 9)
                        hf = QFont(fam)
                        hf.setPixelSize(max(9, int(fz * sy)))
                        hf.setBold(li < 2)
                        painter.setFont(hf)
                        line_h = float(painter.fontMetrics().height()) + (5.0 * sy)
                        rr = QRectF(full_dev.left(), y, full_dev.width(), line_h)
                        painter.setPen(QColor(0, 0, 0))
                        painter.drawText(
                            rr,
                            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
                            htext,
                        )
                        y += line_h
                ft = f"頁數: {i + 1}/{n}"
                fr = QRectF(
                    full_dev.left(),
                    full_dev.bottom() - (footer_h_pt * sy),
                    full_dev.width(),
                    max(14.0, footer_h_pt * sy),
                )
                painter.setPen(QColor(0, 0, 0))
                ff = QFont("Microsoft JhengHei")
                ff.setPixelSize(max(9, int(9 * sy)))
                painter.setFont(ff)
                painter.drawText(
                    fr,
                    int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
                    ft,
                )
        except Exception:
            doc.print(printer)
        finally:
            if painter is not None and painter_began and painter.isActive():
                painter.end()

    def _selected_rpt_proc(self) -> str:
        ent = self._cmb_report.currentData()
        if not ent or not isinstance(ent, dict):
            return ""
        return str(ent.get("RPT_PROC") or "").strip()

    def _selected_rpt_sql(self) -> str:
        ent = self._cmb_report.currentData()
        if not ent or not isinstance(ent, dict):
            return ""
        return str(ent.get("RPT_SQL") or "").strip()

    def _selected_rpt_field(self) -> str:
        ent = self._cmb_report.currentData()
        if not ent or not isinstance(ent, dict):
            return ""
        return str(ent.get("RPT_FIELD") or "").strip()

    def _selected_group_by(self) -> str:
        ent = self._cmb_report.currentData()
        if not ent or not isinstance(ent, dict):
            return ""
        return str(ent.get("GROUP_BY") or "").strip()

    def _selected_group_sum_field_tokens(self) -> List[str]:
        """
        REPORT.GROUP_SUM 拆成欄名 token（先 _raw 再 ent，與 GROUP 報表邏輯一致）。
        """
        ent = self._selected_report_entry()
        gs_raw = ""
        eraw = ent.get("_raw")
        if isinstance(eraw, dict):
            gs_raw = _dict_get_report_group_sum(eraw)
        if not gs_raw:
            gs_raw = str(ent.get("GROUP_SUM") or "").strip()
        toks = self._split_field_names(gs_raw)
        if len(toks) == 1 and toks[0] and re.search(r"[\s\t\u3000]", toks[0]):
            toks = [
                x.strip()
                for x in re.split(r"[\s\t\u3000]+", toks[0])
                if x.strip()
            ]
        return toks

    def _resolve_runtime_field_index(self, name_or_title: str) -> Optional[int]:
        """有 RPT_SQL 時先走執行期映射（已依 SQL 對應欄位），再回退資料表／標題解析。"""
        for tok in self._candidate_report_field_tokens(name_or_title):
            if tok in self._runtime_token_index_map:
                return self._runtime_token_index_map[tok]
            compact = tok.replace("_", "").replace(" ", "").replace(".", "")
            if compact in self._runtime_token_index_map:
                return self._runtime_token_index_map[compact]
        return self._resolve_field_index(name_or_title)

    def _add_strict_mapping_error(self, kind: str, token: str) -> None:
        t = (token or "").strip()
        if not t:
            return
        msg = f"{kind}: {t}"
        if msg not in self._strict_mapping_errors:
            self._strict_mapping_errors.append(msg)

    def _rows_for_selected_report(self) -> List[List[str]]:
        """
        規則：
        - REPORT.RPT_SQL 不為空白：報表資料由 RPT_SQL 查詢取得
        - REPORT.RPT_SQL 為空白：報表資料由 PROC_NAME 對應之 PROGRAM.WORK_FILE/TX_FILE（此處即主檔 WORK_FILE）取得
        """
        if self.backend is None:
            return []

        # 每次取數前即時同步該 RPT_PROC 的 REPORT 設定（不使用初始化快取）。
        self._refresh_selected_report_entry_from_db()
        self._runtime_token_index_map = {}
        self._runtime_index_field_name = {}
        self._sql_src_index_by_target = {}
        self._strict_mapping_errors = []
        self._last_sql_columns = []
        rpt_sql = self._selected_rpt_sql()
        if not rpt_sql:
            try:
                return self.backend.fetch_rows(
                    self.table_name,
                    "",
                    False,
                    limit=5000,
                    column_order=self.physical_fields,
                )
            except Exception:
                return []

        rpt_field = self._selected_rpt_field()
        group_by = self._selected_group_by()
        sql_cols, sql_rows = self.backend.fetch_rows_sql(
            rpt_sql,
            params=None,
            limit=5000,
            column_order=None,
        )
        self._last_sql_columns = [str(c or "").strip() for c in sql_cols]
        if not sql_rows:
            be = getattr(self.backend, "last_error", "")
            if str(be or "").strip():
                self._add_strict_mapping_error("RPT_SQL 執行錯誤", str(be))
            return []

        # RPT_SQL 有設定時：先將 GROUP_BY、RPT_FIELD、GROUP_SUM 對到 **SQL 結果欄**（src_i），
        # 再以 SQL 實際欄名與設定 token 對 **資料表 physical_fields**（target_i）；對不到主檔則動態索引。
        # 例：RPT_FIELD="ITEM_NO,QTY"；RPT_SQL 回傳欄位可為 ITEM_NO / TABLE.ITEM_NO / Alias。
        mapped_rows: List[List[str]] = []
        field_tokens = self._split_field_names(rpt_field)
        group_tokens = self._split_field_names(group_by)
        gs_tokens = self._selected_group_sum_field_tokens()
        all_tokens: List[str] = []
        for t in group_tokens + field_tokens + gs_tokens:
            if t and t not in all_tokens:
                all_tokens.append(t)
        group_set = frozenset(group_tokens)
        field_set = frozenset(field_tokens)
        gs_set = frozenset(gs_tokens)
        if all_tokens and sql_cols:
            sql_lookup: Dict[str, int] = {}
            for ci, col in enumerate(sql_cols):
                cands = self._candidate_report_field_tokens(str(col or ""))
                for cand in cands:
                    if cand not in sql_lookup:
                        sql_lookup[cand] = ci
                    compact = cand.replace("_", "").replace(" ", "").replace(".", "")
                    if compact and compact not in sql_lookup:
                        sql_lookup[compact] = ci
            # 實體欄位查表：僅用於「對應資料表」階段（在 SQL 對應之後）
            physical_lookup: Dict[str, int] = {}
            for pi, pf in enumerate(self.physical_fields):
                for cand in self._candidate_report_field_tokens(str(pf or "")):
                    if cand and cand not in physical_lookup:
                        physical_lookup[cand] = pi
                    compact = cand.replace("_", "").replace(" ", "").replace(".", "")
                    if compact and compact not in physical_lookup:
                        physical_lookup[compact] = pi

            def _sql_src_for_token(tok: str) -> Optional[int]:
                for cand in self._candidate_report_field_tokens(tok):
                    if cand in sql_lookup:
                        return sql_lookup[cand]
                    compact = cand.replace("_", "").replace(" ", "").replace(".", "")
                    if compact in sql_lookup:
                        return sql_lookup[compact]
                return None

            def _physical_from_name(name: str) -> Optional[int]:
                for cand in self._candidate_report_field_tokens(name):
                    if cand in physical_lookup:
                        return physical_lookup[cand]
                    compact = cand.replace("_", "").replace(" ", "").replace(".", "")
                    if compact in physical_lookup:
                        return physical_lookup[compact]
                return None

            field_pairs: List[Tuple[int, int]] = []
            next_dyn_i = len(self.physical_fields)
            for tok in all_tokens:
                src_i = _sql_src_for_token(tok)
                if src_i is None:
                    if tok in group_set:
                        self._add_strict_mapping_error("GROUP_BY 對不到 SQL 欄位", tok)
                    elif tok in field_set:
                        self._add_strict_mapping_error("RPT_FIELD 對不到 SQL 欄位", tok)
                    elif tok in gs_set:
                        self._add_strict_mapping_error("GROUP_SUM 對不到 SQL 欄位", tok)
                    else:
                        self._add_strict_mapping_error("欄位對不到 SQL 欄位", tok)
                    continue

                sql_hdr = ""
                if 0 <= src_i < len(sql_cols):
                    sql_hdr = str(sql_cols[src_i] or "").strip()
                target_i = _physical_from_name(sql_hdr) if sql_hdr else None
                if target_i is None:
                    target_i = _physical_from_name(tok)
                if target_i is None:
                    target_i = self._resolve_field_index(tok)
                if target_i is None:
                    target_i = next_dyn_i
                    next_dyn_i += 1
                    self._runtime_index_field_name[target_i] = str(tok or "").strip()

                field_pairs.append((target_i, src_i))
                self._sql_src_index_by_target[target_i] = src_i
                for cand in self._candidate_report_field_tokens(tok):
                    self._runtime_token_index_map[cand] = target_i
                    compact = cand.replace("_", "").replace(" ", "").replace(".", "")
                    if compact:
                        self._runtime_token_index_map[compact] = target_i
                if sql_hdr:
                    for cand in self._candidate_report_field_tokens(sql_hdr):
                        self._runtime_token_index_map[cand] = target_i
                        compact = cand.replace("_", "").replace(" ", "").replace(".", "")
                        if compact:
                            self._runtime_token_index_map[compact] = target_i

            if field_pairs:
                max_target_i = max((ti for ti, _si in field_pairs), default=-1)
                rec_len = max(len(self.physical_fields), max_target_i + 1)
                for srow in sql_rows:
                    rec = [""] * rec_len
                    for target_i, src_i in field_pairs:
                        if 0 <= target_i < len(rec) and 0 <= src_i < len(srow):
                            rec[target_i] = str(srow[src_i] or "")
                    mapped_rows.append(rec)

        if mapped_rows:
            return list(mapped_rows)

        return []

    def _pick_quotation_key_for_detail(self, row: List[str]) -> Tuple[Optional[str], Optional[str]]:
        preferred = ("QUOTE_NO", "QUOTATION_NO", "QUOT_NO", "TX_KEY", "QUO_KEY", "ID")
        upper_names = [f.strip().upper() for f in self.physical_fields]
        for cand in preferred:
            try:
                idx = upper_names.index(cand)
            except ValueError:
                continue
            if idx < len(row):
                v = str(row[idx] or "").strip()
                if v:
                    return self.physical_fields[idx], v
        # 若標準鍵名都找不到，回退使用「由/至編號」對應欄位（PROGRAM.KEY_CODE）。
        if self._inv_i is not None and 0 <= self._inv_i < len(self.physical_fields):
            if self._inv_i < len(row):
                v2 = str(row[self._inv_i] or "").strip()
                if v2:
                    return self.physical_fields[self._inv_i], v2
        return None, None

    def _build_quotation_html_for_row(self, row: List[str]) -> str:
        if self.backend is None:
            raise RuntimeError("backend not available")
        key_field, key_value = self._pick_quotation_key_for_detail(row)
        if not key_field or not key_value:
            raise RuntimeError("quotation key not found")

        quotation_row: Dict[str, Any] = {}
        for i, name in enumerate(self.physical_fields):
            quotation_row[name] = str(row[i]) if i < len(row) else ""

        trx_cols, trx_rows_raw = self._load_quotation_trx_rows(row)
        qouttrx_rows: List[Dict[str, Any]] = []
        for r in trx_rows_raw:
            rec: Dict[str, Any] = {}
            for i, c in enumerate(trx_cols):
                rec[c] = str(r[i]) if i < len(r) else ""
            qouttrx_rows.append(rec)

        fd, out_path = tempfile.mkstemp(suffix=".html", prefix="wolee_quotation_")
        os.close(fd)
        render_quotation_html(
            base_dir=self.app_base_dir or os.getcwd(),
            quotation_row=quotation_row,
            qouttrx_rows=qouttrx_rows,
            output_html_path=out_path,
        )
        return out_path

    def _load_quotation_trx_rows(self, row: List[str]) -> Tuple[List[str], List[List[str]]]:
        """
        讀取 QUOTTRX/QOUTTRX 明細，依主檔鍵值過濾。
        回傳 (trx_fields, trx_rows_raw)。
        """
        if self.backend is None:
            return [], []
        key_field, key_value = self._pick_quotation_key_for_detail(row)
        if not key_field or not key_value:
            return [], []
        trx_table = ""
        for name in ("QUOTTRX", "QOUTTRX"):
            cols = self.backend.list_columns(name)
            if cols:
                trx_table = name
                break
        if not trx_table:
            return [], []
        trx_cols = self.backend.list_columns(trx_table)
        if not trx_cols:
            return [], []
        candidate_fk: List[str] = []
        key_upper = key_field.strip().upper()
        for c in trx_cols:
            if c.strip().upper() == key_upper:
                candidate_fk.append(c)
        for fallback in ("QUOTE_NO", "QUOTATION_NO", "QUOT_NO", "TX_KEY", "QUO_KEY"):
            for c in trx_cols:
                if c.strip().upper() == fallback and c not in candidate_fk:
                    candidate_fk.append(c)
        trx_rows_raw: List[List[str]] = []
        for fk in candidate_fk:
            try:
                rows = self.backend.fetch_rows_where(
                    trx_table,
                    fk,
                    key_value,
                    limit=1000,
                    column_order=trx_cols,
                )
            except Exception:
                rows = []
            if rows:
                trx_rows_raw = rows
                break
        return trx_cols, trx_rows_raw

    def _load_invoice_stk_rows(self, row: List[str]) -> Tuple[List[str], List[List[str]]]:
        """
        讀取 INVSTK 明細，依主檔鍵值過濾。
        回傳 (stk_fields, stk_rows_raw)。
        """
        if self.backend is None:
            return [], []
        key_field = None
        key_value = ""
        preferred = ("TX_KEY", "TX_NO", "INVOICE_NO", "INV_NO", "ID")
        up_fields = [f.strip().upper() for f in self.physical_fields]
        for p in preferred:
            try:
                i = up_fields.index(p)
            except ValueError:
                continue
            if i < len(row):
                v = str(row[i] or "").strip()
                if v:
                    key_field = self.physical_fields[i]
                    key_value = v
                    break
        if not key_field or not key_value:
            return [], []

        stk_table = "INVSTK"
        stk_cols = self.backend.list_columns(stk_table)
        if not stk_cols:
            return [], []
        candidate_fk: List[str] = []
        key_upper = key_field.strip().upper()
        for c in stk_cols:
            if c.strip().upper() == key_upper:
                candidate_fk.append(c)
        for fallback in ("TX_KEY", "TX_NO", "INVOICE_NO", "INV_NO"):
            for c in stk_cols:
                if c.strip().upper() == fallback and c not in candidate_fk:
                    candidate_fk.append(c)
        stk_rows_raw: List[List[str]] = []
        for fk in candidate_fk:
            try:
                rows = self.backend.fetch_rows_where(
                    stk_table,
                    fk,
                    key_value,
                    limit=1000,
                    column_order=stk_cols,
                )
            except Exception:
                rows = []
            if rows:
                stk_rows_raw = rows
                break
        return stk_cols, stk_rows_raw

    def _get_single_row_for_current_inv_filter(self) -> Optional[List[str]]:
        """
        由目前由/至編號條件反推唯一一筆主檔，供 DO_PRNQUOTATION 模板列印使用。
        只有在 from=to 且能匹配到資料時才回傳，避免誤印多筆。
        """
        if self._inv_i is None or self.backend is None:
            return None
        fi = (self._ed_inv_from.text() or "").strip()
        ti = (self._ed_inv_to.text() or "").strip()
        if not fi or fi != ti:
            return None
        rows = self._filtered_rows()
        if not rows:
            return None
        hit = [r for r in rows if self._inv_i < len(r) and str(r[self._inv_i] or "").strip() == fi]
        if len(hit) == 1:
            return list(hit[0])
        return None

    def _show_embedded_pdf_preview(self, pdf_paths: List[str], start_index: int = 0) -> bool:
        """
        以程式內嵌視窗預覽 PDF；若 Qt PDF 元件不可用則回傳 False。
        """
        if not pdf_paths:
            return False
        try:
            from PyQt6.QtPdf import QPdfDocument  # type: ignore[import-not-found]
            from PyQt6.QtPdfWidgets import QPdfView  # type: ignore[import-not-found]
        except Exception:
            return False

        dlg = QDialog(self)
        dlg.setWindowTitle("報表預覽" if self.lang == "CHN" else "Report Preview")
        dlg.resize(1100, 760)
        lay = QVBoxLayout(dlg)

        doc = QPdfDocument(dlg)
        cur_doc_i = max(0, min(len(pdf_paths) - 1, int(start_index)))
        status = doc.load(pdf_paths[cur_doc_i])
        if status != QPdfDocument.Error.None_:
            return False

        view = QPdfView(dlg)
        view.setDocument(doc)
        view.setPageMode(QPdfView.PageMode.MultiPage)
        view.setZoomMode(QPdfView.ZoomMode.FitInView)
        tools = QHBoxLayout()
        tools.setSpacing(6)
        btn_prev = QPushButton("上一頁" if self.lang == "CHN" else "Prev")
        btn_next = QPushButton("下一頁" if self.lang == "CHN" else "Next")
        btn_zoom_out = QPushButton("縮小" if self.lang == "CHN" else "Zoom -")
        btn_zoom_in = QPushButton("放大" if self.lang == "CHN" else "Zoom +")
        btn_fit = QPushButton("適合頁面" if self.lang == "CHN" else "Fit")
        btn_prev_doc = QPushButton("上一單" if self.lang == "CHN" else "Prev Doc")
        btn_next_doc = QPushButton("下一單" if self.lang == "CHN" else "Next Doc")
        lb_page = QLabel()
        lb_doc = QLabel()
        lb_zoom = QLabel()
        lb_doc.setMinimumWidth(150)
        lb_doc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lb_page.setMinimumWidth(120)
        lb_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lb_zoom.setMinimumWidth(80)
        lb_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for b in (btn_prev_doc, btn_next_doc, btn_prev, btn_next, btn_zoom_out, btn_zoom_in, btn_fit):
            self._apply_btn_style(b)
            tools.addWidget(b)
        tools.addWidget(lb_doc)
        tools.addWidget(lb_page)
        tools.addWidget(lb_zoom)
        tools.addStretch(1)
        lay.addLayout(tools)
        lay.addWidget(view)

        nav = view.pageNavigator()
        state = {"alive": True}
        page_changed_slot = None

        def _refresh_doc_label() -> None:
            lb_doc.setText(
                f"單據 {cur_doc_i + 1}/{len(pdf_paths)}"
                if self.lang == "CHN"
                else f"Doc {cur_doc_i + 1}/{len(pdf_paths)}"
            )

        def _refresh_page_label() -> None:
            if not state["alive"]:
                return
            try:
                total = max(1, doc.pageCount())
            except RuntimeError:
                return
            cur = 1
            try:
                cur = int(nav.currentPage()) + 1
            except Exception:
                pass
            lb_page.setText(
                f"第 {cur}/{total} 頁" if self.lang == "CHN" else f"Page {cur}/{total}"
            )

        def _refresh_zoom_label() -> None:
            try:
                z = float(view.zoomFactor())
            except Exception:
                z = 1.0
            lb_zoom.setText(f"{int(round(z * 100.0))}%")

        def _load_doc(i: int) -> None:
            nonlocal cur_doc_i
            if not state["alive"]:
                return
            if i < 0 or i >= len(pdf_paths):
                return
            cur_doc_i = i
            try:
                st = doc.load(pdf_paths[cur_doc_i])
            except RuntimeError:
                return
            if st == QPdfDocument.Error.None_:
                view.setZoomMode(QPdfView.ZoomMode.FitInView)
                _refresh_doc_label()
                _refresh_page_label()
                _refresh_zoom_label()

        def _jump(delta: int) -> None:
            if not state["alive"]:
                return
            try:
                total = doc.pageCount()
            except RuntimeError:
                return
            if total <= 0:
                return
            try:
                cur0 = int(nav.currentPage())
            except Exception:
                cur0 = 0
            target = max(0, min(total - 1, cur0 + delta))
            try:
                nav.jump(target, QPointF(), view.zoomFactor())
            except Exception:
                return
            _refresh_page_label()

        def _zoom(scale: float) -> None:
            if not state["alive"]:
                return
            try:
                z = float(view.zoomFactor())
            except Exception:
                z = 1.0
            z2 = max(0.2, min(4.0, z * scale))
            view.setZoomMode(QPdfView.ZoomMode.Custom)
            view.setZoomFactor(z2)
            _refresh_zoom_label()

        btn_prev.clicked.connect(lambda: _jump(-1))
        btn_next.clicked.connect(lambda: _jump(1))
        btn_zoom_out.clicked.connect(lambda: _zoom(0.8))
        btn_zoom_in.clicked.connect(lambda: _zoom(1.25))
        def _fit() -> None:
            view.setZoomMode(QPdfView.ZoomMode.FitInView)
            _refresh_zoom_label()
        btn_fit.clicked.connect(_fit)
        btn_prev_doc.clicked.connect(lambda: _load_doc(cur_doc_i - 1))
        btn_next_doc.clicked.connect(lambda: _load_doc(cur_doc_i + 1))
        try:
            def _on_page_changed(_p: int) -> None:
                _refresh_page_label()
            page_changed_slot = _on_page_changed
            nav.currentPageChanged.connect(page_changed_slot)
        except Exception:
            page_changed_slot = None
        _refresh_doc_label()
        _refresh_page_label()
        _refresh_zoom_label()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dlg)
        btns.rejected.connect(dlg.reject)
        btns.accepted.connect(dlg.accept)
        lay.addWidget(btns)
        def _on_dlg_finished(_code: int) -> None:
            state["alive"] = False
            if page_changed_slot is not None:
                try:
                    nav.currentPageChanged.disconnect(page_changed_slot)
                except Exception:
                    pass
        dlg.finished.connect(_on_dlg_finished)
        dlg.exec()
        return True

    def _on_preview(self) -> None:
        rpt_proc_selected = self._selected_rpt_proc().upper()
        if rpt_proc_selected == "DO_PRNINVOICE":
            rows = self._filtered_rows()
            if not rows:
                QMessageBox.information(
                    self,
                    "預覽" if self.lang == "CHN" else "Preview",
                    "在目前由/至編號與日期條件下，沒有可預覽的發票資料。"
                    if self.lang == "CHN"
                    else "No invoice records match current number/date filters.",
                )
                return
            if not self.app_base_dir:
                QMessageBox.warning(
                    self,
                    "預覽" if self.lang == "CHN" else "Preview",
                    "無法取得程式目錄，無法載入 Invoice.xlsx。"
                    if self.lang == "CHN"
                    else "App directory missing; cannot load Invoice.xlsx.",
                )
                return
            pdf_paths: List[str] = []
            first_err = ""
            for src in rows:
                row = list(src)
                stk_fields, stk_rows = self._load_invoice_stk_rows(row)
                ok, msg, pdf_path = generate_invoice_pdf_from_template(
                    self.app_base_dir,
                    self.physical_fields,
                    row,
                    stk_fields,
                    stk_rows,
                    self.lang,
                )
                if ok and pdf_path:
                    pdf_paths.append(pdf_path)
                elif not first_err:
                    first_err = msg
            if not pdf_paths:
                QMessageBox.warning(self, "預覽" if self.lang == "CHN" else "Preview", first_err or "預覽失敗。")
                return
            shown = self._show_embedded_pdf_preview(pdf_paths, 0)
            for p in pdf_paths:
                try:
                    os.remove(p)
                except OSError:
                    pass
            if not shown:
                QMessageBox.warning(
                    self,
                    "預覽" if self.lang == "CHN" else "Preview",
                    "目前環境不支援內嵌 PDF 預覽（缺少 Qt PDF 元件）。"
                    if self.lang == "CHN"
                    else "Embedded PDF preview is unavailable (Qt PDF components missing).",
                )
            return
        if rpt_proc_selected in ("DO_PRNQUOTATION", "DO_PRNQUOTATION1"):
            rows = self._filtered_rows()
            if not rows:
                QMessageBox.information(
                    self,
                    "預覽" if self.lang == "CHN" else "Preview",
                    "在目前由/至編號與日期條件下，沒有可預覽的報價資料。"
                    if self.lang == "CHN"
                    else "No quotation records match current number/date filters.",
                )
                return
            if not self.app_base_dir:
                tpl_name = (
                    "Quotation1.xlsx"
                    if rpt_proc_selected == "DO_PRNQUOTATION1"
                    else "Quotation.xlsx"
                )
                QMessageBox.warning(
                    self,
                    "預覽" if self.lang == "CHN" else "Preview",
                    f"無法取得程式目錄，無法載入 {tpl_name}。"
                    if self.lang == "CHN"
                    else f"App directory missing; cannot load {tpl_name}.",
                )
                return
            pdf_paths: List[str] = []
            first_err = ""
            gen_fn = (
                generate_quotation1_pdf_from_template
                if rpt_proc_selected == "DO_PRNQUOTATION1"
                else generate_quotation_pdf_from_template
            )
            for src in rows:
                row = list(src)
                trx_fields, trx_rows = self._load_quotation_trx_rows(row)
                ok, msg, pdf_path = gen_fn(
                    self.app_base_dir,
                    self.physical_fields,
                    row,
                    trx_fields,
                    trx_rows,
                    self.lang,
                )
                if ok and pdf_path:
                    pdf_paths.append(pdf_path)
                elif not first_err:
                    first_err = msg
            if not pdf_paths:
                QMessageBox.warning(self, "預覽" if self.lang == "CHN" else "Preview", first_err or "預覽失敗。")
                return
            shown = self._show_embedded_pdf_preview(pdf_paths, 0)
            for p in pdf_paths:
                try:
                    os.remove(p)
                except OSError:
                    pass
            if not shown:
                QMessageBox.warning(
                    self,
                    "預覽" if self.lang == "CHN" else "Preview",
                    "目前環境不支援內嵌 PDF 預覽（缺少 Qt PDF 元件）。"
                    if self.lang == "CHN"
                    else "Embedded PDF preview is unavailable (Qt PDF components missing).",
                )
            return

        doc, _ = self._doc_html(for_print_per_page_header=True)
        pr = self._make_printer()
        dlg = QPrintPreviewDialog(pr, self)
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            ag = screen.availableGeometry()
            dlg.resize(int(ag.width() * 0.9), int(ag.height() * 0.88))
        pv = dlg.findChild(QPrintPreviewWidget)
        if pv is not None:
            pv.setZoomFactor(1.0)
        dlg.paintRequested.connect(lambda p: self._print_document_with_page_footer(doc, p))
        dlg.exec()

    def _on_print(self) -> None:
        # 只要下拉選到 DO_PRNQUOTATION / DO_PRNQUOTATION1，就優先走報價單模板列印，避免誤走清單表格列印。
        # DO_PRNQUOTATION → Quotation.xlsx；DO_PRNQUOTATION1 → Quotation1.xlsx
        rpt_proc_selected = self._selected_rpt_proc().upper()
        if not rpt_proc_selected:
            QMessageBox.warning(
                self,
                "列印" if self.lang == "CHN" else "Print",
                "所選報表沒有對應的 RPT_PROC，請檢查 SYS_DATA.REPORT 設定。"
                if self.lang == "CHN"
                else "Selected report has no mapped RPT_PROC. Please check SYS_DATA.REPORT.",
            )
            return
        if rpt_proc_selected == "DO_PRNINVOICE":
            rows = self._filtered_rows()
            if not rows:
                QMessageBox.information(
                    self,
                    "列印" if self.lang == "CHN" else "Print",
                    "在目前由/至編號與日期條件下，沒有可列印的發票資料。"
                    if self.lang == "CHN"
                    else "No invoice records match current number/date filters.",
                )
                return
            if not self.app_base_dir:
                QMessageBox.warning(
                    self,
                    "列印" if self.lang == "CHN" else "Print",
                    "無法取得程式目錄，無法載入 Invoice.xlsx。"
                    if self.lang == "CHN"
                    else "App directory missing; cannot load Invoice.xlsx.",
                )
                return
            total = len(rows)
            ok_count = 0
            last_err = ""
            for src in rows:
                row = list(src)
                stk_fields, stk_rows = self._load_invoice_stk_rows(row)
                ok, msg = print_invoice_xls(
                    self.app_base_dir,
                    self.physical_fields,
                    row,
                    stk_fields,
                    stk_rows,
                    self.lang,
                )
                if ok:
                    ok_count += 1
                else:
                    last_err = msg
            if ok_count == total:
                QMessageBox.information(
                    self,
                    "列印" if self.lang == "CHN" else "Print",
                    f"已按條件列印 {ok_count} 筆發票。"
                    if self.lang == "CHN"
                    else f"Printed {ok_count} invoice report(s) by current filters.",
                )
            elif ok_count == 0:
                QMessageBox.warning(
                    self,
                    "列印" if self.lang == "CHN" else "Print",
                    last_err or ("列印失敗。" if self.lang == "CHN" else "Printing failed."),
                )
            else:
                QMessageBox.warning(
                    self,
                    "列印" if self.lang == "CHN" else "Print",
                    f"共 {total} 筆，成功 {ok_count} 筆，失敗 {total - ok_count} 筆。\n{last_err}"
                    if self.lang == "CHN"
                    else f"Total {total}, succeeded {ok_count}, failed {total - ok_count}.\n{last_err}",
                )
            return
        if rpt_proc_selected in ("DO_PRNQUOTATION", "DO_PRNQUOTATION1"):
            rows = self._filtered_rows()
            if not rows:
                QMessageBox.information(
                    self,
                    "列印" if self.lang == "CHN" else "Print",
                    "在目前由/至編號與日期條件下，沒有可列印的報價資料。"
                    if self.lang == "CHN"
                    else "No quotation records match current number/date filters.",
                )
                return
            if not self.app_base_dir:
                tpl_name = (
                    "Quotation1.xlsx"
                    if rpt_proc_selected == "DO_PRNQUOTATION1"
                    else "Quotation.xlsx"
                )
                QMessageBox.warning(
                    self,
                    "列印" if self.lang == "CHN" else "Print",
                    f"無法取得程式目錄，無法載入 {tpl_name}。"
                    if self.lang == "CHN"
                    else f"App directory missing; cannot load {tpl_name}.",
                )
                return
            total = len(rows)
            ok_count = 0
            last_err = ""
            print_fn = (
                print_quotation1_xls
                if rpt_proc_selected == "DO_PRNQUOTATION1"
                else print_quotation_xls
            )
            for src in rows:
                row = list(src)
                trx_fields, trx_rows = self._load_quotation_trx_rows(row)
                ok, msg = print_fn(
                    self.app_base_dir,
                    self.physical_fields,
                    row,
                    trx_fields,
                    trx_rows,
                    self.lang,
                )
                if ok:
                    ok_count += 1
                else:
                    last_err = msg
            if ok_count == total:
                QMessageBox.information(
                    self,
                    "列印" if self.lang == "CHN" else "Print",
                    f"已按條件列印 {ok_count} 筆報價單。"
                    if self.lang == "CHN"
                    else f"Printed {ok_count} quotation report(s) by current filters.",
                )
            elif ok_count == 0:
                QMessageBox.warning(
                    self,
                    "列印" if self.lang == "CHN" else "Print",
                    last_err or ("列印失敗。" if self.lang == "CHN" else "Printing failed."),
                )
            else:
                QMessageBox.warning(
                    self,
                    "列印" if self.lang == "CHN" else "Print",
                    f"共 {total} 筆，成功 {ok_count} 筆，失敗 {total - ok_count} 筆。\n{last_err}"
                    if self.lang == "CHN"
                    else f"Total {total}, succeeded {ok_count}, failed {total - ok_count}.\n{last_err}",
                )
            return

        if self._quotation_xls_mode:
            row = list(self._quotation_current_row) if self._quotation_current_row is not None else None
            if row is None:
                QMessageBox.information(
                    self,
                    "列印" if self.lang == "CHN" else "Print",
                    "請先在清單選取一筆報價資料再列印。"
                    if self.lang == "CHN"
                    else "Please select one quotation row before printing.",
                )
                return
            rpt_proc = rpt_proc_selected
            if rpt_proc in ("DO_PRNQUOTATION", "DO_PRNQUOTATION1"):
                if not self.app_base_dir:
                    tpl_name = (
                        "Quotation1.xlsx"
                        if rpt_proc == "DO_PRNQUOTATION1"
                        else "Quotation.xlsx"
                    )
                    QMessageBox.warning(
                        self,
                        "列印" if self.lang == "CHN" else "Print",
                        f"無法取得程式目錄，無法載入 {tpl_name}。"
                        if self.lang == "CHN"
                        else f"App directory missing; cannot load {tpl_name}.",
                    )
                    return
                trx_fields, trx_rows = self._load_quotation_trx_rows(row)
                print_fn = (
                    print_quotation1_xls
                    if rpt_proc == "DO_PRNQUOTATION1"
                    else print_quotation_xls
                )
                ok, msg = print_fn(
                    self.app_base_dir,
                    self.physical_fields,
                    row,
                    trx_fields,
                    trx_rows,
                    self.lang,
                )
                if ok:
                    QMessageBox.information(self, "列印" if self.lang == "CHN" else "Print", msg)
                else:
                    QMessageBox.warning(self, "列印" if self.lang == "CHN" else "Print", msg)
                return

        doc, _ = self._doc_html(for_print_per_page_header=True)
        pr = self._make_printer()
        dlg = QPrintDialog(pr, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._print_document_with_page_footer(doc, pr)

    def _on_export_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "PDF",
            "",
            "PDF (*.pdf)",
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        doc, _ = self._doc_html(for_print_per_page_header=True)
        pr = self._make_printer()
        pr.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        pr.setOutputFileName(path)
        self._print_document_with_page_footer(doc, pr)
        QMessageBox.information(
            self,
            "OK",
            f"已匯出：{path}" if self.lang == "CHN" else f"Exported: {path}",
        )

    def _on_export_xlsx(self) -> None:
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Alignment
        except ImportError:
            QMessageBox.warning(
                self,
                "XLSX",
                "請安裝 openpyxl：pip install openpyxl"
                if self.lang == "CHN"
                else "Please install openpyxl: pip install openpyxl",
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "XLSX",
            "",
            "Excel (*.xlsx)",
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        specs = self._active_specs()
        rows = self._filtered_rows()
        headers, body, totals, align_right_cols = self._project_rows(specs, rows)
        right_global = set(align_right_cols or [])
        align_right = Alignment(horizontal="right")
        align_left = Alignment(horizontal="left")
        wb = Workbook()
        chunks = _chunk_report_columns(
            headers, body, totals, LIST_PRINT_COLS_PER_PAGE
        )
        offset = 0
        for ci, (h, b, t) in enumerate(chunks):
            name = f"P{ci + 1}"
            if ci == 0:
                ws = wb.active
                ws.title = name
            else:
                ws = wb.create_sheet(name)
            ws.append(h)
            hr = ws.max_row
            for j in range(len(h)):
                ag = align_right if (offset + j) in right_global else align_left
                ws.cell(hr, j + 1).alignment = ag
            for line in b:
                ws.append(line)
                rr = ws.max_row
                for j in range(len(line)):
                    ag = align_right if (offset + j) in right_global else align_left
                    ws.cell(rr, j + 1).alignment = ag
            if t and any(str(x).strip() for x in t):
                tr = list(t)
                if ci == 0:
                    tr[0] = "合計" if self.lang == "CHN" else "Total"
                ws.append(tr)
                rr = ws.max_row
                for j in range(len(tr)):
                    ag = align_right if (offset + j) in right_global else align_left
                    ws.cell(rr, j + 1).alignment = ag
            offset += len(h)
        wb.save(path)
        QMessageBox.information(
            self,
            "OK",
            f"已匯出：{path}" if self.lang == "CHN" else f"Exported: {path}",
        )

    def _on_export_docx(self) -> None:
        try:
            from docx import Document
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.shared import Pt
        except ImportError:
            QMessageBox.warning(
                self,
                "DOCX",
                "請安裝 python-docx：pip install python-docx"
                if self.lang == "CHN"
                else "Please install python-docx: pip install python-docx",
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "DOCX",
            "",
            "Word (*.docx)",
        )
        if not path:
            return
        if not path.lower().endswith(".docx"):
            path += ".docx"
        specs = self._active_specs()
        rows = self._filtered_rows()
        headers, body, totals, align_right_cols = self._project_rows(specs, rows)
        right_global = set(align_right_cols or [])
        doc = Document()
        title = self._cmb_report.currentText()
        chunks = _chunk_report_columns(
            headers, body, totals, LIST_PRINT_COLS_PER_PAGE
        )
        cpp = LIST_PRINT_COLS_PER_PAGE
        offset = 0
        for ci, (h, b, t) in enumerate(chunks):
            if ci > 0:
                doc.add_page_break()
            if ci == 0:
                h1 = doc.add_heading(title, level=1)
                h1.runs[0].font.size = Pt(14)
            else:
                is_chn = self.lang == "CHN"
                start = ci * cpp + 1
                end = start + len(h) - 1
                lab = f"欄 {start}–{end}" if is_chn else f"Columns {start}-{end}"
                h2 = doc.add_heading(lab, level=2)
                h2.runs[0].font.size = Pt(12)
            nrows = 1 + len(b) + (1 if t and any(str(x).strip() for x in t) else 0)
            ncols = max(1, len(h))
            table = doc.add_table(rows=nrows, cols=ncols)
            table.style = "Table Grid"
            hdr_cells = table.rows[0].cells
            for i, ht in enumerate(h):
                hdr_cells[i].text = str(ht)
                para = hdr_cells[i].paragraphs[0]
                para.alignment = (
                    WD_ALIGN_PARAGRAPH.RIGHT
                    if (offset + i) in right_global
                    else WD_ALIGN_PARAGRAPH.LEFT
                )
            for ri, line in enumerate(b):
                row_cells = table.rows[ri + 1].cells
                for cj, cell in enumerate(line):
                    if cj < len(row_cells):
                        row_cells[cj].text = str(cell)
                        para = row_cells[cj].paragraphs[0]
                        para.alignment = (
                            WD_ALIGN_PARAGRAPH.RIGHT
                            if (offset + cj) in right_global
                            else WD_ALIGN_PARAGRAPH.LEFT
                        )
            if t and any(str(x).strip() for x in t):
                tr = list(t)
                if ci == 0:
                    tr[0] = "合計" if self.lang == "CHN" else "Total"
                last = table.rows[len(b) + 1].cells
                for cj in range(ncols):
                    last[cj].text = str(tr[cj]) if cj < len(tr) else ""
                    para = last[cj].paragraphs[0]
                    para.alignment = (
                        WD_ALIGN_PARAGRAPH.RIGHT
                        if (offset + cj) in right_global
                        else WD_ALIGN_PARAGRAPH.LEFT
                    )
            offset += len(h)
        doc.save(path)
        QMessageBox.information(
            self,
            "OK",
            f"已匯出：{path}" if self.lang == "CHN" else f"Exported: {path}",
        )

    def _report_plain_text_for_clipboard(self) -> str:
        """Tab 分隔，供貼入郵件／Excel；避免 mailto 超過系統 URL 長度。"""
        specs = self._active_specs()
        rows = self._filtered_rows()
        headers, body, totals, _align_right_cols = self._project_rows(specs, rows)
        title = self._cmb_report.currentText()
        lines: List[str] = [title, ""]
        lines.append("\t".join(str(h) for h in headers))
        for line in body:
            lines.append("\t".join(str(c) for c in line))
        if totals and any(str(t).strip() for t in totals):
            tr = list(totals)
            tr[0] = "合計" if self.lang == "CHN" else "Total"
            lines.append("\t".join(str(c) for c in tr))
        return "\n".join(lines)

    def _on_email(self) -> None:
        plain = self._report_plain_text_for_clipboard()
        QGuiApplication.clipboard().setText(plain)

        n = len(self._filtered_rows())
        if self.lang == "CHN":
            short_body = (
                f"報表全文（Tab 分隔）已複製到剪貼簿，請在郵件本文按 Ctrl+V 貼上。\n"
                f"篩選後約 {n} 筆。"
            )
        else:
            short_body = (
                f"Full report (tab-separated) is on the clipboard; paste with Ctrl+V.\n"
                f"About {n} row(s) after filters."
            )

        sub = urllib.parse.quote(self._cmb_report.currentText()[:180])
        body_q = urllib.parse.quote(short_body[:600])
        url = QUrl(f"mailto:?subject={sub}&body={body_q}")
        opened = QDesktopServices.openUrl(url)
        title = "電郵" if self.lang == "CHN" else "Email"
        if not opened:
            msg = (
                "無法開啟預設郵件程式（可能未安裝或未關聯 mailto）。\n"
                "報表全文已複製到剪貼簿，請手動開啟郵件並貼上。"
                if self.lang == "CHN"
                else "Could not open the default mail program (none installed or mailto not associated).\n"
                "The full report is on the clipboard — open your mail app and paste."
            )
            QMessageBox.warning(self, title, msg)

    # region Web / headless API

    def _report_rpt_type_at(self, index: int) -> str:
        ent = self._cmb_report.itemData(index)
        if not isinstance(ent, dict):
            return ""
        return str(ent.get("RPT_TYPE") or "").strip()

    def to_web_init_dict(self) -> dict:
        reports: List[Dict[str, Any]] = []
        for i in range(self._cmb_report.count()):
            reports.append(
                {
                    "index": i,
                    "title": self._cmb_report.itemText(i),
                    "rpt_type": self._report_rpt_type_at(i),
                }
            )
        printers: List[Dict[str, Any]] = []
        for i in range(self._cmb_printer.count()):
            printers.append({"index": i, "name": self._cmb_printer.itemText(i)})
        out: Dict[str, Any] = {
            "no_report": self._no_report,
            "doc_no_label": self._doc_no_label(),
            "reports": reports,
            "printers": printers,
            "report_index": self._cmb_report.currentIndex(),
            "printer_index": self._cmb_printer.currentIndex(),
            "inv_from": self._ed_inv_from.text(),
            "inv_to": self._ed_inv_to.text(),
            "date_from": self._ed_date_from.text(),
            "date_to": self._ed_date_to.text(),
            "lang": self.lang,
            "is_list": self._selected_report_is_list(),
            "is_document": self._selected_report_is_document(),
            "is_finance": self._selected_report_is_finance(),
        }
        if self._no_report:
            out["message"] = "沒有可列印的報表 !\nNo Report Print !"
        return out

    def web_pick_rows_dict(self) -> dict:
        """與 _pick_doc_no_into 相同資料來源（依目前報表 RPT_SQL / 主檔）。"""
        is_chn = self.lang == "CHN"
        if self._inv_i is None:
            return {
                "ok": False,
                "message": (
                    "找不到可選擇的主編號欄位。"
                    if is_chn
                    else "Cannot find a key number column."
                ),
            }
        cols, src_idx, rows, headers = self._pick_grid_rows_payload()
        if not rows:
            return {
                "ok": False,
                "message": (
                    "目前沒有可選擇的資料。"
                    if is_chn
                    else "No records available."
                ),
            }
        display_rows: List[List[str]] = []
        key_values: List[str] = []
        for rec in rows:
            rendered: List[str] = []
            for c, pi in enumerate(src_idx):
                raw = rec[pi] if pi < len(rec) else ""
                fname = cols[c] if c < len(cols) else ""
                dfmt = self.data_dict.get_data_format(self.table_name, fname)
                dtyp = self.data_dict.get_data_type(self.table_name, fname)
                rendered.append(format_cell_display(fname, raw, dfmt, dtyp))
            display_rows.append(rendered)
            key_values.append(self._pick_key_from_rec(rec))
        columns = [
            {"name": cols[i], "title": headers[i] or cols[i]} for i in range(len(cols))
        ]
        return {
            "ok": True,
            "fields": cols,
            "columns": columns,
            "rows": display_rows,
            "key_values": key_values,
        }

    def apply_web_params(self, params: dict) -> None:
        ri = params.get("report_index")
        if ri is not None:
            idx = int(ri)
            self._cmb_report.blockSignals(True)
            try:
                if 0 <= idx < self._cmb_report.count():
                    self._cmb_report.setCurrentIndex(idx)
            finally:
                self._cmb_report.blockSignals(False)
        pi = params.get("printer_index")
        if pi is not None:
            pidx = int(pi)
            if 0 <= pidx < self._cmb_printer.count():
                self._cmb_printer.setCurrentIndex(pidx)
        if "inv_from" in params:
            self._ed_inv_from.setText(str(params.get("inv_from") or ""))
        if "inv_to" in params:
            self._ed_inv_to.setText(str(params.get("inv_to") or ""))
        if "date_from" in params:
            self._ed_date_from.setText(str(params.get("date_from") or ""))
            self._on_print_date_from_changed(self._ed_date_from.text())
        if "date_to" in params:
            self._ed_date_to.setText(str(params.get("date_to") or ""))

    def apply_web_params_for_pick(self, params: dict) -> None:
        """編號選取：僅同步報表，避免 apply_web_params 觸發日期/預設值副作用。"""
        ri = params.get("report_index")
        if ri is None:
            return
        idx = int(ri)
        self._cmb_report.blockSignals(True)
        try:
            if 0 <= idx < self._cmb_report.count():
                self._cmb_report.setCurrentIndex(idx)
        finally:
            self._cmb_report.blockSignals(False)

    def _pick_grid_rows_payload(self) -> Tuple[List[str], List[int], List[List[str]], List[str]]:
        """與 _pick_doc_no_into 相同：GRID 投影欄位 + 報表列 + 表頭標題。"""
        cols, src_idx = self.data_dict.grid_display_projection(
            self.table_name, self.physical_fields
        )
        if not cols:
            cols = list(self.physical_fields)
            src_idx = list(range(len(cols)))
        rows = [list(r) for r in self._rows_for_selected_report()]
        headers = [self.data_dict.get_title(self.table_name, c, self.lang) for c in cols]
        return cols, src_idx, rows, headers

    def _pick_key_from_rec(self, rec: List[str]) -> str:
        if self._inv_i is not None and self._inv_i < len(rec):
            v = str(rec[self._inv_i] or "").strip()
            if v:
                return v
        return ""

    def web_preview(self) -> dict:
        rpt_proc_selected = self._selected_rpt_proc().upper()
        is_chn = self.lang == "CHN"
        if rpt_proc_selected == "DO_PRNINVOICE":
            rows = self._filtered_rows()
            if not rows:
                msg = (
                    "在目前由/至編號與日期條件下，沒有可預覽的發票資料。"
                    if is_chn
                    else "No invoice records match current number/date filters."
                )
                return {"ok": False, "message": msg, "kind": "pdf"}
            if not self.app_base_dir:
                msg = (
                    "無法取得程式目錄，無法載入 Invoice.xlsx。"
                    if is_chn
                    else "App directory missing; cannot load Invoice.xlsx."
                )
                return {"ok": False, "message": msg, "kind": "pdf"}
            pdf_paths: List[str] = []
            first_err = ""
            for src in rows:
                row = list(src)
                stk_fields, stk_rows = self._load_invoice_stk_rows(row)
                ok, msg, pdf_path = generate_invoice_pdf_from_template(
                    self.app_base_dir,
                    self.physical_fields,
                    row,
                    stk_fields,
                    stk_rows,
                    self.lang,
                )
                if ok and pdf_path:
                    pdf_paths.append(pdf_path)
                elif not first_err:
                    first_err = msg
            if not pdf_paths:
                return {"ok": False, "message": first_err or "預覽失敗。", "kind": "pdf"}
            return self._preview_pdf_response(pdf_paths)
        if rpt_proc_selected in ("DO_PRNQUOTATION", "DO_PRNQUOTATION1"):
            rows = self._filtered_rows()
            if not rows:
                msg = (
                    "在目前由/至編號與日期條件下，沒有可預覽的報價資料。"
                    if is_chn
                    else "No quotation records match current number/date filters."
                )
                return {"ok": False, "message": msg, "kind": "pdf"}
            if not self.app_base_dir:
                tpl_name = (
                    "Quotation1.xlsx"
                    if rpt_proc_selected == "DO_PRNQUOTATION1"
                    else "Quotation.xlsx"
                )
                msg = (
                    f"無法取得程式目錄，無法載入 {tpl_name}。"
                    if is_chn
                    else f"App directory missing; cannot load {tpl_name}."
                )
                return {"ok": False, "message": msg, "kind": "pdf"}
            pdf_paths = []
            first_err = ""
            gen_fn = (
                generate_quotation1_pdf_from_template
                if rpt_proc_selected == "DO_PRNQUOTATION1"
                else generate_quotation_pdf_from_template
            )
            for src in rows:
                row = list(src)
                trx_fields, trx_rows = self._load_quotation_trx_rows(row)
                ok, msg, pdf_path = gen_fn(
                    self.app_base_dir,
                    self.physical_fields,
                    row,
                    trx_fields,
                    trx_rows,
                    self.lang,
                )
                if ok and pdf_path:
                    pdf_paths.append(pdf_path)
                elif not first_err:
                    first_err = msg
            if not pdf_paths:
                return {"ok": False, "message": first_err or "預覽失敗。", "kind": "pdf"}
            return self._preview_pdf_response(pdf_paths)
        ok, msg, pdf_data = self._render_document_pdf_bytes()
        if not ok:
            return {"ok": False, "message": msg, "kind": "pdf"}
        b64 = base64.b64encode(pdf_data).decode("ascii")
        return {"ok": True, "message": "", "kind": "pdf", "pdfs_base64": [b64]}

    def _render_document_pdf_bytes(
        self, *, fail_label: Optional[str] = None
    ) -> Tuple[bool, str, bytes]:
        """與 Windows QPrintPreviewDialog / 匯出 PDF 相同之排版（含頁首、頁尾、方向）。"""
        is_chn = self.lang == "CHN"
        default_fail = "預覽失敗。" if is_chn else "Preview failed."
        fd, path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        try:
            doc, _ = self._doc_html(for_print_per_page_header=True)
            pr = self._make_printer()
            pr.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            pr.setOutputFileName(path)
            self._print_document_with_page_footer(doc, pr)
            with open(path, "rb") as f:
                data = f.read()
            return True, "", data
        except Exception as exc:
            msg = str(exc) or fail_label or default_fail
            return False, msg, b""
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    def _preview_pdf_response(self, pdf_paths: List[str]) -> dict:
        b64_list: List[str] = []
        for p in pdf_paths:
            try:
                with open(p, "rb") as f:
                    b64_list.append(base64.b64encode(f.read()).decode("ascii"))
            finally:
                try:
                    os.remove(p)
                except OSError:
                    pass
        if not b64_list:
            is_chn = self.lang == "CHN"
            return {
                "ok": False,
                "message": "預覽失敗。" if is_chn else "Preview failed.",
                "kind": "pdf",
            }
        return {"ok": True, "message": "", "kind": "pdf", "pdfs_base64": b64_list}

    def web_print(self) -> Tuple[bool, str]:
        is_chn = self.lang == "CHN"
        rpt_proc_selected = self._selected_rpt_proc().upper()
        if not rpt_proc_selected:
            msg = (
                "所選報表沒有對應的 RPT_PROC，請檢查 SYS_DATA.REPORT 設定。"
                if is_chn
                else "Selected report has no mapped RPT_PROC. Please check SYS_DATA.REPORT."
            )
            return False, msg
        if rpt_proc_selected == "DO_PRNINVOICE":
            rows = self._filtered_rows()
            if not rows:
                msg = (
                    "在目前由/至編號與日期條件下，沒有可列印的發票資料。"
                    if is_chn
                    else "No invoice records match current number/date filters."
                )
                return False, msg
            if not self.app_base_dir:
                msg = (
                    "無法取得程式目錄，無法載入 Invoice.xlsx。"
                    if is_chn
                    else "App directory missing; cannot load Invoice.xlsx."
                )
                return False, msg
            total = len(rows)
            ok_count = 0
            last_err = ""
            for src in rows:
                row = list(src)
                stk_fields, stk_rows = self._load_invoice_stk_rows(row)
                ok, msg = print_invoice_xls(
                    self.app_base_dir,
                    self.physical_fields,
                    row,
                    stk_fields,
                    stk_rows,
                    self.lang,
                )
                if ok:
                    ok_count += 1
                else:
                    last_err = msg
            if ok_count == total:
                return True, (
                    f"已按條件列印 {ok_count} 筆發票。"
                    if is_chn
                    else f"Printed {ok_count} invoice report(s) by current filters."
                )
            if ok_count == 0:
                return False, last_err or ("列印失敗。" if is_chn else "Printing failed.")
            return False, (
                f"共 {total} 筆，成功 {ok_count} 筆，失敗 {total - ok_count} 筆。\n{last_err}"
                if is_chn
                else f"Total {total}, succeeded {ok_count}, failed {total - ok_count}.\n{last_err}"
            )
        if rpt_proc_selected in ("DO_PRNQUOTATION", "DO_PRNQUOTATION1"):
            rows = self._filtered_rows()
            if not rows:
                msg = (
                    "在目前由/至編號與日期條件下，沒有可列印的報價資料。"
                    if is_chn
                    else "No quotation records match current number/date filters."
                )
                return False, msg
            if not self.app_base_dir:
                tpl_name = (
                    "Quotation1.xlsx"
                    if rpt_proc_selected == "DO_PRNQUOTATION1"
                    else "Quotation.xlsx"
                )
                msg = (
                    f"無法取得程式目錄，無法載入 {tpl_name}。"
                    if is_chn
                    else f"App directory missing; cannot load {tpl_name}."
                )
                return False, msg
            total = len(rows)
            ok_count = 0
            last_err = ""
            print_fn = (
                print_quotation1_xls
                if rpt_proc_selected == "DO_PRNQUOTATION1"
                else print_quotation_xls
            )
            for src in rows:
                row = list(src)
                trx_fields, trx_rows = self._load_quotation_trx_rows(row)
                ok, msg = print_fn(
                    self.app_base_dir,
                    self.physical_fields,
                    row,
                    trx_fields,
                    trx_rows,
                    self.lang,
                )
                if ok:
                    ok_count += 1
                else:
                    last_err = msg
            if ok_count == total:
                return True, (
                    f"已按條件列印 {ok_count} 筆報價單。"
                    if is_chn
                    else f"Printed {ok_count} quotation report(s) by current filters."
                )
            if ok_count == 0:
                return False, last_err or ("列印失敗。" if is_chn else "Printing failed.")
            return False, (
                f"共 {total} 筆，成功 {ok_count} 筆，失敗 {total - ok_count} 筆。\n{last_err}"
                if is_chn
                else f"Total {total}, succeeded {ok_count}, failed {total - ok_count}.\n{last_err}"
            )
        if self._quotation_xls_mode:
            row = (
                list(self._quotation_current_row)
                if self._quotation_current_row is not None
                else None
            )
            if row is None:
                msg = (
                    "請先在清單選取一筆報價資料再列印。"
                    if is_chn
                    else "Please select one quotation row before printing."
                )
                return False, msg
            if rpt_proc_selected in ("DO_PRNQUOTATION", "DO_PRNQUOTATION1"):
                if not self.app_base_dir:
                    tpl_name = (
                        "Quotation1.xlsx"
                        if rpt_proc_selected == "DO_PRNQUOTATION1"
                        else "Quotation.xlsx"
                    )
                    msg = (
                        f"無法取得程式目錄，無法載入 {tpl_name}。"
                        if is_chn
                        else f"App directory missing; cannot load {tpl_name}."
                    )
                    return False, msg
                trx_fields, trx_rows = self._load_quotation_trx_rows(row)
                print_fn = (
                    print_quotation1_xls
                    if rpt_proc_selected == "DO_PRNQUOTATION1"
                    else print_quotation_xls
                )
                return print_fn(
                    self.app_base_dir,
                    self.physical_fields,
                    row,
                    trx_fields,
                    trx_rows,
                    self.lang,
                )
        doc, _ = self._doc_html(for_print_per_page_header=True)
        pr = self._make_printer()
        self._print_document_with_page_footer(doc, pr)
        return True, "已送出列印。" if is_chn else "Print job sent."

    def web_export_pdf(self) -> Tuple[bool, str, bytes]:
        is_chn = self.lang == "CHN"
        return self._render_document_pdf_bytes(
            fail_label="匯出 PDF 失敗。" if is_chn else "PDF export failed."
        )

    def web_email_text(self) -> dict:
        is_chn = self.lang == "CHN"
        plain = self._report_plain_text_for_clipboard()
        n = len(self._filtered_rows())
        if is_chn:
            hint = (
                f"報表全文（Tab 分隔）已複製到剪貼簿，請在郵件本文按 Ctrl+V 貼上。\n"
                f"篩選後約 {n} 筆。"
            )
        else:
            hint = (
                f"Full report (tab-separated) is on the clipboard; paste with Ctrl+V.\n"
                f"About {n} row(s) after filters."
            )
        return {
            "subject": self._cmb_report.currentText(),
            "plain_text": plain,
            "hint": hint,
        }

    def web_export_xlsx(self) -> Tuple[bool, str, bytes]:
        is_chn = self.lang == "CHN"
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Alignment
        except ImportError:
            msg = (
                "請安裝 openpyxl：pip install openpyxl"
                if is_chn
                else "Please install openpyxl: pip install openpyxl"
            )
            return False, msg, b""
        specs = self._active_specs()
        rows = self._filtered_rows()
        headers, body, totals, align_right_cols = self._project_rows(specs, rows)
        right_global = set(align_right_cols or [])
        align_right = Alignment(horizontal="right")
        align_left = Alignment(horizontal="left")
        wb = Workbook()
        chunks = _chunk_report_columns(headers, body, totals, LIST_PRINT_COLS_PER_PAGE)
        offset = 0
        for ci, (h, b, t) in enumerate(chunks):
            name = f"P{ci + 1}"
            if ci == 0:
                ws = wb.active
                ws.title = name
            else:
                ws = wb.create_sheet(name)
            ws.append(h)
            hr = ws.max_row
            for j in range(len(h)):
                ag = align_right if (offset + j) in right_global else align_left
                ws.cell(hr, j + 1).alignment = ag
            for line in b:
                ws.append(line)
                rr = ws.max_row
                for j in range(len(line)):
                    ag = align_right if (offset + j) in right_global else align_left
                    ws.cell(rr, j + 1).alignment = ag
            if t and any(str(x).strip() for x in t):
                tr = list(t)
                if ci == 0:
                    tr[0] = "合計" if is_chn else "Total"
                ws.append(tr)
                rr = ws.max_row
                for j in range(len(tr)):
                    ag = align_right if (offset + j) in right_global else align_left
                    ws.cell(rr, j + 1).alignment = ag
            offset += len(h)
        buf = io.BytesIO()
        wb.save(buf)
        return True, "", buf.getvalue()

    def web_export_docx(self) -> Tuple[bool, str, bytes]:
        is_chn = self.lang == "CHN"
        try:
            from docx import Document
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.shared import Pt
        except ImportError:
            msg = (
                "請安裝 python-docx：pip install python-docx"
                if is_chn
                else "Please install python-docx: pip install python-docx"
            )
            return False, msg, b""
        specs = self._active_specs()
        rows = self._filtered_rows()
        headers, body, totals, align_right_cols = self._project_rows(specs, rows)
        right_global = set(align_right_cols or [])
        doc = Document()
        title = self._cmb_report.currentText()
        chunks = _chunk_report_columns(headers, body, totals, LIST_PRINT_COLS_PER_PAGE)
        cpp = LIST_PRINT_COLS_PER_PAGE
        offset = 0
        for ci, (h, b, t) in enumerate(chunks):
            if ci > 0:
                doc.add_page_break()
            if ci == 0:
                h1 = doc.add_heading(title, level=1)
                h1.runs[0].font.size = Pt(14)
            else:
                start = ci * cpp + 1
                end = start + len(h) - 1
                lab = f"欄 {start}–{end}" if is_chn else f"Columns {start}-{end}"
                h2 = doc.add_heading(lab, level=2)
                h2.runs[0].font.size = Pt(12)
            nrows = 1 + len(b) + (1 if t and any(str(x).strip() for x in t) else 0)
            ncols = max(1, len(h))
            table = doc.add_table(rows=nrows, cols=ncols)
            table.style = "Table Grid"
            hdr_cells = table.rows[0].cells
            for i, ht in enumerate(h):
                hdr_cells[i].text = str(ht)
                para = hdr_cells[i].paragraphs[0]
                para.alignment = (
                    WD_ALIGN_PARAGRAPH.RIGHT
                    if (offset + i) in right_global
                    else WD_ALIGN_PARAGRAPH.LEFT
                )
            for ri, line in enumerate(b):
                row_cells = table.rows[ri + 1].cells
                for cj, cell in enumerate(line):
                    if cj < len(row_cells):
                        row_cells[cj].text = str(cell)
                        para = row_cells[cj].paragraphs[0]
                        para.alignment = (
                            WD_ALIGN_PARAGRAPH.RIGHT
                            if (offset + cj) in right_global
                            else WD_ALIGN_PARAGRAPH.LEFT
                        )
            if t and any(str(x).strip() for x in t):
                tr = list(t)
                if ci == 0:
                    tr[0] = "合計" if is_chn else "Total"
                last = table.rows[len(b) + 1].cells
                for cj in range(ncols):
                    last[cj].text = str(tr[cj]) if cj < len(tr) else ""
                    para = last[cj].paragraphs[0]
                    para.alignment = (
                        WD_ALIGN_PARAGRAPH.RIGHT
                        if (offset + cj) in right_global
                        else WD_ALIGN_PARAGRAPH.LEFT
                    )
            offset += len(h)
        buf = io.BytesIO()
        doc.save(buf)
        return True, "", buf.getvalue()

    # endregion
