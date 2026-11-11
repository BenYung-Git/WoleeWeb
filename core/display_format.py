"""
全專案統一顯示格式（報表列印／預覽與 Grid 等共用核心）：
- 日期：yyyy/MM/dd（例：2026/04/01）
- 金額／借項／貸項：千分位＋兩位小數（#,###.##，對應 999,999,999.99 類顯示）
- 匯率：千分位＋四位小數（#,###.####，對應 999,999.9999 類顯示）
- 百分比（欄名或格式含 %／PCT 等）：千分位＋一位小數（#,###.#，例 999.9）
- 零補位遮罩（例如 DATA_FORMAT=000009）：顯示與儲存皆補齊固定位數（例 9 → 000009）
- 布林（DATA_TYPE=B/BOOLEAN）：顯示與儲存統一為 Y / N
- 其餘可解析的數字欄位：整數＋千分位
儲存值：日期與數字會正規化為不含千分位的字串，便於寫入資料庫。
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import List, Literal, Optional

NumberKind = Literal["amount", "rate", "percent", "int"]

# 與使用者約定一致（yyyy=年, MM=月, dd=日；亦作 Qt 格式提示傳入 parse_qdate）
APP_DATE_QT_FORMAT = "yyyy/MM/dd"
APP_DATE_DISPLAY = "%Y/%m/%d"


def strip_numeric_commas(s: str) -> str:
    return (s or "").strip().replace(",", "")


def try_parse_float(s: str) -> Optional[float]:
    t = strip_numeric_commas(s)
    if not t or t in ("-", "+", ".", "-.", "+."):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _raw_looks_pure_number(s: str) -> bool:
    t = strip_numeric_commas(s)
    if not t:
        return False
    return bool(re.fullmatch(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?", t))


def _zero_pad_mask_width(data_format: str) -> Optional[int]:
    """
    零補位遮罩：只要 DATA_FORMAT 全由 0/9 組成，就視為固定位數遮罩。
    例如 000009 / 0000 / 999999。
    """
    s = (data_format or "").strip()
    if not s:
        return None
    if not re.fullmatch(r"[09]+", s):
        return None
    return len(s)


def normalize_data_type(data_type: str) -> str:
    """
    將 columns.DATA_TYPE 正規化為內部類別。

    本系統約定（單字元）：
    - N：數字
    - S：文字
    - D：日期
    - B：布林（顯示／儲存 Y、N）

    另相容 C/M/L/T 等 FoxPro 慣例與完整英文名稱。
    """
    t = (data_type or "").strip().upper()
    if not t:
        return ""
    if len(t) == 1:
        return {
            "N": "NUMERIC",
            "S": "STRING",
            "D": "DATE",
            "B": "BOOLEAN",
            "C": "STRING",
            "M": "MEMO",
            "F": "FLOAT",
            "I": "INTEGER",
            "Y": "CURRENCY",
            "T": "DATETIME",
            "L": "BOOLEAN",
        }.get(t, t)
    aliases = {
        "NUM": "NUMERIC",
        "NUMBER": "NUMERIC",
        "NUMERIC": "NUMERIC",
        "DECIMAL": "NUMERIC",
        "STR": "STRING",
        "STRING": "STRING",
        "TEXT": "STRING",
        "CHAR": "STRING",
        "DATE": "DATE",
        "DATETIME": "DATE",
        "BOOL": "BOOLEAN",
        "BOOLEAN": "BOOLEAN",
        "LOGICAL": "BOOLEAN",
    }
    return aliases.get(t, t)


def is_string_data_type(data_type: str) -> bool:
    t = normalize_data_type(data_type)
    return t in (
        "S",
        "STRING",
        "STR",
        "TEXT",
        "CHAR",
        "VARCHAR",
        "NVARCHAR",
        "MEMO",
        "LONGTEXT",
        "NTEXT",
    )


def is_date_data_type(data_type: str) -> bool:
    t = normalize_data_type(data_type)
    return t in ("D", "DATE", "DATETIME", "DT", "TIME")


def is_numeric_data_type(data_type: str) -> bool:
    t = normalize_data_type(data_type)
    return t in (
        "N",
        "NUM",
        "NUMBER",
        "NUMERIC",
        "DECIMAL",
        "FLOAT",
        "DOUBLE",
        "INT",
        "INTEGER",
        "CURRENCY",
        "MONEY",
        "BYTE",
    )


def is_boolean_data_type(data_type: str) -> bool:
    t = normalize_data_type(data_type)
    return t in ("B", "BOOL", "BOOLEAN", "LOGICAL", "BIT", "YESNO", "YN")


def normalize_boolean_yn(text: str) -> str:
    t = (text or "").strip().upper()
    if not t:
        return ""
    if t in ("Y", "YES", "TRUE", "T", "1", "-1"):
        return "Y"
    if t in ("N", "NO", "FALSE", "F", "0"):
        return "N"
    return (text or "").strip()


def _format_zero_pad_value(raw: str, width: int) -> str:
    t = (raw or "").strip()
    if not t:
        return ""
    v = try_parse_float(t)
    if v is None:
        return t
    n = int(round(v))
    sign = "-" if n < 0 else ""
    body = f"{abs(n):0{width}d}"
    return f"{sign}{body}"


def data_format_looks_like_date(df: str) -> bool:
    u = (df or "").strip().upper()
    if not u:
        return False
    return any(x in u for x in ("YYYY", "YY/", "/MM", "MM/", "/DD", "DD/", "日期"))


def is_date_field(field_name: str) -> bool:
    s = (field_name or "").strip().upper()
    if not s:
        return False
    return ("DATE" in s) or s.endswith("DT") or ("日期" in (field_name or ""))


def _field_looks_textish(field_name: str) -> bool:
    """避免將編號／代碼等純數字字串當成數值格式化。"""
    fn = (field_name or "").upper()
    for token in (
        "NAME",
        "ADDR",
        "NOTE",
        "DESC",
        "EMAIL",
        "PHONE",
        "TITLE",
        "REMARK",
        "MEMO",
        "TEXT",
        "CODE",
        "CUST_",
        "VENDOR",
        "INV_NO",
        "DOC_NO",
        "VOUCHER",
        "BILL_NO",
        "SHIP_TO",
    ):
        if token in fn:
            return True
    return False


def guess_number_kind(
    field_name: str, data_format: str, data_type: str = ""
) -> Optional[NumberKind]:
    """
    依欄位名／DATA_FORMAT 推斷數字類型；None 表示不強制為數字欄位。
    """
    fn = (field_name or "").upper()
    df = (data_format or "").upper()

    if is_date_data_type(data_type):
        return None
    if is_boolean_data_type(data_type):
        return None
    if is_string_data_type(data_type):
        return None
    if is_numeric_data_type(data_type):
        df_u = (data_format or "").upper()
        if "0.0000" in df_u or df_u.strip() == "RATE":
            return "rate"
        if "%" in df_u:
            return "percent"
        if "0.00" in df_u or "MONEY" in df_u or "CURRENCY" in df_u:
            return "amount"
        if "INT" in df_u or "INTEGER" in df_u:
            return "int"
        return "amount"
    if is_date_field(field_name) or data_format_looks_like_date(data_format):
        return None

    if "匯率" in (field_name or ""):
        return "rate"
    for token in ("EX_RATE", "EXCHRATE", "FX_RATE", "EXCH_RATE", "CUR_RATE", "ROE", "XRATE"):
        if token in fn:
            return "rate"
    if (fn.endswith("RATE") or fn == "RATE") and "STRATE" not in fn and "CORPORATE" not in fn:
        return "rate"

    if "%" in df:
        return "percent"
    if (
        "PCT" in fn
        or "PERCENT" in fn
        or "%" in (field_name or "")
        or "折扣％" in (field_name or "")
        or "折扣%" in (field_name or "")
    ):
        return "percent"

    zname = field_name or ""
    if any(x in zname for x in ("借項", "貸項", "借方", "貸方", "金額", "實收")):
        return "amount"

    for token in (
        "AMT",
        "AMOUNT",
        "MONEY",
        "PRICE",
        "COST",
        "TOTAL",
        "NET",
        "GROSS",
        "BALANCE",
        "BAL_DUE",
        "SUBTOTAL",
        "TAX_AMT",
        "PAID",
        "DUE",
        "DEBIT",
        "CREDIT",
        "DR_AMT",
        "CR_AMT",
        "DEB_AMT",
        "CRE_AMT",
        "DR_TOT",
        "CR_TOT",
    ):
        if token in fn and "QTY" not in fn and "QUANTITY" not in fn:
            return "amount"
    # 借／貸欄位常見命名：_DR / _CR、DR_BAL、CR_BAL（避免誤判 ADDRESS 等含 DR 子字串）
    if re.search(r"(^|_)(DR|CR)(_|$)", fn) and "STRATE" not in fn:
        return "amount"

    for token in ("QTY", "QUANTITY", "QNTY", "LINE_NO", "SEQ_NO", "PACK", "COUNT"):
        if token in fn:
            return "int"

    if "0.0000" in df or df.strip() == "RATE":
        return "rate"
    if "0.00" in df or "MONEY" in df or "CURRENCY" in df or "CURR" in df:
        return "amount"
    if "INT" in df or "INTEGER" in df:
        return "int"

    return None


def _to_strptime_format(fmt: str) -> str:
    """將 Qt／FoxPro 日期格式字串轉為 strptime 格式。"""
    s = (fmt or "").strip()
    if not s:
        return ""
    reps = (
        ("YYYY", "%Y"),
        ("yyyy", "%Y"),
        ("YY", "%y"),
        ("yy", "%y"),
        ("DD", "%d"),
        ("dd", "%d"),
        ("MM", "%m"),
    )
    for a, b in reps:
        s = s.replace(a, b)
    return s


def _try_parse_iso_date(txt: str) -> Optional[date]:
    t = (txt or "").strip()
    if not t:
        return None
    if " " in t and len(t) >= 10:
        head = t.split()[0]
        d = _try_parse_iso_date(head)
        if d is not None:
            return d
    if "T" in t and len(t) >= 10:
        head = t.split("T", 1)[0]
        d = _try_parse_iso_date(head)
        if d is not None:
            return d
    try:
        return date.fromisoformat(t)
    except ValueError:
        return None


def _try_strptime_date(txt: str, fmt: str) -> Optional[date]:
    if not fmt:
        return None
    try:
        return datetime.strptime(txt, fmt).date()
    except ValueError:
        return None


def _try_flexible_slash_date(txt: str) -> Optional[date]:
    m = re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", txt)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", txt)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{4})(\d{2})/(\d{1,2})", txt)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def parse_qdate(value: str, fmt: str = "") -> Optional[date]:
    """解析日期字串；回傳 datetime.date（不依賴 PyQt6，Web headless 可用）。"""
    txt = (value or "").strip()
    if not txt:
        return None

    d_iso = _try_parse_iso_date(txt)
    if d_iso is not None:
        return d_iso

    formats: List[str] = []
    sp_fmt = _to_strptime_format(fmt)
    if sp_fmt:
        formats.append(sp_fmt)
    formats.extend(
        [
            APP_DATE_DISPLAY,
            "%Y/%m/%d",
            "%Y%m/%d",
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
            "%Y%m%d",
            "%d/%m/%Y",
        ]
    )
    for f in formats:
        d = _try_strptime_date(txt, f)
        if d is not None:
            return d
    return _try_flexible_slash_date(txt)


def format_date_display(raw: str, data_format_hint: str = "") -> str:
    d = parse_qdate(raw, data_format_hint)
    if d is None:
        return (raw or "").strip()
    return d.strftime(APP_DATE_DISPLAY)


def format_numeric_display(raw: str, kind: NumberKind) -> str:
    v = try_parse_float(raw)
    if v is None:
        return (raw or "").strip()
    if kind == "rate":
        return f"{v:,.4f}"
    if kind == "amount":
        return f"{v:,.2f}"
    if kind == "percent":
        return f"{v:,.1f}"
    return f"{int(round(v)):,}"


def format_cell_display(
    field_name: str, raw: str, data_format: str = "", data_type: str = ""
) -> str:
    """Grid／表單顯示用。"""
    if is_boolean_data_type(data_type):
        return normalize_boolean_yn(raw)
    if is_string_data_type(data_type):
        return (raw or "").strip()
    df = data_format or ""
    mask_w = _zero_pad_mask_width(df)
    if mask_w is not None:
        # 字串型欄位（代碼/編號等）不做數字補零轉換，保留原文字。
        if _field_looks_textish(field_name):
            return (raw or "").strip()
        return _format_zero_pad_value(raw, mask_w)
    if is_date_data_type(data_type) or is_date_field(field_name) or data_format_looks_like_date(df):
        return format_date_display(raw, df)

    if is_numeric_data_type(data_type):
        if not _raw_looks_pure_number(raw):
            return (raw or "").strip()
        kind = guess_number_kind(field_name, df, data_type) or "amount"
        return format_numeric_display(raw, kind)

    if not _raw_looks_pure_number(raw):
        return (raw or "").strip()

    kind = guess_number_kind(field_name, df, data_type)
    if kind is None:
        if _field_looks_textish(field_name):
            return (raw or "").strip()
        kind = "int"
    return format_numeric_display(raw, kind)


def grid_column_align(field_name: str, data_format: str = "", data_type: str = "") -> str:
    """Grid 欄位對齊：與 Windows WorkPage._grid_column_text_alignment 一致。"""
    if is_boolean_data_type(data_type) or is_string_data_type(data_type):
        return "left"
    if (
        is_date_data_type(data_type)
        or is_date_field(field_name)
        or data_format_looks_like_date(data_format)
    ):
        return "left"
    if guess_number_kind(field_name, data_format, data_type) is not None:
        return "right"
    return "left"


def normalize_storage_value(
    field_name: str, data_format: str, text: str, data_type: str = ""
) -> str:
    """寫入資料庫前：去掉千分位，數字用固定小數或整數。"""
    t = (text or "").strip()
    if not t:
        return ""
    if is_boolean_data_type(data_type):
        return normalize_boolean_yn(t)
    if is_string_data_type(data_type):
        return t
    df = data_format or ""
    mask_w = _zero_pad_mask_width(df)
    if mask_w is not None:
        # 字串型欄位（代碼/編號等）不做數字補零轉換，保留原文字。
        if _field_looks_textish(field_name):
            return t
        return _format_zero_pad_value(t, mask_w)
    if is_date_data_type(data_type) or is_date_field(field_name) or data_format_looks_like_date(df):
        d = parse_qdate(t, df)
        return d.strftime(APP_DATE_DISPLAY) if d is not None else t

    v = try_parse_float(t)
    if v is None:
        return t

    if is_numeric_data_type(data_type):
        kind = guess_number_kind(field_name, df, data_type) or "amount"
    else:
        kind = guess_number_kind(field_name, df, data_type)
        if kind is None:
            if _field_looks_textish(field_name):
                return t
            kind = "int"

    if kind == "rate":
        return f"{v:.4f}"
    if kind == "amount":
        return f"{v:.2f}"
    if kind == "percent":
        return f"{v:.1f}"
    return str(int(round(v)))
