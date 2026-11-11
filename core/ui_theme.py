"""UI 主題色票與樣式字串（桌面 PyQt6 + Web CSS 變數對齊）。"""

from __future__ import annotations

from typing import Dict, Optional, Sequence

THEME_NAMES = (
    "fusion_blue",
    "soft_green",
    "soft_purple",
    "warm_gray",
    "mint",
    "daylight",
)

# 分頁標題輪替色（每 TAB 不同顏色）
TAB_TITLE_COLORS: Sequence[str] = (
    "#1B4F72",  # 深藍
    "#117A65",  # 青綠
    "#9A7D0A",  # 橄欖
    "#922B21",  # 暗紅
    "#5B2C6F",  # 紫
    "#1A5276",  # 鋼藍
    "#B9770E",  # 琥珀
    "#196F3D",  # 綠
    "#6C3483",  # 堇紫
    "#A04000",  # 赭
)

_current_theme: str = "fusion_blue"


def tab_title_color(index: int) -> str:
    """依分頁序回傳標題色（循環）。"""
    if not TAB_TITLE_COLORS:
        return "#1B3B6F"
    i = int(index) if index is not None else 0
    return TAB_TITLE_COLORS[i % len(TAB_TITLE_COLORS)]


def apply_tab_title_colors(tab_widget) -> None:
    """為 QTabWidget 各分頁標題套用不同顏色。"""
    if tab_widget is None:
        return
    try:
        from PyQt6.QtGui import QColor

        bar = tab_widget.tabBar()
        for i in range(tab_widget.count()):
            bar.setTabTextColor(i, QColor(tab_title_color(i)))
    except Exception:
        pass


def _entry(
    *,
    bg: str,
    fg: str,
    menu_bg: str,
    toolbar_bg: str,
    status_bg: str,
    input_bg: str,
    border: str,
    accent: str,
    btn_g1: str,
    btn_g2: str,
    btn_h1: str,
    btn_h2: str,
    surface_g0: str,
    surface_g1: str,
    surface_g2: str,
    surface_border: str,
    surface_text: str,
    grid_sel_bg: str,
    tab_sel_mid: str,
    tab_sel_end: str,
    wa_g0: str,
    wa_g1: str,
    wa_g2: str,
    wa_border: str,
    wa_text: str,
    wa_h0: str,
    wa_h1: str,
    wa_h2: str,
    wa_p0: str,
    wa_p1: str,
    wa_p2: str,
    wp_g0: str,
    wp_g1: str,
    wp_g2: str,
    wp_border: str,
    nav_g0: str,
    nav_g1: str,
    nav_g2: str,
    nav_border: str,
    nav_text: str,
) -> Dict[str, str]:
    return {
        "bg": bg,
        "fg": fg,
        "menu_bg": menu_bg,
        "toolbar_bg": toolbar_bg,
        "status_bg": status_bg,
        "input_bg": input_bg,
        "border": border,
        "accent": accent,
        "btn_g1": btn_g1,
        "btn_g2": btn_g2,
        "btn_h1": btn_h1,
        "btn_h2": btn_h2,
        "surface_g0": surface_g0,
        "surface_g1": surface_g1,
        "surface_g2": surface_g2,
        "surface_border": surface_border,
        "surface_text": surface_text,
        "grid_sel_bg": grid_sel_bg,
        "tab_sel_mid": tab_sel_mid,
        "tab_sel_end": tab_sel_end,
        "wa_g0": wa_g0,
        "wa_g1": wa_g1,
        "wa_g2": wa_g2,
        "wa_border": wa_border,
        "wa_text": wa_text,
        "wa_h0": wa_h0,
        "wa_h1": wa_h1,
        "wa_h2": wa_h2,
        "wa_p0": wa_p0,
        "wa_p1": wa_p1,
        "wa_p2": wa_p2,
        "wp_g0": wp_g0,
        "wp_g1": wp_g1,
        "wp_g2": wp_g2,
        "wp_border": wp_border,
        "nav_g0": nav_g0,
        "nav_g1": nav_g1,
        "nav_g2": nav_g2,
        "nav_border": nav_border,
        "nav_text": nav_text,
    }


