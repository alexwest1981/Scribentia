"""Paper sizes, modelled the way Writer models them.

Measured in LibreOffice 26.8 (Writer, headless over UNO):

* a page size lives on the **page style**, not on the document frame: `Width` and
  `Height` are two numbers in 1/100 mm and `IsLandscape` is a separate flag — setting
  the flag does not swap the numbers (read back 14801 x 21001 with the flag on);
* the file stores the paper as well: `fo:page-width`/`fo:page-height` hold the portrait
  numbers and `style:print-orientation="landscape"` carries the rotation;
* the paper tray is the only printer-dependent choice (`PrinterPaperTray` defaults to
  "[From printer settings]"); the size itself is always explicit;
* the size drives pagination, it does not scale the text: the same 400-line body came
  out as 8 pages on A4 and 12 pages on A5;
* an impossible size is kept as asked (60 x 60 mm with 40 mm margins stays 60 x 60 mm,
  printable width -2001) — Writer never enlarges the paper to fit.

`PAPER_MM` holds the portrait numbers per name and `page_mm()` is the only place the
orientation flag is applied. Every channel that needs a size reads it from there, so
the paper on screen, the PDF and the DOCX cannot disagree.
"""

PAPER_MM = {
    "A3": (297.0, 420.0),
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "A6": (105.0, 148.0),
    "B5": (176.0, 250.0),
    "Letter": (215.9, 279.4),
    "Legal": (215.9, 355.6),
    "Tabloid": (279.4, 431.8),
}

# The order the page dialog lists them in: ISO first, then the US series.
ORDER = ("A3", "A4", "A5", "A6", "B5", "Letter", "Legal", "Tabloid")
CUSTOM = "Custom"
DEFAULT = "A4"


def page_mm(settings: dict | None) -> tuple[float, float]:
    """The paper in millimetres, orientation already applied.

    `page_size` may name a format, or be anything else ("Custom", a trim like "6x9"):
    then the numbers in `custom_width_mm`/`custom_height_mm` are the size, and a
    missing number falls back to A4 rather than to zero.
    """
    cfg = settings or {}
    name = str(cfg.get("page_size") or DEFAULT)
    if name in PAPER_MM:
        w_mm, h_mm = PAPER_MM[name]
    else:
        w_mm = float(cfg.get("custom_width_mm") or PAPER_MM[DEFAULT][0])
        h_mm = float(cfg.get("custom_height_mm") or PAPER_MM[DEFAULT][1])
    if str(cfg.get("orientation") or "portrait") == "landscape":
        return (h_mm, w_mm)
    return (w_mm, h_mm)


def preset_name(settings: dict | None) -> str:
    """The named format these settings mean, or `CUSTOM`.

    A trim profile (6 x 9 in, 152.4 x 228.6 mm) matches no named paper and must not
    pretend to: the dialog then shows the numbers in its own fields.
    """
    cfg = settings or {}
    name = str(cfg.get("page_size") or DEFAULT)
    if name in PAPER_MM:
        return name
    w_mm, h_mm = cfg.get("custom_width_mm"), cfg.get("custom_height_mm")
    for known, (kw, kh) in PAPER_MM.items():
        if w_mm and h_mm and abs(float(w_mm) - kw) < 0.2 and abs(float(h_mm) - kh) < 0.2:
            return known
    return CUSTOM


def _self_check() -> int:
    kontroller = []

    def check(name, ok, detail=""):
        kontroller.append(bool(ok))
        print(("  ok  " if ok else "  FEL ") + name + (f" ({detail})" if detail else ""))

    check("A4 stående är 210 x 297 mm", page_mm({"page_size": "A4"}) == (210.0, 297.0))
    check("A4 liggande byter plats på måtten",
          page_mm({"page_size": "A4", "orientation": "landscape"}) == (297.0, 210.0))
    check("ett okänt namn faller tillbaka på A4",
          page_mm({"page_size": "Ingenting"}) == (210.0, 297.0))
    check("Custom utan mått blir A4, aldrig noll",
          page_mm({"page_size": CUSTOM}) == (210.0, 297.0))
    check("Custom med mått blir de måtten",
          page_mm({"page_size": CUSTOM, "custom_width_mm": 152.4,
                   "custom_height_mm": 228.6}) == (152.4, 228.6))
    check("ett tryckmått (6x9) läses ur talen, inte ur namnet",
          page_mm({"page_size": "6x9", "custom_width_mm": 152.4,
                   "custom_height_mm": 228.6}) == (152.4, 228.6))
    check("tomma inställningar är A4", page_mm(None) == (210.0, 297.0))
    check("preset_name känner igen A5", preset_name({"page_size": "A5"}) == "A5")
    check("preset_name visar inte ett påhittat namn för 6x9",
          preset_name({"page_size": "6x9", "custom_width_mm": 152.4,
                       "custom_height_mm": 228.6}) == CUSTOM)
    check("varje format i listan har en storlek",
          all(n in PAPER_MM for n in ORDER))
    check("A4 i tabellen är det A4 tabellen lovar",
          PAPER_MM["A4"] == (210.0, 297.0) and round(297 / 210, 3) == 1.414)

    print(f"page_format: {sum(kontroller)} av {len(kontroller)} kontroller gröna")
    return 0 if all(kontroller) else 1


if __name__ == "__main__":
    raise SystemExit(_self_check())
