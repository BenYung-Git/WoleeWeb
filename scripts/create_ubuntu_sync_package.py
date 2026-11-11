#!/usr/bin/env python3
"""打包 Web 附件／其他按鈕修復所需檔案，供 Ubuntu 下載同步。"""
from __future__ import annotations

import os
import zipfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FILES = (
    "web/static/app.js",
    "web/static/index.html",
    "api/schemas.py",
    "api/server.py",
    "services/app_service.py",
    "core/data_dictionary.py",
    "core/attachment_service.py",
    "core/attachment_path_map.py",
    "attachment_path_map.json.example",
    "scripts/debug_work_actions.py",
)

OUT_DIR = os.path.join(os.path.dirname(__file__), "ubuntu_sync_out")
ZIP_PATH = os.path.join(OUT_DIR, "ubuntu_web_sync.zip")


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in FILES:
            src = os.path.join(_ROOT, rel.replace("/", os.sep))
            if not os.path.isfile(src):
                raise SystemExit(f"缺少檔案: {rel}")
            zf.write(src, rel.replace("\\", "/"))
    print(ZIP_PATH)
    print("files:", len(FILES))


if __name__ == "__main__":
    main()