THEMES: Dict[str, Dict[str, str]] = {
    "fusion_blue": _entry(
        bg="#f5f8ff",
        fg="#1f2933",
        menu_bg="#e4ecff",
        toolbar_bg="#e0e8ff",
        status_bg="#dde7ff",
        input_bg="#f3f7ff",
        border="#c5d4f2",
        accent="#4a90e2",
        btn_g1="#8fd3ff",
        btn_g2="#2494ff",
        btn_h1="#b2e5ff",
        btn_h2="#3ba9ff",
        surface_g0="#fbfdff",
        surface_g1="#e8f4ff",
        surface_g2="#c8e4fa",
        surface_border="#b8d8f0",
        surface_text="#0f2f5c",
        grid_sel_bg="#d9e8fc",
        tab_sel_mid="#eef4ff",
        tab_sel_end="#dce9ff",
        wa_g0="#f2f9ff",
        wa_g1="#b4dcff",
        wa_g2="#4eb0f5",
        wa_border="#5aa0e0",
        wa_text="#0f2f5c",
        wa_h0="#ffffff",
        wa_h1="#d4ecff",
        wa_h2="#78c8ff",
        wa_p0="#8ec4f0",
        wa_p1="#4a9ee0",
        wa_p2="#2f86c8",
        wp_g0="#eaf4ff",
        wp_g1="#d4e8ff",
        wp_g2="#b9d8fb",
        wp_border="#8eb4e0",
        nav_g0="#f0f6ff",
        nav_g1="#dce8ff",
        nav_g2="#c4d8f8",
        nav_border="#6b94d8",
        nav_text="#1a2d5c",
    ),
    "soft_green": _entry(
        bg="#f4fbf6",
        fg="#1f2933",
        menu_bg="#e6f5ea",
        toolbar_bg="#ddf0e3",
        status_bg="#d5ebdc",
        input_bg="#f6fbf8",
        border="#bedec7",
        accent="#3ba673",
        btn_g1="#9be7c4",
        btn_g2="#34a36c",
        btn_h1="#b7f1d4",
        btn_h2="#45b67b",
        surface_g0="#f8fcf9",
        surface_g1="#e6f5ea",
        surface_g2="#c8e6d0",
        surface_border="#bedec7",
        surface_text="#1a4d32",
        grid_sel_bg="#d5ebdc",
        tab_sel_mid="#eef8f1",
        tab_sel_end="#d5ebdc",
        wa_g0="#f0faf4",
        wa_g1="#9be7c4",
        wa_g2="#34a36c",
        wa_border="#2f8a5d",
        wa_text="#0d3d24",
        wa_h0="#ffffff",
        wa_h1="#c8f5dc",
        wa_h2="#5bc48f",
        wa_p0="#7fd4a8",
        wa_p1="#3ba673",
        wa_p2="#2f8a5d",
        wp_g0="#eaf8ef",
        wp_g1="#ddf0e3",
        wp_g2="#c5e6d0",
        wp_border="#9ed0b0",
        nav_g0="#f0faf4",
        nav_g1="#ddf0e3",
        nav_g2="#c5e6d0",
        nav_border="#3ba673",
        nav_text="#1a3d28",
    ),
    "soft_purple": _entry(
        bg="#f7f4ff",
        fg="#261c3f",
        menu_bg="#ebe3ff",
        toolbar_bg="#e3dafc",
        status_bg="#ddd3fb",
        input_bg="#f9f6ff",
        border="#cec0f4",
        accent="#7b61ff",
        btn_g1="#cfb8ff",
        btn_g2="#7a5cff",
        btn_h1="#ddcaff",
        btn_h2="#8b6cff",
        surface_g0="#faf8ff",
        surface_g1="#ebe3ff",
        surface_g2="#d8cff8",
        surface_border="#cec0f4",
        surface_text="#261c3f",
        grid_sel_bg="#ddd3fb",
        tab_sel_mid="#f3efff",
        tab_sel_end="#e3dafc",
        wa_g0="#f5f0ff",
        wa_g1="#cfb8ff",
        wa_g2="#7a5cff",
        wa_border="#6849e8",
        wa_text="#261c3f",
        wa_h0="#ffffff",
        wa_h1="#e8dcff",
        wa_h2="#9b84ff",
        wa_p0="#b8a0ff",
        wa_p1="#7b61ff",
        wa_p2="#6849e8",
        wp_g0="#f3efff",
        wp_g1="#e8dcff",
        wp_g2="#ddd3fb",
        wp_border="#b8a8f0",
        nav_g0="#f5f0ff",
        nav_g1="#e8dcff",
        nav_g2="#d8cff8",
        nav_border="#7b61ff",
        nav_text="#261c3f",
    ),
    "warm_gray": _entry(
        bg="#f7f5f2",
        fg="#27241d",
        menu_bg="#ece7df",
        toolbar_bg="#e4ddd3",
        status_bg="#ddd5c9",
        input_bg="#faf7f3",
        border="#c8bfb2",
        accent="#c17b3f",
        btn_g1="#f0c89b",
        btn_g2="#c17b3f",
        btn_h1="#f5d4ad",
        btn_h2="#d08a4a",
        surface_g0="#faf8f5",
        surface_g1="#ece7df",
        surface_g2="#ddd5c9",
        surface_border="#c8bfb2",
        surface_text="#3d2f1f",
        grid_sel_bg="#ddd5c9",
        tab_sel_mid="#f5f0ea",
        tab_sel_end="#e8dfd3",
        wa_g0="#faf3eb",
        wa_g1="#f0c89b",
        wa_g2="#c17b3f",
        wa_border="#a86832",
        wa_text="#3d2f1f",
        wa_h0="#ffffff",
        wa_h1="#f5dcc0",
        wa_h2="#d08a4a",
        wa_p0="#e0b080",
        wa_p1="#c17b3f",
        wa_p2="#a86832",
        wp_g0="#f5efe8",
        wp_g1="#ece4d8",
        wp_g2="#ddd5c9",
        wp_border="#c8b8a4",
        nav_g0="#faf3eb",
        nav_g1="#ece7df",
        nav_g2="#ddd5c9",
        nav_border="#c17b3f",
        nav_text="#3d2f1f",
    ),
    "mint": _entry(
        bg="#f4fffb",
        fg="#10362f",
        menu_bg="#e2f7f0",
        toolbar_bg="#daf2ea",
        status_bg="#d0ece3",
        input_bg="#f7fffb",
        border="#b7ded2",
        accent="#2ab3a6",
        btn_g1="#9ff7e9",
        btn_g2="#2ab3a6",
        btn_h1="#b4f9ee",
        btn_h2="#37c3b5",
        surface_g0="#f7fffc",
        surface_g1="#e2f7f0",
        surface_g2="#c8ebe2",
        surface_border="#b7ded2",
        surface_text="#10362f",
        grid_sel_bg="#d0ece3",
        tab_sel_mid="#eefaf6",
        tab_sel_end="#daf2ea",
        wa_g0="#f0fffb",
        wa_g1="#9ff7e9",
        wa_g2="#2ab3a6",
        wa_border="#229388",
        wa_text="#10362f",
        wa_h0="#ffffff",
        wa_h1="#c8faf2",
        wa_h2="#5ed4c8",
        wa_p0="#6dd8cc",
        wa_p1="#2ab3a6",
        wa_p2="#229388",
        wp_g0="#eafaf5",
        wp_g1="#daf2ea",
        wp_g2="#c8ebe2",
        wp_border="#8fd4c8",
        nav_g0="#f0fffb",
        nav_g1="#daf2ea",
        nav_g2="#c8ebe2",
        nav_border="#2ab3a6",
        nav_text="#10362f",
    ),
    "daylight": _entry(
        bg="#fffef5",
        fg="#332a07",
        menu_bg="#f9f4dd",
        toolbar_bg="#f3eccf",
        status_bg="#ece3c3",
        input_bg="#fffdf2",
        border="#ddd0a6",
        accent="#f2b600",
        btn_g1="#ffe48a",
        btn_g2="#f2b600",
        btn_h1="#ffeaa6",
        btn_h2="#ffc533",
        surface_g0="#fffef8",
        surface_g1="#f9f4dd",
        surface_g2="#ece3c3",
        surface_border="#ddd0a6",
        surface_text="#332a07",
        grid_sel_bg="#ece3c3",
        tab_sel_mid="#fff8e8",
        tab_sel_end="#f3eccf",
        wa_g0="#fff8e0",
        wa_g1="#ffe48a",
        wa_g2="#f2b600",
        wa_border="#d9a300",
        wa_text="#332a07",
        wa_h0="#ffffff",
        wa_h1="#fff0b8",
        wa_h2="#ffc533",
        wa_p0="#f5d060",
        wa_p1="#f2b600",
        wa_p2="#d9a300",
        wp_g0="#fff8e8",
        wp_g1="#f3eccf",
        wp_g2="#ece3c3",
        wp_border="#d9c88a",
        nav_g0="#fff8e0",
        nav_g1="#f3eccf",
        nav_g2="#ece3c3",
        nav_border="#f2b600",
        nav_text="#332a07",
    ),
}


