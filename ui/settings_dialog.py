from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QLineEdit, QCheckBox, QPushButton, QTabWidget, QWidget,
    QFormLayout, QFileDialog
)
import os
from PyQt6.QtCore import Qt, pyqtSignal
from core.i18n import _, i18n
from core.vault import VAULT_DEFAULT_DIR
from core.config import DEFAULT_AI_ENDPOINT
from core import providers as ai_providers
from ui.theme_manager import THEMES

class SettingsDialog(QDialog):
    # Trådarna (modellistan och anslutningsprovet) får aldrig röra widgetar
    # själva: de svarar med en signal och rutan skriver i GUI-tråden. Förut
    # skrev arbetstråden direkt i etiketten, vilket Qt inte tillåter.
    models_ready = pyqtSignal(list)
    models_failed = pyqtSignal(str)
    test_done = pyqtSignal(bool, str)

    def __init__(self, config_mgr, theme_mgr, parent=None):
        super().__init__(parent)
        self.config = config_mgr
        self.theme_mgr = theme_mgr

        self.setWindowTitle(_("settings_title"))
        self.resize(500, 360)
        self.models_ready.connect(self._on_models_ready)
        self.models_failed.connect(self._on_models_failed)
        self.test_done.connect(self._on_test_done)
        self.init_ui()
        self.apply_theme()

    def init_ui(self):
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()

        # Tab 1: General
        tab_gen = QWidget()
        form_gen = QFormLayout(tab_gen)

        self.combo_lang = QComboBox()
        for code, name in i18n.get_available_languages():
            self.combo_lang.addItem(name, code)
        # Select current
        idx = self.combo_lang.findData(i18n.get_language())
        if idx >= 0:
            self.combo_lang.setCurrentIndex(idx)
        form_gen.addRow(_("settings_language"), self.combo_lang)

        self.combo_theme = QComboBox()
        for tid, tinfo in THEMES.items():
            self.combo_theme.addItem(tinfo["name"], tid)
        idx_t = self.combo_theme.findData(self.theme_mgr.current_theme_id)
        if idx_t >= 0:
            self.combo_theme.setCurrentIndex(idx_t)
        form_gen.addRow(_("settings_theme"), self.combo_theme)

        self.chk_autosave = QCheckBox(_("settings_autosave"))
        self.chk_autosave.setChecked(self.config.get("autosave", True))
        form_gen.addRow("", self.chk_autosave)

        self.tabs.addTab(tab_gen, _("settings_tab_general"))

        # Tab 2: AI Provider
        tab_ai = QWidget()
        form_ai = QFormLayout(tab_ai)

        self.combo_provider = QComboBox()
        # Listan bor i core/providers.py — här fanns en kopia som hade blivit
        # inaktuell (OpenAI 2024, Gemini 1.5, Claude 3.5 via OpenRouter).
        self.providers = ai_providers.PROVIDERS
        for post in self.providers:
            self.combo_provider.addItem(post["name"], post["id"])

        curr_url = self.config.get("ai_endpoint", DEFAULT_AI_ENDPOINT)
        curr_model = self.config.get("ai_model", "")
        # Sparad leverantör, annars härledd ur adressen: den som satte upp appen
        # före ai_provider fanns skall se rätt rad förkryssad ändå.
        valt = self.config.get("ai_provider", "") or ai_providers.detect(curr_url)
        idx = self.combo_provider.findData(valt)
        self.combo_provider.setCurrentIndex(idx if idx >= 0 else self.combo_provider.count() - 1)
        self.combo_provider.currentIndexChanged.connect(self._on_provider_preset_changed)
        form_ai.addRow(_("settings_ai_provider"), self.combo_provider)

        self.input_ai_url = QLineEdit(curr_url)
        form_ai.addRow(_("settings_ai_endpoint"), self.input_ai_url)

        self.input_ai_key = QLineEdit(self.config.get("ai_key", ""))
        self.input_ai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_ai_key.setPlaceholderText("sk-... (leave empty if not required, e.g. Ollama)")
        form_ai.addRow(_("settings_ai_key"), self.input_ai_key)

        # Modellen är en rullista man får skriva i: namnen ändras hos
        # leverantörerna, och listan hämtas ur deras egen /models i stället för att
        # appen gissar (en gissad modell blir ett 404 som ser ut som appfel).
        self.input_ai_model = QComboBox()
        self.input_ai_model.setEditable(True)
        self.input_ai_model.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        if curr_model:
            self.input_ai_model.addItem(curr_model)
        self.input_ai_model.setCurrentText(curr_model)
        form_ai.addRow(_("settings_ai_model"), self.input_ai_model)

        model_row = QHBoxLayout()
        self.btn_models = QPushButton(_("settings_ai_fetch_models"))
        self.btn_models.setToolTip(_("settings_ai_fetch_models_tip"))
        self.btn_models.clicked.connect(self._fetch_models)
        self.lbl_model_note = QLabel("")
        self.lbl_model_note.setWordWrap(True)
        self.lbl_model_note.setStyleSheet("font-size: 11px;")
        model_row.addWidget(self.btn_models)
        model_row.addWidget(self.lbl_model_note, 1)
        form_ai.addRow("", model_row)

        # Test connection button & status label
        test_row = QHBoxLayout()
        self.btn_test = QPushButton(_("settings_btn_test_ai"))
        self.btn_test.clicked.connect(self._test_ai_connection)
        self.lbl_test_status = QLabel("")
        self.lbl_test_status.setWordWrap(True)
        test_row.addWidget(self.btn_test)
        test_row.addWidget(self.lbl_test_status)
        test_row.addStretch()
        form_ai.addRow("", test_row)

        self.tabs.addTab(tab_ai, _("settings_tab_ai"))

        # Tab 3: Dictation
        tab_dict = QWidget()
        form_dict = QFormLayout(tab_dict)

        self.combo_dict_lang = QComboBox()
        self.combo_dict_lang.addItem("Auto Detect (SV/EN/...)", "auto")
        self.combo_dict_lang.addItem("Swedish (sv)", "sv")
        self.combo_dict_lang.addItem("English (en)", "en")
        idx_d = self.combo_dict_lang.findData(self.config.get("dictation_lang", "auto"))
        if idx_d >= 0:
            self.combo_dict_lang.setCurrentIndex(idx_d)
        form_dict.addRow(_("dictation_language"), self.combo_dict_lang)

        self.chk_punct = QCheckBox(_("dictation_auto_punctuate"))
        self.chk_punct.setChecked(self.config.get("dictation_auto_punctuate", True))
        form_dict.addRow("", self.chk_punct)

        self.tabs.addTab(tab_dict, _("settings_tab_dictation"))

        # Tab 4: Anteckningsvalv och research
        tab_vault = QWidget()
        form_vault = QFormLayout(tab_vault)

        vault_row = QHBoxLayout()
        self.input_vault_root = QLineEdit(self.config.get("vault_root", VAULT_DEFAULT_DIR))
        vault_row.addWidget(self.input_vault_root, 1)
        self.btn_vault_browse = QPushButton("📂")
        self.btn_vault_browse.setFixedWidth(34)
        self.btn_vault_browse.clicked.connect(self._browse_vault)
        vault_row.addWidget(self.btn_vault_browse)
        form_vault.addRow(_("settings_vault_root"), vault_row)

        self.input_searxng = QLineEdit(self.config.get("research_searxng_url", ""))
        self.input_searxng.setPlaceholderText("http://localhost:8888")
        form_vault.addRow(_("settings_searxng"), self.input_searxng)

        self.lbl_vault_hint = QLabel(_("settings_vault_hint"))
        self.lbl_vault_hint.setWordWrap(True)
        form_vault.addRow("", self.lbl_vault_hint)

        self.tabs.addTab(tab_vault, _("settings_tab_vault"))

        layout.addWidget(self.tabs)

        # Buttons
        btn_row = QHBoxLayout()
        btn_save = QPushButton(_("settings_btn_save"))
        btn_save.clicked.connect(self._save_and_close)
        btn_cancel = QPushButton(_("settings_btn_cancel"))
        btn_cancel.clicked.connect(self.reject)

        btn_row.addStretch()
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def _on_provider_preset_changed(self, idx):
        if not (0 <= idx < len(self.providers)):
            return
        post = self.providers[idx]
        if post["base_url"]:
            self.input_ai_url.setText(post["base_url"])
        # Modellistan hör till den gamla adressen — töm den, men behåll det
        # användaren själv skrev.
        if self.input_ai_model.count() and self.input_ai_model.currentText().startswith("http"):
            self.input_ai_model.clearEditText()
        self.lbl_model_note.setText(post.get("note", ""))

    def _fetch_models(self):
        """Hämtar modellistan ur leverantörens egen /models."""
        url = self.input_ai_url.text().strip()
        key = self.input_ai_key.text().strip()
        if not url:
            self.lbl_model_note.setText(_("settings_ai_test_missing"))
            return
        self.btn_models.setEnabled(False)
        self.lbl_model_note.setText(_("settings_ai_fetching"))

        def worker():
            try:
                self.models_ready.emit(ai_providers.fetch_models(url, key))
            except Exception as e:                      # noqa: BLE001 — felet skall ut
                self.models_failed.emit(str(e)[:160])

        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _on_models_ready(self, modeller):
        self.btn_models.setEnabled(True)
        nu = self.input_ai_model.currentText().strip()
        self.input_ai_model.clear()
        self.input_ai_model.addItems(modeller)
        if nu:
            self.input_ai_model.setCurrentText(nu)
        elif modeller:
            self.input_ai_model.setCurrentText(modeller[0])
        self.lbl_model_note.setText(_("settings_ai_models_found", n=len(modeller)))

    def _on_models_failed(self, fel):
        self.btn_models.setEnabled(True)
        self.lbl_model_note.setText("✕ " + fel)

    def _test_ai_connection(self):
        """Ett riktigt anrop, och ett svar som *är* ett svar.

        Förut räckte HTTP 200: en leverantör som svarade "Claude Sonnet 4.6 is no
        longer available." fick en grön bock, och felet syntes först när
        användaren skrev något i panelen (mätt: det var precis vad som hände).
        """
        url = ai_providers.chat_url(self.input_ai_url.text().strip())
        key = self.input_ai_key.text().strip()
        model = self.input_ai_model.currentText().strip()
        if not url or not model:
            self.lbl_test_status.setText("✕ " + _("settings_ai_test_missing"))
            self.lbl_test_status.setStyleSheet("color: #dc2626; font-size: 11px;")
            return

        self.lbl_test_status.setText("⏳ " + _("settings_ai_testing"))
        self.lbl_test_status.setStyleSheet("color: #3b82f6; font-size: 11px;")
        self.btn_test.setEnabled(False)

        def worker():
            import httpx
            headers = {"Content-Type": "application/json"}
            if key:
                headers["Authorization"] = f"Bearer {key}"
            payload = {"model": model,
                       "messages": [{"role": "user", "content": "Respond with the word OK."}],
                       "max_tokens": 16}
            try:
                with httpx.Client(timeout=15.0) as client:
                    svar = client.post(url, headers=headers, json=payload)
                if svar.status_code != 200:
                    self.test_done.emit(False, f"HTTP {svar.status_code}: {svar.text[:120]}")
                    return
                data = svar.json()
                text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
                if not text.strip():
                    self.test_done.emit(False, _("settings_ai_test_empty"))
                elif ai_providers.is_error_reply(text):
                    self.test_done.emit(False, text.strip()[:160])
                else:
                    self.test_done.emit(True, _("settings_ai_test_success", model=model))
            except Exception as e:                      # noqa: BLE001
                self.test_done.emit(False, _("settings_ai_test_fail", error=str(e)[:80]))

        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _on_test_done(self, ok: bool, text: str):
        self.btn_test.setEnabled(True)
        self.lbl_test_status.setText(("✓ " if ok else "✕ ") + text)
        self.lbl_test_status.setStyleSheet(
            f"color: {'#16a34a' if ok else '#dc2626'}; font-size: 11px;")

    def _browse_vault(self):
        folder = QFileDialog.getExistingDirectory(
            self, _("settings_vault_root"),
            self.input_vault_root.text().strip() or os.path.expanduser("~")
        )
        if folder:
            self.input_vault_root.setText(folder)

    def _save_and_close(self):
        # Apply language
        new_lang = self.combo_lang.currentData()
        if new_lang != i18n.get_language():
            i18n.set_language(new_lang)
            self.config.set("language", new_lang)

        # Apply theme
        new_theme = self.combo_theme.currentData()
        self.theme_mgr.set_theme(new_theme)

        # Apply config
        self.config.set("autosave", self.chk_autosave.isChecked())
        self.config.set("ai_provider", self.combo_provider.currentData() or "custom")
        self.config.set("ai_endpoint", self.input_ai_url.text().strip())
        self.config.set("ai_key", self.input_ai_key.text().strip())
        self.config.set("ai_model", self.input_ai_model.currentText().strip())
        self.config.set("dictation_lang", self.combo_dict_lang.currentData())
        self.config.set("dictation_auto_punctuate", self.chk_punct.isChecked())
        self.config.set("vault_root", self.input_vault_root.text().strip() or VAULT_DEFAULT_DIR)
        self.config.set("research_searxng_url", self.input_searxng.text().strip())
        self.config.save()

        self.accept()

    def apply_theme(self):
        self.setStyleSheet(self.theme_mgr.get_stylesheet())
