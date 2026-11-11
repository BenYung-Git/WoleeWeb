#!/usr/bin/env python3
"""診斷附件路徑：PROGRAM.ATTACH_PATH → 實際 Linux 目錄。"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from core.attachment_path_map import load_attachment_path_mappings
from core.attachment_service import find_attachment_files, resolve_attachment_folder
from core.auth import resolve_sys_data_path
from core.menu_loader import ProgramRepository


def main() -> None:
    base = _ROOT
    do_proc = (sys.argv[1] if len(sys.argv) > 1 else "Purchase").strip()
    key = (sys.argv[2] if len(sys.argv) > 2 else "").strip()

    print("WoleeWeb:", base)
    print("DO_PROC:", do_proc)
    print()

    maps = load_attachment_path_mappings(base)
    if maps:
        print("attachment_path_map:")
        for a, b in maps:
            print(f"  {a!r} -> {b!r}")
    else:
        print("[警告] 未設定 attachment_path_map.json 或 WOLEE_ATTACH_MAP")
        print("  Linux 無法讀取 Q:\\，請建立 attachment_path_map.json")
    print()

    mdb = resolve_sys_data_path(base)
    repo = ProgramRepository(mdb)
    repo.load()
    prg = repo.find_program_item(do_proc)
    if not prg:
        print(f"找不到 PROGRAM: {do_proc}")
        return
    attach_path = (prg.attach_path or "").strip()
    print("PROGRAM.ATTACH_PATH:", repr(attach_path))
    print("KEY_CODE:", repr(prg.key_code))
    print()

    folder = resolve_attachment_folder(
        attach_path,
        key_value=key or "TEST",
        co_key="GS",
        do_proc=do_proc,
        app_base_dir=base,
    )
    print("解析後目錄:", folder)
    print("目錄存在:", os.path.isdir(folder))
    if os.path.isdir(folder):
        try:
            names = sorted(os.listdir(folder))[:10]
            print("目錄內前 10 項:", names)
        except OSError as exc:
            print("無法列出目錄:", exc)
    print()

    if key:
        hits = find_attachment_files(folder, key)
        print(f"符合鍵值 {key!r} 的附件:", len(hits))
        for h in hits[:5]:
            print(" ", h)
    else:
        print("提示: 加上 TX_KEY 測試，例如:")
        print(f"  python3 scripts/diagnose_attachments.py {do_proc} GS-000092")


if __name__ == "__main__":
    main()
