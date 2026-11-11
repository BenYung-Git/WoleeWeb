from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "TEMPLATES" / "Quotation.xlsx"

QUOTATION_FIELDS = [
    "TX_KEY",
    "TX_TYPE",
    "TX_NO",
    "TX_REVISED",
    "TX_GROUP",
    "REF_NO",
    "INVOICE_NO",
    "DATE",
    "TIME",
    "VALID_DAY",
    "EXPIRE_DATE",
    "PRJ_KEY",
    "CUST_KEY",
    "CUST_NAME",
    "CUST_PO",
    "INV_AMEND",
    "ADDR_TYPE",
    "ADDRESS",
    "ATTN",
    "TEL",
    "FAX",
    "MOBILE",
    "EMAIL",
    "TERMS",
    "SALE_CODE",
    "SALE_NAME",
    "TX_CURR",
    "TX_RATE",
    "TX_AMT",
    "DISC_%",
    "DISC_SHARE",
    "DISC_AMT",
    "NET_AMT",
    "FIX_RATE",
    "REMARK",
    "PRN_COUNT",
    "USER",
    "IP_ADDR",
    "POSTED",
    "DELETED",
]

QUOTTRX_FIELDS = [
    "ITEM_NO",
    "TX_KEY",
    "ITEM_CODE",
    "STK_CODE",
    "STK_DESC",
    "OUR_PRODUCT",
    "COUNT_BY",
    "UNIT_CODE",
    "UNIT_RATE",
    "QTY",
    "WEIGHT",
    "WGT_UNIT",
    "LOC",
    "PER",
    "UNIT_PRICE",
    "CURRENCY",
    "RATE",
    "TX_DISC",
    "TX_DISC_AMT",
    "AMOUNT",
    "ITEM_REMARK",
    "DELETED",
]


def _find_logo() -> Optional[Path]:
    candidates: Iterable[Path] = (
        ROOT / "TEMPLATES" / "logo.jpg",
        ROOT / "TEMPLATES" / "logo.bmp",
        ROOT / "REPORT" / "logo.jpg",
        ROOT / "REPORT" / "logo.bmp",
        ROOT / "reports" / "logo.jpg",
        ROOT / "reports" / "logo.bmp",
        ROOT / "templates" / "logo.jpg",
        ROOT / "templates" / "logo.bmp",
        ROOT / "logo.jpg",
        ROOT / "logo.bmp",
    )
    for p in candidates:
        if p.is_file():
            return p
    return None


def _set_border(ws, r1: int, c1: int, r2: int, c2: int) -> None:
    bd = Border(
        left=Side(style="thin", color="000000"),
        right=Side(style="thin", color="000000"),
        top=Side(style="thin", color="000000"),
        bottom=Side(style="thin", color="000000"),
    )
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            ws.cell(r, c).border = bd


