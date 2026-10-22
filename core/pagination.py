"""
core/pagination.py — delar ett dokument i ark, radbundet.

Sidorna ritas som separata ark (som i Word och LibreOffice), så texten måste
delas *mellan rader*: annars klipper arkets kant en rad mitt itu. Här räknas
var varje ark börjar, i dokumentets egna koordinater.

    starts = page_offsets(doc, content_h)      # [0, 984, 1965, ...]
    sida = bisect_right(starts, doc_y) - 1

Block utan rader (tabeller, bilder, tomma stycken) hålls ihop och flyttas
hela till nästa ark. `ponytail:` ett block som är högre än ett ark får ligga
kvar och skjuta över kanten — att dela en tabell mitt i kräver att man ritar om
dess rader, och det är sällan värt det; säg till om det dyker upp i praktiken.
"""

from bisect import bisect_right

from PyQt6.QtGui import QTextFormat

# "Håll ihop stycket": en egen blockegenskap, aldrig Qts setNonBreakableLines.
# Den flaggan stänger nämligen av **radbrytningen** också (mätt: en rad blev 1120 px
# i ett 646 px ark och gick utanför pappret), och Alex regel är att text alltid
# bryts vid ordet före kanten: "det får inte ens vara under diskussion". Här
# betyder märket i stället: hamnar en sidbrytning inne i stycket flyttas hela
# stycket till nästa ark — det Qt-flaggan var tänkt att göra, utan dess pris.
KEEP_TOGETHER = QTextFormat.Property.UserProperty

# "Håll ihop med nästa stycke": samma märkesmekanism, en nivå upp. Rubriker har
# regeln i Writer (rubrikstilarna), och en rubrik som står ensam sist på ett ark
# hör inte till texten efter den.
KEEP_WITH_NEXT = int(QTextFormat.Property.UserProperty) + 1


def mark_keep_together(block_fmt) -> None:
    """Märker ett blockformat som 'håll ihop'. Ingen radbrytning rörs."""
    block_fmt.setProperty(KEEP_TOGETHER, True)


def keeps_together(block) -> bool:
    """Är blocket märkt att hållas ihop över sidbrytningen?"""
    return bool(block.blockFormat().property(KEEP_TOGETHER))


def keeps_with_next(block) -> bool:
    """Håller blocket ihop med stycket efter?

    Rubriker gör det i Writer — rubrikstilarna har keep-with-next, mätt — och det
    är hela skillnaden mot oss: utan regeln blev rubriken sista rad på arket i 5
    av 120 avsnitt. Ett stycke som inte är en rubrik kan märkas för hand med
    `mark_keep_with_next` (t.ex. en ingress som hör till en bild).
    """
    if block.blockFormat().headingLevel() > 0:
        return True
    return bool(block.blockFormat().property(KEEP_WITH_NEXT))


def mark_keep_with_next(block_fmt) -> None:
    """Märker ett blockformat att hållas ihop med nästa stycke."""
    block_fmt.setProperty(KEEP_WITH_NEXT, True)


