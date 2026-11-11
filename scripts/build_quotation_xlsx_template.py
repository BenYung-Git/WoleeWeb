"""
產生 templates/Quotation.xlsx — 版面對齊專案內 quotation_print_template.html
（與常見 PRNQUOTATION / PrnQuotation 報價單結構一致）。

工作區內無法解析 Crystal .rpt 二進位；若您有 PrnQuotation.rpt，請將匯出的
版面截圖或欄位清單對照此模板再微調欄寬／合併範圍。

若存在下列檔案，會嵌入左上角 LOGO 區（需 Pillow 以支援 jpg/bmp）：
  templates/logo.jpg
  templates/logo.bmp

執行： python scripts/build_quotation_xlsx_template.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "templates" / "Quotation.xlsx"
TEMPLATES = ROOT / "templates"


def _thin() -> Side:
    return Side(style="thin", color="000000")


def _border_all() -> Border:
    t = _thin()
    return Border(left=t, right=t, top=t, bottom=t)


def _find_logo() -> Path | None:
    for name in ("logo.jpg", "logo.bmp", "LOGO.jpg", "LOGO.bmp"):
        p = TEMPLATES / name
        if p.is_file():
            return p
    return None


def main() -> int:
    wb = Workbook()
    ws = wb.active
    ws.title = "Quotation"

    for col, w in {
        "A": 10,
        "B": 12,
        "C": 12,
        "D": 12,
        "E": 11,
        "F": 12,
        "G": 11,
        "H": 12,
    }.items():
        ws.column_dimensions[col].width = w

    title_font = Font(name="Calibri", size=11)
    hdr_font = Font(name="Calibri", size=11, bold=True)
    big_title = Font(name="Calibri", size=20, bold=True)
    small_hdr = Font(name="Calibri", size=10)

    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center", wrap_text=True)
    wrap = Alignment(horizontal="left", vertical="top", wrap_text=True)
    hdr_fill = PatternFill("solid", fgColor="F2F2F2")
    b = _border_all()

    # ----- LOGO + 公司抬頭 -----
    ws.merge_cells("A1:B5")
    ws["A1"].value = "LOGO\n(放置 templates/logo.jpg 或 logo.bmp 後重建)"
    ws["A1"].font = Font(name="Calibri", size=9, italic=True, color="666666")
    ws["A1"].alignment = center
    for r in range(1, 6):
        ws.row_dimensions[r].height = 14.5

    for row_idx, placeholder in enumerate(
        [
            "{{company_header_en}}",
            "{{company_header_zh}}",
            "{{company_contact}}",
            "{{company_email}}",
        ],
        start=1,
    ):
        ws.merge_cells(f"C{row_idx}:H{row_idx}")
        c = ws[f"C{row_idx}"]
        c.value = placeholder
        c.font = title_font
        c.alignment = left

    ws.merge_cells("A6:H6")
    ws["A6"] = "QUOTATION"
    ws["A6"].font = big_title
    ws["A6"].alignment = center
    ws.row_dimensions[6].height = 28

    def pair_row(
        r: int,
        l1: str,
        v1: str,
        l2: str,
        v2: str,
        v2_right: bool = False,
    ) -> None:
        ws[f"A{r}"] = l1
        ws[f"A{r}"].font = hdr_font
        ws[f"A{r}"].alignment = left
        ws.merge_cells(f"B{r}:D{r}")
        ws[f"B{r}"] = v1
        ws[f"B{r}"].font = title_font
        ws[f"B{r}"].alignment = left
        ws[f"E{r}"] = l2
        ws[f"E{r}"].font = hdr_font
        ws[f"E{r}"].alignment = left
        ws.merge_cells(f"F{r}:H{r}")
        ws[f"F{r}"] = v2
        ws[f"F{r}"].font = title_font
        ws[f"F{r}"].alignment = right if v2_right else left

    pair_row(8, "Company :", "{{customer_name}}", "Quotation No. :", "{{quotation_no}}", True)
    pair_row(9, "Attention :", "{{attention}}", "Tel:", "{{customer_tel}}")
    ws["A10"] = "Email :"
    ws["A10"].font = hdr_font
    ws.merge_cells("B10:D10")
    ws["B10"] = "{{customer_email}}"
    ws["B10"].font = title_font
    ws["E10"] = "Date :"
    ws["E10"].font = hdr_font
    ws.merge_cells("F10:H10")
    ws["F10"] = "{{quote_date}}"
    ws["F10"].font = title_font
    ws["F10"].alignment = right
    pair_row(11, "Ref. No. :", "{{ref_no}}", "Prepared by :", "{{prepared_by}}")
    pair_row(12, "Tel:", "{{prepared_tel}}", "Project:", "{{project_name}}")
    ws.merge_cells("A13:H13")
    ws["A13"] = "Page : 1 of 1"
    ws["A13"].font = title_font
    ws["A13"].alignment = right

    intro_r = 14
    ws.merge_cells(f"A{intro_r}:H{intro_r}")
    ws[f"A{intro_r}"] = (
        "Thank you for your enquiry. We are pleased to submit our quotation "
        "for the below works as follow:"
    )
    ws[f"A{intro_r}"].font = title_font
    ws[f"A{intro_r}"].alignment = left

    # ----- 明細表（雙列標題，與 HTML 一致）-----
    r_top, r_sub = 16, 17
    ws.merge_cells(f"A{r_top}:A{r_sub}")
    c = ws[f"A{r_top}"]
    c.value = "Item No."
    c.font = hdr_font
    c.alignment = center
    c.fill = hdr_fill
    c.border = b

    ws.merge_cells(f"B{r_top}:D{r_top}")
    c = ws[f"B{r_top}"]
    c.value = "Description"
    c.font = hdr_font
    c.alignment = left
    c.fill = hdr_fill
    c.border = b
    ws.merge_cells(f"B{r_sub}:D{r_sub}")
    c = ws[f"B{r_sub}"]
    c.value = ""
    c.font = small_hdr
    c.fill = hdr_fill
    c.border = b

    ws.merge_cells(f"E{r_top}:E{r_sub}")
    c = ws[f"E{r_top}"]
    c.value = "Quantity\n(Unit)"
    c.font = hdr_font
    c.alignment = center
    c.fill = hdr_fill
    c.border = b

    ws.merge_cells(f"F{r_top}:F{r_sub}")
    c = ws[f"F{r_top}"]
    c.value = "Unit Price\n(HKD)"
    c.font = hdr_font
    c.alignment = right
    c.fill = hdr_fill
    c.border = b

    ws.merge_cells(f"G{r_top}:H{r_top}")
    c = ws[f"G{r_top}"]
    c.value = "Amount"
    c.font = hdr_font
    c.alignment = right
    c.fill = hdr_fill
    c.border = b
    ws.merge_cells(f"G{r_sub}:H{r_sub}")
    c = ws[f"G{r_sub}"]
    c.value = "(HKD)"
    c.font = small_hdr
    c.alignment = right
    c.fill = hdr_fill
    c.border = b

    first_data = r_sub + 1
    for i in range(15):
        rr = first_data + i
        ws.merge_cells(f"B{rr}:D{rr}")
        ws[f"A{rr}"] = "" if i > 0 else "1"
        ws[f"B{rr}"] = "{{item_desc}}" if i == 0 else ""
        ws[f"E{rr}"] = "{{qty}}" if i == 0 else ""
        ws[f"F{rr}"] = "{{unit_price}}" if i == 0 else ""
        ws.merge_cells(f"G{rr}:H{rr}")
        ws[f"G{rr}"] = "{{amount}}" if i == 0 else ""
        for addr in (f"A{rr}", f"B{rr}", f"E{rr}", f"F{rr}", f"G{rr}"):
            cell = ws[addr]
            cell.font = title_font
            cell.border = b
            if addr.startswith("A"):
                cell.alignment = center
            elif addr.startswith("E") or addr.startswith("F") or addr.startswith("G"):
                cell.alignment = right
            else:
                cell.alignment = left

    total_r = first_data + 15
    ws.merge_cells(f"A{total_r}:F{total_r}")
    ws[f"A{total_r}"] = "Total Amount (HKD)"
    ws[f"A{total_r}"].font = hdr_font
    ws[f"A{total_r}"].alignment = right
    ws[f"A{total_r}"].border = b
    ws.merge_cells(f"G{total_r}:H{total_r}")
    ws[f"G{total_r}"] = "{{total_amount}}"
    ws[f"G{total_r}"].font = hdr_font
    ws[f"G{total_r}"].alignment = right
    ws[f"G{total_r}"].border = b

    def block(r: int, label: str, placeholder: str) -> None:
        ws.merge_cells(f"A{r}:H{r}")
        ws[f"A{r}"] = label
        ws[f"A{r}"].font = hdr_font
        ws[f"A{r}"].alignment = left
        ws.merge_cells(f"A{r + 1}:H{r + 4}")
        c2 = ws[f"A{r + 1}"]
        c2.value = placeholder
        c2.font = title_font
        c2.alignment = wrap

    rr = total_r + 2
    block(rr, "Remark :", "{{remark}}")
    rr += 6
    block(rr, "Terms of Payment:", "{{terms_of_payment}}")
    rr += 6
    block(rr, "Validity:", "{{validity_terms}}")

    sig = rr + 6
    ws.merge_cells(f"A{sig}:D{sig + 8}")
    ws[f"A{sig}"] = (
        "Yours faithfully,\n\nFor and on behalf of\n"
        "{{sign_company_en}}\n{{sign_company_zh}}\n\n\n"
        "______________________________\nAuthorized Signature with Company Chop"
    )
    ws[f"A{sig}"].font = title_font
    ws[f"A{sig}"].alignment = left
    ws.merge_cells(f"E{sig}:H{sig + 8}")
    ws[f"E{sig}"] = (
        "\nFor and on behalf of\n{{customer_name}}\n\n\n"
        "______________________________\nAuthorized Signature with Company Chop"
    )
    ws[f"E{sig}"].font = title_font
    ws[f"E{sig}"].alignment = left

    logo = _find_logo()
    if logo:
        try:
            from openpyxl.drawing.image import Image as XLImage

            img = XLImage(str(logo))
            img.width = 110
            img.height = int(img.height * (110 / max(img.width, 1)))
            ws.add_image(img, "A1")
            ws["A1"].value = None
        except Exception as e:
            print(f"[warn] 無法嵌入 LOGO ({logo}): {e}", file=sys.stderr)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
