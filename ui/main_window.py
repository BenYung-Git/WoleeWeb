from __future__ import annotations

import os
import webbrowser
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QAction, QIcon, QFont, QGuiApplication
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QTabWidget,
    QStackedWidget,
    QToolBox,
    QLabel,
    QStatusBar,
    QComboBox,
    QMessageBox,
    QFileDialog,
    QPushButton,
    QStyle,
)

from core.auth import UserSession, load_available_company_keys, load_company_currency, resolve_sys_data_path
from core.data_dictionary import (
    DataDictionary,
    LanguageCode,
    merge_work_action_flags,
    program_work_action_flags,
    resolve_work_actions_for_program,
)
from core.access_pool import get_access_backend
from core.db_backend import AccessBackend, SQLiteBackend, DbBackendBase
from core.db_factory import (
    get_backend_for_path,
    resolve_company_db_path,
    resolve_metadata_db_path,
    resolve_program_company_key,
    ensure_company_db_path,
    validate_company_db,
)
from core.menu_loader import ProgramRepository
from ui.work_page import (
    WorkPage,
    RecordDetailPage,
    apply_work_action_button_style,
    reapply_grid_fonts,
    reapply_form_fonts,
)
from ui.ai_assistant_page import AiAssistantPage
from core.ui_font_settings import get_ui_font_settings, load_ui_font_settings, set_ui_font_settings
from core.ui_icon_map import icon_from_key

# 主選單 MENUITEM 圖示尺寸（QStyle.standardIcon）
_MAIN_MENU_ICON_GRID = QSize(44, 44)
_MAIN_MENU_ICON_LIST = QSize(32, 32)

_MENU_ICON_KIND_TO_SP: Dict[str, QStyle.StandardPixmap] = {
    "system-users": QStyle.StandardPixmap.SP_DirHomeIcon,
    "dialog-password": QStyle.StandardPixmap.SP_MessageBoxWarning,
    "office-building": QStyle.StandardPixmap.SP_DirIcon,
    "package": QStyle.StandardPixmap.SP_DriveHDIcon,
    "basket": QStyle.StandardPixmap.SP_ArrowDown,
    "view-pim-tasks": QStyle.StandardPixmap.SP_FileDialogDetailedView,
    "x-office-document": QStyle.StandardPixmap.SP_FileIcon,
    "x-office-spreadsheet": QStyle.StandardPixmap.SP_FileDialogContentsView,
    "preferences-system": QStyle.StandardPixmap.SP_FileDialogListView,
    "server-database": QStyle.StandardPixmap.SP_DriveNetIcon,
    "applications-system": QStyle.StandardPixmap.SP_ComputerIcon,
}


class MainMenuMode:
    TREE = "TREE"
    ICON_GRID = "ICON_GRID"
    LIST = "LIST"
    TOOLBOX = "TOOLBOX"
    TABS = "TABS"


