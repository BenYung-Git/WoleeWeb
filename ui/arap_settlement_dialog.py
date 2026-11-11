from __future__ import annotations

from decimal import Decimal
from typing import List, Optional, Tuple

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QFontMetrics
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyleOptionViewItem,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from core.arap_settlement_service import (
    SettlementDocument,
    SettlementLine,
    _d,
    _s,
    auto_settle_lines,
    filter_lines,
    find_line_index,
    load_settlement,
    remaining_settlement,
    save_settlement,
    sum_totals,
)
from core.display_format import format_date_display, is_date_field, try_parse_float
from core.data_dictionary import LanguageCode
from core.db_backend import DbBackendBase
from core.ui_icon_map import icon_from_key
from ui.work_page import (
    GridCellDelegate,
    _FORM_EDITOR_WIDTH_PX,
    _FORM_LABEL_WIDTH_MIN_PX,
    _apply_uniform_form_label_widths,
    _font_base_dir_for,
    _form_label_caption,
    apply_work_action_button_style,
    bind_grid_nav_icon_buttons,
    form_editor_style,
    form_label_style,
    format_record_nav_label,
    _grid_data_row_count,
    grid_model_data_row_count,
)

_SETTLE_HEADER_COLS = 2
_SETTLE_HEADER_SLOTS = 8
_SETTLE_HEADER_GRID_COLS = _SETTLE_HEADER_COLS * 2
_SETTLE_GRID_VISIBLE_ROWS = 15
_SETTLE_GRID_ROW_HEIGHT_PX = 24
_SETTLE_GRID_HEADER_PT = 11
_SETTLE_GRID_CELL_PT = 10


def _settlement_col_alignment(col: int) -> int:
    if col >= 3:
        return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)


def _settlement_grid_cell_font() -> QFont:
    f = QFont()
    f.setPointSize(_SETTLE_GRID_CELL_PT)
    f.setWeight(QFont.Weight.Normal)
    return f


def _settlement_grid_header_font() -> QFont:
    f = QFont()
    f.setPointSize(_SETTLE_GRID_HEADER_PT)
    f.setWeight(QFont.Weight.Bold)
    return f


class SettlementGridCellDelegate(GridCellDelegate):
    """清賬 Grid：10pt 儲存格字型；付款／折扣欄不顯示選取高亮。"""

    @staticmethod
    def _is_amount_edit_col(col: int) -> bool:
        return col in (SettlementGridModel.COL_PAY, SettlementGridModel.COL_DISC)

    @classmethod
    def _suppress_cell_highlight(cls, option, col: int) -> None:
        if not cls._is_amount_edit_col(col):
            return
        option.state &= ~QStyle.StateFlag.State_Selected
        option.state &= ~QStyle.StateFlag.State_HasFocus
        option.state &= ~QStyle.StateFlag.State_MouseOver

    def initStyleOption(self, option, index) -> None:  # type: ignore[override]
        super(GridCellDelegate, self).initStyleOption(option, index)
        option.font = _settlement_grid_cell_font()
        if not index.isValid() or not self._is_amount_edit_col(index.column()):
            return
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        self._suppress_cell_highlight(option, index.column())
        if selected:
            option.backgroundBrush = QBrush(QColor("#ffffff"))

    def paint(self, painter, option, index) -> None:  # type: ignore[override]
        if (
            index.isValid()
            and self._is_amount_edit_col(index.column())
            and option.state & QStyle.StateFlag.State_Selected
        ):
            painter.save()
            painter.fillRect(option.rect, QColor("#ffffff"))
            painter.restore()
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        widget = opt.widget
        style = widget.style() if widget is not None else None
        if style is not None:
            style.drawControl(
                QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget
            )
        else:
            super().paint(painter, opt, index)

    def createEditor(self, parent, option, index):  # type: ignore[override]
        editor = super(GridCellDelegate, self).createEditor(parent, option, index)
        if editor is not None:
            editor.setFont(_settlement_grid_cell_font())
            editor.installEventFilter(self)
            if index.isValid() and self._is_amount_edit_col(index.column()):
                editor.setStyleSheet(
                    "QLineEdit { border: none; background: #ffffff; padding: 0px 6px; }"
                    "QLineEdit:focus { border: none; background: #ffffff; }"
                )
        return editor

    def setEditorData(self, editor, index) -> None:  # type: ignore[override]
        if editor is not None:
            editor.setFont(_settlement_grid_cell_font())
        super().setEditorData(editor, index)

    def _handle_editor_key(self, editor: QWidget, event) -> bool:
        if event.modifiers() != Qt.KeyboardModifier.NoModifier:
            return super()._handle_editor_key(editor, event)
        key = event.key()
        if key not in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            return super()._handle_editor_key(editor, event)
        view = self._view
        if view is None:
            return False
        idx = view.currentIndex()
        if not idx.isValid():
            return False
        col = idx.column()
        if not self._is_amount_edit_col(col):
            return super()._handle_editor_key(editor, event)
        model = view.model()
        if model is None:
            return False
        row = idx.row()
        nrows = _grid_data_row_count(view)
        dr = -1 if key == Qt.Key.Key_Up else 1
        nr = row + dr
        if 0 <= nr < nrows:
            return self._navigate_from_editor(editor, nr, col)
        self._finish_edit(editor)
        return True