def set_current_ui_theme(name: str) -> str:
    global _current_theme
    key = (name or "").strip()
    if key in THEMES:
        _current_theme = key
    return _current_theme


def current_ui_theme() -> str:
    return _current_theme


def theme_palette(name: Optional[str] = None) -> Dict[str, str]:
    key = (name or _current_theme or "fusion_blue").strip()
    return dict(THEMES.get(key, THEMES["fusion_blue"]))


def theme_surface_text_color(name: Optional[str] = None) -> str:
    return theme_palette(name)["surface_text"]


def _surface_gradient_qss(p: Dict[str, str]) -> str:
    return (
        "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        f" stop:0 {p['surface_g0']}, stop:0.45 {p['surface_g1']}, stop:1 {p['surface_g2']})"
    )


def form_label_qss(pt: int, name: Optional[str] = None) -> str:
    p = theme_palette(name)
    grad = _surface_gradient_qss(p)
    return (
        f"font-size: {pt}pt; font-weight: 700; color: {p['surface_text']};"
        f" background: {grad};"
        f" border: 1px solid {p['surface_border']};"
        " border-radius: 5px; padding: 2px 4px;"
    )


def form_editor_qss(pt: int, name: Optional[str] = None) -> str:
    p = theme_palette(name)
    return f"font-size: {pt}pt; background-color: {p['input_bg']};"


