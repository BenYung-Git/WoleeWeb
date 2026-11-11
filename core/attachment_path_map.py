from __future__ import annotations

import json
import os
import re
import sys
from typing import List, Tuple

_WIN_DRIVE_RE = re.compile(r"^[A-Za-z]:[/\\]")


def is_attach_path_absolute(path: str) -> bool:
    """Windows 磁碟路徑 Q:\\... 在 Linux 也視為絕對路徑（稍後做對應轉換）。"""
    p = (path or "").strip()
    if not p:
        return False
    if os.path.isabs(p):
        return True
    return bool(_WIN_DRIVE_RE.match(p.replace("/", "\\")))


def _norm_path_key(path: str) -> str:
    return path.replace("\\", "/").rstrip("/").lower()


def _strip_win_drive(path: str) -> str | None:
    """去掉 Windows 磁碟代號，回傳其餘路徑（/ 分隔、小寫）；非磁碟路徑則 None。"""
    p = (path or "").replace("\\", "/").strip()
    if len(p) >= 2 and p[1] == ":" and p[0].isalpha():
        return p[2:].lstrip("/").lower()
    return None


def _load_mappings_from_json(app_base_dir: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for name in ("attachment_path_map.json", "ATTACHMENT_PATH_MAP.json"):
        fp = os.path.join(app_base_dir, name)
        if not os.path.isfile(fp):
            continue
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        items = data.get("mappings", data) if isinstance(data, dict) else data
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            src = (item.get("from") or item.get("windows") or "").strip()
            dst = (item.get("to") or item.get("linux") or "").strip()
            if src and dst:
                out.append((src, dst))
        if out:
            break
    return out


def _load_mappings_from_env() -> List[Tuple[str, str]]:
    """WOLEE_ATTACH_MAP=Q:\\docBiz=/srv/docBiz;D:\\x=/mnt/x"""
    raw = (os.environ.get("WOLEE_ATTACH_MAP") or "").strip()
    if not raw:
        return []
    out: List[Tuple[str, str]] = []
    for part in raw.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        src, _, dst = part.partition("=")
        src, dst = src.strip(), dst.strip()
        if src and dst:
            out.append((src, dst))
    return out


def load_attachment_path_mappings(app_base_dir: str) -> List[Tuple[str, str]]:
    seen = set()
    merged: List[Tuple[str, str]] = []
    for src, dst in _load_mappings_from_env() + _load_mappings_from_json(app_base_dir):
        key = (_norm_path_key(src), _norm_path_key(dst))
        if key in seen:
            continue
        seen.add(key)
        merged.append((src, dst))
    return merged


def _join_mapped(dst: str, suffix: str) -> str:
    if suffix:
        return os.path.normpath(os.path.join(dst, suffix.replace("/", os.sep)))
    return os.path.normpath(dst)


def apply_attachment_path_mappings(path: str, app_base_dir: str) -> str:
    """
    將 Windows 路徑（如 Q:\\docBiz\\...、S:\\docBiz\\...）對應到 Linux 掛載點。
    僅在非 Windows 環境套用（Ubuntu Web 伺服器）；桌面版維持原路徑。
    設定方式（擇一）：
      - 環境變數 WOLEE_ATTACH_MAP=Q:\\docBiz=/srv/docBiz
      - 專案根目錄 attachment_path_map.json

    若精確前綴未命中，會再以「去掉磁碟代號後」比對（Q: 與 S: 指向同一 docBiz 時只需一筆對應）。
    """
    p = (path or "").strip()
    if not p:
        return p
    if sys.platform == "win32":
        return p
    mappings = load_attachment_path_mappings(app_base_dir)
    if not mappings:
        return p
    p_key = _norm_path_key(p)
    for src, dst in mappings:
        sk = _norm_path_key(src)
        if not p_key.startswith(sk):
            continue
        rest = p.replace("\\", "/")
        sk_slash = src.replace("\\", "/").rstrip("/")
        if rest.lower().startswith(sk_slash.lower()):
            suffix = rest[len(sk_slash) :].lstrip("/\\")
        else:
            suffix = ""
        return _join_mapped(dst, suffix)

    # 磁碟代號不同但其餘路徑相同：S:\docBiz\... ↔ 對應表 Q:\docBiz
    p_rest = _strip_win_drive(p)
    if p_rest is not None:
        for src, dst in mappings:
            src_rest = _strip_win_drive(src)
            if not src_rest:
                continue
            if p_rest == src_rest or p_rest.startswith(src_rest + "/"):
                suffix = p_rest[len(src_rest) :].lstrip("/")
                return _join_mapped(dst, suffix)
    return p
