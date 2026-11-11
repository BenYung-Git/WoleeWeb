"""新增編號介面：PROGRAM.NUM_CONTROL 空白時手動指定 KEY_CODE 欄位。"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.data_dictionary import DataDictionary, LanguageCode
from core.db_backend import DbBackendBase
from core.ui_icon_map import icon_from_key
from core.ui_theme import lookup_button_qss


class KeyAssignDialog(QDialog):
    """
    手動指定 KEY_CODE。
    右側 LOOKUP：以 GRID 顯示 COLUMNS 對應 DBF_NAME（或 LOOKUP_DB）資料；
    關閉後焦點回到 KEY_CODE 輸入欄。確定＝帶編號回儲存流程；取消＝返回輸入介面。
    """

    def __init__(
        self,
        *,
        key_field: str,
        key_label: str,
        suggested_key: str,
        lang: LanguageCode = "CHN",
        parent=None,
        backend: Optional[DbBackendBase] = None,
        data_dict: Optional[DataDictionary] = None,
        table_name: str = "",
        lookup_db: str = "",
        lookup_ret: str = "",
        app_base_dir: Optional[str] = None,
    ) -> None:
        super().__init__(parent)
        self.lang = lang
        self._key_field = (key_field or "").strip()
        self._backend = backend
        self._data_dict = data_dict
        self._table_name = (table_name or "").strip()
        # COLUMNS.LOOKUP_DB 優先；否則顯示本作業 WORK_FILE（DBF_NAME）資料
        self._lookup_db = (lookup_db or "").strip() or self._table_name
        self._lookup_ret = (lookup_ret or "").strip() or self._key_field
        self._app_base_dir = app_base_dir

        self.setWindowTitle("新增編號" if lang == "CHN" else "New document number")
        self.resize(480, 200)
        self.setMinimumSize(420, 180)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(16, 14, 16, 14)

        hint = (
            "請輸入或選擇單據編號後按確定儲存；取消則返回輸入資料介面。"
            if lang == "CHN"
            else "Enter or pick a document number, then OK to save; Cancel returns to the form."
        )
        hint_lbl = QLabel(hint)
        hint_lbl.setWordWrap(True)
        hint_lbl.setStyleSheet("font-size: 10pt;")
        lay.addWidget(hint_lbl)

        row = QHBoxLayout()
        row.setSpacing(8)
        cap = (key_label or key_field or "").strip()
        cap_lbl = QLabel(f"{cap}:" if cap else "")
        cap_lbl.setStyleSheet("font-size: 10.5pt; font-weight: 700;")
        row.addWidget(cap_lbl)

        self._edit = QLineEdit()
        self._edit.setText((suggested_key or "").strip())
        self._edit.selectAll()
        self._edit.setMinimumHeight(32)
        self._edit.setStyleSheet("font-size: 11pt; padding: 3px 6px;")
        row.addWidget(self._edit, 1)

        self._btn_lookup = QPushButton("…")
        self._btn_lookup.setToolTip("查找" if lang == "CHN" else "Lookup")
        self._btn_lookup.setFixedSize(32, 32)
        try:
            self._btn_lookup.setStyleSheet(lookup_button_qss())
        except Exception:
            pass
        self._btn_lookup.setEnabled(bool(self._backend and self._lookup_db))
        self._btn_lookup.clicked.connect(self._on_lookup)
        row.addWidget(self._btn_lookup)
        lay.addLayout(row)

        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = box.button(QDialogButtonBox.StandardButton.Ok)
        cancel_btn = box.button(QDialogButtonBox.StandardButton.Cancel)
        if ok_btn is not None:
            ok_btn.setText("儲存" if lang == "CHN" else "Save")
            ok_btn.setIcon(icon_from_key(self.style(), "save"))
            ok_btn.setMinimumHeight(32)
            ok_btn.setMinimumWidth(88)
        if cancel_btn is not None:
            cancel_btn.setText("取消" if lang == "CHN" else "Cancel")
            cancel_btn.setIcon(icon_from_key(self.style(), "cancel"))
            cancel_btn.setMinimumHeight(32)
            cancel_btn.setMinimumWidth(88)
        box.accepted.connect(self._on_ok)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

        QTimer.singleShot(0, self._focus_key_edit)

    def _focus_key_edit(self) -> None:
        self._edit.setFocus(Qt.FocusReason.OtherFocusReason)
        self._edit.selectAll()

    def _on_lookup(self) -> None:
        if not self._backend or not self._lookup_db:
            return
        from ui.lookup_dialog import LookupPickerDialog

        dd = self._data_dict
        if dd is None:
            QMessageBox.warning(
                self,
                "提示" if self.lang == "CHN" else "Notice",
                "無法載入查找資料。" if self.lang == "CHN" else "Lookup data is unavailable.",
            )
            return
        dlg = LookupPickerDialog(
            lookup_db=self._lookup_db,
            lookup_ret=self._lookup_ret or self._key_field,
            backend=self._backend,
            data_dict=dd,
            lang=self.lang,
            parent=self,
            app_base_dir=self._app_base_dir,
        )
        accepted = dlg.exec() == QDialog.DialogCode.Accepted
        if accepted:
            val = (dlg.selected_value or "").strip()
            if val:
                self._edit.setText(val)
        # LOOKUP 關閉後（確定或取消）焦點回到 KEY_CODE
        QTimer.singleShot(0, self._focus_key_edit)

    def _on_ok(self) -> None:
        if not (self._edit.text() or "").strip():
            QMessageBox.warning(
                self,
                "提示" if self.lang == "CHN" else "Notice",
                "請輸入編號。" if self.lang == "CHN" else "Please enter a document number.",
            )
            self._focus_key_edit()
            return
        self.accept()

    @property
    def key_field(self) -> str:
        return self._key_field

    def assigned_key(self) -> str:
        return (self._edit.text() or "").strip()
