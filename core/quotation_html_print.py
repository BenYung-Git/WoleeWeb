from __future__ import annotations

import html
import os
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


def resolve_quotation_html_template(base_dir: str) -> Optional[str]:
    p = os.path.join(os.path.abspath(base_dir or ""), "templates", "quotation_print_template.html")
    return p if os.path.isfile(p) else None


def _pick(data: Dict[str, Any], *keys: str, default: str = "") -> str:
    upper = {(k or "").strip().upper(): v for k, v in data.items()}
    for key in keys:
        v = upper.get((key or "").strip().upper())
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return default


def _format_date(v: str) -> str:
    s = (v or "").strip()
    if not s:
        return ""
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return s


def _to_amount(v: Any) -> float:
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except Exception:
        return 0.0


def _fmt_money(v: float) -> str:
    return f"{v:,.2f}"


def _render_item_rows(qouttrx_rows: Iterable[Dict[str, Any]]) -> tuple[str, float]:
    rows_html: List[str] = []
    total = 0.0
    for idx, row in enumerate(qouttrx_rows, start=1):
        item_no = _pick(row, "ITEM_NO", "SEQ", "LINE_NO", default=str(idx))
        desc = _pick(row, "DESCRIPTION", "DESC", "ITEM_DESC")
        qty = _pick(row, "QUANTITY", "QTY", default="0")
        unit = _pick(row, "UNIT", "QTY_UNIT")
        unit_price_raw = _pick(row, "UNIT_PRICE", "PRICE", "PRICE1", default="0")
        amount_raw = _pick(row, "AMOUNT", "TOTAL", "LINE_TOTAL", default="")

        qty_num = _to_amount(qty)
        unit_price_num = _to_amount(unit_price_raw)
        amount_num = _to_amount(amount_raw) if amount_raw else qty_num * unit_price_num
        total += amount_num

        qty_text = qty if qty else "0"
        unit_price_text = _fmt_money(unit_price_num)
        amount_text = _fmt_money(amount_num)
        if unit:
            qty_text = f"{qty_text} {unit}"

        rows_html.append(
            "<tr>"
            f"<td class='py-1 align-top'>{html.escape(item_no)}</td>"
            f"<td class='py-1 align-top'>{html.escape(desc)}</td>"
            f"<td class='py-1 text-right align-top'>{html.escape(qty_text)}</td>"
            f"<td class='py-1 text-right align-top'>{unit_price_text}</td>"
            f"<td class='py-1 text-right align-top'>{amount_text}</td>"
            "</tr>"
        )

    if not rows_html:
        rows_html.append(
            "<tr><td class='py-4'>&nbsp;</td><td></td><td></td><td></td><td></td></tr>"
        )
    return "\n".join(rows_html), total


def render_quotation_html(
    base_dir: str,
    quotation_row: Dict[str, Any],
    qouttrx_rows: List[Dict[str, Any]],
    output_html_path: str,
) -> str:
    """
    以 QUOTATION（主檔）+ QOUTTRX（明細）輸出可列印 HTML 報價單。
    """
    tpl = resolve_quotation_html_template(base_dir)
    if not tpl:
        raise FileNotFoundError("templates/quotation_print_template.html not found.")
    with open(tpl, "r", encoding="utf-8") as f:
        html_tpl = f.read()

    item_rows_html, calc_total = _render_item_rows(qouttrx_rows)
    total_from_header = _to_amount(_pick(quotation_row, "TOTAL_AMOUNT", "AMOUNT", "TOTAL"))
    total_amount = total_from_header if total_from_header > 0 else calc_total

    fields = {
        "company_header_en": "1/F, ISLAND INDUSTRIAL BUILDING, 81-87 TUNG CHAU STREET, TAI KOK TSUI, KOWLOON, HONG KONG",
        "company_header_zh": "香港九龍大角咀通州街81-87號港灣工業大廈 1/F",
        "company_contact": "TEL.: 2395 1332          FAX.: 2381 9710",
        "company_email": "E-mail: solutions@wolee.com",
        "quotation_no": _pick(quotation_row, "QUOTE_NO", "QUOTATION_NO", "QUOT_NO"),
        "customer_name": _pick(quotation_row, "COMPANY", "CUST_NAME", "CUSTOMER_NAME"),
        "attention": _pick(quotation_row, "ATTENTION", "CONTACT", "CONTACT_NAME"),
        "customer_tel": _pick(quotation_row, "TEL", "PHONE", "CUST_TEL"),
        "quote_date": _format_date(_pick(quotation_row, "DATE", "QUOTE_DATE", "QUOTATION_DATE")),
        "customer_email": _pick(quotation_row, "EMAIL", "CUST_EMAIL"),
        "ref_no": _pick(quotation_row, "REF_NO", "REFERENCE_NO"),
        "prepared_by": _pick(quotation_row, "PREPARED_BY", "CREATED_BY", "USER_NO"),
        "prepared_tel": _pick(quotation_row, "PREPARED_TEL", "STAFF_TEL"),
        "project_name": _pick(quotation_row, "PROJECT", "PROJECT_NAME"),
        "total_amount": _fmt_money(total_amount),
        "remark": _pick(quotation_row, "REMARK", "REMARKS"),
        "terms_of_payment": _pick(
            quotation_row,
            "TERMS_OF_PAYMENT",
            "PAYMENT_TERMS",
            default='1.) The payment shall be paid by crossed cheque.\n2.) NET 30 DAYS',
        ),
        "validity_terms": _pick(
            quotation_row,
            "VALIDITY",
            "VALIDITY_TERMS",
            default=(
                "1.) This quotation is valid for 30 days from date of this quotation.\n"
                "2.) Amendments should be authorized by company representative with company chop."
            ),
        ),
        "sign_company_en": "Wo Lee Green Solutions Limited",
        "sign_company_zh": "和理綠色電子科技有限公司",
        "item_rows_html": item_rows_html,
    }

    out = html_tpl
    for k, v in fields.items():
        if k == "item_rows_html":
            out = out.replace(f"{{{{{k}}}}}", v)
        else:
            out = out.replace(f"{{{{{k}}}}}", html.escape(str(v or "")))

    os.makedirs(os.path.dirname(os.path.abspath(output_html_path)), exist_ok=True)
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(out)
    return output_html_path

