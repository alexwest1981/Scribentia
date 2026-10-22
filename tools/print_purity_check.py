#!/usr/bin/env python3
"""tools/print_purity_check.py — mäter om Scribentias genererade filer är "rena".

Kontraktet som mäts (inte påstås):

  1. PDF: varje pixel i varje renderad sida ska vara akromatisk (R=G=B).
     Sidans hörn ska vara ren vit (255,255,255) och dokumentet ska nå svart
     text (luminans <= 40 vid 300 dpi), annars är den "rena" sidan bara tom.
  2. HTML-export: inga färgdeklarationer med kroma; bakgrund vit, text svart.
  3. DOCX-export: ingen teckenfärg och ingen skuggning med kroma.

Scenarier:

  A. Värsta fallet: kod/citat formaterade med ett mörkt programtema, markerad
     text, temafärgad tabellrubrik och ett diagram — allt programgenererat.
  B. Samtliga inbyggda mallar, en i taget.
  C. Editorns egen väg: `DocumentCanvas.insert_chart()` med en färgpalett.
  D. Fotot: importerat foto är *innehåll*, inte formatering. Det mäts separat
     och fäller inte kontraktet — men det får inte smitta sidbakgrunden.

Kör:  QT_QPA_PLATFORM=offscreen .venv/bin/python tools/print_purity_check.py
"""

import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np

# setdefault räcker inte: skalet ärver Alex egen QT_QPA_PLATFORM, och då öppnar
# provet riktiga fönster över hans arbete. Tvinga offscreen (se ui_smoke.py).
if not os.environ.get("SCRIBENTIA_SHOW_WINDOWS"):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtGui import (  # noqa: E402
    QTextDocument, QTextCursor, QTextCharFormat, QTextBlockFormat,
    QTextTableFormat, QImage, QColor,
)

from core.doc_manager import DocumentManager, DEFAULT_PAGE_SETTINGS  # noqa: E402
from core.charts import ChartRenderer  # noqa: E402
from core import richtext, templates, print_style  # noqa: E402
from core.i18n import i18n  # noqa: E402

i18n.set_language("sv")   # mallarna är svenska; sidfoten ska vara det också

DPI = 300
CHROMA_TOLERANCE = 2          # tillåten avvikelse mellan kanalerna (antialiasing)
WHITE = 255
BLACK_LUMINANCE_MAX = 40      # dokumentet måste faktiskt ha svart text

HEX_RE = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")
RGB_RE = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", re.I)

DARK_THEME = {
    "code_bg": "#12151c", "code_text": "#e2e8f0", "text_color": "#f8fafc",
    "text_muted": "#94a3b8", "sidebar_card": "#212633",
}


def chroma_of(rgb) -> int:
    return int(max(rgb) - min(rgb))


def parse_color(token: str):
    """'#1e293b' / 'rgb(30,41,59)' / 'rgba(...)' -> (r,g,b) eller None."""
    token = token.strip()
    m = HEX_RE.search(token)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = RGB_RE.search(token)
    if m:
        return tuple(int(g) for g in m.groups())
    return None


