"""顧客／供應商查詢：CUSTVEND 主檔 + INVOICE/PURCHASE/VOUCHER 交易明細。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Literal, Optional, Sequence, Tuple

from core.arap_settlement_service import _d, _doc_net_amt, _has_table, _row_val, _s
from core.db_backend import DbBackendBase
from core.display_format import (
    format_cell_display,
    format_date_display,
    format_numeric_display,
    parse_qdate,
)

QueryMode = Literal["AR", "AP"]
# INV=發票, REC=收款(RJ), PUR=購貨發票, PAY=付款(PJ)
TxKind = Literal["INV", "REC", "PUR", "PAY"]

TX_KIND_OPTIONS: Tuple[TxKind, ...] = ("INV", "REC", "PUR", "PAY")


@dataclass
class PartyInfo:
    key: str = ""
    name: str = ""
    contact: str = ""
    tel: str = ""
    mobile: str = ""
    # CUST_LIMIT；顯示用已 FORMAT 字串
    credit_limit: str = ""
    # 剩餘信用額（依信用額＋收款－發票計算）
    remain_credit: str = ""


@dataclass
class PartyQueryLine:
    date: str = ""
    tx_category: str = ""
    tx_key: str = ""
    currency: str = ""
    rate: str = ""
    inv_amt: str = ""
    paid_amt: str = ""
    recv_amt: str = ""
    settle_amt: str = ""


@dataclass
class PartyQueryDocument:
    mode: QueryMode
    parties: List[PartyInfo] = field(default_factory=list)
    party_index: int = 0
    date_from: str = ""
    date_to: str = ""
    tx_kinds: List[str] = field(default_factory=lambda: list(TX_KIND_OPTIONS))
    lines: List[PartyQueryLine] = field(default_factory=list)


def _bool_flag(val: object) -> bool:
    s = str(val or "").strip().lower()
    if not s:
        return False
    if s in {"0", "false", "no", "n", "f"}:
        return False
    return True


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


def normalize_tx_kind_one(raw: str) -> Optional[TxKind]:
    k = (raw or "").strip().upper()
    if k in {"INV", "INVOICE", "發票"}:
        return "INV"
    if k in {"REC", "RECEIPT", "RJ", "收款"}:
        return "REC"
    if k in {"PUR", "PURCHASE", "購貨", "購貨發票"}:
        return "PUR"
    if k in {"PAY", "PAYMENT", "PJ", "付款"}:
        return "PAY"
    return None


def normalize_tx_kinds(
    raw: Optional[Sequence[str] | str] = None,
    *,
    default_all: bool = True,
) -> List[str]:
    """
    正規化多選交易類型。
    - None／空白／ALL：預設全選 INV/REC/PUR/PAY
    - 明確空清單 []：不選任何類型（無資料）
    """
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


def normalize_tx_kind(raw: str) -> str:
    """相容舊 API：單一種類或 ALL。"""
    kinds = normalize_tx_kinds(raw)
    if len(kinds) == len(TX_KIND_OPTIONS):
        return "ALL"
    return kinds[0] if kinds else "ALL"


def is_party_query_program(
    do_proc: str,
    table_name: str = "",
    other_title: str = "",
) -> bool:
    return resolve_party_query_mode(do_proc, table_name, other_title) is not None


def resolve_party_query_mode(
    do_proc: str,
    table_name: str = "",
    other_title: str = "",
) -> Optional[QueryMode]:
    title = (other_title or "").strip()
    title_u = title.upper()
    proc = (do_proc or "").strip().upper()

    # 標題含「查詢」／QUERY：僅明確顧客／供應商（或 CUSTVEND）才視為 party 查詢
    if "查詢" in title or "QUERY" in title_u:
        is_stock = any(m in title for m in ("存貨", "庫存")) or any(
            m in title_u for m in ("STOCK", "INVENTORY")
        )
        is_acc = any(m in title for m in ("賬戶", "帳戶")) or "ACCOUNT" in title_u
        is_cust = any(m in title for m in ("顧客", "客戶")) or any(
            m in title_u for m in ("CUSTOMER", "CUST")
        )
        is_vend = any(m in title for m in ("供應", "廠商")) or any(
            m in title_u for m in ("VENDOR", "VEND", "SUPPLIER")
        )
        if (is_stock or is_acc) and not is_cust and not is_vend:
            return None
        tbl0 = (table_name or "").strip().upper()
        if tbl0 in {"STOCK", "ACCOUNT"}:
            return None
        if is_vend and not is_cust:
            return "AP"
        if is_cust:
            return "AR"
        if tbl0 == "CUSTVEND":
            if is_vend and not is_cust:
                return "AP"
            return "AR"
        # 僅「查詢」字樣、無法辨識類型 → 非顧客／供應商查詢
        return None

    cust_procs = (
        "DO_CUST_QUERY",
        "CUST_QUERY",
        "DO_CUSTQ",
        "CUSTOMER_QUERY",
        "CUSTQ",
    )
    vend_procs = (
        "DO_VEND_QUERY",
        "VEND_QUERY",
        "DO_VENDQ",
        "VENDOR_QUERY",
        "SUPPLIER_QUERY",
        "VENDQ",
    )
    for p in cust_procs:
        if proc == p or proc.endswith(p):
            return "AR"
    for p in vend_procs:
        if proc == p or proc.endswith(p):
            return "AP"

    tbl = (table_name or "").strip().upper()
    if tbl == "CUSTVEND" and ("查詢" in title or "QUERY" in title_u):
        if any(m in title for m in ("供應", "廠商")) or any(
            m in title_u for m in ("VENDOR", "VEND", "SUPPLIER")
        ):
            return "AP"
        return "AR"
    if tbl == "CUSTVEND" and is_cust_vend_combined_title(title):
        return "AR"
    return None


def is_cust_vend_combined_title(other_title: str = "") -> bool:
    """標題同時含顧客與供應商（如「顧客-供應商查詢」）時載入全部 CUSTVEND。"""
    title = (other_title or "").strip()
    if not title:
        return False
    if any(x in title for x in ("顧客-供應商", "客戶-供應商", "顧客/供應商")):
        return True
    title_u = title.upper()
    is_cust = any(m in title for m in ("顧客", "客戶")) or any(
        m in title_u for m in ("CUSTOMER", "CUST")
    )
    is_vend = any(m in title for m in ("供應", "廠商")) or any(
        m in title_u for m in ("VENDOR", "VEND", "SUPPLIER")
    )
    return is_cust and is_vend


def _all_party_key_names() -> Tuple[str, ...]:
    return (
        "CUST_KEY",
        "VEND_KEY",
        "CV_KEY",
        "CUST_CODE",
        "VEND_CODE",
        "PARTY_KEY",
        "KEY_CODE",
        "KEY",
    )


def _row_has_party_key(fields: Sequence[str], row: Sequence[str]) -> bool:
    return bool(_first_val(row, fields, _all_party_key_names()).strip())


def _party_key_names(mode: QueryMode) -> Tuple[str, ...]:
    if mode == "AR":
        return ("CUST_KEY", "CUST_CODE", "CV_KEY", "PARTY_KEY", "KEY_CODE", "KEY")
    # 供應商：交易表多用 VEND_KEY；CUSTVEND 可能為 VEND_CODE／共用 CUST_KEY（TYPE=CV）
    return (
        "VEND_KEY",
        "VEND_CODE",
        "CUST_KEY",
        "CUST_CODE",
        "CV_KEY",
        "PARTY_KEY",
        "KEY_CODE",
        "KEY",
    )


def _party_name_names(mode: QueryMode) -> Tuple[str, ...]:
    if mode == "AR":
        return ("CUST_NAME", "CHN_NAME", "NAME", "COMPANY", "PARTY_NAME")
    return ("VEND_NAME", "CUST_NAME", "CHN_NAME", "NAME", "COMPANY", "PARTY_NAME")


def _fmt_amt_val(raw: object) -> str:
    # 不可用 `raw or ""`：數值 0／Decimal(0) 會被當成空而 FORMAT 失敗
    if raw is None:
        s = "0"
    else:
        s = str(raw).strip()
        if s == "":
            s = "0"
    return format_numeric_display(s, "amount")


def _fmt_rate_val(raw: object) -> str:
    if raw is None:
        s = "0"
    else:
        s = str(raw).strip()
        if s == "":
            s = "0"
    return format_numeric_display(s, "rate")


def _read_custvend_cust_limit(fields: Sequence[str], row: Sequence[str]) -> str:
    """信用額只讀 CUSTVEND.CUST_LIMIT（欄位名大小寫不拘）。"""
    raw = _row_val(row, list(fields), "CUST_LIMIT")
    return _fmt_amt_val(raw)


def _party_col(mode: QueryMode) -> str:
    return "CUST_KEY" if mode == "AR" else "VEND_KEY"


def _party_info_from_row(
    fields: Sequence[str], row: Sequence[str], mode: QueryMode, *, combined: bool = False
) -> PartyInfo:
    """CUSTVEND：編號／名稱／聯絡人／電話#／信用額(CUST_LIMIT)。"""
    key_names = _all_party_key_names() if combined else _party_key_names(mode)
    key = _first_val(row, fields, key_names)
    name = _first_val(row, fields, _party_name_names(mode))
    contact = _first_val(
        row,
        fields,
        (
            "AC_ATTN",
            "ATTN1",
            "DEL_ATTN",
            "CONTACT",
            "ATTENTION",
            "CONTACT_NAME",
            "CONTACT_PERSON",
            "ATTN2",
        ),
    )
    tel = _first_val(
        row,
        fields,
        (
            "AC_TEL",
            "TEL1",
            "DEL_TEL",
            "TEL",
            "PHONE",
            "TEL_NO",
            "TELEPHONE",
            "TEL2",
        ),
    )
    mobile = _first_val(
        row,
        fields,
        (
            "AC_MOBILE",
            "MOBILE1",
            "DEL_MOBILE",
            "MOBILE",
            "HAND_PHONE",
            "HANDPHONE",
            "CELL",
            "HP",
            "MOBILE2",
        ),
    )
    return PartyInfo(
        key=key,
        name=name,
        contact=contact,
        tel=tel,
        mobile=mobile,
        credit_limit=_read_custvend_cust_limit(fields, row),
        remain_credit=_fmt_amt_val("0"),
    )


