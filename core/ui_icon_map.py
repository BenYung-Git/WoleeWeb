"""桌面 UI 圖示 — QStyle.StandardPixmap 集中對應（作業按鈕、選單、資料庫工具等）。

Web 對應鍵名與 SVG：web/static/ui-icons.js（ICON_MAP_KEYS / ICONS）。
"""
from __future__ import annotations

from typing import Dict

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QStyle

ICON_MAP: Dict[str, QStyle.StandardPixmap] = {
    "alter_structure": QStyle.StandardPixmap.SP_FileDialogDetailedView,
    "create_table": QStyle.StandardPixmap.SP_FileDialogNewFolder,
    "copy_table": QStyle.StandardPixmap.SP_DialogSaveButton,
    "delete_table": QStyle.StandardPixmap.SP_TrashIcon,
    "rename_table": QStyle.StandardPixmap.SP_FileDialogContentsView,
    "convert_db": QStyle.StandardPixmap.SP_BrowserReload,
    "add": QStyle.StandardPixmap.SP_FileDialogNewFolder,
    "edit": QStyle.StandardPixmap.SP_FileDialogDetailedView,
    "delete": QStyle.StandardPixmap.SP_TrashIcon,
    "copy": QStyle.StandardPixmap.SP_DialogSaveButton,
    "print": QStyle.StandardPixmap.SP_FileDialogInfoView,
    "exit": QStyle.StandardPixmap.SP_DialogCloseButton,
    "save": QStyle.StandardPixmap.SP_DialogSaveButton,
    "cancel": QStyle.StandardPixmap.SP_DialogCancelButton,
    "search": QStyle.StandardPixmap.SP_FileDialogContentsView,
    "filter": QStyle.StandardPixmap.SP_FileDialogListView,
    "connect": QStyle.StandardPixmap.SP_DriveNetIcon,
    "table": QStyle.StandardPixmap.SP_FileIcon,
    "database": QStyle.StandardPixmap.SP_DriveHDIcon,
    "theme": QStyle.StandardPixmap.SP_DesktopIcon,
    "menu": QStyle.StandardPixmap.SP_TitleBarMenuButton,
    "language": QStyle.StandardPixmap.SP_ComputerIcon,
    "attachment": QStyle.StandardPixmap.SP_FileLinkIcon,
    "other": QStyle.StandardPixmap.SP_DialogHelpButton,
    "ai": QStyle.StandardPixmap.SP_MessageBoxInformation,
}

_DEFAULT_SP = QStyle.StandardPixmap.SP_ComputerIcon


def standard_pixmap_for(icon_key: str) -> QStyle.StandardPixmap:
    return ICON_MAP.get(icon_key, _DEFAULT_SP)


def icon_from_key(style: QStyle, icon_key: str) -> QIcon:
    return style.standardIcon(standard_pixmap_for(icon_key))