def page_offsets(document, content_height: float) -> list:
    """Dokumentets y för första raden på varje ark. Ett ark för ett tomt dokument.

    Writers brytregler, mätta i dess standardstilar (ParaOrphans = ParaWidows = 2
    och rubrikstilarna håller ihop med nästa stycke): ett stycke lämnar aldrig en
    ensam rad på någon sida av ett sidbrott, och en rubrik står aldrig sist på ett
    ark. Båda syns bara i efterhand — därför flyttas hela stycket (änkling),
    respektive en rad tillbaka (föräldralös), och en rubrik som skulle bli sist
    flyttas till nästa ark. Utan reglerna lämnade vi 5 rubriker sist på arket av
    120 avsnitt och en ensam rad vid 228 px textyta (mätt).
    """
    if content_height <= 0:
        return [0.0]

    poster = _items(document)
    starts = [0.0]
    sida = 0.0

    def ny_sida(topp: float) -> None:
        nonlocal sida
        sida = topp
        starts.append(topp)

    for idx, post in enumerate(poster):
        # En sidbrytning som användaren själv lagt in börjar ett nytt ark
        if post["break_before"] and post["top"] > sida:
            ny_sida(post["top"])

        nästa = poster[idx + 1] if idx + 1 < len(poster) else None
        # Ett omtag räcker: en rubrik flyttas en sida, aldrig längre.
        for _försök in range(3):
            sida = _place_block(post, sida, content_height, ny_sida)
            if not (post["keep_with_next"] and nästa is not None
                    and sida < post["top"]
                    and _needs_next(nästa) > sida + content_height):
                break
            sida = post["top"]
            starts.append(sida)

    starts = sorted(set(starts))
    if starts[0] != 0.0:
        starts.insert(0, 0.0)

    # Efterkontroll för rubriken: regeln kan bara prövas när stycket *efter* är
    # placerat, och en änklingsflytt av det stycket kan lämna rubriken ensam kvar
    # trots att den fick plats. Står rubriken sist på sitt ark flyttas arkets
    # början tillbaka till rubriken, alltså till nästa ark.
    for _ in range(len(poster) + 1):
        flyttad = False
        for post in poster:
            if not post["keep_with_next"] or not post["tops"]:
                continue
            sida60 = page_of_offset(starts, post["tops"][0])
            if sida60 + 1 >= len(starts):
                continue
            if post["tops"][0] <= starts[sida60] + 1e-6:
                continue                      # rubriken börjar redan ett ark
            if starts[sida60 + 1] > post["tops"][-1] + post["heights"][-1] + 1e-6:
                continue                      # text står efter rubriken på arket
            starts[sida60 + 1] = post["tops"][0]
            starts = sorted(set(starts))
            flyttad = True
            break
        if not flyttad:
            break

    return starts


def _items(document) -> list[dict]:
    """Varje blocks topp, radpositioner och brytregler — en läsning, ingen gissning."""
    layout = document.documentLayout()
    ut = []
    block = document.begin()
    while block.isValid():
        rect = layout.blockBoundingRect(block)
        textlayout = block.layout()
        rader = textlayout.lineCount() if textlayout is not None else 0
        ut.append({
            "top": rect.top(),
            "height": rect.height(),
            "tops": ([rect.top() + textlayout.lineAt(i).y() for i in range(rader)]
                     if textlayout is not None else []),
            "heights": ([textlayout.lineAt(i).height() for i in range(rader)]
                        if textlayout is not None else []),
            "keep_together": keeps_together(block),
            "keep_with_next": keeps_with_next(block),
            "break_before": bool(block.blockFormat().pageBreakPolicy()
                                 & QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore),
        })
        block = block.next()
    return ut


def _needs_next(post: dict) -> float:
    """Hur långt ned nästa stycke måste nå för att rubriken skall stanna.

    Två rader, inte en: blir det bara plats för en rad flyttar änklingsregeln
    hela stycket till nästa ark, och då står rubriken ensam kvar ändå (mätt: 162
    gånger i egenkontrollen innan det här villkoret fanns).
    """
    if post["tops"]:
        rader = min(2, len(post["tops"]))
        return post["tops"][rader - 1] + post["heights"][rader - 1]
    return post["top"] + post["height"]