def _custvend_row_matches_mode(
    fields: Sequence[str], row: Sequence[str], mode: QueryMode
) -> bool:
    flag_map = (
        ("IS_CUST", "IS_CUSTOMER", "CUSTOMER")
        if mode == "AR"
        else ("IS_VEND", "IS_VENDOR", "VENDOR", "SUPPLIER")
    )
    for flag in flag_map:
        if _find_col(fields, flag):
            return _bool_flag(_row_val(row, fields, flag))
    # TYPE：C=顧客、V=供應商、CV=兩者
    typ = _row_val(row, fields, "TYPE").strip().upper()
    if typ:
        if mode == "AR":
            return typ in {"C", "CU", "CUST", "CUSTOMER", "CV", "B", "BOTH"} or typ.startswith(
                "C"
            )
        return typ in {
            "V",
            "VE",
            "VEND",
            "VENDOR",
            "SUP",
            "SUPPLIER",
            "CV",
            "B",
            "BOTH",
        } or typ.startswith("V") or typ == "CV"
    if mode == "AP":
        if _find_col(fields, "VEND_CODE") and _row_val(row, fields, "VEND_CODE").strip():
            return True
        if _find_col(fields, "VEND_KEY") and _row_val(row, fields, "VEND_KEY").strip():
            return True
        return False
    key_col = _party_col(mode)
    if _find_col(fields, key_col):
        return bool(_row_val(row, fields, key_col).strip())
    if _find_col(fields, "CV_KEY"):
        return bool(_row_val(row, fields, "CV_KEY").strip())
    if _find_col(fields, "CUST_KEY"):
        return bool(_row_val(row, fields, "CUST_KEY").strip())
    return True


