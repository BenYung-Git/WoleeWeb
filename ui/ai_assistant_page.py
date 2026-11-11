"""桌面 AI 助理分頁：日常問答、私人文件、系統操作指令。"""
from __future__ import annotations

import html
from typing import Any, Callable, Dict, List, Optional, Sequence

from PyQt6.QtCore import QEvent, Qt, QTimer
from PyQt6.QtGui import QFont, QKeySequence, QShortcut, QTextCursor
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.ui_icon_map import icon_from_key
from ui.work_page import apply_work_action_button_style


class AiAssistantPage(QWidget):
    def __init__(
        self,
        *,
        base_dir: str,
        user_no: str,
        lang: str = "CHN",
        catalog_func: Optional[Callable[[], Sequence[Dict[str, str]]]] = None,
        context_func: Optional[Callable[[], Dict[str, Any]]] = None,
        backend_func: Optional[Callable[[str, str], Any]] = None,
        on_actions: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
        on_save_ai_command: Optional[Callable[[str, str], None]] = None,
        related_search_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._is_ai_page = True
        self.base_dir = base_dir
        self.user_no = user_no
        self.lang = lang
        self.catalog_func = catalog_func
        self.context_func = context_func
        self.backend_func = backend_func
        self.on_actions = on_actions
        self.on_save_ai_command = on_save_ai_command
        self.related_search_fn = related_search_fn
        self._history: List[Dict[str, str]] = []
        self._prompt_history: List[str] = []
        self._hist_idx: int = -1
        self._hist_draft: str = ""
        self._busy = False
        self._build_ui()
        self._refresh_docs()
        self._append_assistant(self._welcome())

    def set_language(self, lang: str) -> None:
        self.lang = lang
        chn = str(lang).upper().startswith("C")
        self._title.setText("AI 助理" if chn else "AI Assistant")
        self._docs_title.setText("私人文件" if chn else "Private files")
        self._hint.setText(
            "可問日常問題、搜尋已上傳文件、分析/統計需求，或下指令操作系統（開啟資料表、關閉 TAB、新增／更改／刪除／複製／離開／列印預覽／查詢／搜尋）；也可輸入編號或關鍵字找所有相關資料。"
            if chn
            else "Ask questions, search uploaded files, analyze needs, or operate this system; you can also search all related database records by keyword."
        )
        self._btn_send.setText("送出" if chn else "Send")
        self._btn_save_cmd.setText("儲存指令" if chn else "Save command")
        self._btn_clear.setText("清除對話" if chn else "Clear chat")
        self._btn_settings.setText("AI 設定" if chn else "AI Settings")
        self._btn_upload.setText("上傳" if chn else "Upload")
        self._btn_delete.setText("刪除文件" if chn else "Delete file")
        self._btn_save_cmd.setToolTip("儲存指令" if chn else "Save command")
        self._btn_open_cmd.setToolTip("查找指令" if chn else "Lookup command")
        self._btn_open_cmd.setText("…")
        self._input.setPlaceholderText(
            "輸入問題或指令，例如：開啟發票、搜尋 1001、找出編號 INV001 的所有相關資料、分析這些需求…"
            if chn
            else "Ask a question or command, e.g. open invoice, search 1001, analyze these needs…"
        )

    def _chn(self) -> bool:
        return str(self.lang or "").upper().startswith("C")

    def _welcome(self) -> str:
        if self._chn():
            return (
                "您好，我是系統 AI 助理。\n"
                "• 解答日常問題\n"
                "• 上傳私人文件，並在文件中找資料\n"
                "• 分析及統計您的需求\n"
                "• 輸入編號或關鍵字，找出資料庫中的所有相關資料\n"
                "• 操作本系統：開啟資料表、關閉 TAB、"
                "新增／更改／刪除／複製／離開／列印（預覽）／查詢／搜尋\n\n"
                "口語範例：\n"
                "• open 顧客-供應商查詢:GSC33SATAL1\n"
                "• 查一下 GSC33SATAL1\n"
                "• 顯示 GSC33SATAL1 的顧客資料"
            )
        return (
            "Hello. I can answer questions, search uploaded files, analyze needs, "
            "search related database records, and operate this system "
            "(open tables, close tabs, add/edit/delete/copy/exit/print preview/query/search).\n\n"
            "Examples: open customer/vendor query:GSC33SATAL1, look up GSC33SATAL1."
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        head = QHBoxLayout()
        self._title = QLabel()
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(10)
        self._title.setFont(title_font)
        head.addWidget(self._title)
        self._btn_clear = QPushButton()
        self._btn_clear.setIcon(icon_from_key(self.style(), "edit-clear"))
        apply_work_action_button_style(self._btn_clear)
        self._btn_clear.clicked.connect(self._on_clear_chat)
        self._btn_settings = QPushButton()
        self._btn_settings.setIcon(icon_from_key(self.style(), "theme"))
        apply_work_action_button_style(self._btn_settings)
        self._btn_settings.clicked.connect(self._on_settings)
        head.addWidget(self._btn_clear)
        head.addWidget(self._btn_settings)
        head.addStretch(1)
        root.addLayout(head)

        self._hint = QLabel()
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet("color:#5a6a7e;font-size:11px;")
        root.addWidget(self._hint)

        split = QSplitter(Qt.Orientation.Horizontal)
        chat_wrap = QWidget()
        chat_lay = QVBoxLayout(chat_wrap)
        chat_lay.setContentsMargins(0, 0, 0, 0)
        self._log = QTextBrowser()
        self._log.setOpenExternalLinks(False)
        chat_font = QFont()
        chat_font.setPointSize(9)
        self._log.setFont(chat_font)
        chat_lay.addWidget(self._log, 1)

        compose = QHBoxLayout()
        self._input = QTextEdit()
        self._input.setFixedHeight(64)
        self._input.setFont(chat_font)
        self._input.installEventFilter(self)
        self._btn_open_cmd = QPushButton("…")
        self._btn_open_cmd.setFixedSize(22, 22)
        self._btn_open_cmd.setStyleSheet(
            "QPushButton { min-width: 22px; max-width: 22px; min-height: 22px; "
            "max-height: 22px; padding: 0; font-size: 11px; }"
        )
        self._btn_open_cmd.clicked.connect(self._on_open_command)
        compose_btns = QVBoxLayout()
        compose_btns.setSpacing(6)
        compose_btns.setContentsMargins(0, 0, 0, 0)
        self._btn_save_cmd = QPushButton()
        self._btn_save_cmd.setIcon(icon_from_key(self.style(), "save"))
        apply_work_action_button_style(self._btn_save_cmd)
        self._btn_save_cmd.clicked.connect(self._on_save_command)
        self._btn_send = QPushButton()
        self._btn_send.setIcon(icon_from_key(self.style(), "other"))
        apply_work_action_button_style(self._btn_send)
        self._btn_send.clicked.connect(self._on_send)
        send_sc = QShortcut(QKeySequence("Ctrl+Return"), self._input)
        send_sc.activated.connect(self._on_send)
        compose_btns.addWidget(self._btn_save_cmd)
        compose_btns.addWidget(self._btn_send)
        compose.addWidget(self._btn_open_cmd, 0, Qt.AlignmentFlag.AlignBottom)
        compose.addWidget(self._input, 1)
        compose.addLayout(compose_btns, 0)
        chat_lay.addLayout(compose)

        docs_wrap = QWidget()
        docs_lay = QVBoxLayout(docs_wrap)
        docs_lay.setContentsMargins(0, 0, 0, 0)
        self._docs_title = QLabel()
        docs_title_font = QFont()
        docs_title_font.setPointSize(10)
        docs_title_font.setBold(True)
        self._docs_title.setFont(docs_title_font)
        docs_lay.addWidget(self._docs_title)
        self._docs = QListWidget()
        self._docs.setFont(chat_font)
        docs_lay.addWidget(self._docs, 1)
        doc_btns = QHBoxLayout()
        self._btn_upload = QPushButton()
        self._btn_upload.setIcon(icon_from_key(self.style(), "add"))
        apply_work_action_button_style(self._btn_upload)
        self._btn_upload.clicked.connect(self._on_upload)
        self._btn_delete = QPushButton()
        self._btn_delete.setIcon(icon_from_key(self.style(), "delete"))
        apply_work_action_button_style(self._btn_delete)
        self._btn_delete.clicked.connect(self._on_delete_doc)
        doc_btns.addWidget(self._btn_upload)
        doc_btns.addWidget(self._btn_delete)
        docs_lay.addLayout(doc_btns)

        split.addWidget(chat_wrap)
        split.addWidget(docs_wrap)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        split.setSizes([720, 240])
        root.addWidget(split, 1)
        self.set_language(self.lang)

    def _append_html(self, who: str, text: str, sources: Optional[List[Dict[str, str]]] = None) -> None:
        body = html.escape(text or "").replace("\n", "<br>")
        extra = ""
        if sources:
            bits = []
            for s in sources:
                bits.append(
                    f"<li><b>{html.escape(s.get('name') or '')}</b> — "
                    f"{html.escape(s.get('snippet') or '')}</li>"
                )
            extra = "<ul>" + "".join(bits) + "</ul>"
        color = "#1b3b6f" if who == "AI" else "#334155"
        bg = "#e8f0ff" if who == "AI" else "#f8fafc"
        self._log.append(
            f'<div style="background:{bg};border:1px solid #c5d4f2;border-radius:8px;'
            f'padding:6px 8px;margin:5px 0;color:{color};font-size:9pt;line-height:1.4;">'
            f"<b>{html.escape(who)}</b><br>{body}{extra}</div>"
        )

    def _append_user(self, text: str) -> None:
        self._append_html("您" if self._chn() else "You", text)

    def _append_assistant(
        self, text: str, sources: Optional[List[Dict[str, str]]] = None
    ) -> None:
        self._append_html("AI", text, sources)

    def _refresh_docs(self) -> None:
        from core.ai_assistant_service import list_user_docs

        self._docs.clear()
        for d in list_user_docs(self.base_dir, self.user_no):
            item = QListWidgetItem(f"{d.get('name')}  ({d.get('uploaded_at') or ''})")
            item.setData(Qt.ItemDataRole.UserRole, d.get("id"))
            self._docs.addItem(item)

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self._input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Down) and not (
                event.modifiers()
                & (
                    Qt.KeyboardModifier.ControlModifier
                    | Qt.KeyboardModifier.AltModifier
                    | Qt.KeyboardModifier.MetaModifier
                )
            ):
                cursor = self._input.textCursor()
                block = cursor.block()
                doc = self._input.document()
                if key == Qt.Key.Key_Up and block == doc.firstBlock():
                    if self._navigate_prompt_history(-1):
                        return True
                elif key == Qt.Key.Key_Down and block == doc.lastBlock():
                    if self._navigate_prompt_history(1):
                        return True
        return super().eventFilter(obj, event)

    def _navigate_prompt_history(self, direction: int) -> bool:
        if not self._prompt_history:
            return False
        if self._hist_idx < 0:
            self._hist_draft = self._input.toPlainText()
            self._hist_idx = len(self._prompt_history)
        nxt = self._hist_idx + direction
        if nxt < 0 or nxt > len(self._prompt_history):
            return False
        self._hist_idx = nxt
        text = (
            self._hist_draft
            if nxt == len(self._prompt_history)
            else self._prompt_history[nxt]
        )
        self._input.setPlainText(text)
        cursor = self._input.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._input.setTextCursor(cursor)
        return True

    def _on_clear_chat(self) -> None:
        if self._busy:
            return
        chn = self._chn()
        if self._history and QMessageBox.question(
            self,
            "AI",
            "確定清除所有對話？" if chn else "Clear all messages?",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._history.clear()
        self._hist_idx = -1
        self._hist_draft = ""
        self._log.clear()
        self._append_assistant(self._welcome())

    def _on_settings(self) -> None:
        from ui.ai_settings_dialog import open_ai_settings_dialog

        open_ai_settings_dialog(
            base_dir=self.base_dir,
            user_no=self.user_no,
            lang=self.lang,
            parent=self,
        )

    def _on_open_command(self) -> None:
        from core.ai_command_service import (
            AI_COMMAND_TABLE,
            FIELD_PROMPT,
            ensure_ai_command_infra,
            resolve_ai_command_data_path,
        )
        from core.auth import resolve_sys_data_path
        from core.data_dictionary import DataDictionary
        from core.db_factory import get_backend_for_path
        from ui.lookup_dialog import LookupPickerDialog

        sys_path = resolve_sys_data_path(self.base_dir)
        ok, err = ensure_ai_command_infra(self.base_dir, sys_path)
        if not ok:
            QMessageBox.warning(self, "AI", err or "無法準備 AI_COMMAND。")
            return
        data_path = resolve_ai_command_data_path(self.base_dir)
        backend = get_backend_for_path(data_path)
        data_dict = DataDictionary(sys_path)
        data_dict.load()
        dlg = LookupPickerDialog(
            lookup_db=AI_COMMAND_TABLE,
            lookup_ret=FIELD_PROMPT,
            backend=backend,
            data_dict=data_dict,
            lang=self.lang,
            parent=self,
            app_base_dir=self.base_dir,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        text = str(dlg.selected_value or "").strip()
        if not text:
            return
        self._input.setPlainText(text)
        cursor = self._input.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._input.setTextCursor(cursor)
        self._input.setFocus()

    def _on_save_command(self) -> None:
        prompt = (self._input.toPlainText() or "").strip()
        reply = ""
        msgs: List[Dict[str, str]] = []
        if not prompt:
            msgs = [
                {
                    "role": str(m.get("role") or ""),
                    "content": str(m.get("content") or ""),
                }
                for m in self._history
                if str(m.get("role") or "") in ("user", "assistant")
            ]
            # 取最後一則使用者指令（及對應回覆）供 callback 使用
            for m in msgs:
                role = str(m.get("role") or "").strip().lower()
                content = str(m.get("content") or "").strip()
                if not content:
                    continue
                if role == "user":
                    prompt = content
                    reply = ""
                elif role == "assistant":
                    reply = content
        if not prompt:
            QMessageBox.information(
                self,
                "AI",
                "請先在輸入框輸入指令，或先送出一則指令。"
                if self._chn()
                else "Enter a command in the input box, or send one first.",
            )
            return
        if callable(self.on_save_ai_command):
            self.on_save_ai_command(prompt, reply)
            return
        from core.ai_command_service import save_ai_command
        from core.auth import resolve_sys_data_path

        rec, err = save_ai_command(
            self.base_dir,
            resolve_sys_data_path(self.base_dir),
            user_no=self.user_no,
            prompt=prompt,
            reply=reply,
            lang=self.lang,
        )
        if err or rec is None:
            QMessageBox.warning(self, "AI", err or "儲存失敗。")
            return
        QMessageBox.information(
            self,
            "AI",
            "已儲存指令至 AI_COMMAND。" if self._chn() else "Command saved to AI_COMMAND.",
        )

    def _on_upload(self) -> None:
        from core.ai_assistant_service import save_user_document

        path, _ = QFileDialog.getOpenFileName(
            self,
            "上傳私人文件" if self._chn() else "Upload private file",
            "",
            "Documents (*.txt *.md *.csv *.json *.pdf *.docx *.xlsx *.xls);;All (*)",
        )
        if not path:
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
        except Exception as e:
            QMessageBox.warning(self, "AI", str(e))
            return
        rec, err = save_user_document(self.base_dir, self.user_no, path, data)
        if err or rec is None:
            QMessageBox.warning(self, "AI", err or "上傳失敗。")
            return
        self._refresh_docs()
        self._append_assistant(
            f"已上傳「{rec.get('name')}」（{rec.get('chunks')} 段）。"
            if self._chn()
            else f"Uploaded {rec.get('name')}."
        )

    def _on_delete_doc(self) -> None:
        from core.ai_assistant_service import delete_user_document

        item = self._docs.currentItem()
        if item is None:
            QMessageBox.information(
                self,
                "AI",
                "請先選取文件。" if self._chn() else "Select a file first.",
            )
            return
        doc_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        ok, err = delete_user_document(self.base_dir, self.user_no, doc_id)
        if not ok:
            QMessageBox.warning(self, "AI", err or "刪除失敗。")
            return
        self._refresh_docs()

    def _on_send(self) -> None:
        if self._busy:
            return
        msg = (self._input.toPlainText() or "").strip()
        if not msg:
            return
        self._input.clear()
        self._prompt_history.append(msg)
        self._hist_idx = -1
        self._hist_draft = ""
        self._append_user(msg)
        self._history.append({"role": "user", "content": msg})
        self._busy = True
        self._btn_send.setEnabled(False)
        QTimer.singleShot(10, lambda: self._run_chat(msg))

    def _run_chat(self, msg: str) -> None:
        from core.ai_assistant_service import catalog_from_programs, chat

        try:
            catalog = []
            if callable(self.catalog_func):
                catalog = list(self.catalog_func() or [])
            if not catalog:
                catalog = catalog_from_programs([], self.lang)
            ctx = self.context_func() if callable(self.context_func) else {}
            do_proc = str((ctx or {}).get("do_proc") or "")
            table_name = str((ctx or {}).get("table_name") or "")
            backend = None
            if callable(self.backend_func):
                backend = self.backend_func(do_proc, table_name)
            data = chat(
                base_dir=self.base_dir,
                user_no=self.user_no,
                message=msg,
                catalog=catalog,
                history=self._history[:-1],
                active_do_proc=do_proc,
                lang=self.lang,
                backend=backend,
                table_name=table_name,
                related_search_fn=self.related_search_fn
                if callable(self.related_search_fn)
                else None,
            )
            reply = str(data.get("reply") or "")
            sources = data.get("sources") if isinstance(data.get("sources"), list) else []
            actions = data.get("actions") if isinstance(data.get("actions"), list) else []
            self._append_assistant(reply, sources)
            self._history.append({"role": "assistant", "content": reply})
            pending = [a for a in actions if isinstance(a, dict)]
            if pending and callable(self.on_actions):
                self.on_actions(pending)
        except Exception as e:
            self._append_assistant(str(e))
        finally:
            self._busy = False
            self._btn_send.setEnabled(True)
            self._input.setFocus()
