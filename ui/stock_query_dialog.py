"""存貨查詢對話框。"""
from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from PyQt6.QtCore import QAbstractTableModel, QDate, QModelIndex, Qt, QTimer
from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCalendarWidget,
    QCheckBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.data_dictionary import DataDictionary, LanguageCode
from core.db_backend import DbBackendBase
from core.display_format import APP_DATE_QT_FORMAT, parse_qdate
from core.stock_query_service import (
    TX_KIND_OPTIONS,
    StockQueryDocument,
    StockQueryLine,
    current_stock,
    filter_stock_lines,
    find_line_index,
    find_stock_index,
    load_stock_query,
    normalize_date_text,
    normalize_tx_kinds,
    totals_dict,
)
from core.ui_icon_map import icon_from_key
from ui.work_page import (
    _FORM_EDITOR_WIDTH_PX,
    _FORM_LABEL_WIDTH_MIN_PX,
    _apply_uniform_form_label_widths,
    _font_base_dir_for,
    _form_label_caption,
    _wrap_lookup_field_editor,
    apply_nav_button_style,
    apply_work_action_button_style,
    bind_grid_nav_icon_buttons,
    form_editor_style,
    form_label_style,
    format_record_nav_label,
)

_GRID_VISIBLE_ROWS = 15
_GRID_ROW_H = 24
_GRID_HEADER_PT = 11
_GRID_CELL_PT = 10
_HEADER_COLS = 2


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


def _align_for_col(col: int) -> int:
    # 日期/類別/編號/單位/重量單位/貨倉靠左；數量/重量/單價/金額靠右
    if col in {3, 5, 8, 9, 10, 11}:
        return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)


class StockQueryGridModel(QAbstractTableModel):
    COLS = (
        "date",
        "tx_category",
        "tx_key",
        "qty",
        "unit",
        "weight",
        "wgt_unit",
        "warehouse",
        "unit_price",
        "amount",
        "unit_cost",
        "cost_amt",
    )

    def __init__(
        self,
        lines: List[StockQueryLine],
        headers: List[str],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._lines = list(lines)
        self._headers = list(headers)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._lines)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self.COLS)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = ...
    ):
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                if 0 <= section < len(self._headers):
                    return self._headers[section]
                return ""
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return _align_for_col(section)
        if orientation == Qt.Orientation.Vertical and role == Qt.ItemDataRole.DisplayRole:
            return section + 1
        return None

    def data(self, index: QModelIndex, role: int = ...) -> object:  # noqa: N802
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        if row < 0 or row >= len(self._lines) or col < 0 or col >= len(self.COLS):
            return None
        ln = self._lines[row]
        if role == Qt.ItemDataRole.DisplayRole:
            return getattr(ln, self.COLS[col], "") or ""
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return _align_for_col(col)
        return None

    def set_lines(self, lines: List[StockQueryLine]) -> None:
        self.beginResetModel()
        self._lines = list(lines)
        self.endResetModel()


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


def _configure_grid(tv: QTableView) -> None:
    visible = _GRID_VISIBLE_ROWS
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


class _DatePickPopup(QDialog):
    def __init__(self, parent=None, initial: str = "", *, chn: bool = True) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        self._picked = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self._cal = QCalendarWidget(self)
        d = parse_qdate(initial) if (initial or "").strip() else None
        if d is not None:
            self._cal.setSelectedDate(QDate(d.year, d.month, d.day))
        else:
            self._cal.setSelectedDate(QDate.currentDate())
        self._cal.clicked.connect(self._on_picked)
        layout.addWidget(self._cal)
        clear_btn = QPushButton("清除" if chn else "Clear")
        clear_btn.clicked.connect(self._on_clear)
        layout.addWidget(clear_btn)

    def _on_picked(self, qd: QDate) -> None:
        self._picked = qd.toString(APP_DATE_QT_FORMAT)
        self.accept()

    def _on_clear(self) -> None:
        self._picked = ""
        self.accept()

    @property
    def picked(self) -> str:
        return self._picked