def _place_block(post: dict, sida: float, content_height: float, ny_sida) -> float:
    """Lägger ett stycke från sidans start `sida`, med Writers brytregler.

    Returnerar arkets start efter placeringen — den flyttas när en regel bryter,
    och anroparen måste veta var (annars räknar nästa stycke mot ett gammalt ark).
    """
    rader = len(post["tops"])
    if rader == 0:
        # Tabell, bild eller tomt block: flyttas helt om det inte får plats
        if (post["height"] > 0 and post["top"] > sida
                and post["top"] + post["height"] > sida + content_height):
            ny_sida(post["top"])
            return post["top"]
        return sida

    k = 0
    while k < rader:
        topp, höjd = post["tops"][k], post["heights"][k]
        if topp + höjd <= sida + content_height or topp <= sida:
            k += 1
            continue

        kvar_här = k                 # rader av stycket kvar på det här arket
        kvar_under = rader - k       # rader som skulle hamna på nästa ark

        if post["keep_together"] and sida < post["top"]:
            # Märkt stycke som inte får plats: hela stycket börjar nästa ark.
            ny_sida(post["top"])
            sida = post["top"]
            k = 0
            continue

        if kvar_här == 1 and rader >= 2 and sida < post["top"]:
            # Änkling: en ensam rad kvar nederst — hela stycket flyttas.
            ny_sida(post["top"])
            sida = post["top"]
            k = 0
            continue

        if kvar_under == 1 and rader >= 3 and k >= 1:
            # Föräldralös: en ensam rad överst på nästa ark — ta med en rad till.
            # Bara om båda raderna får plats där; annars bryter vi där vi står
            # (en ensam rad är det minsta som går, och utan det här villkoret
            # flyttas brytningen bakåt för evigt på ett ark som är för lågt).
            tidigare = post["tops"][k - 1]
            if topp + höjd - tidigare <= content_height:
                k -= 1
                topp = tidigare

        ny_sida(topp)
        sida = topp
        k += 1
    return sida


def page_of_offset(starts: list, doc_y: float) -> int:
    """Vilket ark dokumentets y hör till (0-baserat)."""
    return max(0, bisect_right(starts, doc_y) - 1)


