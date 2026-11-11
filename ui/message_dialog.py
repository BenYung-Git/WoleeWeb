from __future__ import annotations

from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


def show_copyable_message(parent, title: str, message: str, *, copy_label: str = "複製") -> None:
    """顯示可選取、可複製的文字訊息（供診斷）。"""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    layout = QVBoxLayout(dlg)
    hint = QLabel("以下內容可選取或以「複製」按鈕複製。")
    hint.setWordWrap(True)
    layout.addWidget(hint)
    text = QTextEdit()
    text.setPlainText(message)
    text.setReadOnly(True)
    text.setMinimumSize(480, 120)
    layout.addWidget(text)
    row = QHBoxLayout()
    btn_copy = QPushButton(copy_label)
    btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(message))
    row.addWidget(btn_copy)
    row.addStretch(1)
    layout.addLayout(row)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
    buttons.accepted.connect(dlg.accept)
    layout.addWidget(buttons)
    dlg.exec()
