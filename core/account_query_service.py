"""賬戶查詢：ACCOUNT 主檔 + VOUCHER／VOUTRX 傳票明細。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from core.arap_settlement_service import _d, _has_table, _row_val, _s
from core.db_backend import DbBackendBase
from core.display_format import (
    format_cell_display,
    format_date_display,
    format_numeric_display,
    parse_qdate,
)

# ACC=賬戶傳票明細（VOUTRX）
TX_KIND_OPTIONS: Tuple[str, ...] = ("ACC",)


@dataclass
class AccountInfo:
    key: str = ""
    parent_key: str = ""
    acc_type: str = ""
    acc_level: str = ""
    name: str = ""


@dataclass
class AccountQueryLine:
    date: str = ""
    vou_key: str = ""
    currency: str = ""
    rate: str = ""
    dr_amt: str = ""
    cr_amt: str = ""
    remark: str = ""


@dataclass
class AccountQueryDocument:
    accounts: List[AccountInfo] = field(default_factory=list)
    account_index: int = 0
    date_from: str = ""
    date_to: str = ""
    tx_kinds: List[str] = field(default_factory=lambda: list(TX_KIND_OPTIONS))
    lines: List[AccountQueryLine] = field(default_factory=list)


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


def _fmt_amt(raw: str) -> str:
    return format_numeric_display(str(raw or ""), "amount")


def _fmt_rate(raw: str) -> str:
    return format_numeric_display(str(raw or ""), "rate")


def normalize_tx_kinds(
    raw: Optional[Sequence[str] | str] = None,
    *,
    default_all: bool = True,
) -> List[str]:
    if raw is None:
        return list(TX_KIND_OPTIONS) if default_all else []
    if isinstance(raw, str):
        s = raw.strip().upper()
        if not s or s == "ALL":
            return list(TX_KIND_OPTIONS) if default_all else []
        if s in {"ACC", "ACCOUNT", "VOUTRX", "賬戶", "帳戶"}:
            return ["ACC"]
        return list(TX_KIND_OPTIONS) if default_all else []
    if len(raw) == 0:
        return []
    out: List[str] = []
    for x in raw:
        xu = str(x or "").strip().upper()
        if xu == "ALL" or xu in {"ACC", "ACCOUNT", "VOUTRX", "賬戶", "帳戶"}:
            if "ACC" not in out:
                out.append("ACC")
    return out


def _is_account_query_title(title: str) -> bool:
    t = (title or "").strip()
    tu = t.upper()
    return any(m in t for m in ("賬戶", "帳戶")) or "ACCOUNT" in tu


def is_account_query_program(
    do_proc: str,
    table_name: str = "",
    other_title: str = "",
) -> bool:
    title = (other_title or "").strip()
    title_u = title.upper()
    proc = (do_proc or "").strip().upper()
    tbl = (table_name or "").strip().upper()

    # 實務：PROGRAM.DO_PROC=Account、WORK_FILE=ACCOUNT、OTHER=Enquiry/查詢
    # 即使尚未帶入 table_name，也要能辨識為賬戶查詢（AI／Web 開查詢帶 key）
    if proc in {"ACCOUNT", "DO_ACCOUNT"} or tbl == "ACCOUNT":
        if (
            not title
            or "查詢" in title
            or "ENQUIRY" in title_u
            or "QUERY" in title_u
            or _is_account_query_title(title)
        ):
            return True

    if "查詢" in title or "QUERY" in title_u:
        if _is_account_query_title(title):
            return True
        if tbl == "ACCOUNT":
            return True

    acc_procs = (
        "DO_ACC_QUERY",
        "ACC_QUERY",
        "ACCOUNT_QUERY",
        "DO_ACCOUNT_QUERY",
        "DO_ACCQ",
        "ACCQ",
    )
    for p in acc_procs:
        if proc == p or proc.endswith(p):
            return True

    if tbl == "ACCOUNT" and ("查詢" in title or "QUERY" in title_u):
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


def _account_key_names() -> Tuple[str, ...]:
    return (
        "ACC_KEY",
        "AC_KEY",
        "ACCOUNT_KEY",
        "ACC_CODE",
        "AC_CODE",
        "ACCOUNT_CODE",
        "AC_NO",
        "ACC_NO",
        "ACCOUNT_NO",
        "KEY_CODE",
        "KEY",
    )


def _account_cols(cols: Sequence[str]) -> List[str]:
    found: List[str] = []
    for name in _account_key_names():
        c = _find_col(cols, name)
        if c and c not in found:
            found.append(c)
    return found


def _guess_account_key(fields: Sequence[str], row: Sequence[str]) -> str:
    key = _first_val(row, fields, _account_key_names())
    if key:
        return key
    # 後備：任何 *KEY／*CODE／*NO 欄的第一個非空值
    for c in fields:
        cu = (c or "").strip().upper()
        if not cu or cu in {"AC_TYPE", "ACC_TYPE", "TYPE"}:
            continue
        if (
            cu.endswith("_KEY")
            or cu.endswith("_CODE")
            or cu.endswith("_NO")
            or cu in {"CODE", "NO", "NUMBER"}
        ):
            v = _row_val(row, fields, c).strip()
            if v:
                return v
    return ""


def _account_info_from_row(fields: Sequence[str], row: Sequence[str]) -> AccountInfo:
    return AccountInfo(
        key=_guess_account_key(fields, row),
        parent_key=_first_val(
            row,
            fields,
            (
                "GENERAL",
                "PARENT_KEY",
                "PARENT_ACC",
                "UPPER_KEY",
                "ACC_PARENT",
                "AC_PARENT",
                "PARENT",
                "PARENT_CODE",
            ),
        ),
        acc_type=_first_val(
            row,
            fields,
            ("AC_TYPE", "ACC_TYPE", "ACC_CLASS", "TYPE", "CATEGORY", "CLASS"),
        ),
        acc_level=_first_val(
            row, fields, ("ACC_LEVEL", "AC_LEVEL", "LEVEL", "ACC_LVL", "LVL")
        ),
        name=_first_val(
            row,
            fields,
            (
                "ACC_NAME",
                "AC_NAME",
                "ACCOUNT_NAME",
                "NAME",
                "DESC",
                "DESCRIPTION",
                "AC_DESC",
            ),
        ),
    )


_HEADER_LIKE_TYPES = frozenset(
    {
        "HEADER",
        "TITLE",
        "GROUP",
        "SUMMARY",
        "TOTAL",
        "H",
        "T",
        "G",
        "S",
        "標題",
        "總類",
        "合計",
    }
)
_DETAIL_LIKE_TYPES = frozenset(
    {
        "DETAIL",
        "DET",
        "D",
        "明細",
        "DETAIL ACCOUNT",
        "DETAILS",
    }
)


def _is_detail_account(fields: Sequence[str], row: Sequence[str]) -> bool:
    """
    ACCOUNT.AC_TYPE／ACC_TYPE 為 DETAIL（或常見等同值）才納入。
    空白視為明細；HEADER／TITLE 等排除。
    """
    for name in ("AC_TYPE", "ACC_TYPE"):
        if not _find_col(fields, name):
            continue
        v = _row_val(row, fields, name).strip().upper()
        if not v:
            return True
        if v in _DETAIL_LIKE_TYPES or v.startswith("DETAIL") or "明細" in v:
            return True
        if v in _HEADER_LIKE_TYPES or v.startswith("HEADER") or v.startswith("TITLE"):
            return False
        # 其他非標題類代碼：視為明細（相容各系統代碼）
        return True
    return True


def load_accounts(backend: DbBackendBase) -> Tuple[List[AccountInfo], Optional[str]]:
    table = "ACCOUNT"
    if not _has_table(backend, table):
        return [], f"找不到 {table} 資料表。"
    cols = backend.list_columns(table)
    if not cols:
        return [], f"無法讀取 {table} 欄位。"
    _sel, rows = backend.fetch_rows_sql(f"SELECT * FROM {table}", limit=100000)
    if not rows:
        return [], "ACCOUNT 沒有可查詢的資料。"

    def _collect(predicate) -> List[AccountInfo]:
        out: List[AccountInfo] = []
        seen: set[str] = set()
        for row in rows:
            if predicate is not None and not predicate(cols, row):
                continue
            info = _account_info_from_row(cols, row)
            if not info.key or info.key.upper() in seen:
                continue
            seen.add(info.key.upper())
            out.append(info)
        out.sort(key=lambda a: a.key.upper())
        return out

    # 優先：AC_TYPE=DETAIL（及等同）
    detail_out = _collect(_is_detail_account)
    if detail_out:
        return detail_out, None

    # 後備：若 DETAIL 條件無結果，但仍有帶鍵值列 → 載入全部有編號的賬戶
    all_out = _collect(None)
    if all_out:
        return all_out, None

    # 診斷：有列但無鍵值
    sample_cols = ", ".join((cols or [])[:12])
    return (
        [],
        "ACCOUNT 沒有可查詢的資料"
        f"（已讀 {len(rows)} 筆，但找不到賬戶編號欄或 DETAIL 資料。"
        f"欄位：{sample_cols}）。",
    )


def find_account_index(accounts: List[AccountInfo], account_key: str) -> int:
    raw = (account_key or "").strip()
    if not raw:
        return 0

    def _norm(s: str) -> str:
        return (
            (s or "")
            .strip()
            .upper()
            .replace("－", "-")
            .replace("—", "-")
            .replace("–", "-")
            .replace("_", "-")
            .replace(" ", "")
        )

    key = _norm(raw)
    key_no_hyphen = key.replace("-", "")
    for i, a in enumerate(accounts):
        ak = _norm(a.key or "")
        if not ak:
            continue
        if ak == key:
            return i
        ak_no_hyphen = ak.replace("-", "")
        # 完整鍵或缺連字號（621500-00 / 62150000）
        if ak_no_hyphen == key_no_hyphen:
            return i
        # 只輸入 AC_NO（621500）對 AC_KEY（621500-00）
        if ak.split("-", 1)[0] == key_no_hyphen or ak_no_hyphen == key.split("-", 1)[0]:
            return i
    return -1


def account_key_from_source_row(fields: Sequence[str], row: Sequence[str]) -> str:
    if not row:
        return ""
    return _first_val(row, fields, _account_key_names())


def current_account(doc: AccountQueryDocument) -> AccountInfo:
    if not doc.accounts:
        return AccountInfo()
    idx = doc.account_index
    if idx < 0 or idx >= len(doc.accounts):
        idx = 0
    return doc.accounts[idx]


def _fetch_rows_by_account(
    backend: DbBackendBase,
    table: str,
    acc_cols: Sequence[str],
    account_key: str,
) -> Tuple[List[str], List[Sequence[str]]]:
    cols = backend.list_columns(table)
    if not cols or not account_key or not acc_cols:
        return [], []
    where = " OR ".join(f"{c} = ?" for c in acc_cols)
    params = [account_key] * len(acc_cols)
    sql = f"SELECT * FROM {table} WHERE ({where})"
    _sel, rows = backend.fetch_rows_sql(sql, params=params, limit=50000)
    return cols, rows


def _line_from_voutrx(
    fields: Sequence[str],
    row: Sequence[str],
    *,
    header: Optional[Dict[str, str]] = None,
) -> AccountQueryLine:
    raw_date = _first_val(row, fields, ("DATE", "TX_DATE", "VOU_DATE", "DOC_DATE"))
    rate_raw = _first_val(row, fields, ("TX_RATE", "RATE", "EX_RATE"))
    curr_raw = _first_val(row, fields, ("TX_CURR", "CURRENCY", "CURR"))
    remark_raw = _first_val(
        row, fields, ("REMARK", "NOTE", "MEMO", "DESCRIPTION", "DESC", "ITEM_REMARK")
    )
    dr_raw = _first_val(row, fields, ("DR_AMT", "DEBIT", "DEBIT_AMT", "DR"))
    cr_raw = _first_val(row, fields, ("CR_AMT", "CREDIT", "CREDIT_AMT", "CR"))
    vou_key = _first_val(row, fields, ("VOU_KEY", "TX_KEY", "TX_NO", "VOUCHER_NO"))
    if header:
        if not raw_date:
            raw_date = header.get("date", "")
        if not rate_raw:
            rate_raw = header.get("rate", "")
        if not curr_raw:
            curr_raw = header.get("currency", "")
        if not remark_raw:
            remark_raw = header.get("remark", "")
    return AccountQueryLine(
        date=format_cell_display("DATE", raw_date, "", "DATE") if raw_date else "",
        vou_key=vou_key,
        currency=curr_raw,
        rate=_fmt_rate(rate_raw) if rate_raw else "",
        dr_amt=_fmt_amt(dr_raw) if dr_raw else _fmt_amt("0"),
        cr_amt=_fmt_amt(cr_raw) if cr_raw else _fmt_amt("0"),
        remark=remark_raw,
    )


def _load_voucher_headers(backend: DbBackendBase) -> Dict[str, Dict[str, str]]:
    """VOUCHER 表頭：以 VOU_KEY 對應日期／貨幣／滙率／備註。"""
    if not _has_table(backend, "VOUCHER"):
        return {}
    cols = backend.list_columns("VOUCHER")
    if not cols:
        return {}
    _sel, rows = backend.fetch_rows_sql("SELECT * FROM VOUCHER", limit=100000)
    out: Dict[str, Dict[str, str]] = {}
    for row in rows:
        key = _first_val(row, cols, ("VOU_KEY", "TX_KEY", "TX_NO", "VOUCHER_NO"))
        if not key:
            continue
        raw_date = _first_val(row, cols, ("DATE", "TX_DATE", "VOU_DATE", "DOC_DATE"))
        out[key.strip().upper()] = {
            "date": format_cell_display("DATE", raw_date, "", "DATE") if raw_date else "",
            "currency": _first_val(row, cols, ("TX_CURR", "CURRENCY", "CURR")),
            "rate": _first_val(row, cols, ("TX_RATE", "RATE", "EX_RATE")),
            "remark": _first_val(
                row, cols, ("REMARK", "NOTE", "MEMO", "DESCRIPTION", "DESC")
            ),
        }
    return out


def _line_dedupe_key(ln: AccountQueryLine) -> Tuple[str, str, str, str]:
    return (
        (ln.vou_key or "").strip().upper(),
        (ln.date or "").strip(),
        (ln.dr_amt or "").strip(),
        (ln.cr_amt or "").strip(),
    )


def load_account_transactions(
    backend: DbBackendBase,
    account_key: str,
    date_from: str = "",
    date_to: str = "",
    tx_kinds: Optional[Sequence[str] | str] = None,
) -> List[AccountQueryLine]:
    """載入指定賬戶的 VOUCHER＋VOUTRX 明細。tx_kinds 空清單＝不載入。"""
    if not account_key:
        return []
    if isinstance(tx_kinds, (list, tuple)) and len(tx_kinds) == 0:
        return []
    from_d = _parse_filter_date(date_from)
    to_d = _parse_filter_date(date_to)
    headers = _load_voucher_headers(backend)
    lines: List[AccountQueryLine] = []
    seen: set[Tuple[str, str, str, str]] = set()

    def _append(ln: AccountQueryLine) -> None:
        if from_d or to_d:
            if not ln.date or not _date_in_range(ln.date, from_d, to_d):
                return
        dk = _line_dedupe_key(ln)
        if dk in seen:
            return
        seen.add(dk)
        lines.append(ln)

    # 明細：VOUTRX（以賬戶過濾，缺欄位時以 VOUCHER 表頭補齊）
    if _has_table(backend, "VOUTRX"):
        cols = backend.list_columns("VOUTRX")
        acc_cols = _account_cols(cols)
        if not acc_cols:
            for name in ("ACC_KEY", "ACCOUNT_KEY", "ACC_CODE"):
                c = _find_col(cols, name)
                if c:
                    acc_cols.append(c)
        if acc_cols:
            cols, rows = _fetch_rows_by_account(backend, "VOUTRX", acc_cols, account_key)
            for row in rows:
                vou = _first_val(row, cols, ("VOU_KEY", "TX_KEY", "TX_NO", "VOUCHER_NO"))
                hdr = headers.get((vou or "").strip().upper())
                _append(_line_from_voutrx(cols, row, header=hdr))

    # 表頭：VOUCHER 若本身有賬戶欄位，一併帶入
    if _has_table(backend, "VOUCHER"):
        cols = backend.list_columns("VOUCHER")
        acc_cols = _account_cols(cols)
        if not acc_cols:
            for name in ("ACC_KEY", "ACCOUNT_KEY", "ACC_CODE"):
                c = _find_col(cols, name)
                if c:
                    acc_cols.append(c)
        if acc_cols:
            cols, rows = _fetch_rows_by_account(backend, "VOUCHER", acc_cols, account_key)
            for row in rows:
                _append(_line_from_voutrx(cols, row))

    lines.sort(key=lambda x: (x.date, x.vou_key))
    return lines


def load_account_query(
    backend: DbBackendBase,
    do_proc: str,
    source_row: Sequence[str],
    source_fields: Sequence[str],
    *,
    table_name: str = "",
    other_title: str = "",
    account_index: int = -1,
    date_from: str = "",
    date_to: str = "",
    tx_kinds: Optional[Sequence[str] | str] = None,
    account_key: str = "",
) -> Tuple[Optional[AccountQueryDocument], Optional[str]]:
    if not is_account_query_program(do_proc, table_name, other_title):
        if (table_name or "").strip().upper() != "ACCOUNT":
            return None, "此作業非賬戶查詢。"
    try:
        backend.refresh_for_read()
    except Exception:
        pass
    accounts, err = load_accounts(backend)
    if err:
        return None, err
    if not accounts:
        return None, "ACCOUNT 沒有可查詢的資料。"
    date_from_n = normalize_date_text(date_from)
    date_to_n = normalize_date_text(date_to)
    kinds = normalize_tx_kinds(tx_kinds)
    start_key = account_key_from_source_row(source_fields, source_row)
    explicit_key = (account_key or "").strip()
    # account_index < 0：依來源列／account_key 定位；>= 0：明確索引（含 FIRST=0）
    if account_index is not None and account_index >= 0:
        idx = account_index
    elif explicit_key:
        idx = find_account_index(accounts, explicit_key)
        if idx < 0:
            # DETAIL 清單找不到時，改載入全部有編號賬戶再找一次
            table = "ACCOUNT"
            if _has_table(backend, table):
                cols = backend.list_columns(table)
                _sel, rows = backend.fetch_rows_sql(f"SELECT * FROM {table}", limit=100000)
                widened: List[AccountInfo] = []
                seen: set[str] = set()
                for row in rows or []:
                    info = _account_info_from_row(cols, row)
                    if not info.key or info.key.upper() in seen:
                        continue
                    seen.add(info.key.upper())
                    widened.append(info)
                widened.sort(key=lambda a: a.key.upper())
                if widened:
                    accounts = widened
                    idx = find_account_index(accounts, explicit_key)
            if idx < 0:
                return None, f"找不到此賬戶編號「{explicit_key}」。"
    elif start_key:
        idx = find_account_index(accounts, start_key)
        if idx < 0:
            idx = 0
    else:
        idx = 0
    if idx < 0 or idx >= len(accounts):
        idx = 0
    account_key = accounts[idx].key
    lines = load_account_transactions(
        backend,
        account_key,
        date_from=date_from_n,
        date_to=date_to_n,
        tx_kinds=kinds,
    )
    return AccountQueryDocument(
        accounts=accounts,
        account_index=idx,
        date_from=date_from_n,
        date_to=date_to_n,
        tx_kinds=kinds,
        lines=lines,
    ), None


def line_search_blob(ln: AccountQueryLine) -> str:
    return " ".join(
        [
            ln.date,
            ln.vou_key,
            ln.currency,
            ln.rate,
            ln.dr_amt,
            ln.cr_amt,
            ln.remark,
        ]
    ).lower()


def filter_account_lines(
    lines: List[AccountQueryLine], keyword: str
) -> List[AccountQueryLine]:
    kw = (keyword or "").strip().lower()
    if not kw:
        return list(lines)
    return [ln for ln in lines if kw in line_search_blob(ln)]


def find_line_index(lines: List[AccountQueryLine], keyword: str) -> Optional[int]:
    kw = (keyword or "").strip().lower()
    if not kw:
        return None
    for i, ln in enumerate(lines):
        if kw in line_search_blob(ln):
            return i
    return None


def totals_dict(lines: List[AccountQueryLine]) -> dict[str, str]:
    dr = cr = Decimal("0")
    for ln in lines:
        dr += _d(ln.dr_amt)
        cr += _d(ln.cr_amt)
    return {
        "dr_amt": _fmt_amt(str(dr)),
        "cr_amt": _fmt_amt(str(cr)),
    }