# ------------------------------------------------------------------ dokument
def build_kitchen_sink() -> QTextDocument:
    """Programgenererat värsta fall: mörkt tema inbakat i dokumentets format."""
    doc = QTextDocument()
    doc.setHtml(templates.get_template_html("report", lang="sv"))

    cursor = QTextCursor(doc)
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertBlock(QTextBlockFormat(), QTextCharFormat())
    cursor.insertText("Kod och citat nedan är formaterade med ett mörkt programtema:")
    cursor.insertBlock()
    cursor.insertText("def analys(serie):\n    return sum(serie) / len(serie)")
    block = cursor.block()
    richtext.apply_role_to_blocks(doc, block.blockNumber(), block.blockNumber(),
                                  richtext.ROLE_CODE, DARK_THEME, "python")
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertBlock()
    cursor.insertText("Ett citat som temats textfärg har färgat.")
    ci = cursor.block().blockNumber()
    richtext.apply_role_to_blocks(doc, ci, ci, richtext.ROLE_QUOTE, DARK_THEME)

    # Markeringsfärg (gul text på lila botten) — användarens eget val
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertBlock()
    cursor.insertText("Överstruken markeringstext")
    sel = QTextCursor(doc)
    sel.setPosition(cursor.block().position())
    sel.setPosition(cursor.block().position() + cursor.block().length() - 1,
                    QTextCursor.MoveMode.KeepAnchor)
    hl = QTextCharFormat()
    hl.setBackground(QColor("#fff59d"))
    hl.setForeground(QColor("#7c3aed"))
    sel.mergeCharFormat(hl)

    # Tabell med temafärgad rubrikrad och kulört ramverk
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertBlock()
    tfmt = QTextTableFormat()
    tfmt.setBorder(1)
    tfmt.setBorderBrush(QColor("#2563eb"))
    tfmt.setCellPadding(6)
    table = cursor.insertTable(2, 2, tfmt)
    if table is not None:
        hc = QTextCharFormat()
        hc.setBackground(QColor("#dbeafe"))
        for col in range(2):
            table.cellAt(0, col).firstCursorPosition().insertText("Rubrik", hc)
            table.cellAt(1, col).firstCursorPosition().insertText("Värde")

    # Diagram i färg, precis som diagramdialogen kan skapa dem. Dialogen
    # infogar via DocumentCanvas.insert_chart(), som märker bilden som ett
    # Scribentia-diagram — märkningen görs här på samma sätt.
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertBlock()
    chart = ChartRenderer.render(
        "bar", "Mätvärden", ["A", "B", "C"],
        [{"name": "Serie 1", "values": [4, 7, 3]}],
        palette="modern_blue", width=520, height=300,
    )
    cursor.insertImage(chart)
    block = cursor.block()
    it = block.begin()
    while not it.atEnd():
        frag = it.fragment()
        if frag.isValid() and frag.charFormat().isImageFormat():
            fmt = print_style.mark_as_generated_chart(QTextCharFormat(frag.charFormat()))
            sel = QTextCursor(doc)
            sel.setPosition(frag.position())
            sel.setPosition(frag.position() + frag.length(), QTextCursor.MoveMode.KeepAnchor)
            sel.setCharFormat(fmt)
            break
        it += 1
    return doc


def build_document_with_photo() -> QTextDocument:
    doc = build_kitchen_sink()
    photo = QImage(120, 80, QImage.Format.Format_RGB32)
    for y in range(80):
        for x in range(120):
            photo.setPixelColor(x, y, QColor(200, 40, 90) if (x + y) % 7 else QColor(30, 160, 90))
    cursor = QTextCursor(doc)
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertBlock()
    cursor.insertImage(photo)
    return doc


_KEEP_ALIVE: list = []                 # canvasten äger dokumentet; håll den vid liv


def build_editor_chart_document() -> QTextDocument:
    """Editorns egen väg: infogning via DocumentCanvas.insert_chart()."""
    from ui.editor_view import DocumentCanvas

    canvas = DocumentCanvas()          # offscreen, visas aldrig
    _KEEP_ALIVE.append(canvas)
    canvas.set_block_colors(print_style.paper_colors())
    canvas.insert_page_break()
    canvas.insertHtml("<p>Diagram infogat via editorn:</p>")

    def render(pal: str):
        return ChartRenderer.render(
            "pie", "Färgval i editorn", ["Del A", "Del B", "Del C"],
            [{"name": "Serie", "values": [3, 5, 2]}],
            palette=pal, width=520, height=300,
        )

    # Precis som ChartDialog: färgbilden för skärmen och en gråskaleversion av
    # samma data som exporten byter till.
    canvas.insert_chart(render("warm_sunset"), align="center", mono_image=render("mono"))
    doc = canvas.document()
    return doc if doc is not None else QTextDocument()


# ------------------------------------------------------------------ analys
def image_to_array(img: QImage) -> np.ndarray:
    """Pixlarna som (h, w, 3) uint8. Kopian är nödvändig: vyn nedan pekar in i
    QImage:s minne, som frigörs så snart funktionen returnerar."""
    img = img.convertToFormat(QImage.Format.Format_RGB888)
    w, h = img.width(), img.height()
    buf = img.constBits()
    if buf is None:
        return np.zeros((h, w, 3), np.uint8)
    buf.setsize(img.sizeInBytes())
    arr = np.frombuffer(buf, np.uint8).reshape(h, img.bytesPerLine())  # type: ignore[arg-type]
    return np.array(arr[:, :w * 3].reshape(h, w, 3), copy=True)


