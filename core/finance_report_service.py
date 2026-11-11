"""財務報表 (RPT_TYPE=FINANCE)：PERIOD 期間、賬戶 OPEN_BAL / PRD_n 計算。"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from core.arap_settlement_service import _d, _row_val
from core.db_backend import DbBackendBase
from core.display_format import format_numeric_display, parse_qdate


def _period_num_from_row(fields: Sequence[str], row: Sequence[str]) -> Optional[int]:
    raw = _row_val(row, fields, "PERIOD")
    if not raw:
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def resolve_period_for_date(
    backend: DbBackendBase, d: Optional[date]
) -> Optional[int]:
    """依 PERIOD 表 YEAR/MONTH 對應日期的會計期間編號。"""
    if d is None:
        return None
    if not _has_table(backend, "PERIOD"):
        return None
    cols = backend.list_columns("PERIOD")
    if not cols:
        return None
    _sel, rows = backend.fetch_rows_sql("SELECT * FROM PERIOD", limit=500)
    if not rows:
        _sel, rows = backend.fetch_rows_sql("SELECT * FROM [PERIOD]", limit=500)
    if not rows:
        return None
    fields = list(_sel) if _sel else cols
    y, m = d.year, d.month
    for row in rows:
        try:
            ry = int(float(_row_val(row, fields, "YEAR") or "0"))
            rm = int(float(_row_val(row, fields, "MONTH") or "0"))
        except (TypeError, ValueError):
            continue
        if ry == y and rm == m:
            pn = _period_num_from_row(fields, row)
            if pn is not None:
                return pn
    return None


def resolve_period_range(
    backend: DbBackendBase,
    date_from: str = "",
    date_to: str = "",
) -> Tuple[int, int, Optional[str]]:
    """
  由「由日期」「至日期」解析 FROM_PERIOD / TO_PERIOD。
  無日期時預設當月第一日～最後一日對應之期間。
    """
    from_d = parse_qdate((date_from or "").strip())
    to_d = parse_qdate((date_to or "").strip())
    if from_d is None and to_d is None:
        today = date.today()
        from_d = date(today.year, today.month, 1)
        if today.month == 12:
            to_d = date(today.year, 12, 31)
        else:
            to_d = date(today.year, today.month + 1, 1) - timedelta(days=1)
    if from_d is None and to_d is not None:
        from_d = date(to_d.year, to_d.month, 1)
    if to_d is None and from_d is not None:
        d_first = date(from_d.year, from_d.month, 1)
        if from_d.month == 12:
            to_d = date(from_d.year, 12, 31)
        else:
            nxt = date(from_d.year, from_d.month + 1, 1)
            to_d = nxt - timedelta(days=1)
    from_p = resolve_period_for_date(backend, from_d)
    to_p = resolve_period_for_date(backend, to_d)
    if from_p is None or to_p is None:
        return 1, 1, "無法從 PERIOD 表對應所選日期之會計期間。"
    if from_p > to_p:
        from_p, to_p = to_p, from_p
    return from_p, to_p, None


def _prd_amount(fields: Sequence[str], row: Sequence[str], period_n: int) -> Decimal:
    if period_n <= 0:
        return Decimal("0")
    col = f"PRD_{period_n}"
    return _d(_row_val(row, fields, col))


def _normalize_ac_group(raw: str) -> str:
    """AC_GROUP 正規化：C.O.G.S → COGS。"""
    s = str(raw or "").strip().upper()
    for ch in (".", " ", "_", "-"):
        s = s.replace(ch, "")
    return s


# ASSETS / C.O.G.S / EXPENSES 為正金額，其餘為負金額
_POSITIVE_AC_GROUPS = frozenset({"ASSETS", "COGS", "EXPENSES"})


def account_group_sign(fields: Sequence[str], row: Sequence[str]) -> Decimal:
    """依 ACCOUNT.AC_GROUP 決定金額正負。"""
    grp = _normalize_ac_group(_row_val(row, fields, "AC_GROUP"))
    if grp in _POSITIVE_AC_GROUPS:
        return Decimal("1")
    return Decimal("-1")


def compute_finance_amounts(
    fields: Sequence[str],
    row: Sequence[str],
    from_period: int,
    to_period: int,
    *,
    apply_group_sign: bool = True,
) -> Tuple[Decimal, Decimal, Decimal]:
    """
    初始結餘、本週期金額、結餘。
    FROM=1 TO=1 → OPEN_BAL, PRD_1
    FROM=3 TO=5 → OPEN_BAL+PRD_1+PRD_2, PRD_3+PRD_4+PRD_5
    若 apply_group_sign：ASSETS/COGS/EXPENSES 為正，其餘為負。
    """
    open_bal = _d(_row_val(row, fields, "OPEN_BAL"))
    fp = max(1, int(from_period))
    tp = max(fp, int(to_period))
    if fp <= 1:
        opening = open_bal
    else:
        opening = open_bal
        for p in range(1, fp):
            opening += _prd_amount(fields, row, p)
    period_amt = Decimal("0")
    for p in range(fp, tp + 1):
        period_amt += _prd_amount(fields, row, p)
    balance = opening + period_amt
    if apply_group_sign:
        sign = account_group_sign(fields, row)
        opening *= sign
        period_amt *= sign
        balance *= sign
    return opening, period_amt, balance


def _fmt_amt(v: Decimal) -> str:
    return format_numeric_display(str(v), "amount")


def finance_field_value(
    fields: Sequence[str],
    row: Sequence[str],
    field_token: str,
    from_period: int,
    to_period: int,
) -> str:
    """將 REPORT.RPT_FIELD 單一 token 轉為顯示字串。"""
    tok = (field_token or "").strip().upper()
    if not tok:
        return ""
    opening, period_amt, balance = compute_finance_amounts(
        fields, row, from_period, to_period
    )
    if tok in ("OPEN_AMT", "OPEN_BAL", "OPENING", "OPEN"):
        return _fmt_amt(opening)
    if tok in ("PERIOD_AMT", "PERIOD", "CUR_AMT", "CURRENT"):
        return _fmt_amt(period_amt)
    if tok in ("YTD_AMT", "BALANCE", "CLOSE", "CLOSING", "結餘"):
        return _fmt_amt(balance)
    raw = _row_val(row, fields, tok)
    if raw:
        return raw
    # 別名
    if tok == "AC_KEY":
        return _row_val(row, fields, "AC_KEY") or _row_val(row, fields, "KEY")
    if tok == "AC_NAME":
        return _row_val(row, fields, "AC_NAME") or _row_val(row, fields, "NAME")
    return ""


def build_finance_table(
    fields: Sequence[str],
    rows: Sequence[Sequence[str]],
    field_names: Sequence[str],
    from_period: int,
    to_period: int,
) -> Tuple[List[List[str]], List[int]]:
    """
    依 RPT_FIELD 順序產生表格列；回傳 (body, right_align_col_indexes)。
    """
    names = [str(n or "").strip() for n in field_names if str(n or "").strip()]
    if not names:
        names = ["AC_KEY", "AC_NAME", "OPEN_AMT", "PERIOD_AMT", "YTD_AMT"]
    amount_tokens = {
        "OPEN_AMT",
        "OPEN_BAL",
        "OPENING",
        "OPEN",
        "PERIOD_AMT",
        "PERIOD",
        "CUR_AMT",
        "CURRENT",
        "YTD_AMT",
        "BALANCE",
        "CLOSE",
        "CLOSING",
    }
    align_right: List[int] = []
    for i, n in enumerate(names):
        if n.upper() in amount_tokens or n.upper().startswith("PRD_"):
            align_right.append(i)
    body: List[List[str]] = []
    for row in rows:
        line: List[str] = []
        for n in names:
            line.append(
                finance_field_value(fields, row, n, from_period, to_period)
            )
        body.append(line)
    return body, align_right


def finance_totals_row(
    fields: Sequence[str],
    rows: Sequence[Sequence[str]],
    field_names: Sequence[str],
    from_period: int,
    to_period: int,
) -> List[str]:
    """表尾合計：僅金額欄累加。"""
    names = [str(n or "").strip() for n in field_names if str(n or "").strip()]
    if not names:
        names = ["AC_KEY", "AC_NAME", "OPEN_AMT", "PERIOD_AMT", "YTD_AMT"]
    amount_tokens = {
        "OPEN_AMT",
        "PERIOD_AMT",
        "YTD_AMT",
        "OPEN_BAL",
        "OPENING",
        "OPEN",
        "PERIOD",
        "CUR_AMT",
        "CURRENT",
        "BALANCE",
        "CLOSE",
        "CLOSING",
    }
    sums: dict[str, Decimal] = {}
    for row in rows:
        opening, period_amt, balance = compute_finance_amounts(
            fields, row, from_period, to_period
        )
        sums["OPEN_AMT"] = sums.get("OPEN_AMT", Decimal("0")) + opening
        sums["PERIOD_AMT"] = sums.get("PERIOD_AMT", Decimal("0")) + period_amt
        sums["YTD_AMT"] = sums.get("YTD_AMT", Decimal("0")) + balance
    out: List[str] = []
    for i, n in enumerate(names):
        nu = n.upper()
        if i == 0:
            out.append("")
        elif nu in amount_tokens:
            key = nu
            if nu in ("OPEN_BAL", "OPENING", "OPEN"):
                key = "OPEN_AMT"
            elif nu in ("PERIOD", "CUR_AMT", "CURRENT"):
                key = "PERIOD_AMT"
            elif nu in ("BALANCE", "CLOSE", "CLOSING"):
                key = "YTD_AMT"
            out.append(_fmt_amt(sums.get(key, Decimal("0"))))
        else:
            out.append("")
    if out and not str(out[0]).strip():
        out[0] = "合計"
    return out


def _has_table(backend: DbBackendBase, table: str) -> bool:
    try:
        cols = backend.list_columns(table)
        return bool(cols)
    except Exception:
        return False


def _yn(raw: str) -> bool:
    s = str(raw or "").strip().upper()
    return s in ("Y", "YES", "1", "T", "TRUE")


def _ac_no_sort_key(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    # AC_KEY 形如 400000-00 → 取賬號前段
    if "-" in s:
        s = s.split("-", 1)[0].strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    if digits:
        return digits.zfill(12)
    return s.upper().zfill(12)


def _ac_no_in_range(ac_no: str, from_no: str, to_no: str) -> bool:
    key = _ac_no_sort_key(ac_no)
    if not key:
        return False
    lo = _ac_no_sort_key(from_no)
    hi = _ac_no_sort_key(to_no)
    if lo and key < lo:
        return False
    if hi and key > hi:
        return False
    return True


def _structure_seq_key(raw: str) -> float:
    try:
        return float(str(raw or "0").strip() or "0")
    except (TypeError, ValueError):
        return 0.0


def load_finance_structure_rows(
    backend: DbBackendBase, table_name: str
) -> Tuple[List[str], List[Sequence[str]]]:
    """依 SEQ_NO 讀取 PL_RPT / BS_RPT 架構列。"""
    t = (table_name or "").strip().upper()
    if not t or not _has_table(backend, t):
        return [], []
    sql = f"SELECT * FROM {t}"
    sel, rows = backend.fetch_rows_sql(sql, limit=2000)
    if not rows:
        sel, rows = backend.fetch_rows_sql(f"SELECT * FROM [{t}]", limit=2000)
    fields = list(sel) if sel else backend.list_columns(t)
    if not rows:
        return fields, []
    indexed = list(enumerate(rows))
    indexed.sort(
        key=lambda it: (
            _structure_seq_key(_row_val(it[1], fields, "SEQ_NO")),
            it[0],
        )
    )
    return fields, [r for _, r in indexed]


def _account_is_detail(fields: Sequence[str], row: Sequence[str]) -> bool:
    ac_type = str(_row_val(row, fields, "AC_TYPE") or "").strip().upper()
    if not ac_type:
        return True
    return ac_type == "DETAIL"


def _account_key(fields: Sequence[str], row: Sequence[str]) -> str:
    return (
        _row_val(row, fields, "AC_KEY")
        or _row_val(row, fields, "AC_NO")
        or _row_val(row, fields, "KEY")
        or ""
    ).strip()


def _account_no(fields: Sequence[str], row: Sequence[str]) -> str:
    return (
        _row_val(row, fields, "AC_NO")
        or _row_val(row, fields, "AC_KEY")
        or ""
    ).strip()


def _filter_accounts_for_range(
    fields: Sequence[str],
    rows: Sequence[Sequence[str]],
    from_no: str,
    to_no: str,
    *,
    detail_only: bool = True,
) -> List[Sequence[str]]:
    out: List[Sequence[str]] = []
    for row in rows:
        ac_no = _account_no(fields, row)
        if not _ac_no_in_range(ac_no, from_no, to_no):
            continue
        if detail_only and not _account_is_detail(fields, row):
            continue
        out.append(row)
    if detail_only and not out:
        # 區間內無 DETAIL 時改列所有賬戶，避免整段空白
        for row in rows:
            ac_no = _account_no(fields, row)
            if _ac_no_in_range(ac_no, from_no, to_no):
                out.append(row)
    out.sort(key=lambda r: _ac_no_sort_key(_account_no(fields, r)))
    return out


def _sum_finance_amounts(
    fields: Sequence[str],
    rows: Sequence[Sequence[str]],
    from_period: int,
    to_period: int,
) -> Tuple[Decimal, Decimal, Decimal]:
    """合計已含 AC_GROUP 正負。"""
    o = p = b = Decimal("0")
    for row in rows:
        opening, period_amt, balance = compute_finance_amounts(
            fields, row, from_period, to_period
        )
        o += opening
        p += period_amt
        b += balance
    return o, p, b


def _blank_row(n_cols: int) -> List[str]:
    return [""] * max(1, n_cols)


def _label_amount_row(
    n_cols: int,
    label: str,
    opening: Decimal,
    period_amt: Decimal,
    balance: Decimal,
    field_names: Sequence[str],
) -> List[str]:
    """依 RPT_FIELD 欄位位置填入標題與三個金額欄。標題優先放在賬戶名稱欄。"""
    names = [str(n or "").strip() for n in field_names if str(n or "").strip()]
    if not names:
        names = ["AC_KEY", "AC_NAME", "OPEN_AMT", "PERIOD_AMT", "YTD_AMT"]
    out = [""] * len(names)
    amount_map = {
        "OPEN_AMT": _fmt_amt(opening),
        "OPEN_BAL": _fmt_amt(opening),
        "OPENING": _fmt_amt(opening),
        "OPEN": _fmt_amt(opening),
        "PERIOD_AMT": _fmt_amt(period_amt),
        "PERIOD": _fmt_amt(period_amt),
        "CUR_AMT": _fmt_amt(period_amt),
        "CURRENT": _fmt_amt(period_amt),
        "YTD_AMT": _fmt_amt(balance),
        "BALANCE": _fmt_amt(balance),
        "CLOSE": _fmt_amt(balance),
        "CLOSING": _fmt_amt(balance),
    }
    for i, n in enumerate(names):
        nu = n.upper()
        if nu in amount_map:
            out[i] = amount_map[nu]

    # 長標題放 AC_NAME，避免撐開賬戶編號欄寬
    label_i = next(
        (i for i, n in enumerate(names) if n.upper() in ("AC_NAME", "NAME", "DESC")),
        None,
    )
    if label_i is None:
        label_i = next(
            (i for i, n in enumerate(names) if n.upper() not in amount_map),
            0,
        )
    if 0 <= label_i < len(out):
        out[label_i] = label
    while len(out) < n_cols:
        out.append("")
    return out[:n_cols]


def build_structured_finance_table(
    account_fields: Sequence[str],
    account_rows: Sequence[Sequence[str]],
    structure_fields: Sequence[str],
    structure_rows: Sequence[Sequence[str]],
    field_names: Sequence[str],
    from_period: int,
    to_period: int,
    *,
    lang: str = "CHN",
) -> Tuple[List[Tuple[str, List[str]]], List[int], List[str]]:
    """
    依 PL_RPT / BS_RPT 架構產生報表列。
    回傳 (styled_rows, align_right, grand_totals)。
    styled_rows 每項為 (kind, cells)，kind:
      group | detail | subtotal | summary | all_total
    """
    names = [str(n or "").strip() for n in field_names if str(n or "").strip()]
    if not names:
        names = ["AC_KEY", "AC_NAME", "OPEN_AMT", "PERIOD_AMT", "YTD_AMT"]
    n_cols = len(names)
    amount_tokens = {
        "OPEN_AMT",
        "OPEN_BAL",
        "OPENING",
        "OPEN",
        "PERIOD_AMT",
        "PERIOD",
        "CUR_AMT",
        "CURRENT",
        "YTD_AMT",
        "BALANCE",
        "CLOSE",
        "CLOSING",
    }
    align_right: List[int] = [
        i
        for i, n in enumerate(names)
        if n.upper() in amount_tokens or n.upper().startswith("PRD_")
    ]

    styled: List[Tuple[str, List[str]]] = []
    unique_for_grand: Dict[str, Sequence[str]] = {}
    is_chn = str(lang or "").strip().upper() in ("CHN", "ZH", "ZH-TW", "ZH_CN", "C")

    def _group_title(srow: Sequence[str]) -> str:
        if is_chn:
            title = _row_val(srow, structure_fields, "CHN_DESC").strip()
            if title:
                return title
        title = _row_val(srow, structure_fields, "DESC").strip()
        if title:
            return title
        return _row_val(srow, structure_fields, "CHN_DESC").strip()

    def _detail_line(row: Sequence[str]) -> List[str]:
        opening, period_amt, balance = compute_finance_amounts(
            account_fields, row, from_period, to_period
        )
        line: List[str] = []
        for n in names:
            nu = n.upper()
            if nu in ("OPEN_AMT", "OPEN_BAL", "OPENING", "OPEN"):
                line.append(_fmt_amt(opening))
            elif nu in ("PERIOD_AMT", "PERIOD", "CUR_AMT", "CURRENT"):
                line.append(_fmt_amt(period_amt))
            elif nu in ("YTD_AMT", "BALANCE", "CLOSE", "CLOSING"):
                line.append(_fmt_amt(balance))
            elif nu == "AC_KEY":
                line.append(_account_key(account_fields, row))
            elif nu == "AC_NAME":
                line.append(
                    _row_val(row, account_fields, "AC_NAME")
                    or _row_val(row, account_fields, "NAME")
                )
            else:
                line.append(_row_val(row, account_fields, n))
        return line

    for srow in structure_rows:
        title = _group_title(srow)
        from_no = _row_val(srow, structure_fields, "FROM").strip()
        to_no = _row_val(srow, structure_fields, "TO").strip()
        want_sub = _yn(_row_val(srow, structure_fields, "SUBTOTAL"))
        want_summary = _yn(_row_val(srow, structure_fields, "SUMMARY"))
        want_all = _yn(_row_val(srow, structure_fields, "ALL_TOTAL"))

        # 僅合計列（無賬戶區間）
        if want_all and not from_no and not to_no:
            g_rows = list(unique_for_grand.values())
            o, p, b = _sum_finance_amounts(
                account_fields, g_rows, from_period, to_period
            )
            styled.append(
                (
                    "all_total",
                    _label_amount_row(
                        n_cols,
                        title or ("合計" if is_chn else "Total"),
                        o,
                        p,
                        b,
                        names,
                    ),
                )
            )
            continue

        range_rows = _filter_accounts_for_range(
            account_fields, account_rows, from_no, to_no, detail_only=True
        )
        for r in range_rows:
            k = _account_key(account_fields, r)
            if k and k not in unique_for_grand:
                unique_for_grand[k] = r

        # SUMMARY：只顯示區間合計一列（不展開明細）
        if want_summary and not want_sub:
            o, p, b = _sum_finance_amounts(
                account_fields, range_rows, from_period, to_period
            )
            styled.append(
                (
                    "summary",
                    _label_amount_row(
                        n_cols,
                        title or ("小計" if is_chn else "Subtotal"),
                        o,
                        p,
                        b,
                        names,
                    ),
                )
            )
            continue

        if title:
            hdr = _blank_row(n_cols)
            name_i = next(
                (
                    i
                    for i, n in enumerate(names)
                    if n.upper() in ("AC_NAME", "NAME", "DESC")
                ),
                0,
            )
            hdr[name_i] = title
            styled.append(("group", hdr))

        for row in range_rows:
            styled.append(("detail", _detail_line(row)))

        if want_sub:
            o, p, b = _sum_finance_amounts(
                account_fields, range_rows, from_period, to_period
            )
            sub_label = "小計" if is_chn else "Subtotal"
            if title:
                sub_label = f"{title.strip()} {sub_label}"
            styled.append(
                ("subtotal", _label_amount_row(n_cols, sub_label, o, p, b, names))
            )

    g_rows = list(unique_for_grand.values())
    go, gp, gb = _sum_finance_amounts(
        account_fields, g_rows, from_period, to_period
    )
    totals = _label_amount_row(
        n_cols, "合計" if is_chn else "Total", go, gp, gb, names
    )
    return styled, align_right, totals