class MainWindow(QMainWindow):
    """
    主視窗:
    - 左側: 多種主選單型態（可切換）
    - 右側: QTabWidget 工作區
    """

    def __init__(self, base_dir: str, session: UserSession, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"企業管理系統 — {session.user_no}")
        self.resize(1280, 720)  # fallback: 若螢幕資訊不可取得

        self.session = session
        self.base_dir = os.path.abspath(base_dir)
        load_ui_font_settings(self.base_dir)
        self.mdb_path = resolve_sys_data_path(self.base_dir)
        self.lang: LanguageCode = "CHN"
        self._theme_name: str = "fusion_blue"

        # 資料庫相關狀態（登入公司 → {CO_KEY}.sqlite / .MDB）
        self.user_data_path: str = session.user_data_path
        co = (session.company_key or "GS").strip() or "GS"
        self.db_path: str = resolve_company_db_path(self.base_dir, co)
        self.db_type: str = self._db_type_for_path(self.db_path)
        self.current_table: str = ""
        # 同一個 .mdb 路徑共用 access_pool 的 AccessBackend（避免 ODBC「太多用戶端工作」）
        self._access_backend_by_path: Dict[str, AccessBackend] = {}

        # 同目錄 sys_data.mdb：啟動時偵測 columns 結構；開作業時依 WORK_PROC 載入欄位定義
        self.data_dict = DataDictionary(self.mdb_path)
        self.data_dict.load()

        self.program_repo = ProgramRepository(self.mdb_path)
        self.program_repo.load()
        self.program_repo.apply_permission_filter(
            session.group_level, session.company_key
        )

        self._work_tabs: QTabWidget

        self._build_ui()
        self._load_companies()

        # MAINMENU 主畫面預設為「接近全螢幕」：90% 可用螢幕大小
        self._apply_default_mainmenu_size_90pct()
        self._refresh_web_menu_status()

    def _dispose_access_backend_cache(self) -> None:
        # 共用 pool 不在此關閉連線，僅清本地參考
        self._access_backend_by_path.clear()

    def _access_backend_for_path(self, db_path: str) -> AccessBackend:
        key = os.path.abspath(db_path)
        b = get_access_backend(key)
        self._access_backend_by_path[key] = b
        return b

    @staticmethod
    def _db_type_for_path(db_path: str) -> str:
        ext = os.path.splitext((db_path or "").strip().lower())[1]
        if ext in (".sqlite", ".db", ".db3"):
            return "SQLite"
        return "Access"

    # region UI
    def _set_widget_font_pt(self, widget: QWidget, pt: int = 11) -> None:
        f = QFont(widget.font())
        f.setPointSize(pt)
        widget.setFont(f)

    def _menu_item_icon(self, do_proc: str, title: str) -> QIcon:
        """
        依 DO_PROC / 標題決定語意分類，再以 QStyle.standardIcon 取得系統圖示。
        """
        proc = (do_proc or "").strip().upper()
        key = f"{proc} {title}".lower()
        icon_name = "applications-system"

        # 1) DO_PROC 精準對應（可持續擴充）
        do_proc_icon_map = {
            "USERS": "system-users",
            "USER": "system-users",
            "SYS_USER": "system-users",
            "SYS_GROUP": "dialog-password",
            "GROUP": "dialog-password",
            "SYS_CO": "office-building",
            "COMPANY": "office-building",
            "ITEM": "package",
            "STOCK": "package",
            "INVENTORY": "package",
            "PURCHASE": "basket",
            "PO": "basket",
            "SALE": "view-pim-tasks",
            "SO": "view-pim-tasks",
            "REPORT": "x-office-document",
            "PRINT": "x-office-document",
            "ACCOUNT": "x-office-spreadsheet",
            "FINANCE": "x-office-spreadsheet",
            "SETTING": "preferences-system",
            "CONFIG": "preferences-system",
            "DATA": "server-database",
            "DB": "server-database",
        }
        if proc in do_proc_icon_map:
            icon_name = do_proc_icon_map[proc]
        else:
            # 2) 前綴匹配（例如 SALES_*, SYS_*）
            prefix_rules = [
                (("USR", "USER"), "system-users"),
                (("GRP", "GROUP"), "dialog-password"),
                (("CO", "COMPANY"), "office-building"),
                (("ITEM", "INV", "STK"), "package"),
                (("PO", "PUR"), "basket"),
                (("SO", "SAL"), "view-pim-tasks"),
                (("RPT", "REP", "PRN"), "x-office-document"),
                (("ACC", "FIN"), "x-office-spreadsheet"),
                (("SET", "CFG"), "preferences-system"),
                (("DB", "DATA"), "server-database"),
            ]
            for prefixes, name in prefix_rules:
                if any(proc.startswith(p) for p in prefixes):
                    icon_name = name
                    break

        # 3) 標題關鍵字備援
        if icon_name == "applications-system":
            rules = [
                (("user", "users", "帳", "員工", "person", "member"), "system-users"),
                (("group", "權限", "role", "permission"), "dialog-password"),
                (("co", "company", "公司"), "office-building"),
                (("stock", "inventory", "item", "product", "品號", "料號"), "package"),
                (("sale", "order", "訂單", "銷"), "view-pim-tasks"),
                (("purchase", "採購"), "basket"),
                (("finance", "account", "會計", "帳務"), "x-office-spreadsheet"),
                (("report", "報表", "print"), "x-office-document"),
                (("setting", "config", "參數", "設定"), "preferences-system"),
                (("db", "data", "資料"), "server-database"),
            ]
            for keys, name in rules:
                if any(k in key for k in keys):
                    icon_name = name
                    break
        sp = _MENU_ICON_KIND_TO_SP.get(
            icon_name, QStyle.StandardPixmap.SP_ComputerIcon
        )
        return self.style().standardIcon(sp)

    def _add_menu_list_item(
        self,
        listw: QListWidget,
        do_proc: str,
        title_for_icon: str,
        label_text: str,
    ) -> QListWidgetItem:
        ic = self._menu_item_icon(do_proc, title_for_icon)
        item = QListWidgetItem(ic, label_text)
        item.setData(Qt.ItemDataRole.UserRole, do_proc)
        listw.addItem(item)
        return item

    def _build_ui(self) -> None:
        central = QWidget()
        root_layout = QHBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)

        # 左: 主選單容器 (StackedWidget)
        self.menu_stack = QStackedWidget()
        self.menu_stack.setFixedWidth(260)

        # 不同類型的 main menu（依 MAINMENU.mainmenu_groups 建立）
        self._tree_menu = self._build_tree_menu()
        self._icon_grid_menu = self._build_icon_grid_menu()
        self._list_menu = self._build_list_menu()
        self._toolbox_menu = self._build_toolbox_menu()
        self._tabs_menu = self._build_tabs_menu()

        self.menu_stack.addWidget(self._tree_menu)
        self.menu_stack.addWidget(self._icon_grid_menu)
        self.menu_stack.addWidget(self._list_menu)
        self.menu_stack.addWidget(self._toolbox_menu)
        self.menu_stack.addWidget(self._tabs_menu)

        root_layout.addWidget(self.menu_stack)

        # 右: 工作區 TabWidget
        self._work_tabs = QTabWidget()
        self._work_tabs.setTabsClosable(True)
        self._work_tabs.tabCloseRequested.connect(self._on_close_tab)
        root_layout.addWidget(self._work_tabs, 1)

        central.setLayout(root_layout)
        self.setCentralWidget(central)

        self._build_menu_bar()
        self._build_status_bar()

        # 預設套用 Fusion 科技風主題
        self._apply_theme("fusion_blue")

    def _apply_default_mainmenu_size_90pct(self) -> None:
        """將主視窗預設設定為 primary screen 的可用區 90%（並置中）。"""
        try:
            screen = QGuiApplication.primaryScreen()
            if screen is None:
                return
            geo = screen.availableGeometry()
            if geo.width() <= 0 or geo.height() <= 0:
                return
            w = int(geo.width() * 0.9)
            h = int(geo.height() * 0.9)
            if w <= 0 or h <= 0:
                return
            x = geo.x() + (geo.width() - w) // 2
            y = geo.y() + (geo.height() - h) // 2
            self.setGeometry(x, y, w, h)
        except Exception:
            # 若遇到任何 Qt/driver 問題就維持 fallback resize(1280,720)
            return

    def _build_menu_bar(self) -> None:
        menubar = self.menuBar()

        # 語系選單（選單列僅文字；圖示在 QMenuBar 上易造成顯示異常）
        lang_menu = menubar.addMenu("語言 Language")
        act_chn = QAction("中文", self)
        act_eng = QAction("English", self)
        act_chn.triggered.connect(lambda: self._change_language("CHN"))
        act_eng.triggered.connect(lambda: self._change_language("ENG"))
        lang_menu.addAction(act_chn)
        lang_menu.addAction(act_eng)

        # Main menu 樣式選單
        style_menu = menubar.addMenu("主選單樣式")

        def add_style_action(text: str, mode_index: int):
            act = QAction(text, self)
            act.triggered.connect(lambda: self.menu_stack.setCurrentIndex(mode_index))
            style_menu.addAction(act)

        add_style_action("樹狀 TreeView", 0)
        add_style_action("圖示 ImageListView", 1)
        add_style_action("列表 ListMenu", 2)
        add_style_action("折疊 ToolBox", 3)
        add_style_action("分頁 TabsMenu", 4)

        # 主題選單（6 種淡色風格）
        theme_menu = menubar.addMenu("主題 Theme")
        for name, label in [
            ("fusion_blue", "Fusion 科技風（預設）"),
            ("soft_green", "柔和綠"),
            ("soft_purple", "淡紫"),
            ("warm_gray", "暖灰"),
            ("mint", "薄荷綠"),
            ("daylight", "日光"),
        ]:
            act = QAction(label, self)
            act.triggered.connect(lambda checked=False, n=name: self._apply_theme(n))
            theme_menu.addAction(act)

        # 檢視：全系統 Grid／表單字體
        view_menu = menubar.addMenu("檢視 View")
        act_grid_plus = QAction("Grid 字體 +1pt（含標題列）", self)
        act_grid_minus = QAction("Grid 字體 -1pt（含標題列）", self)
        act_form_plus = QAction("表單字體 +1pt", self)
        act_form_minus = QAction("表單字體 -1pt", self)
        act_grid_plus.triggered.connect(lambda: self._bump_system_grid_font(1))
        act_grid_minus.triggered.connect(lambda: self._bump_system_grid_font(-1))
        act_form_plus.triggered.connect(lambda: self._bump_system_form_font(1))
        act_form_minus.triggered.connect(lambda: self._bump_system_form_font(-1))
        view_menu.addAction(act_grid_plus)
        view_menu.addAction(act_grid_minus)
        view_menu.addSeparator()
        view_menu.addAction(act_form_plus)
        view_menu.addAction(act_form_minus)

        # 資料庫選單（Access / SQLite）
        db_menu = menubar.addMenu("資料庫")
        act_access = QAction("使用 Access (目前路徑)", self)
        act_access.triggered.connect(self._switch_to_access)
        db_menu.addAction(act_access)
        act_sqlite = QAction("使用 SQLite...", self)
        act_sqlite.triggered.connect(self._switch_to_sqlite)
        db_menu.addAction(act_sqlite)

        # 介面切換（桌面 ↔ Web）
        iface_menu = menubar.addMenu("介面 Interface")
        self._act_open_web = QAction("開啟 Web 介面", self)
        self._act_open_web.triggered.connect(self._open_web_interface)
        iface_menu.addAction(self._act_open_web)
        self._act_web_status = QAction("", self)
        self._act_web_status.setEnabled(False)
        iface_menu.addAction(self._act_web_status)
        self._refresh_web_menu_status()

        self._act_ai = QAction("AI", self)
        self._act_ai.setToolTip("開啟 AI 助理")
        self._act_ai.triggered.connect(self._open_ai_tab)
        menubar.addAction(self._act_ai)

        # 離開／AI／重新載入放選單列右側（介面 Interface 右面），省去工具列高度
        self._install_menubar_corner_actions(menubar)

    def _install_menubar_corner_actions(self, menubar) -> None:
        """將離開／AI／重新載入放在選單列右上角。"""
        corner = QWidget()
        row = QHBoxLayout(corner)
        row.setContentsMargins(4, 0, 8, 0)
        row.setSpacing(6)

        self._tb_btn_ai = QPushButton()
        self._tb_btn_ai.setIcon(icon_from_key(self.style(), "ai"))
        apply_work_action_button_style(self._tb_btn_ai)
        self._tb_btn_ai.clicked.connect(self._open_ai_tab)

        self._tb_btn_reload = QPushButton()
        self._tb_btn_reload.setIcon(icon_from_key(self.style(), "convert_db"))
        self._tb_btn_reload.setToolTip("重新載入資料字典與主選單")
        apply_work_action_button_style(self._tb_btn_reload)
        self._tb_btn_reload.clicked.connect(self._reload_metadata)

        self._tb_btn_exit = QPushButton()
        self._tb_btn_exit.setIcon(icon_from_key(self.style(), "exit"))
        apply_work_action_button_style(self._tb_btn_exit)
        self._tb_btn_exit.clicked.connect(self._logout_to_login)

        row.addWidget(self._tb_btn_exit)
        row.addWidget(self._tb_btn_ai)
        row.addWidget(self._tb_btn_reload)
        menubar.setCornerWidget(corner, Qt.Corner.TopRightCorner)
        self._refresh_toolbar_labels()

    def _refresh_all_work_ui_fonts(self) -> None:
        """將目前字體設定套用到所有已開啟的作業／明細分頁（Grid 儲存格與欄位標題列）。"""
        from ui.work_page import RecordDetailPage, WorkPage, apply_grid_column_width_limits, apply_grid_visible_row_count, reapply_grid_fonts

        for i in range(self._work_tabs.count()):
            w = self._work_tabs.widget(i)
            if isinstance(w, WorkPage):
                reapply_grid_fonts(w.table, self.base_dir)
                rows = getattr(w, "_grid_visible_rows", None)
                if rows is not None:
                    apply_grid_visible_row_count(w.table, rows)
                if hasattr(w, "_ensure_column_widths"):
                    w._ensure_column_widths()
                for tx_grid in getattr(w, "_tx_input_grids", {}).values():
                    reapply_grid_fonts(tx_grid, self.base_dir)
            elif isinstance(w, RecordDetailPage):
                w._reapply_detail_grids()
                w._reapply_detail_form()

    def _refresh_all_work_ui_theme(self) -> None:
        from ui.work_page import RecordDetailPage, WorkPage

        for i in range(self._work_tabs.count()):
            w = self._work_tabs.widget(i)
            if isinstance(w, WorkPage):
                w.reapply_work_theme()
            elif isinstance(w, RecordDetailPage):
                w.reapply_detail_theme()

    def _bump_system_grid_font(self, delta: int) -> None:
        s = get_ui_font_settings(self.base_dir)
        s.bump_grid(delta)
        set_ui_font_settings(self.base_dir, s)
        self._apply_theme(self._theme_name)
        self._refresh_all_work_ui_fonts()

    def _bump_system_form_font(self, delta: int) -> None:
        s = get_ui_font_settings(self.base_dir)
        s.bump_form(delta)
        set_ui_font_settings(self.base_dir, s)
        self._refresh_all_work_ui_fonts()

    def _refresh_web_menu_status(self) -> None:
        chn = self.lang == "CHN"
        try:
            from api.server import WebServerManager

            mgr = WebServerManager.instance()
            if mgr.is_running:
                urls = mgr.access_urls
                status = urls[0] if len(urls) == 1 else f"{urls[0]} (+{len(urls)-1} LAN)"
                self._act_web_status.setText(f"Web: {status}")
            else:
                web_url = os.environ.get("WOLEE_WEB_URL", "")
                if web_url:
                    self._act_web_status.setText(f"Web: {web_url}")
                else:
                    self._act_web_status.setText(
                        "Web 伺服器未啟動" if chn else "Web server stopped"
                    )
        except Exception:
            self._act_web_status.setText("")

    def _open_web_interface(self) -> None:
        """啟動 Web 伺服器（若尚未執行）並在瀏覽器開啟。"""
        chn = self.lang == "CHN"
        try:
            from api.server import WebServerManager

            mgr = WebServerManager.instance()
            if not mgr.is_running:
                host = os.environ.get("WOLEE_WEB_HOST", "0.0.0.0")
                port = int(os.environ.get("WOLEE_WEB_PORT", "8080"))
                mgr.configure(host=host, port=port, base_dir=self.base_dir)
                mgr.start(blocking=False)
            webbrowser.open(mgr.url)
            self._refresh_web_menu_status()
            urls_text = "\n".join(mgr.access_urls)
            lan_urls = [u for u in mgr.access_urls if "127.0.0.1" not in u]
            lan_hint = (
                f"\n\n其他電腦請用瀏覽器開啟：\n" + "\n".join(lan_urls)
                if lan_urls
                else ""
            )
            QMessageBox.information(
                self,
                "Web 介面" if chn else "Web Interface",
                (
                    f"已在瀏覽器開啟 Web 介面。\n\n可連線位址：\n{urls_text}"
                    f"{lan_hint}\n\n"
                    "Web 伺服器須在存有 .mdb 的 Windows 電腦執行；"
                    "其他電腦只需瀏覽器，無需安裝 Python。"
                    if chn
                    else f"Web interface opened.\n\nURLs:\n{urls_text}{lan_hint}"
                ),
            )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Web 介面" if chn else "Web Interface",
                f"無法啟動 Web 伺服器：{e}\n\n"
                "請確認已安裝 fastapi、uvicorn：\n  pip install -r requirements.txt",
            )

    def _switch_to_access(self) -> None:
        self.db_type = "Access"
        self._refresh_status_bar()

    def _switch_to_sqlite(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "選擇 SQLite 資料庫", self.base_dir, "SQLite (*.db *.sqlite *.sqlite3);;All (*)")
        if path:
            self.db_type = "SQLite"
            self.db_path = path
            self._refresh_status_bar()

    def _refresh_toolbar_labels(self) -> None:
        chn = self.lang == "CHN"
        if hasattr(self, "_tb_btn_ai") and self._tb_btn_ai is not None:
            self._tb_btn_ai.setText("AI")
            self._tb_btn_ai.setToolTip("開啟 AI 助理" if chn else "Open AI assistant")
        if hasattr(self, "_act_ai") and self._act_ai is not None:
            self._act_ai.setText("AI")
            self._act_ai.setToolTip("開啟 AI 助理" if chn else "Open AI assistant")
        if hasattr(self, "_tb_btn_reload") and self._tb_btn_reload is not None:
            self._tb_btn_reload.setText("重新載入" if chn else "Reload")
            self._tb_btn_reload.setToolTip(
                "重新載入資料字典與主選單" if chn else "Reload data dictionary & main menu"
            )
        if hasattr(self, "_tb_btn_exit") and self._tb_btn_exit is not None:
            self._tb_btn_exit.setText("離開" if chn else "Exit")
            self._tb_btn_exit.setToolTip("登出並返回登入畫面" if chn else "Logout and back to login")
        if hasattr(self, "_act_open_web") and self._act_open_web is not None:
            self._act_open_web.setText("開啟 Web 介面" if chn else "Open Web Interface")
        for btn in (
            getattr(self, "_tb_btn_ai", None),
            getattr(self, "_tb_btn_reload", None),
            getattr(self, "_tb_btn_exit", None),
        ):
            if btn is not None:
                apply_work_action_button_style(btn)
        self._refresh_web_menu_status()

    def _apply_session(self, session: UserSession) -> None:
        """套用新登入 session，重建主選單並清空既有工作分頁。"""
        self.session = session
        self.setWindowTitle(f"企業管理系統 — {session.user_no}")
        self.user_data_path = session.user_data_path
        co = (session.company_key or "GS").strip() or "GS"
        self.db_path = resolve_company_db_path(self.base_dir, co)
        self.db_type = self._db_type_for_path(self.db_path)
        self.current_table = ""
        self._dispose_access_backend_cache()

        # 使用新帳號權限重載 metadata
        self.data_dict.load()
        self.program_repo.load()
        self.program_repo.apply_permission_filter(
            session.group_level, session.company_key
        )

        while self._work_tabs.count() > 0:
            w = self._work_tabs.widget(0)
            self._work_tabs.removeTab(0)
            if w is not None:
                w.deleteLater()

        self._reload_metadata(reload_db=False)
        self._load_companies()
        self._refresh_status_bar()

    def _logout_to_login(self) -> None:
        """MainMenu 離開：返回登入畫面；取消登入才真正結束程式。"""
        from ui.login_dialog import LoginDialog

        self.hide()
        login = LoginDialog(self.base_dir)
        if login.exec() == QDialog.DialogCode.Accepted:
            session = login.session()
            if session is not None:
                self._apply_session(session)
                self.show()
                self.raise_()
                self.activateWindow()
                return
        self.close()

    def _build_status_bar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)

        sb.addWidget(QLabel("公司"))
        self.cbo_company = QComboBox()
        self.cbo_company.setMinimumWidth(72)
        self.cbo_company.currentTextChanged.connect(self._on_company_changed)
        sb.addWidget(self.cbo_company)

        self.lbl_session = QLabel()
        sb.addWidget(self.lbl_session, 1)

        self.lbl_db_type = QLabel()
        self.lbl_db_path = QLabel()
        self.lbl_table = QLabel()

        sb.addPermanentWidget(self.lbl_db_type)
        sb.addPermanentWidget(self.lbl_db_path, 1)
        sb.addPermanentWidget(self.lbl_table)

        self._refresh_status_bar()

    def _refresh_status_bar(self) -> None:
        user = (self.session.user_no or "").strip() or "-"
        parts = [f"使用者: {user}"]
        login_date = (getattr(self.session, "login_date", "") or "").strip()
        if login_date:
            parts.append(f"日期: {login_date}")
        if getattr(self, "lbl_session", None) is not None:
            self.lbl_session.setText("  ".join(parts))
        self.lbl_db_type.setText(f"DB: {self.db_type}")
        self.lbl_db_path.setText(f"Path: {self.db_path}")
        self.lbl_table.setText(f"Table: {self.current_table or '-'}")

    def _apply_theme(self, name: str) -> None:
        """套用 6 種淡色主題，並刷新已開啟作業頁的按鈕／標題樣式。"""
        from core.ui_theme import apply_app_stylesheet

        self._theme_name = name
        font_s = get_ui_font_settings(self.base_dir)
        apply_app_stylesheet(
            name,
            grid_cell_pt=font_s.grid_cell_pt,
            grid_header_pt=font_s.grid_header_pt,
        )
        self._refresh_all_work_ui_theme()
        self._refresh_toolbar_labels()

    # endregion

    # region 主選單 UI 建立
    def _build_tree_menu(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        tree = QTreeWidget()
        self._set_widget_font_pt(tree, 11)
        tree.setHeaderHidden(True)
        tree.setIconSize(_MAIN_MENU_ICON_LIST)

        for mm_group in self.program_repo.mainmenu_groups:
            group_item = QTreeWidgetItem([mm_group.get_title(self.lang)])
            tree.addTopLevelItem(group_item)
            for prg in mm_group.items:
                title = prg.get_title(self.lang)
                child = QTreeWidgetItem([title])
                child.setData(0, Qt.ItemDataRole.UserRole, prg.do_proc)
                child.setIcon(0, self._menu_item_icon(prg.do_proc, title))
                group_item.addChild(child)
        tree.itemDoubleClicked.connect(self._on_program_triggered_from_tree)
        layout.addWidget(tree, 1)
        widget.setLayout(layout)
        return widget

    def _build_icon_grid_menu(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        listw = QListWidget()
        self._set_widget_font_pt(listw, 11)
        listw.setViewMode(QListWidget.ViewMode.IconMode)
        listw.setIconSize(_MAIN_MENU_ICON_GRID)
        listw.setResizeMode(QListWidget.ResizeMode.Adjust)
        listw.setMovement(QListWidget.Movement.Static)
        listw.setSpacing(10)

        for mm_group in self.program_repo.mainmenu_groups:
            for item in mm_group.items:
                title = item.get_title(self.lang)
                self._add_menu_list_item(listw, item.do_proc, title, title)

        listw.itemDoubleClicked.connect(self._on_program_triggered_from_list)
        layout.addWidget(listw, 1)
        widget.setLayout(layout)
        return widget

    def _build_list_menu(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        listw = QListWidget()
        self._set_widget_font_pt(listw, 11)
        listw.setIconSize(_MAIN_MENU_ICON_LIST)

        for mm_group in self.program_repo.mainmenu_groups:
            group_title = mm_group.get_title(self.lang)
            for item in mm_group.items:
                title = f"[{group_title}] {item.get_title(self.lang)}"
                self._add_menu_list_item(
                    listw,
                    item.do_proc,
                    item.get_title(self.lang),
                    title,
                )

        listw.itemDoubleClicked.connect(self._on_program_triggered_from_list)
        layout.addWidget(listw, 1)
        widget.setLayout(layout)
        return widget

    def _build_toolbox_menu(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        toolbox = QToolBox()
        self._set_widget_font_pt(toolbox, 11)
        for mm_group in self.program_repo.mainmenu_groups:
            page = QListWidget()
            self._set_widget_font_pt(page, 11)
            page.setIconSize(_MAIN_MENU_ICON_LIST)
            for prg in mm_group.items:
                title = prg.get_title(self.lang)
                self._add_menu_list_item(page, prg.do_proc, title, title)
            page.itemDoubleClicked.connect(self._on_program_triggered_from_list)
            toolbox.addItem(page, mm_group.get_title(self.lang))

        layout.addWidget(toolbox, 1)
        widget.setLayout(layout)
        return widget

    def _build_tabs_menu(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()
        self._set_widget_font_pt(tabs.tabBar(), 11)

        for mm_group in self.program_repo.mainmenu_groups:
            page = QListWidget()
            self._set_widget_font_pt(page, 11)
            page.setIconSize(_MAIN_MENU_ICON_LIST)
            for prg in mm_group.items:
                title = prg.get_title(self.lang)
                self._add_menu_list_item(page, prg.do_proc, title, title)
            page.itemDoubleClicked.connect(self._on_program_triggered_from_list)
            tabs.addTab(page, mm_group.get_title(self.lang))

        from core.ui_theme import apply_tab_title_colors

        apply_tab_title_colors(tabs)
        layout.addWidget(tabs, 1)
        widget.setLayout(layout)
        return widget

    # endregion

    def _colorize_work_tabs(self) -> None:
        from core.ui_theme import apply_tab_title_colors

        apply_tab_title_colors(self._work_tabs)

    # region 動作
    def _change_language(self, lang: LanguageCode) -> None:
        self.lang = lang
        self._refresh_toolbar_labels()
        # 切換語言不需要重連資料庫：只重建主選單 UI 與已開啟分頁文字。
        self._reload_metadata(reload_db=False)
        # 讓已開啟的 Tab 也同步更新 Grid 與搜尋介面
        for i in range(self._work_tabs.count()):
            w = self._work_tabs.widget(i)
            if isinstance(w, WorkPage):
                w.set_language(lang)
                do_proc = getattr(w, "_do_proc", None)
                if do_proc:
                    prg = self.program_repo.find_by_do_proc(do_proc)
                    menu_title = prg.get_title(lang) if prg else str(do_proc)
                    self._work_tabs.setTabText(i, menu_title)
            elif isinstance(w, RecordDetailPage):
                w.set_language(lang)
                do_proc = getattr(w, "_do_proc", None)
                if do_proc:
                    prg = self.program_repo.find_by_do_proc(do_proc)
                    menu_title = prg.get_title(lang) if prg else str(do_proc)
                    mode = getattr(w, "_detail_mode", "edit")
                    if mode == "copy":
                        suffix = "複製" if lang == "CHN" else "Copy"
                    elif mode == "add":
                        suffix = "新增" if lang == "CHN" else "Add"
                    else:
                        suffix = "明細" if lang == "CHN" else "Detail"
                    self._work_tabs.setTabText(i, f"{menu_title} — {suffix}")
            elif isinstance(w, AiAssistantPage):
                w.set_language(lang)
                self._work_tabs.setTabText(i, "AI" if lang == "CHN" else "AI")
        self._colorize_work_tabs()

    def _reload_metadata(self, reload_db: bool = True) -> None:
        if reload_db:
            self.data_dict.load()
            self.program_repo.load()
            self.program_repo.apply_permission_filter(
                self.session.group_level, self.session.company_key
            )
        # 重建主選單
        self.menu_stack.removeWidget(self._tree_menu)
        self.menu_stack.removeWidget(self._icon_grid_menu)
        self.menu_stack.removeWidget(self._list_menu)
        self.menu_stack.removeWidget(self._toolbox_menu)
        self.menu_stack.removeWidget(self._tabs_menu)

        self._tree_menu = self._build_tree_menu()
        self._icon_grid_menu = self._build_icon_grid_menu()
        self._list_menu = self._build_list_menu()
        self._toolbox_menu = self._build_toolbox_menu()
        self._tabs_menu = self._build_tabs_menu()

        self.menu_stack.addWidget(self._tree_menu)
        self.menu_stack.addWidget(self._icon_grid_menu)
        self.menu_stack.addWidget(self._list_menu)
        self.menu_stack.addWidget(self._toolbox_menu)
        self.menu_stack.addWidget(self._tabs_menu)

        if reload_db:
            seen_dbf: set[str] = set()
            for i in range(self._work_tabs.count()):
                w = self._work_tabs.widget(i)
                if isinstance(w, WorkPage):
                    proc = self.data_dict.resolve_rule_dbf_name(w.table_name)
                    if proc not in seen_dbf:
                        self.data_dict.load_columns_for_dbf(proc)
                        seen_dbf.add(proc)
                    for tx in w.tx_files:
                        tu = tx.strip().upper()
                        if tu and tu not in seen_dbf:
                            self.data_dict.load_columns_for_dbf(tu)
                            seen_dbf.add(tu)
                    w.refresh_after_data_dictionary_reload()
                elif isinstance(w, RecordDetailPage):
                    proc = self.data_dict.resolve_rule_dbf_name(w.table_name)
                    if proc not in seen_dbf:
                        self.data_dict.load_columns_for_dbf(proc)
                        seen_dbf.add(proc)
                    w.refresh_after_data_dictionary_reload()

    def _on_company_changed(self, co_key: str) -> None:
        """公司 ComboBox 變更時，主要資料庫改為 {CO_KEY}.sqlite / .MDB。"""
        co = (co_key or "").strip()
        if not co:
            return
        expected_path = resolve_company_db_path(self.base_dir, co)
        if (
            co == (self.session.company_key or "").strip()
            and os.path.normcase(self.db_path) == os.path.normcase(expected_path)
        ):
            self._refresh_status_bar()
            return
        db_err = validate_company_db(self.base_dir, co)
        if db_err:
            QMessageBox.warning(self, "公司", db_err)
            self._pick_company_combo(self.session.company_key or "GS")
            return
        self.session.company_key = co
        self.session.company_currency = load_company_currency(self.user_data_path, co)
        self.db_path = resolve_company_db_path(self.base_dir, co)
        self.db_type = self._db_type_for_path(self.db_path)
        self._refresh_status_bar()
        self._reload_metadata(reload_db=True)
        # 已開啟工作頁同步公司貨幣，供新增預設使用
        from ui.work_page import WorkPage

        for i in range(self._work_tabs.count()):
            w = self._work_tabs.widget(i)
            if isinstance(w, WorkPage):
                w._company_co_key = co
                w._company_currency = self.session.company_currency or ""

    def _load_companies(self) -> None:
        """
        從 user_data 讀取 sys_co.CO_KEY 填入 ComboBox；
        選中公司對應主要資料庫為 {CO_KEY}.sqlite 或 .MDB。
        """
        keys, err, _missing = load_available_company_keys(
            self.base_dir, self.user_data_path
        )
        if err:
            QMessageBox.warning(self, "公司清單", err)
        self.cbo_company.clear()
        for k in keys:
            self.cbo_company.addItem(k)
        if self.cbo_company.count() == 0:
            self.cbo_company.addItem("GS")
        self._pick_company_combo(self.session.company_key or "GS")
        self._refresh_status_bar()

    def _pick_company_combo(self, co_key: str) -> None:
        """選取公司並同步主要資料庫路徑。"""
        co = (co_key or "").strip() or "GS"
        self.cbo_company.blockSignals(True)
        try:
            idx = self.cbo_company.findText(co, Qt.MatchFlag.MatchFixedString)
            if idx >= 0:
                self.cbo_company.setCurrentIndex(idx)
            else:
                self.cbo_company.insertItem(0, co)
                self.cbo_company.setCurrentIndex(0)
        finally:
            self.cbo_company.blockSignals(False)
        self._on_company_changed(self.cbo_company.currentText())

    def _remove_tab_widget(self, w: QWidget) -> None:
        idx = self._work_tabs.indexOf(w)
        if idx >= 0:
            self._work_tabs.removeTab(idx)
            w.deleteLater()
            self._colorize_work_tabs()

    def _on_program_triggered_from_tree(self, item: QTreeWidgetItem, column: int) -> None:
        do_proc = item.data(0, Qt.ItemDataRole.UserRole)
        if do_proc:
            self._open_program(str(do_proc))

    def _on_program_triggered_from_list(self, item) -> None:
        do_proc = item.data(Qt.ItemDataRole.UserRole)
        if do_proc:
            self._open_program(str(do_proc))

    def _get_backend(self) -> DbBackendBase:
        """依目前 db_path 取得資料庫後端。"""
        return get_backend_for_path(self.db_path)

    def _resolve_program_db_path(self, prg) -> tuple[str, Optional[str]]:
        """
        依規則選資料庫：
        1) WORK_DB 非空白：使用 WORK_DB
        2) 否則依 PRG_CO 與登入公司
        """
        work_db = (getattr(prg, "work_db", None) or "").strip() if prg else ""
        co_key = (getattr(prg, "co_key", None) or "").strip() if prg else ""
        if work_db:
            meta_path = resolve_metadata_db_path(self.base_dir, work_db)
            if meta_path:
                return meta_path, None
            if os.path.isabs(work_db):
                return work_db, None
            root, ext = os.path.splitext(work_db)
            if ext:
                cand = os.path.join(self.base_dir, work_db)
                if os.path.isfile(cand):
                    return cand, None
                if work_db.lower().endswith(".mdb"):
                    sqlite_cand = os.path.join(self.base_dir, root + ".sqlite")
                    if os.path.isfile(sqlite_cand):
                        return sqlite_cand, None
                return cand, None
            return ensure_company_db_path(self.base_dir, work_db)
        key, err = resolve_program_company_key(co_key, self.session.company_key)
        if err:
            return "", err
        return ensure_company_db_path(self.base_dir, key)

    def _backend_for_db_path(self, db_path: str) -> DbBackendBase:
        if str(db_path).strip().lower().endswith((".sqlite", ".db", ".db3")):
            return SQLiteBackend(db_path)
        return self._access_backend_for_path(db_path)

    def _open_non_standard_program(self, do_proc: str, prg) -> bool:
        """STD_PROC=False 之程序；回傳 True 表示已處理（含錯誤提示）。"""
        from core.data_import_service import is_data_import_program
        from core.program_dispatch import non_standard_program_kind
        from core.run_query_service import is_run_query_program
        from ui.data_import_dialog import open_data_import

        kind = non_standard_program_kind(do_proc)
        if kind is None:
            QMessageBox.warning(
                self,
                "開啟作業",
                f"非標準程式「{do_proc}」尚未支援。",
            )
            return True
        if is_run_query_program(do_proc):
            self._open_run_query_tab(do_proc, prg)
            return True
        if is_data_import_program(do_proc):
            from core.db_factory import (
                prepare_transfer_db_for_import,
                resolve_spec_transfer_folder,
            )

            binding = self.program_repo.resolve_program_binding(do_proc)
            data_prg = binding.data_item
            # 每次重新執行 DO_DATAIMPORT：強制使用規格預設 TRANSFER
            pref_folder = resolve_spec_transfer_folder(self.base_dir)
            transfer_path, _share, t_err, _t_warn = prepare_transfer_db_for_import(
                self.base_dir, folder=pref_folder
            )
            if t_err:
                QMessageBox.warning(self, "開啟作業", t_err)
                return True
            company_path, co_err = self._resolve_program_db_path(data_prg or prg)
            if co_err:
                QMessageBox.warning(self, "開啟作業", co_err)
                return True
            if not company_path or not os.path.isfile(company_path):
                QMessageBox.warning(
                    self,
                    "開啟作業",
                    f"找不到公司資料庫：{company_path or ''}",
                )
                return True
            open_data_import(
                self._backend_for_db_path(transfer_path),
                self._backend_for_db_path(company_path),
                do_proc=do_proc,
                lang=self.lang,
                parent=self,
                base_dir=self.base_dir,
            )
            return True
        return False

    def _open_run_query_tab(self, do_proc: str, prg) -> None:
        """開啟執行查詢（RUNQUERY）專用 TAB。"""
        from core.run_query_service import RUN_QUERY_DO_PROC, ensure_run_query_infra
        from ui.run_query_dialog import open_run_query

        ok, err = ensure_run_query_infra(self.base_dir, self.mdb_path)
        if not ok:
            QMessageBox.warning(self, "開啟作業", err or "無法準備 RUN_QUERY。")
            return

        for i in range(self._work_tabs.count()):
            w = self._work_tabs.widget(i)
            if w is not None and getattr(w, "_run_query_tab", False):
                self._work_tabs.setCurrentIndex(i)
                return

        page_holder: dict = {"w": None}

        def _close() -> None:
            w = page_holder.get("w")
            if w is not None:
                self._remove_tab_widget(w)

        if prg:
            title = prg.get_title(self.lang)
        else:
            title = "執行查詢" if str(self.lang).upper().startswith("C") else "Execute Query"

        page = open_run_query(
            base_dir=self.base_dir,
            sys_mdb_path=self.mdb_path,
            lang=self.lang,
            data_dict=self.data_dict,
            user_no=str(getattr(self.session, "user_no", "") or ""),
            company_key=str(getattr(self.session, "company_key", "") or "GS"),
            do_proc=do_proc or RUN_QUERY_DO_PROC,
            menu_title=title,
            on_close=_close,
            parent=self,
        )
        page._run_query_tab = True  # type: ignore[attr-defined]
        page_holder["w"] = page
        self._work_tabs.addTab(page, title)
        self._work_tabs.setCurrentWidget(page)

    def _open_program(self, do_proc: str) -> None:
        """
        執行 DO_PROC：
        1) 使用同目錄 sys_data.mdb，即時重讀 PROGRAM 取得 WORK_PROC / WORK_FILE / WORK_DB
        2) 以 WORK_PROC 查 columns（DBF_NAME），載入標題、WIDTH、GRID_VIEW、GRID_INDEX 等至字典
        3) 開啟 WORK_DB 上的 WORK_FILE，Grid 依 GRID_VIEW + GRID_INDEX、欄寬依 WIDTH
        """
        if not os.path.isfile(self.mdb_path):
            QMessageBox.warning(
                self,
                "錯誤",
                f"找不到系統資料庫：\n{self.mdb_path}",
            )
            return
        # 即時重讀 PROGRAM（避免選單快取與 sys_data 內容不一致）
        self.program_repo.load()
        self.program_repo.apply_permission_filter(
            self.session.group_level, self.session.company_key
        )

        prg = self.program_repo.find_allowed_program_item(do_proc)
        if prg is None:
            QMessageBox.warning(
                self,
                "開啟作業",
                f"無權限執行此程式或程式不存在：{do_proc}",
            )
            return

        from core.program_dispatch import is_standard_program
        from core.data_import_service import is_data_import_program
        from core.run_query_service import is_run_query_program

        # DATAIMPORT／RUNQUERY：即使 STD_PROC 誤標為 True，仍走專用介面
        if (
            is_data_import_program(do_proc)
            or is_run_query_program(do_proc)
            or not is_standard_program(prg)
        ):
            if self._open_non_standard_program(do_proc, prg):
                return
            if is_data_import_program(do_proc) or is_run_query_program(do_proc):
                return

        binding = self.program_repo.resolve_program_binding(do_proc)
        prg = binding.menu_item or prg
        table_name = binding.work_file
        resolved_proc = binding.rule_proc
        data_prg = binding.data_item
        resolved_prg = self.program_repo.find_by_do_proc(resolved_proc)
        # columns 字典鍵：DBF_NAME = WORK_PROC；實體資料表 = WORK_FILE（table_name）。
        self.data_dict.set_rule_alias(table_name, resolved_proc)
        menu_title = prg.get_title(self.lang) if prg else do_proc

        tx_files = self.program_repo.list_tx_files_by_do_proc(do_proc)
        if not tx_files and resolved_proc:
            tx_files = self.program_repo.list_tx_files_by_do_proc(resolved_proc)
        if not tx_files:
            tx_files = self._parse_tx_files(prg.tx_file if prg else None)
        if not tx_files and resolved_prg is not None:
            tx_files = self._parse_tx_files(resolved_prg.tx_file)
        # TX 明細：優先 columns.DBF_NAME = 明細表名；無定義時才退回 WORK_PROC。
        for tx_table in tx_files:
            self.data_dict.ensure_tx_column_rules(tx_table, resolved_proc)

        # WORK_DB：DO_USER 等選單列常無 WORK_DB，改採 WORK_PROC 對應列的 WORK_DB / CO_KEY。
        db_path, co_err = self._resolve_program_db_path(data_prg or prg)
        if co_err:
            QMessageBox.warning(self, "開啟作業", co_err)
            return
        backend: DbBackendBase
        backend = self._backend_for_db_path(db_path)
        physical = backend.list_columns(table_name)
        if not physical:
            QMessageBox.warning(
                self,
                "開啟作業",
                f"找不到資料表「{table_name}」或無法讀取欄位。\n資料庫：{db_path}",
            )
            return
        grid_fields = self.data_dict.grid_columns_for_table(table_name, physical)
        form_fields = self.data_dict.edit_columns_for_table(table_name, physical)

        def load_data(keyword: str, as_filter: bool):
            return backend.fetch_rows(
                table_name,
                keyword,
                as_filter,
                column_order=physical,
            )

        prog_work_actions = merge_work_action_flags(
            program_work_action_flags(prg),
            program_work_action_flags(resolved_prg),
            program_work_action_flags(data_prg),
        )
        page = WorkPage(
            table_name=table_name,
            field_names=grid_fields,
            data_dict=self.data_dict,
            lang=self.lang,
            load_data_func=load_data,
            backend=backend,
            tx_files=tx_files,
            on_close_tab=lambda: self._close_tab_for_page(page),
            on_detail_tab=lambda vals, old, input_lang, tx_src=None: self._open_record_detail_tab(
                do_proc, table_name, vals, old, tx_files, page, input_lang, tx_src
            ),
            on_query_tab=lambda kind, row, other_title: self._open_query_tab(
                kind, page, row, other_title
            ),
            do_proc=do_proc,
            proc_name=prg.proc_name if prg else None,
            menu_item_title=menu_title,
            form_field_names=form_fields,
            physical_field_names=physical,
            app_base_dir=self.base_dir,
            sys_data_mdb_path=self.mdb_path,
            print_doc_key_column=(
                (resolved_prg.key_code if resolved_prg else None)
                or (prg.key_code if prg else None)
            ),
            user_data_mdb_path=self.user_data_path,
            company_co_key=(self.session.company_key or "GS").strip(),
            group_level=self.session.group_level,
            work_actions=resolve_work_actions_for_program(
                self.data_dict, table_name, do_proc, prg, resolved_prg, data_prg
            ),
            program_work_actions=prog_work_actions,
            login_date=(getattr(self.session, "login_date", "") or "").strip(),
            company_currency=(getattr(self.session, "company_currency", "") or "").strip(),
            parent=self,
        )
        # 記錄 do_proc：供切換語言時更新 Tab 標題
        page._do_proc = do_proc  # type: ignore[attr-defined]
        tab_index = self._work_tabs.addTab(page, menu_title)
        self._work_tabs.setCurrentIndex(tab_index)
        self._colorize_work_tabs()
        self.current_table = table_name
        self._refresh_status_bar()

    def _open_record_detail_tab(
        self,
        do_proc: str,
        table_name: str,
        values: Dict[str, str],
        old_row: List[str],
        tx_files: List[str],
        source_page: WorkPage,
        input_lang: LanguageCode,
        tx_source_row: Optional[List[str]] = None,
    ) -> None:
        from core.record_key_service import resolve_program_number_config

        prg = self.program_repo.find_by_do_proc(do_proc)
        menu_title = prg.get_title(input_lang) if prg else do_proc
        is_new = not any(str(x or "").strip() for x in (old_row or []))
        is_copy = is_new and any(str(x or "").strip() for x in (tx_source_row or []))
        if is_copy:
            detail_mode = "copy"
        elif is_new:
            detail_mode = "add"
        else:
            detail_mode = "edit"
        if detail_mode == "copy":
            suffix = "複製" if input_lang == "CHN" else "Copy"
        elif detail_mode == "add":
            suffix = "新增" if input_lang == "CHN" else "Add"
        else:
            suffix = "明細" if input_lang == "CHN" else "Detail"
        outer_tab_text = f"{menu_title} — {suffix}"
        # RecordDetailPage 上方的 header（非 TAB 標題）不要帶「明細」
        header_title = menu_title
        detail = RecordDetailPage(
            table_name=table_name,
            field_names=source_page.form_field_names,
            values=values,
            old_row=old_row,
            data_dict=self.data_dict,
            lang=input_lang,
            backend=source_page.backend,
            tx_files=tx_files,
            on_saved=source_page.reload_keep_current_row,
            on_close=lambda: self._remove_tab_widget(detail),
            title=header_title,
            menu_item_title=menu_title,
            physical_field_names=source_page.physical_fields,
            key_filter_column=getattr(source_page, "_print_doc_key_column", None),
            app_base_dir=getattr(source_page, "_app_base_dir", None),
            work_actions=getattr(source_page, "_work_actions", None),
            do_proc=do_proc,
            company_co_key=getattr(source_page, "_company_co_key", "") or "",
            print_doc_key_column=getattr(source_page, "_print_doc_key_column", None),
            number_config=resolve_program_number_config(self.program_repo, do_proc),
            tx_source_row=tx_source_row,
            parent=self,
        )
        detail._do_proc = do_proc  # type: ignore[attr-defined]
        detail._detail_mode = detail_mode  # type: ignore[attr-defined]
        idx = self._work_tabs.addTab(detail, outer_tab_text)
        self._work_tabs.setCurrentIndex(idx)
        self._colorize_work_tabs()

    def _open_query_tab(
        self,
        kind: str,
        source_page: WorkPage,
        source_row: List[str],
        other_title: str = "",
        entity_key: str = "",
    ) -> None:
        """在右側工作區新增查詢 TAB（顧客／存貨／賬戶）。"""
        from ui.account_query_dialog import open_account_query
        from ui.party_query_dialog import open_party_query
        from ui.stock_query_dialog import open_stock_query

        kind_u = (kind or "").strip().lower()
        do_proc = source_page.do_proc
        entity_key = (entity_key or "").strip()
        for i in range(self._work_tabs.count()):
            w = self._work_tabs.widget(i)
            if (
                w is not None
                and getattr(w, "_query_kind", None) == kind_u
                and getattr(w, "_do_proc", None) == do_proc
            ):
                # 已開啟的查詢 TAB：切回並強制重讀最新資料
                if hasattr(w, "refresh_from_db"):
                    try:
                        w.refresh_from_db(source_row or [])
                    except Exception:
                        pass
                if entity_key:
                    goto = getattr(w, "goto_entity_key", None) or getattr(
                        w, f"_goto_{kind_u}_key", None
                    )
                    if callable(goto):
                        try:
                            goto(entity_key)
                        except Exception:
                            pass
                self._work_tabs.setCurrentIndex(i)
                return

        page_holder: dict = {"w": None}

        def _close() -> None:
            w = page_holder.get("w")
            if w is not None:
                self._remove_tab_widget(w)

        common = dict(
            backend=source_page.backend,
            do_proc=do_proc,
            source_row=source_row or [],
            source_fields=list(source_page.physical_fields),
            lang=source_page.lang,
            table_name=source_page.table_name,
            other_title=other_title or "",
            data_dict=source_page.data_dict,
            on_close=_close,
            parent=self,
        )
        if kind_u == "account":
            page = open_account_query(**common, account_key=entity_key)
        elif kind_u == "stock":
            page = open_stock_query(**common)
        elif kind_u == "party":
            page = open_party_query(**common)
        else:
            return
        if page is None:
            return
        page_holder["w"] = page
        page._query_kind = kind_u  # type: ignore[attr-defined]
        page._do_proc = do_proc  # type: ignore[attr-defined]
        if entity_key and kind_u != "account":
            goto = getattr(page, "goto_entity_key", None) or getattr(
                page, f"_goto_{kind_u}_key", None
            )
            if callable(goto):
                try:
                    goto(entity_key)
                except Exception:
                    pass
        title = page.tab_title() if hasattr(page, "tab_title") else (other_title or kind_u)
        idx = self._work_tabs.addTab(page, title)
        self._work_tabs.setCurrentIndex(idx)
        self._colorize_work_tabs()

    def _parse_tx_files(self, tx_file_value: str | None) -> List[str]:
        if not tx_file_value:
            return []
        raw = tx_file_value.replace(";", ",").replace("|", ",").replace("，", ",")
        out = []
        for item in raw.split(","):
            name = item.strip()
            if name:
                out.append(name)
        return out

    def _find_ai_tab(self) -> Optional[AiAssistantPage]:
        for i in range(self._work_tabs.count()):
            w = self._work_tabs.widget(i)
            if isinstance(w, AiAssistantPage):
                return w
        return None

    def _find_work_page(self, do_proc: str) -> Optional[WorkPage]:
        key = (do_proc or "").strip().upper()
        if not key:
            return None
        for i in range(self._work_tabs.count()):
            w = self._work_tabs.widget(i)
            if isinstance(w, WorkPage) and str(getattr(w, "_do_proc", "")).upper() == key:
                return w
        return None

    def _active_work_page(self) -> Optional[WorkPage]:
        w = self._work_tabs.currentWidget()
        if isinstance(w, WorkPage):
            return w
        for i in range(self._work_tabs.count() - 1, -1, -1):
            w = self._work_tabs.widget(i)
            if isinstance(w, WorkPage):
                return w
        return None

    def _ai_catalog(self) -> List[Dict[str, str]]:
        from core.ai_assistant_service import catalog_from_programs

        items = getattr(self.program_repo, "_items", None) or []
        return catalog_from_programs(items, self.lang)

    def _ai_context(self) -> Dict[str, str]:
        page = self._work_tabs.currentWidget()
        if not isinstance(page, WorkPage):
            return {"do_proc": "", "table_name": ""}
        return {
            "do_proc": str(getattr(page, "_do_proc", "") or ""),
            "table_name": str(getattr(page, "table_name", "") or ""),
        }

    def _ai_backend(self, do_proc: str, table_name: str):
        page = self._find_work_page(do_proc) if do_proc else None
        if page is None:
            page = self._active_work_page()
        if page is not None:
            return getattr(page, "backend", None)
        return None

    def _focus_or_open_program(self, do_proc: str, title: str = "") -> Optional[WorkPage]:
        page = self._find_work_page(do_proc)
        if page is not None:
            idx = self._work_tabs.indexOf(page)
            if idx >= 0:
                self._work_tabs.setCurrentIndex(idx)
            return page
        self._open_program(do_proc)
        return self._find_work_page(do_proc)

    def _open_ai_tab(self) -> None:
        existing = self._find_ai_tab()
        if existing is not None:
            idx = self._work_tabs.indexOf(existing)
            if idx >= 0:
                self._work_tabs.setCurrentIndex(idx)
            return
        page = AiAssistantPage(
            base_dir=self.base_dir,
            user_no=self.session.user_no,
            lang=self.lang,
            catalog_func=self._ai_catalog,
            context_func=self._ai_context,
            backend_func=self._ai_backend,
            on_actions=self._execute_ai_actions,
            on_save_ai_command=self._save_ai_command_chat,
            related_search_fn=self._ai_related_search,
            parent=self,
        )
        title = "AI"
        idx = self._work_tabs.addTab(page, title)
        self._work_tabs.setCurrentIndex(idx)
        self._colorize_work_tabs()

    def _ai_related_search(
        self,
        keyword: str,
        fields=None,
        include_date: bool = True,
        include_qty: bool = True,
    ) -> dict:
        from services.app_service import AppRuntime, AppService

        rt = AppRuntime(
            base_dir=self.base_dir,
            session=self.session,
            lang=self.lang,
            mdb_path=self.mdb_path,
        )
        rt.data_dict = self.data_dict
        rt.program_repo = self.program_repo
        rt._program_loaded = True
        return AppService(self.base_dir).search_related_records(
            rt,
            keyword,
            fields=fields,
            include_date=include_date,
            include_qty=include_qty,
        )

    def _save_ai_command_chat(self, prompt: str, reply: str = "") -> None:
        from core.ai_command_service import save_ai_command

        rec, err = save_ai_command(
            self.base_dir,
            self.mdb_path,
            user_no=str(self.session.user_no or ""),
            prompt=prompt or "",
            reply=reply or "",
            lang=self.lang,
        )
        if err or rec is None:
            QMessageBox.warning(self, "AI", err or "儲存失敗。")
            return
        chn = str(self.lang).upper().startswith("C")
        QMessageBox.information(
            self,
            "AI",
            "已儲存指令至 AI_COMMAND。" if chn else "Command saved to AI_COMMAND.",
        )

    def _close_all_work_tabs(self, keep_ai: bool = True) -> None:
        for i in range(self._work_tabs.count() - 1, -1, -1):
            w = self._work_tabs.widget(i)
            if keep_ai and isinstance(w, AiAssistantPage):
                continue
            self._work_tabs.removeTab(i)
            if w is not None:
                w.deleteLater()
        self._colorize_work_tabs()
        self.current_table = ""
        self._refresh_status_bar()

    def _export_ai_related_xlsx(
        self,
        keyword: str,
        fields=None,
        include_date: bool = True,
        include_qty: bool = True,
    ) -> None:
        from services.app_service import AppRuntime, AppService

        query = str(keyword or "").strip()
        if not query:
            return
        rt = AppRuntime(
            base_dir=self.base_dir,
            session=self.session,
            lang=self.lang,
            mdb_path=self.mdb_path,
        )
        rt.data_dict = self.data_dict
        rt.program_repo = self.program_repo
        rt._program_loaded = True
        ok, filename, data = AppService(self.base_dir).export_related_records_xlsx(
            rt,
            query,
            fields=fields,
            include_date=include_date,
            include_qty=include_qty,
        )
        if not ok:
            QMessageBox.warning(self, "AI", filename or "匯出 XLSX 失敗。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "匯出 Excel" if self.lang == "CHN" else "Export Excel",
            filename or f"related_{query}.xlsx",
            "Excel (*.xlsx)",
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            with open(path, "wb") as f:
                f.write(data)
        except Exception as ex:
            QMessageBox.warning(self, "AI", str(ex))
            return
        QMessageBox.information(
            self,
            "AI",
            f"已匯出：{path}" if self.lang == "CHN" else f"Exported: {path}",
        )

    def _execute_ai_actions(self, actions: List[Dict[str, str]]) -> None:
        for act in actions or []:
            kind = str(act.get("type") or "").strip().lower()
            do_proc = str(act.get("do_proc") or "").strip()
            title = str(act.get("title") or "")
            if kind == "export_related_xlsx":
                include_date = True
                include_qty = True
                fields = act.get("fields") if isinstance(act.get("fields"), list) else None
                if "include_date" in act:
                    include_date = bool(act.get("include_date"))
                if "include_qty" in act:
                    include_qty = bool(act.get("include_qty"))
                self._export_ai_related_xlsx(
                    str(act.get("keyword") or ""),
                    fields=fields,
                    include_date=include_date,
                    include_qty=include_qty,
                )
                continue
            if kind == "open_work" and do_proc:
                self._focus_or_open_program(do_proc, title)
            elif kind == "close_all_tabs":
                self._close_all_work_tabs(keep_ai=True)
            elif kind == "close_tab":
                page = self._find_work_page(do_proc) if do_proc else self._active_work_page()
                if page is not None:
                    self._close_tab_for_page(page)
            elif kind in {"add", "edit", "copy", "delete", "exit", "print", "query", "search"}:
                page = self._find_work_page(do_proc) if do_proc else None
                if page is None and do_proc:
                    page = self._focus_or_open_program(do_proc, title)
                if page is None:
                    page = self._active_work_page()
                if page is None:
                    continue
                idx = self._work_tabs.indexOf(page)
                if idx >= 0:
                    self._work_tabs.setCurrentIndex(idx)
                if kind == "search":
                    keyword = str(act.get("keyword") or "")
                    txt = getattr(page, "txt_search", None)
                    if txt is not None:
                        txt.setText(keyword)
                    fn = getattr(page, "_on_search_enter", None)
                    if callable(fn):
                        fn()
                    continue
                if kind == "query":
                    from core.query_registry import (
                        extract_entity_key_from_action,
                        resolve_query_kind,
                    )

                    entity_key = extract_entity_key_from_action(act)
                    other_title = ""
                    wa = getattr(page, "_work_actions", None)
                    if wa is not None:
                        other_title = str(getattr(wa, "other_title", "") or "")
                    qk = resolve_query_kind(
                        getattr(page, "do_proc", "") or do_proc,
                        getattr(page, "table_name", "") or "",
                        other_title,
                    )
                    if qk:
                        row = []
                        get_row = getattr(page, "_get_current_full_row", None)
                        if callable(get_row):
                            row = get_row() or []
                        self._open_query_tab(
                            qk, page, row, other_title, entity_key=entity_key
                        )
                        continue
                fn = {
                    "add": getattr(page, "_on_add", None),
                    "edit": getattr(page, "_on_edit", None),
                    "copy": getattr(page, "_on_copy", None),
                    "delete": getattr(page, "_on_delete", None),
                    "exit": getattr(page, "_on_exit", None),
                    "print": getattr(page, "_on_print_preview", None),
                    "query": getattr(page, "_on_other", None),
                }.get(kind)
                if callable(fn):
                    # 搜尋已同步完成；更改／複製等稍後執行以確保列已選取
                    QTimer.singleShot(0, fn)
        self._refresh_status_bar()

    def _on_close_tab(self, index: int) -> None:
        widget = self._work_tabs.widget(index)
        self._work_tabs.removeTab(index)
        if widget is not None:
            widget.deleteLater()
        self.current_table = ""
        self._colorize_work_tabs()
        self._refresh_status_bar()

    def _close_tab_for_page(self, page: QWidget) -> None:
        idx = self._work_tabs.indexOf(page)
        if idx >= 0:
            self._work_tabs.removeTab(idx)
            page.deleteLater()
        self.current_table = ""
        self._colorize_work_tabs()
        self._refresh_status_bar()

    # endregion


