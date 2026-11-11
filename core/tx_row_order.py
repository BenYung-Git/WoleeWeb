"""TX 明細列順序：移動列與自動重算 ITEM_NO。"""

from __future__ import annotations

from typing import List, Optional, Sequence


def item_no_column_index(physical_fields: Sequence[str]) -> Optional[int]:
    for i, name in enumerate(physical_fields):
        if str(name or "").strip().upper() == "ITEM_NO":
            return i
    return None


def renumber_item_no(physical_fields: Sequence[str], rows: List[List[str]]) -> None:
    """依目前列順序將 ITEM_NO 重編為 1..n（就地修改）。無 ITEM_NO 欄則略過。"""
    idx = item_no_column_index(physical_fields)
    if idx is None:
        return
    for n, row in enumerate(rows, start=1):
        while len(row) <= idx:
            row.append("")
        row[idx] = str(n)


def move_row(rows: List, src: int, dest_before: int) -> int:
    """
    將 src 列移到 dest_before 之前（dest_before 以移動前索引計）。
    dest_before == len(rows) 表示移到最後。
    回傳移動後的新索引。
    """
    n = len(rows)
    if n <= 1 or src < 0 or src >= n:
        return src
    dest = int(dest_before)
    if dest < 0:
        dest = 0
    if dest > n:
        dest = n
    if dest == src or dest == src + 1:
        return src
    row = rows.pop(src)
    if dest > src:
        dest -= 1
    dest = max(0, min(dest, len(rows)))
    rows.insert(dest, row)
    return dest


def relocate_row(rows: List, src: int, new_index: int) -> int:
    """將 src 列移到 new_index（0-based 最終位置），回傳實際新索引。"""
    n = len(rows)
    if n <= 1 or src < 0 or src >= n:
        return src
    target = max(0, min(int(new_index), n - 1))
    if target == src:
        return src
    # insert-before index in pre-removal coordinates
    dest_before = target if target < src else target + 1
    return move_row(rows, src, dest_before)