def _settlement_grid_table_outer_height(tv: QTableView, visible_rows: int) -> int:
    row_h = _SETTLE_GRID_ROW_HEIGHT_PX
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
    viewport_h = row_h * visible_rows + grid_lines
    return viewport_h + header_h + frame + 4


def configure_settlement_grid_table_view(tv: QTableView) -> None:
    """清賬 Grid：列高 24px、可視 15 列；表頭 11pt、儲存格 10pt。"""
    visible_rows = _SETTLE_GRID_VISIBLE_ROWS
    tv.setObjectName("appGridTable")
    tv.setStyleSheet(
        "#appGridTable::item { padding-top: 0px; padding-bottom: 0px; "
        "padding-left: 6px; padding-right: 6px; }"
    )
    tv.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tv.setAlternatingRowColors(True)
    tv.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    tv.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    tv.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)
    tv.setFont(_settlement_grid_cell_font())
    hdr = tv.horizontalHeader()
    hdr.setFont(_settlement_grid_header_font())
    hdr.setStretchLastSection(False)
    hdr.setDefaultAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )
    tv.setItemDelegate(SettlementGridCellDelegate(tv))
    row_h = _SETTLE_GRID_ROW_HEIGHT_PX
    grid_lines = max(0, visible_rows - 1) if tv.showGrid() else 0
    need_viewport_h = row_h * visible_rows + grid_lines

    def _apply_height(extra: int = 0) -> None:
        desired_h = _settlement_grid_table_outer_height(tv, visible_rows) + extra
        tv.setMinimumHeight(desired_h)
        tv.setMaximumHeight(desired_h)

    def _fine_tune_after_layout() -> None:
        vp_h = tv.viewport().height()
        if vp_h <= 0 or vp_h >= need_viewport_h:
            return
        _apply_height(need_viewport_h - vp_h)

    _apply_height()
    QTimer.singleShot(0, _fine_tune_after_layout)
    tv.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


def _footer_amount_style(*, bordered: bool = False) -> str:
    pt = _SETTLE_GRID_CELL_PT
    base = f"font-weight: normal; font-size: {pt}pt;"
    if bordered:
        return f"{base} border: 1px solid #9fb4d9; padding: 0px 6px;"
    return base


def _style_footer_amount_widget(
    widget,
    *,
    bordered: bool = False,
) -> None:
    """與清賬 Grid 儲存格相同 10pt 字型（非粗體）、右對齊。"""
    widget.setFont(_settlement_grid_cell_font())
    widget.setStyleSheet(_footer_amount_style(bordered=bordered))
    widget.setAlignment(
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    )
    widget.setSizePolicy(
        QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
    )
    if bordered:
        widget.setMinimumHeight(_SETTLE_GRID_ROW_HEIGHT_PX)


def _fmt_amt(val: str) -> str:
    """金額顯示：千位分號、2 位小數（與系統標準一致）。"""
    v = try_parse_float(val)
    if v is None:
        return (val or "").strip()
    return f"{v:,.2f}"


def _fmt_date(val: str) -> str:
    return format_date_display(val or "")


def _fmt_rate(val: str) -> str:
    """匯率顯示：千位分號、4 位小數。"""
    v = try_parse_float(val)
    if v is None:
        return (val or "").strip()
    return f"{v:,.4f}"