def load_parties(
    backend: DbBackendBase, mode: QueryMode, *, combined: bool = False
) -> Tuple[List[PartyInfo], Optional[str]]:
    table = "CUSTVEND"
    if not _has_table(backend, table):
        return [], f"找不到 {table} 資料表。"
    cols = backend.list_columns(table)
    if not cols:
        return [], f"無法讀取 {table} 欄位。"
    # 必須用 SELECT 回傳的欄位順序對應列值（Access list_columns 順序可能不同）
    sel, rows = backend.fetch_rows_sql(f"SELECT * FROM {table}", limit=100000)
    fields = list(sel) if sel else list(cols)
    if not any((f or "").strip().upper() == "CUST_LIMIT" for f in fields):
        return [], "CUSTVEND 缺少 CUST_LIMIT 欄位，無法讀取信用額。"
    out: List[PartyInfo] = []
    seen: set[str] = set()
    for row in rows:
        if combined:
            if not _row_has_party_key(fields, row):
                continue
        elif not _custvend_row_matches_mode(fields, row, mode):
            continue
        info = _party_info_from_row(fields, row, mode, combined=combined)
        if not info.key or info.key.upper() in seen:
            continue
        seen.add(info.key.upper())
        out.append(info)
    out.sort(key=lambda p: p.key.upper())
    return out, None


