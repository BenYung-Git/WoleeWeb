"""主檔 UPDATE/DELETE 的 WHERE 鍵解析（避免整列比對失敗）。"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

# 常見單據鍵欄（報價／發票／採購等）
STABLE_KEY_FALLBACKS: Tuple[str, ...] = (
    "TX_KEY",
    "QUOTE_NO",
    "QUOTATION_NO",
    "QUOT_NO",
    "QUO_KEY",
    "VOU_KEY",
    "INV_NO",
    "INVOICE_NO",
    "ID",
)


def resolve_tx_filter_column(
    tx_physical: Sequence[str],
    master_key_col: Optional[str],
) -> Optional[str]:
    if master_key_col:
        want = master_key_col.strip().upper()
        for c in tx_physical:
            if (c or "").strip().upper() == want:
                return str(c)
    for c in tx_physical:
        if (c or "").strip().upper() == "TX_KEY":
            return str(c)
    for name in STABLE_KEY_FALLBACKS:
        if name == "TX_KEY":
            continue
        want = name.upper()
        for c in tx_physical:
            if (c or "").strip().upper() == want:
                return str(c)
    return None


def resolve_update_where(
    physical_fields: Sequence[str],
    old_row: Sequence[str],
    *,
    print_doc_key_column: Optional[str] = None,
    form_fields: Optional[Sequence[str]] = None,
) -> Tuple[List[str], List[str]]:
    """
    優先用 KEY_CODE / 單據編號 / TX_KEY / ID 作 WHERE。
    找不到鍵值時才回退整列（或 form_fields 子集）。
    """
    phys = list(physical_fields)
    row = list(old_row)
    candidates: List[str] = []
    for c in ((print_doc_key_column or "").strip(), *STABLE_KEY_FALLBACKS):
        if c and c.upper() not in [x.upper() for x in candidates]:
            candidates.append(c)

    for col in candidates:
        want = col.strip().upper()
        for i, name in enumerate(phys):
            if (name or "").strip().upper() != want:
                continue
            if i < len(row):
                v = str(row[i] or "").strip()
                if v:
                    return [phys[i]], [row[i]]
            break

    if form_fields:
        out_fields: List[str] = []
        out_vals: List[str] = []
        for f in form_fields:
            try:
                i = phys.index(f)
                out_fields.append(f)
                out_vals.append(row[i] if i < len(row) else "")
            except ValueError:
                out_fields.append(f)
                out_vals.append("")
        if out_fields:
            return out_fields, out_vals

    return phys, row


def delete_tx_rows_for_master(
    backend,
    tx_tables: Sequence[str],
    master_key_col: str,
    master_key_val: str,
) -> Tuple[bool, str]:
    """刪除主檔前先刪除同鍵之 TX 明細（有資料才 DELETE）。"""
    key_col = (master_key_col or "").strip()
    key_val = (master_key_val or "").strip()
    if not key_col or not key_val:
        return True, ""

    for tx_table in tx_tables or []:
        table = (tx_table or "").strip()
        if not table:
            continue
        phys = backend.list_columns(table)
        if not phys:
            continue
        tx_key = resolve_tx_filter_column(phys, key_col)
        if not tx_key:
            continue
        existing = backend.fetch_rows_where(
            table, tx_key, key_val, limit=1, column_order=list(phys)
        )
        if not existing:
            continue
        if not backend.delete_one(table, [tx_key], [key_val]):
            err = str(getattr(backend, "last_error", "") or "").strip()
            return False, err or f"{table}: 刪除明細失敗。"

    return True, ""
