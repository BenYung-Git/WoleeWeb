"""顧客／供應商查詢對話框。"""
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
from core.party_query_service import (
    TX_KIND_OPTIONS,
    PartyQueryDocument,
    PartyQueryLine,
    _custvend_row_matches_mode,
    current_party,
    filter_party_lines,
    find_line_index,
    find_party_index,
    load_party_query,
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
    # 日期/類別/編號/貨幣靠左；滙率與金額靠右（與資料列一致）
    if col >= 4:
        return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)


class PartyQueryGridModel(QAbstractTableModel):
    COLS = (
        "date",
        "tx_category",
        "tx_key",
        "currency",
        "rate",
        "inv_amt",
        "paid_amt",
        "recv_amt",
        "settle_amt",
    )

    def __init__(
        self,
        lines: List[PartyQueryLine],
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

    def set_lines(self, lines: List[PartyQueryLine]) -> None:
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


class PartyQueryDialog(QWidget):
    """顧客／供應商查詢頁面（可嵌入右側 TAB）。"""

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
        self._doc: Optional[PartyQueryDocument] = None
        self._all_lines: List[PartyQueryLine] = []
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

        doc, err = load_party_query(
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

        chn = lang == "CHN"
        if doc.mode == "AR":
            self._tab_title = (other_title or "").strip() or (
                "顧客查詢" if chn else "Customer Query"
            )
        else:
            self._tab_title = (other_title or "").strip() or (
                "供應商查詢" if chn else "Vendor Query"
            )
        self.setWindowTitle(self._tab_title)
        self._build_ui()
        self._apply_line_filter()
        self._refresh_totals()
        self._refresh_party_nav()

    def tab_title(self) -> str:
        return getattr(self, "_tab_title", self._t("查詢", "Query"))

    def _request_close(self) -> None:
        if callable(self._on_close):
            self._on_close()
            return
        # 相容：若外層仍以 QDialog 包住
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
                "貨幣",
                "滙率",
                "發票金額",
                "已收(付)金額",
                "收(付)款金額",
                "清賬金額",
            ]
        return [
            "Date",
            "Type",
            "Doc No.",
            "Curr.",
            "Rate",
            "Invoice Amt.",
            "Paid Amt.",
            "Recv/Pay Amt.",
            "Settled",
        ]

    def _party_field_specs(self) -> List[Tuple[str, str, str]]:
        assert self._doc is not None
        p = current_party(self._doc)
        return [
            ("KEY", self._t("顧客-供應商編號", "Cust/Vend No."), p.key),
            ("NAME", self._t("名稱", "Name"), p.name),
            ("CONTACT", self._t("聯絡人", "Contact"), p.contact),
            ("TEL", self._t("電話#", "Tel."), p.tel),
            ("CREDIT", self._t("信用額", "Credit Limit"), p.credit_limit),
            ("REMAIN", self._t("剩餘信用額", "Remaining Credit"), p.remain_credit),
        ]

    def _build_header_panel(self) -> QWidget:
        """二欄靠左排列。"""
        base_dir = _font_base_dir_for(self)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        labels_by_field: dict[str, QLabel] = {}
        raw_titles: dict[str, str] = {}
        editors: dict[str, QLineEdit] = {}
        specs = self._party_field_specs()
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
            if field_id in {"CREDIT", "REMAIN"}:
                le.setAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
            else:
                le.setAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
            editors[field_id] = le
            if field_id == "KEY" and self._data_dict is not None:
                le.editingFinished.connect(self._on_party_key_edited)
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
                    ed, on_lookup=self._open_party_lookup, lang=self.lang
                )
                grid.addWidget(wrapped, row, editor_col)
            else:
                grid.addWidget(ed, row, editor_col)
        # 靠左：右側不拉伸佔位
        grid.setColumnStretch(_HEADER_COLS * 2, 1)
        self._party_editors = editors
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

    def _open_party_lookup(self) -> None:
        if self.backend is None or self._data_dict is None or not self._doc:
            return
        from ui.lookup_dialog import LookupPickerDialog

        mode = self._doc.mode
        lookup_ret = "CUST_KEY" if mode == "AR" else "VEND_KEY"
        try:
            self._data_dict.load_columns_for_dbf("CUSTVEND")
            for cand in ("CV_KEY", "CUST_KEY", "VEND_KEY"):
                _db, _key, ret = self._data_dict.get_lookup("CUSTVEND", cand)
                if (ret or "").strip():
                    lookup_ret = ret.strip()
                    break
            else:
                phys = self.backend.list_columns("CUSTVEND") or []
                for cand in ("CV_KEY", "CUST_KEY", "VEND_KEY", "KEY"):
                    if any((c or "").strip().upper() == cand for c in phys):
                        lookup_ret = cand
                        break
        except Exception:
            pass

        def _row_filter(fields, row) -> bool:
            return _custvend_row_matches_mode(fields, row, mode)

        dlg = LookupPickerDialog(
            lookup_db="CUSTVEND",
            lookup_ret=lookup_ret,
            backend=self.backend,
            data_dict=self._data_dict,
            lang=self.lang,
            parent=self,
            app_base_dir=getattr(self.parent(), "_app_base_dir", None)
            if self.parent()
            else None,
            row_filter=_row_filter,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            key = (dlg.selected_value or "").strip()
            if key:
                self._goto_party_key(key)

    def _on_party_key_edited(self) -> None:
        ed = getattr(self, "_party_editors", {}).get("KEY")
        if ed is None:
            return
        key = ed.text().strip()
        if key:
            self._goto_party_key(key)

    def _goto_party_key(self, key: str) -> None:
        if not self._doc or not key:
            return
        idx = find_party_index(self._doc.parties, key)
        if idx < 0:
            QMessageBox.information(
                self,
                self._t("查詢", "Query"),
                self._t("找不到此顧客-供應商編號。", "Customer/Vendor not found."),
            )
            self._refresh_header_fields()
            return
        self._nav_party(idx)

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
        # 簡化：置於游標旁
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

        party_nav = QHBoxLayout()
        self.btn_party_first = QPushButton()
        self.btn_party_prev = QPushButton()
        self.btn_party_next = QPushButton()
        self.btn_party_last = QPushButton()
        for b in (
            self.btn_party_first,
            self.btn_party_prev,
            self.btn_party_next,
            self.btn_party_last,
        ):
            apply_nav_button_style(b)
        bind_grid_nav_icon_buttons(
            self.lang,
            self.style(),
            self.btn_party_first,
            self.btn_party_prev,
            self.btn_party_next,
            self.btn_party_last,
        )
        self.btn_party_first.clicked.connect(lambda: self._nav_party(0))
        self.btn_party_prev.clicked.connect(
            lambda: self._nav_party((self._doc.party_index if self._doc else 0) - 1)
        )
        self.btn_party_next.clicked.connect(
            lambda: self._nav_party((self._doc.party_index if self._doc else 0) + 1)
        )
        self.btn_party_last.clicked.connect(
            lambda: self._nav_party(len(self._doc.parties) - 1 if self._doc else 0)
        )
        party_nav.addWidget(self.btn_party_first)
        party_nav.addWidget(self.btn_party_prev)
        party_nav.addWidget(self.btn_party_next)
        party_nav.addWidget(self.btn_party_last)
        self.lbl_party_nav = QLabel()
        self.lbl_party_nav.setStyleSheet("font-weight: 700; color: #1b3b6f;")
        party_nav.addWidget(self.lbl_party_nav, 1)
        layout.addLayout(party_nav)

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
            ("INV", self._t("發票(INVOICE)", "Invoice (INVOICE)")),
            ("REC", self._t("收款(VOUCHER/RJ)", "Receipt (VOUCHER/RJ)")),
            ("PUR", self._t("購貨發票(PURCHASE)", "Purchase (PURCHASE)")),
            ("PAY", self._t("付款(VOUCHER/PJ)", "Payment (VOUCHER/PJ)")),
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
        self._model = PartyQueryGridModel(self._all_lines, self._grid_headers(), self)
        self.table.setModel(self._model)
        self.table.selectionModel().selectionChanged.connect(self._on_line_selection)
        layout.addWidget(self.table)

        foot = QVBoxLayout()
        self.lbl_inv_totals = QLabel()
        self.lbl_pur_totals = QLabel()
        for w in (self.lbl_inv_totals, self.lbl_pur_totals):
            w.setStyleSheet("font-weight: 700; color: #1b3b6f;")
        foot.addWidget(self.lbl_inv_totals)
        foot.addWidget(self.lbl_pur_totals)
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
        self._refresh_party_nav()

    def _visible_lines(self) -> List[PartyQueryLine]:
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
        doc, err = load_party_query(
            self.backend,
            self._do_proc,
            self._source_row,
            self._source_fields,
            table_name=self._table_name,
            other_title=self._other_title,
            party_index=self._doc.party_index,
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
        p = current_party(self._doc)
        mapping = {
            "KEY": p.key,
            "NAME": p.name,
            "CONTACT": p.contact,
            "TEL": p.tel,
            "CREDIT": p.credit_limit,
            "REMAIN": p.remain_credit,
        }
        for k, ed in getattr(self, "_party_editors", {}).items():
            ed.setText(mapping.get(k, "") or "")

    def _nav_party(self, index: int) -> None:
        if not self._doc or not self._doc.parties:
            return
        index = max(0, min(index, len(self._doc.parties) - 1))
        self._doc.party_index = index
        self._reload_transactions()
        self._refresh_party_nav()

    def _refresh_party_nav(self) -> None:
        if not self._doc:
            return
        n = len(self._doc.parties)
        cur = self._doc.party_index + 1 if n else None
        self.lbl_party_nav.setText(format_record_nav_label(n, cur))
        dis_first = n <= 0 or self._doc.party_index <= 0
        dis_prev = n <= 0 or self._doc.party_index <= 0
        dis_next = n <= 0 or self._doc.party_index >= n - 1
        dis_last = n <= 0 or self._doc.party_index >= n - 1
        self.btn_party_first.setEnabled(not dis_first)
        self.btn_party_prev.setEnabled(not dis_prev)
        self.btn_party_next.setEnabled(not dis_next)
        self.btn_party_last.setEnabled(not dis_last)

    def _apply_line_filter(self) -> None:
        kw = self._filter_keyword.strip()
        visible = filter_party_lines(self._all_lines, kw) if kw else list(self._all_lines)
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
        self.lbl_inv_totals.setText(
            self._t("發票合計", "Invoice totals")
            + f"：{self._t('金額', 'Amt')} {totals.get('inv_amt', '0.00')}　"
            f"{self._t('已付金額', 'Paid')} {totals.get('inv_paid_amt', '0.00')}　"
            f"{self._t('收款金額', 'Receipt')} {totals.get('inv_recv_amt', '0.00')}　"
            f"{self._t('已清賬金額', 'Settled')} {totals.get('inv_settle_amt', '0.00')}"
        )
        self.lbl_pur_totals.setText(
            self._t("購貨發票合計", "Purchase totals")
            + f"：{self._t('金額', 'Amt')} {totals.get('pur_amt', '0.00')}　"
            f"{self._t('已付金額', 'Paid')} {totals.get('pur_paid_amt', '0.00')}　"
            f"{self._t('付款金額', 'Payment')} {totals.get('pur_pay_amt', '0.00')}　"
            f"{self._t('已清賬金額', 'Settled')} {totals.get('pur_settle_amt', '0.00')}"
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


def open_party_query(
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
) -> Optional[PartyQueryDialog]:
    """建立查詢頁面；成功回傳 widget（供 TAB 嵌入），失敗回傳 None。"""
    if backend is None:
        QMessageBox.warning(
            parent,
            "查詢" if lang == "CHN" else "Query",
            "無法連線資料庫。" if lang == "CHN" else "Database unavailable.",
        )
        return None
    page = PartyQueryDialog(
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