def analyse_pdf(pdf_path: Path, keep_pages_in: Path | None = None) -> dict:
    pages_dir = keep_pages_in or Path(tempfile.mkdtemp(prefix="scribentia-pages-"))
    subprocess.run(
        ["pdftoppm", "-r", str(DPI), "-png", str(pdf_path), str(pages_dir / "page")],
        check=True,
    )
    pages = sorted(pages_dir.glob("page*.png"))
    if not pages:
        raise RuntimeError(f"Kunde inte rendera {pdf_path}")

    chromatic_total = 0
    pixel_total = 0
    corners_ok = True
    darkest = 255
    top_colors: dict[tuple, int] = {}
    white_shares = []
    for p in pages:
        arr = image_to_array(QImage(str(p)))
        pixel_total += arr.shape[0] * arr.shape[1]
        chroma = arr.max(axis=2).astype(np.int16) - arr.min(axis=2).astype(np.int16)
        mask = chroma > CHROMA_TOLERANCE
        chromatic_total += int(mask.sum())
        for rgb in np.unique(arr[mask].reshape(-1, 3), axis=0)[:400]:
            key = tuple(int(v) for v in rgb)
            top_colors[key] = top_colors.get(key, 0) + 1
        for corner in (arr[0, 0], arr[0, -1], arr[-1, 0], arr[-1, -1]):
            if tuple(int(v) for v in corner) != (WHITE, WHITE, WHITE):
                corners_ok = False
        white_shares.append(float((arr == WHITE).all(axis=2).mean()))
        darkest = min(darkest, int(arr.mean(axis=2).min()))

    return {
        "pages": len(pages),
        "chromatic_pixels": chromatic_total,
        "pixel_total": pixel_total,
        "chromatic_share": chromatic_total / max(1, pixel_total),
        "corners_white": corners_ok,
        "darkest_luminance": darkest,
        "white_share": sum(white_shares) / len(white_shares),
        "top_chromatic": sorted(top_colors.items(), key=lambda kv: -kv[1])[:6],
    }


def analyse_html(html_path: Path) -> dict:
    text = html_path.read_text(encoding="utf-8")
    findings = []
    for prop, value in re.findall(r"([a-z-]+)\s*:\s*([^;\"'<>]+)", text, re.I):
        prop = prop.lower()
        if "color" not in prop and prop not in {"background", "border", "border-left", "border-top"}:
            continue
        rgb = parse_color(value)
        if rgb and chroma_of(rgb) > CHROMA_TOLERANCE:
            findings.append((prop, value.strip()))
    has_white_bg = bool(re.search(r"background(-color)?\s*:\s*#fff(fff)?\b", text, re.I))
    return {"chromatic_declarations": findings, "explicit_white_background": has_white_bg}


def analyse_docx(docx_path: Path) -> dict:
    """Färger i själva innehållet OCH i stilarna.

    Word skriver alltid en färgpalett i ``word/theme/theme1.xml`` — den är en
    del av formatets infrastruktur och renderar ingenting i sig själv. Det som
    mäts här är vad dokumentet och dess stilar faktiskt pekar ut: ``w:color``
    och ``w:fill`` i ``document.xml`` och ``styles.xml``.
    """
    with zipfile.ZipFile(docx_path) as z:
        names = z.namelist()
        doc_xml = z.read("word/document.xml").decode("utf-8", "replace")
        styles_xml = z.read("word/styles.xml").decode("utf-8", "replace") if "word/styles.xml" in names else ""

    def chromatic_colors(xml: str) -> list[tuple[str, str]]:
        out = []
        for val in re.findall(r'w:color\s+w:val="([0-9A-Fa-f]{6})"', xml):
            rgb = tuple(int(val[i:i + 2], 16) for i in (0, 2, 4))
            if chroma_of(rgb) > CHROMA_TOLERANCE:
                out.append(("w:color", val))
        for val in re.findall(r'w:fill="([0-9A-Fa-f]{6})"', xml):
            rgb = tuple(int(val[i:i + 2], 16) for i in (0, 2, 4))
            if chroma_of(rgb) > CHROMA_TOLERANCE:
                out.append(("w:fill", val))
        return out

    return {"document": chromatic_colors(doc_xml), "styles": chromatic_colors(styles_xml)}


