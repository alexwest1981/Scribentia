import os
import re
from PyQt6.QtCore import Qt, QMarginsF, QRectF, QSizeF, QPointF
from PyQt6.QtGui import (
    QTextDocument, QTextCursor, QPageLayout, QPageSize,
    QFont, QColor, QPainter, QPen, QAbstractTextDocumentLayout
)
from PyQt6.QtPrintSupport import QPrinter

try:
    import docx
    from docx.shared import Pt, Cm, Inches, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.style import WD_STYLE_TYPE
except ImportError:
    docx = None
    WD_STYLE_TYPE = None

try:
    import markdown
except ImportError:
    markdown = None

from core import page_format, richtext, print_style
from core.i18n import _

# ```-block i Markdown, med valfritt språk
_FENCE_RE = re.compile(r"^```([A-Za-z0-9_+#.\-]*)[ \t]*\n(.*?)^```[ \t]*$", re.M | re.S)
# Platshållaren som tillfälligt ersätter ett kodblock under HTML-konverteringen
_FENCE_PLACEHOLDER_RE = re.compile(r"^ScribentiaKodblock(\d+)Z$")

# En rad som bara består av #taggar (Obsidian-stil), inte en rubrik.
TAG_LINE_RE = re.compile(r"^(?:#[^\W_][\w\-/]*\s*)+$")

# Dokumentets layout räknar i enheter om 1/96 tum. Skrivaren räknar i sin egen
# upplösning (1200 dpi för PDF i HighResolution-läge), så målningen skalas med
# resolution / LAYOUT_DPI. Slår man ihop de två blir allt text några millimeter
# stor i ena hörnet i stället för en full sida.
LAYOUT_DPI = 96.0

def release_wrapping(dokument) -> int:
    """Tar bort Qts nonBreakableLines från varje block. Antalet rättade.

    Den flaggan stänger av **radbrytningen**, inte bara sidbrytningen: en rad i en
    inläst `<pre>` blev mätt 1355 px i ett 646 px ark och gick utanför pappret.
    Alex regel är att text alltid bryts vid ordet före kanten — "det får inte ens
    vara under diskussion" — så ingen väg in i editorn får lämna flaggan på.
    """
    from PyQt6.QtGui import QTextCursor
    if dokument is None:
        return 0
    rättade = 0
    markor = QTextCursor(dokument)
    markor.beginEditBlock()
    try:
        block = dokument.begin()
        while block.isValid():
            if block.blockFormat().nonBreakableLines():
                fmt = block.blockFormat()
                fmt.setNonBreakableLines(False)
                markor.setPosition(block.position())
                markor.mergeBlockFormat(fmt)
                rättade += 1
            block = block.next()
    finally:
        markor.endEditBlock()
    return rättade


DEFAULT_PAGE_SETTINGS = {
    "page_size": "A4",                   # "A4", "Letter"
    "orientation": "portrait",           # "portrait", "landscape"
    "margin_top_mm": 20.0,
    "margin_bottom_mm": 20.0,
    "margin_left_mm": 20.0,
    "margin_right_mm": 20.0,
    "page_numbering": True,              # True / False
    "page_number_pos": "bottom-center",  # "bottom-center", "bottom-right", "bottom-alternating", "top-right", "top-alternating", "none"
    "page_number_format": "page_of_total", # "number", "page_of_total", "hyphen", "slash"
    "skip_first_page": False,            # True för att dölja på titelsida/framsida
    "header_text": "",                   # Löpande sidhuvud
    "footer_text": "",                   # Löpande sidfot
    "clean_print": True,                 # Rena svartvita exporter (papper, inte tema)
    "grayscale_images": False,           # Gör inbäddade bilder gråskaliga vid export
    "large_print": False,                # Stor stil: större grad och radavstånd (5.16)
}


# Rollerna ur core/richtext.py -> Word-stilarnas namn. Namnen är de inbyggda i
# Words standardmall och är desamma i varje språkversion av Word.
DOCX_ROLE_STYLES = {
    richtext.ROLE_QUOTE: "Quote",          # finns i Words standardmall
    richtext.ROLE_CODE: "Code Block",      # skapas om den inte finns
    richtext.ROLE_BREAK: "Scene Break",
    richtext.ROLE_VERSE: "Verse",
    richtext.ROLE_MESSAGE: "Message",
}
DOCX_CODE_FONT = "Consolas"


