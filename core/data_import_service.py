"""DATAIMPORT 作業：由 TRANSFER 暫存庫匯入至公司正式資料表。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from core.db_backend import DbBackendBase

DATA_IMPORT_PROC = "DATAIMPORT"
# 選單常見代號別名（PROGRAM.DO_PROC）
DATA_IMPORT_PROC_ALIASES = frozenset({"DATAIMPORT", "DO_DATAIMPORT"})

IMPORT_KINDS: Tuple[str, ...] = ("PURCHASE", "INVOICE", "STOCK")

# (TRANSFER 來源表, 公司庫目標表)
IMPORT_MAPPINGS: Dict[str, Tuple[Tuple[str, str], ...]] = {
    "PURCHASE": (
        ("PUR_HEADER", "PURCHASE"),
        ("PUR_ITEM", "PURSTK"),
    ),
    "INVOICE": (
        ("INV_HEADER", "INVOICE"),
        ("INV_ITEM", "INVSTK"),
    ),
    "STOCK": (
        ("STK", "STOCK"),
    ),
}

# 寫入正式表時不直接複製來源的 POSTED（來源表示「已匯入」；目標表示公司過帳狀態）
_SKIP_COPY_COLS = frozenset({"POSTED"})

from core.row_insert_defaults import (
    INSERT_BIT_DEFAULT_ZERO as _BIT_DEFAULT_ZERO,
    apply_insert_bit_defaults as _ensure_bit_defaults,
)

# 主檔匯入預設：貨幣 HKD、匯率 1、其餘數字欄空白為 0
DEFAULT_TX_CURR = "HKD"
DEFAULT_TX_RATE = "1"
_HEADER_CURR_COLS = frozenset({"TX_CURR", "CURRENCY"})
_HEADER_RATE_COLS = frozenset({"TX_RATE", "FIX_RATE"})
_HEADER_NUMERIC_ZERO_COLS = frozenset(
    {
        "TX_AMT",
        "DISC_%",
        "DISC_SHARE",
        "DISC_AMT",
        "NET_AMT",
        "PAID_AMT",
        "CREDIT_DAY",
        "PRN_COUNT",
    }
)

ProgressCallback = Optional[Callable[[str], None]]


def is_data_import_program(do_proc: str) -> bool:
    key = (do_proc or "").strip().upper()
    if not key:
        return False
    if key in DATA_IMPORT_PROC_ALIASES:
        return True
    # 結尾為 DATAIMPORT 亦視為匯入作業（如 XX_DATAIMPORT）
    return key.endswith("DATAIMPORT")


def canonical_data_import_proc(do_proc: str = "") -> str:
    """正規化為 DATAIMPORT（供訊息／分派）。"""
    return DATA_IMPORT_PROC if is_data_import_program(do_proc) else (do_proc or "").strip().upper()


def list_import_kind_options() -> List[Dict[str, str]]:
    """回傳可選匯入類型與說明（供 Web／API）。"""
    labels = {
        "PURCHASE": "採購 PURCHASE",
        "INVOICE": "發票 INVOICE",
        "STOCK": "庫存 STOCK",
    }
    out: List[Dict[str, str]] = []
    for kind in IMPORT_KINDS:
        pairs = IMPORT_MAPPINGS.get(kind, ())
        detail = "; ".join(f"TRANSFER.{s}→{d}" for s, d in pairs)
        out.append(
            {
                "kind": kind,
                "label": labels.get(kind, kind),
                "detail": detail,
            }
        )
    return out


def list_import_source_folders(
    base_dir: str, path: str = ""
) -> Tuple[Dict[str, object], Optional[str]]:
    """
    列出可選來源資料夾（供 Web 瀏覽）。
    回傳 ({path, parent, folders, has_transfer, transfer_path}, error)。
    """
    import os

    from core.db_factory import normalize_transfer_folder, resolve_transfer_db_path

    root = os.path.abspath(base_dir or ".")
    cur, _folder_warn = normalize_transfer_folder(base_dir, path or "")
    if not os.path.isdir(cur):
        return {}, f"資料夾不存在：{cur}"
    folders: List[str] = []
    try:
        for name in sorted(os.listdir(cur), key=lambda s: s.upper()):
            full = os.path.join(cur, name)
            if os.path.isdir(full) and not name.startswith("."):
                folders.append(full)
    except OSError as e:
        return {}, f"無法讀取資料夾：{cur}（{e}）"

    transfer_path = resolve_transfer_db_path(root, folder=cur)
    has_transfer = os.path.isfile(transfer_path)
    parent = os.path.dirname(cur)
    if parent == cur:
        parent = ""
    return {
        "path": cur,
        "parent": parent,
        "folders": folders,
        "has_transfer": has_transfer,
        "transfer_path": transfer_path if has_transfer else "",
    }, None


@dataclass
class TableImportResult:
    source_table: str
    dest_table: str
    rows_imported: int = 0
    error: str = ""


@dataclass
class DataImportResult:
    kind: str
    tables: List[TableImportResult] = field(default_factory=list)
    ok: bool = False
    message: str = ""


def _find_col(cols: Sequence[str], name: str) -> Optional[str]:
    target = (name or "").strip().upper()
    for c in cols:
        if (c or "").strip().upper() == target:
            return c
    return None


def _find_col_index(fields: Sequence[str], name: str) -> int:
    target = (name or "").strip().upper()
    for i, f in enumerate(fields):
        if (f or "").strip().upper() == target:
            return i
    return -1


def _is_unposted(value: object) -> bool:
    """POSTED=FALSE／空白／0 視為未處理。"""
    if value is None:
        return True
    s = str(value).strip()
    if not s:
        return True
    low = s.lower()
    if low in ("0", "false", "no", "n", "f"):
        return True
    if low in ("1", "true", "yes", "y", "t", "-1"):
        return False
    try:
        return float(s) == 0
    except (TypeError, ValueError):
        return False


def _posted_true_value(backend: DbBackendBase, table: str, posted_col: str) -> str:
    """依資料表既有 POSTED 真值格式寫入（Access 常為 -1）。"""
    for literal in ("-1", "1", "True", "true", "YES", "Yes"):
        rows = backend.fetch_rows_where(table, posted_col, literal, limit=1)
        if rows and not backend.last_error:
            return literal
    return "1"


def _header_display_label(
    key: str,
    tx_type: str,
    row: Sequence[str],
    fields: Sequence[str],
) -> str:
    parts = [p for p in (tx_type, key) if p]
    for date_name in ("TX_DATE", "DATE", "INV_DATE", "PUR_DATE"):
        idx = _find_col_index(fields, date_name)
        if idx >= 0 and idx < len(row):
            dv = str(row[idx] or "").strip()
            if dv:
                parts.append(dv)
                break
    return " / ".join(parts) if parts else key


def _extract_int_tail(value: str) -> int:
    s = (value or "").strip()
    if not s:
        return 0
    digits: List[str] = []
    i = len(s) - 1
    while i >= 0 and s[i].isdigit():
        digits.append(s[i])
        i -= 1
    if not digits:
        return 0
    return int("".join(reversed(digits)))


# 正式表 TX_NO：前置補零的 8 位數字文字（例 00000001）
# TX_KEY = TX_TYPE + TX_NO（例 GS-00000001）
# TX_TYPE 空白時預設 GS-
TX_NO_DIGIT_WIDTH = 8
DEFAULT_TX_TYPE = "GS-"


def _format_tx_no(n: int) -> str:
    """將編號格式化為固定 8 位前置補零數字文字。"""
    return str(max(0, int(n))).zfill(TX_NO_DIGIT_WIDTH)


def _build_tx_key(tx_type: str, tx_no: str) -> str:
    """TX_KEY = TX_TYPE + TX_NO（例 GS-00000001）。"""
    return f"{(tx_type or '').strip()}{(tx_no or '').strip()}"


def _resolve_import_tx_type(source_tx_type: str) -> str:
    """來源 TX_TYPE；空白則預設 GS-。"""
    t = (source_tx_type or "").strip()
    return t if t else DEFAULT_TX_TYPE


def _emit(progress: ProgressCallback, msg: str) -> None:
    if progress:
        try:
            progress(msg)
        except Exception:
            pass


def _next_tx_key(
    dst_backend: DbBackendBase, table: str, tx_type: str
) -> Tuple[str, str, Optional[str]]:
    """
    依目標表同 TX_TYPE 組別，取 TX_NO 最後編號 +1。
    TX_NO 為前置補零的 8 位數字文字；
    TX_KEY = TX_TYPE + TX_NO（例 GS-00000001）。
    若 TX_KEY 已存在則再 +1，直至唯一。

    回傳 (tx_key, tx_no, error)。
    """
    cols = dst_backend.list_columns(table)
    if not cols:
        return "", "", f"找不到目標表「{table}」或無法讀取欄位。"
    tx_type_col = _find_col(cols, "TX_TYPE")
    tx_no_col = _find_col(cols, "TX_NO")
    tx_key_col = _find_col(cols, "TX_KEY")
    if not tx_type_col or not tx_no_col:
        return "", "", f"目標表「{table}」缺少 TX_TYPE/TX_NO 欄位。"

    type_val = _resolve_import_tx_type(tx_type)

    rows = dst_backend.fetch_rows_where(
        table,
        tx_type_col,
        type_val,
        limit=200000,
        column_order=[tx_no_col],
    )
    if dst_backend.last_error:
        return "", "", dst_backend.last_error
    max_no = 0
    for r in rows:
        val = (r[0] if r else "") or ""
        sval = str(val).strip()
        max_no = max(max_no, _extract_int_tail(sval))

    next_no = max_no + 1
    while True:
        tx_no = _format_tx_no(next_no)
        tx_key = _build_tx_key(type_val, tx_no)
        if not tx_key_col:
            return tx_key, tx_no, None
        exists_rows = dst_backend.fetch_rows_where(table, tx_key_col, tx_key, limit=1)
        if dst_backend.last_error:
            return "", "", dst_backend.last_error
        if not exists_rows:
            return tx_key, tx_no, None
        next_no += 1


def _lookup_custvend_key_by_name(
    company_backend: DbBackendBase,
    party_name: str,
) -> str:
    """
    在 CUSTVEND 以名稱找出對應 CUST_KEY。
    比對欄位優先：CUST_NAME／VEND_NAME／CHN_NAME／NAME／COMPANY／PARTY_NAME。
    """
    name = (party_name or "").strip()
    if not name:
        return ""
    cols = company_backend.list_columns("CUSTVEND")
    if not cols:
        return ""
    key_col = _find_col(cols, "CUST_KEY")
    if not key_col:
        return ""
    name_cols: List[str] = []
    for cand in (
        "CUST_NAME",
        "VEND_NAME",
        "CHN_NAME",
        "NAME",
        "COMPANY",
        "PARTY_NAME",
    ):
        hit = _find_col(cols, cand)
        if hit and hit not in name_cols:
            name_cols.append(hit)
    if not name_cols:
        return ""

    fetch_cols = [key_col] + name_cols
    rows = company_backend.fetch_rows(
        "CUSTVEND", "", False, limit=100000, column_order=fetch_cols
    )
    want = name.upper()
    for r in rows:
        if not r:
            continue
        for i in range(1, len(fetch_cols)):
            if i >= len(r):
                continue
            if str(r[i] or "").strip().upper() == want:
                return str(r[0] or "").strip()
    return ""


def _set_dest_field(
    dst_cols: Sequence[str],
    fields: List[str],
    values: List[str],
    logical: str,
    value: str,
) -> Tuple[List[str], List[str]]:
    """
    在目標欄位清單中寫入／覆寫 logical（不分大小寫）。
    若目標表有該欄但 fields 尚未包含，則補上。
    """
    out_fields = list(fields)
    out_values = [str(v) if v is not None else "" for v in values]
    dst_map = {(c or "").strip().upper(): c for c in dst_cols if (c or "").strip()}
    physical = dst_map.get((logical or "").strip().upper())
    if not physical:
        return out_fields, out_values
    idx = _find_col_index(out_fields, physical)
    if idx < 0:
        out_fields.append(physical)
        out_values.append("" if value is None else str(value))
    else:
        out_values[idx] = "" if value is None else str(value)
    return out_fields, out_values


def _source_cell(
    fields: Sequence[str], row: Sequence[str], *logicals: str
) -> str:
    """從來源列依邏輯欄名取值（第一個非空白）。"""
    for name in logicals:
        idx = _find_col_index(list(fields), name)
        if idx >= 0 and idx < len(row):
            v = str(row[idx] or "").strip()
            if v:
                return v
    return ""


def _apply_party_key_from_custvend(
    company_backend: DbBackendBase,
    kind: str,
    fields: List[str],
    values: List[str],
    *,
    dst_cols: Optional[Sequence[str]] = None,
    party_name_hint: str = "",
    progress: ProgressCallback = None,
) -> Tuple[List[str], List[str]]:
    """
    若供應商／顧客編號空白，以名稱在 CUSTVEND 找出 CUST_KEY 回填：
    - PURCHASE → 填 VEND_KEY
    - INVOICE → 填 CUST_KEY

    party_name_hint：來源列供應商／顧客名稱（即使未對應到目標表欄位亦可）。
    """
    out_fields = list(fields)
    out_values = [str(v) if v is not None else "" for v in values]
    is_purchase = (kind or "").strip().upper() == "PURCHASE"
    key_logical = "VEND_KEY" if is_purchase else "CUST_KEY"
    name_logicals = (
        ("VEND_NAME", "CUST_NAME", "CHN_NAME", "NAME", "COMPANY")
        if is_purchase
        else ("CUST_NAME", "CHN_NAME", "NAME", "COMPANY", "VEND_NAME")
    )

    key_idx = _find_col_index(out_fields, key_logical)
    key_val = (
        str(out_values[key_idx]).strip()
        if key_idx >= 0 and key_idx < len(out_values)
        else ""
    )
    if key_val:
        return out_fields, out_values

    party_name = (party_name_hint or "").strip()
    if not party_name:
        for nm in name_logicals:
            ni = _find_col_index(out_fields, nm)
            if ni >= 0 and ni < len(out_values):
                party_name = str(out_values[ni] or "").strip()
                if party_name:
                    break
    if not party_name:
        return out_fields, out_values

    found = _lookup_custvend_key_by_name(company_backend, party_name)
    if not found:
        _emit(
            progress,
            f"警告：找不到名稱「{party_name}」對應的 CUSTVEND.CUST_KEY，"
            f"{key_logical} 維持空白。",
        )
        return out_fields, out_values

    cols_for_set = list(dst_cols) if dst_cols else list(out_fields)
    if key_logical.upper() not in {(c or "").strip().upper() for c in cols_for_set}:
        cols_for_set.append(key_logical)
    out_fields, out_values = _set_dest_field(
        cols_for_set, out_fields, out_values, key_logical, found
    )
    _emit(
        progress,
        f"已依名稱「{party_name}」帶入 {key_logical}={found}（CUSTVEND）。",
    )
    return out_fields, out_values


def _common_column_pairs(
    src_cols: Sequence[str],
    dst_cols: Sequence[str],
    *,
    skip: Optional[Set[str]] = None,
) -> List[Tuple[str, str]]:
    skip_u = {(s or "").strip().upper() for s in (skip or set())}
    dst_map = {(c or "").strip().upper(): c for c in dst_cols if (c or "").strip()}
    pairs: List[Tuple[str, str]] = []
    for sc in src_cols:
        su = (sc or "").strip().upper()
        if not su or su in skip_u:
            continue
        if su in dst_map:
            pairs.append((sc, dst_map[su]))
    return pairs


def _is_header_numeric_name(name: str) -> bool:
    """判斷主檔欄位名是否為應預設 0 的數字欄（不含貨幣／匯率）。"""
    u = (name or "").strip().upper()
    if not u or u in _HEADER_CURR_COLS or u in _HEADER_RATE_COLS:
        return False
    if u in _BIT_DEFAULT_ZERO:
        return False
    if u in _HEADER_NUMERIC_ZERO_COLS:
        return True
    if u.endswith("%"):
        return True
    for token in (
        "_AMT",
        "_QTY",
        "_PRICE",
        "_COST",
        "_SHARE",
        "_COUNT",
        "_DAY",
        "_TOTAL",
        "_TAX",
    ):
        if u.endswith(token) or token in u:
            return True
    return False


def _is_grid_numeric_column(name: str) -> bool:
    """GRID 對齊用：數字／匯率欄靠右，其餘靠左。"""
    u = (name or "").strip().upper()
    if not u:
        return False
    if u in _HEADER_RATE_COLS:
        return True
    return _is_header_numeric_name(name)


def _ensure_doc_header_defaults(
    dst_cols: Sequence[str],
    fields: Sequence[str],
    values: Sequence[str],
) -> Tuple[List[str], List[str]]:
    """
    PURCHASE／INVOICE 主檔匯入預設：
    貨幣強制 HKD、匯率強制 1；其餘數字欄空白則填 0；
    購貨／發票金額（優先 NET_AMT，否則 TX_AMT−DISC_AMT）寫入 TX_AMT＝NET_AMT；
    PAID_AMT 固定為 0。
    """
    out_fields = list(fields)
    out_values = [str(v) if v is not None else "" for v in values]
    dst_map = {(c or "").strip().upper(): c for c in dst_cols if (c or "").strip()}

    def _set_value(logical: str, default: str, *, force: bool) -> None:
        physical = dst_map.get(logical)
        if not physical:
            return
        idx = _find_col_index(out_fields, physical)
        if idx < 0:
            out_fields.append(physical)
            out_values.append(default)
            return
        if force or not (out_values[idx] or "").strip():
            out_values[idx] = default

    def _val(logical: str) -> str:
        idx = _find_col_index(out_fields, logical)
        if idx < 0 or idx >= len(out_values):
            return ""
        return str(out_values[idx] or "").strip()

    for logical in sorted(_HEADER_CURR_COLS):
        _set_value(logical, DEFAULT_TX_CURR, force=True)
    for logical in sorted(_HEADER_RATE_COLS):
        _set_value(logical, DEFAULT_TX_RATE, force=True)
    for logical in sorted(dst_map.keys()):
        if _is_header_numeric_name(logical):
            _set_value(logical, "0", force=False)

    # TX_AMT = NET_AMT = 購貨／發票金額；PAID_AMT = 0
    from decimal import Decimal, InvalidOperation

    def _d(raw: str) -> Decimal:
        try:
            return Decimal(str(raw or "0").strip().replace(",", ""))
        except (InvalidOperation, ValueError):
            return Decimal("0")

    doc_amt = _d(_val("NET_AMT"))
    if doc_amt == 0:
        doc_amt = _d(_val("TX_AMT")) - _d(_val("DISC_AMT"))
    amt_s = format(doc_amt.quantize(Decimal("0.01")), "f")
    _set_value("TX_AMT", amt_s, force=True)
    _set_value("NET_AMT", amt_s, force=True)
    _set_value("PAID_AMT", "0", force=True)
    return out_fields, out_values


def _fetch_source_rows(
    backend: DbBackendBase,
    source_table: str,
    src_fields: List[str],
    *,
    limit: int,
) -> Tuple[List[List[str]], Optional[str]]:
    if not src_fields:
        return [], "無來源欄位。"
    src_cols = backend.list_columns(source_table)
    if not src_cols:
        return [], f"找不到來源表「{source_table}」或無法讀取欄位。"
    missing = [
        sf
        for sf in src_fields
        if not any(
            (c or "").strip().upper() == (sf or "").strip().upper() for c in src_cols
        )
    ]
    if missing:
        return [], f"來源表「{source_table}」缺少欄位「{missing[0]}」。"
    # Access ODBC metadata 欄位順序可能與 SELECT * 不同，必須依欄位名對齊
    rows = backend.fetch_rows(
        source_table, "", False, limit=limit, column_order=list(src_fields)
    )
    if not rows and backend.last_error:
        return [], backend.last_error
    return rows, None


def copy_table_rows(
    src_backend: DbBackendBase,
    dst_backend: DbBackendBase,
    source_table: str,
    dest_table: str,
    *,
    limit: int = 100_000,
    progress: ProgressCallback = None,
) -> Tuple[int, Optional[str]]:
    """將 TRANSFER 來源表列依共同欄位名稱附加寫入公司庫目標表。"""
    src_cols = src_backend.list_columns(source_table)
    dst_cols = dst_backend.list_columns(dest_table)
    if not src_cols:
        return 0, f"TRANSFER 找不到來源表「{source_table}」或無法讀取欄位。"
    if not dst_cols:
        return 0, f"公司庫找不到目標表「{dest_table}」或無法讀取欄位。"
    pairs = _common_column_pairs(src_cols, dst_cols, skip=_SKIP_COPY_COLS)
    if not pairs:
        return 0, f"「{source_table}」與「{dest_table}」無共同欄位可對應。"
    src_fields = [p[0] for p in pairs]
    dst_fields = [p[1] for p in pairs]
    _emit(progress, f"讀取 TRANSFER.{source_table}…")
    rows, err = _fetch_source_rows(src_backend, source_table, src_fields, limit=limit)
    if err:
        return 0, err
    if not rows:
        return 0, None
    count = 0
    total = len(rows)
    for row in rows:
        field_list, value_list = _ensure_bit_defaults(dst_cols, dst_fields, row)
        if not dst_backend.insert_one(dest_table, field_list, value_list):
            detail = (dst_backend.last_error or "寫入失敗").strip()
            return count, f"匯入至「{dest_table}」失敗（已寫入 {count} 筆）：{detail}"
        count += 1
        if count == 1 or count == total or count % 50 == 0:
            _emit(progress, f"TRANSFER.{source_table}→{dest_table}：{count}/{total} 筆")
    return count, None


def list_pending_import_rows(
    transfer_backend: DbBackendBase, kind: str
) -> Tuple[List[Dict[str, str]], Optional[str]]:
    """
    列出 TRANSFER 庫 PURCHASE／INVOICE 未處理主檔（POSTED=FALSE）。
    回傳 [{key, tx_type, label}, ...]。
    """
    grid, err = list_pending_import_grid(transfer_backend, kind)
    if err:
        return [], err
    rows = grid.get("rows") if isinstance(grid, dict) else None
    if not isinstance(rows, list):
        return [], None
    out: List[Dict[str, str]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        out.append(
            {
                "key": str(r.get("key") or ""),
                "tx_type": str(r.get("tx_type") or ""),
                "label": str(r.get("label") or r.get("key") or ""),
            }
        )
    return out, None


def list_pending_import_grid(
    transfer_backend: DbBackendBase, kind: str
) -> Tuple[Dict[str, object], Optional[str]]:
    """
    以 GRID 資料列出 TRANSFER 未處理主檔（POSTED=FALSE）。
    回傳 {
      source_table, columns:[{name,title,numeric}],
      rows:[{key, tx_type, label, cells:[...]}]
    }。
    """
    import os

    # 讀取前先 stat，降低 Samba／NFS 讀到舊檔內容的機率
    dbp = getattr(transfer_backend, "db_path", "") or ""
    if dbp:
        try:
            os.stat(dbp)
        except OSError:
            pass

    key = (kind or "").strip().upper()
    if key == "PURCHASE":
        src_header = "PUR_HEADER"
    elif key == "INVOICE":
        src_header = "INV_HEADER"
    else:
        return {
            "source_table": "",
            "columns": [],
            "rows": [],
        }, None

    sh_cols = transfer_backend.list_columns(src_header)
    if not sh_cols:
        return {}, f"TRANSFER 找不到主檔資料表：{src_header}"
    posted_col = _find_col(sh_cols, "POSTED")
    if not posted_col:
        return {}, f"TRANSFER.{src_header} 缺少 POSTED 欄位。"
    key_col = _find_col(sh_cols, "TX_KEY") or _find_col(sh_cols, "TX_NO")
    tx_type_col = _find_col(sh_cols, "TX_TYPE")
    if not key_col or not tx_type_col:
        return {}, f"TRANSFER.{src_header} 缺少 TX_KEY/TX_NO 或 TX_TYPE 欄位。"

    # GRID 顯示來源表全部欄位（與桌面／Web 表格對齊）
    src_fields = list(sh_cols)
    if posted_col not in src_fields:
        src_fields.append(posted_col)

    rows, err = _fetch_source_rows(transfer_backend, src_header, src_fields, limit=200000)
    if err:
        return {}, err

    key_idx = _find_col_index(src_fields, key_col)
    type_idx = _find_col_index(src_fields, tx_type_col)
    posted_idx = _find_col_index(src_fields, posted_col)
    columns = [
        {
            "name": c,
            "title": c,
            "numeric": _is_grid_numeric_column(c),
        }
        for c in src_fields
    ]
    out_rows: List[Dict[str, object]] = []
    seen: Set[str] = set()
    for row in rows:
        if not _is_unposted(row[posted_idx] if posted_idx >= 0 and posted_idx < len(row) else ""):
            continue
        row_key = str(row[key_idx] if key_idx >= 0 and key_idx < len(row) else "").strip()
        if not row_key or row_key in seen:
            continue
        seen.add(row_key)
        tx_type = _resolve_import_tx_type(
            str(row[type_idx] if type_idx >= 0 and type_idx < len(row) else "")
        )
        cells = [str(v) if v is not None else "" for v in row]
        # 補齊長度
        while len(cells) < len(src_fields):
            cells.append("")
        out_rows.append(
            {
                "key": row_key,
                "tx_type": tx_type,
                "label": _header_display_label(row_key, tx_type, row, src_fields),
                "cells": cells[: len(src_fields)],
            }
        )
    out_rows.sort(
        key=lambda x: (str(x.get("tx_type") or ""), str(x.get("key") or ""))
    )
    return {
        "source_table": src_header,
        "columns": columns,
        "rows": out_rows,
    }, None


def run_data_import(
    transfer_backend: DbBackendBase,
    company_backend: DbBackendBase,
    kind: str,
    selected_keys: Optional[Sequence[str]] = None,
    *,
    progress: ProgressCallback = None,
) -> DataImportResult:
    """
    自 TRANSFER 匯入至公司庫。
    PURCHASE／INVOICE 需 selected_keys；STOCK 匯入全部 STK。
    """
    key = (kind or "").strip().upper()
    mapping = IMPORT_MAPPINGS.get(key)
    if not mapping:
        return DataImportResult(
            kind=key,
            ok=False,
            message=f"不支援的匯入類型：{kind}",
        )
    if key in ("PURCHASE", "INVOICE"):
        keys = [str(k).strip() for k in (selected_keys or []) if str(k).strip()]
        if not keys:
            return DataImportResult(
                kind=key,
                ok=False,
                message="請選擇要匯入的未處理資料。",
            )
        return _run_doc_import(
            transfer_backend,
            company_backend,
            key,
            keys,
            progress=progress,
        )

    results: List[TableImportResult] = []
    total = 0
    _emit(progress, f"開始匯入 STOCK：TRANSFER.STK → STOCK…")
    for src, dst in mapping:
        n, err = copy_table_rows(
            transfer_backend,
            company_backend,
            src,
            dst,
            progress=progress,
        )
        tr = TableImportResult(source_table=src, dest_table=dst, rows_imported=n, error=err or "")
        results.append(tr)
        if err:
            return DataImportResult(
                kind=key,
                tables=results,
                ok=False,
                message=err,
            )
        total += n
    lines = [f"TRANSFER.{r.source_table}→{r.dest_table}: {r.rows_imported} 筆" for r in results]
    msg = (
        "匯入完成（TRANSFER → 公司庫）。\n" + "\n".join(lines)
        if lines
        else "匯入完成（無資料列）。"
    )
    _emit(progress, msg)
    return DataImportResult(kind=key, tables=results, ok=True, message=msg)


def _run_doc_import(
    transfer_backend: DbBackendBase,
    company_backend: DbBackendBase,
    kind: str,
    selected_keys: Sequence[str],
    *,
    progress: ProgressCallback = None,
) -> DataImportResult:
    if kind == "PURCHASE":
        src_header, dst_header = "PUR_HEADER", "PURCHASE"
        src_item, dst_item = "PUR_ITEM", "PURSTK"
    else:
        src_header, dst_header = "INV_HEADER", "INVOICE"
        src_item, dst_item = "INV_ITEM", "INVSTK"

    sh_cols = transfer_backend.list_columns(src_header)
    dh_cols = company_backend.list_columns(dst_header)
    si_cols = transfer_backend.list_columns(src_item)
    di_cols = company_backend.list_columns(dst_item)
    if not sh_cols or not dh_cols:
        return DataImportResult(
            kind=kind,
            ok=False,
            message=f"找不到主檔資料表：TRANSFER.{src_header}／公司庫.{dst_header}",
        )
    if not si_cols or not di_cols:
        return DataImportResult(
            kind=kind,
            ok=False,
            message=f"找不到明細資料表：TRANSFER.{src_item}／公司庫.{dst_item}",
        )

    posted_col = _find_col(sh_cols, "POSTED")
    if not posted_col:
        return DataImportResult(
            kind=kind, ok=False, message=f"TRANSFER.{src_header} 缺少 POSTED 欄位。"
        )
    header_key_col = _find_col(sh_cols, "TX_KEY") or _find_col(sh_cols, "TX_NO")
    if not header_key_col:
        return DataImportResult(
            kind=kind, ok=False, message=f"TRANSFER.{src_header} 缺少 TX_KEY/TX_NO 欄位。"
        )

    h_pairs = _common_column_pairs(sh_cols, dh_cols, skip=_SKIP_COPY_COLS)
    i_pairs = _common_column_pairs(si_cols, di_cols, skip=_SKIP_COPY_COLS)
    if not h_pairs:
        return DataImportResult(
            kind=kind,
            ok=False,
            message=f"「{src_header}」與「{dst_header}」無共同欄位可對應。",
        )
    if not i_pairs:
        return DataImportResult(
            kind=kind,
            ok=False,
            message=f"「{src_item}」與「{dst_item}」無共同欄位可對應。",
        )

    h_src_fields = [p[0] for p in h_pairs]
    h_dst_fields = [p[1] for p in h_pairs]
    i_src_fields = [p[0] for p in i_pairs]
    i_dst_fields = [p[1] for p in i_pairs]
    fetch_header_fields = list(h_src_fields)
    posted_fetch_idx = _find_col_index(fetch_header_fields, posted_col)
    if posted_fetch_idx < 0:
        fetch_header_fields.append(posted_col)
        posted_fetch_idx = len(fetch_header_fields) - 1
    # 來源供應商／顧客名稱：即使未對應到目標表，仍需讀取供 CUSTVEND 回填
    party_name_src_cols = (
        ("VEND_NAME", "CUST_NAME", "CHN_NAME", "NAME", "COMPANY")
        if (kind or "").strip().upper() == "PURCHASE"
        else ("CUST_NAME", "CHN_NAME", "NAME", "COMPANY", "VEND_NAME")
    )
    for pname in party_name_src_cols:
        hit = _find_col(sh_cols, pname)
        if hit and _find_col_index(fetch_header_fields, hit) < 0:
            fetch_header_fields.append(hit)
    # 來源 TX_TYPE：即使未列入共同欄位也要讀；無此欄則視為空白→預設 GS-
    src_tx_type_phys = _find_col(sh_cols, "TX_TYPE")
    if src_tx_type_phys and _find_col_index(fetch_header_fields, src_tx_type_phys) < 0:
        fetch_header_fields.append(src_tx_type_phys)

    _emit(progress, f"讀取 TRANSFER.{src_header}／{src_item}…")
    h_rows, h_err = _fetch_source_rows(
        transfer_backend, src_header, fetch_header_fields, limit=200000
    )
    if h_err:
        return DataImportResult(kind=kind, ok=False, message=h_err)
    i_rows, i_err = _fetch_source_rows(
        transfer_backend, src_item, i_src_fields, limit=200000
    )
    if i_err:
        return DataImportResult(kind=kind, ok=False, message=i_err)

    src_header_key_idx = _find_col_index(fetch_header_fields, header_key_col)
    src_header_type_idx = _find_col_index(fetch_header_fields, "TX_TYPE")
    if src_header_key_idx < 0:
        return DataImportResult(
            kind=kind,
            ok=False,
            message=f"TRANSFER.{src_header} 缺少 TX_KEY/TX_NO 欄位。",
        )

    src_item_key_idx = -1
    for name in ("TX_KEY", "TX_NO"):
        src_item_key_idx = _find_col_index(i_src_fields, name)
        if src_item_key_idx >= 0:
            break
    if src_item_key_idx < 0:
        return DataImportResult(
            kind=kind, ok=False, message=f"TRANSFER.{src_item} 缺少 TX_KEY/TX_NO 欄位。"
        )

    want_keys = {str(k).strip() for k in selected_keys if str(k).strip()}
    item_map: Dict[str, List[List[str]]] = {}
    for row in i_rows:
        old_key = (row[src_item_key_idx] if src_item_key_idx < len(row) else "") or ""
        k = str(old_key).strip()
        if not k:
            continue
        item_map.setdefault(k, []).append(row)

    posted_true = _posted_true_value(transfer_backend, src_header, posted_col)
    h_count = 0
    i_count = 0
    posted_count = 0
    detail_lines: List[str] = []
    todo = [r for r in h_rows if str(r[src_header_key_idx] if src_header_key_idx < len(r) else "").strip() in want_keys]
    total_todo = len(todo)

    for row in h_rows:
        old_key = str(row[src_header_key_idx] if src_header_key_idx < len(row) else "").strip()
        if old_key not in want_keys:
            continue
        if posted_fetch_idx >= 0 and not _is_unposted(
            row[posted_fetch_idx] if posted_fetch_idx < len(row) else ""
        ):
            continue
        if not old_key:
            continue
        raw_type = (
            str(row[src_header_type_idx] if 0 <= src_header_type_idx < len(row) else "").strip()
            if src_header_type_idx >= 0
            else ""
        )
        tx_type = _resolve_import_tx_type(raw_type)

        step = h_count + 1
        _emit(
            progress,
            f"處理 {step}/{max(total_todo, 1)}：{old_key}（TX_TYPE={tx_type}）產生 TX_KEY…",
        )
        new_key, new_tx_no, key_err = _next_tx_key(company_backend, dst_header, tx_type)
        if key_err:
            return DataImportResult(kind=kind, ok=False, message=key_err)

        h_values = []
        for sf in h_src_fields:
            idx = _find_col_index(fetch_header_fields, sf)
            h_values.append(str(row[idx]) if idx >= 0 and idx < len(row) else "")
        # 正式主檔：強制寫入 TX_KEY／TX_NO／TX_TYPE（即使非共同欄位）
        h_fields, h_vals = list(h_dst_fields), list(h_values)
        h_fields, h_vals = _set_dest_field(dh_cols, h_fields, h_vals, "TX_NO", new_tx_no)
        h_fields, h_vals = _set_dest_field(dh_cols, h_fields, h_vals, "TX_KEY", new_key)
        h_fields, h_vals = _set_dest_field(dh_cols, h_fields, h_vals, "TX_TYPE", tx_type)
        # 正式主檔：POSTED=0；貨幣 HKD、匯率 1；空白數字欄填 0；TX_AMT=NET_AMT=購貨／發票金額；PAID_AMT=0
        h_fields, h_vals = _ensure_bit_defaults(
            dh_cols,
            h_fields,
            h_vals,
            overrides={"POSTED": "0"},
        )
        h_fields, h_vals = _ensure_doc_header_defaults(dh_cols, h_fields, h_vals)
        party_hint = _source_cell(
            fetch_header_fields,
            row,
            *party_name_src_cols,
        )
        h_fields, h_vals = _apply_party_key_from_custvend(
            company_backend,
            kind,
            h_fields,
            h_vals,
            dst_cols=dh_cols,
            party_name_hint=party_hint,
            progress=progress,
        )
        if not company_backend.insert_one(dst_header, h_fields, h_vals):
            return DataImportResult(
                kind=kind,
                ok=False,
                message=f"寫入公司庫 {dst_header} 失敗：{company_backend.last_error or '未知錯誤'}",
            )
        h_count += 1

        item_n = 0
        for item_row in item_map.get(old_key, []):
            i_values = [str(v) for v in item_row]
            i_fields, i_vals = list(i_dst_fields), list(i_values)
            i_fields, i_vals = _set_dest_field(di_cols, i_fields, i_vals, "TX_NO", new_tx_no)
            i_fields, i_vals = _set_dest_field(di_cols, i_fields, i_vals, "TX_KEY", new_key)
            i_fields, i_vals = _set_dest_field(di_cols, i_fields, i_vals, "TX_TYPE", tx_type)
            i_fields, i_vals = _ensure_bit_defaults(di_cols, i_fields, i_vals)
            if not company_backend.insert_one(dst_item, i_fields, i_vals):
                return DataImportResult(
                    kind=kind,
                    ok=False,
                    message=f"寫入公司庫 {dst_item} 失敗：{company_backend.last_error or '未知錯誤'}",
                )
            i_count += 1
            item_n += 1

        if not transfer_backend.update_one(
            src_header,
            [posted_col],
            [posted_true],
            [header_key_col],
            [old_key],
        ):
            return DataImportResult(
                kind=kind,
                ok=False,
                message=(
                    f"已匯入 {old_key}→{new_key}，但更新 TRANSFER.{src_header}.POSTED 失敗："
                    f"{transfer_backend.last_error or '未知錯誤'}"
                ),
            )
        posted_count += 1
        detail_lines.append(
            f"{old_key} → {new_key}（TX_NO={new_tx_no}，{dst_header} 1 筆，{dst_item} {item_n} 筆，"
            f"已更新 TRANSFER.{src_header}.POSTED）"
        )
        _emit(progress, detail_lines[-1])

    if h_count == 0:
        msg = "沒有符合的未處理資料可匯入。"
        if want_keys and total_todo == 0:
            msg += (
                f" 已選 {len(want_keys)} 筆，但 TRANSFER 主檔對不到相同鍵值"
                f"（讀取來源可能已變更）。請關閉視窗後重新開啟 DATAIMPORT。"
            )
        elif want_keys:
            msg += (
                f" 已選 {len(want_keys)} 筆且鍵值有對到，但皆非未處理（POSTED=FALSE）。"
                f" 請重新載入待匯入清單。"
            )
        return DataImportResult(
            kind=kind,
            ok=False,
            message=msg,
        )

    tables = [
        TableImportResult(source_table=src_header, dest_table=dst_header, rows_imported=h_count),
        TableImportResult(source_table=src_item, dest_table=dst_item, rows_imported=i_count),
    ]
    summary = (
        f"匯入完成（TRANSFER → 公司庫）：處理 {h_count} 筆主檔、{i_count} 筆明細，"
        f"更新 POSTED {posted_count} 筆。\n"
        f"TRANSFER.{src_header}→{dst_header}: {h_count} 筆\n"
        f"TRANSFER.{src_item}→{dst_item}: {i_count} 筆"
    )
    if detail_lines:
        summary += "\n\n" + "\n".join(detail_lines)
    _emit(progress, summary)
    return DataImportResult(kind=kind, tables=tables, ok=True, message=summary)


def data_import_result_dict(result: DataImportResult) -> Dict[str, object]:
    return {
        "kind": result.kind,
        "ok": result.ok,
        "message": result.message,
        "tables": [
            {
                "source_table": t.source_table,
                "dest_table": t.dest_table,
                "rows_imported": t.rows_imported,
                "error": t.error,
            }
            for t in result.tables
        ],
        "total_rows": sum(t.rows_imported for t in result.tables),
    }
