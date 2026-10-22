"""Kanalernas siffror — som data med källa (R05.1, R05.5, R05.6).

Det här är tabellen ur forskningen, inte påhittade tal. Varje värde bär sin
källa, och **kanalerna delar inte varandras koefficienter**: KDP har en
publicerad ryggbreddsformel, medan IngramSpark och Lulu hänvisar till produkt-
och sidantalsspecifika mallar. Där det inte finns ett belagt tal står det
"använd kanalens mall" i stället för en gissning — en författare som litar på en
felaktig ryggbredd får ett omslag som inte passar, och felet syns först i tryck.

Samma regel gäller marginalerna: gutter-trappan är KDP:s, och den används inte
för andra kanaler utan att säga det.

Ren Python utan Qt — `python core/publishing.py` provar hela tabellen.
"""

# Källorna i klartext, så att ett tal kan följas tillbaka till sitt ursprung.
SOURCES = {
    "kdp_print": "https://kdp.amazon.com/en_US/help/topic/GVBQ3CMEQW3W2VL6/",
    "kdp_manuscript": "https://kdp.amazon.com/en_US/help/topic/G201857950",
    "kdp_cover": "https://kdp.amazon.com/en_US/help/topic/G201953020",
    "ingramspark": "https://www.ingramspark.com/hubfs/downloads/file-creation-guide.pdf",
    "lulu": "https://assets.lulu.com/media/guides/en/lulu-book-creation-guide.pdf",
    "epub": "https://www.w3.org/TR/epub-33/",
    "epub_a11y": "https://www.w3.org/TR/epub-a11y/",
}

# Trim i millimeter. 6×9 är den vanliga romanstorleken i USA, A5 i Europa —
# 6×9 är belagd hos KDP, de andra är marknadsval (forskningens [resonemang]).
TRIMS = {
    "5x8": (127.0, 203.2),
    "6x9": (152.4, 228.6),
    "a5": (148.0, 210.0),
    "a4": (210.0, 297.0),
}

TRIM_NAMES = {
    "5x8": "5 × 8 tum", "6x9": "6 × 9 tum", "a5": "A5", "a4": "A4",
}

# Ryggbredd per sida, i millimeter. Bara KDP publicerar en formel.
KDP_PAPERS = {
    "white": (0.0572, "svartvitt på vitt papper"),
    "cream": (0.0635, "svartvitt på crème papper"),
    "premium_color": (0.0596, "premiumfärg"),
    "standard_color": (0.0572, "standardfärg"),
}

# KDP:s gutter-trappa: (högsta sidantal, minsta innermarginal i mm).
KDP_GUTTER = ((150, 9.6), (300, 12.7), (500, 15.9), (700, 19.1), (828, 22.3))

BLOED_MM = 3.2            # 0,125 tum, KDP och Lulu
KDP_OUTER_MM = 6.4        # minsta ytterkant utan blöd
KDP_MIN_PAGES = 24        # minsta paperback
KDP_SPINE_TEXT_PAGES = 79 # först då får ryggtext plats
KDP_MIN_FONT_PT = 7

CHANNELS = {
    "kdp": {"label": "Amazon KDP", "print": True, "ebook": True, "formula": True,
            "source": "kdp_print"},
    "ingramspark": {"label": "IngramSpark", "print": True, "ebook": True, "formula": False,
                    "source": "ingramspark"},
    "lulu": {"label": "Lulu", "print": True, "ebook": True, "formula": False,
             "source": "lulu"},
    "apple": {"label": "Apple Books", "print": False, "ebook": True, "formula": False,
              "source": "epub"},
    "kobo": {"label": "Kobo", "print": False, "ebook": True, "formula": False,
             "source": "epub"},
}


def trim_mm(name: str):
    """Trimmets mått i millimeter, eller None."""
    return TRIMS.get((name or "").lower())


def gutter_mm(pages: int, channel: str = "kdp"):
    """Minsta innermarginal. Trappan är KDP:s och används bara för KDP."""
    if channel != "kdp":
        return None
    for gräns, mm in KDP_GUTTER:
        if pages <= gräns:
            return mm
    return KDP_GUTTER[-1][1]          # över 828 sidor: den sista trappan gäller


def spine_mm(pages: int, paper: str = "white", channel: str = "kdp"):
    """Ryggbredd i millimeter — bara där kanalen publicerar en formel."""
    if channel != "kdp" or paper not in KDP_PAPERS:
        return None
    return round(pages * KDP_PAPERS[paper][0], 2)


def cover_mm(trim: str, pages: int, paper: str = "white", bleed: bool = True,
             channel: str = "kdp"):
    """Omslagets totalmått (bredd, höjd) i millimeter, eller None.

    Baksida + rygg + framsida, plus blöd runt om när det behövs. Ryggbredden
    måste räknas om varje gång sidantalet eller pappret ändras — det är därför
    den här funktionen tar sidantalet och inte ett färdigt tal.
    """
    mått = trim_mm(trim)
    rygg = spine_mm(pages, paper, channel)
    if mått is None or rygg is None:
        return None
    bredd, höjd = mått
    blöd = BLOED_MM if bleed else 0.0
    return (round(blöd + bredd + rygg + bredd + blöd, 2), round(höjd + 2 * blöd, 2))


