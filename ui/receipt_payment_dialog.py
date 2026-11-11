"""發票收款／購貨付款對話框（顯示方式與系統標準／規劃介面一致）。"""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.data_dictionary import DataDictionary, LanguageCode
from core.db_backend import DbBackendBase
from core.display_format import (
    APP_DATE_QT_FORMAT,
    format_date_display,
    format_numeric_display,
    strip_numeric_commas,
)
from core.receipt_payment_service import (
    DEFAULT_PAY_METHOD,
    PAY_METHOD_OPTIONS,
    ReceiptPaymentDocument,
    is_receipt_payment_program,
    load_receipt_payment,
    save_receipt_payment,
)
from core.ui_icon_map import icon_from_key
from core.ui_theme import lookup_button_qss
from ui.work_page import (
    FORM_LAYOUT_PLANNED,
    _FORM_GRID_V_SPACING_PX,
    _FORM_LONG_TEXT_ROW_SPAN,
    _form_add_long_text_block,
    _form_add_short_field_pair,
    _form_apply_grid_column_stretch,
    _form_apply_planned_grid_stretch,
    _form_dims_for_mode,
    _form_label_align_above,
    _form_label_align_vcenter,
    _form_label_caption,
    _form_long_text_height_px,
    _form_make_stacked_cell,
    _form_row_for_long_text,
    apply_work_action_button_style,
    form_editor_locked_style,
    form_editor_style,
    form_label_style,
    get_form_layout_mode,
)

# 收付款介面：預設二欄；規劃介面四欄
_RP_COLS_DEFAULT = 2
_RP_COLS_PLANNED = 4


def open_receipt_payment(
    backend: Optional[DbBackendBase],
    do_proc: str,
    row: Sequence[str],
    physical_fields: List[str],
    *,
    lang: LanguageCode = "CHN",
    table_name: str = "",
    other_title: str = "",
    data_dict: Optional[DataDictionary] = None,
    app_base_dir: Optional[str] = None,
    login_date: str = "",
    parent: Optional[QWidget] = None,
    on_saved: Optional[Callable[[str], None]] = None,
) -> bool:
    """開啟收／付款介面；儲存成功回傳 True。"""
    if backend is None:
        QMessageBox.warning(
            parent,
            "錯誤" if lang == "CHN" else "Error",
            "資料庫未連線。" if lang == "CHN" else "Database is not connected.",
        )
        return False
    if not is_receipt_payment_program(do_proc, table_name, other_title):
        return False
    doc, err = load_receipt_payment(
        backend,
        row,
        physical_fields,
        table_name=table_name,
        other_title=other_title,
        login_date=login_date,
    )
    if err or doc is None:
        QMessageBox.warning(
            parent,
            "錯誤" if lang == "CHN" else "Error",
            err or ("無法載入。" if lang == "CHN" else "Load failed."),
        )
        return False
    dlg = ReceiptPaymentDialog(
        backend=backend,
        document=doc,
        lang=lang,
        data_dict=data_dict,
        app_base_dir=app_base_dir,
        other_title=other_title,
        parent=parent,
    )
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return False
    if on_saved and dlg.saved_vou_key:
        on_saved(dlg.saved_vou_key)
    return True


