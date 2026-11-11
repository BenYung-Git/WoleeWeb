"""
將現有 Quotation1.xlsx 複製為專案內模板（不從 PDF / RPT 產生）。

來源優先順序：
  1) 環境變數 WOLEE_QUOTATION1_SOURCE（完整路徑）
  2) D:\\AI\\WOLEE\\Quotation1.xlsx
  3) D:\\AI\\Wolee\\Quotation1.xlsx
  4) 專案根目錄 Quotation1.xlsx

輸出：
  <專案根>/TEMPLATES/Quotation1.xlsx

執行： python scripts/build_quotation1_xlsx_from_rpt.py
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
OUT = _ROOT / "TEMPLATES" / "Quotation1.xlsx"


def _source_candidates() -> list[Path]:
    env = (os.environ.get("WOLEE_QUOTATION1_SOURCE") or "").strip()
    out: list[Path] = []
    if env:
        out.append(Path(env))
    out.extend(
        [
            Path(r"D:\AI\WOLEE\Quotation1.xlsx"),
            Path(r"D:\AI\Wolee\Quotation1.xlsx"),
            _ROOT / "Quotation1.xlsx",
        ]
    )
    return out


def main() -> int:
    src: Path | None = None
    for p in _source_candidates():
        if p.is_file():
            src = p
            break
    if src is None:
        print(
            "找不到來源 Quotation1.xlsx。\n"
            "請將檔案放在 D:\\AI\\WOLEE\\Quotation1.xlsx，\n"
            "或設定環境變數 WOLEE_QUOTATION1_SOURCE 指向完整路徑，\n"
            "或放在專案根目錄 Quotation1.xlsx。",
            file=sys.stderr,
        )
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, OUT)
    print(f"Copied\n  {src}\n-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
