import os
from datetime import datetime
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QFileDialog,
    QMessageBox, QLabel, QSplitter, QStatusBar, QApplication, QMenuBar,
    QStackedWidget, QMenu, QDialog, QPushButton, QInputDialog, QTextEdit
)
from PyQt6 import QtCore
from PyQt6.QtCore import Qt, QTimer, QPoint, QMarginsF, QEvent
from PyQt6.QtGui import (QAction, QKeySequence, QPalette, QTextCursor, QTextDocument,
                         QPageLayout, QPageSize, QCursor)
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog, QPrintPreviewDialog

from core.i18n import _, i18n
from core.languages import ai_name, native, next_language
from core.doc_manager import DocumentManager
from core.vault import Vault, VAULT_DEFAULT_DIR
from ui.editor_view import EditorView
from ui.toolbar import FormattingToolBar
from ui.sidebar_inspector import SidebarInspector
from ui.inline_ai_popup import InlineAIPopup
from ui.settings_dialog import SettingsDialog
from ui.google_fonts_dialog import GoogleFontsDialog
from ui.start_screen import StartScreen
from ui.notes_panel import NotesPanel
from ui.insight_panel import InsightPanel
from ui.research_dialog import ResearchDialog
from ui.ask_panel import AskPanel
from ui.ghostwriter_dialog import GhostwriterDialog
from ui.graph_dialog import GraphDialog
from ui.code_dialog import CodeDialog
from ui.template_dialog import TemplateDialog
from ui.project_dialog import NewProjectDialog
from ui.binder_panel import BinderPanel
from ui.chrome import LeftRail, TopBar
from ui.scene_inspector import SceneInspector
from ui.writing_log_panel import WritingLogPanel
from ui.codex_panel import CodexPanel
from ui.plot_grid import PlotGrid
from ui.exercise_dialog import ExerciseDialog
from ui.overview_dialog import OverviewDialog
from ui.snapshot_dialog import HistoryDialog
from ui.review_dialog import ReviewDialog
from core.font_manager import install_dropdown_style
from core import revisions
from ui.scrivenings import ScriveningsView
from core.project import Project
from ui.chart_dialog import ChartDialog
from ui.image_dialog import ImageDialog
from ui.page_setup_dialog import PageSetupDialog
from core.templates import get_template_html
from core.doc_manager import DEFAULT_PAGE_SETTINGS
from core import richtext, directives

# Ett ord: bokstäver (även svenska), siffror och apostrof — samma avgränsning
# som core/autocorrect.py använder för hela ord.
_WORD_PATTERN = r"[\w\u00c0-\u024f']+"


# Innehållsförteckningens markeringar — samma form som appens andra direktiv.
_TOC_OPEN = "[innehåll]"
_TOC_CLOSE = "[/innehåll]"


def _all_blocks(document):
    """Alla textblock i ett dokument, i ordning."""
    block = document.begin()
    while block.isValid():
        yield block
        block = block.next()


