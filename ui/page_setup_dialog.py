"""
ui/page_setup_dialog.py — Dialog för sidinställningar, sidnummer och sidhuvud/sidfot.

Konfigurerar:
- Pappersstorlek (A4, Letter) och orientering (Stående, Liggande)
- Marginaler (Överkant, Nederkant, Vänster, Höger)
- Sidnumrering (Placering: Nedtill centrerat, Nedtill höger, Växlande vänster/höger, Ovantill mm.)
- Format: "Sida X av Y", "1, 2, 3...", "— X —"
- Undanta titelsida / första sida
- Löpande sidhuvud- och sidfotstext
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QCheckBox, QGroupBox, QDoubleSpinBox, QLineEdit, QPushButton,
    QTabWidget, QWidget, QRadioButton, QButtonGroup
)
from PyQt6.QtCore import Qt, pyqtSignal
from core.i18n import _
from core import page_format
from core.doc_manager import DEFAULT_PAGE_SETTINGS


class PageSetupDialog(QDialog):
    settings_applied = pyqtSignal(dict)

    def __init__(self, current_settings: dict, theme_mgr, parent=None):
        super().__init__(parent)
        self.theme_mgr = theme_mgr
        self.settings = DEFAULT_PAGE_SETTINGS.copy()
        if current_settings:
            self.settings.update(current_settings)

        self.setWindowTitle(_("pagesetup_dialog_title"))
        self.setFixedWidth(460)
        self.setModal(True)

        self.init_ui()
        self.apply_theme()
        self._load_from_settings()

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(14)

        # Header
        lbl_header = QLabel("📄 " + _("pagesetup_dialog_title"))
        lbl_header.setStyleSheet("font-size: 16px; font-weight: bold;")
        root_layout.addWidget(lbl_header)

        # Tabs: 1. Sida & Marginaler, 2. Sidnummer & Sidhuvud/Sidfot
        tabs = QTabWidget()

        # =====================================================================
        # FLIK 1: SIDA & MARGINALER
        # =====================================================================
        tab_page = QWidget()
        layout_page = QVBoxLayout(tab_page)
        layout_page.setSpacing(12)

        # Pappersformat & Orientering
        grp_paper = QGroupBox(_("pagesetup_grp_paper"))
        paper_layout = QVBoxLayout(grp_paper)

        row_size = QHBoxLayout()
        lbl_size = QLabel(_("pagesetup_size") + ":")
        self.combo_page_size = QComboBox()
        # Writer listar namngivna papper och låter "Anpassad" ta egna mått; måtten
        # är de stående, orienteringen läggs på som en flagga (core/page_format).
        for _namn in page_format.ORDER:
            _w, _h = page_format.PAPER_MM[_namn]
            self.combo_page_size.addItem(f"{_namn} ({_w:g} × {_h:g} mm)", _namn)
        self.combo_page_size.addItem(_("pagesetup_margin_custom"), page_format.CUSTOM)
        self.combo_page_size.currentIndexChanged.connect(self._on_size_changed)
        row_size.addWidget(lbl_size)
        row_size.addWidget(self.combo_page_size)
        paper_layout.addLayout(row_size)

        # Egna mått. "×" och enheten är språkoberoende, så raden behöver inga
        # egna i18n-nycklar.
        row_custom = QHBoxLayout()
        self.spin_page_w = QDoubleSpinBox()
        self.spin_page_w.setRange(50.0, 600.0)
        self.spin_page_w.setDecimals(1)
        self.spin_page_w.setSuffix(" mm")
        self.spin_page_h = QDoubleSpinBox()
        self.spin_page_h.setRange(50.0, 600.0)
        self.spin_page_h.setDecimals(1)
        self.spin_page_h.setSuffix(" mm")
        row_custom.addWidget(self.spin_page_w)
        row_custom.addWidget(QLabel("×"))
        row_custom.addWidget(self.spin_page_h)
        paper_layout.addLayout(row_custom)

        row_orient = QHBoxLayout()
        lbl_orient = QLabel(_("pagesetup_orientation") + ":")
        self.combo_orient = QComboBox()
        self.combo_orient.addItem("📄 " + _("pagesetup_portrait"), "portrait")
        self.combo_orient.addItem("📑 " + _("pagesetup_landscape"), "landscape")
        row_orient.addWidget(lbl_orient)
        row_orient.addWidget(self.combo_orient)
        paper_layout.addLayout(row_orient)

        layout_page.addWidget(grp_paper)

        # Marginaler
        grp_margins = QGroupBox(_("pagesetup_grp_margins"))
        margin_layout = QVBoxLayout(grp_margins)
        margin_layout.setSpacing(8)

        # Förinställningar
        row_preset = QHBoxLayout()
        lbl_pre = QLabel(_("pagesetup_preset") + ":")
        self.combo_margin_preset = QComboBox()
        self.combo_margin_preset.addItem(_("pagesetup_margin_normal") + " (20 mm)", "normal")
        self.combo_margin_preset.addItem(_("pagesetup_margin_narrow") + " (12 mm)", "narrow")
        self.combo_margin_preset.addItem(_("pagesetup_margin_wide") + " (25 mm)", "wide")
        self.combo_margin_preset.addItem(_("pagesetup_margin_custom"), "custom")
        self.combo_margin_preset.currentIndexChanged.connect(self._on_margin_preset_changed)
        row_preset.addWidget(lbl_pre)
        row_preset.addWidget(self.combo_margin_preset)
        margin_layout.addLayout(row_preset)

        # Exakta mått
        row_m1 = QHBoxLayout()
        lbl_top = QLabel(_("pagesetup_top") + ":")
        self.spin_top = QDoubleSpinBox()
        self.spin_top.setRange(5.0, 60.0)
        self.spin_top.setSuffix(" mm")
        self.spin_top.setValue(20.0)

        lbl_bottom = QLabel(_("pagesetup_bottom") + ":")
        self.spin_bottom = QDoubleSpinBox()
        self.spin_bottom.setRange(5.0, 60.0)
        self.spin_bottom.setSuffix(" mm")
        self.spin_bottom.setValue(20.0)

        row_m1.addWidget(lbl_top)
        row_m1.addWidget(self.spin_top)
        row_m1.addWidget(lbl_bottom)
        row_m1.addWidget(self.spin_bottom)
        margin_layout.addLayout(row_m1)

        row_m2 = QHBoxLayout()
        lbl_left = QLabel(_("pagesetup_left") + ":")
        self.spin_left = QDoubleSpinBox()
        self.spin_left.setRange(5.0, 60.0)
        self.spin_left.setSuffix(" mm")
        self.spin_left.setValue(20.0)

        lbl_right = QLabel(_("pagesetup_right") + ":")
        self.spin_right = QDoubleSpinBox()
        self.spin_right.setRange(5.0, 60.0)
        self.spin_right.setSuffix(" mm")
        self.spin_right.setValue(20.0)

        row_m2.addWidget(lbl_left)
        row_m2.addWidget(self.spin_left)
        row_m2.addWidget(lbl_right)
        row_m2.addWidget(self.spin_right)
        margin_layout.addLayout(row_m2)

        layout_page.addWidget(grp_margins)
        layout_page.addStretch()
        tabs.addTab(tab_page, "📄 " + _("pagesetup_tab_page"))

        # =====================================================================
        # FLIK 2: SIDNUMMER & SIDHUVUD / SIDFOT
        # =====================================================================
        tab_headers = QWidget()
        layout_headers = QVBoxLayout(tab_headers)
        layout_headers.setSpacing(12)

        # Sidnumrering
        grp_numbers = QGroupBox(_("pagesetup_grp_numbers"))
        num_layout = QVBoxLayout(grp_numbers)
        num_layout.setSpacing(8)

        self.chk_enable_numbers = QCheckBox(_("pagesetup_enable_numbers"))
        self.chk_enable_numbers.setChecked(True)
        self.chk_enable_numbers.toggled.connect(self._on_numbers_toggled)
        num_layout.addWidget(self.chk_enable_numbers)

        # Placering
        row_pos = QHBoxLayout()
        lbl_pos = QLabel(_("pagesetup_position") + ":")
        self.combo_num_pos = QComboBox()
        self.combo_num_pos.addItem("⬇️ " + _("pagesetup_pos_bottom_center"), "bottom-center")
        self.combo_num_pos.addItem("↘️ " + _("pagesetup_pos_bottom_right"), "bottom-right")
        self.combo_num_pos.addItem("📖 " + _("pagesetup_pos_bottom_alternating"), "bottom-alternating")
        self.combo_num_pos.addItem("↗️ " + _("pagesetup_pos_top_right"), "top-right")
        self.combo_num_pos.addItem("📖 " + _("pagesetup_pos_top_alternating"), "top-alternating")
        row_pos.addWidget(lbl_pos)
        row_pos.addWidget(self.combo_num_pos)
        num_layout.addLayout(row_pos)

        # Format
        row_fmt = QHBoxLayout()
        lbl_fmt = QLabel(_("pagesetup_format") + ":")
        self.combo_num_fmt = QComboBox()
        self.combo_num_fmt.addItem("Sida 1 av 5", "page_of_total")
        self.combo_num_fmt.addItem("1, 2, 3...", "number")
        self.combo_num_fmt.addItem("— 1 —", "hyphen")
        self.combo_num_fmt.addItem("1 / 5", "slash")
        row_fmt.addWidget(lbl_fmt)
        row_fmt.addWidget(self.combo_num_fmt)
        num_layout.addLayout(row_fmt)

        self.chk_skip_first = QCheckBox(_("pagesetup_skip_first_page"))
        self.chk_skip_first.setChecked(False)
        num_layout.addWidget(self.chk_skip_first)

        layout_headers.addWidget(grp_numbers)

        # Sidhuvud & Sidfotstext
        grp_text = QGroupBox(_("pagesetup_grp_text"))
        text_layout = QVBoxLayout(grp_text)
        text_layout.setSpacing(8)

        row_head_txt = QHBoxLayout()
        lbl_head_txt = QLabel(_("pagesetup_header_text") + ":")
        self.input_header_text = QLineEdit()
        self.input_header_text.setPlaceholderText(_("pagesetup_header_placeholder"))
        row_head_txt.addWidget(lbl_head_txt)
        row_head_txt.addWidget(self.input_header_text)
        text_layout.addLayout(row_head_txt)

        row_foot_txt = QHBoxLayout()
        lbl_foot_txt = QLabel(_("pagesetup_footer_text") + ":")
        self.input_footer_text = QLineEdit()
        self.input_footer_text.setPlaceholderText(_("pagesetup_footer_placeholder"))
        row_foot_txt.addWidget(lbl_foot_txt)
        row_foot_txt.addWidget(self.input_footer_text)
        text_layout.addLayout(row_foot_txt)

        layout_headers.addWidget(grp_text)

        # Ren utskrift — papper, inte tema
        grp_clean = QGroupBox(_("pagesetup_grp_clean"))
        clean_layout = QVBoxLayout(grp_clean)
        clean_layout.setSpacing(6)

        self.chk_clean_print = QCheckBox(_("pagesetup_clean_print"))
        self.chk_clean_print.setChecked(True)
        self.chk_clean_print.setToolTip(_("pagesetup_clean_print_hint"))
        clean_layout.addWidget(self.chk_clean_print)

        lbl_clean_hint = QLabel(_("pagesetup_clean_print_hint"))
        lbl_clean_hint.setWordWrap(True)
        lbl_clean_hint.setObjectName("PageSetupHint")
        clean_layout.addWidget(lbl_clean_hint)

        self.chk_grayscale_images = QCheckBox(_("pagesetup_grayscale_images"))
        self.chk_grayscale_images.setChecked(False)
        self.chk_grayscale_images.setToolTip(_("pagesetup_grayscale_images_hint"))
        clean_layout.addWidget(self.chk_grayscale_images)

        layout_headers.addWidget(grp_clean)
        layout_headers.addStretch()
        tabs.addTab(tab_headers, "🔢 " + _("pagesetup_tab_numbers"))

        root_layout.addWidget(tabs)

        # Dialog-knappar
        btn_bar = QHBoxLayout()
        self.btn_cancel = QPushButton(_("dlg_cancel"))
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_ok = QPushButton("✓ " + _("dlg_ok"))
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self._on_apply)

        btn_bar.addStretch()
        btn_bar.addWidget(self.btn_cancel)
        btn_bar.addWidget(self.btn_ok)
        root_layout.addLayout(btn_bar)

    def _load_from_settings(self):
        # Pappersformat: namnet om inställningarna betyder ett namngivet papper,
        # annars "Anpassad" med talen i fälten (ett tryckmått som 6x9 heter
        # ingenting i listan och skall inte låtsas göra det).
        idx = self.combo_page_size.findData(page_format.preset_name(self.settings))
        if idx >= 0:
            self.combo_page_size.setCurrentIndex(idx)
        w_mm, h_mm = page_format.page_mm({**self.settings, "orientation": "portrait"})
        self.spin_page_w.setValue(w_mm)
        self.spin_page_h.setValue(h_mm)
        self._on_size_changed()

        idx_o = self.combo_orient.findData(self.settings.get("orientation", "portrait"))
        if idx_o >= 0:
            self.combo_orient.setCurrentIndex(idx_o)

        self.spin_top.setValue(float(self.settings.get("margin_top_mm", 20.0)))
        self.spin_bottom.setValue(float(self.settings.get("margin_bottom_mm", 20.0)))
        self.spin_left.setValue(float(self.settings.get("margin_left_mm", 20.0)))
        self.spin_right.setValue(float(self.settings.get("margin_right_mm", 20.0)))

        self.chk_enable_numbers.setChecked(bool(self.settings.get("page_numbering", True)))

        idx_pos = self.combo_num_pos.findData(self.settings.get("page_number_pos", "bottom-center"))
        if idx_pos >= 0:
            self.combo_num_pos.setCurrentIndex(idx_pos)

        idx_fmt = self.combo_num_fmt.findData(self.settings.get("page_number_format", "page_of_total"))
        if idx_fmt >= 0:
            self.combo_num_fmt.setCurrentIndex(idx_fmt)

        self.chk_skip_first.setChecked(bool(self.settings.get("skip_first_page", False)))
        self.input_header_text.setText(str(self.settings.get("header_text", "")))
        self.input_footer_text.setText(str(self.settings.get("footer_text", "")))
        self.chk_clean_print.setChecked(bool(self.settings.get("clean_print", True)))
        self.chk_grayscale_images.setChecked(bool(self.settings.get("grayscale_images", False)))

        self._on_numbers_toggled(self.chk_enable_numbers.isChecked())

    def _on_size_changed(self, *_args) -> None:
        """Egna mått går bara att skriva när "Anpassad" är valt.

        Ett namnval fyller fälten med papprets stående mått, så att siffrorna
        alltid visar den storlek som gäller (och orienteringen syns i sin egen
        ruta, som i Writer).
        """
        eget = self.combo_page_size.currentData() == page_format.CUSTOM
        self.spin_page_w.setEnabled(eget)
        self.spin_page_h.setEnabled(eget)
        if not eget:
            namn = self.combo_page_size.currentData()
            w_mm, h_mm = page_format.PAPER_MM.get(namn, page_format.PAPER_MM[page_format.DEFAULT])
            self.spin_page_w.setValue(w_mm)
            self.spin_page_h.setValue(h_mm)

    def _on_margin_preset_changed(self):
        val = self.combo_margin_preset.currentData()
        if val == "normal":
            self.spin_top.setValue(20.0)
            self.spin_bottom.setValue(20.0)
            self.spin_left.setValue(20.0)
            self.spin_right.setValue(20.0)
        elif val == "narrow":
            self.spin_top.setValue(12.0)
            self.spin_bottom.setValue(12.0)
            self.spin_left.setValue(12.0)
            self.spin_right.setValue(12.0)
        elif val == "wide":
            self.spin_top.setValue(25.0)
            self.spin_bottom.setValue(25.0)
            self.spin_left.setValue(25.0)
            self.spin_right.setValue(25.0)

    def _on_numbers_toggled(self, enabled):
        self.combo_num_pos.setEnabled(enabled)
        self.combo_num_fmt.setEnabled(enabled)
        self.chk_skip_first.setEnabled(enabled)

    def _on_apply(self):
        new_cfg = {
            "page_size": self.combo_page_size.currentData() or page_format.DEFAULT,
            "orientation": self.combo_orient.currentData() or "portrait",
            "margin_top_mm": self.spin_top.value(),
            "margin_bottom_mm": self.spin_bottom.value(),
            "margin_left_mm": self.spin_left.value(),
            "margin_right_mm": self.spin_right.value(),
            "page_numbering": self.chk_enable_numbers.isChecked(),
            "page_number_pos": self.combo_num_pos.currentData() or "bottom-center",
            "page_number_format": self.combo_num_fmt.currentData() or "page_of_total",
            "skip_first_page": self.chk_skip_first.isChecked(),
            "header_text": self.input_header_text.text().strip(),
            "footer_text": self.input_footer_text.text().strip(),
            "clean_print": self.chk_clean_print.isChecked(),
            "grayscale_images": self.chk_grayscale_images.isChecked(),
        }
        if new_cfg["page_size"] == page_format.CUSTOM:
            # De egna måtten sparas som tal, precis som Writer sparar pappret i
            # sidstilen: namnet "Anpassad" säger ingenting om storleken.
            new_cfg["custom_width_mm"] = round(self.spin_page_w.value(), 1)
            new_cfg["custom_height_mm"] = round(self.spin_page_h.value(), 1)
        self.settings.update(new_cfg)
        self.settings_applied.emit(self.settings)
        self.accept()

    def get_settings(self) -> dict:
        return self.settings

    def apply_theme(self):
        c = self.theme_mgr.current
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {c["window_bg"]};
                color: {c["text_color"]};
            }}
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {c["canvas_border"]};
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 14px;
                background-color: {c["toolbar_bg"]};
                color: {c["text_color"]};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 2px 8px;
                color: {c["accent"]};
            }}
            QTabWidget::pane {{
                border: 1px solid {c["canvas_border"]};
                background-color: {c["toolbar_bg"]};
                border-radius: 4px;
            }}
            QTabBar::tab {{
                background-color: {c["window_bg"]};
                color: {c["text_color"]};
                padding: 6px 14px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background-color: {c["toolbar_bg"]};
                border: 1px solid {c["canvas_border"]};
                border-bottom: none;
                font-weight: bold;
                color: {c["accent"]};
            }}
            QLineEdit, QComboBox, QDoubleSpinBox {{
                background-color: {c["canvas_bg"]};
                border: 1px solid {c["canvas_border"]};
                border-radius: 4px;
                padding: 5px 8px;
                color: {c["text_color"]};
            }}
            QPushButton {{
                background-color: {c["sidebar_card"]};
                border: 1px solid {c["canvas_border"]};
                border-radius: 4px;
                padding: 5px 14px;
                color: {c["text_color"]};
            }}
            QPushButton:hover {{
                background-color: {c["btn_hover"]};
                border-color: {c["accent"]};
            }}
        """)
