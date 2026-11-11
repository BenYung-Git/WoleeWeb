from __future__ import annotations

from typing import List, Optional, Tuple

from core import quotation_xls_print as _q

_INVOICE_XLS_NAMES = (
    "Invoice.xlsx",
    "INVOICE.xlsx",
    "invoice.xlsx",
    "Invoice.xls",
    "INVOICE.xls",
    "invoice.xls",
)


def _run_with_invoice_names(fn, *args, **kwargs):
    old_names = _q._QUOTATION_XLS_NAMES
    try:
        _q._QUOTATION_XLS_NAMES = _INVOICE_XLS_NAMES
        return fn(*args, **kwargs)
    finally:
        _q._QUOTATION_XLS_NAMES = old_names


def print_invoice_xls(
    base_dir: str,
    physical_fields: List[str],
    row: List[str],
    stk_fields: Optional[List[str]] = None,
    stk_rows: Optional[List[List[str]]] = None,
    lang: str = "CHN",
) -> Tuple[bool, str]:
    return _run_with_invoice_names(
        _q.print_quotation_xls,
        base_dir,
        physical_fields,
        row,
        stk_fields,
        stk_rows,
        lang,
    )


def generate_invoice_pdf_from_template(
    base_dir: str,
    physical_fields: List[str],
    row: List[str],
    stk_fields: Optional[List[str]] = None,
    stk_rows: Optional[List[List[str]]] = None,
    lang: str = "CHN",
) -> Tuple[bool, str, Optional[str]]:
    return _run_with_invoice_names(
        _q.generate_quotation_pdf_from_template,
        base_dir,
        physical_fields,
        row,
        stk_fields,
        stk_rows,
        lang,
    )

