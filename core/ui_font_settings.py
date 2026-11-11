"""Grid／輸入表單字體大小（pt）— 桌面與 Web 共用預設與持久化。"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Optional

_MIN_PT = 6
_MAX_PT = 28

_DEFAULT_GRID_CELL = 10
_DEFAULT_GRID_HEADER = 11
_DEFAULT_FORM_LABEL = 12
_DEFAULT_FORM_EDITOR = 11


@dataclass
class UiFontSettings:
    grid_cell_pt: int = _DEFAULT_GRID_CELL
    grid_header_pt: int = _DEFAULT_GRID_HEADER
    form_label_pt: int = _DEFAULT_FORM_LABEL
    form_editor_pt: int = _DEFAULT_FORM_EDITOR

    def clamp(self) -> None:
        self.grid_cell_pt = _clamp_pt(self.grid_cell_pt, _DEFAULT_GRID_CELL)
        self.grid_header_pt = _clamp_pt(self.grid_header_pt, _DEFAULT_GRID_HEADER)
        self.form_label_pt = _clamp_pt(self.form_label_pt, _DEFAULT_FORM_LABEL)
        self.form_editor_pt = _clamp_pt(self.form_editor_pt, _DEFAULT_FORM_EDITOR)

    def bump_grid(self, delta: int) -> None:
        self.grid_cell_pt = _clamp_pt(self.grid_cell_pt + delta, _DEFAULT_GRID_CELL)
        self.grid_header_pt = _clamp_pt(self.grid_header_pt + delta, _DEFAULT_GRID_HEADER)

    def bump_form(self, delta: int) -> None:
        self.form_label_pt = _clamp_pt(self.form_label_pt + delta, _DEFAULT_FORM_LABEL)
        self.form_editor_pt = _clamp_pt(self.form_editor_pt + delta, _DEFAULT_FORM_EDITOR)


def _clamp_pt(value: int, default: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(_MIN_PT, min(_MAX_PT, v))


def settings_file_path(base_dir: str) -> str:
    return os.path.join(os.path.abspath(base_dir), "ui_font_settings.json")


def load_ui_font_settings(base_dir: Optional[str] = None) -> UiFontSettings:
    s = UiFontSettings()
    if not base_dir:
        s.clamp()
        return s
    path = settings_file_path(base_dir)
    if not os.path.isfile(path):
        s.clamp()
        return s
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            s = UiFontSettings(
                grid_cell_pt=int(raw.get("grid_cell_pt", _DEFAULT_GRID_CELL)),
                grid_header_pt=int(raw.get("grid_header_pt", _DEFAULT_GRID_HEADER)),
                form_label_pt=int(raw.get("form_label_pt", _DEFAULT_FORM_LABEL)),
                form_editor_pt=int(raw.get("form_editor_pt", _DEFAULT_FORM_EDITOR)),
            )
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        s = UiFontSettings()
    s.clamp()
    return s


def save_ui_font_settings(base_dir: str, settings: UiFontSettings) -> None:
    settings.clamp()
    path = settings_file_path(base_dir)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(settings), f, ensure_ascii=False, indent=2)
    except OSError:
        pass


# 程序內快取（桌面 WorkPage 熱更新）
_cached: Optional[UiFontSettings] = None
_cached_base: Optional[str] = None


def get_ui_font_settings(base_dir: Optional[str] = None) -> UiFontSettings:
    global _cached, _cached_base
    base = (base_dir or _cached_base or "").strip()
    if _cached is not None and (not base or _cached_base == base):
        return _cached
    _cached = load_ui_font_settings(base or None)
    if base:
        _cached_base = base
    return _cached


def set_ui_font_settings(base_dir: str, settings: UiFontSettings) -> UiFontSettings:
    global _cached, _cached_base
    settings.clamp()
    save_ui_font_settings(base_dir, settings)
    _cached = settings
    _cached_base = os.path.abspath(base_dir)
    return settings
