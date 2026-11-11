"""SEARCH_RET：LOOKUP_DB／LOOKUP_KEY 查找後，依「目標欄=LOOKUP欄」回寫。"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from core.data_dictionary import DataDictionary, LanguageCode
from core.db_backend import DbBackendBase

_BOOL_LIKE = frozenset(
    {"Y", "N", "YES", "NO", "TRUE", "FALSE", "1", "0", "-1"}
)


def _field_index(columns: List[str], name: str) -> int:
    want = (name or "").strip().upper()
    if not want:
        return -1
    for i, c in enumerate(columns or []):
        if (c or "").strip().upper() == want:
            return i
    return -1


def _match_lookup_key(cell: str, keyword: str) -> bool:
    a = (cell or "").strip().lower()
    b = (keyword or "").strip().lower()
    if not b:
        return False
    return a == b or b in a


def parse_search_ret_pairs(search_ret: str) -> List[Tuple[str, str]]:
    """
    解析 SEARCH_RET：
      左邊（= 前）＝本表／表單要回存的欄位
      右邊（= 後）＝LOOKUP_DB 要取值的欄位
    多組可用 ; 或 , 分隔，例如：CUS_NAME=NAME;ADDR=ADDRESS
    無等號時：僅目標欄，右邊稍後預設 LOOKUP_KEY。
    """
    raw = (search_ret or "").strip()
    if not raw or raw.upper() in _BOOL_LIKE:
        return []
    parts: List[str] = []
    for chunk in raw.replace(",", ";").split(";"):
        s = chunk.strip()
        if s:
            parts.append(s)
    out: List[Tuple[str, str]] = []
    for part in parts:
        if "=" in part:
            left, right = part.split("=", 1)
            dest = left.strip()
            src = right.strip()
            if dest:
                out.append((dest, src))
        else:
            out.append((part, ""))
    return out


def _find_lookup_row(
    *,
    data_dict: DataDictionary,
    backend: DbBackendBase,
    lookup_db: str,
    lookup_key: str,
    keyword: str,
) -> Tuple[Optional[List[str]], Optional[List[str]], Optional[str]]:
    """
    回傳 (physical_columns, matched_row, error)。
    error 僅在資料表／鍵欄無法使用時；找不到列回 (cols, None, None)。
    """
    data_dict.load_columns_for_dbf(lookup_db)
    physical = backend.list_columns(lookup_db)
    if not physical:
        return None, None, "missing"
    key_idx = _field_index(physical, lookup_key)
    if key_idx < 0:
        return None, None, "missing"
    rows = backend.fetch_rows(lookup_db, "", False, limit=5000, column_order=physical)
    for rec in rows:
        if key_idx >= len(rec):
            continue
        if _match_lookup_key(str(rec[key_idx] or ""), keyword):
            return physical, [str(x or "") for x in rec], None
    return physical, None, None


def _values_from_lookup_row(
    physical: List[str],
    row: List[str],
    pairs: List[Tuple[str, str]],
    default_src: str,
) -> List[Tuple[str, str]]:
    """依 pairs 從 LOOKUP 列取值 → [(dest_field, value), ...]。"""
    out: List[Tuple[str, str]] = []
    for dest, src in pairs:
        src_field = (src or "").strip() or (default_src or "").strip()
        if not dest or not src_field:
            continue
        idx = _field_index(physical, src_field)
        if idx < 0 or idx >= len(row):
            continue
        val = str(row[idx] or "").strip()
        out.append((dest, val))
    return out


def resolve_search_ret_via_lookup(
    *,
    data_dict: DataDictionary,
    backend: Optional[DbBackendBase],
    table_name: str,
    keyword: str,
    lang: LanguageCode = "CHN",
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Grid 搜尋／過濾：LOOKUP_KEY 比對後，取 SEARCH_RET 右邊 LOOKUP 欄值，
    以左邊欄位在主檔定位。

    回傳 (dest_field, resolved_value, error_message)
    """
    kw = (keyword or "").strip()
    if not kw or backend is None:
        return None, None, None

    rules = data_dict.list_search_ret_rules(table_name)
    if not rules:
        return None, None, None

    not_found = "找不到符合的資料。" if lang == "CHN" else "No matching data found."

    for rule in rules:
        lookup_db = (rule.get("lookup_db") or "").strip()
        lookup_key = (rule.get("lookup_key") or "").strip()
        search_ret = (rule.get("search_ret") or "").strip()
        if not lookup_db or not lookup_key or not search_ret:
            continue
        pairs = parse_search_ret_pairs(search_ret)
        if not pairs:
            continue
        _phys, row, miss = _find_lookup_row(
            data_dict=data_dict,
            backend=backend,
            lookup_db=lookup_db,
            lookup_key=lookup_key,
            keyword=kw,
        )
        if miss == "missing":
            continue
        if row is None or _phys is None:
            continue
        mapped = _values_from_lookup_row(_phys, row, pairs, lookup_key)
        if mapped:
            dest, value = mapped[0]
            if value:
                return dest, value, None

    return None, None, not_found


def resolve_input_search_ret_for_field(
    *,
    data_dict: DataDictionary,
    backend: Optional[DbBackendBase],
    table_name: str,
    source_field: str,
    input_value: str,
    lang: LanguageCode = "CHN",
) -> Tuple[Optional[List[Tuple[str, str]]], Optional[str]]:
    """
    輸入欄結束編輯：
      以 LOOKUP_KEY 在 LOOKUP_DB 查找輸入值；
      依 SEARCH_RET「左邊=本表欄／右邊=LOOKUP欄」回存各對應值。

    回傳 ([(dest_field, value), ...], error_message)
    - 無設定：(None, None)
    - 找不到：(None, 訊息)
    - 成功：(對應清單, None)
    """
    kw = (input_value or "").strip()
    if not kw or backend is None:
        return None, None

    field = (source_field or "").strip()
    if not field:
        return None, None

    search_ret = (data_dict.get_search_ret(table_name, field) or "").strip()
    lookup_db, lookup_key, _lookup_ret = data_dict.get_lookup(table_name, field)
    lookup_db = (lookup_db or "").strip()
    lookup_key = (lookup_key or "").strip()
    pairs = parse_search_ret_pairs(search_ret)
    if not pairs or not lookup_db or not lookup_key:
        return None, None

    not_found = "找不到符合的資料。" if lang == "CHN" else "No matching data found."

    physical, row, miss = _find_lookup_row(
        data_dict=data_dict,
        backend=backend,
        lookup_db=lookup_db,
        lookup_key=lookup_key,
        keyword=kw,
    )
    if miss == "missing" or physical is None or row is None:
        return None, not_found

    mapped = _values_from_lookup_row(physical, row, pairs, lookup_key)
    if not mapped:
        return None, not_found
    return mapped, None


def find_row_by_field_value(
    rows: List[List[str]],
    physical: List[str],
    field_name: str,
    value: str,
) -> int:
    """在主檔列中找欄位等於 value 的列索引；找不到回 -1。"""
    idx = _field_index(physical, field_name)
    if idx < 0:
        return -1
    want = (value or "").strip().lower()
    for r, rec in enumerate(rows or []):
        if idx < len(rec) and str(rec[idx] or "").strip().lower() == want:
            return r
        if idx < len(rec) and want and want in str(rec[idx] or "").strip().lower():
            return r
    return -1
