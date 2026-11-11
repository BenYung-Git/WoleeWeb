"""AI 設定對話框（桌面）。"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from core.ai_settings import (
    list_model_options,
    preset_model_ids,
    save_ai_settings,
    settings_for_client,
)

_CUSTOM_MODEL_ID = "__custom__"


class AiSettingsDialog(QDialog):
    def __init__(
        self,
        *,
        base_dir: str,
        user_no: str,
        lang: str = "CHN",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.base_dir = base_dir
        self.user_no = user_no
        self.lang = lang
        chn = str(lang).upper().startswith("C")
        self.setWindowTitle("AI 設定" if chn else "AI Settings")
        self.setMinimumWidth(460)
        font = self.font()
        font.setPointSize(9)
        self.setFont(font)
        self._info = settings_for_client(base_dir, user_no, lang=lang)
        self._build_ui(chn)
        self._load_values()

    def _build_ui(self, chn: bool) -> None:
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self._cmb_model = QComboBox()
        self._cmb_model.setEditable(False)
        for opt in self._info.get("models") or list_model_options(self.lang):
            self._cmb_model.addItem(str(opt.get("label") or opt.get("id")), str(opt.get("id")))
        self._cmb_model.addItem("自訂…" if chn else "Custom…", _CUSTOM_MODEL_ID)
        self._cmb_model.currentIndexChanged.connect(self._sync_model_custom_visible)
        self._ed_model_custom = QLineEdit()
        self._ed_model_custom.setPlaceholderText(
            "輸入模型名稱，例如 gpt-4o-mini" if chn else "Enter model id, e.g. gpt-4o-mini"
        )
        self._ed_base = QLineEdit()
        self._ed_key = QLineEdit()
        self._ed_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._ed_key.setPlaceholderText(
            "留空表示不變更已儲存的 Key" if chn else "Leave blank to keep saved key"
        )
        self._lbl_key_hint = QLabel()
        self._lbl_key_hint.setStyleSheet("color:#5a6a7e;font-size:11px;")
        self._chk_clear = QCheckBox("清除已儲存的 API Key" if chn else "Clear saved API key")
        form.addRow("模型" if chn else "Model", self._cmb_model)
        form.addRow("自訂模型" if chn else "Custom model", self._ed_model_custom)
        form.addRow("API 端點" if chn else "API base URL", self._ed_base)
        form.addRow("API Key" if chn else "API Key", self._ed_key)
        form.addRow("", self._lbl_key_hint)
        form.addRow("", self._chk_clear)
        lay.addLayout(form)
        src = self._info.get("config_source") or "none"
        share_note = QLabel(
            "此設定全系統共用，儲存後所有使用者皆可使用。"
            if chn
            else "These settings are system-wide and available to all users after saving."
        )
        share_note.setStyleSheet("color:#1b3b6f;font-weight:600;")
        share_note.setWordWrap(True)
        lay.addWidget(share_note)
        if src == "env":
            lay.addWidget(
                QLabel(
                    "目前使用伺服器環境變數的 API Key。"
                    if chn
                    else "Currently using server environment API key."
                )
            )
        elif self._info.get("llm_enabled"):
            lay.addWidget(QLabel("LLM 已啟用。" if chn else "LLM is enabled."))
        else:
            lay.addWidget(
                QLabel(
                    "尚未設定 API Key；一般問答能力有限。"
                    if chn
                    else "No API key; general Q&A is limited."
                )
            )
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _sync_model_custom_visible(self) -> None:
        custom = self._cmb_model.currentData() == _CUSTOM_MODEL_ID
        self._ed_model_custom.setVisible(custom)
        self._ed_model_custom.setEnabled(custom)

    def _load_values(self) -> None:
        saved = str(self._info.get("model") or "")
        presets = preset_model_ids()
        idx = self._cmb_model.findData(saved)
        if idx >= 0 and saved in presets:
            self._cmb_model.setCurrentIndex(idx)
        elif saved:
            custom_idx = self._cmb_model.findData(_CUSTOM_MODEL_ID)
            if custom_idx >= 0:
                self._cmb_model.setCurrentIndex(custom_idx)
            self._ed_model_custom.setText(saved)
        self._ed_base.setText(str(self._info.get("base_url") or ""))
        hint = str(self._info.get("api_key_hint") or "")
        if self._info.get("user_api_key_set"):
            self._lbl_key_hint.setText(
                f"已儲存 Key：{hint}"
                if str(self.lang).upper().startswith("C")
                else f"Saved key: {hint}"
            )
        elif self._info.get("has_api_key"):
            self._lbl_key_hint.setText(
                "使用環境變數 Key"
                if str(self.lang).upper().startswith("C")
                else "Using environment key"
            )
        self._sync_model_custom_visible()

    def _selected_model(self) -> str:
        if self._cmb_model.currentData() == _CUSTOM_MODEL_ID:
            return self._ed_model_custom.text().strip()
        data = self._cmb_model.currentData()
        return str(data or "").strip()

    def _on_save(self) -> None:
        chn = str(self.lang).upper().startswith("C")
        model = self._selected_model()
        if not model:
            QMessageBox.warning(
                self,
                self.windowTitle(),
                "請選擇或輸入模型。" if chn else "Please select or enter a model.",
            )
            return
        try:
            save_ai_settings(
                self.base_dir,
                self.user_no,
                api_key=self._ed_key.text(),
                model=model,
                base_url=self._ed_base.text(),
                clear_api_key=self._chk_clear.isChecked(),
            )
        except Exception as e:
            QMessageBox.warning(self, self.windowTitle(), str(e))
            return
        QMessageBox.information(
            self,
            self.windowTitle(),
            "設定已儲存（全系統共用）。"
            if chn
            else "Settings saved (system-wide)."
        )
        self.accept()


def open_ai_settings_dialog(
    *,
    base_dir: str,
    user_no: str,
    lang: str = "CHN",
    parent=None,
) -> None:
    dlg = AiSettingsDialog(base_dir=base_dir, user_no=user_no, lang=lang, parent=parent)
    dlg.exec()