class SettlementGridModel(QAbstractTableModel):
    COL_PAY = 7
    COL_DISC = 8

    def __init__(
        self,
        headers: List[str],
        lines: List[SettlementLine],
        lang: LanguageCode,
        parent=None,
        min_display_rows: int = _SETTLE_GRID_VISIBLE_ROWS,
    ) -> None:
        super().__init__(parent)
        self._headers = headers
        self._lines = lines
        self.lang = lang
        self._min_display_rows = max(0, int(min_display_rows))

    def data_row_count(self) -> int:
        return len(self._lines)

    def _is_padding_row(self, row: int) -> bool:
        return row >= self.data_row_count()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        return max(self.data_row_count(), self._min_display_rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        return len(self._headers)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole  # type: ignore[override]
    ):
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self._headers):
                if role == Qt.ItemDataRole.DisplayRole:
                    return self._headers[section]
                if role == Qt.ItemDataRole.TextAlignmentRole:
                    return _settlement_col_alignment(section)
                if role == Qt.ItemDataRole.FontRole:
                    return _settlement_grid_header_font()
        return super().headerData(section, orientation, role)

    def _cell_text(self, row: int, col: int, *, edit: bool) -> str:
        ln = self._lines[row]
        raw = [
            (ln.tx_key or "").strip(),
            ln.date,
            ln.currency,
            ln.rate,
            ln.net_amt,
            ln.paid_amt,
            ln.balance,
            ln.pay_amount,
            ln.discount,
        ]
        if not (0 <= col < len(raw)):
            return ""
        v = raw[col]
        if edit:
            return (v or "").strip()
        # 顯示格式：col 3=匯率，col 4-8=金額，其餘文字原樣
        if col == 1:
            return _fmt_date(v)
        if col == 3:
            return _fmt_rate(v)
        if col >= 4:
            return _fmt_amt(v)
        return (v or "").strip()

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # type: ignore[override]
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        if self._is_padding_row(row):
            if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
                return ""
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return _settlement_col_alignment(col)
            if role == Qt.ItemDataRole.FontRole:
                return _settlement_grid_cell_font()
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return self._cell_text(row, col, edit=role == Qt.ItemDataRole.EditRole)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return _settlement_col_alignment(col)
        if role == Qt.ItemDataRole.FontRole:
            return _settlement_grid_cell_font()
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:  # type: ignore[override]
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        if self._is_padding_row(index.row()):
            return Qt.ItemFlag.ItemIsEnabled
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() in (self.COL_PAY, self.COL_DISC):
            base |= Qt.ItemFlag.ItemIsEditable
        return base

    def setData(self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole) -> bool:  # type: ignore[override]
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        row, col = index.row(), index.column()
        if self._is_padding_row(row):
            return False
        if col not in (self.COL_PAY, self.COL_DISC):
            return False
        text = str(value).strip() if value is not None else ""
        try:
            num = _d(text)
            text = _s(num)
        except Exception:
            text = "0"
        ln = self._lines[row]
        if col == self.COL_PAY:
            ln.pay_amount = text
        else:
            ln.discount = text
        self.dataChanged.emit(
            index,
            index,
            [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole],
        )
        return True

    def line_at(self, row: int) -> Optional[SettlementLine]:
        if 0 <= row < len(self._lines):
            return self._lines[row]
        return None