def _build_template() -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Quotation"

    for col, w in {
        "A": 10,
        "B": 13,
        "C": 13,
        "D": 13,
        "E": 10,
        "F": 13,
        "G": 11,
        "H": 13,
    }.items():
        ws.column_dimensions[col].width = w

    f11 = Font(name="Calibri", size=11)
    f11b = Font(name="Calibri", size=11, bold=True)
    f20b = Font(name="Calibri", size=20, bold=True)
    fill = PatternFill("solid", fgColor="F2F2F2")
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center", wrap_text=True)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    top = Alignment(horizontal="left", vertical="top", wrap_text=True)

    ws.merge_cells("A1:B5")
    ws["A1"] = "LOGO"
    ws["A1"].alignment = center
    ws["A1"].font = Font(name="Calibri", size=10, italic=True, color="666666")

    header = [
        "{{company_header_en}}",
        "{{company_header_zh}}",
        "{{company_contact}}",
        "{{company_email}}",
    ]
    for i, t in enumerate(header, start=1):
        ws.merge_cells(f"C{i}:H{i}")
        ws[f"C{i}"] = t
        ws[f"C{i}"].font = f11
        ws[f"C{i}"].alignment = left

    ws.merge_cells("A6:H6")
    ws["A6"] = "QUOTATION"
    ws["A6"].font = f20b
    ws["A6"].alignment = center

    def pair_row(r: int, l1: str, v1: str, l2: str, v2: str, right2: bool = False) -> None:
        ws[f"A{r}"] = l1
        ws[f"A{r}"].font = f11b
        ws.merge_cells(f"B{r}:D{r}")
        ws[f"B{r}"] = v1
        ws[f"B{r}"].alignment = left
        ws[f"E{r}"] = l2
        ws[f"E{r}"].font = f11b
        ws.merge_cells(f"F{r}:H{r}")
        ws[f"F{r}"] = v2
        ws[f"F{r}"].alignment = right if right2 else left

    pair_row(8, "Company :", "{{CUST_NAME}}", "Quotation No. :", "{{TX_NO}}", True)
    pair_row(9, "Attention :", "{{ATTN}}", "Tel:", "{{TEL}}")
    pair_row(10, "Email :", "{{EMAIL}}", "Date :", "{{DATE}}", True)
    pair_row(11, "Ref. No. :", "{{REF_NO}}", "Prepared by :", "{{SALE_NAME}}")
    pair_row(12, "Tel:", "{{SALE_TEL}}", "Project:", "{{PRJ_KEY}}")

    ws.merge_cells("A14:H14")
    ws["A14"] = "Thank you for your enquiry. We are pleased to submit our quotation for the below works as follow:"
    ws["A14"].alignment = left

    # table headers
    ws.merge_cells("A16:A17")
    ws["A16"] = "Item No."
    ws["A16"].alignment = center
    ws.merge_cells("B16:D16")
    ws["B16"] = "Description"
    ws["B16"].alignment = left
    ws.merge_cells("B17:D17")
    ws["B17"] = ""
    ws.merge_cells("E16:E17")
    ws["E16"] = "Quantity\n(Unit)"
    ws["E16"].alignment = center
    ws.merge_cells("F16:F17")
    ws["F16"] = "Unit Price\n(HKD)"
    ws["F16"].alignment = right
    ws.merge_cells("G16:H16")
    ws["G16"] = "Amount"
    ws["G16"].alignment = right
    ws.merge_cells("G17:H17")
    ws["G17"] = "(HKD)"
    ws["G17"].alignment = right
    for c in ("A16", "B16", "E16", "F16", "G16", "B17", "G17"):
        ws[c].font = f11b
        ws[c].fill = fill

    data_start = 18
    for i in range(15):
        r = data_start + i
        ws[f"A{r}"] = f"{{{{TRX.ITEM_NO[{i}]}}}}"
        ws.merge_cells(f"B{r}:D{r}")
        ws[f"B{r}"] = f"{{{{TRX.STK_DESC[{i}]}}}}"
        ws[f"E{r}"] = f"{{{{TRX.QTY[{i}]}}}}"
        ws[f"F{r}"] = f"{{{{TRX.UNIT_PRICE[{i}]}}}}"
        ws.merge_cells(f"G{r}:H{r}")
        ws[f"G{r}"] = f"{{{{TRX.AMOUNT[{i}]}}}}"
        ws[f"A{r}"].alignment = center
        ws[f"B{r}"].alignment = left
        ws[f"E{r}"].alignment = right
        ws[f"F{r}"].alignment = right
        ws[f"G{r}"].alignment = right

    total_r = data_start + 15
    ws.merge_cells(f"A{total_r}:F{total_r}")
    ws[f"A{total_r}"] = "Total Amount (HKD)"
    ws[f"A{total_r}"].font = f11b
    ws[f"A{total_r}"].alignment = right
    ws.merge_cells(f"G{total_r}:H{total_r}")
    ws[f"G{total_r}"] = "{{NET_AMT}}"
    ws[f"G{total_r}"].font = f11b
    ws[f"G{total_r}"].alignment = right

    sec = total_r + 2
    ws.merge_cells(f"A{sec}:H{sec}")
    ws[f"A{sec}"] = "Remark :"
    ws[f"A{sec}"].font = f11b
    ws.merge_cells(f"A{sec+1}:H{sec+3}")
    ws[f"A{sec+1}"] = "{{REMARK}}"
    ws[f"A{sec+1}"].alignment = top

    ws.merge_cells(f"A{sec+5}:H{sec+5}")
    ws[f"A{sec+5}"] = "Terms of Payment:"
    ws[f"A{sec+5}"].font = f11b
    ws.merge_cells(f"A{sec+6}:H{sec+9}")
    ws[f"A{sec+6}"] = "{{TERMS}}"
    ws[f"A{sec+6}"].alignment = top

    ws.merge_cells(f"A{sec+11}:H{sec+11}")
    ws[f"A{sec+11}"] = "Validity:"
    ws[f"A{sec+11}"].font = f11b
    ws.merge_cells(f"A{sec+12}:H{sec+15}")
    ws[f"A{sec+12}"] = "{{VALIDITY_TERMS}}"
    ws[f"A{sec+12}"].alignment = top

    sig = sec + 18
    ws.merge_cells(f"A{sig}:D{sig+8}")
    ws[f"A{sig}"] = (
        "Yours faithfully,\n\nFor and on behalf of\n{{company_name}}\n\n\n"
        "______________________________\nAuthorized Signature with Company Chop"
    )
    ws[f"A{sig}"].alignment = left
    ws.merge_cells(f"E{sig}:H{sig+8}")
    ws[f"E{sig}"] = (
        "For and on behalf of\n{{CUST_NAME}}\n\n\n"
        "______________________________\nAuthorized Signature with Company Chop"
    )
    ws[f"E{sig}"].alignment = left

    _set_border(ws, 16, 1, total_r, 8)
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = False
    ws.print_title_rows = "1:17"

    logo = _find_logo()
    if logo:
        try:
            from openpyxl.drawing.image import Image as XLImage

            img = XLImage(str(logo))
            img.width = 125
            img.height = int(img.height * (125 / max(img.width, 1)))
            ws.add_image(img, "A1")
            ws["A1"] = ""
        except Exception:
            pass
    return wb


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb = _build_template()
    wb.save(OUT)
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