def page_settings_for(trim: str, pages: int, paper: str = "white", bleed: bool = False,
                      channel: str = "kdp", top_mm: float = 15.0, bottom_mm: float = 20.0,
                      large_print: bool = False):
    """Appens sidinställningar för en tryckprofil (R05.5).

    Inner- och yttermarginalen sätts var för sig och speglas sedan av
    utskriftsvägen — topp och botten är ett **val**, inte en kanalregel: ingen
    av kanalerna föreskriver dem, så de står som parametrar med en rimlig
    utgångspunkt (15 mm uppe, 20 mm nere, vilket ger plats åt folion).
    """
    if trim_mm(trim) is None:
        return None
    inner = gutter_mm(int(pages), channel)
    if inner is None:
        inner = 15.0                 # ingen belagd trappa: ett rimligt val, inte ett påstående
    # Avrundat till en tiondels millimeter: 6,4 + 3,2 blir 9,6 och inte
    # 9,600000000000001, och ett mått med femton decimaler är inte ett mått.
    ytter = round(KDP_OUTER_MM + (BLOED_MM if bleed else 0.0), 2)
    return {
        "page_size": "Custom",
        "custom_width_mm": trim_mm(trim)[0],
        "custom_height_mm": trim_mm(trim)[1],
        "margin_top_mm": top_mm,
        "margin_bottom_mm": bottom_mm,
        "margin_left_mm": inner,      # innermarginal (gutter) — udda sidor
        "margin_right_mm": ytter,     # ytterkant; speglas på jämna sidor
        "mirror_margins": True,
        "page_numbering": True,
        "page_number_pos": "bottom-alternating",
        "page_number_format": "number",
        "skip_first_page": True,
        # Stor stil (5.16): bok i större grad. En egen utgåva, inte en detalj —
        # sidantalet och därmed gutter och ryggbredd ändras av den.
        "large_print": bool(large_print),
    }


def page_margins(settings: dict, page_index: int = 0) -> tuple:
    """(vänster, topp, höger, botten) i millimeter för en sida.

    Speglade marginaler växlar inner/ytter mellan sidorna: udda sidor är
    högersidor (sidnummer 1, 3, 5 …) och har innermarginalen — guttern — till
    vänster; jämna sidor har den till höger. Texten är lika bred på båda, det är
    bara blocket som flyttas, och det är därför utskriften ritar sida för sida.

    Förut sattes samma marginal på båda sidor (max av de två), för att en riktig
    växling krävde en paginerad målare. Den finns nu: utskriftsvägen känner
    sidindex, så priset — en onödigt bred yttermarginal — behöver inte betalas.
    """
    vänster = float(settings.get("margin_left_mm", 20.0) or 20.0)
    höger = float(settings.get("margin_right_mm", 20.0) or 20.0)
    if settings.get("mirror_margins") and page_index % 2 == 1:
        vänster, höger = höger, vänster
    return (vänster,
            float(settings.get("margin_top_mm", 20.0) or 20.0),
            höger,
            float(settings.get("margin_bottom_mm", 20.0) or 20.0))


def mirrored_margins(settings: dict) -> tuple:
    """(vänster, höger) för en udda sida — kvar för äldre anrop."""
    vänster, _topp, höger, _botten = page_margins(settings, 0)
    return (vänster, höger)


def warnings(trim: str, pages: int, paper: str = "white", bleed: bool = False,
             channel: str = "kdp") -> list:
    """Det kanalen skulle klaga på, sagt innan filen skickas."""
    ut = []
    kanal = CHANNELS.get(channel) or {}
    if trim_mm(trim) is None:
        ut.append("trim_unknown")
    if channel == "kdp":
        if pages < KDP_MIN_PAGES:
            ut.append("kdp_min_pages")
        if pages % 2:
            ut.append("odd_pages")
        if pages and pages < KDP_SPINE_TEXT_PAGES:
            ut.append("no_spine_text")
        if pages > KDP_GUTTER[-1][0]:
            ut.append("over_last_gutter")
    if not kanal.get("formula"):
        ut.append("use_channel_template")
    if bleed and kanal.get("print") and channel != "kdp":
        ut.append("bleed_channel_specific")
    return ut


