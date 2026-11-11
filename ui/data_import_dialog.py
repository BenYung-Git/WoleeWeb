"""DATAIMPORT 匯入類型選擇對話框。"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.data_dictionary import LanguageCode
from core.data_import_service import (
    IMPORT_KINDS,
    IMPORT_MAPPINGS,
    is_data_import_program,
    list_pending_import_grid,
    run_data_import,
)
from core.db_backend import DbBackendBase
from core.db_factory import get_backend_for_path, prepare_transfer_db_for_import

# GRID：至少同時看到 10 筆；超過則垂直捲軸。表頭 11pt、資料 10pt。
_IMPORT_GRID_VISIBLE_ROWS = 10
_IMPORT_GRID_ROW_H = 26
_IMPORT_GRID_HEADER_PT = 11
_IMPORT_GRID_CELL_PT = 10


def _align_flags(*, numeric: bool) -> Qt.AlignmentFlag:
    if numeric:
        return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter


class DataImportDialog(QDialog):
    def __init__(
        self,
        transfer_backend: Optional[DbBackendBase],
        company_backend: Optional[DbBackendBase],
        *,
        lang: LanguageCode = "CHN",
        parent=None,
        base_dir: str = "",
    ) -> None:
        super().__init__(parent)
        self._company = company_backend
        self._lang = lang
        self._base_dir = os.path.abspath(base_dir) if base_dir else ""
        # 各匯入類型可選不同來源資料夾；開啟時一律先鎖定規格預設 TRANSFER
        self._folder_by_kind: Dict[str, str] = {
            k: self._base_dir for k in IMPORT_KINDS
        }
        default_folder = self._base_dir
        try:
            from core.db_factory import (
                resolve_default_transfer_folder,
                resolve_spec_transfer_folder,
            )

            pref = resolve_spec_transfer_folder(self._base_dir)
            if pref:
                default_folder = pref
            else:
                default_folder, _note = resolve_default_transfer_folder(self._base_dir)
        except Exception:
            if transfer_backend is not None:
                dbp = getattr(transfer_backend, "db_path", "") or ""
                if dbp:
                    default_folder = os.path.dirname(os.path.abspath(dbp))
        for k in IMPORT_KINDS:
            self._folder_by_kind[k] = default_folder
        self._transfer = transfer_backend
        chn = lang == "CHN"
        self.setWindowTitle("資料匯入" if chn else "Data Import")
        self.setMinimumWidth(900)
        self.setMinimumHeight(560)

        layout = QVBoxLayout(self)
        hint = (
            "來源：TRANSFER 資料庫；目標：公司資料庫。\n"
            "請以下拉選單選擇匯入類型（PURCHASE／INVOICE／STOCK）與來源資料夾"
            "（各類型可選不同資料夾）。採購／發票以 GRID 顯示 POSTED=FALSE 的未處理主檔，可複選後匯入。"
            if chn
            else "Source: TRANSFER DB; Destination: company DB.\n"
            "Use the combo box to select import type (PURCHASE/INVOICE/STOCK) and source folder "
            "(each kind may use a different folder).\n"
            "Purchase/Invoice show unposted headers in a GRID for multi-select."
        )
        layout.addWidget(QLabel(hint))

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("來源資料夾:" if chn else "Source folder:"))
        self._txt_folder = QLineEdit(default_folder)
        self._txt_folder.setPlaceholderText(
            "含 TRANSFER.sqlite 的資料夾（建議 docBiz\\Transfer）"
            if chn
            else "Folder with TRANSFER.sqlite (usually docBiz\\Transfer)"
        )
        folder_row.addWidget(self._txt_folder, 1)
        self._btn_browse = QPushButton("瀏覽…" if chn else "Browse…")
        self._btn_browse.clicked.connect(self._browse_folder)
        folder_row.addWidget(self._btn_browse)
        layout.addLayout(folder_row)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#1b3b6f; font-weight:600;")
        layout.addWidget(self._status)

        kind_row = QHBoxLayout()
        kind_row.addWidget(QLabel("匯入類型:" if chn else "Import type:"))
        self._cbo_kind = QComboBox(self)
        labels = {
            "PURCHASE": "採購 (PURCHASE)" if chn else "Purchase (PURCHASE)",
            "INVOICE": "發票 (INVOICE)" if chn else "Invoice (INVOICE)",
            "STOCK": "庫存 (STOCK)" if chn else "Stock (STOCK)",
        }
        for kind in IMPORT_KINDS:
            pairs = IMPORT_MAPPINGS.get(kind, ())
            detail = "; ".join(f"TRANSFER.{s} → {d}" for s, d in pairs)
            self._cbo_kind.addItem(f"{labels.get(kind, kind)} — {detail}", kind)
        self._cbo_kind.currentIndexChanged.connect(self._on_kind_index_changed)
        kind_row.addWidget(self._cbo_kind, 1)
        layout.addLayout(kind_row)

        self._pending_label = QLabel(
            "待匯入主檔（GRID）：" if chn else "Pending headers (GRID):"
        )
        layout.addWidget(self._pending_label)

        self._grid = QTableWidget(0, 0, self)
        self._grid.setObjectName("dataImportGrid")
        self._grid.setStyleSheet(
            "#dataImportGrid::item { padding-top: 0px; padding-bottom: 0px; "
            "padding-left: 6px; padding-right: 6px; }"
        )
        self._grid.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._grid.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._grid.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._grid.setAlternatingRowColors(True)
        self._grid.verticalHeader().setVisible(False)
        self._grid.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._grid.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._grid.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)
        self._grid.horizontalHeader().setStretchLastSection(False)
        self._grid.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._apply_grid_fonts()
        self._apply_grid_visible_rows()
        layout.addWidget(self._grid, 1)

        pick_row = QHBoxLayout()
        self._btn_all = QPushButton("全選" if chn else "Select All")
        self._btn_none = QPushButton("全不選" if chn else "Select None")
        self._btn_all.clicked.connect(self._select_all_pending)
        self._btn_none.clicked.connect(self._select_none_pending)
        pick_row.addWidget(self._btn_all)
        pick_row.addWidget(self._btn_none)
        pick_row.addStretch(1)
        layout.addLayout(pick_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_import)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._txt_folder.editingFinished.connect(self._on_folder_edited)

        self._cbo_kind.blockSignals(True)
        self._cbo_kind.setCurrentIndex(0)
        self._cbo_kind.blockSignals(False)
        self._on_kind_changed(IMPORT_KINDS[0])

    def _selected_kind(self) -> str:
        data = self._cbo_kind.currentData()
        if isinstance(data, str) and data:
            return data
        return IMPORT_KINDS[0]

    def _on_kind_index_changed(self, _index: int) -> None:
        self._on_kind_changed(self._selected_kind())

    def _current_folder(self) -> str:
        return (self._txt_folder.text() or "").strip()

    def _browse_folder(self) -> None:
        chn = self._lang == "CHN"
        start = self._current_folder() or self._base_dir or os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(
            self,
            "選擇含 TRANSFER.sqlite 的資料夾" if chn else "Select folder with TRANSFER.sqlite",
            start,
        )
        if path:
            self._txt_folder.setText(path)
            self._apply_folder_for_kind(self._selected_kind(), path)

    def _on_folder_edited(self) -> None:
        self._apply_folder_for_kind(self._selected_kind(), self._current_folder())

    def _apply_folder_for_kind(self, kind: str, folder: str) -> None:
        key = (kind or "").strip().upper() or IMPORT_KINDS[0]
        folder = (folder or "").strip() or self._base_dir
        self._folder_by_kind[key] = folder
        self._reconnect_transfer(folder)
        self._reload_pending(key)

    def _reconnect_transfer(self, folder: str, *, for_write: bool = False) -> Optional[str]:
        """依資料夾重連 TRANSFER；回傳錯誤訊息或 None。"""
        path, _share, err, warn = prepare_transfer_db_for_import(
            self._base_dir or folder,
            for_write=for_write,
            folder=folder,
        )
        if err:
            self._transfer = None
            self._set_status(err)
            return err
        self._transfer = get_backend_for_path(path)
        msg = f"來源：{path}"
        if warn:
            msg = f"{msg}\n{warn}"
        self._set_status(msg)
        return None

    def _apply_grid_fonts(self) -> None:
        f_cell = QFont(self._grid.font())
        f_cell.setPointSize(_IMPORT_GRID_CELL_PT)
        f_cell.setWeight(QFont.Weight.Normal)
        self._grid.setFont(f_cell)
        hdr = self._grid.horizontalHeader()
        f_hdr = QFont(hdr.font())
        f_hdr.setPointSize(_IMPORT_GRID_HEADER_PT)
        f_hdr.setWeight(QFont.Weight.Bold)
        hdr.setFont(f_hdr)
        self._grid.verticalHeader().setDefaultSectionSize(_IMPORT_GRID_ROW_H)
        fm_hdr = QFontMetrics(f_hdr)
        hdr.setFixedHeight(max(hdr.sizeHint().height(), fm_hdr.height() + 12))

    def _apply_grid_visible_rows(self) -> None:
        """固定可視 10 列高度；資料少於 10 筆時保留空白列空間，超過則垂直捲軸。"""
        visible = _IMPORT_GRID_VISIBLE_ROWS
        row_h = _IMPORT_GRID_ROW_H
        hdr = self._grid.horizontalHeader()
        header_h = max(hdr.height(), hdr.sizeHint().height(), 28)
        grid_lines = max(0, visible - 1) if self._grid.showGrid() else 0
        frame = 2 * max(1, self._grid.frameWidth())
        desired = row_h * visible + grid_lines + header_h + frame + 4
        self._grid.setMinimumHeight(desired)
        self._grid.setMaximumHeight(desired)

        def _fine_tune() -> None:
            vp_h = self._grid.viewport().height()
            need = row_h * visible + grid_lines
            if vp_h > 0 and vp_h < need:
                extra = need - vp_h
                self._grid.setMinimumHeight(desired + extra)
                self._grid.setMaximumHeight(desired + extra)

        QTimer.singleShot(0, _fine_tune)

    def _clear_grid(self) -> None:
        self._grid.clear()
        self._grid.setRowCount(0)
        self._grid.setColumnCount(0)

    def _fill_pending_grid(
        self,
        columns: Sequence[dict],
        rows: Sequence[dict],
    ) -> None:
        col_count = max(1, len(columns))
        self._grid.setColumnCount(col_count)
        numeric_flags: List[bool] = []
        for c_i in range(col_count):
            col = columns[c_i] if c_i < len(columns) else {}
            title = str(col.get("title") or col.get("name") or "") or ("TX_KEY" if c_i == 0 else "")
            numeric = bool(col.get("numeric"))
            numeric_flags.append(numeric)
            hi = QTableWidgetItem(title)
            hi.setTextAlignment(int(_align_flags(numeric=numeric)))
            hi.setFont(self._grid.horizontalHeader().font())
            self._grid.setHorizontalHeaderItem(c_i, hi)
        self._grid.setRowCount(len(rows))
        f_cell = self._grid.font()
        for r_i, row in enumerate(rows):
            cells = list(row.get("cells") or [])
            row_key = str(row.get("key") or "").strip()
            for c_i in range(col_count):
                text = cells[c_i] if c_i < len(cells) else ""
                item = QTableWidgetItem(str(text))
                item.setFont(f_cell)
                item.setTextAlignment(int(_align_flags(numeric=numeric_flags[c_i])))
                if c_i == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row_key)
                self._grid.setItem(r_i, c_i, item)
        # 不足 10 筆時補空白列空間（不可選），超過 10 筆則靠垂直捲軸瀏覽
        data_n = len(rows)
        pad_n = max(0, _IMPORT_GRID_VISIBLE_ROWS - data_n)
        if pad_n:
            self._grid.setRowCount(data_n + pad_n)
            for r_i in range(data_n, data_n + pad_n):
                for c_i in range(col_count):
                    item = QTableWidgetItem("")
                    item.setFlags(Qt.ItemFlag.NoItemFlags)
                    item.setFont(f_cell)
                    item.setTextAlignment(int(_align_flags(numeric=numeric_flags[c_i])))
                    self._grid.setItem(r_i, c_i, item)
        self._grid.resizeColumnsToContents()
        self._apply_grid_visible_rows()
        if rows:
            # 只選取實際資料列（略過空白墊列）
            self._grid.clearSelection()
            for r_i in range(data_n):
                self._grid.selectRow(r_i)
        else:
            self._grid.clearSelection()

    def _on_kind_changed(self, kind: str) -> None:
        key = (kind or "").strip().upper()
        folder = self._folder_by_kind.get(key) or self._base_dir
        self._txt_folder.blockSignals(True)
        self._txt_folder.setText(folder)
        self._txt_folder.blockSignals(False)
        self._reconnect_transfer(folder)
        self._reload_pending(key)

    def _reload_pending(self, kind: str) -> None:
        chn = self._lang == "CHN"
        self._clear_grid()
        key = (kind or "").strip().upper()
        needs_pick = key in ("PURCHASE", "INVOICE")
        self._pending_label.setVisible(True)
        self._btn_all.setVisible(needs_pick)
        self._btn_none.setVisible(needs_pick)
        self._grid.setVisible(needs_pick)
        if not needs_pick:
            self._pending_label.setText(
                "庫存匯入：將 TRANSFER.STK 資料寫入公司庫 STOCK。"
                if chn
                else "Stock import: copy TRANSFER.STK into company STOCK."
            )
            return
        src_name = "PUR_HEADER" if key == "PURCHASE" else "INV_HEADER"
        self._pending_label.setText(
            f"待匯入主檔 GRID（TRANSFER.{src_name}，POSTED=FALSE）："
            if chn
            else f"Pending GRID (TRANSFER.{src_name}, POSTED=FALSE):"
        )
        if self._transfer is None:
            self._pending_label.setText(
                (self._pending_label.text() + "\n無法連線 TRANSFER 資料庫。")
                if chn
                else (self._pending_label.text() + "\nTRANSFER database unavailable.")
            )
            self._apply_grid_visible_rows()
            return
        grid, err = list_pending_import_grid(self._transfer, key)
        if err:
            self._pending_label.setText(f"{self._pending_label.text()}\n{err}")
            self._apply_grid_visible_rows()
            return
        columns = list(grid.get("columns") or [])
        rows = list(grid.get("rows") or [])
        self._fill_pending_grid(columns, rows)
        if not rows:
            self._pending_label.setText(
                (
                    f"TRANSFER.{src_name} 沒有 POSTED=FALSE 的未處理資料。"
                    if chn
                    else f"No unposted rows in TRANSFER.{src_name} (POSTED=FALSE)."
                )
            )
            return
        self._pending_label.setText(
            (
                f"待匯入主檔 GRID（TRANSFER.{src_name}，POSTED=FALSE）：共 {len(rows)} 筆"
                if chn
                else f"Pending GRID (TRANSFER.{src_name}, POSTED=FALSE): {len(rows)} row(s)"
            )
        )

    def _selected_keys(self) -> List[str]:
        keys: List[str] = []
        seen = set()
        for idx in self._grid.selectionModel().selectedRows():
            item = self._grid.item(idx.row(), 0)
            if item is None:
                continue
            key = str(item.data(Qt.ItemDataRole.UserRole) or item.text() or "").strip()
            if key and key not in seen:
                seen.add(key)
                keys.append(key)
        return keys

    def _select_all_pending(self) -> None:
        self._grid.clearSelection()
        for r_i in range(self._grid.rowCount()):
            item = self._grid.item(r_i, 0)
            if item is None:
                continue
            key = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
            if key:
                self._grid.selectRow(r_i)

    def _select_none_pending(self) -> None:
        self._grid.clearSelection()

    def _set_status(self, text: str) -> None:
        self._status.setText(text or "")
        QApplication.processEvents()

    def _on_import(self) -> None:
        if self._company is None:
            QMessageBox.warning(
                self,
                "錯誤" if self._lang == "CHN" else "Error",
                "無法連線公司資料庫。",
            )
            return
        kind = self._selected_kind()
        folder = self._current_folder()
        self._folder_by_kind[kind] = folder
        # 執行前以可寫模式重連 TRANSFER
        err = self._reconnect_transfer(folder, for_write=True)
        if err or self._transfer is None:
            QMessageBox.warning(
                self,
                "錯誤" if self._lang == "CHN" else "Error",
                err or ("無法連線 TRANSFER 資料庫。" if self._lang == "CHN" else "TRANSFER unavailable."),
            )
            return
        chn = self._lang == "CHN"
        title = "確認匯入" if chn else "Confirm Import"
        pairs = IMPORT_MAPPINGS.get(kind, ())
        detail = "\n".join(f"  TRANSFER.{s} → {d}" for s, d in pairs)
        selected = self._selected_keys() if kind in ("PURCHASE", "INVOICE") else None
        if kind in ("PURCHASE", "INVOICE") and not selected:
            QMessageBox.warning(
                self,
                title,
                "請在 GRID 中選擇要匯入的未處理資料。"
                if chn
                else "Please select unposted rows in the GRID.",
            )
            return
        extra = ""
        if selected:
            extra = (
                f"\n\n已選 {len(selected)} 筆主檔。\n來源資料夾：{folder}"
                if chn
                else f"\n\n{len(selected)} header row(s) selected.\nFolder: {folder}"
            )
        else:
            extra = (
                f"\n\n來源資料夾：{folder}" if chn else f"\n\nFolder: {folder}"
            )
        prompt = (
            f"確定執行「{kind}」匯入？\n\n{detail}{extra}"
            if chn
            else f"Run import for「{kind}」?\n\n{detail}{extra}"
        )
        if QMessageBox.question(self, title, prompt) != QMessageBox.StandardButton.Yes:
            return
        # 公司庫寫入前準備（網路碟 WAL／鎖定常導致 readonly）
        try:
            from core.db_factory import _is_sqlite_path, prepare_sqlite_for_write

            co_path = str(getattr(self._company, "db_path", "") or "")
            if co_path and _is_sqlite_path(co_path):
                prep_err = prepare_sqlite_for_write(co_path)
                if prep_err:
                    QMessageBox.warning(
                        self,
                        "匯入失敗" if chn else "Import Failed",
                        f"公司庫寫入失敗：{prep_err}"
                        if chn
                        else f"Company DB write failed: {prep_err}",
                    )
                    self._set_status(prep_err)
                    return
        except Exception:
            pass
        self._set_status("處理中…" if chn else "Processing…")
        result = run_data_import(
            self._transfer,
            self._company,
            kind,
            selected_keys=selected,
            progress=self._set_status,
        )
        if result.ok:
            QMessageBox.information(
                self,
                "完成" if chn else "Done",
                result.message,
            )
            self.accept()
        else:
            QMessageBox.warning(
                self,
                "匯入失敗" if chn else "Import Failed",
                result.message,
            )
            self._set_status(result.message)
            # 失敗後重新載入待匯清單
            self._reconnect_transfer(folder, for_write=False)
            self._reload_pending(kind)


def open_data_import(
    transfer_backend: Optional[DbBackendBase],
    company_backend: Optional[DbBackendBase] = None,
    *,
    do_proc: str = "",
    lang: LanguageCode = "CHN",
    parent=None,
    base_dir: str = "",
) -> None:
    """開啟匯入對話框。若僅傳一個 backend（舊呼叫），視同來源=目標（不建議）。"""
    if not is_data_import_program(do_proc):
        return
    src = transfer_backend
    dst = company_backend if company_backend is not None else transfer_backend
    dlg = DataImportDialog(
        src, dst, lang=lang, parent=parent, base_dir=base_dir
    )
    dlg.exec()
