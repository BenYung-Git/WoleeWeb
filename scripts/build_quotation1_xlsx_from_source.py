"""
由現有 Quotation1.xls 產生可填值的 Quotation1.xlsx 模板（保留原樣式/LOGO），
並寫入 QUOTATION + QUOTTRX 的 token。
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "TEMPLATES" / "Quotation1.xlsx"


def _source_candidates() -> list[Path]:
    env = (os.environ.get("WOLEE_QUOTATION1_SOURCE") or "").strip()
    out: list[Path] = []
    if env:
        out.append(Path(env))
    out.extend(
        [
            Path(r"D:\AI\WOLEE\Quotation1.xls"),
            Path(r"D:\AI\Wolee\Quotation1.xls"),
            ROOT / "Quotation1.xls",
            Path(r"D:\AI\WOLEE\Quotation1.xlsx"),
            Path(r"D:\AI\Wolee\Quotation1.xlsx"),
            ROOT / "Quotation1.xlsx",
        ]
    )
    return out


def _convert_to_xlsx(src: Path, dst: Path) -> None:
    ext = src.suffix.lower()
    if ext == ".xlsx":
        shutil.copy2(src, dst)
        return
    try:
        import win32com.client  # type: ignore[import-untyped]
    except ImportError as e:
        raise RuntimeError("需要 pywin32 才能將 .xls 轉 .xlsx") from e
    excel = win32com.client.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    wb = None
    try:
        wb = excel.Workbooks.Open(str(src))
        # 51 = xlOpenXMLWorkbook (.xlsx)
        wb.SaveAs(str(dst), FileFormat=51)
    finally:
        if wb is not None:
            wb.Close(SaveChanges=False)
        excel.Quit()


def _set_tokens(ws) -> None:
    def put(addr: str, value: str) -> None:
        # 若 addr 在合併儲存格內，寫入其左上角儲存格。
        for rg in ws.merged_cells.ranges:
            if addr in rg:
                ws.cell(rg.min_row, rg.min_col).value = value
                return
        ws[addr] = value

    # Header / master fields (QUOTATION)
    put("G12", "{{CUST_NAME}}")
    put("AB12", "{{TX_NO}}")
    put("G14", "{{ATTN}}")
    put("N14", "{{TEL}}")
    put("AB14", "{{DATE}}")
    put("G16", "{{EMAIL}}")
    put("AB16", "{{REF_NO}}")
    put("G18", "{{SALE_NAME}}")
    put("N18", "{{SALE_TEL}}")
    put("G20", "{{PRJ_KEY}}")
    put("AB20", "{{PAGE_NO}}")
    put("AF20", "{{PAGE_TOTAL}}")

    # Detail rows (QUOTTRX) - preserve style by editing values only
    start_row = 27
    max_rows = 18
    for i in range(max_rows):
        r = start_row + i
        put(f"C{r}", f"{{{{TRX.ITEM_NO[{i}]}}}}")
        put(f"G{r}", f"{{{{TRX.STK_DESC[{i}]}}}}")
        put(f"Q{r}", f"{{{{TRX.QTY[{i}]}}}}")
        put(f"T{r}", f"{{{{TRX.UNIT_CODE[{i}]}}}}")
        put(f"Y{r}", f"{{{{TRX.UNIT_PRICE[{i}]}}}}")
        put(f"AE{r}", f"{{{{TRX.AMOUNT[{i}]}}}}")

    # Totals / footer
    put("AE29", "{{NET_AMT}}")
    put("C32", "{{REMARK}}")
    put("C36", "{{TERMS}}")
    put("C42", "{{VALIDITY_TERMS}}")


def main() -> int:
    src = next((p for p in _source_candidates() if p.is_file()), None)
    if src is None:
        print("找不到 Quotation1.xls / Quotation1.xlsx 來源檔。", file=sys.stderr)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(suffix=".xlsx", prefix="wolee_q1_tpl_")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        _convert_to_xlsx(src, tmp)
        wb = openpyxl.load_workbook(tmp)
        ws = wb[wb.sheetnames[0]]
        _set_tokens(ws)
        wb.save(OUT)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
    print(f"Wrote {OUT} from {src}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