def _self_test() -> int:
    grönt = 0

    def check(namn: str, fick, väntat) -> None:
        nonlocal grönt
        assert fick == väntat, f"{namn}: {fick!r} != {väntat!r}"
        grönt += 1

    check("6×9 är 152,4 × 228,6 mm", trim_mm("6x9"), (152.4, 228.6))
    check("A5 är 148 × 210 mm", trim_mm("a5"), (148.0, 210.0))
    check("okänt trim ger inget", trim_mm("b5"), None)

    # Gutter-trappan, inklusive gränserna mellan stegen
    check("100 sidor ger 9,6 mm", gutter_mm(100), 9.6)
    check("150 är sista steget i första trappan", gutter_mm(150), 9.6)
    check("151 ger 12,7 mm", gutter_mm(151), 12.7)
    check("300 är sista steget i andra", gutter_mm(300), 12.7)
    check("301 ger 15,9 mm", gutter_mm(301), 15.9)
    check("828 är sista steget", gutter_mm(828), 22.3)
    check("över 828 gäller den sista trappan", gutter_mm(900), 22.3)
    check("trappan är KDP:s och lånas inte ut", gutter_mm(300, channel="lulu"), None)

    # Ryggbredden: bara KDP har en formel, och pappret spelar roll
    check("300 sidor vitt papper", spine_mm(300, "white"), 17.16)
    check("300 sidor crème", spine_mm(300, "cream"), 19.05)
    check("300 sidor premiumfärg", spine_mm(300, "premium_color"), 17.88)
    check("IngramSpark får ingen påhittad siffra", spine_mm(300, "white", "ingramspark"), None)
    check("Lulu inte heller", spine_mm(300, "white", "lulu"), None)

    # Omslaget: bleed + baksida + rygg + framsida + bleed
    check("omslaget runt 6×9, 300 sidor",
          cover_mm("6x9", 300, "white"), (328.36, 235.0))
    check("utan blöd blir det exakt",
          cover_mm("6x9", 300, "white", bleed=False), (321.96, 228.6))
    check("och utan formel inget omslagsmått",
          cover_mm("6x9", 300, "white", channel="lulu"), None)

    # Sidinställningarna: inner blir gutter, ytter blir 6,4 mm
    inst = page_settings_for("6x9", 300)
    check("trimmets mått följer med", (inst["custom_width_mm"], inst["custom_height_mm"]), (152.4, 228.6))
    check("innermarginalen är gutter", inst["margin_left_mm"], 12.7)
    check("ytterkanten är KDP:s minimum", inst["margin_right_mm"], 6.4)
    check("och speglingen är på", inst["mirror_margins"], True)
    check("blöd läggs på ytterkanten",
          page_settings_for("6x9", 300, bleed=True)["margin_right_mm"], 9.6)
    check("okänt trim ger inga inställningar", page_settings_for("b5", 300), None)

    # Varningarna
    check("under 24 sidor sägs det", "kdp_min_pages" in warnings("6x9", 20), True)
    check("udda sidantal sägs det", "odd_pages" in warnings("6x9", 301), True)
    check("och för litet för ryggtext", "no_spine_text" in warnings("6x9", 60), True)
    check("300 sidor är rent", warnings("6x9", 300), [])
    check("en kanal utan formel säger till", "use_channel_template" in warnings("6x9", 300, channel="lulu"), True)
    check("och blöd utanför KDP likaså",
          "bleed_channel_specific" in warnings("6x9", 300, bleed=True, channel="lulu"), True)

    # Kanalerna själva
    check("fem kanaler", sorted(CHANNELS), ["apple", "ingramspark", "kdp", "kobo", "lulu"])
    check("och bara KDP har en formel",
          [n for n, k in CHANNELS.items() if k["formula"]], ["kdp"])
    check("alla bär en källa", all(k["source"] in SOURCES for k in CHANNELS.values()), True)

    # Spegelvändningen: inner/ytter växlar mellan udda och jämn sida, och textytan
    # är lika bred på båda (det är bara blocket som flyttas).
    spegel = {"margin_left_mm": 12.7, "margin_right_mm": 6.4, "mirror_margins": True,
              "margin_top_mm": 15.0, "margin_bottom_mm": 20.0}
    check("udda sida har innermarginalen till vänster",
          page_margins(spegel, 0)[0::2], (12.7, 6.4))
    check("jämn sida växlar den till höger",
          page_margins(spegel, 1)[0::2], (6.4, 12.7))
    check("och textytan är lika bred på båda",
          round(page_margins(spegel, 0)[0] + page_margins(spegel, 0)[2], 2)
          == round(page_margins(spegel, 1)[0] + page_margins(spegel, 1)[2], 2), True)
    check("utan spegling står marginalerna som de är",
          mirrored_margins({"margin_left_mm": 6.4, "margin_right_mm": 12.7}), (6.4, 12.7))
    check("och en sida utan speglingsflagga rörs inte",
          page_margins({"margin_left_mm": 20.0, "margin_right_mm": 20.0}, 3)[0::2], (20.0, 20.0))
    check("tomma värden faller tillbaka på 20 mm",
          mirrored_margins({}), (20.0, 20.0))
    return grönt


if __name__ == "__main__":
    print(f"publishing: {_self_test()} kontroller gröna")
