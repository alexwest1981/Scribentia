import re
import math
import uuid
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QScrollArea, QFrame, QMenu,
    QApplication, QLabel, QSizePolicy, QListWidget, QListWidgetItem, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRectF, QPointF, QByteArray, QBuffer, QIODevice, QUrl
from PyQt6.QtGui import QLinearGradient, QFontMetricsF
from PyQt6.QtGui import (
    QTextDocument, QTextCursor, QTextCharFormat, QTextBlockFormat,
    QTextTableFormat, QTextTableCellFormat, QTextFrameFormat, QTextLength,
    QFont, QColor, QPainter, QAction, QKeySequence, QPalette,
    QSyntaxHighlighter, QImage, QPixmap, QPen, QBrush, QTextFormat
)
from core.i18n import _
from core.document_stats import DocumentStats, sentence_ranges
from core.vault import WIKILINK_RE, split_link_target, slugify
from core import directives, richtext, print_style
from core.doc_manager import DEFAULT_PAGE_SETTINGS
from ui.chrome import set_tracking

# Papprets mått och ark-kolumnen bor i ui/paged_paper.py; namnen importeras hit
# så att den som redan läser dem härifrån (och proven) fortsätter att hitta dem.
from ui.paged_paper import (                     # noqa: E402
    CANVAS_PAGE_PX, PAGE_HEIGHT_PX, PAGE_MARGIN_BOTTOM, PAGE_MARGIN_TOP,
    PAGE_MARGIN_X, PAGE_WIDTH_PX, PagedPaper,
)


class WikiLinkHighlighter(QSyntaxHighlighter):
    """Färgar [[wikilänkar]] så att de syns som länkar och inte som vanlig text.

    Länkar vars mål finns i valvet får temats accentfärg. Länkar till något
    som ännu inte finns får varningston och streckad understrykning — samma
    signal som Obsidian ger. Highlightern ritar bara ovanpå dokumentet och
    rör inte texten, så sparning och export påverkas inte.
    """

    def __init__(self, document):
        super().__init__(document)
        self.known = set()
        self.color_resolved = QColor("#2d7ff9")
        self.color_missing = QColor("#d97706")
        self._build_formats()

    def set_known_targets(self, titles):
        """Vilka länkmål som faktiskt har en anteckning."""
        self.known = {slugify(t) for t in (titles or []) if t}
        self.rehighlight()

    def set_colors(self, resolved, missing):
        self.color_resolved = QColor(resolved)
        self.color_missing = QColor(missing)
        self._build_formats()
        self.rehighlight()

    def _build_formats(self):
        self.fmt_ok = QTextCharFormat()
        self.fmt_ok.setForeground(self.color_resolved)
        self.fmt_ok.setFontUnderline(True)
        self.fmt_ok.setUnderlineColor(self.color_resolved)

        self.fmt_missing = QTextCharFormat()
        self.fmt_missing.setForeground(self.color_missing)
        self.fmt_missing.setFontUnderline(True)
        self.fmt_missing.setUnderlineStyle(QTextCharFormat.UnderlineStyle.DashUnderline)
        self.fmt_missing.setUnderlineColor(self.color_missing)

    def highlightBlock(self, text):
        for m in WIKILINK_RE.finditer(text):
            target, _heading, _alias = split_link_target(m.group(1))
            fmt = self.fmt_ok if slugify(target) in self.known else self.fmt_missing
            self.setFormat(m.start(), m.end() - m.start(), fmt)


class ReadabilityHighlighter(QSyntaxHighlighter):
    """Markerar tunga meningar med en prickad understrykning.

    Målar över texten utan att röra den, precis som wikilänkarna: markeringen
    hamnar aldrig i scenfilen. Formen (prickad linje) bär betydelsen, färgen
    bara förstärker — en färgblind författare ser den också. Gränsen är orden
    per mening, samma sak som driver LIX.
    """

    def __init__(self, document, max_words: int = 20):
        super().__init__(document)
        self.max_words = max_words
        self.active = False
        self.colour = QColor("#c2410c")          # uppmärksamhet, inte temats accent

    def set_active(self, on: bool) -> None:
        self.active = bool(on)
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        if not self.active or not text.strip():
            return
        fmt = QTextCharFormat()
        fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.DotLine)
        fmt.setUnderlineColor(self.colour)
        for start, längd in sentence_ranges(text, self.max_words):
            self.setFormat(start, längd, fmt)