def _parse_filter_date(raw: str) -> Optional[date]:
    s = (raw or "").strip()
    if not s:
        return None
    return parse_qdate(s)


def normalize_date_text(raw: str) -> str:
    """空白維持空白；可解析則轉 yyyy/MM/dd。"""
    s = (raw or "").strip()
    if not s:
        return ""
    d = parse_qdate(s)
    if d is None:
        return s
    return format_date_display(s)


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


def _line_date(fields: Sequence[str], row: Sequence[str]) -> str:
    raw = _first_val(row, fields, ("DATE", "TX_DATE", "DOC_DATE", "VOU_DATE"))
    return format_cell_display("DATE", raw, "", "DATE")


def _fmt_rate(fields: Sequence[str], row: Sequence[str]) -> str:
    raw = _first_val(row, fields, ("TX_RATE", "RATE", "EX_RATE"))
    return _fmt_rate_val(raw)


def _line_from_invoice(fields: Sequence[str], row: Sequence[str]) -> PartyQueryLine:
    net = _doc_net_amt(fields, row)
    paid = _d(_row_val(row, fields, "PAID_AMT"))
    return PartyQueryLine(
        date=_line_date(fields, row),
        tx_category="INV",
        tx_key=_first_val(row, fields, ("TX_KEY", "TX_NO")),
        currency=_row_val(row, fields, "TX_CURR"),
        rate=_fmt_rate(fields, row),
        inv_amt=_fmt_amt_val(net),
        paid_amt=_fmt_amt_val(paid),
        recv_amt=_fmt_amt_val("0"),
        settle_amt=_fmt_amt_val(paid),
    )


def _line_from_purchase(fields: Sequence[str], row: Sequence[str]) -> PartyQueryLine:
    """購貨發票：金額以負數顯示。"""
    net = _doc_net_amt(fields, row)
    paid = _d(_row_val(row, fields, "PAID_AMT"))
    return PartyQueryLine(
        date=_line_date(fields, row),
        tx_category="PUR",
        tx_key=_first_val(row, fields, ("TX_KEY", "TX_NO")),
        currency=_row_val(row, fields, "TX_CURR"),
        rate=_fmt_rate(fields, row),
        inv_amt=_fmt_amt_val(-net),
        paid_amt=_fmt_amt_val(-paid),
        recv_amt=_fmt_amt_val("0"),
        settle_amt=_fmt_amt_val(-paid),
    )


