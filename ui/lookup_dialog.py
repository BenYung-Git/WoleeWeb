"""LOOKUP 選取對話框：顯示 LOOKUP_DB 對應表，回傳 LOOKUP_RET 欄位值。"""
from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import Qt, QModelIndex
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from core.data_dictionary import DataDictionary, LanguageCode
from core.db_backend import DbBackendBase
from core.ui_icon_map import icon_from_key


class LookupPickerDialog(QDialog):
    """以 Grid 顯示 LOOKUP_DB，雙擊／確定後回傳 LOOKUP_RET 值。"""

    def __init__(
        self,
        *,
        lookup_db: str,
        lookup_ret: str,
        backend: DbBackendBase,
        data_dict: DataDictionary,
        lang: LanguageCode = "CHN",
        parent: Optional[QWidget] = None,
        app_base_dir: Optional[str] = None,
        row_filter=None,
    ) -> None:
        super().__init__(parent)
        from ui.work_page import (
            SimpleTableModel,
            apply_grid_column_width_limits,
            apply_nav_button_style,
            apply_work_action_button_style,
            bind_grid_nav_icon_buttons,
            configure_grid_table_view,
            format_record_nav_label,
            _GRID_VISIBLE_ROWS_MAIN,
        )

        self._SimpleTableModel = SimpleTableModel
        self._apply_grid_column_width_limits = apply_grid_column_width_limits
        self._apply_work_action_button_style = apply_work_action_button_style
        self._apply_nav_button_style = apply_nav_button_style
        self._bind_grid_nav_icon_buttons = bind_grid_nav_icon_buttons
        self._format_record_nav_label = format_record_nav_label
        self._configure_grid_table_view = configure_grid_table_view
        self._visible_rows = _GRID_VISIBLE_ROWS_MAIN

        self._lookup_db = (lookup_db or "").strip()
        self._lookup_ret = (lookup_ret or "").strip() or self._lookup_db
        self._backend = backend
        self._data_dict = data_dict
        self._lang = lang
        self._app_base_dir = app_base_dir
        self._row_filter = row_filter
        self.selected_value = ""
        self.selected_row: Optional[List[str]] = None

        title = "查找" if lang == "CHN" else "Lookup"
        self.setWindowTitle(f"{title} — {self._lookup_db}")
        self.resize(720, 480)

        data_dict.load_columns_for_dbf(self._lookup_db)
        self._physical = backend.list_columns(self._lookup_db) if backend else []
        self._grid_fields = (
            data_dict.grid_columns_for_table(self._lookup_db, self._physical)
            if self._physical
            else []
        )
        if not self._grid_fields and self._physical:
            self._grid_fields = list(self._physical)

        self._all_rows: List[List[str]] = []
        self._phys_indices: List[int] = []
        for name in self._grid_fields:
            try:
                self._phys_indices.append(
                    next(
                        i
                        for i, p in enumerate(self._physical)
                        if (p or "").strip().upper() == (name or "").strip().upper()
                    )
                )
            except StopIteration:
                self._phys_indices.append(0)

        layout = QVBoxLayout(self)
        search_row = QHBoxLayout()
        self._txt_search = QLineEdit()
        self._txt_search.setPlaceholderText(
            "搜尋…" if lang == "CHN" else "Search…"
        )
        btn_search = QPushButton("搜尋" if lang == "CHN" else "Search")
        btn_search.setIcon(icon_from_key(self.style(), "search"))
        self._apply_work_action_button_style(btn_search)
        btn_search.clicked.connect(self._on_search)
        self._txt_search.returnPressed.connect(self._on_search)
        search_row.addWidget(self._txt_search, 1)
        search_row.addWidget(btn_search)
        layout.addLayout(search_row)

        self._table = QTableView()
        self._configure_grid_table_view(
            self._table, self._visible_rows, app_base_dir
        )
        self._table.doubleClicked.connect(self._on_activate)
        layout.addWidget(self._table, 1)

        # 資料瀏覽圖示／樣式與輸入介面 Grid 一致
        nav = QHBoxLayout()
        nav.setSpacing(8)
        self._btn_nav_first = QPushButton()
        self._btn_nav_prev = QPushButton()
        self._btn_nav_next = QPushButton()
        self._btn_nav_last = QPushButton()
        for nb in (
            self._btn_nav_first,
            self._btn_nav_prev,
            self._btn_nav_next,
            self._btn_nav_last,
        ):
            self._apply_nav_button_style(nb)
        self._bind_grid_nav_icon_buttons(
            self._lang,
            self.style(),
            self._btn_nav_first,
            self._btn_nav_prev,
            self._btn_nav_next,
            self._btn_nav_last,
        )
        self._btn_nav_first.clicked.connect(lambda: self._nav(0))
        self._btn_nav_prev.clicked.connect(lambda: self._nav_rel(-1))
        self._btn_nav_next.clicked.connect(lambda: self._nav_rel(1))
        self._btn_nav_last.clicked.connect(lambda: self._nav(-1))
        nav.addWidget(self._btn_nav_first)
        nav.addWidget(self._btn_nav_prev)
        nav.addWidget(self._btn_nav_next)
        nav.addWidget(self._btn_nav_last)
        self._lbl_count = QLabel("")
        self._lbl_count.setStyleSheet(
            "font-size: 11pt; font-weight: 700; color: #1b3b6f;"
        )
        nav.addWidget(self._lbl_count, 1)
        layout.addLayout(nav)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        sm = self._table.selectionModel()
        if sm is not None:
            sm.selectionChanged.connect(lambda *_a: self._refresh_nav_ui())
        self._reload("")

    def _headers(self) -> List[str]:
        return [
            self._data_dict.get_title(self._lookup_db, f, self._lang)
            for f in self._grid_fields
        ]

    def _reload(self, keyword: str) -> None:
        if not self._backend or not self._lookup_db:
            self._all_rows = []
        else:
            self._all_rows = self._backend.fetch_rows(
                self._lookup_db, keyword or "", False, column_order=self._physical
            )
            if callable(self._row_filter):
                self._all_rows = [
                    r
                    for r in self._all_rows
                    if self._row_filter(self._physical, r)
                ]
        model = self._SimpleTableModel(
            self._headers(),
            self._all_rows,
            self,
            self._phys_indices,
            self._grid_fields,
            [],
            self._data_dict,
            self._lookup_db,
            editable=False,
            physical_column_count=len(self._physical),
            min_display_rows=0,
        )
        self._table.setModel(model)
        self._apply_grid_column_width_limits(self._table)
        # 換 model 後需重新接上選取變更，才能更新導覽按鈕狀態
        sm = self._table.selectionModel()
        if sm is not None:
            sm.selectionChanged.connect(lambda *_a: self._refresh_nav_ui())
        n = (
            model.data_row_count()
            if hasattr(model, "data_row_count")
            else len(self._all_rows)
        )
        if n > 0:
            self._table.selectRow(0)
        self._refresh_nav_ui()

    def _refresh_nav_ui(self) -> None:
        model = self._table.model()
        n = 0
        if model is not None:
            n = (
                model.data_row_count()
                if hasattr(model, "data_row_count")
                else model.rowCount()
            )
        idx = self._table.currentIndex()
        row = idx.row() if idx.isValid() else -1
        cur = (row + 1) if row >= 0 else None
        self._lbl_count.setText(self._format_record_nav_label(n, cur))
        has_rows = n > 0
        no_sel = row < 0
        self._btn_nav_first.setEnabled(has_rows and (no_sel or row > 0))
        self._btn_nav_prev.setEnabled(has_rows and not no_sel and row > 0)
        self._btn_nav_next.setEnabled(has_rows and not no_sel and row < n - 1)
        self._btn_nav_last.setEnabled(has_rows and (no_sel or row < n - 1))

    def _on_search(self) -> None:
        kw = self._txt_search.text().strip()
        self._reload("")
        model = self._table.model()
        if model is None or not kw:
            return
        kw_l = kw.lower()
        for r in range(model.rowCount()):
            for c in range(model.columnCount()):
                idx = model.index(r, c)
                val = str(model.data(idx, Qt.ItemDataRole.DisplayRole) or "").lower()
                if kw_l in val:
                    self._table.selectRow(r)
                    self._table.scrollTo(idx)
                    return

    def _nav(self, row: int) -> None:
        model = self._table.model()
        if model is None:
            return
        n = (
            model.data_row_count()
            if hasattr(model, "data_row_count")
            else model.rowCount()
        )
        if n <= 0:
            return
        if row < 0:
            row = n - 1
        row = max(0, min(row, n - 1))
        self._table.selectRow(row)
        self._refresh_nav_ui()

    def _nav_rel(self, delta: int) -> None:
        idx = self._table.currentIndex()
        row = idx.row() if idx.isValid() else 0
        self._nav(row + delta)

    def _ret_value_from_row(self, row: int) -> str:
        if row < 0 or row >= len(self._all_rows):
            return ""
        full = self._all_rows[row]
        ret = (self._lookup_ret or "").strip().upper()
        for i, name in enumerate(self._physical):
            if (name or "").strip().upper() == ret and i < len(full):
                return str(full[i] or "").strip()
        if self._phys_indices and self._phys_indices[0] < len(full):
            return str(full[self._phys_indices[0]] or "").strip()
        return str(full[0] if full else "").strip()

    def _on_activate(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        self.selected_value = self._ret_value_from_row(index.row())
        if index.row() >= 0 and index.row() < len(self._all_rows):
            self.selected_row = list(self._all_rows[index.row()])
        if self.selected_value:
            self.accept()

    def _on_ok(self) -> None:
        idx = self._table.currentIndex()
        if not idx.isValid():
            return
        self.selected_value = self._ret_value_from_row(idx.row())
        if idx.row() >= 0 and idx.row() < len(self._all_rows):
            self.selected_row = list(self._all_rows[idx.row()])
        if self.selected_value:
            self.accept()