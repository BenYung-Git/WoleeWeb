from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import Qt, QDate, QEvent, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QPushButton,
    QMessageBox,
    QFrame,
)

from core.display_format import APP_DATE_QT_FORMAT
from core.ui_icon_map import icon_from_key
from core.auth import (
    UserSession,
    authenticate,
    detect_last_company_by_credentials,
    load_available_company_keys,
    record_login_success,
    resolve_user_data_path,
)
from core.db_factory import validate_company_db

try:
    import ctypes
    _HAS_IMM = True
except Exception:
    _HAS_IMM = False


class LoginDialog(QDialog):
    """啟動登入：使用者編號、密碼、公司、日期。"""

    def __init__(self, base_dir: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("企業管理系統 — 登入")
        self.resize(560, 430)
        self.base_dir = base_dir
        self.user_data_path = resolve_user_data_path(base_dir)
        self._session: Optional[UserSession] = None

        self._build_ui()
        self._load_companies()

    def _force_english_ime(self, widget: QLineEdit) -> None:
        """
        嘗試強制 Windows IME 進入英數/Latin 模式（比 setInputMethodHints 更接近你要的「預設英文輸入法」）。
        若環境不支援或呼叫失敗，仍會保留 fallback hints。
        """
        # fallback：仍設置 hints
        try:
            widget.setInputMethodHints(Qt.InputMethodHint.ImhPreferLatin)
        except Exception:
            pass

        if not _HAS_IMM:
            return
        try:
            hwnd = int(widget.winId())
            h_imc = ctypes.windll.imm32.ImmGetContext(hwnd)
            if not h_imc:
                return
            # conversion=0, sentence=0 通常代表英數/直接輸入模式
            ctypes.windll.imm32.ImmSetConversionStatus(h_imc, 0, 0)
            # 保持開啟，不關閉 IME
            ctypes.windll.imm32.ImmSetOpenStatus(h_imc, 1)
            ctypes.windll.imm32.ImmReleaseContext(hwnd, h_imc)
        except Exception:
            # 若失敗，不打斷使用流程
            pass

    def session(self) -> Optional[UserSession]:
        return self._session

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(16)
        root.setContentsMargins(22, 22, 22, 22)

        title = QLabel("使用者登入")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 22pt; font-weight: 800; color: #1b3b6f;")
        root.addWidget(title)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #c5d4f2;")
        root.addWidget(line)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(14)

        self.ed_user = QLineEdit()
        self.ed_pw = QLineEdit()
        self.ed_pw.setEchoMode(QLineEdit.EchoMode.Password)
        edit_style = """
            QLineEdit, QDateEdit {
                font-size: 12pt;
                border: 1px solid #9fb4d9;
                border-radius: 4px;
                padding: 2px 6px;
                background-color: #f7faff;
            }
            QLineEdit:focus, QDateEdit:focus {
                border: 2px solid #2f80ed;
                background-color: #ffffff;
            }
        """
        # 預設輸入英文（Latin）：每次 FocusIn 都重新套用，避免使用者切換 IME 後被覆蓋
        for w in (self.ed_user, self.ed_pw):
            try:
                w.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
            except Exception:
                pass
            try:
                w.setInputMethodHints(Qt.InputMethodHint.ImhLatinOnly)
            except Exception:
                pass
            w.installEventFilter(self)
            w.setStyleSheet(edit_style)
        self.cbo_co = QComboBox()
        self.cbo_co.setMinimumWidth(280)
        self.cbo_co.installEventFilter(self)
        self.cbo_co.activated.connect(lambda _=0: self._focus_date_day())
        self.cbo_co.setStyleSheet(
            """
            QComboBox {
                font-size: 12pt;
                color: #1b3b6f;
                background-color: #dfeaff;
                border: 1px solid #8fb0e4;
                border-radius: 4px;
                padding: 2px 8px;
            }
            QComboBox:focus {
                border: 2px solid #2f80ed;
            }
            QComboBox QAbstractItemView {
                font-size: 11pt;
                color: #1b3b6f;
                background-color: #ecf3ff;
                selection-background-color: #bfd7ff;
                border: 1px solid #8fb0e4;
            }
            """
        )
        self.dt = QDateEdit()
        self.dt.setCalendarPopup(True)
        self.dt.setDate(QDate.currentDate())
        self.dt.setReadOnly(False)
        self.dt.setButtonSymbols(QDateEdit.ButtonSymbols.UpDownArrows)
        self.dt.setDisplayFormat(APP_DATE_QT_FORMAT)
        self.dt.setCurrentSection(QDateTimeEdit.Section.DaySection)
        self.dt.installEventFilter(self)
        self.dt.setStyleSheet(edit_style)

        for lbl, w in [
            ("使用者編號", self.ed_user),
            ("密碼", self.ed_pw),
            ("公司編號", self.cbo_co),
            ("日期", self.dt),
        ]:
            lab = QLabel(lbl)
            lab.setStyleSheet("font-size: 13pt; font-weight: 700;")
            w.setMinimumHeight(38)
            form.addRow(lab, w)

        root.addLayout(form)

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("確定")
        btn_ok.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_DialogOkButton))
        btn_ok.setMinimumHeight(42)
        btn_cancel = QPushButton("離開")
        btn_cancel.setIcon(icon_from_key(self.style(), "cancel"))
        btn_cancel.setMinimumHeight(42)
        btn_ok.clicked.connect(self._try_login)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        root.addLayout(btn_row)

    def eventFilter(self, obj, event) -> bool:
        dt_widget = getattr(self, "dt", None)
        if obj in (
            getattr(self, "ed_user", None),
            getattr(self, "ed_pw", None),
            getattr(self, "cbo_co", None),
            dt_widget,
        ):
            if obj is dt_widget and event.type() == QEvent.Type.FocusIn:
                QTimer.singleShot(0, self._focus_date_day)
                return False
            if obj is dt_widget and event.type() == QEvent.Type.MouseButtonPress:
                QTimer.singleShot(0, self._focus_date_day)
                return False
            if event.type() == QEvent.Type.FocusIn:
                try:
                    self._force_english_ime(obj)
                except Exception:
                    # fallback：至少嘗試 hints
                    try:
                        obj.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
                    except Exception:
                        pass

            if event.type() == QEvent.Type.KeyPress:
                # 登入表單 Enter 導覽：
                # - 使用者編號 Enter -> 密碼欄位
                # - 密碼 Enter -> 公司欄位（下個欄位）
                if event.modifiers() == Qt.KeyboardModifier.NoModifier and event.key() in (
                    Qt.Key.Key_Return,
                    Qt.Key.Key_Enter,
                ):
                    if obj is self.ed_user:
                        self.ed_pw.setFocus()
                        return True
                    if obj is self.ed_pw:
                        self._sync_company_by_credentials()
                        self.cbo_co.setFocus()
                        return True
                    if obj is self.cbo_co:
                        self._focus_date_day()
                        return True
        return super().eventFilter(obj, event)

    def _focus_date_day(self) -> None:
        dt_widget = getattr(self, "dt", None)
        if dt_widget is None:
            return
        dt_widget.setFocus()
        dt_widget.setCurrentSection(QDateTimeEdit.Section.DaySection)

    def _sync_company_by_credentials(self) -> None:
        """依輸入帳密查 USERS.LAST_CO，找到且資料庫存在就帶入公司編號。"""
        last_co, err = detect_last_company_by_credentials(
            self.user_data_path,
            self.ed_user.text(),
            self.ed_pw.text(),
        )
        if err or not last_co:
            return
        idx = self.cbo_co.findText(last_co, Qt.MatchFlag.MatchFixedString)
        if idx >= 0:
            self.cbo_co.setCurrentIndex(idx)

    def _load_companies(self) -> None:
        self.cbo_co.clear()
        keys, err, _missing = load_available_company_keys(
            self.base_dir, self.user_data_path
        )
        if err:
            QMessageBox.warning(self, "公司清單", err)
        for k in keys:
            self.cbo_co.addItem(k)
        if self.cbo_co.count() == 0:
            self.cbo_co.addItem("GS")
        gs_idx = self.cbo_co.findText("GS", Qt.MatchFlag.MatchFixedString)
        if gs_idx >= 0:
            self.cbo_co.setCurrentIndex(gs_idx)
        elif self.cbo_co.count() > 0:
            self.cbo_co.setCurrentIndex(0)

    def _try_login(self) -> None:
        co = self.cbo_co.currentText().strip()
        db_err = validate_company_db(self.base_dir, co)
        if db_err:
            QMessageBox.warning(self, "登入失敗", db_err)
            return
        sess, err = authenticate(
            self.user_data_path,
            self.ed_user.text(),
            self.ed_pw.text(),
            co,
        )
        if err:
            QMessageBox.warning(self, "登入失敗", err)
            return
        if sess:
            upd_err = record_login_success(
                self.user_data_path,
                sess.user_no,
                co,
            )
            if upd_err:
                QMessageBox.warning(self, "登入成功但更新失敗", upd_err)
            sess.login_date = self.dt.date().toString(APP_DATE_QT_FORMAT)
            self._session = sess
            self.accept()