class DocumentCanvas(QTextEdit):
    cursor_format_changed = pyqtSignal()
    magic_ai_requested = pyqtSignal(str, QPoint) # (selected_text, global_pos)
    wikilink_activated = pyqtSignal(str)         # [[mål]] följt med Ctrl+klick
    directives_converted = pyqtSignal(int)       # antal [kodblock]/[citat] som blev block

    # En sidas höjd *inuti* pappret. Sidmärkena ritas vid denna höjd, så den
    # måste vara papprets innermått — annars hamnar märkena mitt i texten.
    PAGE_HEIGHT_PX = CANVAS_PAGE_PX

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(True)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Document page settings
        doc = self.document()
        doc.setDocumentMargin(36) # ~25mm page padding

        # Sidlayout och sidnummer
        self.page_settings = DEFAULT_PAGE_SETTINGS.copy()

        # Wikilänkar: färgning av länkar + förslag när man skriver [[
        self.highlighter = WikiLinkHighlighter(self.document())
        self.readability = ReadabilityHighlighter(self.document())
        self._link_titles = []
        self._colors = {}          # temafärger för kod- och citatblock
        self._completer_start = 0
        self.completer = QListWidget(self)
        self.completer.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.completer.setVisible(False)
        self.completer.itemClicked.connect(lambda item: self._insert_link(item.text()))
        self.verticalScrollBar().valueChanged.connect(self._hide_completer)

        # Cursor change listener to update toolbar
        self.cursorPositionChanged.connect(self._on_cursor_changed)

    def _on_cursor_changed(self):
        self.cursor_format_changed.emit()

    def set_readability_marks(self, on: bool) -> None:
        """Slår på markeringen av tunga meningar (R03.17)."""
        self.readability.set_active(on)

    def readability_marks(self) -> bool:
        return self.readability.active

    def set_page_settings(self, settings: dict):
        if settings:
            self.page_settings.update(settings)
            vp = self.viewport()
            if vp is not None:
                vp.update()

    def keyPressEvent(self, event):
        # Trigger inline Magic AI with Ctrl+K
        if event.key() == Qt.Key.Key_K and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            cursor = self.textCursor()
            selected = cursor.selectedText()
            rect = self.cursorRect()
            global_pos = self.mapToGlobal(rect.bottomLeft())
            self.magic_ai_requested.emit(selected, global_pos)
            event.accept()
            return

        # Infoga sidbrytning med Ctrl+Enter
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.insert_page_break()
            event.accept()
            return

        # Wikilänk-förslag: navigering med piltangenter, val med Enter/Tab
        if self.completer.isVisible():
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                row = self.completer.currentRow()
                row += 1 if event.key() == Qt.Key.Key_Down else -1
                self.completer.setCurrentRow(max(0, min(row, self.completer.count() - 1)))
                event.accept()
                return
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                item = self.completer.currentItem()
                if item is not None:
                    self._insert_link(item.text())
                    event.accept()
                    return
            if event.key() == Qt.Key.Key_Escape:
                self._hide_completer()
                event.accept()
                return

        super().keyPressEvent(event)
        self._maybe_show_completer()
        # Stängs en markering med ] ska den bli ett riktigt block direkt
        if event.text() == "]":
            self._maybe_convert_directive()

    # ---------------------------------------------------------------- Drag & Drop / Urklipp
    def dragEnterEvent(self, e):
        if e is not None:
            mime = e.mimeData()
            if mime is not None and (mime.hasUrls() or mime.hasImage() or mime.hasText()):
                e.acceptProposedAction()
            else:
                super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e is not None:
            mime = e.mimeData()
            if mime is not None and (mime.hasUrls() or mime.hasImage() or mime.hasText()):
                e.acceptProposedAction()
            else:
                super().dragMoveEvent(e)

    def dropEvent(self, e):
        if e is None:
            return
        mime = e.mimeData()
        if mime is not None and mime.hasUrls():
            for url in mime.urls():
                fpath = url.toLocalFile()
                if fpath and fpath.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".bmp")):
                    self.insert_image(fpath)
                    e.acceptProposedAction()
                    return
        elif mime is not None and mime.hasImage():
            img = mime.imageData()
            if isinstance(img, QImage) and not img.isNull():
                self.insert_image(img)
                e.acceptProposedAction()
                return
        super().dropEvent(e)

    def insertFromMimeData(self, source):
        if source is None:
            return
        # 1. Klistra in bild från urklipp
        if source.hasImage():
            img = source.imageData()
            if isinstance(img, QImage) and not img.isNull():
                self.insert_image(img)
                return
            elif isinstance(img, QPixmap) and not img.isNull():
                self.insert_image(img.toImage())
                return

        # 2. Klistra in tabulär data (TSV från Excel, Google Sheets eller LibreOffice Calc)
        if source.hasText():
            text = source.text()
            if "\t" in text and "\n" in text:
                lines = [ln for ln in text.splitlines() if ln.strip()]
                if len(lines) >= 2 and all("\t" in ln for ln in lines[:min(3, len(lines))]):
                    if self._try_insert_tsv_table(lines):
                        return

        super().insertFromMimeData(source)

    def _try_insert_tsv_table(self, lines: list[str]) -> bool:
        """Konverterar inklistrad TSV-data till en formaterad tabell."""
        matrix = [line.split("\t") for line in lines]
        num_rows = len(matrix)
        num_cols = max(len(row) for row in matrix)
        if num_rows < 1 or num_cols < 1:
            return False

        cursor = self.textCursor()
        cursor.beginEditBlock()
        try:
            table_fmt = QTextTableFormat()
            table_fmt.setBorder(1)
            table_fmt.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
            table_fmt.setBorderBrush(QBrush(QColor(print_style.PAPER_RULE)))
            table_fmt.setCellPadding(8)
            table_fmt.setCellSpacing(0)
            table_fmt.setWidth(QTextLength(QTextLength.Type.PercentageLength, 100))

            table = cursor.insertTable(num_rows, num_cols, table_fmt)
            if table is None:
                return False
            
            # Header-styling på första raden
            header_fmt = QTextTableCellFormat()
            header_fmt.setBackground(QBrush(QColor(print_style.PAPER_TINT)))

            for r, row in enumerate(matrix):
                for c, val in enumerate(row):
                    if c < num_cols:
                        cell = table.cellAt(r, c)
                        if cell is not None and cell.isValid():
                            if r == 0:
                                cell.setFormat(header_fmt)
                            cell_cursor = cell.firstCursorPosition()
                            cell_cursor.insertText(val.strip())
        finally:
            cursor.endEditBlock()
        self.setTextCursor(cursor)
        return True

    # ---------------------------------------------------------------- Infogning av media
    def insert_image(self, filepath_or_qimage, width_px: int = 480, align: str = "center", caption: str = ""):
        """Infogar en bild i dokumentet med angiven bredd, justering och bildtext."""
        if isinstance(filepath_or_qimage, str):
            qimg = QImage(filepath_or_qimage)
            if qimg.isNull():
                return
        elif isinstance(filepath_or_qimage, QImage):
            qimg = filepath_or_qimage
        elif isinstance(filepath_or_qimage, QPixmap):
            qimg = filepath_or_qimage.toImage()
        else:
            return

        disp_w = min(qimg.width(), width_px) if width_px else min(qimg.width(), 680)

        # Koda till base64 för direkt inbäddning i HTML och dokumentresurser
        ba = QByteArray()
        buff = QBuffer(ba)
        buff.open(QIODevice.OpenModeFlag.WriteOnly)
        qimg.save(buff, "PNG")
        b64_str = ba.toBase64().data().decode("utf-8")
        data_url = f"data:image/png;base64,{b64_str}"

        res_id = f"qrc:///images/{uuid.uuid4().hex[:12]}.png"
        doc = self.document()
        if doc is not None:
            doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(res_id), qimg)

        cursor = self.textCursor()
        cursor.beginEditBlock()
        try:
            caption_html = (
                f'<br/><span style="font-size: 10pt; color: {print_style.PAPER_MUTED};'
                f' font-style: italic;">{caption}</span>'
            ) if caption else ""
            html_chunk = f'<p style="text-align: {align}; margin: 14px 0;"><img src="{data_url}" width="{disp_w}" />{caption_html}</p><p></p>'
            cursor.insertHtml(html_chunk)
        finally:
            cursor.endEditBlock()
        self.setTextCursor(cursor)

    def insert_chart(self, qimage: QImage, align: str = "center",
                     mono_image: QImage | None = None):
        """Infogar ett genererat diagram och märker det som vårt eget.

        Märkningen gör att en export kan byta till gråskaleversionen även om
        man valde en färgpalett på skärmen — diagrammet är programmets utdata,
        inte användarens innehåll. ``mono_image`` är samma diagram ritat i
        gråskala; utan den nyanseras bilden ned vid export i stället.
        """
        self.insert_image(qimage, width_px=680, align=align)
        self._mark_last_image_as_chart(mono_image)

    def _mark_last_image_as_chart(self, mono_image: QImage | None = None) -> bool:
        """Ger den senast infogade bilden före markören diagrammärkningen."""
        doc = self.document()
        if doc is None:
            return False

        mono_name = ""
        if mono_image is not None and not mono_image.isNull():
            mono_name = f"scribentia-diagram-mono://{uuid.uuid4().hex}"
            doc.addResource(QTextDocument.ResourceType.ImageResource,
                            QUrl(mono_name), mono_image)
        pos = self.textCursor().position()
        block = doc.findBlock(pos)
        while block.isValid():
            frags = []
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    frags.append(frag)
                it += 1
            for frag in reversed(frags):
                if not frag.charFormat().isImageFormat() or frag.position() > pos:
                    continue
                fmt = print_style.mark_as_generated_chart(
                    QTextCharFormat(frag.charFormat()), mono_name
                )
                sel = QTextCursor(doc)
                sel.setPosition(frag.position())
                sel.setPosition(frag.position() + frag.length(),
                                QTextCursor.MoveMode.KeepAnchor)
                sel.setCharFormat(fmt)
                return True
            block = block.previous()
        return False

    def insert_page_break(self):
        """Infogar en visuell och utskriftsmässig sidbrytning."""
        cursor = self.textCursor()
        cursor.beginEditBlock()
        try:
            cursor.insertBlock()
            bfmt = QTextBlockFormat()
            bfmt.setPageBreakPolicy(QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore)
            cursor.setBlockFormat(bfmt)
            cursor.insertHtml('<p style="page-break-before: always; margin-top: 16px;"><br/></p>')
        finally:
            cursor.endEditBlock()
        self.setTextCursor(cursor)

    # ------------------------------------------------------------- skrollning
    def scrollContentsBy(self, dx, dy):
        """Editorn står alltid på sitt arks första rad.

        Qt skrollar själv för att visa markören (också när markören sätts
        programmatiskt), vilket skulle flytta texten inne i arket. Varje sådan
        skrollning rättas direkt av pappret i stället.
        """
        super().scrollContentsBy(dx, dy)
        papper = self.parentWidget()
        if getattr(self, "_rattar_skroll", False) or not hasattr(papper, "_sync_scroll"):
            return
        self._rattar_skroll = True
        try:
            papper._sync_scroll()
        finally:
            self._rattar_skroll = False

    def wheelEvent(self, e):
        """Hjulet över texten ska skrolla pappret, inte det enskilda arket."""
        papper = self.parentWidget()
        if hasattr(papper, "wheelEvent"):
            papper.wheelEvent(e)
            return
        super().wheelEvent(e)

    def ensureCursorVisible(self):
        """Ytan skrollar inte själv — arken äger skrollningen, så be pappret."""
        papper = self.parentWidget()
        if hasattr(papper, "ensure_cursor_visible"):
            papper.ensure_cursor_visible()
            return
        super().ensureCursorVisible()

    # ---------------------------------------------------------------- markeringar

    def set_block_colors(self, colors: dict):
        """Temafärger för kod- och citatblock."""
        self._colors = dict(colors or {})

    def format_directives(self) -> int:
        """Gör om [kodblock] och [citat] till riktiga block. Returnerar antalet."""
        found = directives.parse(self.toPlainText())
        if not found:
            return 0
        converted = 0
        for d in sorted(found, key=lambda x: -x.start_offset):
            if self._convert_directive(d):
                converted += 1
        if converted:
            self.directives_converted.emit(converted)
        return converted

    def _convert_directive(self, d) -> bool:
        """Byter ut en markering mot sitt innehåll och ger det rätt roll."""
        doc = self.document()
        last = doc.characterCount() - 1

        sel = QTextCursor(doc)
        sel.setPosition(min(d.start_offset, last))
        sel.setPosition(min(d.end_offset, last), QTextCursor.MoveMode.KeepAnchor)
        sel.beginEditBlock()
        try:
            sel.removeSelectedText()
            sel.insertText(d.body)
        finally:
            sel.endEditBlock()

        role = richtext.ROLE_CODE if d.kind == "code" else richtext.ROLE_QUOTE
        lang = d.lang
        if role == richtext.ROLE_CODE and not lang:
            lang = directives.detect_language(d.body)

        end = min(d.start_offset + len(d.body), doc.characterCount() - 1)
        sel2 = QTextCursor(doc)
        sel2.setPosition(min(d.start_offset, end))
        sel2.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        richtext.apply_role(sel2, role, self._colors, lang)
        return True

    def _maybe_convert_directive(self):
        """Konverterar den markering som just avslutades vid markören."""
        cursor = self.textCursor()
        if cursor.hasSelection():
            return
        pos = cursor.position()
        for d in directives.parse(self.toPlainText()):
            if d.end_offset != pos:
                continue
            if self._convert_directive(d):
                end = min(d.start_offset + len(d.body),
                          self.document().characterCount() - 1)
                c = QTextCursor(self.document())
                c.setPosition(end)
                self.setTextCursor(c)
            return

    # ---------------------------------------------------------------- wikilänkar

    def set_link_titles(self, titles):
        """Anteckningstitlar som förslås när man skriver [[."""
        self._link_titles = sorted(set(t or "" for t in (titles or []) if t), key=str.lower)
        self.highlighter.set_known_targets(self._link_titles)

    def style_links(self, resolved, missing):
        """Sätter länkfärgerna utifrån aktivt tema."""
        self.highlighter.set_colors(resolved, missing)

    def _hide_completer(self):
        if self.completer.isVisible():
            self.completer.hide()

    def _link_query(self):
        """(söktext, start i blocket) om markören står inuti ett oavslutat [[."""
        cursor = self.textCursor()
        if cursor.hasSelection():
            return None
        block_text = cursor.block().text()
        before = block_text[:cursor.positionInBlock()]
        start = before.rfind("[[")
        if start < 0:
            return None
        between = before[start + 2:]
        if "]]" in between:
            return None
        return between, start

    def _maybe_show_completer(self):
        info = self._link_query()
        if info is None or not self._link_titles:
            self._hide_completer()
            return

        query, start = info
        self._completer_start = start
        q = query.strip().lower()
        matches = [t for t in self._link_titles if q in t.lower()] if q else list(self._link_titles)
        matches = matches[:40]
        if not matches:
            self._hide_completer()
            return

        self.completer.clear()
        for t in matches:
            self.completer.addItem(QListWidgetItem(t))

        row = 0
        for i, t in enumerate(matches):
            if t.lower().startswith(q):
                row = i
                break
        self.completer.setCurrentRow(row)

        rect = self.cursorRect()
        width = max(200, min(340, max(200, self.width() - rect.left() - 24)))
        self.completer.setFixedWidth(width)
        self.completer.setFixedHeight(min(180, 22 * len(matches) + 6))
        self.completer.move(rect.left(), rect.bottom() + 2)
        self.completer.show()
        self.completer.raise_()

    def _insert_link(self, title):
        """Ersätter den påbörjade [[söktexten med en färdig länk."""
        cursor = self.textCursor()
        original_pos = cursor.position()
        n = max(0, cursor.positionInBlock() - (self._completer_start + 2))
        if n > 0:
            cursor.setPosition(original_pos - n, QTextCursor.MoveMode.KeepAnchor)

        after = self.toPlainText()[original_pos:original_pos + 2]
        closing = "" if after.startswith("]]") else "]]"
        cursor.insertText(f"{title}{closing}")
        self.setTextCursor(cursor)
        self._hide_completer()

    def _link_at(self, pos):
        """Länkmålet om positionen ligger inuti en [[länk]], annars None."""
        cursor = self.cursorForPosition(pos)
        in_block = cursor.positionInBlock()
        for m in WIKILINK_RE.finditer(cursor.block().text()):
            if m.start() <= in_block <= m.end():
                target, _heading, _alias = split_link_target(m.group(1))
                return target or None
        return None

    def mousePressEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and (event.modifiers() & Qt.KeyboardModifier.ControlModifier)):
            target = self._link_at(event.position().toPoint())
            if target:
                self.wikilink_activated.emit(target)
                event.accept()
                return
        self._hide_completer()
        super().mousePressEvent(event)

    def style_completer(self, c):
        """Temastyling för förslagslistan."""
        self.completer.setStyleSheet(f"""
            QListWidget {{
                background-color: {c['bg']};
                color: {c['fg']};
                border: 1px solid {c['border']};
                border-radius: 4px;
                font-size: 12px;
                outline: none;
            }}
            QListWidget::item {{ padding: 3px 8px; }}
            QListWidget::item:selected {{
                background-color: {c['accent']};
                color: #ffffff;
            }}
        """)

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        menu.addSeparator()
        
        cursor = self.textCursor()
        selected = cursor.selectedText()
        table = cursor.currentTable()

        if table:
            tbl_menu = menu.addMenu("📊 " + _("tb_table"))
            
            def add_row_above():
                c = self.textCursor()
                t = c.currentTable()
                if t: t.insertRows(t.cellAt(c).row(), 1)

            def add_row_below():
                c = self.textCursor()
                t = c.currentTable()
                if t: t.insertRows(t.cellAt(c).row() + 1, 1)

            def add_col_left():
                c = self.textCursor()
                t = c.currentTable()
                if t: t.insertColumns(t.cellAt(c).column(), 1)

            def add_col_right():
                c = self.textCursor()
                t = c.currentTable()
                if t: t.insertColumns(t.cellAt(c).column() + 1, 1)

            def del_row():
                c = self.textCursor()
                t = c.currentTable()
                if t: t.removeRows(t.cellAt(c).row(), 1)

            def del_col():
                c = self.textCursor()
                t = c.currentTable()
                if t: t.removeColumns(t.cellAt(c).column(), 1)

            def del_table():
                c = self.textCursor()
                t = c.currentTable()
                if t:
                    c.setPosition(t.firstPosition())
                    c.setPosition(t.lastPosition(), QTextCursor.MoveMode.KeepAnchor)
                    c.removeSelectedText()

            tbl_menu.addAction("⬆️ " + _("tb_table_insert_rows_above"), add_row_above)
            tbl_menu.addAction("⬇️ " + _("tb_table_insert_rows_below"), add_row_below)
            tbl_menu.addAction("⬅️ " + _("tb_table_insert_cols_left"), add_col_left)
            tbl_menu.addAction("➡️ " + _("tb_table_insert_cols_right"), add_col_right)
            tbl_menu.addSeparator()
            tbl_menu.addAction("🗑️ " + _("tb_table_delete_row"), del_row)
            tbl_menu.addAction("🗑️ " + _("tb_table_delete_col"), del_col)
            tbl_menu.addAction("⚠️ " + _("tb_table_delete_table"), del_table)
            menu.addSeparator()

        ai_act = menu.addAction("✨ " + _("inline_ai_title") + " (Ctrl+K)")
        ai_act.triggered.connect(lambda: self.magic_ai_requested.emit(selected, event.globalPos()))

        menu.exec(event.globalPos())