class MainWindow(QMainWindow):
    def __init__(self, ai_client, dictation_engine, theme_mgr, config_mgr):
        super().__init__()
        self.ai = ai_client
        self.dictation = dictation_engine
        self.theme_mgr = theme_mgr
        self.config = config_mgr
        # Vanliga menyer i stället för skärmhöga popuper: stilmallens QComboBox-
        # regler får Qt att välja meny-läget, och stilen svarar nej på det. En gång
        # här, före gränssnittet, så att applikationen äger stilen.
        install_dropdown_style()
        self._qt_translator = None
        self._install_qt_translations()

        self.current_filepath = None
        self.is_modified = False
        self.page_settings = self.config.get("page_settings", DEFAULT_PAGE_SETTINGS.copy())

        # Anteckningsvalvet delas av panelen, graftvyn och wikilänk-förslagen
        self.vault = Vault(self.config.get("vault_root", VAULT_DEFAULT_DIR))
        self.research_dialog = None
        self.ghost_dialog = None
        self.graph_dialog = None
        self.code_dialog = None

        self.setWindowTitle(_("app_name"))
        self.resize(1200, 850)

        self.init_ui()
        self.init_menus()
        self.apply_theme()
        self.retranslate_ui()

        # Connect signals
        self.theme_mgr.theme_changed.connect(self.apply_theme)
        i18n.language_changed.connect(self.retranslate_ui)

        # Text change debouncer for autosave & stats & AI
        self.review_timer = QTimer(self)
        self.review_timer.setSingleShot(True)
        self.review_timer.setInterval(2500)
        self.review_timer.timeout.connect(self._on_review_timer_fired)

        # Pauspåminnelsen: en klocka som säger till med jämna mellanrum. Minuten
        # är inställningsbar (pause_minutes), för en skrivare i flöde och en som
        # sitter i möten behöver olika långa pass.
        self.pause_timer = QTimer(self)
        self.pause_timer.setInterval(max(1, int(self.config.get("pause_minutes", 50))) * 60 * 1000)
        self.pause_timer.timeout.connect(self.pause_reminder_tick)

        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(self.config.get("autosave_interval_sec", 30) * 1000)
        self.autosave_timer.timeout.connect(self._on_autosave_timer_fired)
        self.autosave_timer.start()

        self.editor.canvas.textChanged.connect(self._on_text_changed)
        self.editor.canvas.cursorPositionChanged.connect(self._update_cursor_pos)
        self.editor.canvas.magic_ai_requested.connect(self._open_inline_ai)
        self.editor.canvas.wikilink_activated.connect(self._open_wikilink)
        self.editor.canvas.directives_converted.connect(
            lambda n: self.status_bar.showMessage(_("fmt_converted", n=n), 6000))

        # Dictation engine connections
        self.dictation.state_changed.connect(self._on_dictation_state_changed)
        self.dictation.transcription_ready.connect(self._on_transcription_ready)

        # AI Status
        self.ai.ai_status_changed.connect(self._on_ai_status_changed)

        # Sidebar interactions
        self.sidebar.apply_suggestion_requested.connect(self._apply_ai_suggestion)
        self.sidebar.comment_suggestion_requested.connect(self.comment_ai_suggestion)
        self.sidebar.check_language_requested.connect(self.run_spellcheck)
        self.sidebar.replace_issue_requested.connect(self.apply_language_issue)
        self.sidebar.language_issue_clicked.connect(self.show_language_issue)
        self.sidebar.outline_item_clicked.connect(self._navigate_to_position)
        self.sidebar.btn_refresh.clicked.connect(self._trigger_ai_review)
        self.sidebar.close_requested.connect(self._toggle_sidebar)
        self.sidebar.rewrite_requested.connect(
            lambda: self._open_inline_ai(self.editor.textCursor().selectedText(), None))

        # Popups
        self.inline_ai = InlineAIPopup(self.ai, self.theme_mgr, self)
        self.inline_ai.replace_requested.connect(self._on_inline_ai_replace)
        self.inline_ai.insert_below_requested.connect(self._on_inline_ai_insert_below)

        # Initial screen state: first run gets welcome sample; subsequent runs show start page
        has_run_before = self.config.get("has_run_before", False)
        if not has_run_before:
            self.config.set("has_run_before", True)
            self._insert_welcome_sample()
            self.show_editor_screen()
        else:
            self.show_start_screen()

    def init_ui(self):
        self.stack = QStackedWidget(self)

        # 1. Start Screen (Index 0)
        self.start_screen = StartScreen(self.config, self.theme_mgr, self)
        self.start_screen.new_document_requested.connect(self.file_new)
        self.start_screen.open_document_requested.connect(self.file_open)
        self.start_screen.open_recent_requested.connect(self.open_recent_file)
        self.start_screen.open_templates_requested.connect(self.open_template_dialog)
        self.stack.addWidget(self.start_screen)

        # 2. Editor & Sidebar Container (Index 1)
        self.editor = EditorView(self.theme_mgr, self)
        self.editor.set_page_settings(self.page_settings)
        # Skrivmaskinsläget är ett val användaren gjort förut, inte ett påhitt
        self.editor.set_typewriter_mode(bool(self.config.get("typewriter_mode", False)))
        self.editor.set_readability_marks(bool(self.config.get("readability_marks", False)))
        # Graden och papprets skala (9/10): autoläget fyller bredden tills
        # skrivaren själv zoomar, och en sparad zoom överlever nu en omstart.
        self._apply_start_zoom()
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.editor)

        self.sidebar = SidebarInspector(self.ai, self.theme_mgr, self)
        self._focus_mode = False     # ägs av programmet, se _set_focus_mode
        self.sidebar.setVisible(self.config.get("show_ai_sidebar", False))

        # Anteckningspanelen som egen flik bredvid granskning/disposition
        self.vault.scan()
        self.notes_panel = NotesPanel(self.vault, self.theme_mgr, self)
        self.notes_panel.open_file_requested.connect(self.open_recent_file)
        self.notes_panel.insert_text_requested.connect(self._insert_text_at_cursor)
        self.notes_panel.show_graph_requested.connect(self._open_graph)
        self.notes_panel.vault_changed.connect(self._on_vault_changed)
        self.sidebar.add_tab(self.notes_panel, "sidebar_tab_notes")

        # Scenens uppgifter: synopsis, status, etiketter, mål. Panelen äger ingen
        # data — den visar den nod projektvyn har markerat.
        self.scene_inspector = SceneInspector(self)
        self.scene_inspector.meta_changed.connect(self._on_scene_meta_changed)
        self.scene_inspector.open_node.connect(self._open_node)
        self.scene_inspector.comment_requested.connect(self.ask_new_comment)
        self.scene_inspector.comment_activated.connect(self.goto_comment)
        self.scene_inspector.reply_requested.connect(self.ask_reply)
        self.sidebar.add_tab(self.scene_inspector, "sidebar_tab_scene")

        # Skrivloggen (fas 2.1–2.5): dagens ord, kvot mot deadline, historik,
        # svit och sprintar. Den bokför skillnaden mellan två mätningar av
        # ordantalet — ett ändrat ord är inte ett skrivet ord.
        self.writing_log = WritingLogPanel(self.config, self.theme_mgr)
        self.writing_log.status_message.connect(
            lambda m: self.status_bar.showMessage(m, 6000))
        self.writing_log.sprint_finished.connect(self._on_sprint_finished)
        self.sidebar.add_tab(self.writing_log, "sidebar_tab_log")

        # Story biblen (fas 2.8): karaktärsblad, relationer och scenkopplingar
        # ur projektets codex. Bladet visar vilka scener personen är med i och
        # hur ofta namnet nämns i manuset.
        self.codex_panel = CodexPanel(self.config, self.theme_mgr)
        self.codex_panel.status_message.connect(
            lambda m: self.status_bar.showMessage(m, 6000))
        self.codex_panel.open_scene.connect(self._open_node)
        self.sidebar.add_tab(self.codex_panel, "sidebar_tab_codex")

        # Analysen (4.17, 2.18): upprepade ord och fraser, namnvarianter och
        # codexnamn som aldrig nämns — plus siffrorna över manuset. Klicket på
        # en rad öppnar scenen och markerar textstället, så rapporten är en väg
        # in i texten. Analysen körs när författaren ber om den: den kostar tid
        # på en färdig bok.
        self.insight = InsightPanel()
        self.insight.scene_requested.connect(self.goto_quote)
        self.insight.status_message.connect(
            lambda m: self.status_bar.showMessage(m, 6000))
        self.sidebar.add_tab(self.insight, "sidebar_tab_insight")

        # Fråga manuset (6.3, 6.4): urvalet byggs i core/context och visas
        # innan det skickas. Klick i ett citat öppnar scenen det kom ifrån.
        self.ask = AskPanel(self.ai, self.config)
        self.ask.scene_requested.connect(self._open_node)
        self.ask.status_message.connect(
            lambda meddelande: self.status_bar.showMessage(meddelande, 6000))
        self.sidebar.add_tab(self.ask, "sidebar_tab_ask")

        self.splitter.addWidget(self.sidebar)

        # Projektets träd. Ligger först i delaren men visas bara när ett projekt
        # är öppet — ett enstaka dokument och ett projekt är två skilda lägen.
        self.project = None
        self.active_scene_id = None
        self.codex = None                # projektets entiteter (core.storybible)
        self.binder = BinderPanel(self)
        self.binder.scene_selected.connect(self._load_scene)
        self.binder.structure_changed.connect(self._on_structure_changed)
        self.binder.collections.read_requested.connect(self._read_collection)
        self.binder.setVisible(False)
        self.splitter.insertWidget(0, self.binder)

        self.splitter.setStretchFactor(0, 0)   # projektvyn: så bred som den behöver
        self.splitter.setStretchFactor(1, 1)   # editorn växer
        self.splitter.setStretchFactor(2, 0)   # sidopanelen
        self.stack.addWidget(self.splitter)

        # Läsvyn: flera scener som en sammanhängande text. Egen sida i stacken,
        # så den vanliga editorn står orörd kvar när man går tillbaka.
        self.scrivenings = ScriveningsView(self)
        self.scrivenings.scene_activated.connect(self._open_from_scrivenings)
        self.scrivenings.closed.connect(self._close_scrivenings)
        self.stack.addWidget(self.scrivenings)
        self._scrivenings_index = self.stack.indexOf(self.scrivenings)

        # Plot-tavlan (fas 2.9): en rad per scen med tråd, POV, status och tid.
        # Egen sida i stacken, inte en flik i sidopanelen — åtta kolumner är
        # ~790 px och panelen är 370, så tabellen behöver bredden.
        self.plot_grid = PlotGrid(self)
        self.plot_grid.scene_selected.connect(self._open_node)
        self.plot_grid.structure_changed.connect(self._on_structure_changed)
        self.plot_grid.events_requested.connect(self.show_events)
        self.stack.addWidget(self.plot_grid)
        self._plot_grid_index = self.stack.indexOf(self.plot_grid)

        # Appskalet: topbaren läggs i fönstrets menyplats (då hamnar den över
        # verktygsraden, som referensen), och railen + stacken blir innehållet.
        self.topbar = TopBar(self.theme_mgr, self)
        self.topbar.undo_requested.connect(lambda: self.active_canvas.undo())
        self.topbar.redo_requested.connect(lambda: self.active_canvas.redo())
        self.topbar.help_requested.connect(self._show_about)
        # Egen menyrad inuti topbaren. Fönstrets egen menyrad hade tagit
        # tillbaka sin plats ovanför innehållet (och gjort topbaren osynlig).
        self.menu_bar = QMenuBar(self.topbar)
        self.topbar.set_menu_bar(self.menu_bar)
        self.setMenuWidget(self.topbar)

        self.rail = LeftRail(self.theme_mgr, self)
        self.rail.view_requested.connect(self._on_rail_view)
        self.rail.settings_requested.connect(self._open_settings)

        self.shell = QWidget(self)
        rad = QHBoxLayout(self.shell)
        rad.setContentsMargins(0, 0, 0, 0)
        rad.setSpacing(0)
        rad.addWidget(self.rail)
        rad.addWidget(self.stack, 1)
        self.setCentralWidget(self.shell)

        # 3. Formatting Toolbar
        self.toolbar = FormattingToolBar(self.editor, self.theme_mgr, self)
        self.toolbar.magic_ai_clicked.connect(lambda: self._open_inline_ai(self.editor.textCursor().selectedText(), None))
        self.toolbar.dictation_clicked.connect(self._toggle_dictation)
        self.toolbar.sidebar_toggled.connect(self._toggle_sidebar)
        self.toolbar.google_fonts_clicked.connect(self._open_google_fonts_dialog)
        self.toolbar.research_clicked.connect(self._open_research)
        self.toolbar.ghostwriter_clicked.connect(self._open_ghostwriter)
        self.toolbar.code_clicked.connect(self._open_code_analysis)
        self.toolbar.image_clicked.connect(self.open_insert_image_dialog)
        self.toolbar.chart_clicked.connect(self.open_insert_chart_dialog)
        self.toolbar.templates_clicked.connect(self.open_template_dialog)
        self.toolbar.page_break_clicked.connect(self.editor.canvas.insert_page_break)
        self.toolbar.page_setup_clicked.connect(self.open_page_setup_dialog)
        self.addToolBar(self.toolbar)

        # 4. Status Bar
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)

        self.lbl_stats = QLabel("0 words | 0 characters")
        self.lbl_cursor = QLabel("Ln 1, Col 1")
        self.lbl_ai_status = QLabel("✨ " + _("status_ai_ready"))
        self.lbl_dict_status = QLabel("🎙️ " + _("status_dictation_idle"))

        self.btn_lang_toggle = QPushButton()
        self.btn_lang_toggle.setObjectName("StatusBarLangBtn")
        self.btn_lang_toggle.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_lang_toggle.clicked.connect(self._toggle_language)
        self.btn_lang_toggle.setStyleSheet("""
            QPushButton#StatusBarLangBtn {
                background-color: transparent;
                border: 1px solid rgba(128, 128, 128, 0.3);
                border-radius: 4px;
                padding: 2px 6px;
                font-weight: 600;
                font-size: 11px;
            }
            QPushButton#StatusBarLangBtn:hover {
                background-color: rgba(128, 128, 128, 0.15);
            }
        """)
        self._update_lang_toggle_btn()

        self.status_bar.addWidget(self.lbl_stats)
        self.status_bar.addPermanentWidget(self.writing_log.status_widget())
        self.status_bar.addPermanentWidget(self.lbl_ai_status)
        self.status_bar.addPermanentWidget(self.lbl_dict_status)
        self.status_bar.addPermanentWidget(self.lbl_cursor)
        self.status_bar.addPermanentWidget(self.btn_lang_toggle)

        # 5. Appskalet enligt referensen: topbar (64px) överst med menyraden
        # inuti, och en 66px-rail längst till vänster. Se
        # docs/design/scribentia-ui-spec.md. Railen äger ingen data — den byter vy.
        # Gör valvets anteckningar tillgängliga som [[förslag]] direkt
        self._refresh_link_titles()

    def _on_rail_view(self, key: str) -> None:
        """Railen byter vy. Varje knapp gör något som redan finns: visa
        dokumentet, visa filerna (projektets träd, annars listan över senaste)
        eller öppna mallarna."""
        if not hasattr(self, "rail"):
            return
        self.rail.set_active(key)
        if key == "document":
            self.show_editor_screen()
        elif key == "files":
            if self.project is not None:
                self.binder.setVisible(True)
                self.show_editor_screen()
            else:
                self.show_start_screen()
        elif key == "templates":
            self.open_template_dialog()

    def _add_action(self, menu, text, slot, shortcut=None):
        act = QAction(text, self)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        if slot:
            act.triggered.connect(slot)
        menu.addAction(act)
        return act

    def init_menus(self):
        mb = self.menu_bar

        # File Menu
        self.menu_file = mb.addMenu(_("menu_file"))
        self.act_start_page = self._add_action(self.menu_file, _("menu_file_start_page"), self.show_start_screen, "Ctrl+H")
        self.act_new = self._add_action(self.menu_file, _("menu_file_new"), self.file_new, "Ctrl+N")
        self.act_new_template = self._add_action(self.menu_file, "🎨 " + _("menu_file_new_template"), self.open_template_dialog, "Ctrl+Shift+T")
        self.act_instructions = self._add_action(self.menu_file, "📌 " + _("menu_file_instructions"),
                                                 self._edit_ai_instructions)
        self.act_overview = self._add_action(self.menu_file, "📊 " + _("menu_file_overview"),
                                             self._open_overview, "Ctrl+Shift+O")
        self.act_history = self._add_action(self.menu_file, "🕘 " + _("menu_file_history"),
                                            self._open_history, "Ctrl+Shift+H")
        self.act_review = self._add_action(self.menu_file, "📝 " + _("menu_file_review"),
                                           self._open_review, "Ctrl+Alt+R")
        self.act_open = self._add_action(self.menu_file, _("menu_file_open"), self.file_open, "Ctrl+O")
        self.menu_file.addSeparator()
        self.act_new_project = self._add_action(self.menu_file, "📚 " + _("menu_file_new_project"), self.new_project)
        self.act_open_project = self._add_action(self.menu_file, "📚 " + _("menu_file_open_project"), self.open_project)
        self.act_close_project = self._add_action(self.menu_file, _("menu_file_close_project"), self.close_project)
        self.menu_file.addSeparator()
        
        # Recent Files submenu
        self.menu_recent = self.menu_file.addMenu(_("menu_file_recent"))
        self._update_recent_menu()

        self.menu_file.addSeparator()
        self.act_save = self._add_action(self.menu_file, _("menu_file_save"), self.file_save, "Ctrl+S")
        self.act_save_as = self._add_action(self.menu_file, _("menu_file_save_as"), self.file_save_as, "Ctrl+Shift+S")
        self.menu_file.addSeparator()
        self.act_page_setup = self._add_action(self.menu_file, "⚙️ " + _("menu_file_page_setup"), self.open_page_setup_dialog)
        self.act_print = self._add_action(self.menu_file, _("menu_file_print"), self.file_print, "Ctrl+P")
        self.act_print_prev = self._add_action(self.menu_file, _("menu_file_print_preview"), self.file_print_preview, "Ctrl+Shift+P")
        self.menu_file.addSeparator()
        self.act_exp_pdf = self._add_action(self.menu_file, _("menu_file_export_pdf"), self.export_pdf, "Ctrl+Shift+E")
        self.act_exp_docx = self._add_action(self.menu_file, _("menu_file_export_docx"), self.export_docx)
        self.act_exp_md = self._add_action(self.menu_file, _("menu_file_export_md"), self.export_markdown)
        self.act_exp_html = self._add_action(self.menu_file, _("menu_file_export_html"), self.export_html)
        self.act_exp_epub = self._add_action(self.menu_file, _("menu_file_export_epub"), self.export_epub_book)
        # Kompileringen (5.15) samlar det de andra gör var för sig: urval,
        # delning och namn — med sparade profiler per bok.
        self.act_compile = self._add_action(self.menu_file, _("menu_file_compile"),
                                            self.open_compile_dialog)
        self.act_release = self._add_action(self.menu_file, _("menu_file_release"), self.release_book)
        self.act_epubcheck = self._add_action(self.menu_file, _("menu_file_epubcheck"),
                                              self.check_epub_with_epubcheck)
        self.act_cover = self._add_action(self.menu_file, _("menu_file_cover"), self.draw_cover_sheet)
        self.act_open_release = self._add_action(self.menu_file, _("menu_file_open_release"),
                                                self.open_release_folder)
        self.last_release_folder = None
        self.menu_file.addSeparator()
        self.act_exit = self._add_action(self.menu_file, _("menu_file_exit"), self.close, "Ctrl+Q")

        # Edit Menu
        self.menu_edit = mb.addMenu(_("menu_edit"))
        self.act_undo = self._add_action(self.menu_edit, _("menu_edit_undo"), lambda: self.active_canvas.undo(), "Ctrl+Z")
        self.act_redo = self._add_action(self.menu_edit, _("menu_edit_redo"), lambda: self.active_canvas.redo(), "Ctrl+Y")
        self.menu_edit.addSeparator()
        self.act_cut = self._add_action(self.menu_edit, _("menu_edit_cut"), lambda: self.active_canvas.cut(), "Ctrl+X")
        self.act_copy = self._add_action(self.menu_edit, _("menu_edit_copy"), lambda: self.active_canvas.copy(), "Ctrl+C")
        self.act_paste = self._add_action(self.menu_edit, _("menu_edit_paste"), lambda: self.active_canvas.paste(), "Ctrl+V")
        self.act_select_all = self._add_action(self.menu_edit, _("menu_edit_select_all"), lambda: self.active_canvas.selectAll(), "Ctrl+A")
        self.menu_edit.addSeparator()
        self.act_find = self._add_action(self.menu_edit, _("menu_edit_find"), self.open_find, "Ctrl+F")
        self.act_find_replace = self._add_action(self.menu_edit, _("menu_edit_find_replace"), lambda: self.open_find(with_replace=True), "Ctrl+H")
        self.act_autocorrect = self._add_action(self.menu_edit, _("menu_edit_autocorrect"), self.run_autocorrect, "Ctrl+Shift+K")
        self.act_spellcheck = self._add_action(self.menu_edit, _("menu_edit_spellcheck"), self.run_spellcheck, "Ctrl+Shift+G")

        # View Menu
        self.menu_view = mb.addMenu(_("menu_view"))
        self.act_view_sidebar = self._add_action(self.menu_view, _("menu_view_ai_sidebar"), self._toggle_sidebar, "Ctrl+Shift+I")
        self.act_view_focus = self._add_action(self.menu_view, _("menu_view_focus_mode"), self._toggle_focus_mode, "F11")
        self.act_view_typewriter = self._add_action(
            self.menu_view, _("menu_view_typewriter"), self._toggle_typewriter)
        self.act_view_grid = self._add_action(
            self.menu_view, _("menu_view_grid"), self._toggle_plot_grid)
        self.act_view_readability = self._add_action(
            self.menu_view, _("menu_view_readability"), self._toggle_readability)
        self.act_view_readability.setCheckable(True)
        self.act_view_readability.setChecked(
            bool(self.config.get("readability_marks", False)))
        self.act_view_typewriter.setCheckable(True)
        self.act_view_typewriter.setChecked(bool(self.config.get("typewriter_mode", False)))
        self.act_file_publish = self._add_action(
            self.menu_file, _("menu_file_publish"), self.open_publish_dialog)
        self.act_view_pause = self._add_action(
            self.menu_view, _("menu_view_pause"), self._toggle_pause_reminder)
        self.act_view_pause.setCheckable(True)
        self.act_view_pause.setChecked(bool(self.config.get("pause_reminder", False)))
        self.start_pause_timer_if_enabled()
        self.act_view_scrivenings = self._add_action(
            self.menu_view, _("menu_view_scrivenings"), self._toggle_scrivenings, "Ctrl+Shift+L")
        self.act_view_scrivenings.setEnabled(False)     # bara i projektläge
        self.act_view_variants = self._add_action(
            self.menu_view, "🔀 " + _("menu_view_variants"), self.open_variants_dialog,
            "Ctrl+Alt+V")
        self.act_view_variants.setEnabled(False)        # bara i projektläge
        self.menu_view.addSeparator()
        self.act_zoom_in = self._add_action(self.menu_view, _("menu_view_zoom_in"), self._zoom_in, "Ctrl++")
        self.act_zoom_out = self._add_action(self.menu_view, _("menu_view_zoom_out"), self._zoom_out, "Ctrl+-")
        self.act_zoom_reset = self._add_action(self.menu_view, _("menu_view_zoom_reset"), self._zoom_reset, "Ctrl+0")
        self.menu_view.addSeparator()
        
        # Språkmenyn: ett val per språkfil, med språkets namn på sig självt.
        self.menu_language = self.menu_view.addMenu("🌐 " + _("menu_view_language"))
        self.act_lang = {}
        for kod, namn in i18n.get_available_languages():
            act = QAction(namn, self)
            act.setCheckable(True)
            act.triggered.connect(lambda _checked=False, k=kod: self._set_language(k))
            self.menu_language.addAction(act)
            self.act_lang[kod] = act
        self._update_lang_menu_actions()

        # Insert Menu
        self.menu_insert = mb.addMenu(_("menu_insert"))
        self.act_ins_table = self._add_action(self.menu_insert, "📊 " + _("menu_insert_table"), self.toolbar._open_insert_table_dialog)
        self.act_ins_image = self._add_action(self.menu_insert, "🖼️ " + _("menu_insert_image"), self.open_insert_image_dialog)
        self.act_ins_chart = self._add_action(self.menu_insert, "📈 " + _("menu_insert_chart"), self.open_insert_chart_dialog)
        self.act_ins_divider = self._add_action(self.menu_insert, "─ " + _("menu_insert_horizontal_rule"), self.toolbar._insert_divider)
        self.act_ins_page_break = self._add_action(self.menu_insert, "📄 " + _("menu_insert_page_break"), self.editor.canvas.insert_page_break, "Ctrl+Return")
        self.act_ins_template = self._add_action(self.menu_insert, "🎨 " + _("menu_insert_template"), self.open_template_dialog)
        self.act_ins_comment = self._add_action(
            self.menu_insert, "💬 " + _("menu_insert_comment"), self.ask_new_comment, "Ctrl+Alt+M")
        
        self.menu_ins_callout = self.menu_insert.addMenu("💡 " + _("tb_callout"))
        self.act_callout_info = self.menu_ins_callout.addAction(_("tb_callout_info"), lambda: self.toolbar._insert_callout("info"))
        self.act_callout_tip = self.menu_ins_callout.addAction(_("tb_callout_tip"), lambda: self.toolbar._insert_callout("tip"))
        self.act_callout_warning = self.menu_ins_callout.addAction(_("tb_callout_warning"), lambda: self.toolbar._insert_callout("warning"))
        self.act_callout_quote = self.menu_ins_callout.addAction(_("tb_callout_quote"), lambda: self.toolbar._insert_callout("quote"))

        # Format Menu
        self.menu_format = mb.addMenu(_("menu_format"))
        self.act_fmt_bold = self._add_action(self.menu_format, _("menu_format_bold"), self.toolbar._toggle_bold, "Ctrl+B")
        self.act_fmt_italic = self._add_action(self.menu_format, _("menu_format_italic"), self.toolbar._toggle_italic, "Ctrl+I")
        self.act_fmt_underline = self._add_action(self.menu_format, _("menu_format_underline"), self.toolbar._toggle_underline, "Ctrl+U")
        self.act_fmt_strike = self._add_action(self.menu_format, _("menu_format_strikethrough"), self.toolbar._toggle_strike)
        self.act_fmt_sub = self._add_action(self.menu_format, _("tb_subscript"), self.toolbar._toggle_subscript)
        self.act_fmt_super = self._add_action(self.menu_format, _("tb_superscript"), self.toolbar._toggle_superscript)
        self.act_fmt_clear = self._add_action(self.menu_format, _("menu_format_clear"), self.toolbar._clear_formatting, "Ctrl+\\")
        self.menu_format.addSeparator()
        self.act_gfonts = self._add_action(self.menu_format, "🌐 " + _("menu_format_google_fonts"), self._open_google_fonts_dialog)
        self.menu_format.addSeparator()
        self.act_fmt_directives = self._add_action(self.menu_format, "⌗ " + _("menu_format_directives"), self._format_directives, "Ctrl+Shift+M")
        self.menu_insert.addSeparator()
        self.act_fld_note = self._add_action(self.menu_insert, _("menu_format_note"), lambda: self.insert_field("not"), "Ctrl+Alt+F")
        self.act_fld_figure = self._add_action(self.menu_insert, _("menu_format_figure"), lambda: self.insert_field("figur"))
        self.act_fld_table = self._add_action(self.menu_insert, _("menu_format_table"), lambda: self.insert_field("tabell"))
        self.act_fld_ref = self._add_action(self.menu_insert, _("menu_format_ref"), self.insert_reference)
        self.act_fld_toc = self._add_action(self.menu_insert, _("menu_format_toc"), self.insert_toc, "Ctrl+Alt+I")

        # AI Assistant Menu
        self.menu_ai = mb.addMenu(_("menu_ai"))
        self.act_inline_ai = self._add_action(self.menu_ai, _("menu_ai_inline"), lambda: self._open_inline_ai(self.editor.textCursor().selectedText(), None), "Ctrl+K")
        self.act_review_ai = self._add_action(self.menu_ai, _("menu_ai_review"), self._trigger_ai_review)
        self.act_dictation = self._add_action(self.menu_ai, _("menu_ai_dictation"), self._toggle_dictation, "F8")
        self.menu_ai.addSeparator()
        self.act_research = self._add_action(self.menu_ai, "🔎 " + _("menu_ai_research"), self._open_research, "Ctrl+Shift+R")
        self.act_ghost = self._add_action(self.menu_ai, "👻 " + _("menu_ai_ghostwriter"), self._open_ghostwriter, "Ctrl+Shift+G")
        self.act_ask = self._add_action(self.menu_ai, "❓ " + _("menu_ai_ask"), self.open_ask_panel, "Ctrl+Shift+Q")
        self.act_ins_link = self._add_action(self.menu_ai, "🔗 " + _("menu_ai_insert_link"), self._insert_wikilink_dialog, "Ctrl+L")
        self.act_gen_para = self._add_action(self.menu_ai, "✎ " + _("menu_ai_paragraph"), self._open_generate_paragraph, "Ctrl+Shift+A")
        self.act_code = self._add_action(self.menu_ai, "⌨ " + _("menu_ai_code"), self._open_code_analysis, "Ctrl+Shift+K")
        self.act_exercise = self._add_action(self.menu_ai, "🧩 " + _("menu_ai_exercise"),
                                             self._open_exercises, "Ctrl+Shift+E")
        self.menu_ai.addSeparator()
        self.act_settings = self._add_action(self.menu_ai, _("menu_ai_settings"), self._open_settings)

        # Notes Menu
        self.menu_notes = mb.addMenu(_("menu_notes"))
        self.act_notes_new = self._add_action(self.menu_notes, "➕ " + _("menu_notes_new"), self._new_note, "Ctrl+Shift+N")
        self.act_notes_search = self._add_action(self.menu_notes, "🔍 " + _("menu_notes_search"), self._focus_vault_search, "Ctrl+Shift+F")
        self.menu_notes.addSeparator()
        self.act_notes_graph = self._add_action(self.menu_notes, "🕸 " + _("menu_notes_graph"), self._open_graph)
        self.act_notes_rescan = self._add_action(self.menu_notes, "⟳ " + _("menu_notes_rescan"), self._rescan_vault)
        self.menu_notes.addSeparator()
        self.act_notes_panel = self._add_action(self.menu_notes, "🗂 " + _("menu_notes_panel"), self._show_vault_panel)

        # Help Menu
        self.menu_help = mb.addMenu(_("menu_help"))
        self.act_about = self._add_action(self.menu_help, _("menu_help_about"), self._show_about)

        # Dokumentknappen i topbaren: samma kommandon som Arkiv, samlade på
        # det ställe referensen har dem (filnamnet högst upp till vänster).
        self.menu_document = QMenu(self)
        self.menu_document.addAction(self.act_new)
        self.menu_document.addAction(self.act_open)
        self.menu_document.addAction(self.menu_recent.menuAction())
        self.menu_document.addSeparator()
        self.menu_document.addAction(self.act_save)
        self.menu_document.addAction(self.act_save_as)
        if getattr(self, "topbar", None) is not None:
            self.topbar.set_file_menu(self.menu_document)

    def _update_recent_menu(self):
        self.menu_recent.clear()
        recents = self.config.get("recent_files", [])
        if not recents:
            act = self.menu_recent.addAction(_("menu_file_no_recents"))
            act.setEnabled(False)
            return

        for fpath in recents[:10]:
            fname = os.path.basename(fpath)
            act = self.menu_recent.addAction(f"{fname} ({fpath})")
            act.triggered.connect(lambda checked, fp=fpath: self.open_recent_file(fp))

        self.menu_recent.addSeparator()
        act_clear = self.menu_recent.addAction(_("menu_file_clear_recents"))
        act_clear.triggered.connect(self._clear_recent_files)

    def _clear_recent_files(self):
        self.config.clear_recent_files()
        self._update_recent_menu()
        self.start_screen.refresh_recents()

    def show_start_screen(self):
        if self.stack.currentIndex() == 1 and not self._maybe_save_changes():
            return
        self.start_screen.refresh_recents()
        self.stack.setCurrentIndex(0)
        self.toolbar.setVisible(False)
        self.status_bar.setVisible(False)
        self.setWindowTitle(_("app_name"))

    @property
    def active_canvas(self):
        """Skrivytan som tar emot kommandon: läsvyn om den är öppen, annars editorn.

        Det som bara finns i editorn (verktygsraden, infogningar, direktiv) är i
        stället avstängt så länge läsvyn är uppe — se _sync_reading_mode. Ett
        halvt läge som formaterar fel scen vore värre än inget (R01.9).
        """
        if self.stack.currentIndex() == getattr(self, "_scrivenings_index", -1):
            return self.scrivenings.pane
        return self.editor.canvas

    def _sync_reading_mode(self, reading: bool) -> None:
        """Stänger av det som hör till editorn medan läsvyn är uppe."""
        if self.toolbar is not None:
            self.toolbar.setEnabled(not reading)
        for name in ("act_ins_page_break", "act_ins_image", "act_ins_chart",
                     "act_ins_table", "act_ins_template", "act_ins_divider",
                     "act_ins_comment"):
            action = getattr(self, name, None)
            if action is not None:
                action.setEnabled(not reading)

    def show_editor_screen(self):
        self.stack.setCurrentIndex(1)
        self.toolbar.setVisible(True)
        self.sidebar.setVisible(self.config.get("show_ai_sidebar", False))
        self.status_bar.setVisible(True)
        self._update_window_title()
        self._update_stats()
        self.editor.canvas.setFocus()

    def _toggle_language(self):
        """Statusfältets knapp går till nästa språk — inte bara mellan två."""
        self._set_language(next_language(i18n.get_language()))

    def _set_language(self, lang_code):
        if lang_code != i18n.get_language():
            i18n.set_language(lang_code)
            self.config.set("language", lang_code)
            self._update_lang_menu_actions()

    def _update_lang_toggle_btn(self):
        """Knappen visar språket det står på, inte en tvåspråkig flagga."""
        self.btn_lang_toggle.setText(native(i18n.get_language()))
        self.btn_lang_toggle.setToolTip(_("status_lang_switch_tooltip"))

    def _update_lang_menu_actions(self):
        curr = i18n.get_language()
        for kod, act in getattr(self, "act_lang", {}).items():
            act.setChecked(kod == curr)

    def _zoom_in(self):
        self._set_zoom_pt(self.editor.text_point_size() + 1)

    def _zoom_out(self):
        self._set_zoom_pt(self.editor.text_point_size() - 1)

    def _zoom_reset(self):
        # 100 %: den grad skrivaren har valt i inställningarna.
        self._set_zoom_pt(float(self.config.get("default_font_size", 12)))

    def _set_zoom_pt(self, pt: float) -> None:
        """Sätter graden, minns den och lämnar autoläget.

        Graden går genom dokumentet (se EditorView.set_text_point_size), för
        widgetens grad styr temats stilmall över — mätt: Ctrl++ gav 13,0 pt före
        och efter, alltså en död knapp. zoom_level skrevs i configen men lästes
        aldrig, så en zoom överlevde inte en omstart.
        """
        self.editor.zoom_auto = False
        self.editor.set_text_point_size(pt)
        self.config.set("zoom_auto", False)
        self.config.set("zoom_level",
                        int(round(self.editor.text_point_size()
                                  / self.editor.BASE_TEXT_PT * 100)))

    def _apply_start_zoom(self) -> None:
        """Vid start: autoläget fyller bredden, annars den sparade graden.

        Autoläget är på tills skrivaren själv zoomar. En A4 i verklig storlek
        (750 px) är en liten lapp på en bred skärm, och det var hela känslan av
        A5 — i autoläget ritas pappret så stort att det fyller bredden, och
        texten med det. Ctrl+0 ger verklig storlek och stänger autoläget.
        """
        if self.config.get("zoom_auto", True):
            self.editor.zoom_auto = True
            self.editor.set_text_point_size(
                self.editor.BASE_TEXT_PT * self.editor.fit_scale())
        else:
            self.editor.zoom_auto = False
            self.editor.set_text_point_size(
                self.editor.BASE_TEXT_PT * float(self.config.get("zoom_level", 100)) / 100.0)

    def _insert_welcome_sample(self):
        lang = i18n.get_language()
        if lang == "sv":
            html = f"""
            <h1>{_("app_title")}</h1>
            <p>Välkommen till <b>Scribentia</b>, din moderna och intelligenta skrivmiljö för Linux & Omarchy.</p>
            
            <h2>🚀 Vad gör Scribentia unikt?</h2>
            <p>Scribentia kombinerar en ren och fokuserad ordbehandlare med inbyggd AI-granskning, interaktiv omskrivning och lokal röst-diktering:</p>
            
            <ul>
              <li><b>✨ Magisk Co-Writer:</b> Markera valfri text och tryck <code>Ctrl + K</code> för att skriva om, förbättra tonläge, översätta eller utveckla.</li>
              <li><b>📑 AI-Granskare & Statistik:</b> Få förslag i realtid, LIX-läsbarhet, tonanalys och automatisk disposition.</li>
              <li><b>🎙️ Röst-diktering:</b> Tryck <code>F8</code> för att tala in din text med automatisk transkribering.</li>
              <li><b>📄 Full kompatibilitet:</b> Öppna och spara direkt i Word <code>.docx</code>, <code>.md</code> (Markdown) och skriv ut till <code>.pdf</code>.</li>
            </ul>
            
            <blockquote>"Det mest skrämmande ögonblicket är alltid precis innan du börjar. Därefter kan det bara bli bättre." — Stephen King</blockquote>
            <p>Börja skriva eller radera denna text för att påbörja ditt mästerverk!</p>
            """
        else:
            html = f"""
            <h1>{_("app_title")}</h1>
            <p>Welcome to <b>Scribentia</b>, your next-generation intelligent writing environment designed for Linux and Omarchy.</p>
            
            <h2>🚀 What makes Scribentia unique?</h2>
            <p>Scribentia combines standard WYSIWYG document editing with built-in AI review, intelligent rephrasing, and local voice dictation:</p>
            
            <ul>
              <li><b>✨ Magic Co-Writer:</b> Highlight any phrase or sentence and press <code>Ctrl + K</code> to rewrite, polish, translate, or expand.</li>
              <li><b>📑 AI Inspector Sidebar:</b> Get live suggestions, readability grading (LIX), tone analysis, and automatic heading outline.</li>
              <li><b>🎙️ Voice Dictation:</b> Press <code>F8</code> to speak and dictate your thoughts naturally.</li>
              <li><b>📄 Native Export:</b> Export your documents directly to Word <code>.docx</code>, print-ready <code>.pdf</code>, and <code>.md</code>.</li>
            </ul>
            
            <blockquote>"The scariest moment is always just before you start. After that, things can only get better." — Stephen King</blockquote>
            <p>Start typing or deleting this text to draft your masterwork!</p>
            """
        self.editor.document.setHtml(html)
        self.is_modified = False
        self._update_window_title()

    def _on_text_changed(self):
        if self.stack.currentIndex() == 1:
            self.is_modified = True
            self._update_window_title()
            self._update_stats()
            self.review_timer.start()

    def _update_cursor_pos(self):
        cursor = self.editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.positionInBlock() + 1
        self.lbl_cursor.setText(f"Ln {line}, Col {col}")

    def _update_stats(self):
        if self.stack.currentIndex() == getattr(self, "_scrivenings_index", -1):
            words = sum(self.project.words(n.id) for n in self.scrivenings.shown_nodes()) \
                if self.project else 0
            self.lbl_stats.setText(_("scrivenings_stats", words=words))
            self._track_writing()
            return
        self.sidebar.update_metrics_and_outline(self.editor.document)
        self.lbl_stats.setText(self.sidebar.status_text())
        self._track_writing()

    def _track_writing(self) -> None:
        """Skrivloggen får antalet ord och vilket dokument det gäller.

        Nyckeln skiljer scen, läsvyns samlade text och ett löst dokument, så att
        ett byte av vy eller scen blir en ny baslinje i stället för ett hopp i
        statistiken.
        """
        if self.stack.currentIndex() == getattr(self, "_scrivenings_index", -1):
            ord_antal = (sum(self.project.words(n.id) for n in self.scrivenings.shown_nodes())
                         if self.project else 0)
            self.writing_log.track(ord_antal, f"scrivenings:{id(self.project)}")
        elif self.project is not None and self.active_scene_id:
            self.writing_log.track(self.sidebar.words, f"scen:{self.active_scene_id}")
        else:
            self.writing_log.track(self.sidebar.words,
                                   f"dok:{self.current_filepath or 'utan-titel'}")

    def _on_sprint_finished(self, minutes: int, words: int) -> None:
        """Sprinten är slut: en rad i statusfältet och en vink i aktivitetsfältet."""
        self.status_bar.showMessage(_("log_sprint_done", minutes=minutes, n=words), 10000)
        QApplication.alert(self, 3000)

    def _update_window_title(self):
        if self.stack.currentIndex() == 0:
            self.setWindowTitle(_("app_name"))
            self._sync_topbar_document("", False)
            return
        if self.project is not None:
            if self.stack.currentIndex() == getattr(self, "_scrivenings_index", -1):
                self.setWindowTitle(
                    f"{self.project.title} — {_('menu_view_scrivenings')} — {_('app_name')}")
                self._sync_topbar_document(self.project.title, self.is_modified)
                return
            scene = ""
            if self.active_scene_id:
                try:
                    scene = self.project.by_id(self.active_scene_id).title
                except KeyError:
                    scene = ""
            mod_flag = " •" if self.is_modified else ""
            parts = [self.project.title] + ([scene] if scene else [])
            self.setWindowTitle(f"{' — '.join(parts)}{mod_flag} — {_('app_name')}")
            self._sync_topbar_document(parts[-1], self.is_modified)
            return
        doc_name = os.path.basename(self.current_filepath) if self.current_filepath else _("untitled_document")
        mod_flag = " •" if self.is_modified else ""
        self.setWindowTitle(f"{doc_name}{mod_flag} — {_('app_name')}")
        self._sync_topbar_document(doc_name, self.is_modified)

    def _sync_topbar_document(self, name: str, modified: bool) -> None:
        """Håller topbarens dokumentknapp och sparat-läge i takt med fönstret.

        Sparat-läget syns som text också — punkten är färg, orden är beskedet.
        """
        if getattr(self, "topbar", None) is None:
            return
        self.topbar.set_document_name(name)
        self.topbar.set_modified(modified)
        tid = None
        if self.current_filepath and os.path.exists(self.current_filepath):
            tid = datetime.fromtimestamp(os.path.getmtime(self.current_filepath))
        self.editor.set_stage_meta(
            name, _("stage_edited_today", time=(tid or datetime.now()).strftime("%H:%M")))

    def _on_review_timer_fired(self):
        if self.stack.currentIndex() == 1:
            text = self.editor.document.toPlainText()
            lang = i18n.get_language()
            self.ai.review_document(text, lang=lang)

    def _on_autosave_timer_fired(self):
        if self.project is not None:
            if self.is_modified and self.config.get("autosave", True):
                if self._flush_scene(quiet=True):
                    self.project.save()
                    self.is_modified = False
                    self._update_window_title()
            return
        if self.stack.currentIndex() == 1 and self.is_modified and self.current_filepath and self.config.get("autosave", True):
            try:
                self._save_document(self.current_filepath)
                self.is_modified = False
                self._update_window_title()
            except Exception as e:
                print(f"[Autosave] Error: {e}")

    def _open_inline_ai(self, selected_text, global_pos):
        if self.stack.currentIndex() != 1:
            return
        if global_pos is None:
            rect = self.editor.canvas.cursorRect()
            global_pos = self.editor.canvas.mapToGlobal(rect.bottomLeft())
        self.inline_ai.show_at(selected_text, global_pos)

    def _on_inline_ai_replace(self, new_text):
        cursor = self.editor.textCursor()
        cursor.insertText(new_text)
        self.editor.setTextCursor(cursor)

    def _on_inline_ai_insert_below(self, new_text):
        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cursor.insertBlock()
        cursor.insertText(new_text)
        self.editor.setTextCursor(cursor)

    def _apply_ai_suggestion(self, original, replacement):
        """Skriver in förslaget — ett markövergrepp, ett ångra-steg (R04.15).

        Ett enskilt insertText över markeringen blir ett steg i
        ångra-historiken, så ett förslag går att ta tillbaka för sig. Texten
        sparas först när scenen sparas, som allt annat man skriver.
        """
        cursor = self.editor.document.find(original)
        if cursor.isNull():
            self.status_bar.showMessage(_("ai_apply_not_found"), 5000)
            return
        cursor.insertText(replacement)
        self.editor.setTextCursor(cursor)
        self.is_modified = True
        self.status_bar.showMessage(_("ai_apply_done"), 5000)

    def comment_ai_suggestion(self, original, replacement) -> bool:
        """Lägger AI:ns förslag som en kommentar i marginalen (R04.14).

        I stället för att skriva över texten: förslaget hamnar där författaren
        läser sina egna kommentarer, texten står kvar orörd, och först när man
        väljer det skrivs det in — som ett eget ångra-steg.
        """
        if self.project is None or not self.active_scene_id or not original.strip():
            return False
        if self.project.comment_by_quote(self.active_scene_id, original) is not None:
            self.status_bar.showMessage(_("ai_comment_exists"), 5000)
            return True
        if self.add_comment(original, _("ai_comment_text", replacement=replacement)) is None:
            return False
        self.status_bar.showMessage(_("ai_comment_added"), 5000)
        return True

    def _navigate_to_position(self, pos):
        cursor = QTextCursor(self.editor.document)
        cursor.setPosition(pos)
        self.editor.setTextCursor(cursor)
        self.editor.canvas.setFocus()

    def _trigger_ai_review(self):
        text = self.editor.document.toPlainText()
        self.sidebar.update_metrics_and_outline(self.editor.document)
        self._update_stats()
        if not text or len(text.strip()) < 10:
            self.sidebar.show_short_message()
            return
        self.sidebar.set_loading(True)
        self.ai.review_document(text, lang=i18n.get_language())

    def _toggle_sidebar(self):
        vis = not self.sidebar.isVisible()
        self.sidebar.setVisible(vis)
        self.config.set("show_ai_sidebar", vis)

    def _toggle_pause_reminder(self) -> None:
        """Pauspåminnelsen: en rad i statusfältet var N:te minut (R03.7).

        Diskret, som sprintens slut — ingen modal ruta som avbryter mitt i en
        mening. Att ta en paus är författarens beslut; påminnelsen ska bara
        finnas där, inte kräva ett svar.
        """
        på = not self.pause_timer.isActive()
        self.act_view_pause.setChecked(på)
        self.config.set("pause_reminder", på)
        if på:
            self.pause_timer.start()
            self.status_bar.showMessage(
                _("pause_on", minutes=self.pause_timer.interval() // 60000), 5000)
        else:
            self.pause_timer.stop()
            self.status_bar.showMessage(_("pause_off"), 4000)

    def pause_reminder_tick(self) -> None:
        """En vänlig påminnelse om att räta på ryggen."""
        self.status_bar.showMessage(_("pause_reminder"), 15000)
        QApplication.alert(self)

    def _toggle_readability(self) -> None:
        """Markerar tunga meningar i texten — en läsbarhetsanalys man kan se.

        Meningen är den enhet LIX drivs av, så det är där rådet blir konkret:
        markeringen visar vilka meningar som är värda att korta. Texten rörs inte.
        """
        på = not self.editor.readability_marks()
        self.editor.set_readability_marks(på)
        self.act_view_readability.setChecked(på)
        self.config.set("readability_marks", på)
        if på:
            self.status_bar.showMessage(_("readability_on"), 5000)

    def _toggle_plot_grid(self) -> None:
        """Växlar mellan manuset och plot-tavlan (samma projekt, annan vy)."""
        if self.stack.currentIndex() == getattr(self, "_plot_grid_index", -1):
            self._sync_reading_mode(False)     # verktygsraden hör till manuset
            self.show_editor_screen()          # tillbaka till manuset
            return
        if self.project is None:
            self.status_bar.showMessage(_("grid_no_project"), 4000)
            return
        self.plot_grid.refresh()
        self.stack.setCurrentIndex(self._plot_grid_index)
        self._sync_reading_mode(True)
        if self.toolbar is not None:
            self.toolbar.setVisible(False)     # formatering hör till manuset
        self._update_window_title()

    def _toggle_typewriter(self) -> None:
        """Skrivmaskinsläge: markörens rad står stilla mitt i fönstret."""
        på = not self.editor.typewriter
        self.editor.set_typewriter_mode(på)
        self.act_view_typewriter.setChecked(på)
        self.config.set("typewriter_mode", på)
        if på:
            self.status_bar.showMessage(_("typewriter_on"), 4000)

    def _toggle_focus_mode(self):
        """Distraktionsfritt läge: bort med allt utom texten, och tillbaka igen.

        Läget ägs av programmet, inte av fönsterhanteraren. Det avgjordes förut av
        isFullScreen(), och kompositören kan lämna fullskärm på egen hand (sin
        egen genväg, eller sin egen hantering av F11): då svarar isFullScreen()
        nej medan menyn fortfarande är borta, nästa tryck går in i samma gren och
        gömmer allt igen, och menyn kommer aldrig tillbaka. En flagga gör att en
        tryckning alltid växlar.
        """
        self._set_focus_mode(not getattr(self, "_focus_mode", False))

    def _set_focus_mode(self, on: bool, window: bool = True):
        """Sätter läget och synligheten. `window=False` när Qt redan bytt läge."""
        self._focus_mode = on
        if window:
            if on:
                self.showFullScreen()
            else:
                self.showNormal()
        # Menyraden är inte QMainWindow:s egen utan en QMenuBar inuti menywidgeten
        # (setMenuWidget), så den göms och visas här — den följer inte med fönstret.
        self.menu_bar.setVisible(not on)
        self.status_bar.setVisible(not on)
        if on:
            self.toolbar.setVisible(False)
            self.sidebar.setVisible(False)
        elif self.stack.currentIndex() == 1:
            self.toolbar.setVisible(True)
            self.sidebar.setVisible(self.config.get("show_ai_sidebar", False))

    def changeEvent(self, event):  # noqa: N802 — Qt:s eget namn
        """Lämnas fullskärmen på annat sätt än med F11 skall menyn tillbaka."""
        super().changeEvent(event)
        if (event.type() == QEvent.Type.WindowStateChange
                and getattr(self, "_focus_mode", False)
                and not self.isFullScreen()):
            self._set_focus_mode(False, window=False)

    def _toggle_dictation(self):
        self.dictation.toggle_recording()

    def _on_dictation_state_changed(self, state):
        if state == "listening":
            self.lbl_dict_status.setText("🎙️ " + _("status_dictation_listening"))
        elif state == "transcribing":
            self.lbl_dict_status.setText("⏳ " + _("status_dictation_transcribing"))
        else:
            self.lbl_dict_status.setText("🎙️ " + _("status_dictation_idle"))

    def _on_transcription_ready(self, text):
        if self.stack.currentIndex() == 1:
            cursor = self.editor.textCursor()
            cursor.insertText(text + " ")
            self.editor.setTextCursor(cursor)

    def _on_ai_status_changed(self, status):
        if status == "analyzing":
            self.lbl_ai_status.setText("✨ " + _("status_ai_analyzing"))
        else:
            self.lbl_ai_status.setText("✨ " + _("status_ai_ready"))

    def _open_google_fonts_dialog(self):
        dlg = GoogleFontsDialog(self.theme_mgr, self)
        dlg.font_list_changed.connect(self.toolbar.combo_font.populate_fonts)
        dlg.exec()

    def _open_settings(self):
        old_root = self.config.get("vault_root", VAULT_DEFAULT_DIR)
        dlg = SettingsDialog(self.config, self.theme_mgr, self)
        dlg.exec()
        new_root = self.config.get("vault_root", VAULT_DEFAULT_DIR)
        if new_root and os.path.abspath(new_root) != os.path.abspath(old_root):
            self._on_vault_changed(new_root)

    def _show_about(self):
        QMessageBox.about(
            self,
            _("app_name"),
            f"<h3>{_('app_title')}</h3>"
            f"<p>Version 0.1.0</p>"
            f"<p>{_('about_desc')}</p>"
            # GPL v3 section 5d: an interactive interface must display its
            # legal notices. One line, plus the source link a recipient is
            # entitled to.
            f"<p>{_('about_license')}</p>"
        )

    # -------------------------------------------------------------------------
    # Extension enforcement helper
    # -------------------------------------------------------------------------
    def _ensure_extension(self, filepath: str, selected_filter: str, default_ext: str = ".docx") -> str:
        if not filepath:
            return filepath
        root, ext = os.path.splitext(filepath)
        valid_extensions = {".docx", ".md", ".markdown", ".html", ".htm", ".txt", ".pdf"}
        if ext.lower() in valid_extensions:
            return filepath
        
        filter_lower = (selected_filter or "").lower()
        if "*.docx" in filter_lower:
            target_ext = ".docx"
        elif "*.md" in filter_lower or "*.markdown" in filter_lower:
            target_ext = ".md"
        elif "*.html" in filter_lower or "*.htm" in filter_lower:
            target_ext = ".html"
        elif "*.txt" in filter_lower:
            target_ext = ".txt"
        elif "*.pdf" in filter_lower:
            target_ext = ".pdf"
        else:
            target_ext = default_ext
        return f"{filepath}{target_ext}"

    # -------------------------------------------------------------------------
    # File Operations & Printing
    # -------------------------------------------------------------------------
    # ------------------------------------------------------------ projektet

    def new_project(self):
        """Skapar ett projekt: en mapp med manifest och en fil per scen."""
        if self.stack.currentIndex() == 1 and not self._maybe_save_changes():
            return
        folder = QFileDialog.getExistingDirectory(self, _("menu_file_new_project"))
        if not folder:
            return
        default = os.path.basename(folder.rstrip(os.sep)) or _("project_untitled")
        dialog = NewProjectDialog(default_name=default, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        title, template, target = dialog.values()
        if not title:
            return
        try:
            project = Project.create(folder, title, template=template)
            project.settings["target_words"] = target
            project.save()
        except FileExistsError:
            QMessageBox.warning(self, _("project_new_title"),
                                _("project_not_empty", path=folder))
            return
        except OSError as exc:
            QMessageBox.critical(self, _("project_new_title"), str(exc))
            return
        self._activate_project(project)

    def open_project(self):
        if self.stack.currentIndex() == 1 and not self._maybe_save_changes():
            return
        folder = QFileDialog.getExistingDirectory(self, _("menu_file_open_project"))
        if not folder:
            return
        try:
            project = Project.load(folder)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, _("project_open_error_title"),
                                 _("project_open_error_text", error=exc))
            return
        self._activate_project(project)

    def close_project(self):
        if self.project is None:
            return
        self._deactivate_project()
        self.show_start_screen()

    def _activate_project(self, project):
        self._deactivate_project()
        self.project = project
        # Sidmåtten hör till dokumentet, som i Writer, där pappret ägs av
        # sidstilen: projektet minns sin egen storlek och configen är bara
        # grunden för ett nytt projekt. Förut låg måtten enbart i configen, så
        # ett A5-projekt trycktes i den storlek det förra projektet lämnade.
        eget = project.settings.get("page_settings") or {}
        if eget:
            self.page_settings = {**DEFAULT_PAGE_SETTINGS, **eget}
            self.editor.set_page_settings(self.page_settings)
        # AI:n läser projektets instruktioner ur det projekt som är öppet just nu
        self.ai.set_project_context(
            lambda: (self.project.settings.get("ai_instructions", "") if self.project else ""))
        self._open_codex(project)
        self.binder.set_project(project)
        self.writing_log.set_project(project)
        self.plot_grid.set_statuses(project.settings.get("statuses", []))
        self.plot_grid.set_project(project)
        self.binder.setVisible(True)
        self.act_view_scrivenings.setEnabled(True)
        self.act_view_variants.setEnabled(True)
        broken = project.validate()
        if broken:
            QMessageBox.warning(self, _("project_broken_title"),
                                _("project_broken_text", problems="\n".join(broken[:5])))
        self.show_editor_screen()
        scenes = project.manuscript()
        if scenes:
            self.binder.select_node(scenes[0].id)
            self._load_scene(scenes[0].id)
        self._update_window_title()

    def _open_codex(self, project):
        """Öppnar projektets egen codex. Ligger i projektmappen (R03.9, R04.2)."""
        from core.storybible import StoryBible

        try:
            self.codex = StoryBible(str(project.codex_path))
        except Exception as exc:                     # trasig fil får inte stoppa projektet
            self.codex = None
            print(f"[codex] kunde inte öppnas: {exc}")
        self.scene_inspector.set_codex(self.codex)
        self.codex_panel.set_project(project, self.codex)
        self.insight.set_project(project, self.codex)
        self.ask.set_project(project, self.codex)
        return self.codex

    def _close_codex(self):
        if self.codex is not None:
            try:
                self.codex.close()
            except Exception:                        # stängning får inte fälla projektbytet
                pass
        self.codex = None
        self.scene_inspector.set_codex(None)
        self.codex_panel.set_project(None, None)
        self.insight.set_project(None, None)
        self.ask.set_project(None, None)

    def _deactivate_project(self):
        """Lämnar projektläget. Projektet ligger kvar på disk."""
        if self.project is not None:
            self._flush_scrivenings()
            self._flush_scene(quiet=True)
        self._close_codex()
        self.project = None
        self.active_scene_id = None
        self.binder.set_project(None)
        self.writing_log.set_project(None)
        self.plot_grid.set_project(None)
        self.binder.setVisible(False)
        self.scene_inspector.set_scene(None, None)
        if hasattr(self, "ask"):
            self.ask.set_scene("")
        self._refresh_comment_marks()
        self.act_view_scrivenings.setEnabled(False)
        self.act_view_variants.setEnabled(False)
        # Editorn stod med projektets sista scen. Texten ligger redan på disk
        # (ovan), så den får inte lämna kvar ett "osparat dokument" utan väg —
        # då frågar stängningen om att spara en scenfil som redan är sparad.
        self.editor.document.clear()
        self.current_filepath = None
        self.is_modified = False
        self._update_window_title()
        if self.stack.currentIndex() == getattr(self, "_scrivenings_index", -1):
            self._sync_reading_mode(False)
            self.show_editor_screen()

    def _flush_scene(self, quiet: bool = False) -> bool:
        """Skriver editorns text till den scen som är öppen."""
        if self.project is None or not self.active_scene_id:
            return True
        try:
            self.project.write(self.active_scene_id, self.editor.document.toHtml())
            self.scene_inspector.refresh_words()
            # Ordantalet i trädet ändras när texten når disk, inte medan man skriver.
            self.binder.refresh_labels()
            # Citaten kan ha flyttat sig med texten: markeringarna byggs om.
            self._refresh_comment_marks()
            return True
        except Exception as exc:                      # noqa: BLE001 — skall synas
            if quiet:
                # ponytail: städning under autosparning skall inte kasta en modal
                # ruta i ansiktet på den som skriver. is_modified blir kvar, så
                # statusfältet visar fortfarande att något är osparat, och felet
                # hamnar i terminalen. En explicit Spara visar ruta.
                print(f"[project] kunde inte spara scenen: {exc}")
            else:
                QMessageBox.critical(self, _("project_save_error_title"), str(exc))
            return False

    def _load_scene(self, node_id):
        if self.project is None:
            return
        if self.stack.currentIndex() == getattr(self, "_scrivenings_index", -1):
            # En scen väljs medan läsvyn står uppe: texten skrivs tillbaka först,
            # annars skriver vyn över det som just valdes.
            self._flush_scrivenings()
            self.show_editor_screen()
        if node_id == self.active_scene_id:
            return
        # "Så såg scenen ut när jag lämnade den" — tas innan texten rörs, och
        # bara om den skiljer sig från den senaste punkten (annars blir historiken
        # en trave kopior av samma mening).
        self.project.snapshot_scene(node_id)
        if not self._flush_scene(quiet=True):
            return
        try:
            node = self.project.by_id(node_id)
            html = self.project.read(node_id)
        except KeyError:
            return
        self._show_scene_html(node_id, html)

    def _show_scene_html(self, node_id: str, html: str) -> None:
        """Lägger en scens text i editorn — samma väg vid öppning och återställning."""
        node = self.project.by_id(node_id)
        self.active_scene_id = node_id
        self.editor.document.setHtml(html)
        # Radbrytningen får aldrig vara avstängd i editorn. En <pre> i en sparad
        # scen gör Qt obrytbar, och då går raden utanför pappret (mätt: 1355 px i
        # ett 646 px ark). Alex regel (9/10): text bryts alltid vid ordet före
        # kanten — "det får inte ens vara under diskussion".
        from core.doc_manager import release_wrapping
        release_wrapping(self.editor.document)
        path = self.project.path_of(node)
        self.current_filepath = str(path) if path else None
        self.is_modified = False
        self.scene_inspector.set_scene(self.project, node)
        self.ask.set_scene(getattr(node, "id", ""))
        self._refresh_comment_marks()
        self.notes_panel.set_current_document(self._current_note_title())
        self.notes_panel.set_current_file(self.current_filepath or "")
        self._update_window_title()
        self._update_stats()
        self.editor.canvas.setFocus()

    def _open_exercises(self) -> None:
        """Fastnat? En fråga, tre förslag, och en väg tillbaka till skrivandet.

        Rutan vet inget om editorn: den ber om sammanhanget och lämnar tillbaka
        ett valt förslag, som hamnar i scenens anteckning — inte i manuset.
        Förslagen är vägar in, inte text att klistra in.
        """
        if self.project is None or not self.active_scene_id:
            self.status_bar.showMessage(_("exercise_needs_scene"), 5000)
            return
        dialog = ExerciseDialog(self.ai, self)
        self._exercise_dialog = dialog                 # hålls vid liv medan den visas
        dialog.ask_requested.connect(lambda kategori: self._ask_exercise(dialog, kategori))
        dialog.insert_requested.connect(self._insert_exercise)
        dialog.exec()
        self._exercise_dialog = None

    def _ask_exercise(self, dialog, category: str) -> None:
        """Skickar scenens sammanhang — markerad text om det finns, annars raden."""
        self._last_exercise_category = category
        markerat = self.editor.textCursor().selectedText().strip()
        if not markerat:
            markerat = self.editor.textCursor().block().text().strip()
        node = self.project.by_id(self.active_scene_id) if self.active_scene_id else None
        self.ai.suggest(
            category,
            selection=markerat,
            scene_note=(node.note if node else ""),
            chapter=(node.title if node else ""),
            lang=ai_name(i18n.get_language()),
        )

    def _insert_exercise(self, suggestion: str) -> None:
        """Förslaget hamnar där det hör hemma (R03.12, R03.16).

        En väg vidare hör till scenen — den hamnar i scenens anteckning, där
        författaren ser den igen. Ett **namn** hör till boken: det läggs i
        codexet, med noten som sammanfattning, så att personen finns där nästa
        gång man undrar vad hon heter.
        """
        if getattr(self, "_last_exercise_category", "") == "namn" and self.codex is not None:
            namn, _streck, noten = (suggestion or "").partition("—")
            namn = namn.strip(" -–—\t")
            try:
                self.codex.add_entity(namn, type="character", summary=noten.strip())
            except ValueError:
                self.status_bar.showMessage(_("name_empty"), 4000)
                return
            self.codex_panel.refresh()
            self.status_bar.showMessage(_("name_added", name=namn), 5000)
            return
        node = self.project.by_id(self.active_scene_id) if self.project and self.active_scene_id else None
        if node is None or not suggestion.strip():
            return
        self.project.set_meta(node.id, note=(node.note.strip() + "\n\n" + suggestion.strip()).strip())
        self._save_project_manifest()
        self.scene_inspector.set_scene(self.project, self.project.by_id(node.id))
        self.status_bar.showMessage(_("exercise_saved"), 5000)

    def open_find(self, with_replace: bool = False) -> None:
        """Sökrutan (R02.16). Modulen har funnits hela tiden — nu nås den.

        Icke-modal, för man ska kunna skriva vidare medan rutan står öppen; en
        modal ruta hade låst texten man söker i. Dokumentet hämtas genom en
        funktion i stället för att ges en gång, så rutan följer med när man
        byter scen eller vy.
        """
        from ui.find_replace_dialog import FindReplaceDialog

        if getattr(self, "find_dialog", None) is None:
            self.find_dialog = FindReplaceDialog(
                lambda: self.active_canvas.document() if self.active_canvas else None,
                self, with_replace=with_replace)
        else:
            self.find_dialog.with_replace = with_replace
        if with_replace:
            self.find_dialog.input_replace.setFocus()
        else:
            self.find_dialog.input_find.setFocus()
        self.find_dialog.input_find.selectAll()
        self.find_dialog.show()
        self.find_dialog.raise_()
        self.find_dialog.activateWindow()

    def run_autocorrect(self) -> bool:
        """Autokorrigering och typografi över scenen (R02.12).

        Allt sker i **ett** edit block: ett ångra-steg tar tillbaka hela
        körningen. Bara de områden som faktiskt skiljer skrivs om — ett helt
        stycke i taget hade plattat ut fet och kursiv stil i resten av det — och
        rättelserna samlas först och skrivs bakifrån, eftersom ett block blir
        ogiltigt så snart dokumentet ändras.
        """
        from core.autocorrect import Autocorrect, changed_spans
        from core.find_replace import find_all

        canvas = self.active_canvas
        if canvas is None:
            return False
        document = canvas.document()
        if document is None or not document.toPlainText().strip():
            self.status_bar.showMessage(_("autocorrect_none"), 5000)
            return False

        motor = Autocorrect()
        rattelser = []
        # Typografin per stycke: raka citattecken blir svenska och tre punkter
        # blir ett tecken. Bara själva tecknet byts, resten av stycket står stilla.
        for block in _all_blocks(document):
            rent = block.text()
            for del_start, del_slut, ny_text in changed_spans(rent, motor.apply_typography(rent)):
                rattelser.append((block.position() + del_start,
                                  block.position() + del_slut, ny_text))
        # Sedan orden, ett i taget, ur samma dokument.
        for traff in find_all(document, _WORD_PATTERN, regex=True):
            rattat = motor.apply(traff.text)
            if rattat != traff.text:
                rattelser.append((traff.start, traff.start + traff.length, rattat))

        markor = QTextCursor(document)
        markor.beginEditBlock()
        sista = None
        try:
            for start, slut, ny_text in sorted(rattelser, key=lambda r: r[0], reverse=True):
                if sista is not None and slut > sista:
                    continue          # ligger i ett område som redan skrivits
                markor.setPosition(start)
                markor.setPosition(slut, QTextCursor.MoveMode.KeepAnchor)
                markor.insertText(ny_text)
                sista = start
        finally:
            markor.endEditBlock()

        if rattelser:
            self.is_modified = True
            self.status_bar.showMessage(_("autocorrect_done", n=len(rattelser)), 6000)
            return True
        self.status_bar.showMessage(_("autocorrect_none"), 5000)
        return False

    def _open_review(self) -> None:
        """Vad som ändrats sedan senaste punkten (R02.1).

        Ändringarna räknas ur samma jämförelse som historiken visar: punkten mot
        texten på disk nu. Finns inget att granska sägs det i statusfältet i
        stället för att öppna en tom ruta.
        """
        if self.project is None or not self.active_scene_id:
            self.status_bar.showMessage(_("history_needs_scene"), 5000)
            return
        path = self.project.scene_path(self.active_scene_id)
        if path is None:
            self.status_bar.showMessage(_("history_needs_scene"), 5000)
            return
        self._flush_scene(quiet=True)
        punkter = self.project.snapshots().list(str(path))
        if not punkter:
            self.status_bar.showMessage(_("review_no_point"), 5000)
            return
        self._open_review_against(punkter[0].id)

    def _open_review_against(self, snapshot_id: str) -> None:
        """Granskar en vald punkt mot texten på disk nu (R02.3).

        Samma väg som för den senaste punkten, och originalet förblir orört:
        punkten läses, texten jämförs, och ingenting skrivs förrän granskningen
        är verkställd. Är det bara formateringen som skiljer sägs det i rutan i
        stället för att visas som ändringar (R02.15).
        """
        if self.project is None or not self.active_scene_id:
            self.status_bar.showMessage(_("history_needs_scene"), 5000)
            return
        path = self.project.scene_path(self.active_scene_id)
        if path is None:
            self.status_bar.showMessage(_("history_needs_scene"), 5000)
            return
        self._flush_scene(quiet=True)
        store = self.project.snapshots()
        try:
            punkt = store.get(snapshot_id)
            före = store.read(snapshot_id)
        except Exception:                                  # noqa: BLE001
            self.status_bar.showMessage(_("review_no_point"), 5000)   # punkten är borta
            return
        nu = self.project.read(self.active_scene_id)
        if not revisions.changes(före, nu) and not revisions.formatting_changes(före, nu):
            self.status_bar.showMessage(_("review_none"), 5000)
            return
        etikett = (f"{HistoryDialog._lokal_tid(punkt.created)} · "
                   f"{punkt.label or _('history_automatic')}")
        dialog = ReviewDialog(före, nu, etikett, self)
        dialog.apply_requested.connect(
            lambda beslut, f=före, n=nu: self._apply_review(f, n, beslut))
        dialog.exec()

    def _review_from_history(self, dialog, snapshot_id: str) -> None:
        """Stänger historiken och granskar punkten — en modal ruta i taget."""
        dialog.accept()
        self._open_review_against(snapshot_id)

    def _apply_review(self, before_html: str, after_html: str, decisions: list) -> None:
        """Skriver texten som granskningen beslutade — med en punkt före ingreppet."""
        node_id = self.active_scene_id
        if not node_id:
            return
        resultat = revisions.apply_changes(before_html, after_html, decisions)
        self.project.snapshot_scene(node_id, label=_("review_before"))
        self.project.write(node_id, resultat)
        self._show_scene_html(node_id, resultat)
        self.status_bar.showMessage(_("review_applied"), 5000)

    def _open_history(self) -> None:
        """Scenens punkter, skillnaden mot texten nu, och vägen tillbaka (R02.4).

        Öppnas historiken med osparade ändringar sparas de först: annars jämförs
        punkterna mot en text på disk som är äldre än den man ser.
        """
        if self.project is None or not self.active_scene_id:
            self.status_bar.showMessage(_("history_needs_scene"), 5000)
            return
        path = self.project.scene_path(self.active_scene_id)
        if path is None:
            self.status_bar.showMessage(_("history_needs_scene"), 5000)
            return
        self._flush_scene(quiet=True)
        dialog = HistoryDialog(self.project.snapshots(), str(path), self)
        dialog.restore_requested.connect(self._restore_snapshot)
        dialog.review_requested.connect(
            lambda pid, d=dialog: self._review_from_history(d, pid))
        dialog.exec()

    def _restore_snapshot(self, snapshot_id: str) -> None:
        """Lägger tillbaka punkten — och sparar texten som låg där först.

        En återställning är ett ingrepp i texten, och ska gå att ångra med samma
        knapp som allt annat i historiken.
        """
        node_id = self.active_scene_id
        if not node_id:
            return
        self._flush_scene(quiet=True)
        self.project.restore_snapshot(node_id, snapshot_id, label=_("history_before_restore"))
        self._show_scene_html(node_id, self.project.read(node_id))
        self.status_bar.showMessage(_("history_restored"), 5000)

    def _install_qt_translations(self) -> None:
        """Qts egna standardknappar på rätt språk (OK, Avbryt, Stäng).

        Appens egna texter översätts av i18n, men QDialogButtonBox hämtar sina
        knapptexter ur Qts egna översättningar — utan den här raden står det
        "Close" i en svensk dialog. Översättaren hålls i self, för en
        QTranslator som dör tas bort igen.
        """
        språk = i18n.current_lang
        app = QApplication.instance()
        if app is None:
            return
        if getattr(self, "_qt_translator", None) is not None:
            app.removeTranslator(self._qt_translator)
            self._qt_translator = None
        if språk == "sv":
            kataloger = [QtCore.QLibraryInfo.path(QtCore.QLibraryInfo.LibraryPath.TranslationsPath),
                         "/usr/share/qt6/translations"]
            for katalog in kataloger:
                if not katalog:
                    continue
                if self._qt_translator is None:
                    self._qt_translator = QtCore.QTranslator()
                if self._qt_translator.load("qtbase_sv", katalog) and app.installTranslator(self._qt_translator):
                    break

    def _open_overview(self) -> None:
        """Var boken står: framsteg, ogjort, trådar och anteckningar på ett ställe."""
        if self.project is None:
            self.status_bar.showMessage(_("instructions_needs_project"), 5000)
            return
        OverviewDialog(self.project, self.vault, self).exec()

    def _edit_ai_instructions(self) -> None:
        """Projektets egna instruktioner till AI:n (R03.18).

        En rad i projektet, inte i appen: ton, tempus, namn och allt annat som
        ska gälla för just den här boken. Instruktionerna läggs sist i
        systemprompten, närmast uppgiften — och ett tomt fält ändrar ingenting.
        """
        if self.project is None:
            self.status_bar.showMessage(_("instructions_needs_project"), 5000)
            return
        text, ok = QInputDialog.getMultiLineText(
            self, _("instructions_title"), _("instructions_label"),
            self.project.settings.get("ai_instructions", ""))
        if ok:
            self._set_ai_instructions(text)

    def _set_ai_instructions(self, text: str) -> None:
        self.project.settings["ai_instructions"] = (text or "").strip()
        self._save_project_manifest()
        self.status_bar.showMessage(_("instructions_saved"), 5000)

    def _save_project_manifest(self):
        if self.project is None:
            return
        try:
            self.project.save()
        except Exception as exc:                      # noqa: BLE001
            QMessageBox.critical(self, _("project_save_error_title"), str(exc))

    def _on_structure_changed(self):
        """Trädet ändrades: spara manifestet och kontrollera scenen i editorn.

        Tar man bort kapitlet som scenen ligger i står editorn annars kvar med en
        nod som inte finns, och nästa Spara skriver till en död scen. Här släpps
        den i stället, så det syns att texten är borta och inte går att spara.
        """
        self._save_project_manifest()
        if self.stack.currentIndex() == getattr(self, "_scrivenings_index", -1):
            # Läsvyn kan inte stå kvar över en ändrad struktur: dess stycken pekar
            # på scener som kan ha flyttat eller försvunnit.
            self._close_scrivenings()
            return
        if self.project is None or not self.active_scene_id:
            return
        try:
            self.project.by_id(self.active_scene_id)
            return
        except KeyError:
            pass
        self.active_scene_id = None
        self.current_filepath = None
        self.editor.document.clear()
        self.is_modified = False
        self.scene_inspector.set_scene(None, None)
        self._update_window_title()

    def show_events(self) -> None:
        """Händelsetabellen (2.23). Scenen som är öppen kopplas med ett klick.

        Ändringarna skrivs rakt i projektet, och `changed` sparar manifestet —
        samma väg som scenens metadata, så tavlan och trädet inte visar något
        annat än det som ligger på disk.
        """
        if self.project is None:
            return
        from ui.events_dialog import EventsDialog

        dialog = EventsDialog(self.project, current_scene_id=self.active_scene_id or "",
                              parent=self)
        dialog.changed.connect(self._save_project_manifest)
        dialog.exec()

    def _on_scene_meta_changed(self):
        """Panelen ändrade något i scenen: spara och visa det i vyerna."""
        if self.project is None:
            return
        self._save_project_manifest()
        self.binder.refresh(select_id=self.active_scene_id)
        # En kommentar som markerats löst skall tappa sin markering i texten med.
        self._refresh_comment_marks()

    def _open_node(self, node_id: str):
        """Öppna en nod i editorn — en scen, eller en researchanteckning."""
        if self.project is None:
            return
        self._close_scrivenings()
        self.binder.select_node(node_id)

    # ------------------------------------------------------------ kommentarerna

    def ask_new_comment(self) -> bool:
        """💬: kommentera det som är markerat i texten (R01.12)."""
        if self.project is None or not self.active_scene_id:
            return False
        quote = self.active_canvas.textCursor().selectedText().strip()
        if not quote:
            # Ingen modal ruta för det här: statusfältet säger vad som fattas.
            self.status_bar.showMessage(_("comment_no_selection"), 6000)
            return False
        text, accepted = QInputDialog.getMultiLineText(
            self, _("comment_new_title"), _("comment_new_label"))
        if not accepted:
            return False
        return self.add_comment(quote, text) is not None

    def ask_reply(self, node_id: str, comment_id: str) -> bool:
        """↳: ett svar i tråden under en kommentar (R02.2)."""
        if self.project is None:
            return False
        comment = self.project.comment(node_id, comment_id)
        if comment is None:
            return False
        text, accepted = QInputDialog.getMultiLineText(
            self, _("comment_reply_title"),
            _("comment_reply_label", quote=comment["quote"][:60]))
        if not accepted or not text.strip():
            return False
        if self.project.add_reply(node_id, comment_id, text) is None:
            return False
        if node_id == self.active_scene_id:
            self.scene_inspector.set_scene(self.project, self.project.by_id(node_id))
        self._save_project_manifest()
        return True

    def add_comment(self, quote: str, text: str):
        """Fäster kommentaren på citatet och markerar stället i texten."""
        if self.project is None or not self.active_scene_id:
            return None
        try:
            comment = self.project.add_comment(self.active_scene_id, quote, text)
        except ValueError:
            return None
        self._save_project_manifest()
        self.scene_inspector.set_scene(self.project, self.project.by_id(self.active_scene_id))
        self._refresh_comment_marks()
        return comment

    def goto_comment(self, node_id: str, comment_id: str) -> bool:
        """Gå till kommentarens textställe och markera det."""
        if self.project is None:
            return False
        comment = self.project.comment(node_id, comment_id)
        if comment is None:
            return False
        self._close_scrivenings()
        if node_id != self.active_scene_id:
            self.binder.select_node(node_id)
        cursor = self.editor.document.find(comment["quote"])
        if cursor.isNull():
            self.status_bar.showMessage(_("comment_quote_gone"), 6000)
            return False
        self.editor.setTextCursor(cursor)
        self.editor.canvas.ensureCursorVisible()
        self.active_canvas.setFocus()
        return True

    def goto_quote(self, node_id: str, quote: str, occurrence: int = 0) -> bool:
        """Gå till ett textställe i en scen och markera det.

        Förekomsten räknas inom scenen, så rätt träff av flera likadana träffas.
        Texten kan ha ändrats sedan fyndet gjordes: då säger statusfältet det i
        stället för att markera fel ord.
        """
        if self.project is None or not quote:
            return False
        self._close_scrivenings()
        if node_id != self.active_scene_id:
            self.binder.select_node(node_id)      # laddar scenen i editorn
        doc = self.editor.document
        cursor, position = None, 0
        for _steg in range(int(occurrence) + 1):
            found = doc.find(quote, position)
            if found.isNull():
                break
            cursor = found
            position = found.selectionEnd()
        if cursor is None or cursor.isNull():
            self.status_bar.showMessage(_("insight_quote_gone"), 6000)
            return False
        self.editor.setTextCursor(cursor)
        self.editor.canvas.ensureCursorVisible()
        self.active_canvas.setFocus()
        return True

    def _refresh_comment_marks(self) -> None:
        """Markerar kommentarernas ställen i texten — utan att röra dokumentet.

        Extra selections är vyens egen markering: den syns i editorn men hamnar
        aldrig i scenfilen, till skillnad från en char-format-markering. Priset är
        att markeringen hittar citatet först när den byggs om (vid inläsning,
        sparning och när kommentarerna ändras).
        """
        canvas = self.editor.canvas
        # Registret över noter och bildtexter följer scenen, även när ingen
        # kommentar finns och även utan projekt.
        self.sidebar.set_fields(self.editor.document.toPlainText(), self.field_labels())
        if self.project is None or not self.active_scene_id:
            canvas.setExtraSelections([])
            return
        doc = self.editor.document
        colour = self.palette().color(QPalette.ColorRole.Highlight)
        colour.setAlpha(70)
        selections = []
        for comment in self.project.comments_for(self.active_scene_id):
            if comment.get("resolved"):
                continue
            cursor = doc.find(comment["quote"])
            if cursor.isNull():
                continue
            markering = QTextEdit.ExtraSelection()
            markering.cursor = cursor
            markering.format.setBackground(colour)
            selections.append(markering)
        canvas.setExtraSelections(selections)

    def open_variants_dialog(self):
        """Manusvarianter: namngivna ordningar av scenerna (R01.14)."""
        from ui.variants_dialog import VariantsDialog

        if self.project is None:
            return None
        kalla = self._scrivenings_content()[0] or self.project.manuscript()
        dialog = VariantsDialog(self.project, nodes=kalla, parent=self)
        dialog.changed.connect(self._on_variant_changed)
        self._variants_dialog = dialog            # hålls vid liv medan den är öppen
        dialog.exec()
        self._variants_dialog = None
        return dialog

    def _on_variant_changed(self):
        """Varianten ändrades: spara, och visa den nya ordningen i trädet."""
        if self.project is None:
            return
        self._save_project_manifest()
        self.binder.refresh(select_id=self.active_scene_id)

    # ---------------------------------------------------------------- läsvyn

    def _scrivenings_content(self) -> tuple[list, str]:
        """Vilka scener läsvyn skall visa, och vad den skall kalla dem."""
        node_id = self.binder.current_node_id() or self.active_scene_id
        node = None
        if node_id:
            try:
                node = self.project.by_id(node_id)
            except KeyError:
                node = None
        if node is None:
            return self.project.manuscript(), self.project.title
        if node.is_writable:
            # En scen: läs hela dess kapitel, annars tappar vyn sammanhanget.
            if not node.parent:
                return [node], node.title
            kap = self.project.by_id(node.parent)
            return [n for n in self.project.walk(kap.id) if n.is_writable], kap.title
        return [n for n in self.project.walk(node.id) if n.is_writable], node.title

    def _toggle_scrivenings(self):
        if self.project is None:
            return
        if self.stack.currentIndex() == self._scrivenings_index:
            self._close_scrivenings()
            return
        nodes, heading = self._scrivenings_content()
        if not nodes:
            return
        self._show_scrivenings(nodes, heading)

    def _show_scrivenings(self, nodes, heading: str = "") -> None:
        """Visar noderna i läsvyn. Samma väg för hela manuset och för en samling."""
        self._flush_scene(quiet=True)          # scenen i editorn sparas först
        self.scrivenings.set_content(self.project, nodes, heading=heading)
        self.stack.setCurrentIndex(self._scrivenings_index)
        self._sync_reading_mode(True)
        self.scrivenings.pane.setFocus()
        self._update_stats()
        self._update_window_title()

    def _read_collection(self, collection_id: str) -> None:
        """Läsvyn över en samling: arbeta igenom scenerna i tur och ordning."""
        if self.project is None:
            return
        try:
            noder = self.project.select_collection(collection_id)
            namn = self.project.collection(collection_id).name
        except KeyError:
            return
        if not noder:
            self.status_bar.showMessage(_("collections_read_empty"), 4000)
            return
        self._show_scrivenings(noder, heading=namn)

    def _flush_scrivenings(self) -> int:
        """Skriver läsvyns text tillbaka till scenerna, en fil per scen.

        Bara de scener som ändrats skrivs, så en läsning utan ändringar rör inte
        en enda fil. Returnerar antalet skrivna scener.
        """
        if self.project is None or not self.scrivenings.shown_nodes():
            return 0
        changed = self.scrivenings.changed_content()
        for node_id, html in changed.items():
            try:
                self.project.write(node_id, html)
            except (KeyError, ValueError) as exc:
                print(f"[projekt] kunde inte skriva scenen: {exc}")
        if changed:
            self.scrivenings.mark_saved()
            self.binder.refresh_labels()
        return len(changed)

    def _close_scrivenings(self):
        if self.stack.currentIndex() != self._scrivenings_index:
            return
        self._flush_scrivenings()
        self._sync_reading_mode(False)
        self.show_editor_screen()
        if self.active_scene_id:
            self._load_scene(self.active_scene_id)
        self._update_stats()
        self._update_window_title()

    def _open_from_scrivenings(self, node_id: str):
        """Ett klick på en scenrubrik: tillbaka till editorn med den scenen."""
        self._close_scrivenings()
        self.binder.select_node(node_id)

    def file_new(self):
        if self.stack.currentIndex() == 1 and not self._maybe_save_changes():
            return
        self.editor.document.clear()
        # Projektläget och ett enstaka dokument är ömsesidigt uteslutande: att
        # hålla båda i luften samtidigt gör Spara tvetydigt.
        self._deactivate_project()
        self.current_filepath = None
        self.is_modified = False
        self.notes_panel.set_current_document("")
        self.notes_panel.set_current_file(None)
        self.show_editor_screen()

    def file_open(self):
        if self.stack.currentIndex() == 1 and not self._maybe_save_changes():
            return
        fpath, _filter = QFileDialog.getOpenFileName(
            self,
            _("menu_file_open"),
            "",
            "Documents (*.docx *.md *.markdown *.html *.htm *.txt);;Word Documents (*.docx);;Markdown (*.md);;HTML Files (*.html *.htm);;Plain Text (*.txt);;All Files (*.*)"
        )
        if fpath:
            self.open_recent_file(fpath)

    def open_recent_file(self, filepath):
        if self.stack.currentIndex() == 1 and not self._maybe_save_changes():
            return
        if not os.path.exists(filepath):
            QMessageBox.warning(self, _("menu_file_open"), f"{_('start_file_not_found')}:\n{filepath}")
            self.config.remove_recent_file(filepath)
            self._update_recent_menu()
            self.start_screen.refresh_recents()
            return
        self._deactivate_project()
        try:
            DocumentManager.load_file(filepath, self.editor.document)
            self.current_filepath = filepath
            self.is_modified = False
            self.config.add_recent_file(filepath)
            self._update_recent_menu()
            self.notes_panel.set_current_document(self._current_note_title())
            self.notes_panel.set_current_file(filepath)
            self.show_editor_screen()
        except Exception as e:
            QMessageBox.critical(self, "Error Opening File", str(e))

    def file_save(self):
        # I ett projekt betyder Spara "skriv scenen och manifestet" — ingen
        # filväljare, ingen exportväg: scenens HTML sparas som den är.
        if self.project is not None:
            if not self._flush_scene():
                return False
            self.project.save()
            self.is_modified = False
            self._update_window_title()
            return True
        if self.current_filepath:
            try:
                self._save_document(self.current_filepath)
                self.is_modified = False
                self._update_window_title()
                return True
            except Exception as e:
                QMessageBox.critical(self, "Error Saving File", str(e))
                return False
        else:
            return self.file_save_as()

    def file_save_as(self):
        fpath, selected_filter = QFileDialog.getSaveFileName(
            self,
            _("menu_file_save_as"),
            "",
            "Word Document (*.docx);;Markdown (*.md);;HTML Document (*.html);;Plain Text (*.txt)"
        )
        if fpath:
            fpath = self._ensure_extension(fpath, selected_filter, ".docx")
            try:
                self._save_document(fpath)
                self.current_filepath = fpath
                self.is_modified = False
                self._update_window_title()
                self.config.add_recent_file(fpath)
                self._update_recent_menu()
                return True
            except Exception as e:
                QMessageBox.critical(self, "Error Saving File", str(e))
        return False

    def file_print(self):
        if self.stack.currentIndex() == 0:
            return
        doc = self.editor.document
        if doc is None:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle(_("menu_file_print"))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            DocumentManager.print_document_to_printer(doc, printer, page_settings=self.page_settings)

    def file_print_preview(self):
        if self.stack.currentIndex() == 0:
            return
        doc = self.editor.document
        if doc is None:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle(_("menu_file_print_preview"))
        preview.setMinimumSize(800, 600)
        preview.resize(1050, 850)
        preview.paintRequested.connect(lambda p: DocumentManager.print_document_to_printer(doc, p, page_settings=self.page_settings))
        preview.exec()

    def export_pdf(self):
        """Hela boken som PDF. Urval, delning och profiler görs i kompileringen."""
        doc = self.editor.document
        if doc is None:
            return
        fpath, selected_filter = QFileDialog.getSaveFileName(
            self,
            _("menu_file_export_pdf"),
            "",
            "PDF Document (*.pdf)"
        )
        if fpath:
            fpath = self._ensure_extension(fpath, "*.pdf", ".pdf")
            try:
                self._save_document(fpath, doc)
                QMessageBox.information(self, _("export_success_title"), _("export_success_text", path=fpath))
            except Exception as e:
                QMessageBox.critical(self, _("export_error_title"), str(e))

    def open_template_dialog(self):
        dlg = TemplateDialog(self.theme_mgr, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            t_id = dlg.get_selected_template_id()
            if t_id:
                if self.stack.currentIndex() == 1 and not self._maybe_save_changes():
                    return
                html = get_template_html(t_id, lang=i18n.get_language())
                doc = self.editor.document
                if doc is not None:
                    doc.setHtml(html)
                self.current_filepath = None
                self.is_modified = False
                self.notes_panel.set_current_document("")
                self.notes_panel.set_current_file(None)
                self.show_editor_screen()
                self.status_bar.showMessage(_("template_loaded"), 5000)

    def open_insert_image_dialog(self):
        if self.stack.currentIndex() != 1:
            self.show_editor_screen()
        dlg = ImageDialog(self.theme_mgr, parent=self)
        dlg.image_ready.connect(lambda path, w, a, c: self.editor.canvas.insert_image(path, w, a, c))
        dlg.exec()

    def open_insert_chart_dialog(self):
        if self.stack.currentIndex() != 1:
            self.show_editor_screen()
        dlg = ChartDialog(self.theme_mgr, self)
        dlg.chart_ready.connect(
            lambda img, mono, a: self.editor.canvas.insert_chart(img, a, mono_image=mono)
        )
        dlg.exec()

    def open_publish_dialog(self) -> None:
        """Publicerarprofilen: kanalens siffror och vad de gör med boken (R05.1).

        Sidantalet hämtas ur det öppna manuset när det går — gutter, ryggbredd
        och omslag hänger alla på det, så det är där siffrorna kommer ifrån. Att
        använda profilen skriver in trim och marginaler i sidinställningarna, på
        samma väg som sidinställningsrutan.
        """
        from ui.publish_dialog import PublishDialog

        dlg = PublishDialog(self._page_count() or 300, self.page_settings, self)
        dlg.settings_applied.connect(self._on_page_settings_applied)
        dlg.settings_applied.connect(
            lambda ny: self.status_bar.showMessage(
                _("publish_applied", gutter=f"{ny.get('margin_right_mm', 0):g}".replace(".", ","),
                  outer=f"{ny.get('margin_left_mm', 0):g}".replace(".", ",")), 8000))
        dlg.exec()

    def open_page_setup_dialog(self):
        dlg = PageSetupDialog(self.page_settings, self.theme_mgr, self)
        dlg.settings_applied.connect(self._on_page_settings_applied)
        dlg.exec()

    def _on_page_settings_applied(self, new_settings: dict):
        """Nya sidinställningar, **sammanslagna** med de gamla (R05.5).

        En profil (eller en ruta) som bara känner till några av nycklarna får
        inte tappa resten: `clean_print` och de andra valen hör till samma
        inställning och ska överleva att man byter tryckmått. Det nya värdet
        vinner där båda finns — annars vore sammanslagningen en bugg.
        """
        self.page_settings = {**DEFAULT_PAGE_SETTINGS, **self.page_settings, **new_settings}
        self.config.set("page_settings", self.page_settings)
        self.editor.set_page_settings(self.page_settings)
        if self.project is not None:
            # Måtten bor i projektet (det öppna dokumentet), configen behåller
            # dem som standard för nästa nya projekt.
            self.project.settings["page_settings"] = dict(self.page_settings)
            self.project.save()
        self.status_bar.showMessage(_("pagesetup_applied"), 4000)

    def hold_together_bad_paragraphs(self) -> int:
        """Håller ihop de stycken som har en ensam rad över ett sidbrott (5.16).

        Ett ångringssteg, inte flera: markören öppnar en redigeringsgrupp och
        stänger den efter sig. Texten rörs inte — bara formen, så författaren
        kan ångra och bestämma själv.
        """
        doc = self.editor.document if self.editor is not None else None
        if doc is None:
            return 0
        from core import prepress

        fynd = prepress.widows_and_orphans(doc, self.page_settings)
        if not fynd:
            return 0
        nummer = {f["block"] for f in fynd}
        markor = QTextCursor(doc)
        markor.beginEditBlock()
        try:
            block = doc.begin()
            i = 0
            while block.isValid():
                if i in nummer:
                    markor.setPosition(block.position())
                    fmt = block.blockFormat()
                    # Märket är vårt eget (se core/pagination): Qts
                    # setNonBreakableLines stänger av radbrytningen också, och då
                    # blev ett långt stycke en enda rad utanför pappret.
                    from core import pagination
                    pagination.mark_keep_together(fmt)
                    markor.mergeBlockFormat(fmt)
                block = block.next()
                i += 1
        finally:
            markor.endEditBlock()
        if hasattr(self, "status_bar"):
            self.status_bar.showMessage(_("prepress_held_message", count=str(len(nummer))), 4000)
        return len(nummer)

    def export_pdfx(self) -> str:
        """En tryckfärdig PDF/X-1a:2003: Qt ritar den, Ghostscript gör den tryckbar.

        Stegen syns med flit: först en vanlig PDF genom appens egen exportväg,
        sedan konverteringen. Misslyckas den andra finns den första kvar och
        felet sägs rakt ut — en fil som ser färdig ut men inte är det är värre
        än ingen fil.
        """
        from core import prepress

        if self.editor is None or self.editor.document is None:
            return ""
        if not prepress.available():
            QMessageBox.warning(self, _("prepress_pdfx"), _("prepress_no_ghostscript"))
            return ""
        fpath, _valt = QFileDialog.getSaveFileName(
            self, _("prepress_pdfx"), "", "PDF (*.pdf)")
        if not fpath:
            return ""
        if not fpath.lower().endswith(".pdf"):
            fpath += ".pdf"
        try:
            self._save_document(fpath)
            mål = fpath[:-4] + "-tryck.pdf"
            prepress.to_pdfx(fpath, mål, title=self.book_metadata().get("title", ""))
        except Exception as fel:                      # noqa: BLE001 — felet visas för användaren
            QMessageBox.critical(self, _("export_error_title"), str(fel))
            return ""
        if not prepress.has_pdfx_marker(mål):
            QMessageBox.critical(self, _("prepress_pdfx"), _("prepress_pdfx_unverified"))
            return ""
        teckensnitt = prepress.embedded_fonts(mål)
        icke = [namn for namn, inbäddat in teckensnitt if not inbäddat]
        if icke:
            QMessageBox.warning(self, _("prepress_pdfx"),
                                _("prepress_fonts_missing", fonts=", ".join(icke)))
        QMessageBox.information(self, _("export_success_title"),
                                _("prepress_pdfx_done", path=mål))
        return mål

    def open_ask_panel(self) -> None:
        """Öppnar fliken Fråga manuset och sätter markören i frågefältet.

        Panelen fälls ut om den är infälld: ett menyval som inte syns har inte
        hänt, och användaren skall inte behöva leta efter den.
        """
        if self.project is None:
            return
        self.sidebar.setVisible(True)
        self.config.set("show_ai_sidebar", True)
        self.sidebar.tabs.setCurrentWidget(self.ask)
        self.ask.set_scene(self.active_scene_id or "")
        self.ask.input_question.setFocus()

    def open_compile_dialog(self) -> None:
        """Kompilera det som är öppet, eller markeringen (5.15).

        Fönstret gör jobbet: valen, profilen och filerna. Här kontrolleras bara
        att det finns något att kompilera — en editor utan dokument skall säga
        det, inte öppna ett fönster som inte kan göra något.
        """
        if self.project is None:
            return
        if self.editor is None or self.editor.document is None:
            QMessageBox.information(self, _("compile_title"), _("compile_empty"))
            return
        from ui.compile_dialog import CompileDialog

        dlg = CompileDialog(self.project, self.editor, self)
        dlg.exec()

    def export_docx(self):
        fpath, selected_filter = QFileDialog.getSaveFileName(
            self,
            _("menu_file_export_docx"),
            "",
            "Word Document (*.docx)"
        )
        if fpath:
            fpath = self._ensure_extension(fpath, "*.docx", ".docx")
            try:
                self._save_document(fpath)
                QMessageBox.information(self, _("export_success_title"), _("export_success_text", path=fpath))
            except Exception as e:
                QMessageBox.critical(self, _("export_error_title"), str(e))

    def _page_count(self) -> int:
        """Sidantalet ur det öppna manuset — gutter, rygg och omslag hänger på det."""
        canvas = self.editor.canvas if self.editor else None
        return len(getattr(canvas, "pages", None) or [])

    def _release_warnings(self) -> list:
        """Vad en kanal skulle klaga på, sagt innan filen skickas (R05.10)."""
        from core import publishing

        inst = self.page_settings or {}
        varningar = []
        if inst.get("trim"):
            varningar = [_("warn_" + kod) for kod in publishing.warnings(
                inst.get("trim"), self._page_count(), inst.get("paper", "white"),
                bool(inst.get("bleed")), inst.get("channel", "kdp"))]
        else:
            varningar.append(_("release_no_profile"))
        uppgifter = self.book_metadata()
        if not str(uppgifter.get("description") or "").strip():
            varningar.append(_("release_no_blurb"))
        if not str(uppgifter.get("identifier") or "").strip():
            varningar.append(_("release_no_isbn"))
        if self._page_count() % 2:
            varningar.append(_("release_odd_pages", pages=str(self._page_count())))
        return varningar

    def book_metadata(self) -> dict:
        """Bokens metadata: ur projektet när det finns, annars ur filen (R05.4).

        Titeln, författaren och ISBN hör till **boken**, inte till scenen — en
        EPUB kan inte heta "Scen tolv". Sammalunda blir baksidestexten bokens
        beskrivning: den text en läsare läser först.
        """
        if self.project is not None:
            inst = self.project.settings
            titel = self.project.title
        else:
            inst = {}
            titel = os.path.splitext(os.path.basename(self.current_filepath or ""))[0]
        return {
            "title": titel or _("untitled_document"),
            "author": inst.get("author", ""),
            "publisher": inst.get("publisher", ""),
            "language": (inst.get("language") or i18n.get_language()),
            "identifier": inst.get("isbn", ""),
            "description": inst.get("blurb", ""),
        }

    def export_epub_book(self):
        """EPUB 3 — boken som fil, med projektets metadata (R05.2, R05.4, R05.8).

        Exporten har funnits i `core/epub.py` sedan 0b men nåtts aldrig från
        menyn. Metadata, kapitelindelning, tillgänglighetsmärkning och TOC sköts
        av modulen; här hämtas bara bokens uppgifter och filen skrivs.
        """
        from core.epub import export_epub

        fpath, _valt = QFileDialog.getSaveFileName(
            self, _("menu_file_export_epub"), "", "EPUB (*.epub)")
        if not fpath:
            return
        fpath = self._ensure_extension(fpath, "*.epub", ".epub")
        try:
            export_epub(fpath, self.editor.document, self.book_metadata())
            QMessageBox.information(self, _("export_success_title"),
                                    _("export_success_text", path=fpath))
        except Exception as e:                            # noqa: BLE001
            QMessageBox.critical(self, _("export_error_title"), str(e))

    def draw_cover_sheet(self, path: str | None = None):
        """Omslagsarket: hela arket i kanalens mått, med ryggen utmärkt (R05.6).

        Det som behövs för ett omslag är inte en bild utan ett *ark* i rätt
        storlek med rätt ryggbredd — den enda siffran som ändras varje gång
        sidantalet eller pappret gör det. Formgivningen gör författaren; det här
        är arket den läggs på.
        """
        from core.cover import cover_layout, draw_cover

        layout = cover_layout(*self._cover_args())
        if layout is None:
            QMessageBox.information(
                self, _("cover_no_trim_title"),
                _("cover_no_trim_text") if not (self.page_settings or {}).get("trim")
                else _("cover_no_sizes"))
            return
        if not path:
            path, _valt = QFileDialog.getSaveFileName(
                self, _("menu_file_cover"), "", "PDF (*.pdf)")
        if not path:
            return
        path = self._ensure_extension(path, "*.pdf", ".pdf")
        uppgifter = self.book_metadata()
        svar = draw_cover(path, layout, title=uppgifter.get("title", ""),
                          author=uppgifter.get("author", ""),
                          blurb=uppgifter.get("description", ""),
                          language=uppgifter.get("language", "sv"))
        QMessageBox.information(
            self, _("cover_title"),
            _("cover_done_text", path=path,
              width=f"{svar['sheet'][0]:g}".replace(".", ","),
              height=f"{svar['sheet'][1]:g}".replace(".", ","),
              spine=f"{svar['spine_mm']:g}".replace(".", ",")))

    def _cover_args(self) -> tuple:
        """Trimm, sidantal, papper, blöd och kanal — som omslaget räknas ur."""
        inst = self.page_settings or {}
        return (inst.get("trim") or "", self._page_count(), inst.get("paper", "white"),
                bool(inst.get("bleed")), inst.get("channel", "kdp"))

    def open_release_folder(self):
        """Öppna mappen från det senaste släppet, i datorns filhanterare (R05.9)."""
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices

        if not self.last_release_folder or not os.path.isdir(self.last_release_folder):
            QMessageBox.information(self, _("release_done_title"), _("release_no_folder"))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.last_release_folder))

    def check_epub_with_epubcheck(self, path: str | None = None):
        """EPUBCheck som val: kontrollen mitt i menyn, med besked om den saknas (R05.8).

        Ett eget menyval och inte ett krav i exporten: EPUBCheck är ett
        Java-program, och Java finns inte på varje dator. Går det inte att köra
        ska boken ändå kunna skrivas — men beskedet ska säga exakt vad som
        fattas och var man lägger det.
        """
        from core.epubcheck import SEARCH_PATHS, java_available, validate

        if not path:
            path, _valt = QFileDialog.getOpenFileName(
                self, _("menu_file_epubcheck"), "", "EPUB (*.epub)")
        if not path:
            return
        svar = validate(path)
        if svar.get("reason") == "no_epubcheck":
            QMessageBox.information(
                self, _("epubcheck_missing_title"),
                _("epubcheck_missing_text",
                  java=_("epubcheck_java_yes") if svar.get("java") else _("epubcheck_java_no"),
                  paths="\n".join("• " + str(p) for p in SEARCH_PATHS)))
            return
        if not svar.get("ran"):
            QMessageBox.warning(self, _("epubcheck_result_title"),
                                _("epubcheck_run_failed", error="; ".join(svar.get("messages", []))))
            return
        if svar["clean"]:
            QMessageBox.information(self, _("epubcheck_result_title"), _("epubcheck_clean"))
            return
        rader = [_("epubcheck_counts", errors=str(svar["errors"]), warnings=str(svar["warnings"]))]
        rader += ["", *svar["messages"]]
        QMessageBox.information(self, _("epubcheck_result_title"), "\n".join(rader))

    def release_book(self, folder: str | None = None):
        """Släpp boken: EPUB, tryck-PDF och rapport i en mapp (R05.9, R05.10).

        En utgivning är inte en fil utan ett paket. EPUB:en är boken man läser,
        PDF:en är boken man trycker, och rapporten säger vad som ligger i mappen,
        när det byggdes och vad kanalen kommer att klaga på — med checksummor, så
        att frågan "är det här samma fil som i går?" går att svara på.
        """
        from core.epub import export_epub
        from core.project import slugify
        from core.release import build_release

        if not folder:
            folder = QFileDialog.getExistingDirectory(self, _("release_choose_folder"))
        if not folder:
            return
        uppgifter = self.book_metadata()
        namn = slugify(uppgifter.get("title") or "") or "boken"
        epub_sökväg = os.path.join(folder, f"{namn}.epub")
        pdf_sökväg = os.path.join(folder, f"{namn}-tryck.pdf")
        varningar = self._release_warnings()

        try:
            export_epub(epub_sökväg, self.editor.document, uppgifter)
        except Exception as e:                                # noqa: BLE001
            varningar.append(_("release_epub_failed", error=str(e)))
        if not self._render_release_pdf(pdf_sökväg):
            varningar.append(_("release_pdf_failed"))

        # EPUBCheck körs när den finns — och säger till när den inte gjorde det,
        # så att "inte kontrollerad" står i rapporten i stället för att tigas bort.
        from core.epubcheck import validate as _validera

        kontroll = _validera(epub_sökväg)
        if not kontroll.get("ran"):
            varningar.append(_("release_unchecked", reason=kontroll.get("reason", "?")))
        elif kontroll.get("errors"):
            varningar.append(_("release_check_errors", errors=str(kontroll["errors"])))
            varningar += kontroll["messages"]

        # Omslagsarket hör till paketet när en tryckprofil är vald — det är arket
        # formgivaren ska lägga omslaget på, i kanalens exakta mått.
        omslag_sökväg = None
        from core.cover import cover_layout, draw_cover

        layout = cover_layout(*self._cover_args())
        if layout is not None:
            omslag_sökväg = os.path.join(folder, f"{namn}-omslag.pdf")
            try:
                draw_cover(omslag_sökväg, layout, title=uppgifter.get("title", ""),
                           author=uppgifter.get("author", ""),
                           blurb=uppgifter.get("description", ""),
                           language=uppgifter.get("language", "sv"))
            except Exception as e:                            # noqa: BLE001
                omslag_sökväg = None
                varningar.append(_("release_cover_failed", error=str(e)))

        rapport = build_release(
            folder, [epub_sökväg, pdf_sökväg, omslag_sökväg], uppgifter, varningar)
        self.last_release_folder = folder
        text = _("release_done_text", folder=folder, count=str(len(rapport["files"])))
        if rapport["missing"]:
            text += "\n" + _("release_missing_text", files=", ".join(rapport["missing"]))
        if varningar:
            text += "\n\n" + _("release_warnings_lead") + "\n" + "\n".join(
                "• " + rad for rad in varningar[:6])
        QMessageBox.information(self, _("release_done_title"), text)

    def _render_release_pdf(self, path: str) -> bool:
        """Tryck-PDF:en — boken som den ska se ut på papper, utan redigeringsmärken."""
        from PyQt6.QtPrintSupport import QPrinter

        from core.doc_manager import DocumentManager

        skrivare = QPrinter(QPrinter.PrinterMode.HighResolution)
        skrivare.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        skrivare.setOutputFileName(path)
        try:
            DocumentManager.print_document_to_printer(
                self.editor.document, skrivare, {**self.page_settings, "clean_print": True})
        except Exception:                                     # noqa: BLE001
            return False
        return os.path.exists(path) and os.path.getsize(path) > 0

    def export_markdown(self):
        fpath, selected_filter = QFileDialog.getSaveFileName(
            self,
            _("menu_file_export_md"),
            "",
            "Markdown Document (*.md)"
        )
        if fpath:
            fpath = self._ensure_extension(fpath, "*.md", ".md")
            try:
                self._save_document(fpath)
                QMessageBox.information(self, _("export_success_title"), _("export_success_text", path=fpath))
            except Exception as e:
                QMessageBox.critical(self, _("export_error_title"), str(e))

    def export_html(self):
        fpath, selected_filter = QFileDialog.getSaveFileName(
            self,
            _("menu_file_export_html"),
            "",
            "HTML Document (*.html)"
        )
        if fpath:
            fpath = self._ensure_extension(fpath, "*.html", ".html")
            try:
                self._save_document(fpath)
                QMessageBox.information(self, _("export_success_title"), _("export_success_text", path=fpath))
            except Exception as e:
                QMessageBox.critical(self, _("export_error_title"), str(e))

    def spellchecker(self):
        """Kontrollen. Adressen och språket kommer ur inställningarna (R02.13).

        Den publika tjänsten används om inget annat är inställt; en egen server
        ställs in med `spellcheck_endpoint`. Texten lämnar datorn, så adressen
        står i panelen — det ska man veta om.
        """
        from core.spellcheck import DEFAULT_ENDPOINT, SpellChecker

        if getattr(self, "_checker", None) is None:
            self._checker = SpellChecker(
                language=self.config.get("spellcheck_language", "sv-SE") or "sv-SE",
                endpoint=self.config.get("spellcheck_endpoint", DEFAULT_ENDPOINT) or DEFAULT_ENDPOINT)
        return self._checker

    def run_spellcheck(self) -> bool:
        """Stavning och grammatik över scenen (R02.13).

        Ett språk per avsnitt: stycken med egen språkmärkning skickas för sig,
        resten med scenens språk. I den vanliga boken — ett språk hela vägen —
        blir det **ett** anrop. En trasig eller frånvarande tjänst säger vad som
        gick fel i stället för att tiga.
        """
        from core import richtext

        canvas = self.active_canvas
        if canvas is None:
            return False
        document = canvas.document()
        if document is None or not document.toPlainText().strip():
            self.status_bar.showMessage(_("spell_none"), 5000)
            return False

        grund = self.spellchecker().language.split("-")[0]
        # Stycke för stycke är den enkla, exakta vägen: varje träff får sin
        # position i dokumentet direkt ur stycket den kom ifrån.
        stycken: list[tuple[str, int, str]] = []
        block = document.begin()
        while block.isValid():
            rent = block.text()
            if rent.strip():
                stycken.append((richtext.lang_of(block.blockFormat()) or grund,
                                block.position(), rent))
            block = block.next()
        if not stycken:
            self.status_bar.showMessage(_("spell_none"), 5000)
            return False

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            träffar = []
            for språk, start, rent in stycken:
                for issue in self.spellchecker().check(rent, språk):
                    träffar.append((start + issue.offset, issue))
        finally:
            QApplication.restoreOverrideCursor()

        förpackade = []
        for position, issue in träffar:
            # Texten träffen gäller läses ur dokumentet, så raden i panelen visar
            # vad som är fel och var — tjänsten svarar bara med position.
            område = QTextCursor(document)
            område.setPosition(position)
            område.setPosition(min(position + issue.length, document.characterCount() - 1),
                               QTextCursor.MoveMode.KeepAnchor)
            issue.text = område.selectedText()
            issue.offset = position
            förpackade.append(issue)

        self.sidebar.set_language_issues(förpackade, self.spellchecker().endpoint,
                                         self.spellchecker().available())
        if not self.spellchecker().available():
            self.status_bar.showMessage(
                _("spell_unavailable", error=self.spellchecker().last_error or ""), 8000)
        elif len(förpackade) == 1:
            self.status_bar.showMessage(_("spell_done_one"), 6000)
        else:
            self.status_bar.showMessage(_("spell_done", n=len(förpackade)), 6000)
        return True

    def show_language_issue(self, start: int, length: int) -> bool:
        """Markerar träffen i texten, så att man ser vad tjänsten menar."""
        canvas = self.active_canvas
        if canvas is None:
            return False
        cursor = QTextCursor(canvas.document())
        cursor.setPosition(int(start))
        cursor.setPosition(min(int(start) + int(length), canvas.document().characterCount() - 1),
                           QTextCursor.MoveMode.KeepAnchor)
        canvas.setTextCursor(cursor)
        canvas.setFocus()
        return True

    def apply_language_issue(self, start: int, length: int, replacement: str) -> bool:
        """Tar tjänstens första förslag — ett steg i ångra-historiken."""
        canvas = self.active_canvas
        if canvas is None:
            return False
        cursor = QTextCursor(canvas.document())
        cursor.setPosition(int(start))
        cursor.setPosition(min(int(start) + int(length), canvas.document().characterCount() - 1),
                           QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(replacement)
        self.is_modified = True
        self.status_bar.showMessage(_("spell_applied", value=replacement), 4000)
        return True

    def field_labels(self) -> dict:
        """Orden fälten visas med — core/fields.py är språkoberoende."""
        return {"note": _("field_name_note"), "figure": _("field_name_figure"),
                "table": _("field_name_table"),
                "ref_see": _("field_ref_see"), "notes_heading": _("field_notes_heading"),
                "note_ref": '<sup><a href="#not{n}">{n}</a></sup>'}

    def _fields_available(self) -> bool:
        return self.active_canvas is not None and self.active_canvas.document() is not None

    def insert_field(self, kind: str) -> bool:
        """Infogar en fältmarkering vid markören (R02.5, R02.8).

        Markeringen är vanlig text i scenen — den syns, den går att flytta och
        den överlever allt som händer med filen. Numret räknas fram, inte skrivs.
        """
        if not self._fields_available():
            return False
        namn = _("field_" + kind)
        text, ok = QInputDialog.getText(self, _("field_dialog_title", kind=namn),
                                        _("field_dialog_prompt", kind=namn))
        if not ok or not text.strip():
            return False
        cursor = self.active_canvas.textCursor()
        cursor.insertText(f"[{kind}: {' '.join(text.split())}]")
        self.is_modified = True
        self._refresh_comment_marks()
        self.status_bar.showMessage(_("field_inserted", kind=namn), 4000)
        return True

    def insert_reference(self) -> bool:
        """En hänvisning till en rubrik i dokumentet (R02.6).

        Rubrikerna visas med sina kapitelnummer, så man väljer rätt kapitel i
        stället för att skriva dess text och hoppas att den stämmer.
        """
        if not self._fields_available():
            return False
        rubriker, nummer = self.headings_and_numbers()
        if not rubriker:
            self.status_bar.showMessage(_("toc_none"), 5000)
            return False
        val = [f"{n}. {r}" for n, r in zip(nummer, rubriker)]
        valt, ok = QInputDialog.getItem(self, _("field_ref_title"), _("field_ref_prompt"), val, 0, False)
        if not ok or not valt:
            return False
        text = valt.split(". ", 1)[-1].strip()
        cursor = self.active_canvas.textCursor()
        cursor.insertText(f"[ref: {text}]")
        self.is_modified = True
        self.status_bar.showMessage(_("field_inserted", kind=_("field_ref")), 4000)
        return True

    def headings_and_numbers(self, document=None) -> tuple:
        """Rubrikerna i dokumentet och deras kapitelnummer (R02.7)."""
        from core.fields import number_headings

        doc = document
        if doc is None and self.active_canvas is not None:
            doc = self.active_canvas.document()
        if doc is None:
            return [], []
        rubriker, nivaer = [], []
        block = doc.begin()
        while block.isValid():
            if block.blockFormat().headingLevel() and block.text().strip():
                rubriker.append(block.text().strip())
                nivaer.append(block.blockFormat().headingLevel())
            block = block.next()
        return rubriker, number_headings(nivaer)

    def insert_toc(self) -> bool:
        """Infogar eller uppdaterar innehållsförteckningen (R02.7).

        Innehållet står mellan ``[innehåll]`` och ``[/innehåll]``, som appens
        andra markeringar: skriver man om ett kapitel trycker man en gång till
        och listan är uppdaterad, i stället för att redigera den för hand.
        """
        rubriker, nummer = self.headings_and_numbers()
        if not rubriker:
            self.status_bar.showMessage(_("toc_none"), 5000)
            return False
        rader = "\n".join(f"{n}. {r}" for n, r in zip(nummer, rubriker))
        document = self.active_canvas.document()
        cursor = document.find(_TOC_OPEN)
        if not cursor.isNull():
            slut = document.find(_TOC_CLOSE, cursor.selectionEnd())
            if not slut.isNull():
                # Uppdatera på plats: allt mellan markeringarna byts ut.
                cursor.setPosition(cursor.selectionEnd())
                cursor.setPosition(slut.selectionStart(), QTextCursor.MoveMode.KeepAnchor)
                cursor.insertText("\n" + rader + "\n")
                self.is_modified = True
                self.status_bar.showMessage(_("toc_updated"), 4000)
                return True
        cursor = self.active_canvas.textCursor()
        cursor.insertText(f"{_TOC_OPEN}\n{rader}\n{_TOC_CLOSE}")
        self.is_modified = True
        self.status_bar.showMessage(_("toc_inserted"), 4000)
        return True

    def _resolved_for_export(self, document):
        """Löser upp fälten inför export: en fotnot ska bli en not i filen.

        En kopia byggs bara när det finns något att lösa upp — annars går samma
        dokument vidare. Markeringen är text, så den här är det enda stället
        fälten behöver kännas vid för att filen ska bli riktig.
        """
        from core import fields as fields_module

        text = document.toHtml()
        if "[" not in text:
            return document
        rubriker, nummer = self.headings_and_numbers(document)
        kopia = QTextDocument()
        kopia.setHtml(fields_module.resolve(text, rubriker, nummer, self.field_labels()))
        return kopia

    def _save_document(self, filepath, text_document=None):
        """Sparar eller exporterar med appens aktuella sidinställningar.

        Utan page_settings faller save_file tillbaka på DEFAULT_PAGE_SETTINGS,
        och då fick samma dokument olika rening och geometri beroende på väg —
        DOCX-exporten tappade dem medan PDF-exporten hade dem.
        """
        document = text_document if text_document is not None else self.editor.document
        DocumentManager.save_file(
            filepath,
            self._resolved_for_export(document),
            page_settings=self.page_settings,
        )

    def _maybe_save_changes(self):
        if not self.is_modified:
            return True
        doc_name = os.path.basename(self.current_filepath) if self.current_filepath else _("untitled_document")
        ret = QMessageBox.question(
            self,
            _("dlg_save_changes_title"),
            _("dlg_save_changes_text", name=doc_name),
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
        )
        if ret == QMessageBox.StandardButton.Save:
            return self.file_save()
        elif ret == QMessageBox.StandardButton.Discard:
            return True
        return False

    def start_pause_timer_if_enabled(self) -> None:
        """Sätter igång klockan om påminnelsen var på sist (R03.7)."""
        if self.config.get("pause_reminder", False):
            self.act_view_pause.setChecked(True)
            self.pause_timer.start()

    def closeEvent(self, event):
        self.writing_log.close_log()
        if self.project is not None:
            self._flush_scene(quiet=True)
            try:
                self.project.save()
            except Exception as exc:                  # noqa: BLE001
                print(f"[project] kunde inte spara manifestet: {exc}")
            event.accept()
            return
        if self.stack.currentIndex() == 0:
            event.accept()
            return
        if self._maybe_save_changes():
            event.accept()
        else:
            event.ignore()

    # ------------------------------------------------------- valv & anteckningar

    def _current_note_title(self):
        """Namnet valvpanelen slår upp backlinks med.

        I ett projekt heter filen '0001-scen-1', vilket ingen skriver i sina
        anteckningar — där används scenens rubrik i stället, så [[Scen 1]] i
        valvet hittar sin scen.
        """
        if self.project is not None and self.active_scene_id:
            try:
                return self.project.by_id(self.active_scene_id).title
            except KeyError:
                return ""
        if not self.current_filepath:
            return ""
        return os.path.splitext(os.path.basename(self.current_filepath))[0]

    def _refresh_link_titles(self):
        """Uppdaterar förslagen som dyker upp när man skriver [[ i editorn."""
        self.editor.canvas.set_link_titles([n.title for n in self.vault.notes])

    def _on_vault_changed(self, folder):
        self.vault = Vault(folder)
        self.vault.scan()
        self.notes_panel.set_vault(self.vault)
        self.config.set("vault_root", folder)
        self._refresh_link_titles()
        self.status_bar.showMessage(_("notes_vault_switched", root=folder), 6000)

    def _show_vault_panel(self):
        self.sidebar.setVisible(True)
        self.config.set("show_ai_sidebar", True)
        idx = self.sidebar.tabs.indexOf(self.notes_panel)
        if idx >= 0:
            self.sidebar.tabs.setCurrentIndex(idx)

    def _focus_vault_search(self):
        self._show_vault_panel()
        self.notes_panel.input_search.setFocus()
        self.notes_panel.input_search.selectAll()

    def _rescan_vault(self):
        n = self.vault.scan()
        self._refresh_link_titles()
        self.notes_panel.refresh()
        self.status_bar.showMessage(
            _("notes_rescan_done", n=n, root=self.vault.root), 6000)

    def _new_note(self):
        title, ok = QInputDialog.getText(self, _("menu_notes_new"), _("notes_new_prompt"))
        if not ok or not title.strip():
            return
        note = self.vault.create_note(title.strip())
        if note is None:
            QMessageBox.warning(self, _("menu_notes"), _("notes_create_failed"))
            return
        self._refresh_link_titles()
        self.notes_panel.refresh()
        self.open_recent_file(note.path)

    def _insert_wikilink_dialog(self):
        titles = [n.title for n in self.vault.notes]
        if not titles:
            QMessageBox.information(self, _("menu_notes"), _("notes_no_vault"))
            return
        title, ok = QInputDialog.getItem(
            self, _("menu_ai_insert_link"), _("notes_link_pick"), titles, 0, False)
        if ok and title:
            self._insert_text_at_cursor(f"[[{title}]]")

    def _open_wikilink(self, target):
        """Ctrl+klick på [[länk]]: öppna anteckningen, eller erbjud att skapa den."""
        note = self.vault.get(target)
        if note is not None:
            self.open_recent_file(note.path)
            return
        answer = QMessageBox.question(
            self, _("notes_create_from_link"),
            _("notes_create_confirm", title=target),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            created = self.vault.create_note(target, content=f"# {target}\n\n")
            if created is not None:
                self._refresh_link_titles()
                self.notes_panel.refresh()
                self.open_recent_file(created.path)

    def _open_graph(self):
        self.vault.scan()
        self.graph_dialog = GraphDialog(self.vault, self.theme_mgr, self)
        self.graph_dialog.open_file_requested.connect(self.open_recent_file)
        self.graph_dialog.create_note_requested.connect(self._create_note_from_link)
        self.graph_dialog.exec()

    def _create_note_from_link(self, target):
        created = self.vault.create_note(target, content=f"# {target}\n\n")
        if created is not None:
            self._refresh_link_titles()
            self.notes_panel.refresh()
            if self.graph_dialog is not None and self.graph_dialog.isVisible():
                self.graph_dialog.canvas.rebuild()
                self.graph_dialog._refresh()

    # ------------------------------------------------------------ AI i dokumentet

    def _insert_text_at_cursor(self, text):
        if not text:
            return
        if self.stack.currentIndex() != 1:
            self.show_editor_screen()
        cursor = self.editor.textCursor()
        cursor.insertText(text)
        self.editor.setTextCursor(cursor)
        self.editor.canvas.setFocus()

    def _open_research(self):
        if self.stack.currentIndex() != 1:
            return
        self.research_dialog = ResearchDialog(
            self.config, self.theme_mgr,
            document_text=self.editor.document.toPlainText(),
            lang=i18n.get_language(), vault=self.vault, parent=self,
        )
        if self.research_dialog.exec() == QDialog.DialogCode.Accepted:
            text = self.research_dialog.inserted_text()
            if text.strip():
                self._insert_text_at_cursor("\n\n" + text.strip() + "\n")
                self._refresh_link_titles()
                self.notes_panel.refresh()

    def _open_ghostwriter(self):
        if self.stack.currentIndex() != 1:
            return
        self.ghost_dialog = GhostwriterDialog(
            self.config, self.theme_mgr,
            document_text=self.editor.document.toPlainText(),
            lang=i18n.get_language(), vault=self.vault, parent=self,
        )
        self.ghost_dialog.insert_requested.connect(self._on_ghost_insert)
        self.ghost_dialog.exec()

    def _on_ghost_insert(self, text):
        cursor = self.editor.textCursor()
        prefix = "" if cursor.atBlockStart() else "\n\n"
        cursor.insertText(prefix + text.strip())
        self.editor.setTextCursor(cursor)
        self.editor.canvas.setFocus()

    def _open_generate_paragraph(self):
        """Skapa stycken utifrån en instruktion — öppnar ghostwritern i bygg-ut-läget."""
        if self.stack.currentIndex() != 1:
            return
        self.ghost_dialog = GhostwriterDialog(
            self.config, self.theme_mgr,
            document_text=self.editor.document.toPlainText(),
            lang=i18n.get_language(), vault=self.vault, parent=self,
            preset_mode="expand",
        )
        self.ghost_dialog.insert_requested.connect(self._on_ghost_insert)
        self.ghost_dialog.exec()

    # ------------------------------------------------- markeringar och kodgranskning

    def _format_directives(self):
        """Gör [kodblock]- och [citat]-markeringar i dokumentet till riktiga block."""
        converted = self.editor.canvas.format_directives()
        text = self.editor.document.toPlainText()
        open_markers = directives.unclosed(text)
        typos = directives.suspicious_lines(text)

        if converted:
            self.status_bar.showMessage(_("fmt_converted", n=converted), 7000)
        elif not open_markers and not typos:
            self.status_bar.showMessage(_("fmt_nothing"), 5000)

        problems = [_("fmt_unclosed", line=ln, kind=kind) for ln, kind in open_markers]
        problems += [_("fmt_typo", line=ln, raw=raw) for ln, raw in typos]
        if problems:
            QMessageBox.warning(self, _("fmt_title"),
                                _("fmt_problems") + "\n\n" + "\n".join(problems[:8]))
        if converted:
            self._update_stats()

    def _code_block_at_cursor(self):
        blocks = richtext.code_blocks(self.editor.document)
        if not blocks:
            return None
        current = self.editor.textCursor().blockNumber()
        for b in blocks:
            if b["first_block"] <= current <= b["last_block"]:
                return b
        if len(blocks) == 1:
            return blocks[0]
        labels = [f"{i + 1}: {b['code'].splitlines()[0][:44]}" for i, b in enumerate(blocks)]
        choice, ok = QInputDialog.getItem(self, _("code_title"), _("code_pick_block"),
                                          labels, 0, False)
        if not ok:
            return None
        return blocks[labels.index(choice)]

    def _open_code_analysis(self):
        if self.stack.currentIndex() != 1:
            return
        block = self._code_block_at_cursor()
        if block is None:
            QMessageBox.information(self, _("code_title"), _("code_no_blocks"))
            return
        self.code_dialog = CodeDialog(
            self.config, self.theme_mgr,
            code=block["code"], lang=block.get("lang", ""),
            doc_context=self.editor.document.toPlainText(),
            lang_ui=i18n.get_language(), parent=self,
        )
        self.code_dialog.replace_requested.connect(
            lambda code, b=block: self._replace_code_block(b, code))
        self.code_dialog.insert_requested.connect(
            lambda code, b=block: self._insert_code_after(b, code))
        self.code_dialog.exec()

    def _replace_code_block(self, block, code):
        """Sätter in den formaterade koden i stället för den gamla."""
        lang = block.get("lang") or directives.detect_language(code)
        richtext.replace_blocks(self.editor.document, block["first_block"],
                                block["last_block"], code, self.theme_mgr.current, lang)
        self.status_bar.showMessage(_("code_replaced"), 6000)
        self._update_stats()

    def _insert_code_after(self, block, code):
        """Lägger den formaterade koden som ett nytt kodblock under det gamla."""
        doc = self.editor.document
        last = doc.findBlockByNumber(block["last_block"])
        cursor = QTextCursor(doc)
        if last.isValid():
            cursor.setPosition(last.position() + last.length() - 1)

        body = code.rstrip("\n")
        cursor.beginEditBlock()
        try:
            # En tom rad emellan, så att det nya blocket blir ett eget block
            cursor.insertBlock()
            cursor.insertBlock()
            start_code = cursor.position()
            cursor.insertText(body)
            end_code = cursor.position()
        finally:
            cursor.endEditBlock()

        colors = self.theme_mgr.current

        # Separatorraderna ärver blockformatet från koden de skapas efter, och
        # hade alltså kodroll. Töm den — annars räknas de som kod och båda
        # kodblocken smälter ihop till ett. Blocken räknas ut explicit: att
        # utgå från en teckenposition hamnar inuti det gamla blocket, och då
        # tappar dess sista rad sin roll.
        first_sep = block["last_block"] + 1
        code_block = doc.findBlock(start_code)
        last_sep = code_block.blockNumber() - 1
        if last_sep >= first_sep:
            richtext.apply_role_to_blocks(doc, first_sep, last_sep, "", colors)

        lang = block.get("lang") or directives.detect_language(body)
        sel = QTextCursor(doc)
        sel.setPosition(start_code)
        sel.setPosition(end_code, QTextCursor.MoveMode.KeepAnchor)
        richtext.apply_role(sel, richtext.ROLE_CODE, colors, lang)
        self.status_bar.showMessage(_("code_inserted"), 6000)
        self._update_stats()

    def retranslate_ui(self):
        self._install_qt_translations()
        self.lbl_ai_status.setText("✨ " + _("status_ai_ready"))
        self.lbl_dict_status.setText("🎙️ " + _("status_dictation_idle"))
        self._update_lang_toggle_btn()
        self._update_lang_menu_actions()

        self.menu_file.setTitle(_("menu_file"))
        self.act_start_page.setText(_("menu_file_start_page"))
        self.act_new.setText(_("menu_file_new"))
        self.act_new_template.setText("🎨 " + _("menu_file_new_template"))
        self.act_instructions.setText("📌 " + _("menu_file_instructions"))
        self.act_overview.setText("📊 " + _("menu_file_overview"))
        self.act_history.setText("🕘 " + _("menu_file_history"))
        self.act_review.setText("📝 " + _("menu_file_review"))
        self.act_open.setText(_("menu_file_open"))
        self.menu_recent.setTitle(_("menu_file_recent"))
        self.act_save.setText(_("menu_file_save"))
        self.act_save_as.setText(_("menu_file_save_as"))
        self.act_page_setup.setText("⚙️ " + _("menu_file_page_setup"))
        self.act_print.setText(_("menu_file_print"))
        self.act_print_prev.setText(_("menu_file_print_preview"))
        self.act_exp_pdf.setText(_("menu_file_export_pdf"))
        self.act_exp_docx.setText(_("menu_file_export_docx"))
        self.act_exp_md.setText(_("menu_file_export_md"))
        self.act_exp_html.setText(_("menu_file_export_html"))
        self.act_exit.setText(_("menu_file_exit"))

        self.menu_edit.setTitle(_("menu_edit"))
        self.act_undo.setText(_("menu_edit_undo"))
        self.act_redo.setText(_("menu_edit_redo"))
        self.act_cut.setText(_("menu_edit_cut"))
        self.act_copy.setText(_("menu_edit_copy"))
        self.act_paste.setText(_("menu_edit_paste"))
        self.act_select_all.setText(_("menu_edit_select_all"))
        self.act_find.setText(_("menu_edit_find"))
        self.act_find_replace.setText(_("menu_edit_find_replace"))
        self.act_autocorrect.setText(_("menu_edit_autocorrect"))
        self.act_spellcheck.setText(_("menu_edit_spellcheck"))

        self.menu_view.setTitle(_("menu_view"))
        self.act_view_sidebar.setText(_("menu_view_ai_sidebar"))
        self.act_view_focus.setText(_("menu_view_focus_mode"))
        self.act_view_grid.setText(_("menu_view_grid"))
        self.act_view_readability.setText(_("menu_view_readability"))
        self.act_exercise.setText("🧩 " + _("menu_ai_exercise"))
        self.act_zoom_in.setText(_("menu_view_zoom_in"))
        self.act_zoom_out.setText(_("menu_view_zoom_out"))
        self.act_zoom_reset.setText(_("menu_view_zoom_reset"))
        self.menu_language.setTitle("🌐 " + _("menu_view_language"))
        # Språknamnen är språkets eget namn och översätts inte — menyn byggs om
        # när filerna ändras, så raden fyller på nya språk också.
        for kod, _namn in i18n.get_available_languages():
            if kod not in getattr(self, "act_lang", {}):
                act = QAction(native(kod), self)
                act.setCheckable(True)
                act.triggered.connect(lambda _checked=False, k=kod: self._set_language(k))
                self.menu_language.addAction(act)
                self.act_lang[kod] = act
            self.act_lang[kod].setText(native(kod))

        self.menu_insert.setTitle(_("menu_insert"))
        self.act_ins_table.setText("📊 " + _("menu_insert_table"))
        self.act_ins_image.setText("🖼️ " + _("menu_insert_image"))
        self.act_ins_chart.setText("📈 " + _("menu_insert_chart"))
        self.act_ins_divider.setText("─ " + _("menu_insert_horizontal_rule"))
        self.act_ins_page_break.setText("📄 " + _("menu_insert_page_break"))
        self.act_ins_template.setText("🎨 " + _("menu_insert_template"))
        self.menu_ins_callout.setTitle("💡 " + _("tb_callout"))
        self.act_callout_info.setText(_("tb_callout_info"))
        self.act_callout_tip.setText(_("tb_callout_tip"))
        self.act_callout_warning.setText(_("tb_callout_warning"))
        self.act_callout_quote.setText(_("tb_callout_quote"))

        self.menu_format.setTitle(_("menu_format"))
        self.act_fmt_bold.setText(_("menu_format_bold"))
        self.act_fmt_italic.setText(_("menu_format_italic"))
        self.act_fmt_underline.setText(_("menu_format_underline"))
        self.act_fmt_strike.setText(_("menu_format_strikethrough"))
        self.act_fmt_sub.setText(_("tb_subscript"))
        self.act_fmt_super.setText(_("tb_superscript"))
        self.act_fmt_clear.setText(_("menu_format_clear"))
        self.act_gfonts.setText("🌐 " + _("menu_format_google_fonts"))

        self.menu_ai.setTitle(_("menu_ai"))
        self.act_inline_ai.setText(_("menu_ai_inline"))
        self.act_review_ai.setText(_("menu_ai_review"))
        self.act_dictation.setText(_("menu_ai_dictation"))
        self.act_settings.setText(_("menu_ai_settings"))
        self.act_research.setText("🔎 " + _("menu_ai_research"))
        self.act_ghost.setText("👻 " + _("menu_ai_ghostwriter"))
        self.act_ins_link.setText("🔗 " + _("menu_ai_insert_link"))
        self.act_gen_para.setText("✎ " + _("menu_ai_paragraph"))
        self.act_code.setText("⌨ " + _("menu_ai_code"))
        self.act_fmt_directives.setText("⌗ " + _("menu_format_directives"))
        for act, key in ((self.act_fld_note, "menu_format_note"), (self.act_fld_figure, "menu_format_figure"),
                         (self.act_fld_table, "menu_format_table"), (self.act_fld_ref, "menu_format_ref"),
                         (self.act_fld_toc, "menu_format_toc")):
            act.setText(_(key))

        self.menu_notes.setTitle(_("menu_notes"))
        self.act_notes_new.setText("➕ " + _("menu_notes_new"))
        self.act_notes_search.setText("🔍 " + _("menu_notes_search"))
        self.act_notes_graph.setText("🕸 " + _("menu_notes_graph"))
        self.act_notes_rescan.setText("⟳ " + _("menu_notes_rescan"))
        self.act_notes_panel.setText("🗂 " + _("menu_notes_panel"))

        self.menu_help.setTitle(_("menu_help"))
        self.act_about.setText(_("menu_help_about"))

        self._update_recent_menu()
        self._update_window_title()

    def apply_theme(self):
        self.theme_mgr.apply_theme_to_app()
