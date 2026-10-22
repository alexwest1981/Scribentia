"""
ui/paged_paper.py — pappret: ett ark per sida, som i Word och LibreOffice.

Texten delas mellan rader (`core.pagination`) och ritas i separata A4-ark med
ett mellanrum av ytan runt pappret. Det ark markören står i bär den riktiga
editorn (`DocumentCanvas`), som flyttas dit; övriga ark ritas statiskt ur
dokumentets layout. Ett klick i ett annat ark flyttar markören dit — samma sak
som när man klickar på en annan sida i Word.

Sidnumret hamnar i arkets fot, där det nu finns tom plats: texten slutar vid
arkets innermått i stället för att flöda vidare över kanten.

    ark = PagedPaper(canvas, theme_mgr)     # äger canvasen och papprets mått
    ark.refresh()                           # räknar om sidorna
"""

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QAbstractTextDocumentLayout, QColor, QFont, QFontMetricsF, QPainter, QPalette,
    QPen, QTextCharFormat, QTextCursor,
)
from PyQt6.QtWidgets import QFrame, QSizePolicy, QWidget

from core import page_format, print_style
from core.i18n import _
from core.pagination import page_of_offset, page_offsets

# Papprets mått. Referensen har 750px bred sida; A4 är 1:√2, alltså 750 × 1060.
# Ramens inre marginal är papprets marginal, och den texten har att röra sig på
# är arkets innermått — därför räknas CANVAS_PAGE_PX fram ur dem i stället för
# att skrivas som ett eget tal någon annanstans.
#
# De här talen är A4-basen, inte hela sanningen: arket ritas i den storlek
# sidinställningarna anger (core.page_format.page_mm), och 750 px = 210 mm är
# skalan mellan millimeter och pixlar. Marginalerna på skärmen är en
# visningskonvention och står kvar — utskriftens marginaler kommer ur
# page_settings, som i Writer (där pappret ägs av sidstilen).
PAGE_WIDTH_PX = 750
PX_PER_MM = PAGE_WIDTH_PX / 210.0
PAGE_MARGIN_X = 52
PAGE_MARGIN_TOP = 34
PAGE_MARGIN_BOTTOM = 42
PAGE_HEIGHT_PX = 1060
CANVAS_PAGE_PX = PAGE_HEIGHT_PX - PAGE_MARGIN_TOP - PAGE_MARGIN_BOTTOM    # 984

# Två ankare, båda ur A4: bredden 750 px = 210 mm, höjden 1060 px = 297 mm. Ett
# enda ankare gjorde A4 1061 px högt (297 × 750/210 = 1060,7) och därmed en rad
# mer per ark än basmåtten lovar.
PX_PER_MM_Y = PAGE_HEIGHT_PX / 297.0


