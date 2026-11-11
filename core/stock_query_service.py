"""存貨查詢：STOCK 主檔 + PURSTK/INVSTK/STKTRX/TRANTRX 交易明細。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Literal, Optional, Sequence, Tuple

from core.arap_settlement_service import _d, _has_table, _row_val, _s
from core.db_backend import DbBackendBase
from core.display_format import (
    format_cell_display,
    format_date_display,
    format_numeric_display,
    parse_qdate,
)

# PUR=購貨, INV=銷貨/發票, ADJ=存貨調整, TRI=存貨轉倉
TxKind = Literal["PUR", "INV", "ADJ", "TRI"]

TX_KIND_OPTIONS: Tuple[TxKind, ...] = ("PUR", "INV", "ADJ", "TRI")

# 規格資料表：PURSTK / INVSTK / STKTRX / TRANTRX（僅在缺表時才用舊名後備）
_TX_TABLE_CANDIDATES: Dict[TxKind, Tuple[str, ...]] = {
    "PUR": ("PURSTK", "PUR_ITEM"),
    "INV": ("INVSTK", "INV_ITEM"),
    "ADJ": ("STKTRX", "STKADJ"),
    "TRI": ("TRANTRX", "STKTRAN"),
}

_HEADER_FOR_DETAIL: Dict[str, str] = {
    "PURSTK": "PURCHASE",
    "PUR_ITEM": "PURCHASE",
    "INVSTK": "INVOICE",
    "INV_ITEM": "INVOICE",
    "STKTRX": "STKADJ",
    "TRANTRX": "TRANSFER",
}


@dataclass
class StockInfo:
    key: str = ""
    category: str = ""
    brand: str = ""
    model: str = ""
    desc: str = ""


@dataclass
class StockQueryLine:
    date: str = ""
    tx_category: str = ""
    tx_key: str = ""
    qty: str = ""
    unit: str = ""
    weight: str = ""
    wgt_unit: str = ""
    warehouse: str = ""
    unit_price: str = ""
    amount: str = ""
    unit_cost: str = ""
    cost_amt: str = ""


@dataclass
class StockQueryDocument:
    stocks: List[StockInfo] = field(default_factory=list)
    stock_index: int = 0
    date_from: str = ""
    date_to: str = ""
    tx_kinds: List[str] = field(default_factory=lambda: list(TX_KIND_OPTIONS))
    lines: List[StockQueryLine] = field(default_factory=list)


def _find_col(cols: Sequence[str], name: str) -> Optional[str]:
    key = (name or "").strip().upper()
    for c in cols:
        if (c or "").strip().upper() == key:
            return c
    return None


def _first_val(row: Sequence[str], fields: Sequence[str], names: Sequence[str]) -> str:
    for n in names:
        v = _row_val(row, fields, n)
        if v:
            return v
    return ""


def _fmt_qty(raw: str) -> str:
    """數量／重量：可解析數字則整數千分位；否則原文。"""
    return format_numeric_display(raw, "int") if (raw or "").strip() else ""


def _fmt_amt(raw: str) -> str:
    return format_numeric_display(raw, "amount") if (raw or "").strip() else ""


def _fmt_rate_stock(raw: str) -> str:
    return format_numeric_display(raw, "rate") if (raw or "").strip() else ""


def normalize_tx_kind_one(raw: str) -> Optional[TxKind]:
    k = (raw or "").strip().upper()
    if k in {"PUR", "PURCHASE", "購貨", "採購"}:
        return "PUR"
    if k in {"INV", "INVOICE", "銷貨", "發票", "SALES", "SALE"}:
        return "INV"
    if k in {"ADJ", "STKADJ", "STKTRX", "ADJUST", "ADJUSTMENT", "存貨調整", "調整"}:
        return "ADJ"
    if k in {
        "TRI",
        "STKTRAN",
        "TRANTRX",
        "TRANSFER",
        "TRAN",
        "存貨轉倉",
        "轉倉",
    }:
        return "TRI"
    return None


def normalize_tx_kinds(
    raw: Optional[Sequence[str] | str] = None,
    *,
    default_all: bool = True,
) -> List[str]:
    if raw is None:
        return list(TX_KIND_OPTIONS) if default_all else []
    if isinstance(raw, str):
        s = raw.strip()
        if not s or s.upper() == "ALL":
            return list(TX_KIND_OPTIONS) if default_all else []
        one = normalize_tx_kind_one(s)
        return [one] if one else (list(TX_KIND_OPTIONS) if default_all else [])
    if len(raw) == 0:
        return []
    out: List[str] = []
    for x in raw:
        xu = str(x or "").strip().upper()
        if xu == "ALL":
            return list(TX_KIND_OPTIONS)
        one = normalize_tx_kind_one(xu)
        if one and one not in out:
            out.append(one)
    return out


def _is_stock_query_title(title: str) -> bool:
    t = (title or "").strip()
    tu = t.upper()
    return any(m in t for m in ("存貨", "庫存")) or any(
        m in tu for m in ("STOCK", "INVENTORY")
    )


def is_stock_query_program(
    do_proc: str,
    table_name: str = "",
    other_title: str = "",
) -> bool:
    title = (other_title or "").strip()
    title_u = title.upper()
    proc = (do_proc or "").strip().upper()
    tbl = (table_name or "").strip().upper()

    if "查詢" in title or "QUERY" in title_u:
        if _is_stock_query_title(title):
            return True
        if tbl == "STOCK":
            return True
        # 排除賬戶查詢
        if any(m in title for m in ("賬戶", "帳戶")) or "ACCOUNT" in title_u:
            return False

    stock_procs = (
        "DO_STOCK_QUERY",
        "STOCK_QUERY",
        "DO_STKQ",
        "STK_QUERY",
        "STKQUERY",
        "INVENTORY_QUERY",
        "DO_INV_QUERY_STK",
    )
    for p in stock_procs:
        if proc == p or proc.endswith(p):
            return True

    if tbl == "STOCK" and ("查詢" in title or "QUERY" in title_u):
        return True
    return False


def normalize_date_text(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    d = parse_qdate(s)
    if d is None:
        return s
    return format_date_display(s)


def _parse_filter_date(raw: str) -> Optional[date]:
    s = (raw or "").strip()
    if not s:
        return None
    return parse_qdate(s)


def _date_in_range(raw: str, from_d: Optional[date], to_d: Optional[date]) -> bool:
    if not from_d and not to_d:
        return True
    d = parse_qdate(raw)
    if d is None:
        return True
    if from_d and d < from_d:
        return False
    if to_d and d > to_d:
        return False
    return True


def _stock_key_names() -> Tuple[str, ...]:
    # STOCK 主鍵以 STK_CODE 為準（COLUMNS／實庫常見）
    return ("STK_CODE", "STK_KEY", "STOCK_KEY", "STOCK_CODE", "ITEM_CODE", "KEY_CODE", "KEY")


def _stock_cols(cols: Sequence[str]) -> List[str]:
    found: List[str] = []
    for name in _stock_key_names():
        c = _find_col(cols, name)
        if c and c not in found:
            found.append(c)
    return found


def _stock_info_from_row(fields: Sequence[str], row: Sequence[str]) -> StockInfo:
    """STOCK 主檔欄位對應：編號 STK_CODE、分類 CATE_CODE、牌子 BRAND、型號 MODEL、說明 STK_DESC。"""
    return StockInfo(
        key=_first_val(row, fields, _stock_key_names()),
        category=_first_val(
            row,
            fields,
            (
                "CATE_CODE",
                "CAT_KEY",
                "STK_CAT",
                "CAT_CODE",
                "CATEGORY",
                "CAT_NO",
                "CAT",
            ),
        ),
        # 規格：牌子名稱 = STOCK.BRAND
        brand=_row_val(row, fields, "BRAND")
        or _first_val(row, fields, ("BRAND_NAME", "BRAND_CODE", "MAKE", "MAKER")),
        # 規格：型號 = STOCK.MODEL
        model=_row_val(row, fields, "MODEL")
        or _first_val(row, fields, ("MODEL_NO", "MODEL_CODE")),
        desc=_first_val(
            row,
            fields,
            ("STK_DESC", "DESC", "DESCRIPTION", "NAME", "STK_NAME"),
        ),
    )


def load_stocks(backend: DbBackendBase) -> Tuple[List[StockInfo], Optional[str]]:
    table = "STOCK"
    if not _has_table(backend, table):
        return [], f"找不到 {table} 資料表。"
    cols = backend.list_columns(table)
    if not cols:
        return [], f"無法讀取 {table} 欄位。"
    _sel, rows = backend.fetch_rows_sql(f"SELECT * FROM {table}", limit=100000)
    out: List[StockInfo] = []
    seen: set[str] = set()
    for row in rows:
        info = _stock_info_from_row(cols, row)
        if not info.key or info.key.upper() in seen:
            continue
        seen.add(info.key.upper())
        out.append(info)
    out.sort(key=lambda s: s.key.upper())
    return out, None


def find_stock_index(stocks: List[StockInfo], stock_key: str) -> int:
    key = (stock_key or "").strip().upper()
    if not key:
        return -1
    for i, s in enumerate(stocks):
        if (s.key or "").strip().upper() == key:
            return i
    return -1


def stock_key_from_source_row(fields: Sequence[str], row: Sequence[str]) -> str:
    if not row:
        return ""
    return _first_val(row, fields, _stock_key_names())


def current_stock(doc: StockQueryDocument) -> StockInfo:
    if not doc.stocks:
        return StockInfo()
    idx = doc.stock_index
    if idx < 0 or idx >= len(doc.stocks):
        idx = 0
    return doc.stocks[idx]


def _resolve_tx_table(
    backend: DbBackendBase, kind: TxKind
) -> Tuple[Optional[str], List[str]]:
    for name in _TX_TABLE_CANDIDATES.get(kind, ()):
        if not _has_table(backend, name):
            continue
        cols = backend.list_columns(name)
        if not cols:
            continue
        if _stock_cols(cols) or name in {
            "STKTRX",
            "STKADJ",
            "TRANTRX",
            "STKTRAN",
            "TRANSFER",
            "PURCHASE",
            "INVOICE",
            "PURSTK",
            "INVSTK",
        }:
            return name, cols
    return None, []


def _fetch_rows_by_stock(
    backend: DbBackendBase,
    table: str,
    stock_cols: Sequence[str],
    stock_key: str,
) -> Tuple[List[str], List[Sequence[str]]]:
    cols = backend.list_columns(table)
    if not cols or not stock_key or not stock_cols:
        return [], []
    where = " OR ".join(f"{c} = ?" for c in stock_cols)
    params = [stock_key] * len(stock_cols)
    sql = f"SELECT * FROM {table} WHERE ({where})"
    _sel, rows = backend.fetch_rows_sql(sql, params=params, limit=50000)
    return cols, rows


def _header_date_map(
    backend: DbBackendBase, header_table: str
) -> Dict[str, str]:
    """TX_KEY → DATE（yyyy/MM/dd 顯示字串）。"""
    if not header_table or not _has_table(backend, header_table):
        return {}
    cols = backend.list_columns(header_table)
    if not cols:
        return {}
    key_col = _find_col(cols, "TX_KEY") or _find_col(cols, "TX_NO")
    if not key_col:
        return {}
    date_names = ("DATE", "TX_DATE", "DOC_DATE")
    _sel, rows = backend.fetch_rows_sql(
        f"SELECT * FROM {header_table}", limit=100000
    )
    out: Dict[str, str] = {}
    for row in rows:
        k = _row_val(row, cols, key_col).strip().upper()
        if not k:
            continue
        raw = _first_val(row, cols, date_names)
        if raw:
            out[k] = format_cell_display("DATE", raw, "", "DATE")
    return out


def _line_date(
    fields: Sequence[str],
    row: Sequence[str],
    header_dates: Optional[Dict[str, str]] = None,
) -> str:
    raw = _first_val(row, fields, ("DATE", "TX_DATE", "DOC_DATE", "ADJ_DATE", "TRAN_DATE"))
    if raw:
        return format_cell_display("DATE", raw, "", "DATE")
    if header_dates:
        tx = _first_val(row, fields, ("TX_KEY", "TX_NO")).strip().upper()
        if tx and tx in header_dates:
            return header_dates[tx]
    return ""


def _line_from_row(
    fields: Sequence[str],
    row: Sequence[str],
    category: str,
    header_dates: Optional[Dict[str, str]] = None,
) -> StockQueryLine:
    qty_raw = _first_val(row, fields, ("QTY", "QUANTITY", "STK_QTY"))
    wgt_raw = _first_val(row, fields, ("WEIGHT", "WGT", "STK_WGT"))
    price_raw = _first_val(row, fields, ("UNIT_PRICE", "PRICE", "UPRICE"))
    amt_raw = _first_val(row, fields, ("AMOUNT", "AMT", "NET_AMT", "TX_AMT"))
    if not amt_raw and qty_raw and price_raw:
        try:
            amt_raw = str(_d(qty_raw) * _d(price_raw))
        except Exception:
            amt_raw = ""
    ucost_raw = _first_val(row, fields, ("UNIT_COST", "COST", "AVG_COST", "STK_COST"))
    cost_raw = _first_val(row, fields, ("COST_AMT", "COST_AMOUNT", "COST_AMT"))
    if not cost_raw and qty_raw and ucost_raw:
        try:
            cost_raw = str(_d(qty_raw) * _d(ucost_raw))
        except Exception:
            cost_raw = ""
    return StockQueryLine(
        date=_line_date(fields, row, header_dates),
        tx_category=category,
        tx_key=_first_val(row, fields, ("TX_KEY", "TX_NO", "ADJ_KEY", "TRAN_KEY", "DOC_NO")),
        qty=_fmt_qty(qty_raw),
        unit=_first_val(row, fields, ("UNIT", "UNIT_CODE", "UOM", "STK_UNIT")),
        weight=_fmt_qty(wgt_raw) if wgt_raw else "",
        wgt_unit=_first_val(row, fields, ("WGT_UNIT", "WEIGHT_UNIT", "WUNIT")),
        warehouse=_first_val(
            row, fields, ("LOC", "WAREHOUSE", "WH_KEY", "LOC_KEY", "STORE", "FROM_LOC", "TO_LOC")
        ),
        unit_price=_fmt_amt(price_raw) if price_raw else "",
        amount=_fmt_amt(amt_raw) if amt_raw else "0.00",
        unit_cost=_fmt_amt(ucost_raw) if ucost_raw else "",
        cost_amt=_fmt_amt(cost_raw) if cost_raw else "0.00",
    )


def _should_include(kinds: Sequence[str], category: str) -> bool:
    if not kinds:
        return False
    return category in kinds


def load_stock_transactions(
    backend: DbBackendBase,
    stock_key: str,
    date_from: str = "",
    date_to: str = "",
    tx_kinds: Optional[Sequence[str] | str] = None,
) -> List[StockQueryLine]:
    if not stock_key:
        return []
    kinds = normalize_tx_kinds(tx_kinds)
    from_d = _parse_filter_date(date_from)
    to_d = _parse_filter_date(date_to)
    lines: List[StockQueryLine] = []
    header_cache: Dict[str, Dict[str, str]] = {}

    for kind in TX_KIND_OPTIONS:
        if not _should_include(kinds, kind):
            continue
        table, cols = _resolve_tx_table(backend, kind)
        if not table or not cols:
            continue
        pcs = _stock_cols(cols)
        if not pcs:
            continue
        cols, rows = _fetch_rows_by_stock(backend, table, pcs, stock_key)
        if not rows:
            continue
        header_table = _HEADER_FOR_DETAIL.get(table.upper(), "")
        header_dates: Optional[Dict[str, str]] = None
        if header_table:
            if header_table not in header_cache:
                header_cache[header_table] = _header_date_map(backend, header_table)
            header_dates = header_cache[header_table]
        for row in rows:
            ln = _line_from_row(cols, row, kind, header_dates)
            if from_d or to_d:
                if not ln.date or not _date_in_range(ln.date, from_d, to_d):
                    continue
            lines.append(ln)

    lines.sort(key=lambda x: (x.date, x.tx_category, x.tx_key))
    return lines


def load_stock_query(
    backend: DbBackendBase,
    do_proc: str,
    source_row: Sequence[str],
    source_fields: Sequence[str],
    *,
    table_name: str = "",
    other_title: str = "",
    stock_index: int = -1,
    date_from: str = "",
    date_to: str = "",
    tx_kinds: Optional[Sequence[str] | str] = None,
    stock_key: str = "",
) -> Tuple[Optional[StockQueryDocument], Optional[str]]:
    if not is_stock_query_program(do_proc, table_name, other_title):
        # 寬鬆：主檔為 STOCK 亦允許
        if (table_name or "").strip().upper() != "STOCK":
            return None, "此作業非存貨查詢。"
    try:
        backend.refresh_for_read()
    except Exception:
        pass
    stocks, err = load_stocks(backend)
    if err:
        return None, err
    if not stocks:
        return None, "STOCK 沒有可查詢的資料。"
    date_from_n = normalize_date_text(date_from)
    date_to_n = normalize_date_text(date_to)
    kinds = normalize_tx_kinds(tx_kinds)
    start_key = stock_key_from_source_row(source_fields, source_row)
    explicit_key = (stock_key or "").strip()
    # stock_index < 0：依來源列／stock_key 定位；>= 0：明確索引（含 FIRST=0）
    if stock_index is not None and stock_index >= 0:
        idx = stock_index
    elif explicit_key:
        idx = find_stock_index(stocks, explicit_key)
        if idx < 0:
            return None, "找不到此存貨編號。"
    elif start_key:
        idx = find_stock_index(stocks, start_key)
        if idx < 0:
            idx = 0
    else:
        idx = 0
    if idx < 0 or idx >= len(stocks):
        idx = 0
    resolved_key = stocks[idx].key
    lines = load_stock_transactions(
        backend,
        resolved_key,
        date_from=date_from_n,
        date_to=date_to_n,
        tx_kinds=kinds,
    )
    return StockQueryDocument(
        stocks=stocks,
        stock_index=idx,
        date_from=date_from_n,
        date_to=date_to_n,
        tx_kinds=kinds,
        lines=lines,
    ), None


def line_search_blob(ln: StockQueryLine) -> str:
    return " ".join(
        [
            ln.date,
            ln.tx_category,
            ln.tx_key,
            ln.qty,
            ln.unit,
            ln.weight,
            ln.wgt_unit,
            ln.warehouse,
            ln.unit_price,
            ln.amount,
            ln.unit_cost,
            ln.cost_amt,
        ]
    ).lower()


def filter_stock_lines(
    lines: List[StockQueryLine], keyword: str
) -> List[StockQueryLine]:
    kw = (keyword or "").strip().lower()
    if not kw:
        return list(lines)
    return [ln for ln in lines if kw in line_search_blob(ln)]


def find_line_index(lines: List[StockQueryLine], keyword: str) -> Optional[int]:
    kw = (keyword or "").strip().lower()
    if not kw:
        return None
    for i, ln in enumerate(lines):
        if kw in line_search_blob(ln):
            return i
    return None


def _sum_group(
    lines: List[StockQueryLine], category: str
) -> Tuple[Decimal, Decimal, Decimal]:
    qty = wgt = amt = Decimal("0")
    cat = (category or "").upper()
    for ln in lines:
        if (ln.tx_category or "").upper() != cat:
            continue
        qty += _d(ln.qty)
        wgt += _d(ln.weight)
        amt += _d(ln.amount)
    return qty, wgt, amt


def totals_dict(lines: List[StockQueryLine]) -> dict[str, str]:
    """購貨／發票／存貨調整／存貨轉倉：數量、重量、金額。"""
    out: dict[str, str] = {}
    for cat, prefix in (
        ("PUR", "pur"),
        ("INV", "inv"),
        ("ADJ", "adj"),
        ("TRI", "tri"),
    ):
        q, w, a = _sum_group(lines, cat)
        out[f"{prefix}_qty"] = _fmt_qty(str(q))
        out[f"{prefix}_weight"] = _fmt_qty(str(w))
        out[f"{prefix}_amt"] = _fmt_amt(str(a))
    return out