def form_editor_locked_qss(pt: int, name: Optional[str] = None) -> str:
    """鎖定欄背景／框線／字色與欄位標題（form_label）一致；仍可聚焦。"""
    p = theme_palette(name)
    grad = _surface_gradient_qss(p)
    return (
        f"font-size: {pt}pt; font-weight: 400; color: {p['surface_text']};"
        f" background: {grad};"
        f" border: 1px solid {p['surface_border']};"
        " border-radius: 5px; padding: 2px 4px;"
    )


def work_action_button_qss(name: Optional[str] = None) -> str:
    p = theme_palette(name)
    return f"""
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {p['wa_g0']}, stop:0.42 {p['wa_g1']}, stop:1 {p['wa_g2']});
    border: 1px solid {p['wa_border']};
    border-radius: 8px;
    padding: 4px 10px;
    color: {p['wa_text']};
    font-weight: 800;
    font-size: 10pt;
}}
QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {p['wa_h0']}, stop:0.4 {p['wa_h1']}, stop:1 {p['wa_h2']});
    border: 1px solid {p['accent']};
    color: {p['wa_text']};
}}
QPushButton:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {p['wa_p0']}, stop:0.55 {p['wa_p1']}, stop:1 {p['wa_p2']});
    border: 1px solid {p['wa_border']};
    color: {p['wa_text']};
}}
QPushButton:disabled {{
    background: #e8ecf4;
    border: 1px solid #c8d0e0;
    color: #8899aa;
}}
"""


def work_action_panel_qss(name: Optional[str] = None) -> str:
    p = theme_palette(name)
    return f"""
QFrame#workActionPanel {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {p['wp_g0']}, stop:0.45 {p['wp_g1']}, stop:1 {p['wp_g2']});
    border: 1px solid {p['wp_border']};
    border-radius: 10px;
    padding: 6px;
}}
"""


def nav_button_qss(name: Optional[str] = None) -> str:
    p = theme_palette(name)
    return f"""
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {p['nav_g0']}, stop:0.5 {p['nav_g1']}, stop:1 {p['nav_g2']});
    border: 1px solid {p['nav_border']};
    border-radius: 4px;
    padding: 2px;
    color: {p['nav_text']};
}}
QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {p['wa_h0']}, stop:0.5 {p['nav_g1']}, stop:1 {p['nav_g2']});
    border: 1px solid {p['accent']};
}}
QPushButton:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {p['wa_p0']}, stop:1 {p['wa_p1']});
    border: 1px solid {p['wa_border']};
}}
QPushButton:disabled {{
    background: #e8ecf4;
    border: 1px solid #c8d0e0;
}}
"""


def lookup_button_qss(name: Optional[str] = None) -> str:
    return nav_button_qss(name) + """
QPushButton {
    border-radius: 3px;
    padding: 0px;
    margin: 0px;
    font-size: 11pt;
    font-weight: 700;
}
"""