def _line_from_voucher_rj(fields: Sequence[str], row: Sequence[str]) -> PartyQueryLine:
    amt = _d(
        _first_val(
            row, fields, ("REC_AMT", "NET_AMT", "TX_AMOUNT", "VOU_AMT", "PAY_AMT")
        )
    )
    return PartyQueryLine(
        date=_line_date(fields, row),
        tx_category="REC",
        tx_key=_first_val(row, fields, ("VOU_KEY", "TX_KEY", "TX_NO")),
        currency=_row_val(row, fields, "TX_CURR"),
        rate=_fmt_rate(fields, row),
        inv_amt=_fmt_amt_val("0"),
        paid_amt=_fmt_amt_val("0"),
        recv_amt=_fmt_amt_val(amt),
        settle_amt=_fmt_amt_val(amt),
    )


def _line_from_voucher_pj(fields: Sequence[str], row: Sequence[str]) -> PartyQueryLine:
    """付款：金額以負數顯示。"""
    amt = _d(
        _first_val(
            row, fields, ("PAY_AMT", "NET_AMT", "TX_AMOUNT", "VOU_AMT", "REC_AMT")
        )
    )
    return PartyQueryLine(
        date=_line_date(fields, row),
        tx_category="PAY",
        tx_key=_first_val(row, fields, ("VOU_KEY", "TX_KEY", "TX_NO")),
        currency=_row_val(row, fields, "TX_CURR"),
        rate=_fmt_rate(fields, row),
        inv_amt=_fmt_amt_val("0"),
        paid_amt=_fmt_amt_val("0"),
        recv_amt=_fmt_amt_val(-amt),
        settle_amt=_fmt_amt_val(-amt),
    )


def _match_party_cols(cols: Sequence[str], mode: QueryMode) -> List[str]:
    """依模式優先主鍵，並同時比對 CV_KEY／另一側鍵（同一編號）。"""
    preferred = ["CUST_KEY", "CV_KEY", "VEND_KEY"] if mode == "AR" else [
        "VEND_KEY",
        "CV_KEY",
        "CUST_KEY",
    ]
    found: List[str] = []
    for name in preferred:
        c = _find_col(cols, name)
        if c and c not in found:
            found.append(c)
    return found


def _fetch_rows_by_party(
    backend: DbBackendBase,
    table: str,
    party_cols: Sequence[str],
    party_key: str,
) -> Tuple[List[str], List[Sequence[str]]]:
    cols = backend.list_columns(table)
    if not cols or not party_key or not party_cols:
        return [], []
    where = " OR ".join(f"{c} = ?" for c in party_cols)
    params = [party_key] * len(party_cols)
    sql = f"SELECT * FROM {table} WHERE ({where})"
    sel, rows = backend.fetch_rows_sql(sql, params=params, limit=50000)
    fields = list(sel) if sel else list(cols)
    return fields, rows


def _voucher_type_is(fields: Sequence[str], row: Sequence[str], want: str) -> bool:
    """VOU_TYPE 優先；否則 TX_TYPE。want=RJ/PJ（實庫常見 CARJ／CAPJ）。"""
    want_u = (want or "").strip().upper()
    vou = _row_val(row, fields, "VOU_TYPE").strip().upper()
    if vou:
        if want_u == "RJ":
            return vou == "RJ" or vou.endswith("RJ")
        if want_u == "PJ":
            return vou == "PJ" or vou.endswith("PJ")
        return vou == want_u or vou.endswith(want_u)
    tx = _row_val(row, fields, "TX_TYPE").strip().upper()
    if want_u == "RJ":
        return tx in {"RJ", "REC"} or tx.endswith("RJ") or tx.startswith("REC")
    if want_u == "PJ":
        return tx in {"PJ", "PAY"} or tx.endswith("PJ") or tx.startswith("PAY")
    return False


