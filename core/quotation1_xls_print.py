from __future__ import annotations

from typing import List, Optional, Tuple

from core import quotation_xls_print as _q

_QUOTATION1_XLS_NAMES = (
    "Quotation1.xlsx",
    "QUOTATION1.xlsx",
    "quotation1.xlsx",
    "Quotation1.xls",
    "QUOTATION1.xls",
    "quotation1.xls",
)


def _run_with_quotation1_names(fn, *args, **kwargs):
    old_names = _q._QUOTATION_XLS_NAMES
    try:
        _q._QUOTATION_XLS_NAMES = _QUOTATION1_XLS_NAMES
        return fn(*args, **kwargs)
    finally:
        _q._QUOTATION_XLS_NAMES = old_names


def print_quotation1_xls(
    base_dir: str,
    physical_fields: List[str],
    row: List[str],
    trx_fields: Optional[List[str]] = None,
    trx_rows: Optional[List[List[str]]] = None,
    lang: str = "CHN",
) -> Tuple[bool, str]:
    """僅使用 Quotation1.xlsx / Quotation1.xls 範本列印。"""
    return _run_with_quotation1_names(
        _q.print_quotation_xls,
        base_dir,
        physical_fields,
        row,
        trx_fields,
        trx_rows,
        lang,
    )


def generate_quotation1_pdf_from_template(
    base_dir: str,
    physical_fields: List[str],
    row: List[str],
    trx_fields: Optional[List[str]] = None,
    trx_rows: Optional[List[List[str]]] = None,
    lang: str = "CHN",
) -> Tuple[bool, str, Optional[str]]:
    """僅使用 Quotation1.xlsx / Quotation1.xls 範本產生 PDF。"""
    return _run_with_quotation1_names(
        _q.generate_quotation_pdf_from_template,
        base_dir,
        physical_fields,
        row,
        trx_fields,
        trx_rows,
        lang,
    )
