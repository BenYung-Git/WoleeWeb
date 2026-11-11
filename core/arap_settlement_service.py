from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import List, Literal, Optional, Sequence, Tuple

from core.db_backend import DbBackendBase

SettlementMode = Literal["AR", "AP"]


@dataclass
class SettlementHeader:
    vou_key: str = ""
    settle_date: str = ""
    party_key: str = ""
    party_name: str = ""
    settle_amount: str = ""
    exchange_diff: str = ""


@dataclass
class SettlementLine:
    tx_key: str = ""
    inv_no: str = ""
    date: str = ""
    currency: str = ""
    rate: str = ""
    net_amt: str = ""
    paid_amt: str = ""
    balance: str = ""
    pay_amount: str = ""
    discount: str = ""
    in_trx: bool = False
    old_pay_amount: str = ""
    old_discount: str = ""


@dataclass
class SettlementDocument:
    mode: SettlementMode
    header: SettlementHeader
    lines: List[SettlementLine] = field(default_factory=list)


def invoice_display_label(line: SettlementLine) -> str:
    """發票種類 + 發票編號（TX_KEY + TX_NO）。"""
    parts = [p for p in ((line.tx_key or "").strip(), (line.inv_no or "").strip()) if p]
    return " ".join(parts)


def settlement_proc_ids() -> frozenset[str]:
    """已知應收／應付清賬作業代號（含資料庫實際命名如 Arap）。"""
    return frozenset({"DO_ARAP", "DO_AR", "DO_AP", "ARAP"})


def is_arap_settlement_program(
    do_proc: str,
    table_name: str = "",
    other_title: str = "",
) -> bool:
    """
    判斷是否為應收應付清賬作業：
    - DO_PROC 為 DO_ARAP／DO_AR／DO_AP／Arap 等；或
    - 主檔為 VOUCHER 且 OTHER_TITLE 含清賬／Settlement 等關鍵字。
    """
    proc = (do_proc or "").strip().upper()
    if proc in settlement_proc_ids():
        return True
    if proc in {"AR", "AP"} and (table_name or "").strip().upper() == "VOUCHER":
        return True
    tbl = (table_name or "").strip().upper()
    if tbl != "VOUCHER":
        return False
    title = (other_title or "").strip().upper()
    for marker in (
        "清賬",
        "清帳",
        "SETTLEMENT",
        "應收應付",
        "A/R & A/P",
        "A/R",
        "ARAP",
    ):
        if marker.upper() in title:
            return True
    return False