def _should_include(kinds: Sequence[str], category: str) -> bool:
    if not kinds:
        return False
    return category in kinds


def _sum_invoice_and_receipt_amts(
    backend: DbBackendBase, mode: QueryMode, party_key: str
) -> Tuple[Decimal, Decimal]:
    """合計發票金額（INVOICE.NET_AMT）與發票收款金額（VOUCHER RJ）。"""
    inv_total = Decimal("0")
    recv_total = Decimal("0")
    if not party_key:
        return inv_total, recv_total
    if _has_table(backend, "INVOICE"):
        cols = backend.list_columns("INVOICE")
        pcs = _match_party_cols(cols, mode)
        cols, rows = _fetch_rows_by_party(backend, "INVOICE", pcs, party_key)
        for row in rows:
            inv_total += _doc_net_amt(cols, row)
    if _has_table(backend, "VOUCHER"):
        cols = backend.list_columns("VOUCHER")
        pcs = _match_party_cols(cols, mode)
        cols, rows = _fetch_rows_by_party(backend, "VOUCHER", pcs, party_key)
        for row in rows:
            if not _voucher_type_is(cols, row, "RJ"):
                continue
            recv_total += _d(
                _first_val(
                    row, cols, ("REC_AMT", "NET_AMT", "TX_AMOUNT", "VOU_AMT", "PAY_AMT")
                )
            )
    return inv_total, recv_total


def compute_remain_credit(credit_limit: object, inv_amt: object, recv_amt: object) -> Decimal:
    """
    剩餘信用額規則：
    - 信用額=0 → 剩餘=0
    - 否則 剩餘=信用額+發票收款金額-發票金額；若剩餘>信用額則=信用額
    """
    limit = _d(credit_limit)
    if limit == 0:
        return Decimal("0")
    remain = limit + _d(recv_amt) - _d(inv_amt)
    if remain > limit:
        remain = limit
    return remain


def enrich_party_credit(
    backend: DbBackendBase, mode: QueryMode, party: PartyInfo
) -> PartyInfo:
    """依 CUSTVEND.CUST_LIMIT 與全部 INV/REC 交易寫入剩餘信用額。"""
    limit = _d(party.credit_limit)
    if limit == 0:
        party.remain_credit = _fmt_amt_val("0")
        return party
    inv_amt, recv_amt = _sum_invoice_and_receipt_amts(backend, mode, party.key)
    party.remain_credit = _fmt_amt_val(compute_remain_credit(limit, inv_amt, recv_amt))
    return party