_APP_STYLESHEET_TPL = """
QMainWindow, QWidget#CentralWidget {{
    background-color: {bg};
}}
QWidget {{
    background-color: {bg};
    color: {fg};
}}
QMenuBar {{
    background-color: {menu_bg};
    color: {fg};
    spacing: 2px;
}}
QMenuBar::item {{
    font-size: 11pt;
    padding: 6px 12px;
    background: transparent;
}}
QMenuBar::item:selected {{
    background-color: {toolbar_bg};
}}
QMenu {{
    background-color: {menu_bg};
    color: {fg};
}}
QMenu::item {{
    font-size: 11pt;
    padding: 6px 14px;
}}
QToolBar {{
    background-color: {toolbar_bg};
    border-bottom: 1px solid {border};
}}
QStatusBar {{
    background-color: {status_bg};
}}
QLabel {{
    font-size: 12pt;
    font-weight: 700;
}}
QTreeWidget::item {{
    font-size: 11pt;
    padding: 6px 8px;
}}
QListWidget::item {{
    font-size: 11pt;
    padding: 6px 10px;
}}
QToolBox::tab {{
    font-size: 11pt;
    padding: 8px 10px;
}}
QTabBar::tab {{
    font-size: 11pt;
    padding: 8px 14px;
    border: 1px solid {border};
    border-bottom: 1px solid {border};
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
    background: qlineargradient(
        x1: 0, y1: 0, x2: 0, y2: 1,
        stop: 0 {surface_g0},
        stop: 0.45 {menu_bg},
        stop: 1 {input_bg}
    );
}}
QTabBar::tab:selected {{
    font-weight: 800;
    border: 1px solid {border};
    border-bottom: 1px solid {bg};
    margin-top: -2px;
    background: qlineargradient(
        x1: 0, y1: 0, x2: 0, y2: 1,
        stop: 0 {surface_g0},
        stop: 0.35 {tab_sel_mid},
        stop: 1 {tab_sel_end}
    );
}}
QTabBar::tab:!selected {{
    margin-top: 1px;
}}
QTableView#appGridTable {{
    background-color: #ffffff;
    gridline-color: {border};
    selection-background-color: {grid_sel_bg};
    selection-color: {fg};
    alternate-background-color: {input_bg};
    font-size: {grid_cell_pt}pt;
}}
QTableView#appGridTable::item {{
    font-size: {grid_cell_pt}pt;
    padding: 2px 6px;
}}
QTableView#appGridTable::item:selected {{
    background-color: {grid_sel_bg};
    color: {fg};
}}
QTableView#appGridTable::item:selected:focus {{
    background-color: {accent};
    color: {fg};
}}
QTableView#appGridTable QLineEdit {{
    font-size: {grid_cell_pt}pt;
}}
QHeaderView::section {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {surface_g0}, stop:0.45 {surface_g1}, stop:1 {surface_g2});
    color: {surface_text};
    padding: 4px;
    border: 1px solid {surface_border};
    font-weight: 800;
    font-size: {grid_header_pt}pt;
}}
QTableWidget#appGridTable {{
    background-color: #ffffff;
    font-size: {grid_cell_pt}pt;
    gridline-color: {border};
    selection-background-color: {grid_sel_bg};
    selection-color: {fg};
}}
QTableWidget#appGridTable::item {{
    font-size: {grid_cell_pt}pt;
    padding: 2px 6px;
}}
QTableWidget#appGridTable::item:selected {{
    background-color: {grid_sel_bg};
    color: {fg};
}}
QTableWidget#appGridTable::item:selected:focus {{
    background-color: {accent};
    color: {fg};
}}
QTableWidget#appGridTable QLineEdit {{
    font-size: {grid_cell_pt}pt;
}}
QLineEdit, QTextEdit, QComboBox {{
    background-color: {input_bg};
    border: 1px solid {border};
    border-radius: 4px;
    font-size: 13pt;
    font-weight: 600;
}}
QListView, QTreeView {{
    background-color: {input_bg};
    border: 1px solid {border};
    border-radius: 4px;
    font-size: 11pt;
    font-weight: 600;
}}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
    border: 2px solid {accent};
}}
QPushButton {{
    color: white;
    border-radius: 5px;
    padding: 6px 14px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 {btn_g1}, stop:1 {btn_g2});
}}
QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 {btn_h1}, stop:1 {btn_h2});
}}
"""


def apply_app_stylesheet(
    name: str,
    *,
    grid_cell_pt: int,
    grid_header_pt: int,
    widget=None,
) -> None:
    """套用全域 Qt 樣式（選單、Grid 表頭、一般按鈕等）。"""
    from PyQt6.QtWidgets import QApplication

    set_current_ui_theme(name)
    cfg = {
        **theme_palette(name),
        "grid_cell_pt": grid_cell_pt,
        "grid_header_pt": grid_header_pt,
    }
    qss = _APP_STYLESHEET_TPL.format(**cfg)
    app = QApplication.instance()
    if app is not None:
        app.setStyleSheet(qss)
    elif widget is not None:
        widget.setStyleSheet(qss)