class ArapSettlementDialog(QDialog):

    def __init__(
        self,
        backend: DbBackendBase,
        do_proc: str,
        voucher_row: List[str],
        voucher_fields: List[str],
        lang: LanguageCode = "CHN",
        table_name: str = "",
        other_title: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.lang = lang
        self.backend = backend
        self._all_lines: List[SettlementLine] = []
        self._doc: Optional[SettlementDocument] = None
        self._keyword = ""
        self._ready = False

        doc, err = load_settlement(
            backend,
            do_proc,
            voucher_row,
            voucher_fields,
            table_name=table_name,
            other_title=other_title,
        )
        if err or doc is None:
            QMessageBox.warning(
                parent or self,
                "清賬" if lang == "CHN" else "Settlement",
                err or ("無法載入清賬資料。" if lang == "CHN" else "Cannot load settlement data."),
            )
            return
        self._doc = doc
        self._all_lines = list(doc.lines)
        self._ready = True

        chn = lang == "CHN"
        self.setWindowTitle(
            "應收清賬" if doc.mode == "AR" and chn else
            "應付清賬" if chn else
            ("A/R Settlement" if doc.mode == "AR" else "A/P Settlement")
        )
        self.resize(1080, 720)
        self._build_ui()
        self._apply_filter()
        self._refresh_totals()

    def _t(self, chn: str, eng: str) -> str:
        return chn if self.lang == "CHN" else eng

    def _fmt_header_value(self, field_id: str, value: str) -> str:
        if field_id == "DATE" or is_date_field(field_id):
            return _fmt_date(value)
        if field_id == "SETTLE_AMT":
            return _fmt_amt(value)
        return value or ""

    def _header_field_specs(self) -> List[Tuple[str, str, str]]:
        """二欄排版固定 8 格：傳票編號、清賬日期、顧客/供應商、清賬金額，不足留空。"""
        assert self._doc is not None
        h = self._doc.header
        party_lbl = (
            "顧客編號-名稱" if self._doc.mode == "AR" else "供應商編號-名稱"
        ) if self.lang == "CHN" else (
            "Customer No.-Name" if self._doc.mode == "AR" else "Vendor No.-Name"
        )
        party_text = f"{h.party_key} - {h.party_name}".strip(" -")
        specs: List[Tuple[str, str, str]] = [
            ("VOU_KEY", self._t("傳票編號", "Voucher No."), h.vou_key),
            ("DATE", self._t("清賬日期", "Settle Date"), h.settle_date),
            ("PARTY", party_lbl, party_text),
            (
                "SETTLE_AMT",
                self._t("清賬金額", "Settle Amount"),
                h.settle_amount,
            ),
        ]
        while len(specs) < _SETTLE_HEADER_SLOTS:
            specs.append((f"__EMPTY_{len(specs)}__", "", ""))
        return specs[:_SETTLE_HEADER_SLOTS]

    def _add_header_short_pair(
        self,
        grid: QGridLayout,
        row: int,
        col_slot: int,
        label: QWidget,
        editor: QWidget,
    ) -> None:
        label_col = col_slot * 2
        editor_col = label_col + 1
        grid.addWidget(
            label,
            row,
            label_col,
            alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        grid.addWidget(editor, row, editor_col)

    def _apply_header_grid_fixed_widths(
        self, grid: QGridLayout, label_w: int
    ) -> None:
        for c in range(_SETTLE_HEADER_GRID_COLS):
            grid.setColumnStretch(c, 0)
        grid.setColumnMinimumWidth(0, label_w)
        grid.setColumnMinimumWidth(2, label_w)
        grid.setColumnMinimumWidth(1, _FORM_EDITOR_WIDTH_PX)
        grid.setColumnMinimumWidth(3, _FORM_EDITOR_WIDTH_PX)

    def _build_header_form(self) -> QWidget:
        base_dir = _font_base_dir_for(self)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(0)

        specs = self._header_field_specs()
        labels_by_field: dict[str, QLabel] = {}
        raw_titles: dict[str, str] = {}
        slot_items: List[Tuple[str, Optional[QLabel], Optional[QWidget]]] = []

        for field_id, title, value in specs:
            if field_id.startswith("__EMPTY_"):
                slot_items.append((field_id, None, None))
                continue
            label = QLabel(_form_label_caption(title))
            label.setStyleSheet(form_label_style(base_dir))
            label.setSizePolicy(
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
            )
            labels_by_field[field_id] = label
            raw_titles[field_id] = title
            le = QLineEdit(self._fmt_header_value(field_id, value))
            le.setReadOnly(True)
            le.setStyleSheet(form_editor_style(base_dir))
            le.setFixedWidth(_FORM_EDITOR_WIDTH_PX)
            le.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            if field_id == "SETTLE_AMT":
                le.setAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
            else:
                le.setAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
            slot_items.append((field_id, label, le))

        if labels_by_field:
            _apply_uniform_form_label_widths(labels_by_field, raw_titles, base_dir)
            label_w = max(lb.width() for lb in labels_by_field.values())
        else:
            label_w = _FORM_LABEL_WIDTH_MIN_PX
        for label in labels_by_field.values():
            label.setFixedWidth(label_w)
        self._apply_header_grid_fixed_widths(grid, label_w)

        for slot, (_field_id, label, editor) in enumerate(slot_items):
            row = slot // _SETTLE_HEADER_COLS
            col_slot = slot % _SETTLE_HEADER_COLS
            if label is None or editor is None:
                spacer_l = QWidget()
                spacer_l.setFixedSize(label_w, 24)
                spacer_e = QWidget()
                spacer_e.setFixedSize(_FORM_EDITOR_WIDTH_PX, 24)
                self._add_header_short_pair(grid, row, col_slot, spacer_l, spacer_e)
                continue
            self._add_header_short_pair(grid, row, col_slot, label, editor)

        panel = QWidget()
        panel.setLayout(grid)
        panel.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        return panel

    def _headers(self) -> List[str]:
        if self.lang == "CHN":
            return [
                "發票編號", "日期", "貨幣", "滙率", "發票金額",
                "已付金額", "發票餘額", "付款金額", "折扣金額",
            ]
        return [
            "Invoice No.", "Date", "Curr.", "Rate", "Invoice Amt.",
            "Paid Amt.", "Balance", "Payment", "Discount",
        ]

    def _build_ui(self) -> None:
        assert self._doc is not None
        root = QVBoxLayout(self)
        root.setSpacing(6)

        root.addWidget(self._build_header_form())

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel(self._t("搜尋:", "Search:")))
        self.txt_search = QLineEdit()
        self.txt_search.returnPressed.connect(self._on_search)
        search_row.addWidget(self.txt_search, 1)
        btn_search = QPushButton(self._t("搜尋", "Search"))
        btn_search.setIcon(icon_from_key(self.style(), "search"))
        btn_search.clicked.connect(self._on_search)
        apply_work_action_button_style(btn_search)
        search_row.addWidget(btn_search)
        btn_filter = QPushButton(self._t("過濾", "Filter"))
        btn_filter.setIcon(icon_from_key(self.style(), "filter"))
        btn_filter.clicked.connect(self._on_filter)
        apply_work_action_button_style(btn_filter)
        search_row.addWidget(btn_filter)
        root.addLayout(search_row)

        nav_row = QHBoxLayout()
        self.btn_nav_first = QPushButton()
        self.btn_nav_prev = QPushButton()
        self.btn_nav_next = QPushButton()
        self.btn_nav_last = QPushButton()
        bind_grid_nav_icon_buttons(
            self.lang,
            self.style(),
            self.btn_nav_first,
            self.btn_nav_prev,
            self.btn_nav_next,
            self.btn_nav_last,
        )
        self.btn_nav_first.clicked.connect(lambda: self._nav_select(0))
        self.btn_nav_prev.clicked.connect(self._nav_prev)
        self.btn_nav_next.clicked.connect(self._nav_next)
        self.btn_nav_last.clicked.connect(self._nav_last)
        for b in (
            self.btn_nav_first,
            self.btn_nav_prev,
            self.btn_nav_next,
            self.btn_nav_last,
        ):
            nav_row.addWidget(b)
        self.lbl_record_nav = QLabel("0/0")
        self.lbl_record_nav.setStyleSheet("font-weight:700; color:#1b3b6f;")
        nav_row.addWidget(self.lbl_record_nav, 1)

        btn_auto = QPushButton(self._t("自動清賬", "Auto Settle"))
        btn_auto.setIcon(icon_from_key(self.style(), "filter"))
        btn_auto.clicked.connect(self._on_auto_settle)
        apply_work_action_button_style(btn_auto)
        nav_row.addWidget(btn_auto)

        btn_save = QPushButton(self._t("儲存", "Save"))
        btn_save.setIcon(icon_from_key(self.style(), "save"))
        btn_save.clicked.connect(self._on_save)
        apply_work_action_button_style(btn_save)
        nav_row.addWidget(btn_save)

        btn_cancel = QPushButton(self._t("取消", "Cancel"))
        btn_cancel.setIcon(icon_from_key(self.style(), "cancel"))
        btn_cancel.clicked.connect(self.reject)
        apply_work_action_button_style(btn_cancel)
        nav_row.addWidget(btn_cancel)

        root.addLayout(nav_row)

        self.table = QTableView()
        configure_settlement_grid_table_view(self.table)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
        self.table.verticalHeader().setVisible(False)
        root.addWidget(self.table)

        foot = QGridLayout()
        foot.setHorizontalSpacing(0)
        foot.setVerticalSpacing(2)
        foot.setContentsMargins(0, 0, 0, 0)

        lbl_total = QLabel(self._t("合計:", "Total:"))
        lbl_exch_title = QLabel(self._t("兌匯差額:", "Exchange Diff.:"))
        lbl_remain_title = QLabel(self._t("尚餘清賬金額:", "Remain Settle:"))
        self._foot_title_labels = [lbl_total, lbl_exch_title, lbl_remain_title]
        for lbl in self._foot_title_labels:
            lbl.setStyleSheet("font-weight:700;")
            lbl.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            lbl.setSizePolicy(
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
            )

        self.lbl_sum_balance = QLabel()
        self.lbl_sum_pay = QLabel()
        self.lbl_sum_disc = QLabel()
        for lbl in (self.lbl_sum_balance, self.lbl_sum_pay, self.lbl_sum_disc):
            _style_footer_amount_widget(lbl, bordered=True)

        align_right = (
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        foot.addWidget(lbl_total, 0, 0, align_right)
        foot.addWidget(lbl_exch_title, 1, 0, align_right)
        foot.addWidget(lbl_remain_title, 2, 0, align_right)
        foot.addWidget(self.lbl_sum_balance, 0, 1, align_right)
        foot.addWidget(self.lbl_sum_pay, 0, 2, align_right)
        foot.addWidget(self.lbl_sum_disc, 0, 3, align_right)

        self.txt_exchange = QLineEdit()
        self.txt_exchange.setText(self._doc.header.exchange_diff or "0")
        self.txt_exchange.setFont(_settlement_grid_cell_font())
        self.txt_exchange.setStyleSheet(_footer_amount_style())
        self.txt_exchange.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.txt_exchange.textChanged.connect(self._refresh_totals)
        self.lbl_remain = QLabel()
        _style_footer_amount_widget(self.lbl_remain, bordered=True)

        foot.addWidget(self.txt_exchange, 1, 2, align_right)
        foot.addWidget(self.lbl_remain, 2, 2, align_right)
        for col in range(4):
            foot.setColumnStretch(col, 0)
        foot.setColumnStretch(4, 1)
        foot_host = QWidget()
        foot_host.setLayout(foot)
        foot_host.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        root.addWidget(foot_host)
        root.addStretch(1)

        h_header = self.table.horizontalHeader()
        h_header.sectionResized.connect(self._sync_footer_with_grid)
        h_header.geometriesChanged.connect(self._sync_footer_with_grid)
        self.table.horizontalScrollBar().valueChanged.connect(
            self._sync_footer_with_grid
        )

    def _on_auto_settle(self) -> None:
        if self._doc is None:
            return
        auto_settle_lines(
            self._all_lines,
            self._doc.header.settle_amount,
            self.txt_exchange.text(),
        )
        self._apply_filter()
        self._refresh_totals()

    def _refresh_settlement_grid_geometry(self) -> None:
        visible_rows = _SETTLE_GRID_VISIBLE_ROWS
        row_h = _SETTLE_GRID_ROW_HEIGHT_PX
        vh = self.table.verticalHeader()
        vh.setDefaultSectionSize(row_h)
        vh.setMinimumSectionSize(row_h)
        vh.setMaximumSectionSize(row_h)
        desired_h = _settlement_grid_table_outer_height(self.table, visible_rows)
        self.table.setMinimumHeight(desired_h)
        self.table.setMaximumHeight(desired_h)

    def _attach_grid_nav_selection(self) -> None:
        sm = self.table.selectionModel()
        if sm is None:
            return
        try:
            sm.selectionChanged.disconnect(self._refresh_nav)
        except TypeError:
            pass
        sm.selectionChanged.connect(self._refresh_nav)

    def _visible_lines(self) -> List[SettlementLine]:
        return filter_lines(self._all_lines, self._keyword)

    def _apply_filter(self, select_row: Optional[int] = None) -> None:
        lines = self._visible_lines()
        model = SettlementGridModel(self._headers(), lines, self.lang, self)
        model.dataChanged.connect(lambda *_: self._refresh_totals())
        self.table.setModel(model)
        self._refresh_settlement_grid_geometry()
        self._attach_grid_nav_selection()
        QTimer.singleShot(0, self._sync_footer_with_grid)
        if lines:
            row = (
                select_row
                if select_row is not None and 0 <= select_row < len(lines)
                else 0
            )
            self._nav_select(row)
        self._refresh_nav()

    def _on_search(self) -> None:
        keyword = self.txt_search.text().strip()
        if not keyword:
            return
        if self._keyword:
            self._keyword = ""
            self._apply_filter()
        target = find_line_index(self._all_lines, keyword)
        if target is None:
            return
        self._nav_select(target)
        m = self.table.model()
        if m is not None:
            idx = m.index(target, 0)
            self.table.scrollTo(idx, QAbstractItemView.ScrollHint.EnsureVisible)
        self._refresh_nav()

    def _on_filter(self) -> None:
        self._keyword = self.txt_search.text().strip()
        self._apply_filter()
        self._refresh_totals()

    def _refresh_nav(self, *_args) -> None:
        m = self.table.model()
        total = grid_model_data_row_count(m)
        cur = None
        idx = self.table.currentIndex()
        if idx.isValid() and 0 <= idx.row() < total:
            cur = idx.row() + 1
        self.lbl_record_nav.setText(format_record_nav_label(total, cur))

    def _nav_select(self, row: int) -> None:
        m = self.table.model()
        n = grid_model_data_row_count(m)
        if n <= 0 or row < 0 or row >= n:
            return
        self.table.selectRow(row)
        self.table.setCurrentIndex(m.index(row, 0))

    def _nav_prev(self) -> None:
        idx = self.table.currentIndex()
        if idx.isValid():
            self._nav_select(idx.row() - 1)

    def _nav_next(self) -> None:
        idx = self.table.currentIndex()
        if idx.isValid():
            self._nav_select(idx.row() + 1)

    def _nav_last(self) -> None:
        m = self.table.model()
        n = grid_model_data_row_count(m)
        if n > 0:
            self._nav_select(n - 1)

    def _refresh_totals(self) -> None:
        bal, pay, disc = sum_totals(self._all_lines)
        exch = _d(self.txt_exchange.text())
        settle = (
            _d(self._doc.header.settle_amount)
            if self._doc is not None
            else Decimal("0")
        )
        remain = remaining_settlement(settle, pay, disc, exch)
        self.lbl_sum_balance.setText(_fmt_amt(_s(bal)))
        self.lbl_sum_pay.setText(_fmt_amt(_s(pay)))
        self.lbl_sum_disc.setText(_fmt_amt(_s(disc)))
        self.lbl_remain.setText(_fmt_amt(_s(remain)))
        if self._doc is not None:
            self._doc.header.exchange_diff = _s(exch)

    def _sync_footer_with_grid(self, *_args) -> None:
        m = self.table.model()
        h = self.table.horizontalHeader()
        if m is None or h is None or m.columnCount() < 9:
            return
        col_balance = 6
        col_pay = 7
        col_disc = 8
        left = h.sectionViewportPosition(col_balance)
        w_bal = max(90, h.sectionSize(col_balance))
        w_pay = max(90, h.sectionSize(col_pay))
        w_disc = max(90, h.sectionSize(col_disc))
        title_w = max(0, left)
        for lbl in getattr(self, "_foot_title_labels", ()):
            lbl.setFixedWidth(title_w)
        self.lbl_sum_balance.setFixedWidth(w_bal)
        self.lbl_sum_pay.setFixedWidth(w_pay)
        self.lbl_sum_disc.setFixedWidth(w_disc)
        self.txt_exchange.setFixedWidth(w_pay)
        self.lbl_remain.setFixedWidth(w_pay)

    def _on_save(self) -> None:
        if self._doc is None:
            return
        self._doc.lines = list(self._all_lines)
        ok, err = save_settlement(self.backend, self._doc)
        if not ok:
            QMessageBox.warning(
                self,
                self._t("清賬", "Settlement"),
                err or self._t("儲存失敗。", "Save failed."),
            )
            return
        self.accept()


def open_arap_settlement(
    backend: Optional[DbBackendBase],
    do_proc: str,
    voucher_row: List[str],
    voucher_fields: List[str],
    lang: LanguageCode = "CHN",
    table_name: str = "",
    other_title: str = "",
    parent=None,
) -> None:
    if backend is None:
        QMessageBox.warning(
            parent,
            "清賬" if lang == "CHN" else "Settlement",
            "無法連線資料庫。" if lang == "CHN" else "Database unavailable.",
        )
        return
    dlg = ArapSettlementDialog(
        backend,
        do_proc,
        voucher_row,
        voucher_fields,
        lang=lang,
        table_name=table_name,
        other_title=other_title,
        parent=parent,
    )
    if getattr(dlg, "_ready", False):
        dlg.exec()
