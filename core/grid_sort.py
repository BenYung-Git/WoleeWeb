"""Grid 欄位排序（單欄／多欄）共用邏輯。"""
from __future__ import annotations

from dataclasses import dataclass
from functools import cmp_to_key
from typing import Callable, List, Sequence, TypeVar

T = TypeVar("T")


@dataclass
class GridSortKey:
    column: int
    descending: bool = False


def toggle_grid_sort_stack(
    stack: List[GridSortKey], column: int, *, multi: bool = False
) -> None:
    """更新排序堆疊：一般點擊單欄；Ctrl+點擊多欄（升冪→降冪→移除）。"""
    col = int(column)
    hit = next((i for i, s in enumerate(stack) if s.column == col), -1)
    if not multi:
        if hit >= 0 and len(stack) == 1:
            stack[0] = GridSortKey(col, descending=not stack[0].descending)
        else:
            stack[:] = [GridSortKey(col, descending=False)]
        return
    if hit >= 0:
        cur = stack[hit]
        if not cur.descending:
            stack[hit] = GridSortKey(col, descending=True)
        else:
            stack.pop(hit)
    else:
        stack.append(GridSortKey(col, descending=False))


def _compare_values(a: str, b: str, *, numeric: bool) -> int:
    sa = str(a if a is not None else "").strip()
    sb = str(b if b is not None else "").strip()
    if numeric:
        try:
            na = float(sa.replace(",", "")) if sa else 0.0
            nb = float(sb.replace(",", "")) if sb else 0.0
            if na < nb:
                return -1
            if na > nb:
                return 1
            return 0
        except ValueError:
            pass
    la = sa.lower()
    lb = sb.lower()
    if la < lb:
        return -1
    if la > lb:
        return 1
    return 0


def sort_indices_by_stack(
    rows: Sequence[Sequence[str]],
    stack: Sequence[GridSortKey],
    value_at: Callable[[Sequence[str], int], str],
    *,
    is_numeric_col: Callable[[int], bool] | None = None,
) -> List[int]:
    if not rows or not stack:
        return list(range(len(rows)))
    num_fn = is_numeric_col or (lambda _c: False)

    def row_cmp(ia: int, ib: int) -> int:
        ra = rows[ia]
        rb = rows[ib]
        for sk in stack:
            va = value_at(ra, sk.column)
            vb = value_at(rb, sk.column)
            c = _compare_values(va, vb, numeric=num_fn(sk.column))
            if c != 0:
                return -c if sk.descending else c
        return 0

    return sorted(range(len(rows)), key=cmp_to_key(row_cmp))


def sort_rows_by_stack(
    rows: List[List[str]],
    stack: Sequence[GridSortKey],
    value_at: Callable[[Sequence[str], int], str],
    *,
    is_numeric_col: Callable[[int], bool] | None = None,
) -> List[List[str]]:
    if not rows or not stack:
        return list(rows)
    order = sort_indices_by_stack(
        rows, stack, value_at, is_numeric_col=is_numeric_col
    )
    return [list(rows[i]) for i in order]


def sort_indicator_text(stack: Sequence[GridSortKey], column: int) -> str:
    for i, sk in enumerate(stack):
        if sk.column == column:
            arrow = "▼" if sk.descending else "▲"
            suffix = str(i + 1) if len(stack) > 1 else ""
            return f" {arrow}{suffix}"
    return ""