def load_party_transactions(
    backend: DbBackendBase,
    mode: QueryMode,
    party_key: str,
    date_from: str = "",
    date_to: str = "",
    tx_kinds: Optional[Sequence[str] | str] = None,
    *,
    tx_kind: str = "",
) -> List[PartyQueryLine]:
    if not party_key:
        return []
    if tx_kinds is None and tx_kind:
        kinds = normalize_tx_kinds(tx_kind)
    else:
        kinds = normalize_tx_kinds(tx_kinds)
    from_d = _parse_filter_date(date_from)
    to_d = _parse_filter_date(date_to)
    lines: List[PartyQueryLine] = []

    # INVOICE → INV
    if _should_include(kinds, "INV") and _has_table(backend, "INVOICE"):
        cols = backend.list_columns("INVOICE")
        pcs = _match_party_cols(cols, mode)
        cols, rows = _fetch_rows_by_party(backend, "INVOICE", pcs, party_key)
        for row in rows:
            raw_date = _first_val(row, cols, ("DATE", "TX_DATE", "DOC_DATE"))
            if not _date_in_range(raw_date, from_d, to_d):
                continue
            lines.append(_line_from_invoice(cols, row))

    # VOUCHER VOU_TYPE=RJ → REC
    if _should_include(kinds, "REC") and _has_table(backend, "VOUCHER"):
        cols = backend.list_columns("VOUCHER")
        pcs = _match_party_cols(cols, mode)
        cols, rows = _fetch_rows_by_party(backend, "VOUCHER", pcs, party_key)
        for row in rows:
            if not _voucher_type_is(cols, row, "RJ"):
                continue
            raw_date = _first_val(row, cols, ("DATE", "TX_DATE", "VOU_DATE"))
            if not _date_in_range(raw_date, from_d, to_d):
                continue
            lines.append(_line_from_voucher_rj(cols, row))

    # PURCHASE → PUR
    if _should_include(kinds, "PUR") and _has_table(backend, "PURCHASE"):
        cols = backend.list_columns("PURCHASE")
        pcs = _match_party_cols(cols, mode)
        cols, rows = _fetch_rows_by_party(backend, "PURCHASE", pcs, party_key)
        for row in rows:
            raw_date = _first_val(row, cols, ("DATE", "TX_DATE", "DOC_DATE"))
            if not _date_in_range(raw_date, from_d, to_d):
                continue
            lines.append(_line_from_purchase(cols, row))

    # VOUCHER VOU_TYPE=PJ → PAY
    if _should_include(kinds, "PAY") and _has_table(backend, "VOUCHER"):
        cols = backend.list_columns("VOUCHER")
        pcs = _match_party_cols(cols, mode)
        cols, rows = _fetch_rows_by_party(backend, "VOUCHER", pcs, party_key)
        for row in rows:
            if not _voucher_type_is(cols, row, "PJ"):
                continue
            raw_date = _first_val(row, cols, ("DATE", "TX_DATE", "VOU_DATE"))
            if not _date_in_range(raw_date, from_d, to_d):
                continue
            lines.append(_line_from_voucher_pj(cols, row))

    lines.sort(key=lambda x: (x.date, x.tx_category, x.tx_key))
    return lines


def find_party_index(parties: List[PartyInfo], party_key: str) -> int:
    key = (party_key or "").strip().upper()
    if not key:
        return 0
    for i, p in enumerate(parties):
        if (p.key or "").strip().upper() == key:
            return i
    return -1


def party_key_from_source_row(
    fields: Sequence[str], row: Sequence[str], mode: QueryMode, *, combined: bool = False
) -> str:
    if not row:
        return ""
    names = _all_party_key_names() if combined else _party_key_names(mode)
    return _first_val(row, fields, names)


def load_party_query(
    backend: DbBackendBase,
    do_proc: str,
    source_row: Sequence[str],
    source_fields: Sequence[str],
    *,
    table_name: str = "",
    other_title: str = "",
    party_index: int = -1,
    date_from: str = "",
    date_to: str = "",
    tx_kinds: Optional[Sequence[str] | str] = None,
    tx_kind: str = "",
    party_key: str = "",
) -> Tuple[Optional[PartyQueryDocument], Optional[str]]:
    mode = resolve_party_query_mode(do_proc, table_name, other_title)
    if mode is None:
        return None, "此作業非顧客／供應商查詢。"
    combined = is_cust_vend_combined_title(other_title)
    try:
        backend.refresh_for_read()
    except Exception:
        pass
    parties, err = load_parties(backend, mode, combined=combined)
    if err:
        return None, err
    if not parties:
        return None, "CUSTVEND 沒有可查詢的資料。"
    date_from_n = normalize_date_text(date_from)
    date_to_n = normalize_date_text(date_to)
    if tx_kinds is None and tx_kind:
        kinds = normalize_tx_kinds(tx_kind)
    else:
        kinds = normalize_tx_kinds(tx_kinds)
    start_key = party_key_from_source_row(
        source_fields, source_row, mode, combined=combined
    )
    explicit_key = (party_key or "").strip()
    # party_index < 0：依來源列／party_key 定位；>= 0：明確索引（含 FIRST=0）
    if party_index is not None and party_index >= 0:
        idx = party_index
    elif explicit_key:
        idx = find_party_index(parties, explicit_key)
        if idx < 0:
            return None, "找不到此顧客-供應商編號。"
    elif start_key:
        idx = find_party_index(parties, start_key)
        if idx < 0:
            idx = 0
    else:
        idx = 0
    if idx < 0 or idx >= len(parties):
        idx = 0
    resolved_key = parties[idx].key
    enrich_party_credit(backend, mode, parties[idx])
    lines = load_party_transactions(
        backend,
        mode,
        resolved_key,
        date_from=date_from_n,
        date_to=date_to_n,
        tx_kinds=kinds,
    )
    return PartyQueryDocument(
        mode=mode,
        parties=parties,
        party_index=idx,
        date_from=date_from_n,
        date_to=date_to_n,
        tx_kinds=kinds,
        lines=lines,
    ), None


