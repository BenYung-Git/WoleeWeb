"""發票收款／購貨付款：由「其他功能」開啟，寫入 VOUCHER／VOUTRX／RECTRX|PAYTRX 並更新 PAID_AMT。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Literal, Optional, Sequence, Tuple

from core.db_backend import DbBackendBase
from core.display_format import APP_DATE_DISPLAY
from core.record_key_service import ProgramNumberConfig, allocate_auto_key
from core.row_insert_defaults import apply_insert_bit_defaults, fill_sqlite_not_null_defaults

ReceiptPaymentMode = Literal["AR", "AP"]  # AR=收款(INVOICE)，AP=付款(PURCHASE)

# 收／付款方式（COMBOBOX 選項；預設 CHEQUE）
PAY_METHOD_OPTIONS: Tuple[str, ...] = (
    "CASH",
    "CHEQUE",
    "EPS",
    "VISA",
    "TT",
    "FPS",
    "AliPay",
    "WeChatPay",
)
DEFAULT_PAY_METHOD = "CHEQUE"


@dataclass
class ReceiptPaymentHeader:
    """唯讀顯示：發票／購貨資訊。"""

    mode: ReceiptPaymentMode = "AR"
    inv_key: str = ""  # TX_KEY
    inv_no: str = ""  # 顯示用編號（TX_KEY 或 TX_TYPE-TX_NO）
    inv_date: str = ""
    party_key: str = ""
    party_name: str = ""
    currency: str = ""
    rate: str = "1"
    net_amt: str = "0"
    paid_amt: str = "0"
    balance: str = "0"


@dataclass
class ReceiptPaymentForm:
    """可編輯：收／付款資料。"""

    pay_amount: str = "0"
    pay_date: str = ""
    pay_method: str = ""  # REC_TYPE / PAY_TYPE
    bank: str = ""
    cheque: str = ""
    chq_date: str = ""
    remark: str = ""
    debit_ac: str = ""
    credit_ac: str = ""


@dataclass
class ReceiptPaymentDocument:
    header: ReceiptPaymentHeader = field(default_factory=ReceiptPaymentHeader)
    form: ReceiptPaymentForm = field(default_factory=ReceiptPaymentForm)
    vou_key: str = ""  # 儲存成功後填入


def is_receipt_payment_program(
    do_proc: str = "",
    table_name: str = "",
    other_title: str = "",
) -> bool:
    """
    發票／購貨「其他功能」為收款或付款時觸發。
    - INVOICE + 收款／Receipt → AR
    - PURCHASE + 付款／Payment → AP
    """
    tbl = (table_name or "").strip().upper()
    title = (other_title or "").strip()
    title_u = title.upper()
    if tbl == "INVOICE":
        return any(m in title for m in ("收款",)) or any(
            m in title_u for m in ("RECEIPT", "RECEIVE", "COLLECTION")
        )
    if tbl == "PURCHASE":
        return any(m in title for m in ("付款",)) or any(
            m in title_u for m in ("PAYMENT", "PAY ")
        ) or title_u.strip() in ("PAYMENT", "PAY")
    # 標題明確且表名可推斷
    if any(m in title for m in ("收款",)) or "RECEIPT" in title_u:
        return tbl in ("", "INVOICE")
    if any(m in title for m in ("付款",)) or "PAYMENT" in title_u:
        return tbl in ("", "PURCHASE")
    _ = do_proc
    return False


def resolve_receipt_payment_mode(
    table_name: str = "",
    other_title: str = "",
) -> Optional[ReceiptPaymentMode]:
    tbl = (table_name or "").strip().upper()
    title = (other_title or "").strip()
    title_u = title.upper()
    if tbl == "INVOICE" or any(m in title for m in ("收款",)) or "RECEIPT" in title_u:
        if tbl in ("", "INVOICE"):
            return "AR"
    if tbl == "PURCHASE" or any(m in title for m in ("付款",)) or "PAYMENT" in title_u:
        if tbl in ("", "PURCHASE"):
            return "AP"
    if tbl == "INVOICE":
        return "AR"
    if tbl == "PURCHASE":
        return "AP"
    return None


def _d(val) -> Decimal:
    try:
        return Decimal(str(val or "0").strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _s(val: Decimal, places: int = 2) -> str:
    q = Decimal("0.01") if places == 2 else Decimal(1) / (Decimal(10) ** places)
    return format(val.quantize(q), "f")


def _row_val(row: Sequence[str], fields: Sequence[str], name: str) -> str:
    want = (name or "").strip().upper()
    for i, f in enumerate(fields):
        if str(f or "").strip().upper() == want:
            if i < len(row):
                return str(row[i] or "").strip()
            return ""
    return ""


def _doc_net_amt(fields: Sequence[str], row: Sequence[str]) -> Decimal:
    """
    發票／購貨發票淨額：優先 NET_AMT；若為 0 則回退 TX_AMT - DISC_AMT（或 TX_AMT）。
    部分資料（尤其 PURCHASE）NET_AMT 未入賬但 TX_AMT 有值。
    """
    net = _d(_row_val(row, fields, "NET_AMT"))
    if net != 0:
        return net
    tx_amt = _d(_row_val(row, fields, "TX_AMT"))
    if tx_amt == 0:
        return net
    disc = _d(_row_val(row, fields, "DISC_AMT"))
    return tx_amt - disc


def _col_map(fields: Sequence[str]) -> Dict[str, str]:
    return {(c or "").strip().upper(): c for c in fields if (c or "").strip()}


def _pick_field(cmap: Dict[str, str], *cands: str) -> str:
    for c in cands:
        hit = cmap.get((c or "").strip().upper())
        if hit:
            return hit
    return ""


def _today() -> str:
    return date.today().strftime(APP_DATE_DISPLAY)


def _has_table(backend: DbBackendBase, table_name: str) -> bool:
    try:
        return bool(backend.list_columns(table_name))
    except Exception:
        return False


def ensure_settle_trx_table(backend: DbBackendBase, table_name: str) -> None:
    """SQLite 等環境若無 RECTX／PAYTRX 則建立（鍵為 VOU_KEY + TX_KEY）。"""
    if _has_table(backend, table_name):
        return
    try:
        from core.db_backend import SqliteBackend

        if not isinstance(backend, SqliteBackend):
            return
        import sqlite3

        conn = sqlite3.connect(backend.db_path)
        try:
            conn.execute(
                f'CREATE TABLE IF NOT EXISTS "{table_name}" '
                "(VOU_KEY TEXT, TX_KEY TEXT, INV_KEY TEXT, PAID TEXT, DISCOUNT TEXT)"
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        return


def load_receipt_payment(
    backend: DbBackendBase,
    doc_row: Sequence[str],
    doc_fields: Sequence[str],
    *,
    table_name: str = "",
    other_title: str = "",
    login_date: str = "",
) -> Tuple[Optional[ReceiptPaymentDocument], Optional[str]]:
    mode = resolve_receipt_payment_mode(table_name, other_title)
    if mode is None:
        return None, "無法判斷收款或付款。"
    fields = list(doc_fields)
    if not fields:
        return None, "找不到主檔欄位。"
    tx_key = _row_val(doc_row, fields, "TX_KEY")
    if not tx_key:
        return None, "找不到發票／單據編號。"

    tx_type = _row_val(doc_row, fields, "TX_TYPE")
    tx_no = _row_val(doc_row, fields, "TX_NO")
    inv_no = tx_key
    if tx_type and tx_no:
        inv_no = f"{tx_type}-{tx_no}" if "-" not in tx_key else tx_key

    if mode == "AR":
        party_key = _row_val(doc_row, fields, "CUST_KEY")
        party_name = _row_val(doc_row, fields, "CUST_NAME")
    else:
        party_key = _row_val(doc_row, fields, "VEND_KEY")
        party_name = _row_val(doc_row, fields, "VEND_NAME")

    net = _doc_net_amt(fields, doc_row)
    paid = _d(_row_val(doc_row, fields, "PAID_AMT"))
    bal = net - paid
    if bal < 0:
        bal = Decimal("0")

    header = ReceiptPaymentHeader(
        mode=mode,
        inv_key=tx_key,
        inv_no=inv_no,
        inv_date=_row_val(doc_row, fields, "DATE"),
        party_key=party_key,
        party_name=party_name,
        currency=_row_val(doc_row, fields, "TX_CURR") or "HKD",
        rate=_row_val(doc_row, fields, "TX_RATE") or "1",
        net_amt=_s(net),
        paid_amt=_s(paid),
        balance=_s(bal),
    )
    form = ReceiptPaymentForm(
        pay_amount=_s(net),
        pay_date=(login_date or "").strip() or _today(),
        pay_method=DEFAULT_PAY_METHOD,
        bank="",
        cheque="",
        chq_date="",
        remark=f"INV#:{inv_no}",
        debit_ac="",
        credit_ac="",
    )
    return ReceiptPaymentDocument(header=header, form=form), None


def _account_name(backend: DbBackendBase, ac_key: str) -> str:
    key = (ac_key or "").strip()
    if not key or not _has_table(backend, "ACCOUNT"):
        return ""
    rows = backend.fetch_rows_where("ACCOUNT", "AC_KEY", key, limit=1)
    if not rows:
        # 相容大小寫：掃前 N 筆
        cols = backend.list_columns("ACCOUNT")
        all_rows = backend.fetch_rows("ACCOUNT", "", False, limit=5000, column_order=cols)
        want = key.upper()
        for r in all_rows:
            if _row_val(r, cols, "AC_KEY").upper() == want:
                return _row_val(r, cols, "AC_NAME")
        return ""
    cols = backend.list_columns("ACCOUNT")
    return _row_val(rows[0], cols, "AC_NAME")


def _allocate_voucher_key(
    backend: DbBackendBase, vou_type: str
) -> Tuple[str, str]:
    """
    依 VOU_TYPE 分組：VOU_NO = 最後+1（8 位補零），VOU_KEY = VOU_TYPE + '-' + VOU_NO。
    """
    cols = backend.list_columns("VOUCHER")
    if not cols:
        raise ValueError("找不到 VOUCHER 資料表。")
    cfg = ProgramNumberConfig(
        key_field="VOU_KEY",
        num_type_field="VOU_TYPE",
        num_control_field="VOU_NO",
        num_digit=8,
        num_separate="-",
    )
    prepared = allocate_auto_key(
        backend,
        "VOUCHER",
        cols,
        cfg,
        {"VOU_TYPE": (vou_type or "").strip()},
    )
    vou_key = (prepared.get("VOU_KEY") or "").strip()
    vou_no = (prepared.get("VOU_NO") or "").strip()
    if not vou_key or not vou_no:
        raise ValueError("無法產生傳票編號。")
    return vou_key, vou_no


def _insert_row(
    backend: DbBackendBase,
    table_name: str,
    values: Dict[str, str],
) -> Tuple[bool, Optional[str]]:
    cols = backend.list_columns(table_name)
    if not cols:
        return False, f"找不到資料表 {table_name}。"
    cmap = _col_map(cols)
    field_names: List[str] = []
    row_values: List[str] = []
    for logical, val in values.items():
        phys = cmap.get((logical or "").strip().upper())
        if not phys:
            continue
        field_names.append(phys)
        row_values.append("" if val is None else str(val))
    if not field_names:
        return False, f"{table_name} 無可寫入欄位。"
    field_names, row_values = apply_insert_bit_defaults(cols, field_names, row_values)
    # SQLite NOT NULL 補齊
    try:
        from core.db_backend import SqliteBackend

        if isinstance(backend, SqliteBackend):
            import sqlite3

            conn = sqlite3.connect(backend.db_path)
            try:
                cur = conn.cursor()
                real = backend._table(table_name)  # type: ignore[attr-defined]
                cur.execute(f'PRAGMA table_info("{real}")')
                infos = cur.fetchall()
            finally:
                conn.close()
            field_names, row_values = fill_sqlite_not_null_defaults(
                infos, field_names, row_values
            )
    except Exception:
        pass
    ok = backend.insert_one(table_name, field_names, row_values)
    if not ok:
        return False, getattr(backend, "last_error", "") or f"新增 {table_name} 失敗。"
    return True, None


def save_receipt_payment(
    backend: DbBackendBase,
    doc: ReceiptPaymentDocument,
) -> Tuple[bool, Optional[str], str]:
    """
    儲存收／付款：
    1) INSERT VOUCHER（RJ／PJ 自動編號）
    2) 若借／貸賬戶不空 → INSERT VOUTRX 兩行
    3) INSERT RECTX／PAYTRX（VOU_KEY + TX_KEY）
    4) 更新 INVOICE／PURCHASE.PAID_AMT
    回傳 (ok, err, vou_key)
    """
    header = doc.header
    form = doc.form
    mode = header.mode
    inv_key = (header.inv_key or "").strip()
    if not inv_key:
        return False, "缺少發票／單據編號。", ""

    pay = _d(form.pay_amount)
    if pay <= 0:
        return False, "付款金額必須大於 0。", ""

    vou_type = "RJ" if mode == "AR" else "PJ"
    tx_type = "AR" if mode == "AR" else "AP"
    try:
        vou_key, vou_no = _allocate_voucher_key(backend, vou_type)
    except Exception as ex:
        return False, str(ex) or "無法產生傳票編號。", ""

    pay_s = _s(pay)
    pay_date = (form.pay_date or "").strip() or _today()
    curr = (header.currency or "").strip() or "HKD"
    rate = (header.rate or "").strip() or "1"
    remark = (form.remark or "").strip()
    bank = (form.bank or "").strip()
    cheque = (form.cheque or "").strip()
    chq_date = (form.chq_date or "").strip()
    pay_method = (form.pay_method or "").strip()

    vou_vals: Dict[str, str] = {
        "VOU_KEY": vou_key,
        "VOU_TYPE": vou_type,
        "VOU_NO": vou_no,
        "TX_TYPE": tx_type,
        "DATE": pay_date,
        "TX_CURR": curr,
        "TX_RATE": rate,
        "TX_AMOUNT": pay_s,
        "BANK": bank,
        "CHEQUE": cheque,
        "CHQ_DATE": chq_date,
        "REMARK1": remark,
    }
    if mode == "AR":
        vou_vals.update(
            {
                "CUST_KEY": header.party_key,
                "CUST_NAME": header.party_name,
                "REC_AMT": pay_s,
                "INV_SETTLE": pay_s,
                "REC_TYPE": pay_method,
            }
        )
    else:
        vou_vals.update(
            {
                "VEND_KEY": header.party_key,
                "VEND_NAME": header.party_name,
                "PAY_AMT": pay_s,
                "EXP_SETTLE": pay_s,
                "PAY_TYPE": pay_method,
            }
        )

    ok, err = _insert_row(backend, "VOUCHER", vou_vals)
    if not ok:
        return False, err, ""

    debit = (form.debit_ac or "").strip()
    credit = (form.credit_ac or "").strip()
    if debit and credit:
        if not _has_table(backend, "VOUTRX"):
            return False, "找不到 VOUTRX 資料表。", vou_key
        debit_name = _account_name(backend, debit)
        credit_name = _account_name(backend, credit)
        for item_no, ac_key, ac_name, debit_amt, credit_amt in (
            ("1", debit, debit_name, pay_s, "0"),
            ("2", credit, credit_name, "0", pay_s),
        ):
            ok, err = _insert_row(
                backend,
                "VOUTRX",
                {
                    "ITEM_NO": item_no,
                    "VOU_KEY": vou_key,
                    "AC_KEY": ac_key,
                    "AC_NAME": ac_name,
                    "CURRENCY": curr,
                    "RATE": rate,
                    "DEBIT": debit_amt,
                    "CREDIT": credit_amt,
                    "NARRAT1": remark,
                    "TX_TYPE": tx_type,
                },
            )
            if not ok:
                return False, err, vou_key

    trx_table = "RECTRX" if mode == "AR" else "PAYTRX"
    ensure_settle_trx_table(backend, trx_table)
    # 實庫多為 TX_KEY；規格 INV_KEY＝發票編號，兩者一併寫入（缺欄則略過）
    ok, err = _insert_row(
        backend,
        trx_table,
        {
            "VOU_KEY": vou_key,
            "TX_KEY": inv_key,
            "INV_KEY": inv_key,
            "PAID": pay_s,
            "DISCOUNT": "0",
        },
    )
    if not ok:
        return False, err, vou_key

    doc_table = "INVOICE" if mode == "AR" else "PURCHASE"
    new_paid = _d(header.paid_amt) + pay
    ok = backend.update_one(
        doc_table,
        ["PAID_AMT"],
        [_s(new_paid)],
        ["TX_KEY"],
        [inv_key],
    )
    if not ok:
        return (
            False,
            getattr(backend, "last_error", "") or f"無法更新 {doc_table}.PAID_AMT。",
            vou_key,
        )

    doc.vou_key = vou_key
    return True, None, vou_key


def is_document_fully_paid(
    fields: Sequence[str],
    row: Sequence[str],
) -> bool:
    """
    若 WORK_FILE 有已付金額與發票／購貨金額，且
    發票金額（或購貨發票金額）<= 已付金額，回傳 True（應用於停用「其他功能」）。
    無相關欄位時回傳 False。
    """
    names = {(f or "").strip().upper() for f in fields if (f or "").strip()}
    if "PAID_AMT" not in names:
        return False
    if "NET_AMT" not in names and "TX_AMT" not in names:
        return False
    net = _doc_net_amt(fields, row)
    paid = _d(_row_val(row, fields, "PAID_AMT"))
    return net <= paid


def document_to_dict(doc: ReceiptPaymentDocument) -> Dict:
    h = doc.header
    f = doc.form
    return {
        "mode": h.mode,
        "vou_key": doc.vou_key or "",
        "header": {
            "mode": h.mode,
            "inv_key": h.inv_key,
            "inv_no": h.inv_no,
            "inv_date": h.inv_date,
            "party_key": h.party_key,
            "party_name": h.party_name,
            "currency": h.currency,
            "rate": h.rate,
            "net_amt": h.net_amt,
            "paid_amt": h.paid_amt,
            "balance": h.balance,
        },
        "form": {
            "pay_amount": f.pay_amount,
            "pay_date": f.pay_date,
            "pay_method": f.pay_method,
            "bank": f.bank,
            "cheque": f.cheque,
            "chq_date": f.chq_date,
            "remark": f.remark,
            "debit_ac": f.debit_ac,
            "credit_ac": f.credit_ac,
        },
    }


def document_from_dict(data: Dict) -> ReceiptPaymentDocument:
    h = data.get("header") or {}
    f = data.get("form") or {}
    mode = (data.get("mode") or h.get("mode") or "AR").strip().upper()
    if mode not in ("AR", "AP"):
        mode = "AR"
    return ReceiptPaymentDocument(
        header=ReceiptPaymentHeader(
            mode=mode,  # type: ignore[arg-type]
            inv_key=str(h.get("inv_key") or ""),
            inv_no=str(h.get("inv_no") or ""),
            inv_date=str(h.get("inv_date") or ""),
            party_key=str(h.get("party_key") or ""),
            party_name=str(h.get("party_name") or ""),
            currency=str(h.get("currency") or ""),
            rate=str(h.get("rate") or "1"),
            net_amt=str(h.get("net_amt") or "0"),
            paid_amt=str(h.get("paid_amt") or "0"),
            balance=str(h.get("balance") or "0"),
        ),
        form=ReceiptPaymentForm(
            pay_amount=str(f.get("pay_amount") or "0"),
            pay_date=str(f.get("pay_date") or ""),
            pay_method=str(f.get("pay_method") or ""),
            bank=str(f.get("bank") or ""),
            cheque=str(f.get("cheque") or ""),
            chq_date=str(f.get("chq_date") or ""),
            remark=str(f.get("remark") or ""),
            debit_ac=str(f.get("debit_ac") or ""),
            credit_ac=str(f.get("credit_ac") or ""),
        ),
        vou_key=str(data.get("vou_key") or ""),
    )
