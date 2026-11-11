"""RUNQUERY 執行查詢頁面：多 DB 連線、SQL 執行／更新、結果 GRID。"""
from __future__ import annotations

import os
from typing import Callable, List, Optional, Sequence

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.data_dictionary import DataDictionary, LanguageCode
from core.db_backend import DbBackendBase
from core.db_factory import get_backend_for_path
from core.run_query_service import (
    DB_KIND_ACCESS,
    DB_KIND_MYSQL,
    DB_KIND_SQLITE,
    DB_KIND_SQLSERVER,
    FIELD_CODE,
    FIELD_COMMAND,
    FIELD_DESC,
    RUN_QUERY_DO_PROC,
    RUN_QUERY_TABLE,
    RUN_QUERY_VISIBLE_ROWS,
    DbConnectionSpec,
    db_kind_options,
    default_company_sqlite_spec,
    ensure_run_query_infra,
    execute_sql,
    export_query_result_xlsx,
    filter_result_rows,
    resolve_run_query_data_path,
    save_run_query,
    test_connection,
)
from core.ui_icon_map import icon_from_key
from core.ui_theme import lookup_button_qss
from ui.work_page import (
    apply_nav_button_style,
    apply_work_action_button_style,
    bind_grid_nav_icon_buttons,
    form_editor_style,
    form_label_style,
    format_record_nav_label,
)

_GRID_ROW_H = 24
_GRID_HEADER_PT = 11
_GRID_CELL_PT = 10


def _grid_cell_font() -> QFont:
    f = QFont()
    f.setPointSize(_GRID_CELL_PT)
    f.setWeight(QFont.Weight.Normal)
    return f


def _grid_header_font() -> QFont:
    f = QFont()
    f.setPointSize(_GRID_HEADER_PT)
    f.setWeight(QFont.Weight.Bold)
    return f


def _grid_outer_height(tv: QTableView, visible_rows: int) -> int:
    row_h = _GRID_ROW_H
    vh = tv.verticalHeader()
    vh.setDefaultSectionSize(row_h)
    vh.setMinimumSectionSize(row_h)
    vh.setMaximumSectionSize(row_h)
    vh.setVisible(False)
    hdr = tv.horizontalHeader()
    fm_hdr = QFontMetrics(hdr.font())
    header_h = max(hdr.sizeHint().height(), fm_hdr.height() + 12)
    grid_lines = max(0, visible_rows - 1) if tv.showGrid() else 0
    frame = 2 * max(1, tv.frameWidth())
    return row_h * visible_rows + grid_lines + header_h + frame + 4