def _d(val) -> Decimal:
    try:
        return Decimal(str(val or "0").strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _s(val: Decimal, places: int = 2) -> str:
    q = Decimal("0.01") if places == 2 else Decimal(1) / (Decimal(10) ** places)
    return format(val.quantize(q), "f")


def _has_table(backend: DbBackendBase, table_name: str) -> bool:
    try:
        cols = backend.list_columns(table_name)
        return bool(cols)
    except Exception:
        return False


def ensure_trx_table(backend: DbBackendBase, table_name: str) -> None:
    """SQLite 等環境若無 RECTX／PAYTRX 則建立。"""
    if _has_table(backend, table_name):
        return
    sql = (
        f"CREATE TABLE IF NOT EXISTS {table_name} "
        "(VOU_KEY TEXT, TX_KEY TEXT, PAID TEXT, DISCOUNT TEXT)"
    )
    backend.fetch_rows_sql(sql, limit=0)


def _row_val(row: Sequence[str], fields: List[str], name: str) -> str:
    key = (name or "").strip().upper()
    for i, f in enumerate(fields):
        if (f or "").strip().upper() == key and i < len(row):
            return str(row[i] or "").strip()
    return ""


def _doc_net_amt(fields: Sequence[str], row: Sequence[str]) -> Decimal:
    """
    發票／購貨發票淨額：優先 NET_AMT；若為 0 則回退 TX_AMT - DISC_AMT（或 TX_AMT）。
    部分資料（尤其 PURCHASE）NET_AMT 未入賬但 TX_AMT 有值。
    """
    net = _d(_row_val(row, list(fields), "NET_AMT"))
    if net != 0:
        return net
    tx_amt = _d(_row_val(row, list(fields), "TX_AMT"))
    if tx_amt == 0:
        return net
    disc = _d(_row_val(row, list(fields), "DISC_AMT"))
    return tx_amt - disc


def _fetch_one(
    backend: DbBackendBase, table: str, where_col: str, where_val: str
) -> Tuple[List[str], List[str]]:
    cols = backend.list_columns(table)
    if not cols or not where_val:
        return [], []
    wc = None
    for c in cols:
        if (c or "").strip().upper() == where_col.upper():
            wc = c
            break
    if not wc:
        return [], []
    sql = f"SELECT * FROM {table} WHERE {wc} = ?"
    sel, rows = backend.fetch_rows_sql(sql, params=[where_val], limit=1)
    fields = list(sel) if sel else list(cols)
    if not rows:
        return fields, []
    return fields, list(rows[0])


def resolve_settlement_mode(
    do_proc: str,
    voucher_row: Sequence[str],
    voucher_fields: List[str],
) -> Optional[SettlementMode]:
    proc = (do_proc or "").strip().upper()
    if proc in ("DO_AR", "AR"):
        return "AR"
    if proc in ("DO_AP", "AP"):
        return "AP"
    vend = _row_val(voucher_row, voucher_fields, "VEND_KEY")
    cust = _row_val(voucher_row, voucher_fields, "CUST_KEY")
    pay_amt = _d(_row_val(voucher_row, voucher_fields, "PAY_AMT"))
    rec_amt = _d(_row_val(voucher_row, voucher_fields, "REC_AMT"))
    if vend and not cust:
        return "AP"
    if cust and not vend:
        return "AR"
    if pay_amt > 0 and rec_amt <= 0:
        return "AP"
    if rec_amt > 0 and pay_amt <= 0:
        return "AR"
    return "AR" if cust else "AP"


def _build_header(
    mode: SettlementMode,
    voucher_fields: List[str],
    voucher_row: Sequence[str],
) -> SettlementHeader:
    exch_col = "REC_EXCH" if mode == "AR" else "PAY_EXCH"
    amt_col = "REC_AMT" if mode == "AR" else "PAY_AMT"
    key_col = "CUST_KEY" if mode == "AR" else "VEND_KEY"
    name_col = "CUST_NAME" if mode == "AR" else "VEND_NAME"
    settle = _row_val(voucher_row, voucher_fields, amt_col)
    if not settle:
        settle = _row_val(voucher_row, voucher_fields, "TX_AMOUNT")
    return SettlementHeader(
        vou_key=_row_val(voucher_row, voucher_fields, "VOU_KEY"),
        settle_date=_row_val(voucher_row, voucher_fields, "DATE"),
        party_key=_row_val(voucher_row, voucher_fields, key_col),
        party_name=_row_val(voucher_row, voucher_fields, name_col),
        settle_amount=settle,
        exchange_diff=_row_val(voucher_row, voucher_fields, exch_col),
    )


def _line_from_doc(
    doc_fields: List[str],
    doc_row: Sequence[str],
    trx_paid: str = "",
    trx_discount: str = "",
    in_trx: bool = False,
) -> SettlementLine:
    net = _doc_net_amt(doc_fields, doc_row)
    paid = _d(_row_val(doc_row, doc_fields, "PAID_AMT"))
    bal = net - paid
    pay = trx_paid or "0"
    disc = trx_discount or "0"
    return SettlementLine(
        tx_key=_row_val(doc_row, doc_fields, "TX_KEY"),
        inv_no=_row_val(doc_row, doc_fields, "TX_NO"),
        date=_row_val(doc_row, doc_fields, "DATE"),
        currency=_row_val(doc_row, doc_fields, "TX_CURR"),
        rate=_row_val(doc_row, doc_fields, "TX_RATE"),
        net_amt=_s(net),
        paid_amt=_s(paid),
        balance=_s(bal),
        pay_amount=pay,
        discount=disc,
        in_trx=in_trx,
        old_pay_amount=pay,
        old_discount=disc,
    )


def _fetch_trx_map(
    backend: DbBackendBase, trx_table: str, vou_key: str
) -> dict[str, Tuple[str, str]]:
    ensure_trx_table(backend, trx_table)
    cols = backend.list_columns(trx_table)
    if not cols:
        return {}
    sql = f"SELECT * FROM {trx_table} WHERE VOU_KEY = ?"
    sel, rows = backend.fetch_rows_sql(sql, params=[vou_key], limit=5000)
    fields = list(sel) if sel else list(cols)
    out: dict[str, Tuple[str, str]] = {}
    for row in rows:
        txk = _row_val(row, fields, "TX_KEY")
        if not txk:
            continue
        out[txk] = (
            _row_val(row, fields, "PAID"),
            _row_val(row, fields, "DISCOUNT"),
        )
    return out


def _party_keys_to_match(party_key: str) -> List[str]:
    raw = (party_key or "").strip()
    if not raw:
        return []
    out = [raw]
    up = raw.upper()
    if up not in {x.upper() for x in out}:
        out.append(up)
    return out


def _fetch_open_docs(
    backend: DbBackendBase,
    doc_table: str,
    party_col: str,
    party_key: str,
) -> List[Tuple[List[str], List[str]]]:
    cols = backend.list_columns(doc_table)
    if not cols or not party_key:
        return []
    pc = None
    for c in cols:
        if (c or "").strip().upper() == party_col.upper():
            pc = c
            break
    if not pc:
        return []
    keys = _party_keys_to_match(party_key)
    rows_all: List[Sequence[str]] = []
    fields: List[str] = list(cols)
    seen_row: set[str] = set()
    for key in keys:
        sql = f"SELECT * FROM {doc_table} WHERE {pc} = ?"
        sel, rows = backend.fetch_rows_sql(sql, params=[key], limit=5000)
        if sel:
            fields = list(sel)
        for row in rows:
            sig = "|".join(str(x or "") for x in row)
            if sig in seen_row:
                continue
            seen_row.add(sig)
            rows_all.append(row)
    # 大小寫／空白差異：再掃一次同欄位
    if not rows_all:
        sql = f"SELECT * FROM {doc_table}"
        sel, rows = backend.fetch_rows_sql(sql, limit=20000)
        if sel:
            fields = list(sel)
        want = {(party_key or "").strip().upper()}
        for row in rows:
            got = _row_val(row, fields, party_col).strip().upper()
            if got in want:
                rows_all.append(row)

    hits: List[Tuple[List[str], List[str]]] = []
    for row in rows_all:
        net = _doc_net_amt(fields, row)
        paid = _d(_row_val(row, fields, "PAID_AMT"))
        if abs(net - paid) > Decimal("0.0001"):
            hits.append((fields, list(row)))
    return hits


def load_settlement(
    backend: DbBackendBase,
    do_proc: str,
    voucher_row: Sequence[str],
    voucher_fields: List[str],
    *,
    table_name: str = "",
    other_title: str = "",
) -> Tuple[Optional[SettlementDocument], Optional[str]]:
    if not is_arap_settlement_program(do_proc, table_name, other_title):
        return None, "此作業非應收應付清賬。"
    if (table_name or "").strip().upper() not in ("", "VOUCHER"):
        return None, "清賬功能僅適用於傳票（VOUCHER）資料。"
    mode = resolve_settlement_mode(do_proc, voucher_row, voucher_fields)
    if mode is None:
        return None, "無法判斷應收或應付清賬類型。"
    header = _build_header(mode, voucher_fields, voucher_row)
    if not header.vou_key:
        return None, "找不到傳票編號。"
    if not header.party_key:
        return None, "找不到顧客或供應商編號。"

    trx_table = "RECTRX" if mode == "AR" else "PAYTRX"
    doc_table = "INVOICE" if mode == "AR" else "PURCHASE"
    party_col = "CUST_KEY" if mode == "AR" else "VEND_KEY"
    trx_map = _fetch_trx_map(backend, trx_table, header.vou_key)
    lines: List[SettlementLine] = []
    seen: set[str] = set()

    for tx_key, (paid, disc) in trx_map.items():
        doc_cols, doc_row = _fetch_one(backend, doc_table, "TX_KEY", tx_key)
        if not doc_row:
            continue
        lines.append(_line_from_doc(doc_cols, doc_row, paid, disc, in_trx=True))
        seen.add(tx_key.upper())

    for doc_cols, doc_row in _fetch_open_docs(
        backend, doc_table, party_col, header.party_key
    ):
        tx_key = _row_val(doc_row, doc_cols, "TX_KEY")
        if not tx_key or tx_key.upper() in seen:
            continue
        lines.append(_line_from_doc(doc_cols, doc_row))
        seen.add(tx_key.upper())

    lines.sort(key=lambda x: (x.date, x.inv_no, x.tx_key))
    return SettlementDocument(mode=mode, header=header, lines=lines), None


def _line_search_blob(ln: SettlementLine) -> str:
    return " ".join(
        [
            ln.tx_key,
            ln.inv_no,
            ln.date,
            ln.currency,
            ln.net_amt,
            ln.paid_amt,
            ln.balance,
            ln.pay_amount,
            ln.discount,
        ]
    ).lower()


def line_matches_keyword(ln: SettlementLine, keyword: str) -> bool:
    kw = (keyword or "").strip().lower()
    if not kw:
        return False
    return kw in _line_search_blob(ln)


def find_line_index(lines: List[SettlementLine], keyword: str) -> Optional[int]:
    """第一筆符合搜尋關鍵字的列索引（用於跳轉，不過濾）。"""
    kw = (keyword or "").strip().lower()
    if not kw:
        return None
    for i, ln in enumerate(lines):
        if line_matches_keyword(ln, kw):
            return i
    return None


def filter_lines(lines: List[SettlementLine], keyword: str) -> List[SettlementLine]:
    kw = (keyword or "").strip().lower()
    if not kw:
        return list(lines)
    return [ln for ln in lines if line_matches_keyword(ln, kw)]


def sum_totals(lines: List[SettlementLine]) -> Tuple[Decimal, Decimal, Decimal]:
    bal = Decimal("0")
    pay = Decimal("0")
    disc = Decimal("0")
    for ln in lines:
        bal += _d(ln.balance)
        pay += _d(ln.pay_amount)
        disc += _d(ln.discount)
    return bal, pay, disc


def remaining_settlement(
    settle_amount: Decimal,
    total_pay: Decimal,
    total_disc: Decimal,
    exchange_diff: Decimal,
) -> Decimal:
    """尚餘清賬金額 = 清賬金額 - 合計付款金額 - 合計折扣金額 - 兌匯差額"""
    return settle_amount - total_pay - total_disc - exchange_diff


def auto_settle_lines(
    lines: List[SettlementLine],
    settle_amount: str,
    exchange_diff: str,
) -> None:
    """依清賬金額自動分配各列付款金額（由前至後，以發票餘額為上限）。"""
    pool = _d(settle_amount) - _d(exchange_diff)
    if pool < 0:
        pool = Decimal("0")
    for ln in lines:
        ln.pay_amount = "0"
        ln.discount = "0"
    for ln in lines:
        if pool <= Decimal("0"):
            break
        bal = _d(ln.balance)
        if bal <= Decimal("0"):
            continue
        pay = min(bal, pool)
        ln.pay_amount = _s(pay)
        pool -= pay


def save_settlement(
    backend: DbBackendBase,
    doc: SettlementDocument,
) -> Tuple[bool, Optional[str]]:
    if doc.header.vou_key is None:
        return False, "缺少傳票編號。"
    trx_table = "RECTRX" if doc.mode == "AR" else "PAYTRX"
    doc_table = "INVOICE" if doc.mode == "AR" else "PURCHASE"
    exch_col = "REC_EXCH" if doc.mode == "AR" else "PAY_EXCH"
    ensure_trx_table(backend, trx_table)
    vou_key = doc.header.vou_key

    for ln in doc.lines:
        new_pay = _d(ln.pay_amount)
        new_disc = _d(ln.discount)
        old_pay = _d(ln.old_pay_amount)
        old_disc = _d(ln.old_discount)
        delta = (new_pay + new_disc) - (old_pay + old_disc)
        has_trx = ln.in_trx or old_pay != 0 or old_disc != 0

        if new_pay != 0 or new_disc != 0 or has_trx:
            ok = backend.update_one(
                trx_table,
                ["PAID", "DISCOUNT"],
                [_s(new_pay), _s(new_disc)],
                ["VOU_KEY", "TX_KEY"],
                [vou_key, ln.tx_key],
            )
            if not ok and (new_pay != 0 or new_disc != 0):
                ok = backend.insert_one(
                    trx_table,
                    ["VOU_KEY", "TX_KEY", "PAID", "DISCOUNT"],
                    [vou_key, ln.tx_key, _s(new_pay), _s(new_disc)],
                )
            elif not ok and has_trx:
                ok = backend.delete_one(
                    trx_table,
                    ["VOU_KEY", "TX_KEY"],
                    [vou_key, ln.tx_key],
                )
            if not ok and (new_pay != 0 or new_disc != 0 or has_trx):
                return False, backend.last_error or f"無法儲存 {trx_table}。"

        if delta != 0 and ln.tx_key:
            doc_cols, doc_row = _fetch_one(backend, doc_table, "TX_KEY", ln.tx_key)
            if not doc_row:
                continue
            cur_paid = _d(_row_val(doc_row, doc_cols, "PAID_AMT"))
            new_doc_paid = cur_paid + delta
            ok = backend.update_one(
                doc_table,
                ["PAID_AMT"],
                [_s(new_doc_paid)],
                ["TX_KEY"],
                [ln.tx_key],
            )
            if not ok:
                return False, backend.last_error or f"無法更新 {doc_table}.PAID_AMT。"

    ok = backend.update_one(
        "VOUCHER",
        [exch_col],
        [doc.header.exchange_diff or "0"],
        ["VOU_KEY"],
        [vou_key],
    )
    if not ok:
        return False, backend.last_error or "無法更新傳票兌匯差額。"
    return True, None
