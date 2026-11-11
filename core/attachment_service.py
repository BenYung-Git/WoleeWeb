from __future__ import annotations

import os
import re
from typing import List, Optional, Sequence, Tuple

from core.attachment_path_map import (
    apply_attachment_path_mappings,
    is_attach_path_absolute,
)

ATTACHMENT_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".jpg",
        ".jpeg",
        ".tif",
        ".tiff",
        ".bmp",
        ".png",
        ".gif",
        ".webp",
    }
)


def resolve_attach_lookup_column(attach_key: str, key_code: str) -> str:
    """ATTACH_KEY 非空白用其欄名；否則用 KEY_CODE 欄名。"""
    ak = (attach_key or "").strip()
    if ak:
        return ak
    return (key_code or "").strip()


def physical_field_index(physical_fields: Sequence[str], column_name: str) -> Optional[int]:
    target = (column_name or "").strip().upper()
    if not target:
        return None
    for i, name in enumerate(physical_fields):
        if (name or "").strip().upper() == target:
            return i
    return None


def field_value_from_row(
    row: Sequence[str],
    physical_fields: Sequence[str],
    column_name: str,
) -> str:
    idx = physical_field_index(physical_fields, column_name)
    if idx is None or idx >= len(row):
        return ""
    return (row[idx] or "").strip()


def resolve_attachment_folder(
    attach_path_template: str,
    *,
    key_value: str,
    co_key: str = "",
    do_proc: str = "",
    table_name: str = "",
    app_base_dir: str = "",
) -> str:
    """將 PROGRAM.ATTACH_PATH 樣板展開為實體目錄。"""
    template = (attach_path_template or "").strip() or "ATTACHMENT"
    path = template
    for token, val in (
        ("{KEY}", key_value),
        ("{CO_KEY}", co_key),
        ("{DO_PROC}", do_proc),
        ("{TABLE}", table_name),
    ):
        path = path.replace(token, val)
    if not is_attach_path_absolute(path):
        base = (app_base_dir or "").strip() or os.getcwd()
        path = os.path.join(base, path)
    else:
        path = os.path.normpath(path)
    base = (app_base_dir or "").strip() or os.getcwd()
    path = apply_attachment_path_mappings(path, base)
    return os.path.normpath(path)


def _normalize_key(key_value: str) -> str:
    return re.sub(r"\s+", "", (key_value or "").strip().upper())


def attachment_filename_matches(filename: str, key_value: str) -> bool:
    """檔名（含副檔名）須含鍵值，且為支援之圖形／PDF 副檔名。"""
    kv = _normalize_key(key_value)
    if not kv:
        return False
    name = os.path.basename(filename)
    stem, ext = os.path.splitext(name)
    if ext.lower() not in ATTACHMENT_EXTENSIONS:
        return False
    stem_u = re.sub(r"\s+", "", stem.upper())
    name_u = re.sub(r"\s+", "", name.upper())
    if stem_u == kv:
        return True
    if kv in name_u:
        return True
    return False


def find_attachment_files(folder: str, key_value: str) -> List[str]:
    """在 ATTACH_PATH 目錄尋找檔名符合鍵值之附件（不遞迴子目錄）。"""
    kv = (key_value or "").strip()
    if not kv or not folder:
        return []
    if not os.path.isdir(folder):
        return []
    hits: List[str] = []
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    for name in names:
        full = os.path.join(folder, name)
        if not os.path.isfile(full):
            continue
        if attachment_filename_matches(full, kv):
            hits.append(full)
    hits.sort(key=lambda p: os.path.basename(p).upper())
    return hits


def is_pdf_path(path: str) -> bool:
    return os.path.splitext(path)[1].lower() == ".pdf"


def is_image_path(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in {
        ".jpg",
        ".jpeg",
        ".tif",
        ".tiff",
        ".bmp",
        ".png",
        ".gif",
        ".webp",
    }


def resolve_attachments_for_row(
    attach_path_template: str,
    attach_key_column: str,
    key_code_column: str,
    physical_fields: Sequence[str],
    row: Sequence[str],
    *,
    co_key: str = "",
    do_proc: str = "",
    table_name: str = "",
    app_base_dir: str = "",
) -> Tuple[str, str, str, List[str]]:
    """
    回傳 (lookup_column, key_value, folder, matched_files)。
    lookup_column 為實際用來比對檔名之欄位名。
    """
    lookup = resolve_attach_lookup_column(attach_key_column, key_code_column)
    key_value = field_value_from_row(row, physical_fields, lookup)
    folder = resolve_attachment_folder(
        attach_path_template,
        key_value=key_value,
        co_key=co_key,
        do_proc=do_proc,
        table_name=table_name,
        app_base_dir=app_base_dir,
    )
    files = find_attachment_files(folder, key_value)
    return lookup, key_value, folder, files
