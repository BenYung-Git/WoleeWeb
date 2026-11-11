"""新增資料列時補齊常見 NOT NULL BIT 欄預設值（與資料匯入邏輯一致）。"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Sequence, Tuple

from core.display_format import (
    APP_DATE_DISPLAY,
    data_format_looks_like_date,
    is_boolean_data_type,
    is_date_data_type,
    is_date_field,
    is_numeric_data_type,
    is_string_data_type,
)

if TYPE_CHECKING:
    from core.data_dictionary import DataDictionary

INSERT_BIT_DEFAULT_ZERO = frozenset(
    {
        "POSTED",
        "POST_CHQ",
        "YEAR_END",
        "MONTH_END",
        "STK_RECEIVED",
        "DELETED",
        "IS_STOCK",
        "IS_PRODUCT",
        "CLOSED",
        "LOCKED",
        "VOIDED",
        "CANCELLED",
        "REVERSED",
    }
)


def _looks_like_bit_flag_name(name: str) -> bool:
    """欄名像布林／旗標（過帳、年結、IS_/HAS_ 等）時，新增空白則預設 0。"""
    u = (name or "").strip().upper()
    if not u:
        return False
    if u in INSERT_BIT_DEFAULT_ZERO:
        return True
    if u.startswith(("POST_", "IS_", "HAS_")):
        return True
    if u.endswith(("_FLAG", "_YN", "_BIT", "_END")):
        return True
    return False


def _sqlite_type_default(sql_type: str) -> str:
    """SQLite NOT NULL 欄無值時的型別預設（字串形式供 insert 繫結）。"""
    t = (sql_type or "").strip().upper()
    if any(
        tok in t
        for tok in (
            "INT",
            "REAL",
            "FLOA",
            "DOUB",
            "NUM",
            "DEC",
            "BOOL",
            "BIT",
            "YESNO",
        )
    ):
        return "0"
    return ""


def fill_sqlite_not_null_defaults(
    column_infos: Sequence[Sequence[Any]],
    field_names: List[str],
    values: List[str],
) -> Tuple[List[str], List[str]]:
    """
    依 PRAGMA table_info 補齊 NOT NULL 且無 DEFAULT 的欄位。
    column_infos 列格式：cid, name, type, notnull, dflt_value, pk
    """
    out_fields = list(field_names)
    out_values = ["" if v is None else str(v) for v in values]
    present = {(f or "").strip().upper(): i for i, f in enumerate(out_fields)}

    for row in column_infos or []:
        if len(row) < 6:
            continue
        name = str(row[1] or "").strip()
        if not name:
            continue
        notnull = int(row[3] or 0)
        dflt = row[4]
        pk = int(row[5] or 0)
        typ = str(row[2] or "")
        if not notnull:
            continue
        if dflt is not None:
            continue
        # INTEGER PRIMARY KEY 可省略以使用自動編號
        if pk == 1 and "INT" in typ.upper():
            continue
        key = name.upper()
        default = _sqlite_type_default(typ)
        idx = present.get(key)
        if idx is None:
            out_fields.append(name)
            out_values.append(default)
            present[key] = len(out_fields) - 1
            continue
        if not (out_values[idx] or "").strip():
            out_values[idx] = default
    return out_fields, out_values

# 表單貨幣代碼／匯率欄（新增預設：公司貨幣、匯率 1）
FORM_CURRENCY_CODE_FIELDS = frozenset(
    {"TX_CURR", "CURRENCY", "CURR", "CO_CURR", "BASE_CURR", "HOME_CURR"}
)
FORM_EXCHANGE_RATE_FIELDS = frozenset(
    {"TX_RATE", "FIX_RATE", "EX_RATE", "EXCHANGE_RATE"}
)
DEFAULT_COMPANY_CURRENCY = "HKD"
DEFAULT_EXCHANGE_RATE = "1"


def _find_col_index(fields: Sequence[str], name: str) -> int:
    target = (name or "").strip().upper()
    for i, f in enumerate(fields):
        if (f or "").strip().upper() == target:
            return i
    return -1


def apply_insert_bit_defaults(
    table_columns: Sequence[str],
    field_names: List[str],
    values: List[str],
    *,
    overrides: Optional[Dict[str, str]] = None,
    is_boolean_column: Optional[Callable[[str], bool]] = None,
) -> Tuple[List[str], List[str]]:
    """
    確保目標表常見 BIT／NOT NULL 欄有非空白值。
    POSTED／POST_CHQ 等預設 0（未過帳／否）；若欄位不在表單中亦會補上。
    亦可依 is_boolean_column（COLUMNS.DATA_TYPE）補齊所有布林欄。
    """
    out_fields = list(field_names)
    out_values = [str(v) if v is not None else "" for v in values]
    overrides_u = {
        (k or "").strip().upper(): str(v) for k, v in (overrides or {}).items()
    }
    col_map = {(c or "").strip().upper(): c for c in table_columns if (c or "").strip()}
    candidates = set(INSERT_BIT_DEFAULT_ZERO) | set(overrides_u.keys())
    for logical, physical in col_map.items():
        if _looks_like_bit_flag_name(logical):
            candidates.add(logical)
            continue
        if is_boolean_column is None:
            continue
        try:
            if is_boolean_column(physical) or is_boolean_column(logical):
                candidates.add(logical)
        except Exception:
            continue
    for logical in sorted(candidates):
        physical = col_map.get(logical)
        if not physical:
            continue
        default = overrides_u.get(logical, "0")
        idx = _find_col_index(out_fields, physical)
        if idx < 0:
            out_fields.append(physical)
            out_values.append(default)
            continue
        cur = (out_values[idx] or "").strip()
        if logical in overrides_u or not cur:
            out_values[idx] = default
    return out_fields, out_values


def _field_is_date_for_new_form(field_name: str, data_type: str, data_format: str) -> bool:
    """與表單日期輸入判斷對齊：優先 DATA_TYPE，再欄名／格式。"""
    if is_date_data_type(data_type):
        return True
    if (
        is_boolean_data_type(data_type)
        or is_numeric_data_type(data_type)
        or is_string_data_type(data_type)
    ):
        return False
    return (
        bool((data_format or "").strip())
        or is_date_field(field_name)
        or data_format_looks_like_date(data_format)
    )


def today_app_date() -> str:
    return date.today().strftime(APP_DATE_DISPLAY)


def _field_is_currency_code(field_name: str) -> bool:
    u = (field_name or "").strip().upper()
    if not u:
        return False
    if u in FORM_CURRENCY_CODE_FIELDS:
        return True
    return u.endswith("_CURR")


def _field_is_exchange_rate(field_name: str) -> bool:
    u = (field_name or "").strip().upper()
    if not u:
        return False
    return u in FORM_EXCHANGE_RATE_FIELDS


# PROC_NAME=DO_ARAP 新增預設
DO_ARAP_NEW_DEFAULTS: Dict[str, str] = {
    "VOU_TYPE": "RJ",  # 傳票種類
    "TX_TYPE": "AR",  # 類別
    "PAID_METHOD": "CHEQUE",  # 付款方式
}

# DO_ARAP：類別 AR 鎖付款欄；類別 AP 鎖收款欄；類別 ARAP 兩邊皆可改
DO_ARAP_AR_LOCK_FIELDS = frozenset({"PAY_AMT", "VEND_DISC", "PAY_DISC"})
DO_ARAP_AP_LOCK_FIELDS = frozenset({"REC_AMT", "CUST_DISC", "REC_DISC"})
DO_ARAP_TX_TO_VOU = {"AR": "RJ", "AP": "PJ", "ARAP": "RPJ"}


def is_do_arap_proc(proc_name: str = "", do_proc: str = "") -> bool:
    """PROGRAM.PROC_NAME 或 DO_PROC 是否為應收應付（DO_ARAP）。"""
    for p in (proc_name, do_proc):
        u = (p or "").strip().upper()
        if u in ("DO_ARAP", "ARAP"):
            return True
    return False


def arap_vou_type_for_tx_type(tx_type: str) -> str:
    """類別 → 傳票種類：AR=RJ、AP=PJ、ARAP=RPJ。"""
    return DO_ARAP_TX_TO_VOU.get((tx_type or "").strip().upper(), "")


def arap_field_locked_by_tx_type(
    field_name: str,
    tx_type: str,
    *,
    proc_name: str = "",
    do_proc: str = "",
) -> bool:
    """
    DO_ARAP：
    類別 AR → 付款金額／付款折扣%／付款折扣金額不可改；
    類別 AP → 收款金額／收款折扣%／收款折扣金額不可改；
    類別 ARAP → 上述欄位皆可改。
    """
    if not is_do_arap_proc(proc_name, do_proc):
        return False
    kind = (tx_type or "").strip().upper()
    key = (field_name or "").strip().upper()
    if kind == "AR":
        return key in DO_ARAP_AR_LOCK_FIELDS
    if kind == "AP":
        return key in DO_ARAP_AP_LOCK_FIELDS
    return False


def apply_proc_new_record_defaults(
    values: Dict[str, str],
    field_names: Sequence[str],
    *,
    proc_name: str = "",
    do_proc: str = "",
) -> Dict[str, str]:
    """
    依 PROC_NAME／DO_PROC 套用新增預設值（僅填空白欄）。
    DO_ARAP：傳票種類=RJ、類別=AR、付款方式=CHEQUE。
    """
    out = dict(values or {})
    if not is_do_arap_proc(proc_name, do_proc):
        return out
    by_upper: Dict[str, str] = {}
    for f in field_names or []:
        name = str(f or "").strip()
        if name:
            by_upper[name.upper()] = name
    for f in list(out.keys()):
        name = str(f or "").strip()
        if name and name.upper() not in by_upper:
            by_upper[name.upper()] = name
    for key, val in DO_ARAP_NEW_DEFAULTS.items():
        fname = by_upper.get(key)
        if not fname:
            continue
        if not str(out.get(fname, "") or "").strip():
            out[fname] = val
    return out


def empty_form_values_for_add(
    field_names: Sequence[str],
    *,
    get_data_type: Callable[[str], str],
    get_data_format: Callable[[str], str],
    login_date: str = "",
    company_currency: str = "",
    proc_name: str = "",
    do_proc: str = "",
) -> Dict[str, str]:
    """
    新增表單初值：
    - 日期欄＝登入日期（缺則今天）
    - 貨幣欄＝登入公司貨幣（缺則 HKD）
    - 匯率欄＝1
    - 其餘數字欄＝0
    - 其他＝空白
    - 另依 PROC_NAME／DO_PROC 套用作業專用預設（如 DO_ARAP）
    """
    date_val = (login_date or "").strip() or today_app_date()
    curr_val = (company_currency or "").strip() or DEFAULT_COMPANY_CURRENCY
    out: Dict[str, str] = {}
    for field in field_names:
        name = str(field or "")
        if not name:
            continue
        f_typ = get_data_type(name) or ""
        f_fmt = get_data_format(name) or ""
        if _field_is_date_for_new_form(name, f_typ, f_fmt):
            out[name] = date_val
        elif is_boolean_data_type(f_typ) or _looks_like_bit_flag_name(name):
            out[name] = "0"
        elif _field_is_currency_code(name):
            out[name] = curr_val
        elif _field_is_exchange_rate(name):
            out[name] = DEFAULT_EXCHANGE_RATE
        elif is_numeric_data_type(f_typ):
            out[name] = "0"
        else:
            out[name] = ""
    return apply_proc_new_record_defaults(
        out,
        field_names,
        proc_name=proc_name,
        do_proc=do_proc,
    )


def empty_form_values_for_add_from_dict(
    data_dict: "DataDictionary",
    table_name: str,
    field_names: Sequence[str],
    *,
    login_date: str = "",
    company_currency: str = "",
    proc_name: str = "",
    do_proc: str = "",
) -> Dict[str, str]:
    """DataDictionary 版新增表單初值。"""
    return empty_form_values_for_add(
        field_names,
        get_data_type=lambda f: data_dict.get_data_type(table_name, f),
        get_data_format=lambda f: data_dict.get_data_format(table_name, f),
        login_date=login_date,
        company_currency=company_currency,
        proc_name=proc_name,
        do_proc=do_proc,
    )
