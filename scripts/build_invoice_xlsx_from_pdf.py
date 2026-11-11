from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "TEMPLATES" / "Invoice.xlsx"


def _find_logo() -> Optional[Path]:
    candidates: Iterable[Path] = (
        ROOT / "TEMPLATES" / "logo.jpg",
        ROOT / "TEMPLATES" / "logo.bmp",
        ROOT / "templates" / "logo.jpg",
        ROOT / "templates" / "logo.bmp",
        ROOT / "reports" / "logo.jpg",
        ROOT / "reports" / "logo.bmp",
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
    ws.title = "Invoice"

    for col, w in {"A": 10, "B": 14, "C": 14, "D": 14, "E": 10, "F": 13, "G": 12, "H": 13}.items():
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

    lines = [
        "{{company_header_en}}",
        "{{company_contact}}",
        "{{company_header_zh}}",
        "{{company_email}}",
        "Finance Dept",
    ]
    for i, t in enumerate(lines, start=1):
        ws.merge_cells(f"C{i}:H{i}")
        ws[f"C{i}"] = t
        ws[f"C{i}"].font = f11
        ws[f"C{i}"].alignment = left

    ws.merge_cells("A6:H6")
    ws["A6"] = "INVOICE\n發票"
    ws["A6"].font = f20b
    ws["A6"].alignment = center

    ws["A8"] = "SOLD TO :"
    ws["A8"].font = f11b
    ws.merge_cells("B8:D8")
    ws["B8"] = "{{CUST_NAME}}"
    ws["E8"] = "INVOICE NO. :"
    ws["E8"].font = f11b
    ws.merge_cells("F8:H8")
    ws["F8"] = "{{TX_NO}}"
    ws["F8"].alignment = right

    ws["A9"] = "Attention :"
    ws["A9"].font = f11b
    ws.merge_cells("B9:D9")
    ws["B9"] = "{{ATTN}}"
    ws["E9"] = "TEL :"
    ws["E9"].font = f11b
    ws.merge_cells("F9:H9")
    ws["F9"] = "{{TEL}}"

    ws["A10"] = "CUSTOMER REF. NO. :"
    ws["A10"].font = f11b
    ws.merge_cells("B10:D10")
    ws["B10"] = "{{CUST_PO}}"
    ws["E10"] = "INVOICE DATE :"
    ws["E10"].font = f11b
    ws.merge_cells("F10:H10")
    ws["F10"] = "{{DATE}}"
    ws["F10"].alignment = right

    ws["A11"] = "OUR REF. NO. :"
    ws["A11"].font = f11b
    ws.merge_cells("B11:D11")
    ws["B11"] = "{{REF_NO}}"
    ws["E11"] = "Page :"
    ws["E11"].font = f11b
    ws.merge_cells("F11:H11")
    ws["F11"] = "{{PAGE_NO}} of {{PAGE_TOTAL}}"
    ws["F11"].alignment = right

    # 明細表
    ws.merge_cells("A13:A14")
    ws["A13"] = "ITEM NO."
    ws["A13"].font = f11b
    ws["A13"].alignment = center
    ws.merge_cells("B13:D14")
    ws["B13"] = "DESCRIPTION"
    ws["B13"].font = f11b
    ws["B13"].alignment = left
    ws.merge_cells("E13:E14")
    ws["E13"] = "QUANTITY/\nUNIT"
    ws["E13"].font = f11b
    ws["E13"].alignment = center
    ws.merge_cells("F13:F14")
    ws["F13"] = "UNIT PRICE"
    ws["F13"].font = f11b
    ws["F13"].alignment = right
    ws.merge_cells("G13:H14")
    ws["G13"] = "AMOUNT (HKD)"
    ws["G13"].font = f11b
    ws["G13"].alignment = right
    for c in ("A13", "B13", "E13", "F13", "G13"):
        ws[c].fill = fill

    start = 15
    for i in range(20):
        r = start + i
        ws[f"A{r}"] = f"{{{{TRX.ITEM_NO[{i}]}}}}"
        ws.merge_cells(f"B{r}:D{r}")
        ws[f"B{r}"] = f"{{{{TRX.STK_DESC[{i}]}}}}"
        ws[f"E{r}"] = f"{{{{TRX.QTY[{i}]}}}} {{TRX.UNIT_CODE[{i}]}}"
        ws[f"F{r}"] = f"{{{{TRX.UNIT_PRICE[{i}]}}}}"
        ws.merge_cells(f"G{r}:H{r}")
        ws[f"G{r}"] = f"{{{{TRX.AMOUNT[{i}]}}}}"
        ws[f"A{r}"].alignment = center
        ws[f"B{r}"].alignment = left
        ws[f"E{r}"].alignment = right
        ws[f"F{r}"].alignment = right
        ws[f"G{r}"].alignment = right

    total_r = start + 20
    ws.merge_cells(f"A{total_r}:F{total_r}")
    ws[f"A{total_r}"] = "Total Amount (HKD)"
    ws[f"A{total_r}"].font = f11b
    ws[f"A{total_r}"].alignment = right
    ws.merge_cells(f"G{total_r}:H{total_r}")
    ws[f"G{total_r}"] = "{{NET_AMT}}"
    ws[f"G{total_r}"].font = f11b
    ws[f"G{total_r}"].alignment = right

    ws.merge_cells(f"A{total_r+2}:H{total_r+4}")
    ws[f"A{total_r+2}"] = "Remark : {{REMARK}}"
    ws[f"A{total_r+2}"].alignment = top

    ws.merge_cells(f"A{total_r+6}:H{total_r+8}")
    ws[f"A{total_r+6}"] = (
        "Please make cheque payable to \"Wo Lee Green Solutions Ltd\"\n"
        "支票抬頭請寫「和利綠色動力有限公司」並加橫線\n"
        "恒生銀行戶口號碼: 263-158396-001\n"
        "E.& O. E."
    )
    ws[f"A{total_r+6}"].alignment = top

    _set_border(ws, 13, 1, total_r, 8)
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = False
    ws.print_title_rows = "1:14"

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