class EditorView(QWidget):
    def __init__(self, theme_mgr, parent=None):
        super().__init__(parent)
        self.theme_mgr = theme_mgr

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Centered Paper Page Container
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        # Pappret är alltid 750px brett; krymper fönstret får ytan skrolla.
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Dokumentytan enligt referensen: en metarad ovanför papperet, och
        # papperet så brett referensen har det (750) i A4-höjd.
        self.stage = QWidget()
        self.stage.setObjectName("DocumentStage")
        stage_layout = QVBoxLayout(self.stage)
        stage_layout.setContentsMargins(0, 28, 0, 54)     # referensen: 28px 34px 54px
        stage_layout.setSpacing(0)

        self.meta_row = QWidget()
        meta_row = QHBoxLayout(self.meta_row)
        meta_row.setContentsMargins(0, 0, 0, 13)          # referensen: margin-bottom 13
        meta_row.setSpacing(8)
        self.lbl_meta_left = QLabel()
        self.lbl_meta_left.setObjectName("StageMeta")
        set_tracking(self.lbl_meta_left, 1.2)             # referensen: .12em
        self.lbl_meta_right = QLabel()
        self.lbl_meta_right.setObjectName("StageMeta")
        meta_row.addWidget(self.lbl_meta_left)
        meta_row.addStretch(1)
        meta_row.addWidget(self.lbl_meta_right)
        self.meta_row.setMaximumWidth(750)
        self.meta_row.setVisible(False)                   # visas när fönstret ger den data
        self.meta_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        meta_hall = QHBoxLayout()
        meta_hall.setContentsMargins(0, 0, 0, 0)
        meta_hall.addStretch(1)
        meta_hall.addWidget(self.meta_row, 12)
        meta_hall.addStretch(1)
        stage_layout.addLayout(meta_hall, 0)

        # Pappret: ett ark per sida, med editorn i det ark markören står i.
        # `page_frame` behålls som namn — appen och proven känner igen det.
        self.canvas = DocumentCanvas()
        self.page_frame = PagedPaper(self.canvas, theme_mgr)
        self.paper = self.page_frame
        self.paper.scroll_area = self.scroll_area
        # Skrivmaskinsläge (2.6): markörens rad hålls mitt i fönstret medan man
        # skriver. Läget slås på från Visa-menyn och kommer ihåg sig i configen.
        self.typewriter = False
        self.canvas.cursorPositionChanged.connect(self._typewriter_follow)

        sida_hall = QHBoxLayout()
        sida_hall.setContentsMargins(0, 0, 0, 0)
        sida_hall.addStretch(1)
        sida_hall.addWidget(self.page_frame, 12)
        sida_hall.addStretch(1)
        stage_layout.addLayout(sida_hall, 1)

        self.scroll_area.setWidget(self.stage)
        layout.addWidget(self.scroll_area)

        self.apply_theme()
        self.theme_mgr.theme_changed.connect(self.apply_theme)

    # ---------------------------------------------------------------- graden

    BASE_TEXT_PT = 13.0     # basmåtten i paged_paper hör till denna grad

    def text_point_size(self) -> float:
        """Textens grad. Vyn äger den — dukens stilmall skriver den."""
        return float(getattr(self, "_text_pt", self.BASE_TEXT_PT))

    def set_text_point_size(self, pt: float) -> None:
        """Sätter textens grad och skalar pappret med samma grad.

        Graden bor i dukens stilmall (apply_theme), för det är temats regel för
        QTextEdit som sätter den: den hade 13 pt hårdkodat, och därför var både
        skrivarens egen inställning och Ctrl++/Ctrl+- utan verkan — mätt gav
        canvas.setFont(20) 13,0 pt och radhöjd 19 px. Pappret följer samma grad,
        annars rymmer en zoomad sida färre tecken än en sida och arket ser mindre
        ut än det är.
        """
        pt = max(6.0, min(48.0, float(pt)))
        if abs(self.text_point_size() - pt) < 0.01:
            return
        self._text_pt = pt
        self.apply_theme()                 # enda stället som skriver dukens grad
        self.page_frame.set_scale(pt / self.BASE_TEXT_PT)

    def fit_scale(self, viewport_bredd: int = 0, viewport_höjd: int = 0) -> float:
        """Skalan som får en A4 att fylla fönstret — aldrig under verklig storlek.

        En A4 i verklig storlek är 750 px bred, och på en bred skärm blir den en
        liten lapp: "det känns inte som att det får plats med tillräckligt med
        tecken på en sida, som om det vore ett a5 istället för ett a4" (Alex
        9/10). Texten följer med, så sidan rymmer fortfarande en sidas text.

        Taket är arkets **höjd**, inte fönstrets bredd: i fullskärm på en bred
        skärm blev breddläget mätt 2,5 gånger och texten 30 pt — "det ser ut som
        om jag är närsynt pensionär" (Alex 9/10). Ett ark skall rymmas i fönstret,
        inte fylla en vägg. 1,35 är det yttersta; resten är Ctrl++.
        """
        källa = getattr(self.scroll_area, "viewport", None)
        if källa is not None:
            if not viewport_bredd:
                viewport_bredd = källa().width()
            if not viewport_höjd:
                viewport_höjd = källa().height()
        if viewport_bredd <= 0:
            return 1.0
        # Arkets egen storlek, inte A4-konstanten: ett A5-ark får plats mindre
        # text per rad och skall ändå fylla fönstret lika bra.
        ram = getattr(self, "page_frame", None)
        ark_bredd = float(ram.base_width() if ram is not None else PAGE_WIDTH_PX)
        ark_höjd = float(ram.base_height() if ram is not None else PAGE_HEIGHT_PX)
        bredd_skala = (viewport_bredd - 40) / ark_bredd
        höjd_skala = ((viewport_höjd - 60) / ark_höjd) if viewport_höjd > 0 else 99.0
        return max(1.0, min(1.35, bredd_skala, höjd_skala))

    def resizeEvent(self, event) -> None:
        """I autoläget ritas pappret om när fönstret ändrar bredd."""
        super().resizeEvent(event)
        self._fit_if_auto()

    def showEvent(self, event) -> None:
        """Första gången vyn syns finns bredden: då får autoläget sätta skalan."""
        super().showEvent(event)
        self._fit_if_auto()

    def _fit_if_auto(self) -> None:
        if getattr(self, "zoom_auto", False):
            self.set_text_point_size(self.BASE_TEXT_PT * self.fit_scale())

    def set_typewriter_mode(self, on: bool) -> None:
        """Slår skrivmaskinsläget på eller av. På: centrera markörens rad."""
        self.typewriter = bool(on)
        if self.typewriter:
            self.paper.center_cursor()

    def set_readability_marks(self, on: bool) -> None:
        """Vidare till arbetsytan, som äger markeringen (R03.17)."""
        self.canvas.set_readability_marks(on)

    def readability_marks(self) -> bool:
        return self.canvas.readability_marks()

    def _typewriter_follow(self) -> None:
        if self.typewriter:
            self.paper.center_cursor()

    def set_stage_meta(self, left: str, right: str) -> None:
        """Metaraden över papperet: vad dokumentet är och när det ändrades."""
        self.lbl_meta_left.setText((left or "").upper())
        self.lbl_meta_right.setText(right or "")
        self.meta_row.setVisible(bool(left or right))

    @property
    def document(self):
        return self.canvas.document()

    def textCursor(self):
        return self.canvas.textCursor()

    def setTextCursor(self, cursor):
        self.canvas.setTextCursor(cursor)

    def set_page_settings(self, settings: dict):
        self.canvas.set_page_settings(settings)
        self.paper.set_page_settings(settings)

    def apply_theme(self):
        c = self.theme_mgr.current
        paper = print_style.paper_colors()
        self.scroll_area.setStyleSheet(f"background-color: {c['window_bg']};")
        # Själva pappret är alltid vitt med svart text — appens tema får färga
        # ramen omkring, aldrig arket. Då ser dokumentet likadant ut på skärmen
        # som i PDF:en, och ingen temafärg kan smitta en export.
        self.paper.apply_theme()
        # Editorn är arket, inte ett inmatningsfält: ingen kant och ingen blå
        # fokusring mitt på pappret (den app-vida stilen ger alla QTextEdit en).
        self.canvas.setStyleSheet(f"""
            QTextEdit, QTextEdit:focus {{
                background-color: {paper['canvas_bg']};
                color: {paper['text_color']};
                border: 0;
                border-radius: 0;
                padding: 0;
            }}
            QTextEdit {{
                selection-background-color: {c['accent']};
                selection-color: #ffffff;
                font-size: {self.text_point_size():g}pt;
                line-height: 1.5;
            }}
        """)
        pal = self.canvas.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(paper["canvas_bg"]))
        pal.setColor(QPalette.ColorRole.Text, QColor(paper["text_color"]))
        pal.setColor(QPalette.ColorRole.Highlight, QColor(c["accent"]))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        self.canvas.setPalette(pal)
        self.canvas.style_completer({
            "bg": c["sidebar_card"],
            "fg": c["text_color"],
            "border": c["canvas_border"],
            "accent": c["accent"],
        })
        self.canvas.style_links(
            c.get("link", c["accent"]),
            c.get("link_missing", "#d97706"),
        )
        # Kod- och citatblock får pappersfärger, inte temafärger: blocken är
        # en del av dokumentet och följer därför med ut i exporten.
        self.canvas.set_block_colors(paper)