# ------------------------------------------------------------------ körning
class Report:
    def __init__(self):
        self.failures: list[str] = []
        self.checks = 0

    def check(self, ok: bool, label: str):
        self.checks += 1
        if not ok:
            self.failures.append(label)

    def pdf(self, name: str, pdf: Path, *, with_photos: bool = False) -> dict:
        stats = analyse_pdf(pdf)
        verdict = "REN" if stats["chromatic_pixels"] == 0 else "FÄRG"
        print(f"  {name:<28} {stats['pages']} sid, {stats['pixel_total']:>9} px, "
              f"färgade {stats['chromatic_pixels']:>6} ({stats['chromatic_share'] * 100:.4f} %), "
              f"vitt {stats['white_share'] * 100:5.2f} %, mörkast {stats['darkest_luminance']:>3}  -> {verdict}")
        if stats["top_chromatic"]:
            print(f"      vanligaste färger: {[c for c, _ in stats['top_chromatic']]}")
        if with_photos:
            return stats
        self.check(stats["chromatic_pixels"] == 0, f"{name}: PDF innehåller färgade pixlar")
        self.check(stats["corners_white"], f"{name}: PDF-sidans hörn är inte vita")
        self.check(stats["darkest_luminance"] <= BLACK_LUMINANCE_MAX,
                   f"{name}: PDF saknar svart text (mörkast {stats['darkest_luminance']})")
        return stats

    def sources(self, name: str, html: Path, docx: Path):
        html_stats = analyse_html(html)
        docx_stats = analyse_docx(docx)
        bad_html = len(html_stats["chromatic_declarations"])
        bad_docx = len(docx_stats["document"])
        bad_styles = len(docx_stats["styles"])
        print(f"  {name:<28} HTML-färger {bad_html}, DOCX-färger {bad_docx}, "
              f"DOCX-stilfärger {bad_styles}, vit bakgrund "
              f"{'ja' if html_stats['explicit_white_background'] else 'NEJ'}")
        for prop, val in html_stats["chromatic_declarations"][:4]:
            print(f"      HTML {prop}: {val}")
        for prop, val in docx_stats["document"][:4]:
            print(f"      DOCX {prop}={val}")
        self.check(bad_html == 0, f"{name}: HTML-export innehåller färgdeklarationer")
        self.check(bad_docx == 0, f"{name}: DOCX-export innehåller färger")
        self.check(bad_styles == 0, f"{name}: DOCX-rubrikstilar innehåller färger")


def export_all(doc: QTextDocument, out: Path, stem: str) -> tuple[Path, Path, Path]:
    pdf, html, dx = out / f"{stem}.pdf", out / f"{stem}.html", out / f"{stem}.docx"
    DocumentManager.save_file(str(pdf), doc, page_settings=DEFAULT_PAGE_SETTINGS)
    DocumentManager.save_file(str(html), doc, page_settings=DEFAULT_PAGE_SETTINGS)
    DocumentManager.save_file(str(dx), doc, page_settings=DEFAULT_PAGE_SETTINGS)
    return pdf, html, dx


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    out = Path(tempfile.mkdtemp(prefix="scribentia-purity-"))
    rep = Report()

    print("=" * 78)
    print(f"Scribentia — renhetskontroll av genererade filer (PDF renderad i {DPI} dpi)")
    print("=" * 78)

    print("\n[A] Programgenererat värsta fall (mörkt tema, markering, tabell, diagram)")
    pdf, html, dx = export_all(build_kitchen_sink(), out, "A_kitchen_sink")
    rep.pdf("A kitchen sink", pdf)
    rep.sources("A kitchen sink", html, dx)

    print("\n[B] Samtliga inbyggda mallar")
    for t in templates.TEMPLATES:
        doc = QTextDocument()
        doc.setHtml(templates.get_template_html(t["id"], lang="sv"))
        pdf, html, dx = export_all(doc, out, f"B_{t['id']}")
        rep.pdf(f"B {t['id']}", pdf)
        rep.sources(f"B {t['id']}", html, dx)

    print("\n[C] Editorns diagramväg (insert_chart med färgpalett)")
    pdf, html, dx = export_all(build_editor_chart_document(), out, "C_editor_chart")
    rep.pdf("C editorns diagram", pdf)
    rep.sources("C editorns diagram", html, dx)

    print("\n[D] Foto (innehåll, mäts separat — fäller inte kontraktet)")
    photo_doc = build_document_with_photo()
    photo_pdf = out / "D_med_foto.pdf"
    DocumentManager.save_file(str(photo_pdf), photo_doc, page_settings=DEFAULT_PAGE_SETTINGS)
    photo_stats = rep.pdf("D med foto", photo_pdf, with_photos=True)
    clean_stats = analyse_pdf(out / "A_kitchen_sink.pdf")
    from_photo = max(0, photo_stats["chromatic_pixels"] - clean_stats["chromatic_pixels"])
    print(f"      varav {from_photo} px kommer från fotot (tillåtet — bilder är innehåll)")

    print("\n" + "=" * 78)
    if rep.failures:
        print(f"RESULTAT: INTE RENT — {len(rep.failures)} av {rep.checks} kontroller föll")
        for f in rep.failures:
            print(f"  ✗ {f}")
    else:
        print(f"RESULTAT: RENT — samtliga {rep.checks} kontroller gröna")
    print(f"Filer för inspektion: {out}")
    print("=" * 78)
    return 1 if rep.failures else 0


if __name__ == "__main__":
    sys.exit(main())