class ReceiptPaymentDialog(QDialog):
    """上下兩組：唯讀發票資訊 + 可編輯收／付款欄位（跟隨系統預設／規劃介面）。"""

    def __init__(
        self,
        *,
        backend: DbBackendBase,
        document: ReceiptPaymentDocument,
        lang: LanguageCode = "CHN",
        data_dict: Optional[DataDictionary] = None,
        app_base_dir: Optional[str] = None,
        other_title: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.backend = backend
        self.doc = document
        self.lang = lang
        self.data_dict = data_dict
        self._app_base_dir = app_base_dir
        self.saved_vou_key = ""
        self._form_layout_mode = get_form_layout_mode(app_base_dir)
        self._label_w, self._editor_w, self._editor_h = _form_dims_for_mode(
            self._form_layout_mode
        )
        self._planned = (
            (self._form_layout_mode or "").strip().lower() == FORM_LAYOUT_PLANNED
        )

        mode = document.header.mode
        if other_title.strip():
            title = other_title.strip()
        elif mode == "AR":
            title = "收款" if lang == "CHN" else "Receipt"
        else:
            title = "付款" if lang == "CHN" else "Payment"
        self.setWindowTitle(title)
        self.resize(1100 if self._planned else 720, 560 if self._planned else 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        root.addWidget(self._build_view_group())
        root.addWidget(self._build_edit_group())

        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        ok = box.button(QDialogButtonBox.StandardButton.Save)
        cancel = box.button(QDialogButtonBox.StandardButton.Cancel)
        if ok is not None:
            ok.setText("儲存" if lang == "CHN" else "Save")
            ok.setIcon(icon_from_key(self.style(), "save"))
            apply_work_action_button_style(ok)
        if cancel is not None:
            cancel.setText("取消" if lang == "CHN" else "Cancel")
            cancel.setIcon(icon_from_key(self.style(), "cancel"))
            apply_work_action_button_style(cancel)
        box.accepted.connect(self._on_save)
        box.rejected.connect(self.reject)
        root.addWidget(box)

    def _t(self, chn: str, eng: str) -> str:
        return chn if self.lang == "CHN" else eng

    def _fmt_amt(self, raw: str) -> str:
        return format_numeric_display(raw or "0", "amount")

    def _fmt_rate(self, raw: str) -> str:
        return format_numeric_display(raw or "0", "rate")

    def _fmt_date(self, raw: str) -> str:
        return format_date_display(raw or "")

    def _make_label(self, text: str) -> QLabel:
        lb = QLabel(_form_label_caption(text))
        lb.setStyleSheet(form_label_style(self._app_base_dir))
        lb.setFixedWidth(self._label_w)
        if self._planned:
            lb.setAlignment(_form_label_align_above())
        else:
            lb.setAlignment(_form_label_align_vcenter())
        return lb

    def _size_editor(self, ed: QWidget) -> None:
        ed.setFixedWidth(self._editor_w)
        ed.setFixedHeight(self._editor_h)

    def _make_ro_edit(self, value: str, *, align_right: bool = False) -> QLineEdit:
        ed = QLineEdit(value or "")
        ed.setReadOnly(True)
        ed.setStyleSheet(form_editor_locked_style(self._app_base_dir))
        self._size_editor(ed)
        if align_right:
            ed.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
        return ed

    def _make_edit(self, *, align_right: bool = False) -> QLineEdit:
        ed = QLineEdit()
        ed.setStyleSheet(form_editor_style(self._app_base_dir))
        self._size_editor(ed)
        if align_right:
            ed.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
        return ed

    def _make_date(self) -> QDateEdit:
        dt = QDateEdit()
        dt.setCalendarPopup(True)
        dt.setDisplayFormat(APP_DATE_QT_FORMAT)
        dt.setStyleSheet(form_editor_style(self._app_base_dir))
        self._size_editor(dt)
        return dt

    def _make_pay_method(self, current: str = "") -> QComboBox:
        cb = QComboBox()
        cb.setEditable(False)
        cb.addItems(list(PAY_METHOD_OPTIONS))
        want = (current or "").strip() or DEFAULT_PAY_METHOD
        idx = cb.findText(want)
        if idx < 0:
            # 相容大小寫
            for i in range(cb.count()):
                if cb.itemText(i).upper() == want.upper():
                    idx = i
                    break
        cb.setCurrentIndex(idx if idx >= 0 else cb.findText(DEFAULT_PAY_METHOD))
        cb.setStyleSheet(form_editor_style(self._app_base_dir))
        self._size_editor(cb)
        return cb

    def _make_remark(self) -> QTextEdit:
        te = QTextEdit()
        te.setAcceptRichText(False)
        te.setStyleSheet(form_editor_style(self._app_base_dir))
        te.setFixedHeight(_form_long_text_height_px(self._form_layout_mode))
        return te

    def _set_date(self, w: QDateEdit, text: str) -> None:
        s = format_date_display(text or "").strip().replace("-", "/")
        parts = s.split("/")
        if len(parts) == 3:
            try:
                y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                w.setDate(QDate(y, m, d))
                return
            except ValueError:
                pass
        w.setDate(QDate.currentDate())

    def _wrap_lookup(self, editor: QLineEdit, on_click) -> QWidget:
        wrap = QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(editor)
        btn = QPushButton("…")
        btn.setToolTip(self._t("查找", "Lookup"))
        btn.setFixedSize(self._editor_h, self._editor_h)
        try:
            btn.setStyleSheet(lookup_button_qss())
        except Exception:
            pass
        btn.clicked.connect(on_click)
        lay.addWidget(btn)
        wrap.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        return wrap

    def _fill_field_grid(
        self,
        grid: QGridLayout,
        pairs: List[Tuple[str, QWidget, bool]],
    ) -> None:
        """二欄（預設）／四欄（規劃）靠左；備註／長文字佔一整列。"""
        cols_per_row = _RP_COLS_PLANNED if self._planned else _RP_COLS_DEFAULT
        planned = self._planned
        grid.setContentsMargins(10, 14, 10, 10)
        grid.setHorizontalSpacing(8 if planned else 2)
        grid.setVerticalSpacing(_FORM_GRID_V_SPACING_PX)
        grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        labels_by_field: dict = {}
        row = 0
        col_slot = 0
        h_space = 8 if planned else 2
        for i, (cap, editor, is_long) in enumerate(pairs):
            label = self._make_label(cap)
            labels_by_field[f"f{i}"] = label
            if is_long:
                # 備註佔整列
                span_cols = cols_per_row
                span_rows = max(1, int(_FORM_LONG_TEXT_ROW_SPAN))
                row = _form_row_for_long_text(row, col_slot, span_cols=span_cols)
                if planned:
                    wide_w = self._editor_w * span_cols + h_space * max(0, span_cols - 1)
                    if isinstance(editor, QTextEdit):
                        editor.setFixedHeight(
                            _form_long_text_height_px(self._form_layout_mode)
                        )
                        editor.setFixedWidth(wide_w)
                        editor.setMinimumWidth(wide_w)
                    label.setFixedWidth(wide_w)
                    label.setMinimumWidth(wide_w)
                    label.setAlignment(_form_label_align_above())
                    cell = _form_make_stacked_cell(label, editor)
                    cell.setFixedWidth(wide_w)
                    cell.setMinimumWidth(wide_w)
                    grid.addWidget(cell, row, 0, span_rows, span_cols)
                    row += span_rows
                    col_slot = 0
                else:
                    row, col_slot = _form_add_long_text_block(
                        grid,
                        row,
                        label,
                        editor,
                        cols_per_row=cols_per_row,
                        layout_mode=self._form_layout_mode,
                    )
                continue

            if planned:
                cell = _form_make_stacked_cell(label, editor)
                grid.addWidget(cell, row, col_slot)
            else:
                _form_add_short_field_pair(grid, row, col_slot, label, editor)
            if col_slot == cols_per_row - 1:
                col_slot = 0
                row += 1
            else:
                col_slot += 1

        if planned:
            _form_apply_planned_grid_stretch(
                grid, cols_per_row=cols_per_row, editor_width=self._editor_w
            )
        else:
            _form_apply_grid_column_stretch(
                grid,
                labels_by_field,
                grid_ncols=cols_per_row * 2,
                editor_width=self._editor_w,
            )
        grid.setRowStretch(max(row + 1, 5), 1)

    def _build_view_group(self) -> QGroupBox:
        h = self.doc.header
        box = QGroupBox(self._t("發票資料", "Document"))
        grid = QGridLayout(box)
        if h.mode == "AR":
            party_key_lbl = self._t("顧客編號", "Customer No.")
            party_name_lbl = self._t("顧客名稱", "Customer Name")
            amt_lbl = self._t("發票金額", "Invoice Amount")
        else:
            party_key_lbl = self._t("供應商編號", "Vendor No.")
            party_name_lbl = self._t("供應商名稱", "Vendor Name")
            amt_lbl = self._t("購貨發票金額", "Purchase Amount")
        pairs: List[Tuple[str, QWidget, bool]] = [
            (
                self._t("發票編號", "Invoice No."),
                self._make_ro_edit(h.inv_no or h.inv_key),
                False,
            ),
            (
                self._t("日期", "Date"),
                self._make_ro_edit(self._fmt_date(h.inv_date)),
                False,
            ),
            (party_key_lbl, self._make_ro_edit(h.party_key), False),
            (party_name_lbl, self._make_ro_edit(h.party_name), False),
            (self._t("貨幣", "Currency"), self._make_ro_edit(h.currency), False),
            (
                self._t("滙率", "Rate"),
                self._make_ro_edit(self._fmt_rate(h.rate), align_right=True),
                False,
            ),
            (
                amt_lbl,
                self._make_ro_edit(self._fmt_amt(h.net_amt), align_right=True),
                False,
            ),
            (
                self._t("已付金額", "Paid Amount"),
                self._make_ro_edit(self._fmt_amt(h.paid_amt), align_right=True),
                False,
            ),
            (
                self._t("尚餘金額", "Balance"),
                self._make_ro_edit(self._fmt_amt(h.balance), align_right=True),
                False,
            ),
        ]
        self._fill_field_grid(grid, pairs)
        return box

    def _on_pay_amount_editing_finished(self) -> None:
        raw = self._pay_amount.text().strip()
        if not raw:
            return
        self._pay_amount.setText(self._fmt_amt(raw))

    def _build_edit_group(self) -> QGroupBox:
        f = self.doc.form
        box = QGroupBox(self._t("收付款資料", "Payment"))
        grid = QGridLayout(box)

        self._pay_amount = self._make_edit(align_right=True)
        self._pay_amount.setText(self._fmt_amt(f.pay_amount))
        self._pay_amount.editingFinished.connect(self._on_pay_amount_editing_finished)
        self._pay_date = self._make_date()
        self._set_date(self._pay_date, f.pay_date)
        self._pay_method = self._make_pay_method(f.pay_method)
        self._bank = self._make_edit()
        self._bank.setText(f.bank)
        self._cheque = self._make_edit()
        self._cheque.setText(f.cheque)
        self._chq_date = self._make_date()
        self._set_date(self._chq_date, f.chq_date or f.pay_date)
        self._debit_ac = self._make_edit()
        self._debit_ac.setText(f.debit_ac)
        self._credit_ac = self._make_edit()
        self._credit_ac.setText(f.credit_ac)
        self._remark = self._make_remark()
        self._remark.setPlainText(f.remark or "")

        debit_wrap = self._wrap_lookup(
            self._debit_ac, lambda: self._lookup_account(self._debit_ac)
        )
        credit_wrap = self._wrap_lookup(
            self._credit_ac, lambda: self._lookup_account(self._credit_ac)
        )

        pairs: List[Tuple[str, QWidget, bool]] = [
            (self._t("付款金額", "Pay Amount"), self._pay_amount, False),
            (self._t("付款日期", "Pay Date"), self._pay_date, False),
            (self._t("付款方式", "Pay Method"), self._pay_method, False),
            (self._t("銀行", "Bank"), self._bank, False),
            (self._t("支票編號", "Cheque No."), self._cheque, False),
            (self._t("支票日期", "Cheque Date"), self._chq_date, False),
            (self._t("借項賬戶編號", "Debit A/C"), debit_wrap, False),
            (self._t("貸項賬戶編號", "Credit A/C"), credit_wrap, False),
            (self._t("備註", "Remark"), self._remark, True),
        ]
        self._fill_field_grid(grid, pairs)
        return box

    def _lookup_account(self, target: QLineEdit) -> None:
        if self.data_dict is None:
            QMessageBox.warning(
                self,
                self._t("提示", "Notice"),
                self._t("無法載入查找資料。", "Lookup data is unavailable."),
            )
            return
        from ui.lookup_dialog import LookupPickerDialog

        dlg = LookupPickerDialog(
            lookup_db="ACCOUNT",
            lookup_ret="AC_KEY",
            backend=self.backend,
            data_dict=self.data_dict,
            lang=self.lang,
            parent=self,
            app_base_dir=self._app_base_dir,
        )
        accepted = dlg.exec() == QDialog.DialogCode.Accepted
        if accepted:
            val = (dlg.selected_value or "").strip()
            if val:
                target.setText(val)
        target.setFocus(Qt.FocusReason.OtherFocusReason)
        target.selectAll()

    def _collect_form(self) -> None:
        f = self.doc.form
        f.pay_amount = strip_numeric_commas(self._pay_amount.text())
        f.pay_date = self._pay_date.date().toString(APP_DATE_QT_FORMAT)
        f.pay_method = self._pay_method.currentText().strip()
        f.bank = self._bank.text().strip()
        f.cheque = self._cheque.text().strip()
        f.chq_date = self._chq_date.date().toString(APP_DATE_QT_FORMAT)
        f.remark = self._remark.toPlainText().strip()
        f.debit_ac = self._debit_ac.text().strip()
        f.credit_ac = self._credit_ac.text().strip()

    def _on_save(self) -> None:
        self._collect_form()
        ok, err, vou_key = save_receipt_payment(self.backend, self.doc)
        if not ok:
            QMessageBox.warning(
                self,
                self._t("錯誤", "Error"),
                err or self._t("儲存失敗。", "Save failed."),
            )
            return
        self.saved_vou_key = vou_key
        QMessageBox.information(
            self,
            self._t("儲存成功", "Saved"),
            (
                f"編號已儲存：VOU_KEY = {vou_key}"
                if self.lang == "CHN"
                else f"Saved number: VOU_KEY = {vou_key}"
            ),
        )
        self.accept()