class PagedPaper(QWidget):
    """Ark-kolumnen. Ett ark per sida, med editorn i det aktiva arket.

    Måtten nedan är *basmått*: de hör till BAS_PT (13 pt). Arket ritas i den
    skala texten har, så att ett ark alltid rymmer en A4-sidas text. Förut stod
    pappret still medan zoomen bara ändrade texten, och då rymde en zoomad sida
    färre tecken än en sida — vilket syns som ett litet ark på en stor skärm:
    "det känns inte som att det får plats med tillräckligt med tecken på en sida,
    som om det vore ett a5 istället för ett a4" (Alex 9/10). Skalan sätts av
    vyn (se EditorView.set_text_point_size), aldrig av arket själv.
    """

    GAP_PX = 26                 # mellanrummet mellan två ark (ytan syns där)
    PAD_TOP_PX = 22             # luft ovanför första arket
    PAD_BOTTOM_PX = 40
    MARK_PX = 14                # hörnmarkeringarnas arm
    REFRESH_MS = 120            # innan sidorna räknas om efter en ändring
    MIN_SCALE = 0.5
    MAX_SCALE = 4.0

    page_changed = pyqtSignal(int)

    def __init__(self, canvas, theme_mgr=None, parent=None):
        super().__init__(parent)
        self.setObjectName("PagedPaper")
        self.theme_mgr = theme_mgr
        self.scroll_area = None                 # sätts av EditorView
        self._scale = 1.0

        self.canvas = canvas
        canvas.setParent(self)
        canvas.setFrameShape(QFrame.Shape.NoFrame)
        canvas.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        canvas.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.page_settings = {}
        self.pages = [0.0]
        self.active = 0

        # Arkets mått i baspixlar: A4 tills något annat sägs, sedan det
        # sidinställningarna anger.
        self.page_w = PAGE_WIDTH_PX
        self.page_h = PAGE_HEIGHT_PX
        self.canvas_h = CANVAS_PAGE_PX

        self.setFixedWidth(self.px(self.page_w))
        self.setMinimumHeight(self.px(self.page_h))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.REFRESH_MS)
        self._timer.timeout.connect(self.refresh)

        canvas.cursorPositionChanged.connect(self.follow_cursor)
        canvas.textChanged.connect(self.schedule_refresh)
        layout = canvas.document().documentLayout()
        if layout is not None:
            layout.documentSizeChanged.connect(lambda *_: self.schedule_refresh())

        self.refresh()

    # ------------------------------------------------------------------ mått

    def scale(self) -> float:
        """Arkets skala. 1.0 = basmåtten, alltså en A4 i verklig storlek."""
        return self._scale

    def px(self, v: float) -> int:
        """Basmått i arkets skala — den enda vägen från basmått till pixlar."""
        return int(round(float(v) * self._scale))

    def base_width(self) -> int:
        """Arkets bredd i baspixlar (oskalerad) — det autoläget räknar mot."""
        return int(self.page_w)

    def base_height(self) -> int:
        """Arkets höjd i baspixlar (oskalerad)."""
        return int(self.page_h)

    def _apply_page_size(self) -> None:
        """Sätter arkets mått ur sidinställningarna.

        Writers modell, mätt: papprets storlek hör till sidan och **pagineringen
        följer den** — samma text blev 8 sidor på A4 och 12 på A5 — medan texten
        aldrig skalas om. Därför ändrar en ny storlek arkets bredd och höjd här,
        och sidorna räknas om av refresh().
        """
        w_mm, h_mm = page_format.page_mm(self.page_settings)
        self.page_w = max(1, int(round(w_mm * PX_PER_MM)))
        self.page_h = max(1, int(round(h_mm * PX_PER_MM_Y)))
        self.canvas_h = max(1, self.page_h - PAGE_MARGIN_TOP - PAGE_MARGIN_BOTTOM)
        self.setFixedWidth(self.px(self.page_w))
        self.setMinimumHeight(self.px(self.page_h))

    def set_scale(self, s: float) -> None:
        """Sätter arkets skala och ritar om. Sidorna räknas om av refresh()."""
        s = max(self.MIN_SCALE, min(self.MAX_SCALE, float(s)))
        if abs(s - self._scale) < 0.001:
            return
        self._scale = s
        self.setFixedWidth(self.px(self.page_w))
        self.setMinimumHeight(self.px(self.page_h))
        self.refresh()

    def _slot_px(self) -> float:
        return float(self.px(self.page_h) + self.GAP_PX)

    def sheet_rect(self, i: int) -> QRectF:
        """Arket i widgetens koordinater."""
        return QRectF(0.0, self.PAD_TOP_PX + i * self._slot_px(),
                      float(self.px(self.page_w)), float(self.px(self.page_h)))

    def content_rect(self, i: int) -> QRectF:
        """Arket innanför marginalerna — där texten bor."""
        ark = self.sheet_rect(i)
        kant = self.px(PAGE_MARGIN_X)
        return QRectF(ark.x() + kant, ark.y() + self.px(PAGE_MARGIN_TOP),
                      ark.width() - 2 * kant,
                      ark.height() - self.px(PAGE_MARGIN_TOP) - self.px(PAGE_MARGIN_BOTTOM))

    def total_height(self) -> int:
        n = max(1, len(self.pages))
        return int(self.PAD_TOP_PX + n * self._slot_px() - self.GAP_PX + self.PAD_BOTTOM_PX)

    # ------------------------------------------------------------- geometri

    def page_of_doc_y(self, doc_y: float) -> int:
        return page_of_offset(self.pages, doc_y)

    def schedule_refresh(self) -> None:
        """Sidorna räknas om strax efter att texten ändrats, inte mitt i en tangent."""
        self._timer.start()

    def refresh(self) -> None:
        """Räknar om arken och lägger editorn i det ark markören står i."""
        doc = self.canvas.document()
        if doc is None:
            return
        self.pages = page_offsets(doc, float(self.px(self.canvas_h)))
        self.setFixedHeight(self.total_height())

        sida = min(max(0, self.page_of_doc_y(self._cursor_doc_y())), len(self.pages) - 1)
        self.active = sida
        self._place_canvas()
        self.update()

    def _cursor_doc_y(self) -> float:
        """Markörens y i dokumentets koordinater."""
        try:
            rect = self.canvas.cursorRect(self.canvas.textCursor())
        except Exception:
            return 0.0
        return float(rect.top() + self.canvas.verticalScrollBar().value())

    def _page_height(self, i: int) -> float:
        """Hur mycket text arket rymmer. Radbunden paginering gör att ett ark
        ofta är några pixlar lägre: raden som inte fick plats hör till nästa."""
        if i + 1 < len(self.pages):
            return min(float(self.px(self.canvas_h)), self.pages[i + 1] - self.pages[i])
        # Sista arket: så mycket text som finns kvar. Editorn måste vara exakt så
        # hög, annars når skrollfältet inte fram till arkets första rad.
        doc = self.canvas.document()
        kvar = float(doc.size().height()) - self.pages[i] if doc is not None else 1.0
        return max(1.0, min(float(self.px(self.canvas_h)), kvar))

    def _place_canvas(self) -> None:
        """Lägger editorn i det aktiva arket och sätter dess läge i dokumentet."""
        innehall = self.content_rect(self.active)
        rect = QRectF(innehall.x(), innehall.y(), innehall.width(),
                      self._page_height(self.active)).toRect()
        if self.canvas.geometry() != rect:
            self.canvas.setGeometry(rect)
        bar = self.canvas.verticalScrollBar()
        if bar is not None:
            bar.setValue(int(self.pages[self.active]))

    def follow_cursor(self) -> None:
        """Markörens ark blir det aktiva; vyn ser till att markören syns."""
        if not self.pages:
            return
        sida = min(self.page_of_doc_y(self._cursor_doc_y()), len(self.pages) - 1)
        if sida != self.active:
            self.active = sida
            self._place_canvas()
            self.update()
            self.page_changed.emit(sida)
        # Qt skrollar själv för att visa markören; rätta det efteråt, inte mitt i
        QTimer.singleShot(0, self._sync_scroll)
        self.ensure_cursor_visible()

    def _sync_scroll(self) -> None:
        """Editorn visar alltid sitt ark från arkets första rad."""
        if not self.pages:
            return
        bar = self.canvas.verticalScrollBar()
        if bar is not None and bar.value() != int(self.pages[self.active]):
            bar.setValue(int(self.pages[self.active]))

    def ensure_cursor_visible(self) -> None:
        """Skrollar ytterytan så att markören syns (editorn sköter sitt ark)."""
        if self.scroll_area is None:
            return
        rect = self.content_rect(self.active)
        syns_pa = self._cursor_doc_y() - self.pages[self.active]
        self.scroll_area.ensureVisible(int(rect.x() + 40),
                                       int(rect.y() + syns_pa), 60, 80)

    def center_cursor(self) -> bool:
        """Skrivmaskinsläge: markörens rad skall stå mitt i fönstret.

        Avståndet räknas fram i skrollområdets koordinater, så det stämmer även
        om arket ligger en bit ned (metaraden ovanför) och oavsett vilket ark
        markören står i.
        """
        if self.scroll_area is None or not self.isVisible():
            return False
        rad = self.canvas.cursorRect(self.canvas.textCursor())
        stage = self.scroll_area.widget()
        y = self.canvas.mapTo(stage, rad.center()).y()
        bar = self.scroll_area.verticalScrollBar()
        mål = int(y - self.scroll_area.viewport().height() / 2)
        mål = max(bar.minimum(), min(bar.maximum(), mål))
        if bar.value() != mål:
            bar.setValue(mål)
        return True

    def cursor_from_center(self) -> int:
        """Hur långt markörens rad står från mitten av fönstret, i pixlar."""
        if self.scroll_area is None:
            return -1
        rad = self.canvas.cursorRect(self.canvas.textCursor())
        stage = self.scroll_area.widget()
        y = self.canvas.mapTo(stage, rad.center()).y()
        return int(y - self.scroll_area.verticalScrollBar().value()
                   - self.scroll_area.viewport().height() / 2)

    def set_page_settings(self, settings: dict) -> None:
        """Nya sidinställningar: arket byter storlek och sidorna räknas om.

        Förut bytte bara sidnumret och marginalmarkeringarna — ett A5-dokument
        såg ut som ett A4 på skärmen medan PDF:en var A5, alltså två sanningar
        om samma dokument.
        """
        self.page_settings = dict(settings or {})
        self._apply_page_size()
        self.refresh()

    def apply_theme(self) -> None:
        self.update()

    def _colors(self) -> dict:
        """Ytan runt arken följer temat; själva arket är alltid papper.

        Arket får aldrig temafärg (samma regel som i exporten): då ser
        dokumentet likadant ut på skärmen som i PDF:en.
        """
        c = {}
        if self.theme_mgr is not None:
            c.update(self.theme_mgr.tokens())
        # Pappret läggs sist: temat får färga ytan omkring, aldrig arket.
        c.update(print_style.paper_colors())
        return c

    def _paper_palette(self, colors: dict) -> QPalette:
        """Textfärger för de ark som ritas statiskt: papprets, inte temats text."""
        pal = QPalette()
        text = QColor(colors["text_color"])
        pal.setColor(QPalette.ColorRole.Text, text)
        pal.setColor(QPalette.ColorRole.WindowText, text)
        pal.setColor(QPalette.ColorRole.Base, QColor(colors["canvas_bg"]))
        pal.setColor(QPalette.ColorRole.Window, QColor(colors["canvas_bg"]))
        return pal

    # ------------------------------------------------------------- målning

    def paintEvent(self, e) -> None:
        colors = self._colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(e.rect(), QColor(colors["window_bg"]))

        synligt = QRectF(e.rect())
        for i in range(len(self.pages)):
            ark = self.sheet_rect(i)
            if not ark.intersects(synligt):
                continue
            self._paint_sheet(painter, ark, colors)
            self._paint_margin_marks(painter, self.content_rect(i), colors)
            if i != self.active:
                self._paint_page_text(painter, i, colors)
            self._paint_page_number(painter, i, ark, colors)

    def _paint_sheet(self, painter: QPainter, ark: QRectF, colors: dict) -> None:
        """Ett ark: vitt papper med tunn kant och en mjuk skugga under kanten."""
        skugga = QColor(print_style.PAPER_RULE)
        skugga.setAlpha(70)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(skugga)
        painter.drawRoundedRect(ark.adjusted(2.0, 3.0, 4.0, 7.0), 2.0, 2.0)

        painter.setBrush(QColor(print_style.PAPER_WHITE))
        painter.setPen(QPen(QColor(print_style.PAPER_TINT_STRONG), 1.0))
        painter.drawRect(ark.adjusted(0.5, 0.5, -0.5, -0.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _paint_margin_marks(self, painter: QPainter, innehall: QRectF, colors: dict) -> None:
        """Hörnmarkeringar vid textens kant (som LibreOffice visar marginalen)."""
        kant = QColor(print_style.PAPER_RULE)
        kant.setAlpha(130)
        pen = QPen(kant, 1.0)
        painter.setPen(pen)
        m = self.MARK_PX
        x0, y0 = innehall.left(), innehall.top()
        x1, y1 = innehall.right(), innehall.bottom()
        for x, y, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
            painter.drawLine(QPointF(x, y), QPointF(x + dx * m, y))
            painter.drawLine(QPointF(x, y), QPointF(x, y + dy * m))

    def _paint_page_text(self, painter: QPainter, i: int, colors: dict) -> None:
        """Texten på ett ark som inte redigeras: ur dokumentets layout, klippt
        till arket och flyttat så att arkets första rad hamnar vid innermåttet."""
        doc = self.canvas.document()
        layout = doc.documentLayout()
        if layout is None:
            return
        innehall = self.content_rect(i)
        offset = self.pages[i]
        höjd = self._page_height(i)
        painter.save()
        painter.setClipRect(QRectF(innehall.x(), innehall.y(), innehall.width(), höjd))
        # Dokumentets origo är arkets innermått: både x och y måste flyttas,
        # annars ritas texten med dokumentets marginal utanför arket.
        painter.translate(innehall.x(), innehall.y() - offset)
        ctx = QAbstractTextDocumentLayout.PaintContext()
        ctx.palette = self._paper_palette(colors)
        ctx.clip = QRectF(0.0, offset, innehall.width(), höjd)
        # Markeringen hör till dokumentet, men bara det ark editorn sitter i ritar
        # den själv. Utan detta syns en Ctrl+A bara på ett ark — texten är
        # markerad, men det ser ut som att bara sista sidan blev det, och då
        # vågar man inte trycka Delete (mätt: 1,7 % av ytan ändrades, exakt ett
        # ark). Färgerna tas från editorn, så arken och arket man skriver i ser
        # likadana ut.
        markering = self.canvas.textCursor()
        if markering.hasSelection():
            val = QAbstractTextDocumentLayout.Selection()
            val.cursor = markering
            stil = QTextCharFormat()
            stil.setBackground(self.canvas.palette().highlight())
            stil.setForeground(self.canvas.palette().highlightedText())
            val.format = stil
            ctx.selections = [val]
        layout.draw(painter, ctx)
        painter.restore()

    def _paint_page_number(self, painter: QPainter, i: int, ark: QRectF, colors: dict) -> None:
        """Sidnumret i arkets fot, där det finns tom plats."""
        if not self.page_settings.get("page_numbering", True):
            return
        # Numreringen behöver inte börja på 1: försättsblad och inledning räknas
        # ofta inte med, och då är sidan 1 i boken ark 9 (W10).
        sida = int(self.page_settings.get("page_number_start", 1) or 1) + i
        if bool(self.page_settings.get("skip_first_page", False)) and i == 0:
            return

        antal = max(1, len(self.pages))
        fmt_type = self.page_settings.get("page_number_format", "page_of_total")
        if fmt_type == "number":
            text = str(sida)
        elif fmt_type == "hyphen":
            text = f"— {sida} —"
        elif fmt_type == "slash":
            text = f"{sida} / {antal}"
        else:
            text = _("pdf_page_n_of_total", n=sida, total=antal)

        pos = str(self.page_settings.get("page_number_pos", "bottom-center"))
        font = QFont("sans-serif", 9)
        painter.setFont(font)
        bredd = QFontMetricsF(font).horizontalAdvance(text)
        # "bottom-alternating" lägger udda sidor till höger och jämna till
        # vänster, som i en bok — förut hamnade varje sida till höger, vilket
        # gjorde att vänstersidorna i förhandsvisningen inte såg ut som i tryck.
        vänster = "left" in pos
        if pos.endswith("alternating"):
            vänster = (sida % 2 == 0)
        if vänster:
            x = ark.x() + PAGE_MARGIN_X
        elif "right" in pos:
            x = ark.right() - PAGE_MARGIN_X - bredd
        else:
            x = ark.center().x() - bredd / 2.0
        y = ark.bottom() - PAGE_MARGIN_BOTTOM + 10.0

        painter.setPen(QColor(colors["text_muted"]))
        painter.drawText(QRectF(x, y, bredd + 1.0, 14.0),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, text)

    # ---------------------------------------------------------- interaktion

    def mousePressEvent(self, e) -> None:
        """Klick i ett ark: markören dit och editorn flyttar in i arket."""
        pos = e.position()
        for i in range(len(self.pages)):
            if self.sheet_rect(i).contains(pos):
                self.place_cursor(i, pos)
                return
        super().mousePressEvent(e)

    def place_cursor(self, i: int, pos: QPointF) -> None:
        doc = self.canvas.document()
        layout = doc.documentLayout()
        innehall = self.content_rect(i)
        punkten = QPointF(pos.x() - innehall.x(), pos.y() - innehall.y() + self.pages[i])
        # hitTest ger en teckenposition (int), inte ett element
        position = int(layout.hitTest(punkten, Qt.HitTestAccuracy.FuzzyHit))
        cursor = QTextCursor(doc)
        cursor.setPosition(max(0, position))
        self.active = i
        self._place_canvas()
        self.canvas.setTextCursor(cursor)
        self.canvas.setFocus(Qt.FocusReason.MouseFocusReason)
        QTimer.singleShot(0, self._sync_scroll)
        self.update()

    def wheelEvent(self, e) -> None:
        """Hjulhjulet skrollar pappret, inte det enstaka arket."""
        if self.scroll_area is None:
            return super().wheelEvent(e)
        bar = self.scroll_area.verticalScrollBar()
        if bar is None:
            return super().wheelEvent(e)
        bar.setValue(bar.value() - e.angleDelta().y())
        e.accept()