class DocumentManager:
    @staticmethod
    def _is_docx_file(filepath):
        try:
            with open(filepath, "rb") as f:
                return f.read(4) == b"PK\x03\x04"
        except Exception:
            return False

    @staticmethod
    def load_file(filepath, text_document: QTextDocument, colors=None):
        """Loads a file (.docx, .md, .html, .txt) into a QTextDocument preserving rich formatting."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")

        ext = os.path.splitext(filepath)[1].lower()

        if ext == ".docx" or (not ext and DocumentManager._is_docx_file(filepath)):
            if docx is None:
                raise ImportError("python-docx is required to read .docx files.")
            doc = docx.Document(filepath)
            html_parts = []
            
            for p in doc.paragraphs:
                p_text = p.text
                if not p_text.strip() and not p.runs:
                    html_parts.append("<p><br/></p>")
                    continue

                style_name = p.style.name.lower() if p.style else ""
                tag = "p"
                if "heading 1" in style_name:
                    tag = "h1"
                elif "heading 2" in style_name:
                    tag = "h2"
                elif "heading 3" in style_name:
                    tag = "h3"
                elif "title" in style_name:
                    tag = "h1"
                elif "quote" in style_name:
                    tag = "blockquote"

                align_style = ""
                if p.alignment == WD_ALIGN_PARAGRAPH.CENTER:
                    align_style = "text-align: center;"
                elif p.alignment == WD_ALIGN_PARAGRAPH.RIGHT:
                    align_style = "text-align: right;"
                elif p.alignment == WD_ALIGN_PARAGRAPH.JUSTIFY:
                    align_style = "text-align: justify;"

                runs_html = []
                for run in p.runs:
                    txt = run.text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
                    
                    span_styles = []
                    if run.font.name:
                        span_styles.append(f"font-family: '{run.font.name}';")
                    if run.font.size:
                        span_styles.append(f"font-size: {run.font.size.pt}pt;")
                    if run.font.color and run.font.color.rgb:
                        span_styles.append(f"color: #{run.font.color.rgb};")
                        
                    if run.bold:
                        txt = f"<b>{txt}</b>"
                    if run.italic:
                        txt = f"<i>{txt}</i>"
                    if run.underline:
                        txt = f"<u>{txt}</u>"
                    if run.font.strike:
                        txt = f"<s>{txt}</s>"
                        
                    if span_styles:
                        txt = f'<span style="{" ".join(span_styles)}">{txt}</span>'
                        
                    runs_html.append(txt)

                inner = "".join(runs_html) if runs_html else p_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                style_attr = f' style="{align_style}"' if align_style else ""
                html_parts.append(f"<{tag}{style_attr}>{inner}</{tag}>")

            # Load docx tables if present
            for tbl in doc.tables:
                tbl_html = ['<table border="1" cellpadding="6" style="border-collapse: collapse; margin: 12px 0;">']
                for row in tbl.rows:
                    tbl_html.append("<tr>")
                    for cell in row.cells:
                        cell_txt = cell.text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                        tbl_html.append(f'<td style="padding: 6px; border: 1px solid #cbd5e1;">{cell_txt}</td>')
                    tbl_html.append("</tr>")
                tbl_html.append("</table>")
                html_parts.append("".join(tbl_html))

            text_document.setHtml("".join(html_parts))

        elif ext in {".html", ".htm"}:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            text_document.setHtml(content)

        elif ext in {".md", ".markdown"}:
            with open(filepath, "r", encoding="utf-8") as f:
                md_text = f.read()

            fences = []
            def _stash(m):
                idx = len(fences)
                fences.append((m.group(1) or "", m.group(2)))
                return f"ScribentiaKodblock{idx}Z"

            stashed_md = _FENCE_RE.sub(_stash, md_text)

            clean_lines = []
            for line in stashed_md.splitlines():
                if TAG_LINE_RE.match(line):
                    line = "&#35;" + line[1:]
                clean_lines.append(line)
            stashed_md = "\n".join(clean_lines)

            if markdown:
                html_content = markdown.markdown(
                    stashed_md,
                    extensions=["extra", "tables", "nl2br", "sane_lists"]
                )
            else:
                html_content = f"<pre>{stashed_md}</pre>"

            text_document.setHtml(html_content)
            release_wrapping(text_document)

            if fences:
                doc = text_document
                for idx, (lang, code) in enumerate(fences):
                    token = f"ScribentiaKodblock{idx}Z"
                    cursor = doc.find(token)
                    while not cursor.isNull():
                        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
                        if cursor.selectedText() != token:
                            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                        b_first = cursor.blockNumber()
                        cursor.beginEditBlock()
                        try:
                            cursor.removeSelectedText()
                            cursor.insertText(code.rstrip("\n"))
                            b_last = cursor.blockNumber()
                        finally:
                            cursor.endEditBlock()

                        sel = QTextCursor(doc)
                        sel.setPosition(doc.findBlockByNumber(b_first).position())
                        sel.setPosition(
                            doc.findBlockByNumber(b_last).position() + doc.findBlockByNumber(b_last).length() - 1,
                            QTextCursor.MoveMode.KeepAnchor
                        )
                        richtext.apply_role(sel, richtext.ROLE_CODE,
                                            colors or print_style.paper_colors(), lang)
                        cursor = doc.find(token)

        else:  # .txt or plain text
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            text_document.setPlainText(content)

    @staticmethod
    def print_document_to_printer(text_document: QTextDocument, printer: QPrinter, page_settings: dict | None = None):
        """Utskrift och PDF-generering med sidnummer, sidhuvud/sidfot och speglade marginaler."""
        cfg = DEFAULT_PAGE_SETTINGS.copy()
        if page_settings:
            cfg.update(page_settings)

        from core.pagination import page_offsets
        from core.publishing import page_margins

        # 1. Pappret. Måtten kommer ur page_format.page_mm, som redan har lagt på
        #    orienteringen — därför Portrait här: en Landscape-flagga till skulle
        #    rotera tillbaka arket.
        w_mm, h_mm = page_format.page_mm(cfg)
        left0, top_mm, right0, bottom_mm = page_margins(cfg, 0)
        # Textytan är lika bred på varje sida även när marginalerna växlar mellan
        # udda och jämn sida — det är bara x-läget som flyttas, som i Writer.
        text_w_mm = max(20.0, w_mm - left0 - right0)

        # Skrivarens egen marginal läggs inte ovanpå våra: layouten sätts utan
        # marginaler och varje sida placeras för sig (det är så speglingen kan
        # flytta textblocket utan att byta pappersstorlek).
        page_size = QPageSize(QSizeF(w_mm, h_mm), QPageSize.Unit.Millimeter)
        printer.setPageLayout(QPageLayout(page_size, QPageLayout.Orientation.Portrait,
                                          QMarginsF(0, 0, 0, 0),
                                          QPageLayout.Unit.Millimeter))

        # 2. Mått. Dokumentet räknar i layoutenheter (96 dpi) medan skrivaren
        #    räknar i sin egen upplösning. Skalan förmedlar mellan dem: utan den
        #    ritas texten några millimeter stor i hörnet i stället för att fylla
        #    arket.
        resolution = printer.resolution()
        scale = resolution / LAYOUT_DPI
        dpmm = resolution / 25.4               # millimeter i skrivarpixlar

        paint_rect = printer.pageLayout().paintRectPixels(resolution)
        full_rect = printer.pageLayout().fullRectPixels(resolution)

        # Reservera utrymme för sidhuvud och sidofot
        has_header = bool(cfg.get("header_text")) or "top" in str(cfg.get("page_number_pos", ""))
        has_footer = bool(cfg.get("footer_text")) or ("bottom" in str(cfg.get("page_number_pos", "bottom-center")) and cfg.get("page_number_pos") != "none")

        header_h = (8.0 * dpmm) if has_header else 0.0
        footer_h = (8.0 * dpmm) if has_footer else 0.0

        # Utskriftsskalning (W8): texten skalas, arket och marginalerna står kvar.
        # 1.0 = som dokumentet ser ut; 0.8 ger 25 % fler tecken per rad i samma
        # spalt (mätt som tecken per rad i PDF:en, inte som sidantal).
        print_scale = max(0.5, min(2.0, float(cfg.get("print_scale", 1.0) or 1.0)))
        rit_skala = scale * print_scale

        content_w_px = text_w_mm * dpmm
        content_h_px = paint_rect.height() - header_h - footer_h
        # Layoutenheter: dokumentets egen yta
        content_w = content_w_px / rit_skala
        content_h = content_h_px / rit_skala

        # 3. Klona dokumentet för layout utan att röra originalet
        doc_clone = text_document.clone()
        if doc_clone is None:
            return

        # 3b. Rening: papperet får färg av dokumentet, aldrig av programmets tema
        if cfg.get("clean_print", True):
            print_style.normalize_document(
                doc_clone, grayscale_images=bool(cfg.get("grayscale_images", False))
            )

        # 3c. Stor stil (5.16): utskriftsvägen gör sin egen klon och gick därför
        # förbi _export_clone — utan det här blev en large print-utgåva i PDF
        # exakt lika stor som originalupplagan (mätt: 10 sidor före och efter).
        if cfg.get("large_print"):
            print_style.scale_for_large_print(doc_clone)

        DocumentManager._hyphenate_clone(doc_clone, cfg.get("language", "sv"))
        # Ett enda flöde, som i Writer: dokumentet läggs i **löpande** höjd vid
        # textytans bredd, och arken skärs ur samma radbundna paginering som
        # skärmen ritar (core.pagination).
        doc_clone.setPageSize(QSizeF(content_w, -1))
        doc_clone.setTextWidth(content_w)
        starts = page_offsets(doc_clone, content_h)
        page_count = max(1, len(starts))

        painter = QPainter(printer)
        if not painter.isActive():
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        font_hf = QFont("sans-serif", 9)
        color_hf = QColor(print_style.PAPER_MUTED)
        color_rule = QColor(print_style.PAPER_RULE)
        full_page = QRectF(0, 0, full_rect.width(), full_rect.height())
        first_number = int(cfg.get("page_number_start", 1) or 1)
        page_top = paint_rect.y()

        try:
            for page_idx in range(page_count):
                if page_idx > 0:
                    printer.newPage()

                # Den här sidans vänstermarginal. Speglade marginaler växlar
                # inner/ytter mellan sidorna (page_margins), så textblocket
                # flyttas i sidled — papperet är detsamma.
                page_left = paint_rect.x() + page_margins(cfg, page_idx)[0] * dpmm

                # Vit pappersbotten på varje sida — även om dokumentet är tomt
                painter.fillRect(full_page, QColor(print_style.PAPER_WHITE))

                page_num = first_number + page_idx
                skip_page = bool(cfg.get("skip_first_page", False)) and (page_idx == 0)

                # Formatera sidnumret
                fmt_type = cfg.get("page_number_format", "page_of_total")
                if fmt_type == "number":
                    page_str = str(page_num)
                elif fmt_type == "hyphen":
                    page_str = f"— {page_num} —"
                elif fmt_type == "slash":
                    page_str = f"{page_num} / {page_count}"
                else:  # "page_of_total"
                    page_str = _("pdf_page_n_of_total", n=page_num, total=page_count)

                num_pos = str(cfg.get("page_number_pos", "bottom-center"))

                # Bestäm justering för sidnumret
                if num_pos in ("bottom-alternating", "top-alternating"):
                    # Udda sidor till höger, jämna till vänster (bok/avhandlingsstandard)
                    is_right = (page_num % 2 == 1)
                    align_num = Qt.AlignmentFlag.AlignRight if is_right else Qt.AlignmentFlag.AlignLeft
                elif "right" in num_pos:
                    align_num = Qt.AlignmentFlag.AlignRight
                elif "left" in num_pos:
                    align_num = Qt.AlignmentFlag.AlignLeft
                else:
                    align_num = Qt.AlignmentFlag.AlignHCenter

                # --- 1. RITA SIDHUVUD (oskalat, i skrivarpixlar) ---
                if has_header and not skip_page:
                    painter.setFont(font_hf)
                    painter.setPen(color_hf)
                    header_rect = QRectF(page_left, page_top, content_w_px, header_h)

                    if cfg.get("header_text"):
                        painter.drawText(header_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, str(cfg.get("header_text")))

                    if "top" in num_pos and cfg.get("page_numbering", True):
                        painter.drawText(header_rect, align_num | Qt.AlignmentFlag.AlignTop, page_str)

                    # Tunn linje under sidhuvud
                    painter.setPen(QPen(color_rule, 0.75))
                    rule_y = page_top + header_h - (2 * dpmm)
                    painter.drawLine(QPointF(page_left, rule_y),
                                     QPointF(page_left + content_w_px, rule_y))

                # --- 2. RITA DOKUMENTSIDA (skalad till layoutenheterna) ---
                page_start = starts[page_idx] if page_idx < len(starts) else 0.0
                # Klipp mot aktuell sidas del av dokumentet. Höjden är **avståndet
                # till nästa ark**, inte alltid hela textytan: brytreglerna gör ett
                # ark upp till två rader kortare. Klippet sätts i skrivarpixlar
                # *före* skalningen — i det skalade, flyttade rummet låg det fel.
                nästa_start = starts[page_idx + 1] if page_idx + 1 < len(starts) else None
                klipp_höjd = (content_h if nästa_start is None
                              else min(content_h, max(1.0, nästa_start - page_start)))
                page_clip = QRectF(0, page_start, content_w, klipp_höjd)

                painter.save()
                painter.setClipRect(QRectF(page_left, page_top + header_h,
                                           content_w_px, klipp_höjd * rit_skala))
                painter.scale(rit_skala, rit_skala)
                # Flytta origo till sidans innehållsyta, i layoutenheter
                painter.translate(page_left / rit_skala,
                                  (page_top + header_h) / rit_skala - page_start)

                ctx = QAbstractTextDocumentLayout.PaintContext()
                ctx.clip = page_clip
                ctx.cursorPosition = -1
                ctx.palette = print_style.paper_palette()
                layout = doc_clone.documentLayout()
                if layout is not None:
                    layout.draw(painter, ctx)
                painter.restore()

                # Sudda bort det som ritades förbi arkets sista rad. `layout.draw`
                # klipper på **blocknivå**: ett block som börjar innanför kanten
                # ritas i sin helhet, även den del som hör till nästa ark (mätt:
                # 133 rubriker i en PDF med 120).
                if klipp_höjd < content_h - 0.5:
                    painter.fillRect(
                        QRectF(page_left, page_top + header_h + klipp_höjd * rit_skala,
                               content_w_px, (content_h - klipp_höjd) * rit_skala),
                        QColor(print_style.PAPER_WHITE))

                # --- 3. RITA SIDFOT (oskalat, i skrivarpixlar) ---
                if has_footer and not skip_page:
                    painter.setFont(font_hf)
                    painter.setPen(color_hf)
                    footer_y = page_top + header_h + content_h_px + (2 * dpmm)
                    footer_rect = QRectF(page_left, footer_y, content_w_px, footer_h)

                    # Tunn linje ovanför sidfot
                    painter.setPen(QPen(color_rule, 0.75))
                    painter.drawLine(QPointF(page_left, footer_y),
                                     QPointF(page_left + content_w_px, footer_y))

                    if cfg.get("footer_text"):
                        painter.drawText(footer_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(cfg.get("footer_text")))

                    if "bottom" in num_pos and cfg.get("page_numbering", True):
                        painter.drawText(footer_rect, align_num | Qt.AlignmentFlag.AlignVCenter, page_str)

        finally:
            painter.end()

    @staticmethod
    def _hyphenate_clone(doc, lang: str = "sv") -> int:
        """Sätter mjuka bindestreck i den tryckta kopian (R05.11).

        Görs *före* sidantalet räknas, annars hamnar avstavningen utanför
        måtten. Fragment för fragment, så att fet och kursiv står kvar — och
        aldrig i bilder. Returnerar antalet stycken som ändrades.
        """
        from core.autocorrect import soft_hyphenate

        ändrade = 0
        block = doc.begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid() and not fragment.charFormat().isImageFormat():
                    mjuk = soft_hyphenate(fragment.text(), lang)
                    if mjuk != fragment.text():
                        markör = QTextCursor(doc)
                        markör.setPosition(fragment.position())
                        markör.setPosition(fragment.position() + fragment.length(),
                                           QTextCursor.MoveMode.KeepAnchor)
                        markör.insertText(mjuk, fragment.charFormat())
                        ändrade += 1
                iterator += 1
            block = block.next()
        return ändrade

    @staticmethod
    def _docx_style(doc, stil: str) -> str:
        """Stilens namn, och skapar den om mallen inte har den (R05.7, 5.14).

        `Quote` finns i Words standardmall, en kodstil gör det inte. Att skapa
        den i stället för att formatera stycket direkt är hela poängen: en
        redaktör ska kunna restyla bokens kodblock i ett svep.
        """
        if stil in {s.name for s in doc.styles}:
            return stil
        ny = doc.styles.add_style(stil, WD_STYLE_TYPE.PARAGRAPH)
        ny.font.name = DOCX_CODE_FONT
        # De typografiska textelementen har var sin form (5.14): en scenbrytning
        # är centrerad, versen indragen utan första radens indrag, meddelandet en
        # smalare spalt i fast bredd. Utan det blir de tre stilarna lika tomma.
        if stil == "Scene Break":
            ny.font.name = None
            ny.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
            ny.paragraph_format.space_before = Pt(10)
            ny.paragraph_format.space_after = Pt(10)
        elif stil == "Verse":
            ny.font.name = None
            ny.font.italic = True
            ny.paragraph_format.left_indent = Cm(1.6)
            ny.paragraph_format.first_line_indent = Cm(0)
            ny.paragraph_format.space_after = Pt(10)
        elif stil == "Message":
            ny.paragraph_format.left_indent = Cm(1.2)
            ny.paragraph_format.right_indent = Cm(2.4)
            ny.paragraph_format.space_after = Pt(4)
            ny.font.size = Pt(9.5)
        return stil

    @staticmethod
    def _force_black_styles(doc) -> int:
        """Sätter svart på samtliga stilar i Word-mallen.

        Word-mallens inbyggda stilar bär kulörta färger (blå rubriker, blå
        länkar, grön "Intense Quote"). Även om dokumentet bara använder några
        få av dem ligger de kvar i filen och kan plockas fram av den som
        öppnar den. Här sätts svart på varje stil som har ett typsnitt, så
        filen inte innehåller någon kulör alls.
        """
        if docx is None:
            return 0
        from docx.shared import RGBColor as _RGB

        changed = 0
        for style in doc.styles:
            font = getattr(style, "font", None)
            if font is None:
                continue
            try:
                font.color.rgb = _RGB(0, 0, 0)
                changed += 1
            except (AttributeError, ValueError, TypeError):
                continue
        return changed

    @staticmethod
    def _export_clone(text_document: QTextDocument, page_settings: dict | None) -> QTextDocument:
        """Klon för export, rensad — och i stor stil — om inställningarna vill det."""
        cfg = DEFAULT_PAGE_SETTINGS.copy()
        if page_settings:
            cfg.update(page_settings)
        clone = text_document.clone()
        if clone is None:
            return text_document
        if cfg.get("clean_print", True):
            print_style.normalize_document(
                clone, grayscale_images=bool(cfg.get("grayscale_images", False))
            )
        # Large print (5.16): samma bok i större grad. Efter reningen, så att
        # skalningen gäller den form som faktiskt skrivs ut.
        if cfg.get("large_print"):
            print_style.scale_for_large_print(clone)
        return clone

    @staticmethod
    def save_file(filepath, text_document: QTextDocument, colors=None, page_settings: dict = None):
        """Saves a QTextDocument to a file (.docx, .md, .html, .txt, .pdf) preserving all formatting."""
        ext = os.path.splitext(filepath)[1].lower()
        cfg = DEFAULT_PAGE_SETTINGS.copy()
        if page_settings:
            cfg.update(page_settings)
        clean = bool(cfg.get("clean_print", True))

        if ext == ".docx":
            if docx is None:
                raise ImportError("python-docx is required to write .docx files.")
            doc = docx.Document()
            # Sidmåtten in i filen. Utan dem ärver Word-mallen Letter — en 6x9-bok
            # öppnades som Letter i Word medan PDF:en var 6x9.
            from docx.shared import Mm
            from core.publishing import mirrored_margins

            w_mm, h_mm = page_format.page_mm(cfg)
            left_mm, right_mm = mirrored_margins(cfg)
            for section in doc.sections:
                section.page_width, section.page_height = Mm(w_mm), Mm(h_mm)
                section.top_margin = Mm(float(cfg.get("margin_top_mm", 20.0)))
                section.bottom_margin = Mm(float(cfg.get("margin_bottom_mm", 20.0)))
                section.left_margin, section.right_margin = Mm(left_mm), Mm(right_mm)
            if clean:
                # Word-mallens rubrikstilar är blå. Direkt formatering på
                # stilen själv gör att rubrikerna blir svarta i hela filen,
                # även i navigeringsfönstret och innehållsförteckningen.
                DocumentManager._force_black_styles(doc)
            export_doc = DocumentManager._export_clone(text_document, page_settings)
            block = export_doc.begin()
            
            while block.isValid():
                fmt = block.blockFormat()
                heading_level = fmt.headingLevel()
                alignment = fmt.alignment()
                text_list = block.textList()
                roll = richtext.block_role(block)
                
                if heading_level == 1:
                    p = doc.add_heading(level=1)
                elif heading_level == 2:
                    p = doc.add_heading(level=2)
                elif heading_level == 3:
                    p = doc.add_heading(level=3)
                elif text_list is not None:
                    p = doc.add_paragraph(style="List Bullet")
                else:
                    # Rollen (citat, kod) blir en *namngiven* Word-stil, inte
                    # direkt formatering: redaktören ska kunna restyla hela
                    # boken med ett klick, och stilnamnen är språkoberoende i
                    # filen — Word visar dem på svenska ändå.
                    stil = DOCX_ROLE_STYLES.get(roll)
                    p = doc.add_paragraph(
                        style=DocumentManager._docx_style(doc, stil)) if stil else doc.add_paragraph()
                    
                if alignment & Qt.AlignmentFlag.AlignHCenter:
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                elif alignment & Qt.AlignmentFlag.AlignRight:
                    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                elif alignment & Qt.AlignmentFlag.AlignJustify:
                    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                elif alignment & Qt.AlignmentFlag.AlignLeft:
                    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    
                it = block.begin()
                while not it.atEnd():
                    frag = it.fragment()
                    if frag.isValid():
                        raw_txt = frag.text()
                        txt = raw_txt.replace('\ufffc', '')
                        if txt:
                            char_fmt = frag.charFormat()
                            # I en vers och ett meddelande betyder radbrytningen
                            # något: den blir ett riktigt radbrott i Word, inte
                            # ett mellanslag (5.14).
                            bitar = (txt.split("\u2028")
                                     if roll in (richtext.ROLE_VERSE, richtext.ROLE_MESSAGE)
                                     else [txt])
                            run = p.add_run(bitar[0])
                            for bit in bitar[1:]:
                                run.add_break()
                                run.add_text(bit)
                            
                            if char_fmt.fontWeight() >= 600 or char_fmt.font().bold():
                                run.bold = True
                            if char_fmt.fontItalic():
                                run.italic = True
                            if char_fmt.fontUnderline():
                                run.underline = True
                            if char_fmt.fontStrikeOut():
                                run.font.strike = True
                            try:
                                fam = char_fmt.font().family()
                                if fam and fam.lower() not in {"default", "sans-serif", "serif"}:
                                    run.font.name = fam
                            except Exception:
                                pass
                            pt_sz = char_fmt.fontPointSize()
                            if pt_sz > 0:
                                run.font.size = Pt(pt_sz)
                            fg = char_fmt.foreground().color()
                            if fg.isValid():
                                safe = print_style.clean_foreground(fg) if clean else fg.name()
                                if safe != print_style.PAPER_TEXT:
                                    sc = QColor(safe)
                                    run.font.color.rgb = RGBColor(sc.red(), sc.green(), sc.blue())
                                
                    it += 1
                block = block.next()
                
            doc.save(filepath)
            if clean:
                # Städa filen på nytt: python-docx når inte de kopplade
                # teckenstilarna, men XML:en innehåller dem.
                print_style.neutralize_docx(filepath)

        elif ext == ".pdf":
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(filepath)
            DocumentManager.print_document_to_printer(text_document, printer, page_settings)

        elif ext in {".html", ".htm"}:
            export_doc = DocumentManager._export_clone(text_document, page_settings)
            html = print_style.clean_html(export_doc) if clean else export_doc.toHtml()
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html)

        elif ext in {".md", ".markdown"}:
            md_text = DocumentManager.document_to_markdown(text_document)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(md_text)

        else:  # .txt or plain text
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(text_document.toPlainText())

    @staticmethod
    def document_to_markdown(text_document: QTextDocument) -> str:
        """Converts a QTextDocument to rich Markdown preserving headings, bold, italic, strike, lists, quotes."""
        md_lines = []
        block = text_document.begin()
        
        while block.isValid():
            if richtext.block_role(block) == richtext.ROLE_CODE:
                lang = richtext.lang_of(block.blockFormat())
                code_lines = []
                while block.isValid() and richtext.block_role(block) == richtext.ROLE_CODE:
                    if not lang:
                        lang = richtext.lang_of(block.blockFormat())
                    code_lines.append(block.text())
                    block = block.next()
                while code_lines and not code_lines[0].strip():
                    code_lines.pop(0)
                while code_lines and not code_lines[-1].strip():
                    code_lines.pop()
                md_lines.append(f"```{lang}\n" + "\n".join(code_lines) + "\n```\n")
                continue

            fmt = block.blockFormat()
            heading_level = fmt.headingLevel()
            text_list = block.textList()
            role = richtext.block_role(block)
            is_quote = role == richtext.ROLE_QUOTE or (not role and fmt.leftMargin() >= 20)
            
            prefix = ""
            if heading_level == 1:
                prefix = "# "
            elif heading_level == 2:
                prefix = "## "
            elif heading_level == 3:
                prefix = "### "
            elif text_list is not None:
                prefix = "* "
            elif is_quote:
                prefix = "> "
                
            line_parts = []
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    txt = frag.text().replace('\ufffc', '')
                    if txt:
                        cf = frag.charFormat()
                        # Versens och meddelandets radbrytningar är innehåll, inte
                        # radbrytning: i markdown blir de en hård radbrytning med
                        # två avslutande blanksteg (5.14).
                        if role in (richtext.ROLE_VERSE, richtext.ROLE_MESSAGE):
                            txt = txt.replace("\u2028", "  \n")
                        is_bold = (cf.fontWeight() >= 600 or cf.font().bold()) \
                            and heading_level not in (1, 2, 3)
                        # Kursiven i versen och citatet bärs av *stilen* (CSS,
                        # Word-stilen, teckenformen) — markdown skall inte
                        # dessutom sätta stjärnor runt varje rad (5.14).
                        is_italic = cf.fontItalic() and role not in (
                            richtext.ROLE_QUOTE, richtext.ROLE_VERSE)
                        is_strike = cf.fontStrikeOut()
                        is_underline = cf.fontUnderline()
                        
                        part = txt
                        if is_bold and is_italic:
                            part = f"***{part}***"
                        elif is_bold:
                            part = f"**{part}**"
                        elif is_italic:
                            part = f"*{part}*"
                        elif is_underline:
                            part = f"_{part}_"
                        if is_strike:
                            part = f"~~{part}~~"
                        line_parts.append(part)
                it += 1
                
            line_str = "".join(line_parts)
            if prefix and line_str:
                md_lines.append(f"{prefix}{line_str}\n")
            elif line_str:
                md_lines.append(f"{line_str}\n")
            else:
                md_lines.append("\n")
                
            block = block.next()
            
        full_md = "\n".join(md_lines)
        full_md = re.sub(r'\n{3,}', '\n\n', full_md)
        return full_md.strip() + "\n"