def _self_test() -> int:
    """Radbunden paginering mot ett riktigt dokument. 0 = allt grönt."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QTextDocument

    app = QApplication.instance() or QApplication([])   # noqa: F841
    fel = 0

    def kolla(ok, text):
        nonlocal fel
        print(f"  {'OK  ' if ok else 'FEL '} {text}")
        if not ok:
            fel += 1

    doc = QTextDocument()
    doc.setDocumentMargin(38)
    doc.setHtml("".join(f"<p>Stycke {i}. " + "Ord och meningar som fyller en rad. " * 8 + "</p>"
                        for i in range(1, 40)))
    höjd = 400.0
    starts = page_offsets(doc, höjd)
    kolla(len(starts) >= 2, f"flera ark ({len(starts)} stycken)")
    kolla(starts[0] == 0.0, "första arket börjar på 0")

    # Ingen rad får korsa en arkgräns
    layout = doc.documentLayout()
    gränser = list(starts[1:])
    korsar = 0
    block = doc.begin()
    while block.isValid():
        rect = layout.blockBoundingRect(block)
        tl = block.layout()
        for i in range(tl.lineCount() if tl else 0):
            rad = tl.lineAt(i)
            topp = rect.top() + rad.y()
            if any(topp < g < topp + rad.height() for g in gränser):
                korsar += 1
        block = block.next()
    kolla(korsar == 0, f"ingen rad korsar en arkgräns ({korsar} korsande)")

    # Varje ark rymmer så mycket det kan utan att gå över höjden
    för_stort = [s for s in starts
                 if any(s < g < s + höjd for g in starts[1:])]
    kolla(not för_stort, f"arken ligger minst en sidhöjd isär ({len(för_stort)} för täta)")

    kolla(page_of_offset(starts, 0.0) == 0, "y=0 hör till första arket")
    kolla(page_of_offset(starts, starts[-1] + 10) == len(starts) - 1,
          "y efter sista gränsen hör till sista arket")

    # En tabell hålls ihop (block utan rader)
    tabell = QTextDocument()
    tabell.setDocumentMargin(38)
    tabell.setHtml("<p>Före</p>" +
                   "<table border=1 cellspacing=0 cellpadding=6>" +
                   "".join(f"<tr><td>Cell {r}</td><td>Rad {r}</td></tr>" for r in range(12)) +
                   "</table><p>Efter</p>")
    t_starts = page_offsets(tabell, 200.0)
    kolla(len(t_starts) >= 2, f"tabell-dokumentet delas ({len(t_starts)} ark)")
    kolla(all(b - a > 40 for a, b in zip(t_starts, t_starts[1:])),
          "och inga ark ligger orealistiskt tätt")

    # En sidbrytning användaren lagt in börjar ett nytt ark
    bruten = QTextDocument()
    bruten.setDocumentMargin(38)
    bruten.setHtml("<p>Ett</p><p>Tva</p>")
    from PyQt6.QtGui import QTextBlockFormat, QTextCursor
    bf = QTextBlockFormat()
    bf.setPageBreakPolicy(QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore)
    mark = QTextCursor(bruten)
    mark.setPosition(bruten.findBlockByNumber(1).position())
    mark.setBlockFormat(bf)
    b_starts = page_offsets(bruten, 400.0)
    kolla(len(b_starts) == 2 and b_starts[1] > 0,
          f"en inlagd sidbrytning börjar ett nytt ark ({[round(x) for x in b_starts]})")

    tom = QTextDocument()
    kolla(page_offsets(tom, 400.0) == [0.0], "tomt dokument ger ett ark")
    kolla(page_offsets(doc, 0) == [0.0], "nollhöjd ger ett ark")

    # Writers brytregler, mätta i dess standardstilar: ParaOrphans = ParaWidows = 2,
    # och rubrikstilarna håller ihop med nästa stycke. Reglerna prövas som
    # invarianter över många ark-höjder, för det är bara vid vissa geometrier de
    # slår till: innan de fanns lämnade vi en ensam rad vid 228 px textyta och
    # rubriken sist på arket i 5 av 120 avsnitt.
    from PyQt6.QtGui import QTextBlockFormat, QTextCharFormat, QTextCursor
    from bisect import bisect_right

    regel = QTextDocument()
    regel.setDocumentMargin(0)
    regel.setTextWidth(600.0)
    m = QTextCursor(regel)
    for i in range(40):
        if i:
            m.insertBlock()
        bf = QTextBlockFormat()
        if i % 4 == 3:
            bf.setHeadingLevel(1)                 # en enradsrubrik
        m.setBlockFormat(bf)
        if i % 4 == 3:
            m.insertText(f"Rubrik {i}", QTextCharFormat())
        else:
            m.insertText(f"Stycke {i} " + "ord som fyller en hel rad " * 6,
                         QTextCharFormat())
    # Sista stycket är brödtext: en rubrik allra sist har inget att hållas ihop
    # med, och då är det inget fel att arket slutar med den.
    m.insertBlock()
    m.setBlockFormat(QTextBlockFormat())    # insertBlock ärver rubriknivån annars
    m.insertText("Sista stycket.", QTextCharFormat())
    regel_layout = regel.documentLayout()
    rubrik_sist = 0
    ensam_rad = 0
    # Höjder under en rubrik plus en rad kan ingen regel uppfylla: där prövas de inte.
    for h in range(80, 420, 6):
        st = page_offsets(regel, float(h))
        sista = {}
        stycken: dict[str, list[int]] = {}
        b = regel.begin()
        while b.isValid():
            r = regel_layout.blockBoundingRect(b)
            tl = b.layout()
            for i in range(tl.lineCount() if tl else 0):
                y = r.top() + tl.lineAt(i).y()
                sida = max(0, bisect_right(st, y) - 1)
                sista[sida] = (y, b.blockFormat().headingLevel())
                stycken.setdefault(b.text(), []).append(sida)
            b = b.next()
        rubrik_sist += sum(1 for y, nivå in sista.values() if nivå > 0)
        # Ett stycke med flera rader får inte lämna en ensam rad på ett ark.
        for rader in stycken.values():
            for sida in set(rader):
                if rader.count(sida) == 1 and len(rader) > 1:
                    ensam_rad += 1
    kolla(rubrik_sist == 0, f"ingen rubrik står sist på ett ark ({rubrik_sist} gånger)")
    kolla(ensam_rad == 0, f"ingen ensam rad över ett sidbrott ({ensam_rad} gånger)")

    return fel


if __name__ == "__main__":
    import sys
    sys.exit(1 if _self_test() else 0)