class StockQueryDialog(QWidget):
    """存貨查詢頁面（可嵌入右側 TAB）。"""

    def __init__(
        self,
        backend: DbBackendBase,
        do_proc: str,
        source_row: List[str],
        source_fields: List[str],
        lang: LanguageCode = "CHN",
        table_name: str = "",
        other_title: str = "",
        data_dict: Optional[DataDictionary] = None,
        on_close: Optional[Callable[[], None]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.lang = lang
        self.backend = backend
        self._data_dict = data_dict
        self._on_close = on_close
        self._do_proc = do_proc
        self._source_row = list(source_row)
        self._source_fields = list(source_fields)
        self._table_name = table_name
        self._other_title = other_title
        self._doc: Optional[StockQueryDocument] = None
        self._all_lines: List[StockQueryLine] = []
        self._keyword = ""
        self._filter_keyword = ""
        self._selected_row: Optional[int] = None
        self._ready = False
        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(250)
        self._reload_timer.timeout.connect(self._reload_transactions)
        self._ui_ready = False
        self._skip_next_show_refresh = True

        doc, err = load_stock_query(
            backend,
            do_proc,
            source_row,
            source_fields,
            table_name=table_name,
            other_title=other_title,
        )
        if err or doc is None:
            QMessageBox.warning(
                parent or self,
                "查詢" if lang == "CHN" else "Query",
                err or ("無法載入查詢資料。" if lang == "CHN" else "Cannot load query data."),
            )
            return
        self._doc = doc
        self._all_lines = list(doc.lines)
        self._ready = True
        self._tab_title = (other_title or "").strip() or (
            "存貨查詢" if lang == "CHN" else "Stock Query"
        )
        self.setWindowTitle(self._tab_title)
        self._build_ui()
        self._apply_line_filter()
        self._refresh_totals()
        self._refresh_stock_nav()

    def tab_title(self) -> str:
        return getattr(self, "_tab_title", self._t("查詢", "Query"))

    def _request_close(self) -> None:
        if callable(self._on_close):
            self._on_close()
            return
        w = self.window()
        if isinstance(w, QDialog):
            w.reject()

    def _t(self, chn: str, eng: str) -> str:
        return chn if self.lang == "CHN" else eng

    def _grid_headers(self) -> List[str]:
        if self.lang == "CHN":
            return [
                "日期",
                "交易類別",
                "交易編號",
                "數量",
                "單位",
                "重量",
                "重量單位",
                "貨倉",
                "單價",
                "金額",
                "單位成本",
                "成本金額",
            ]
        return [
            "Date",
            "Type",
            "Doc No.",
            "Qty",
            "Unit",
            "Weight",
            "Wgt Unit",
            "Loc",
            "Price",
            "Amount",
            "Unit Cost",
            "Cost Amt",
        ]

    def _stock_field_specs(self) -> List[Tuple[str, str, str]]:
        assert self._doc is not None
        s = current_stock(self._doc)
        return [
            ("KEY", self._t("存貨編號", "Stock No."), s.key),
            ("CAT", self._t("存貨分類", "Category"), s.category),
            ("BRAND", self._t("牌子名稱", "Brand"), s.brand),
            ("MODEL", self._t("型號", "Model"), s.model),
            ("DESC", self._t("說明", "Description"), s.desc),
        ]

    def _build_header_panel(self) -> QWidget:
        base_dir = _font_base_dir_for(self)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        labels_by_field: dict[str, QLabel] = {}
        raw_titles: dict[str, str] = {}
        editors: dict[str, QLineEdit] = {}
        specs = self._stock_field_specs()
        for field_id, title, value in specs:
            label = QLabel(_form_label_caption(title))
            label.setStyleSheet(form_label_style(base_dir))
            labels_by_field[field_id] = label
            raw_titles[field_id] = title
            le = QLineEdit(value or "")
            if field_id == "KEY" and self._data_dict is not None:
                le.setReadOnly(False)
            else:
                le.setReadOnly(True)
            le.setStyleSheet(form_editor_style(base_dir))
            le.setFixedWidth(_FORM_EDITOR_WIDTH_PX)
            le.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            editors[field_id] = le
            if field_id == "KEY" and self._data_dict is not None:
                le.editingFinished.connect(self._on_stock_key_edited)
        if labels_by_field:
            _apply_uniform_form_label_widths(labels_by_field, raw_titles, base_dir)
            label_w = max(lb.width() for lb in labels_by_field.values())
        else:
            label_w = _FORM_LABEL_WIDTH_MIN_PX
        for lb in labels_by_field.values():
            lb.setFixedWidth(label_w)
        for c in range(_HEADER_COLS * 2):
            grid.setColumnStretch(c, 0)
        grid.setColumnMinimumWidth(0, label_w)
        grid.setColumnMinimumWidth(2, label_w)
        grid.setColumnMinimumWidth(1, _FORM_EDITOR_WIDTH_PX)
        grid.setColumnMinimumWidth(3, _FORM_EDITOR_WIDTH_PX)
        for slot, (field_id, _title, _value) in enumerate(specs):
            row = slot // _HEADER_COLS
            col_slot = slot % _HEADER_COLS
            label_col = col_slot * 2
            editor_col = label_col + 1
            grid.addWidget(
                labels_by_field[field_id],
                row,
                label_col,
                alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            )
            ed = editors[field_id]
            if field_id == "KEY" and self._data_dict is not None:
                wrapped = _wrap_lookup_field_editor(
                    ed, on_lookup=self._open_stock_lookup, lang=self.lang
                )
                grid.addWidget(wrapped, row, editor_col)
            else:
                grid.addWidget(ed, row, editor_col)
        grid.setColumnStretch(_HEADER_COLS * 2, 1)
        self._stock_editors = editors
        panel = QWidget()
        panel.setLayout(grid)
        panel.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        wrap = QHBoxLayout()
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.addWidget(panel, 0, Qt.AlignmentFlag.AlignLeft)
        wrap.addStretch(1)
        host = QWidget()
        host.setLayout(wrap)
        return host

    def _open_stock_lookup(self) -> None:
        if self.backend is None or self._data_dict is None:
            return
        from ui.lookup_dialog import LookupPickerDialog

        lookup_ret = "STK_KEY"
        try:
            self._data_dict.load_columns_for_dbf("STOCK")
            _db, _key, ret = self._data_dict.get_lookup("STOCK", "STK_KEY")
            if (ret or "").strip():
                lookup_ret = ret.strip()
            else:
                phys = self.backend.list_columns("STOCK") or []
                for cand in ("STK_KEY", "STOCK_KEY", "ITEM_KEY", "KEY"):
                    if any((c or "").strip().upper() == cand for c in phys):
                        lookup_ret = cand
                        break
        except Exception:
            pass

        dlg = LookupPickerDialog(
            lookup_db="STOCK",
            lookup_ret=lookup_ret,
            backend=self.backend,
            data_dict=self._data_dict,
            lang=self.lang,
            parent=self,
            app_base_dir=getattr(self.parent(), "_app_base_dir", None)
            if self.parent()
            else None,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            key = (dlg.selected_value or "").strip()
            if key:
                self._goto_stock_key(key)

    def _on_stock_key_edited(self) -> None:
        ed = getattr(self, "_stock_editors", {}).get("KEY")
        if ed is None:
            return
        key = ed.text().strip()
        if key:
            self._goto_stock_key(key)

    def _goto_stock_key(self, key: str) -> None:
        if not self._doc or not key:
            return
        idx = find_stock_index(self._doc.stocks, key)
        if idx < 0:
            QMessageBox.information(
                self,
                self._t("查詢", "Query"),
                self._t("找不到此存貨編號。", "Stock not found."),
            )
            self._refresh_header_fields()
            return
        self._nav_stock(idx)

    def _make_date_field(self, initial: str) -> Tuple[QLineEdit, QToolButton]:
        le = QLineEdit(initial or "")
        le.setFixedWidth(120)
        le.setPlaceholderText("yyyy/MM/dd")
        btn = QToolButton()
        btn.setIcon(icon_from_key(self.style(), "view-calendar"))
        btn.setToolTip(self._t("選取日期", "Pick date"))
        btn.clicked.connect(lambda: self._pick_date_for(le))
        le.editingFinished.connect(lambda: self._on_date_edited(le))
        le.textChanged.connect(self._schedule_reload)
        return le, btn

    def _pick_date_for(self, le: QLineEdit) -> None:
        popup = _DatePickPopup(self, le.text(), chn=self.lang == "CHN")
        popup.move(le.mapToGlobal(le.rect().bottomLeft()))
        if popup.exec():
            le.blockSignals(True)
            le.setText(popup.picked)
            le.blockSignals(False)
            self._reload_transactions()

    def _on_date_edited(self, le: QLineEdit) -> None:
        raw = le.text().strip()
        if not raw:
            return
        norm = normalize_date_text(raw)
        if norm != raw:
            le.blockSignals(True)
            le.setText(norm)
            le.blockSignals(False)

    def _schedule_reload(self, *_args) -> None:
        self._reload_timer.start()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        layout.addWidget(self._build_header_panel())

        stock_nav = QHBoxLayout()
        self.btn_stock_first = QPushButton()
        self.btn_stock_prev = QPushButton()
        self.btn_stock_next = QPushButton()
        self.btn_stock_last = QPushButton()
        for b in (
            self.btn_stock_first,
            self.btn_stock_prev,
            self.btn_stock_next,
            self.btn_stock_last,
        ):
            apply_nav_button_style(b)
        bind_grid_nav_icon_buttons(
            self.lang,
            self.style(),
            self.btn_stock_first,
            self.btn_stock_prev,
            self.btn_stock_next,
            self.btn_stock_last,
        )
        self.btn_stock_first.clicked.connect(lambda: self._nav_stock(0))
        self.btn_stock_prev.clicked.connect(
            lambda: self._nav_stock((self._doc.stock_index if self._doc else 0) - 1)
        )
        self.btn_stock_next.clicked.connect(
            lambda: self._nav_stock((self._doc.stock_index if self._doc else 0) + 1)
        )
        self.btn_stock_last.clicked.connect(
            lambda: self._nav_stock(len(self._doc.stocks) - 1 if self._doc else 0)
        )
        stock_nav.addWidget(self.btn_stock_first)
        stock_nav.addWidget(self.btn_stock_prev)
        stock_nav.addWidget(self.btn_stock_next)
        stock_nav.addWidget(self.btn_stock_last)
        self.lbl_stock_nav = QLabel()
        self.lbl_stock_nav.setStyleSheet("font-weight: 700; color: #1b3b6f;")
        stock_nav.addWidget(self.lbl_stock_nav, 1)
        layout.addLayout(stock_nav)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel(self._t("由日期", "From date")))
        self.txt_date_from, btn_from = self._make_date_field(
            self._doc.date_from if self._doc else ""
        )
        filter_row.addWidget(self.txt_date_from)
        filter_row.addWidget(btn_from)
        filter_row.addWidget(QLabel(self._t("至日期", "To date")))
        self.txt_date_to, btn_to = self._make_date_field(
            self._doc.date_to if self._doc else ""
        )
        filter_row.addWidget(self.txt_date_to)
        filter_row.addWidget(btn_to)
        filter_row.addWidget(QLabel(self._t("交易類型", "Type")))
        self._tx_checks: dict[str, QCheckBox] = {}
        kind_items = [
            ("PUR", self._t("購貨(PURCHASE)", "Purchase (PURCHASE)")),
            ("INV", self._t("銷貨(INVOICE)", "Sales (INVOICE)")),
            ("ADJ", self._t("存貨調整(STKADJ)", "Adjustment (STKADJ)")),
            ("TRI", self._t("存貨轉倉(TRANSFER)", "Transfer (TRANSFER)")),
        ]
        cur_kinds = set(
            normalize_tx_kinds(
                getattr(self._doc, "tx_kinds", None) if self._doc else None
            )
        )
        for key, label in kind_items:
            cb = QCheckBox(label)
            cb.setChecked(key in cur_kinds)
            cb.stateChanged.connect(self._schedule_reload)
            self._tx_checks[key] = cb
            filter_row.addWidget(cb)
        filter_row.addStretch(1)
        layout.addLayout(filter_row)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel(self._t("搜尋:", "Search:")))
        self.txt_search = QLineEdit()
        self.txt_search.returnPressed.connect(self._on_search)
        search_row.addWidget(self.txt_search, 1)
        self.btn_search = QPushButton(self._t("搜尋", "Search"))
        apply_work_action_button_style(self.btn_search)
        self.btn_search.setIcon(icon_from_key(self.style(), "search"))
        self.btn_search.clicked.connect(self._on_search)
        self.btn_filter = QPushButton(self._t("過濾", "Filter"))
        apply_work_action_button_style(self.btn_filter)
        self.btn_filter.setIcon(icon_from_key(self.style(), "filter"))
        self.btn_filter.clicked.connect(self._on_filter)
        search_row.addWidget(self.btn_search)
        search_row.addWidget(self.btn_filter)
        layout.addLayout(search_row)

        grid_nav = QHBoxLayout()
        self.btn_line_first = QPushButton()
        self.btn_line_prev = QPushButton()
        self.btn_line_next = QPushButton()
        self.btn_line_last = QPushButton()
        for b in (
            self.btn_line_first,
            self.btn_line_prev,
            self.btn_line_next,
            self.btn_line_last,
        ):
            apply_nav_button_style(b)
        bind_grid_nav_icon_buttons(
            self.lang,
            self.style(),
            self.btn_line_first,
            self.btn_line_prev,
            self.btn_line_next,
            self.btn_line_last,
        )
        self.btn_line_first.clicked.connect(self._nav_line_first)
        self.btn_line_prev.clicked.connect(self._nav_line_prev)
        self.btn_line_next.clicked.connect(self._nav_line_next)
        self.btn_line_last.clicked.connect(self._nav_line_last)
        grid_nav.addWidget(self.btn_line_first)
        grid_nav.addWidget(self.btn_line_prev)
        grid_nav.addWidget(self.btn_line_next)
        grid_nav.addWidget(self.btn_line_last)
        self.lbl_line_nav = QLabel()
        self.lbl_line_nav.setStyleSheet("font-weight: 700; color: #1b3b6f;")
        grid_nav.addWidget(self.lbl_line_nav, 1)
        self.btn_exit = QPushButton(self._t("離開", "Exit"))
        apply_work_action_button_style(self.btn_exit)
        self.btn_exit.setIcon(icon_from_key(self.style(), "exit"))
        self.btn_exit.clicked.connect(self._request_close)
        grid_nav.addWidget(self.btn_exit)
        layout.addLayout(grid_nav)

        self.table = QTableView()
        _configure_grid(self.table)
        self._model = StockQueryGridModel(self._all_lines, self._grid_headers(), self)
        self.table.setModel(self._model)
        self.table.selectionModel().selectionChanged.connect(self._on_line_selection)
        layout.addWidget(self.table)

        foot = QVBoxLayout()
        self.lbl_pur_totals = QLabel()
        self.lbl_inv_totals = QLabel()
        self.lbl_adj_totals = QLabel()
        self.lbl_tri_totals = QLabel()
        for w in (
            self.lbl_pur_totals,
            self.lbl_inv_totals,
            self.lbl_adj_totals,
            self.lbl_tri_totals,
        ):
            w.setStyleSheet("font-weight: 700; color: #1b3b6f;")
            foot.addWidget(w)
        layout.addLayout(foot)
        self._ui_ready = True

    def showEvent(self, event) -> None:  # noqa: N802
        from PyQt6.QtGui import QShowEvent

        super().showEvent(event)
        if not isinstance(event, QShowEvent):
            return
        if not getattr(self, "_ui_ready", False) or not self._ready:
            return
        if getattr(self, "_skip_next_show_refresh", False):
            self._skip_next_show_refresh = False
            return
        QTimer.singleShot(0, self.refresh_from_db)

    def refresh_from_db(self, source_row: Optional[List[str]] = None) -> None:
        """強制自資料庫重讀主檔與交易（更新資料後可看到最新內容）。"""
        if not self._ready or not self._doc:
            return
        if source_row is not None:
            self._source_row = list(source_row)
        self._reload_transactions()
        self._refresh_stock_nav()

    def _visible_lines(self) -> List[StockQueryLine]:
        return list(self._model._lines)

    def _current_tx_kinds(self) -> List[str]:
        out: List[str] = []
        for key in TX_KIND_OPTIONS:
            cb = self._tx_checks.get(key)
            if cb is not None and cb.isChecked():
                out.append(key)
        return out

    def _reload_transactions(self) -> None:
        if not self._doc:
            return
        date_from = normalize_date_text(self.txt_date_from.text())
        date_to = normalize_date_text(self.txt_date_to.text())
        if date_from != self.txt_date_from.text().strip():
            self.txt_date_from.blockSignals(True)
            self.txt_date_from.setText(date_from)
            self.txt_date_from.blockSignals(False)
        if date_to != self.txt_date_to.text().strip():
            self.txt_date_to.blockSignals(True)
            self.txt_date_to.setText(date_to)
            self.txt_date_to.blockSignals(False)
        doc, err = load_stock_query(
            self.backend,
            self._do_proc,
            self._source_row,
            self._source_fields,
            table_name=self._table_name,
            other_title=self._other_title,
            stock_index=self._doc.stock_index,
            date_from=date_from,
            date_to=date_to,
            tx_kinds=self._current_tx_kinds(),
        )
        if err or doc is None:
            QMessageBox.warning(self, self._t("查詢", "Query"), err or "")
            return
        self._doc = doc
        self._all_lines = list(doc.lines)
        self._apply_line_filter()
        self._refresh_header_fields()
        self._refresh_totals()

    def _refresh_header_fields(self) -> None:
        if not self._doc:
            return
        s = current_stock(self._doc)
        mapping = {
            "KEY": s.key,
            "CAT": s.category,
            "BRAND": s.brand,
            "MODEL": s.model,
            "DESC": s.desc,
        }
        for k, ed in getattr(self, "_stock_editors", {}).items():
            ed.setText(mapping.get(k, "") or "")

    def _nav_stock(self, index: int) -> None:
        if not self._doc or not self._doc.stocks:
            return
        index = max(0, min(index, len(self._doc.stocks) - 1))
        self._doc.stock_index = index
        self._reload_transactions()
        self._refresh_stock_nav()

    def _refresh_stock_nav(self) -> None:
        if not self._doc:
            return
        n = len(self._doc.stocks)
        cur = self._doc.stock_index + 1 if n else None
        self.lbl_stock_nav.setText(format_record_nav_label(n, cur))
        dis_first = n <= 0 or self._doc.stock_index <= 0
        dis_prev = n <= 0 or self._doc.stock_index <= 0
        dis_next = n <= 0 or self._doc.stock_index >= n - 1
        dis_last = n <= 0 or self._doc.stock_index >= n - 1
        self.btn_stock_first.setEnabled(not dis_first)
        self.btn_stock_prev.setEnabled(not dis_prev)
        self.btn_stock_next.setEnabled(not dis_next)
        self.btn_stock_last.setEnabled(not dis_last)

    def _apply_line_filter(self) -> None:
        kw = self._filter_keyword.strip()
        visible = filter_stock_lines(self._all_lines, kw) if kw else list(self._all_lines)
        self._model.set_lines(visible)
        n = len(visible)
        if n <= 0:
            self._selected_row = None
        elif self._selected_row is None or self._selected_row >= n:
            self._selected_row = 0
        self._refresh_line_nav()

    def _refresh_line_nav(self) -> None:
        lines = self._visible_lines()
        n = len(lines)
        cur = (
            self._selected_row + 1
            if self._selected_row is not None and 0 <= self._selected_row < n
            else None
        )
        self.lbl_line_nav.setText(format_record_nav_label(n, cur))
        dis_first = n <= 0 or (cur is not None and cur <= 1)
        dis_prev = n <= 0 or cur is None or cur <= 1
        dis_next = n <= 0 or cur is None or cur >= n
        dis_last = n <= 0 or (cur is not None and cur >= n)
        self.btn_line_first.setEnabled(not dis_first)
        self.btn_line_prev.setEnabled(not dis_prev)
        self.btn_line_next.setEnabled(not dis_next)
        self.btn_line_last.setEnabled(not dis_last)
        if self._selected_row is not None and 0 <= self._selected_row < n:
            self.table.selectRow(self._selected_row)

    def _refresh_totals(self) -> None:
        totals = totals_dict(self._visible_lines())
        self.lbl_pur_totals.setText(
            self._t("購貨", "Purchase")
            + f"：{self._t('數量', 'Qty')} {totals.get('pur_qty', '0.00')}　"
            f"{self._t('重量', 'Weight')} {totals.get('pur_weight', '0.00')}　"
            f"{self._t('金額', 'Amt')} {totals.get('pur_amt', '0.00')}"
        )
        self.lbl_inv_totals.setText(
            self._t("發票", "Invoice")
            + f"：{self._t('數量', 'Qty')} {totals.get('inv_qty', '0.00')}　"
            f"{self._t('重量', 'Weight')} {totals.get('inv_weight', '0.00')}　"
            f"{self._t('金額', 'Amt')} {totals.get('inv_amt', '0.00')}"
        )
        self.lbl_adj_totals.setText(
            self._t("存貨調整", "Adjustment")
            + f"：{self._t('數量', 'Qty')} {totals.get('adj_qty', '0.00')}　"
            f"{self._t('重量', 'Weight')} {totals.get('adj_weight', '0.00')}　"
            f"{self._t('金額', 'Amt')} {totals.get('adj_amt', '0.00')}"
        )
        self.lbl_tri_totals.setText(
            self._t("存貨轉倉", "Transfer")
            + f"：{self._t('數量', 'Qty')} {totals.get('tri_qty', '0.00')}　"
            f"{self._t('重量', 'Weight')} {totals.get('tri_weight', '0.00')}　"
            f"{self._t('金額', 'Amt')} {totals.get('tri_amt', '0.00')}"
        )

    def _on_line_selection(self) -> None:
        idxs = self.table.selectionModel().selectedRows()
        self._selected_row = None if not idxs else idxs[0].row()
        self._refresh_line_nav()

    def _nav_line_first(self) -> None:
        if self._visible_lines():
            self._selected_row = 0
            self._refresh_line_nav()

    def _nav_line_prev(self) -> None:
        if self._selected_row is not None and self._selected_row > 0:
            self._selected_row -= 1
            self._refresh_line_nav()

    def _nav_line_next(self) -> None:
        n = len(self._visible_lines())
        if self._selected_row is not None and self._selected_row < n - 1:
            self._selected_row += 1
            self._refresh_line_nav()

    def _nav_line_last(self) -> None:
        n = len(self._visible_lines())
        if n > 0:
            self._selected_row = n - 1
            self._refresh_line_nav()

    def _on_search(self) -> None:
        kw = self.txt_search.text().strip()
        self._keyword = kw
        idx = find_line_index(self._all_lines, kw)
        if idx is None:
            QMessageBox.information(
                self,
                self._t("搜尋", "Search"),
                self._t("找不到符合的資料。", "No matching row."),
            )
            return
        self._filter_keyword = ""
        self._model.set_lines(list(self._all_lines))
        self._selected_row = idx
        self._refresh_line_nav()
        self._refresh_totals()

    def _on_filter(self) -> None:
        self._filter_keyword = self.txt_search.text().strip()
        self._apply_line_filter()
        self._refresh_totals()


def open_stock_query(
    backend: Optional[DbBackendBase],
    do_proc: str,
    source_row: List[str],
    source_fields: List[str],
    lang: LanguageCode = "CHN",
    table_name: str = "",
    other_title: str = "",
    data_dict: Optional[DataDictionary] = None,
    on_close: Optional[Callable[[], None]] = None,
    parent=None,
) -> Optional[StockQueryDialog]:
    if backend is None:
        QMessageBox.warning(
            parent,
            "查詢" if lang == "CHN" else "Query",
            "無法連線資料庫。" if lang == "CHN" else "Database unavailable.",
        )
        return None
    page = StockQueryDialog(
        backend,
        do_proc,
        source_row,
        source_fields,
        lang=lang,
        table_name=table_name,
        other_title=other_title,
        data_dict=data_dict,
        on_close=on_close,
        parent=parent,
    )
    if not getattr(page, "_ready", False):
        page.deleteLater()
        return None
    return page
