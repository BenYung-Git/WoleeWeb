from __future__ import annotations

import os
from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.attachment_service import is_image_path, is_pdf_path
from core.data_dictionary import LanguageCode


def _chn(lang: LanguageCode) -> bool:
    return lang == "CHN"


class AttachmentViewerDialog(QDialog):
    """顯示單一 PDF 或圖形附件。"""

    def __init__(
        self,
        file_path: str,
        lang: LanguageCode = "CHN",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._file_path = file_path
        self.lang = lang
        self.setWindowTitle(
            os.path.basename(file_path)
            if file_path
            else ("附件" if _chn(lang) else "Attachment")
        )
        self.resize(1000, 720)
        self._ready = False
        lay = QVBoxLayout(self)
        self._host = QWidget(self)
        self._host_layout = QVBoxLayout(self._host)
        self._host_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._host)
        lay.addWidget(scroll, 1)
        self._ready = self._build_content()
        if not self._ready:
            QMessageBox.warning(
                self,
                "附件" if _chn(lang) else "Attachment",
                (
                    f"無法顯示檔案：\n{file_path}"
                    if _chn(lang)
                    else f"Cannot display file:\n{file_path}"
                ),
            )
        btn_close = QPushButton("關閉" if _chn(lang) else "Close")
        btn_close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btn_close)
        lay.addLayout(row)

    def _build_content(self) -> bool:
        path = self._file_path
        if not path or not os.path.isfile(path):
            return False
        if is_pdf_path(path):
            return self._build_pdf(path)
        if is_image_path(path):
            return self._build_image(path)
        return False

    def _build_pdf(self, path: str) -> bool:
        try:
            from PyQt6.QtPdf import QPdfDocument  # type: ignore[import-not-found]
            from PyQt6.QtPdfWidgets import QPdfView  # type: ignore[import-not-found]
        except Exception:
            return False
        doc = QPdfDocument(self)
        if doc.load(path) != QPdfDocument.Error.None_:
            return False
        view = QPdfView(self._host)
        view.setDocument(doc)
        view.setPageMode(QPdfView.PageMode.MultiPage)
        view.setZoomMode(QPdfView.ZoomMode.FitInView)
        self._host_layout.addWidget(view)
        return True

    def _build_image(self, path: str) -> bool:
        pix = QPixmap(path)
        if pix.isNull():
            try:
                from PIL import Image
                from PIL.ImageQt import ImageQt

                with Image.open(path) as img:
                    pix = QPixmap.fromImage(ImageQt(img.convert("RGBA")))
            except Exception:
                return False
        if pix.isNull():
            return False
        label = QLabel(self._host)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setPixmap(pix)
        label.setScaledContents(False)
        self._host_layout.addWidget(label)
        return True


class AttachmentPickDialog(QDialog):
    """多個符合附件時供使用者選擇。"""

    def __init__(
        self,
        files: List[str],
        lang: LanguageCode = "CHN",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.lang = lang
        self._files = list(files)
        self.selected_path: Optional[str] = None
        self.setWindowTitle("選擇附件" if _chn(lang) else "Select Attachment")
        self.resize(520, 360)
        lay = QVBoxLayout(self)
        lay.addWidget(
            QLabel(
                "找到多個附件，請選擇要顯示的檔案："
                if _chn(lang)
                else "Multiple attachments found. Please select one:"
            )
        )
        self.list = QListWidget(self)
        for p in self._files:
            self.list.addItem(QListWidgetItem(os.path.basename(p)))
        if self.list.count():
            self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(self._on_open)
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        btn_open = QPushButton("開啟" if _chn(lang) else "Open")
        btn_cancel = QPushButton("取消" if _chn(lang) else "Cancel")
        btn_open.clicked.connect(self._on_open)
        btn_cancel.clicked.connect(self.reject)
        row.addStretch(1)
        row.addWidget(btn_open)
        row.addWidget(btn_cancel)
        lay.addLayout(row)

    def _on_open(self) -> None:
        row = self.list.currentRow()
        if row < 0 or row >= len(self._files):
            return
        self.selected_path = self._files[row]
        self.accept()


def open_attachments(
    files: List[str],
    lang: LanguageCode = "CHN",
    parent=None,
) -> None:
    """0 檔：不呼叫；1 檔：直接顯示；多檔：選擇後顯示。"""
    if not files:
        return
    if len(files) == 1:
        dlg = AttachmentViewerDialog(files[0], lang=lang, parent=parent)
        if getattr(dlg, "_ready", False):
            dlg.exec()
        return
    pick = AttachmentPickDialog(files, lang=lang, parent=parent)
    if pick.exec() != QDialog.DialogCode.Accepted or not pick.selected_path:
        return
    viewer = AttachmentViewerDialog(pick.selected_path, lang=lang, parent=parent)
    if getattr(viewer, "_ready", False):
        viewer.exec()
