"""Dialog for configuring the AI vision provider, model, key and prompt."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from .config import Config
from .vision import PROVIDERS, preset
from .vision import keys as vision_keys


class AISettingsDialog(QDialog):
    """Edits vision settings in ``config`` and stores the API key in the keychain."""

    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("AI identification settings")
        self.resize(520, 460)

        self.provider_combo = QComboBox()
        for key, spec in PROVIDERS.items():
            self.provider_combo.addItem(spec["label"], key)
        self._select_provider(self.config["vision_provider"])

        self.model_edit = QLineEdit(self.config["vision_model"])
        self.base_url_edit = QLineEdit(self.config["vision_base_url"])
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_status = QLabel()
        self.key_status.setStyleSheet("color:#888;")
        self.prompt_edit = QPlainTextEdit(self.config["vision_prompt"])
        self.prompt_edit.setMinimumHeight(120)

        form = QFormLayout()
        form.addRow("Provider:", self.provider_combo)
        form.addRow("Model:", self.model_edit)
        form.addRow("Base URL:", self.base_url_edit)
        form.addRow("API key:", self.key_edit)
        form.addRow("", self.key_status)
        form.addRow(QLabel("Prompt:"))

        hint = QLabel(
            "Leave Model / Base URL blank to use the provider's defaults. The API "
            "key is stored in your system keychain, never in the settings file."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#888; font-size:11px;")

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.prompt_edit)
        layout.addWidget(hint)
        layout.addWidget(buttons)

        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        self._refresh_placeholders()
        self._refresh_key_status()

    # ----- helpers ------------------------------------------------------

    def _current_provider(self) -> str:
        return self.provider_combo.currentData()

    def _select_provider(self, key: str) -> None:
        idx = self.provider_combo.findData(key)
        self.provider_combo.setCurrentIndex(max(0, idx))

    def _refresh_placeholders(self) -> None:
        spec = preset(self._current_provider())
        self.model_edit.setPlaceholderText(spec["model"] or "model id")
        self.base_url_edit.setPlaceholderText(
            spec["base_url"] or "(default Anthropic endpoint)"
        )

    def _refresh_key_status(self) -> None:
        provider = self._current_provider()
        if vision_keys.has_api_key(provider):
            self.key_status.setText("A key is saved for this provider.")
            self.key_edit.setPlaceholderText("•••••• (leave blank to keep)")
        else:
            self.key_status.setText("No key saved for this provider yet.")
            self.key_edit.setPlaceholderText("paste API key")

    def _on_provider_changed(self) -> None:
        # Switching provider: clear per-provider fields so presets show through.
        self.model_edit.clear()
        self.base_url_edit.clear()
        self.key_edit.clear()
        self._refresh_placeholders()
        self._refresh_key_status()

    def _save(self) -> None:
        provider = self._current_provider()
        self.config["vision_provider"] = provider
        self.config["vision_model"] = self.model_edit.text().strip()
        self.config["vision_base_url"] = self.base_url_edit.text().strip()
        self.config["vision_prompt"] = self.prompt_edit.toPlainText().strip()
        self.config.save()

        key = self.key_edit.text().strip()
        if key:
            vision_keys.set_api_key(provider, key)
        self.accept()