class RunQueryResultModel(QAbstractTableModel):
    def __init__(
        self,
        columns: Sequence[str],
        rows: Sequence[Sequence[str]],
        *,
        min_display_rows: int = RUN_QUERY_VISIBLE_ROWS,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._columns = [str(c or "") for c in columns]
        self._rows = [list(r) for r in rows]
        self._min_display_rows = max(0, int(min_display_rows))

    def data_row_count(self) -> int:
        return len(self._rows)

    def _is_padding_row(self, row: int) -> bool:
        return row >= self.data_row_count()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return max(self.data_row_count(), self._min_display_rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return max(1, len(self._columns))

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = ...
    ):
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                if self._columns and 0 <= section < len(self._columns):
                    return self._columns[section]
                return ""
            if role == Qt.ItemDataRole.FontRole:
                return _grid_header_font()
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if orientation == Qt.Orientation.Vertical and role == Qt.ItemDataRole.DisplayRole:
            return section + 1
        return None

    def data(self, index: QModelIndex, role: int = ...) -> object:  # noqa: N802
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        if self._is_padding_row(row):
            if role == Qt.ItemDataRole.DisplayRole:
                return ""
            return None
        if row < 0 or row >= len(self._rows):
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            r = self._rows[row]
            if 0 <= col < len(r):
                return r[col]
            return ""
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.FontRole:
            return _grid_cell_font()
        return None

    def flags(self, index: QModelIndex):  # noqa: N802
        if not index.isValid() or self._is_padding_row(index.row()):
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def set_result(self, columns: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
        self.beginResetModel()
        self._columns = [str(c or "") for c in columns]
        self._rows = [list(r) for r in rows]
        self.endResetModel()


class RunQueryPage(QWidget):
    """執行查詢頁面（嵌入右側 TAB）。"""

    def __init__(
        self,
        *,
        base_dir: str,
        sys_mdb_path: str,
        lang: LanguageCode = "CHN",
        data_dict: Optional[DataDictionary] = None,
        user_no: str = "",
        company_key: str = "GS",
        do_proc: str = RUN_QUERY_DO_PROC,
        menu_title: str = "",
        on_close: Optional[Callable[[], None]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.lang = lang
        self.base_dir = base_dir
        self.sys_mdb_path = sys_mdb_path
        self._data_dict = data_dict
        self._user_no = user_no
        self._company_key = company_key
        self._do_proc = do_proc or RUN_QUERY_DO_PROC
        self._menu_title = menu_title or self._t("執行查詢", "Execute Query")
        self._on_close = on_close
        self._all_columns: List[str] = []
        self._all_rows: List[List[str]] = []
        self._view_rows: List[List[str]] = []
        self._keyword = ""
        self._selected_row: Optional[int] = None
        self._connected = False

        ok, err = ensure_run_query_infra(base_dir, sys_mdb_path)
        if not ok:
            QMessageBox.warning(self, self._t("執行查詢", "Execute Query"), err or "")

        self._build_ui()
        self._load_default_connection()
        self._refresh_nav()

    def _t(self, chn: str, eng: str) -> str:
        return chn if str(self.lang or "").upper().startswith("C") else eng

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QLabel(self._menu_title)
        title.setStyleSheet("font-size: 14pt; font-weight: 700; color: #1b3b6f;")
        layout.addWidget(title)

        # 資料庫類型與連線
        db_row = QHBoxLayout()
        db_row.addWidget(QLabel(self._t("資料庫:", "Database:")))
        self.cbo_kind = QComboBox()
        for opt in db_kind_options(chn=str(self.lang).upper().startswith("C")):
            self.cbo_kind.addItem(opt["label"], opt["kind"])
        self.cbo_kind.currentIndexChanged.connect(self._on_kind_changed)
        db_row.addWidget(self.cbo_kind)

        self.btn_connect = QPushButton(self._t("連線", "Connect"))
        apply_work_action_button_style(self.btn_connect)
        self.btn_connect.setIcon(icon_from_key(self.style(), "connect"))
        self.btn_connect.clicked.connect(self._on_connect)
        db_row.addWidget(self.btn_connect)
        self.lbl_conn = QLabel("")
        self.lbl_conn.setStyleSheet("color: #555;")
        db_row.addWidget(self.lbl_conn, 1)
        layout.addLayout(db_row)

        self.conn_stack = QStackedWidget()
        # page 0: file (sqlite/access)
        file_page = QWidget()
        fl = QHBoxLayout(file_page)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.addWidget(QLabel(self._t("檔案:", "File:")))
        self.txt_path = QLineEdit()
        self.txt_path.setStyleSheet(form_editor_style())
        fl.addWidget(self.txt_path, 1)
        self.btn_browse = QPushButton("…")
        self.btn_browse.setFixedSize(28, 28)
        self.btn_browse.setStyleSheet(lookup_button_qss())
        self.btn_browse.clicked.connect(self._on_browse)
        fl.addWidget(self.btn_browse)
        self.conn_stack.addWidget(file_page)

        # page 1: server (sqlserver/mysql)
        srv_page = QWidget()
        form = QFormLayout(srv_page)
        form.setContentsMargins(0, 0, 0, 0)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.txt_host = QLineEdit("localhost")
        self.spn_port = QSpinBox()
        self.spn_port.setRange(0, 65535)
        self.spn_port.setSpecialValueText("—")
        self.txt_database = QLineEdit()
        self.txt_user = QLineEdit()
        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        for w in (self.txt_host, self.txt_database, self.txt_user, self.txt_password):
            w.setStyleSheet(form_editor_style())
        form.addRow(self._t("主機:", "Host:"), self.txt_host)
        form.addRow(self._t("連接埠:", "Port:"), self.spn_port)
        form.addRow(self._t("資料庫名:", "Database:"), self.txt_database)
        form.addRow(self._t("使用者:", "User:"), self.txt_user)
        form.addRow(self._t("密碼:", "Password:"), self.txt_password)
        self.conn_stack.addWidget(srv_page)
        layout.addWidget(self.conn_stack)

        sql_lab = QLabel(self._t("SQL 指令", "SQL command"))
        sql_lab.setStyleSheet(form_label_style())
        layout.addWidget(sql_lab)
        self.txt_sql = QTextEdit()
        self.txt_sql.setAcceptRichText(False)
        self.txt_sql.setPlaceholderText(
            self._t("輸入 SELECT／UPDATE／INSERT／DELETE …", "Enter SELECT / UPDATE / INSERT / DELETE …")
        )
        self.txt_sql.setStyleSheet(form_editor_style())
        self.txt_sql.setMinimumHeight(90)
        self.txt_sql.setMaximumHeight(160)
        layout.addWidget(self.txt_sql)

        act = QHBoxLayout()
        self.btn_lookup = QPushButton(self._t("查閱", "Lookup"))
        apply_work_action_button_style(self.btn_lookup)
        self.btn_lookup.setIcon(icon_from_key(self.style(), "search"))
        self.btn_lookup.clicked.connect(self._on_lookup)
        act.addWidget(self.btn_lookup)

        self.btn_save = QPushButton(self._t("儲存", "Save"))
        apply_work_action_button_style(self.btn_save)
        self.btn_save.setIcon(icon_from_key(self.style(), "save"))
        self.btn_save.clicked.connect(self._on_save)
        act.addWidget(self.btn_save)

        self.btn_run = QPushButton(self._t("執行", "Run"))
        apply_work_action_button_style(self.btn_run)
        self.btn_run.setIcon(icon_from_key(self.style(), "search"))
        self.btn_run.clicked.connect(self._on_run)
        act.addWidget(self.btn_run)

        self.btn_export = QPushButton(self._t("匯出 Excel", "Export Excel"))
        apply_work_action_button_style(self.btn_export)
        self.btn_export.setIcon(icon_from_key(self.style(), "print"))
        self.btn_export.clicked.connect(self._on_export)
        act.addWidget(self.btn_export)

        self.btn_exit = QPushButton(self._t("離開", "Exit"))
        apply_work_action_button_style(self.btn_exit)
        self.btn_exit.setIcon(icon_from_key(self.style(), "exit"))
        self.btn_exit.clicked.connect(self._on_exit)
        act.addWidget(self.btn_exit)
        act.addStretch(1)
        layout.addLayout(act)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel(self._t("搜尋:", "Search:")))
        self.txt_search = QLineEdit()
        self.txt_search.returnPressed.connect(self._on_search)
        search_row.addWidget(self.txt_search, 1)
        self.btn_search = QPushButton(self._t("搜尋", "Search"))
        apply_work_action_button_style(self.btn_search)
        self.btn_search.setIcon(icon_from_key(self.style(), "search"))
        self.btn_search.clicked.connect(self._on_search)
        self.btn_clear_search = QPushButton(self._t("清除", "Clear"))
        apply_work_action_button_style(self.btn_clear_search)
        self.btn_clear_search.clicked.connect(self._on_clear_search)
        search_row.addWidget(self.btn_search)
        search_row.addWidget(self.btn_clear_search)
        layout.addLayout(search_row)

        grid_nav = QHBoxLayout()
        self.btn_first = QPushButton()
        self.btn_prev = QPushButton()
        self.btn_next = QPushButton()
        self.btn_last = QPushButton()
        for b in (self.btn_first, self.btn_prev, self.btn_next, self.btn_last):
            apply_nav_button_style(b)
        bind_grid_nav_icon_buttons(
            self.lang,
            self.style(),
            self.btn_first,
            self.btn_prev,
            self.btn_next,
            self.btn_last,
        )
        self.btn_first.clicked.connect(lambda: self._nav_row(0))
        self.btn_prev.clicked.connect(
            lambda: self._nav_row((self._selected_row or 0) - 1)
        )
        self.btn_next.clicked.connect(
            lambda: self._nav_row(
                (self._selected_row if self._selected_row is not None else -1) + 1
            )
        )
        self.btn_last.clicked.connect(
            lambda: self._nav_row(len(self._view_rows) - 1)
        )
        grid_nav.addWidget(self.btn_first)
        grid_nav.addWidget(self.btn_prev)
        grid_nav.addWidget(self.btn_next)
        grid_nav.addWidget(self.btn_last)
        self.lbl_nav = QLabel()
        self.lbl_nav.setStyleSheet("font-weight: 700; color: #1b3b6f;")
        grid_nav.addWidget(self.lbl_nav, 1)
        layout.addLayout(grid_nav)

        self.grid = QTableView()
        self._configure_grid(self.grid)
        self._model = RunQueryResultModel([], [], min_display_rows=RUN_QUERY_VISIBLE_ROWS)
        self.grid.setModel(self._model)
        sel = self.grid.selectionModel()
        if sel is not None:
            sel.selectionChanged.connect(lambda *_: self._on_selection_changed())
        layout.addWidget(self.grid, 1)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #555;")
        layout.addWidget(self.lbl_status)

        self._on_kind_changed()

    def _configure_grid(self, tv: QTableView) -> None:
        visible = RUN_QUERY_VISIBLE_ROWS
        tv.setObjectName("appGridTable")
        tv.setStyleSheet(
            "#appGridTable::item { padding-top: 0px; padding-bottom: 0px; "
            "padding-left: 6px; padding-right: 6px; }"
        )
        tv.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tv.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tv.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tv.setAlternatingRowColors(True)
        tv.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        tv.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        tv.setFont(_grid_cell_font())
        hdr = tv.horizontalHeader()
        hdr.setFont(_grid_header_font())
        tv.setMinimumHeight(_grid_outer_height(tv, visible))
        tv.setMaximumHeight(_grid_outer_height(tv, visible))
        tv.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _current_kind(self) -> str:
        return str(self.cbo_kind.currentData() or DB_KIND_SQLITE)

    def _on_kind_changed(self, *_args) -> None:
        kind = self._current_kind()
        if kind in (DB_KIND_SQLITE, DB_KIND_ACCESS):
            self.conn_stack.setCurrentIndex(0)
        else:
            self.conn_stack.setCurrentIndex(1)
            if kind == DB_KIND_MYSQL and self.spn_port.value() == 0:
                self.spn_port.setValue(3306)
            elif kind == DB_KIND_SQLSERVER and self.spn_port.value() in (0, 3306):
                self.spn_port.setValue(1433)
        self._connected = False
        self.lbl_conn.setText("")

    def _load_default_connection(self) -> None:
        spec = default_company_sqlite_spec(self.base_dir, self._company_key)
        kind = spec.normalized_kind()
        idx = self.cbo_kind.findData(kind)
        if idx >= 0:
            self.cbo_kind.setCurrentIndex(idx)
        self.txt_path.setText(spec.path or "")
        self._on_kind_changed()

    def _build_spec(self) -> DbConnectionSpec:
        kind = self._current_kind()
        if kind in (DB_KIND_SQLITE, DB_KIND_ACCESS):
            return DbConnectionSpec(kind=kind, path=self.txt_path.text().strip())
        return DbConnectionSpec(
            kind=kind,
            host=self.txt_host.text().strip() or "localhost",
            port=int(self.spn_port.value()),
            database=self.txt_database.text().strip(),
            user=self.txt_user.text().strip(),
            password=self.txt_password.text(),
        )

    def _on_browse(self) -> None:
        kind = self._current_kind()
        if kind == DB_KIND_ACCESS:
            filt = "Access (*.mdb *.accdb);;All (*.*)"
        else:
            filt = "SQLite (*.sqlite *.db);;All (*.*)"
        path, _ = QFileDialog.getOpenFileName(
            self, self._t("選擇資料庫", "Select database"), self.txt_path.text(), filt
        )
        if path:
            self.txt_path.setText(path)
            self._connected = False

    def _on_connect(self) -> None:
        spec = self._build_spec()
        ok, msg = test_connection(spec)
        self._connected = ok
        self.lbl_conn.setText(msg)
        if not ok:
            QMessageBox.warning(self, self._t("連線", "Connect"), msg)

    def _user_data_backend(self) -> Optional[DbBackendBase]:
        path = resolve_run_query_data_path(self.base_dir)
        if not path or not os.path.isfile(path):
            return None
        return get_backend_for_path(path)

    def _on_lookup(self) -> None:
        from ui.lookup_dialog import LookupPickerDialog

        ensure_run_query_infra(self.base_dir, self.sys_mdb_path)
        backend = self._user_data_backend()
        if backend is None or not backend.list_columns(RUN_QUERY_TABLE):
            QMessageBox.warning(
                self,
                self._t("查閱", "Lookup"),
                self._t("找不到 USER_DATA.RUN_QUERY。", "USER_DATA.RUN_QUERY missing."),
            )
            return
        dd = self._data_dict
        if dd is None:
            dd = DataDictionary(self.sys_mdb_path)
            try:
                dd.load()
            except Exception:
                pass
        try:
            dd.load_columns_for_dbf(RUN_QUERY_TABLE)
        except Exception:
            pass
        dlg = LookupPickerDialog(
            lookup_db=RUN_QUERY_TABLE,
            lookup_ret=FIELD_COMMAND,
            backend=backend,
            data_dict=dd,
            lang=self.lang,
            parent=self,
            app_base_dir=self.base_dir,
        )
        if not dlg.exec():
            return
        sql = (dlg.selected_value or "").strip()
        if not sql and dlg.selected_row and getattr(dlg, "_grid_fields", None):
            try:
                idx = [str(f).upper() for f in dlg._grid_fields].index(FIELD_COMMAND)
                sql = str(dlg.selected_row[idx] or "").strip()
            except Exception:
                sql = ""
        if sql:
            self.txt_sql.setPlainText(sql)
        try:
            if dlg.selected_row and dlg._grid_fields:
                fi = [str(f).upper() for f in dlg._grid_fields]
                code = str(dlg.selected_row[fi.index(FIELD_CODE)] or "") if FIELD_CODE in fi else ""
                desc = str(dlg.selected_row[fi.index(FIELD_DESC)] or "") if FIELD_DESC in fi else ""
                if code or desc:
                    self.lbl_status.setText(
                        self._t(f"已載入：{code} {desc}", f"Loaded: {code} {desc}").strip()
                    )
        except Exception:
            pass

    def _on_save(self) -> None:
        sql = self.txt_sql.toPlainText().strip()
        if not sql:
            QMessageBox.information(
                self,
                self._t("儲存", "Save"),
                self._t("請先輸入 SQL 指令。", "Please enter SQL first."),
            )
            return
        desc, ok = QInputDialog.getText(
            self,
            self._t("儲存查詢", "Save query"),
            self._t("說明：", "Description:"),
        )
        if not ok:
            return
        rec, err = save_run_query(
            self.base_dir,
            self.sys_mdb_path,
            sql=sql,
            description=desc or "",
            user_no=self._user_no,
        )
        if err or rec is None:
            QMessageBox.warning(self, self._t("儲存", "Save"), err or "儲存失敗。")
            return
        QMessageBox.information(
            self,
            self._t("儲存", "Save"),
            self._t(
                f"已儲存至 RUN_QUERY：{rec.get('qry_code', '')}",
                f"Saved to RUN_QUERY: {rec.get('qry_code', '')}",
            ),
        )

    def _on_run(self) -> None:
        spec = self._build_spec()
        if not self._connected:
            ok, msg = test_connection(spec)
            if not ok:
                QMessageBox.warning(self, self._t("執行", "Run"), msg)
                return
            self._connected = True
            self.lbl_conn.setText(msg)
        data, err = execute_sql(spec, self.txt_sql.toPlainText())
        if err or data is None:
            QMessageBox.warning(self, self._t("執行", "Run"), err or "執行失敗。")
            return
        self._all_columns = list(data.columns or [])
        self._all_rows = [list(r) for r in (data.rows or [])]
        self._keyword = ""
        self.txt_search.clear()
        self._apply_view()
        self.lbl_status.setText(data.message or "")

    def _on_search(self) -> None:
        self._keyword = self.txt_search.text().strip()
        self._apply_view()

    def _on_clear_search(self) -> None:
        self.txt_search.clear()
        self._keyword = ""
        self._apply_view()

    def _apply_view(self) -> None:
        self._view_rows = filter_result_rows(
            self._all_columns, self._all_rows, self._keyword
        )
        self._model.set_result(self._all_columns, self._view_rows)
        if self._view_rows:
            self._nav_row(0)
        else:
            self._selected_row = None
            self.grid.clearSelection()
            self._refresh_nav()

    def _on_selection_changed(self) -> None:
        idxs = self.grid.selectionModel().selectedRows() if self.grid.selectionModel() else []
        if not idxs:
            return
        row = idxs[0].row()
        if row < 0 or row >= len(self._view_rows):
            return
        self._selected_row = row
        self._refresh_nav()

    def _nav_row(self, row: int) -> None:
        n = len(self._view_rows)
        if n <= 0:
            self._selected_row = None
            self.grid.clearSelection()
            self._refresh_nav()
            return
        row = max(0, min(n - 1, int(row)))
        self._selected_row = row
        self.grid.selectRow(row)
        self.grid.scrollTo(self._model.index(row, 0))
        self._refresh_nav()

    def _refresh_nav(self) -> None:
        total = len(self._view_rows)
        cur = None if self._selected_row is None else self._selected_row + 1
        self.lbl_nav.setText(format_record_nav_label(total, cur))
        has = total > 0
        self.btn_first.setEnabled(has and (self._selected_row or 0) > 0)
        self.btn_prev.setEnabled(has and (self._selected_row or 0) > 0)
        self.btn_next.setEnabled(
            has and self._selected_row is not None and self._selected_row < total - 1
        )
        self.btn_last.setEnabled(
            has and self._selected_row is not None and self._selected_row < total - 1
        )
        self.btn_export.setEnabled(bool(self._all_rows))

    def _on_export(self) -> None:
        rows = self._view_rows if self._view_rows else self._all_rows
        if not rows:
            QMessageBox.information(
                self,
                self._t("匯出", "Export"),
                self._t("沒有可匯出的結果。", "No result to export."),
            )
            return
        ok, name, data = export_query_result_xlsx(
            self._all_columns, rows, filename_stem="run_query"
        )
        if not ok:
            QMessageBox.warning(self, self._t("匯出", "Export"), name)
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            self._t("匯出 Excel", "Export Excel"),
            name,
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
            QMessageBox.warning(self, self._t("匯出", "Export"), str(ex))
            return
        QMessageBox.information(
            self,
            self._t("匯出", "Export"),
            self._t(f"已匯出：{path}", f"Exported: {path}"),
        )

    def _on_exit(self) -> None:
        if self._on_close:
            self._on_close()


def open_run_query(
    *,
    base_dir: str,
    sys_mdb_path: str,
    lang: LanguageCode = "CHN",
    data_dict: Optional[DataDictionary] = None,
    user_no: str = "",
    company_key: str = "GS",
    do_proc: str = RUN_QUERY_DO_PROC,
    menu_title: str = "",
    on_close: Optional[Callable[[], None]] = None,
    parent=None,
) -> RunQueryPage:
    return RunQueryPage(
        base_dir=base_dir,
        sys_mdb_path=sys_mdb_path,
        lang=lang,
        data_dict=data_dict,
        user_no=user_no,
        company_key=company_key,
        do_proc=do_proc,
        menu_title=menu_title,
        on_close=on_close,
        parent=parent,
    )