def line_search_blob(ln: PartyQueryLine) -> str:
    return " ".join(
        [
            ln.date,
            ln.tx_category,
            ln.tx_key,
            ln.currency,
            ln.rate,
            ln.inv_amt,
            ln.paid_amt,
            ln.recv_amt,
            ln.settle_amt,
        ]
    ).lower()


def filter_party_lines(
    lines: List[PartyQueryLine], keyword: str
) -> List[PartyQueryLine]:
    kw = (keyword or "").strip().lower()
    if not kw:
        return list(lines)
    return [ln for ln in lines if kw in line_search_blob(ln)]


def find_line_index(lines: List[PartyQueryLine], keyword: str) -> Optional[int]:
    kw = (keyword or "").strip().lower()
    if not kw:
        return None
    for i, ln in enumerate(lines):
        if kw in line_search_blob(ln):
            return i
    return None


def _sum_group(
    lines: List[PartyQueryLine], categories: Sequence[str]
) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
    inv = paid = recv = settle = Decimal("0")
    want = {c.upper() for c in categories}
    for ln in lines:
        if (ln.tx_category or "").upper() not in want:
            continue
        inv += _d(ln.inv_amt)
        paid += _d(ln.paid_amt)
        recv += _d(ln.recv_amt)
        settle += _d(ln.settle_amt)
    return inv, paid, recv, settle


def totals_dict(lines: List[PartyQueryLine]) -> dict[str, str]:
    """
    發票合計：INV+REC → 金額/已付/收款/清賬
    購貨發票合計：PUR+PAY → 金額/已付/付款/清賬
    """
    i_amt, i_paid, i_recv, i_settle = _sum_group(lines, ("INV", "REC"))
    p_amt, p_paid, p_recv, p_settle = _sum_group(lines, ("PUR", "PAY"))
    return {
        "inv_amt": _fmt_amt_val(i_amt),
        "inv_paid_amt": _fmt_amt_val(i_paid),
        "inv_recv_amt": _fmt_amt_val(i_recv),
        "inv_settle_amt": _fmt_amt_val(i_settle),
        "pur_amt": _fmt_amt_val(p_amt),
        "pur_paid_amt": _fmt_amt_val(p_paid),
        "pur_pay_amt": _fmt_amt_val(p_recv),
        "pur_settle_amt": _fmt_amt_val(p_settle),
        # 相容舊鍵
        "total_inv_amt": _fmt_amt_val(i_amt),
        "total_paid_amt": _fmt_amt_val(i_paid),
        "total_recv_amt": _fmt_amt_val(i_recv),
        "total_settle_amt": _fmt_amt_val(i_settle),
    }


def current_party(doc: PartyQueryDocument) -> PartyInfo:
    if not doc.parties:
        return PartyInfo()
    idx = doc.party_index
    if idx < 0 or idx >= len(doc.parties):
        idx = 0
    return doc.parties[idx]
