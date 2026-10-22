# Scribentia — inventering av layout-, sido- och printfunktioner

Läst read-only på `master`, 2026-10-22. Två kolumner hålls isär med flit: **(a)** finns det en entry/kod för saken, och **(b)** är den *klar* — det vill säga dragen hela vägen in i PDF/utskriftsvägen (`core/doc_manager.py:print_document_to_printer`) **och** syns på skärmen (`ui/paged_paper.py`). Att något står i en modul betyder inte att det ritas.

| # | Funktion | (a) Entry/kod | (b) Klar (print + skärm) | Evidens |
|---|---|---|---|---|
| 1 | Widow/orphan control | Ja | Nej — rapport + opt-in-knapp, aldrig automatisk | `core/prepress.py:79`, `ui/main_window.py:2154` |
| 2 | Keep-with-next | Nej | Nej | grep: 0 träffar |
| 3 | Do-not-split-paragraph | Ja | Endast skärm | `core/pagination.py:27`, `ui/paged_paper.py:191` |
| 4 | Spacing över/under stycke, kollaps | Delvis (per roll) | Delvis — inget UI, ingen kollapslogik | `core/richtext.py:93-94` |
| 5 | Line-spacing-lägen | Ja, 4 fasta procent | Ja, men bara ProportionalHeight | `ui/toolbar.py:330-333`, `:674` |
| 6 | Justified last line | Nej | Nej (Qts default) | `ui/toolbar.py:658` |
| 7 | Hyphenation | Ja, pyphen | Print ja (före sidantal), skärm nej | `core/doc_manager.py:336`, `core/autocorrect.py:167` |
| 8 | Header/footer | Ja, ren text | Print ja, skärm nej, DOCX nej | `core/doc_manager.py:302-311` |
| 9 | Page numbering (offset/restart/format) | Format ja, offset/restart nej | Print ja, skärm delvis | `core/doc_manager.py:359-371`, `ui/paged_paper.py:412` |
| 10 | Footnotes/endnotes | Fält ja | Endast export, som slutnoter | `core/fields.py:135`, `ui/main_window.py:2757` |
| 11 | Sections/columns | Nej | Nej | grep: 0 träffar |
| 12 | Tabeller över sidor med upprepad header | Nej | Nej | `core/pagination.py:11-14` |
| 13 | Bilder med wrap/anchor | Endast inline + justering | Ja, som inline | `ui/editor_view.py:307`, `:343` |
| 14 | Tab stops med leader dots | Nej | Nej | grep: 0 träffar |
| 15 | Named styles vs roller | Roller ja, named styles nej | Roller ja i DOCX/MD/EPUB | `core/richtext.py:22-32`, `core/doc_manager.py:91-97` |
| 16 | TOC med sidnummer | TOC ja, sidnummer nej | Nej | `ui/main_window.py:2724` |
| 17 | "Page X of Y"-fält | Som tryckt sträng | Ja i print, inte i brödtext | `core/doc_manager.py:371` |
| 18 | Mirrored margins/gutter | Gutter ja, spegling nej | Nej (samma marginal båda sidor) | `core/publishing.py:163`, `core/doc_manager.py:277` |
| 19 | Print scaling modes | Nej | Nej (endast large print 1,5×) | `core/page_format.py:12`, `core/print_style.py:362` |
| 20 | Språk per text run | Endast per block (kod) | Nej | `core/richtext.py:23`, `:60-64` |

## Numrerade fynd

**1. Widow/orphan.** Mätningen finns: `core/prepress.py:79` `def widows_and_orphans(doc, page_settings: dict | None = None,`. Den räknar sida som `core/prepress.py:95` `sidor = [int(y // mått) for y in ys]` — jämn slot-matematik, medan skärmen staplar faktiska radbrytningar (`core/pagination.py:76`). Modulen säger själv `core/prepress.py:16` `Ingenting här ändrar texten: rapporten säger vad som finns`. Knappen `ui/main_window.py:2154` `fynd = prepress.widows_and_orphans(doc, self.page_settings)` märker stycken, men PDF-vägen läser aldrig märket.

**2. Keep-with-next.** Saknas. `grep -rniE "keep_with_next|KeepWithNext" --include="*.py" core ui main.py` gav noll träffar. Ingen egen property, ingen UI-knapp, ingen Qt-motsvarighet använd.

**3. Do-not-split-paragraph.** Egen property: `core/pagination.py:27` `KEEP_TOGETHER = QTextFormat.Property.UserProperty`. Skärmen respekterar den (`core/pagination.py:68-71`, anropad från `ui/paged_paper.py:191` `self.pages = page_offsets(doc, float(self.px(self.canvas_h)))`). Utskriften gör det inte: `grep -n "keep\|KEEP" core/doc_manager.py` gav noll träffar, och PDF:en läggs ut av Qt:s egen paginering via `doc_clone.setPageSize(...)` (`core/doc_manager.py:337`). Skärm och papper kan alltså dela stycken olika.

**4. Spacing över/under stycke.** Sätts per roll, inte som användarvärde: `core/richtext.py:93-94` `fmt.setTopMargin(8)` / `fmt.setBottomMargin(8)`, liknande i quote/break/verse/message. Ingen kollapslogik finns — `grep -rn "collapse" core ui` ger bara CSS `border-collapse` i `core/templates.py`. DOCX-importen läser bara justering (`core/doc_manager.py:143-149`), inte styckeavstånd.

**5. Line-spacing.** Bara fyra procentlägen: `ui/toolbar.py:330-333` (`1.0`, `1.15`, `1.5`, `2.0`), alla via `ui/toolbar.py:674` `block_fmt.setLineHeight(height_pct, 1) # 1 = ProportionalHeight`. Inget "exakt"/"minst", ingen radavståndsnyckel i `DEFAULT_PAGE_SETTINGS` (`core/doc_manager.py:70-86`). Print skalar radhöjd bara för large print (`core/print_style.py:446`).

**6. Justified last line.** Ingen entry. `ui/toolbar.py:658` `def _set_alignment(self, align_flag):` sätter bara `setAlignment`. Ingen hantering av sista raden någonstans; Qt lämnar den ojämn.

**7. Hyphenation.** pyphen, inte egen algoritm: `core/autocorrect.py:167` `def soft_hyphenate(text: str, lang: str = "sv") -> str:`. Körs i utskriftsklonen och **före** sidantalet: `core/doc_manager.py:336` `DocumentManager._hyphenate_clone(doc_clone, cfg.get("language", "sv"))` står före `:337` `doc_clone.setPageSize(...)` och `:338` `page_count = max(1, doc_clone.pageCount())`. Två luckor: skärmen avstavar aldrig (`grep hyphen ui/paged_paper.py` = 0), och `page_settings` saknar nyckeln `language`, så `cfg.get("language", "sv")` faller alltid tillbaka på svenska. EPUB avstavar med bokens språk (`core/epub.py:91`).

**8. Header/footer.** Ren text, inga fält: `core/doc_manager.py:393` `str(cfg.get("header_text"))`. Bandet är fast 8 mm: `:305` `header_h = (8.0 * dpmm) if has_header else 0.0` — ingen inställning för avstånd från kant. Body-ytan krymper: `:311` `content_h_px = paint_rect.height() - header_h - footer_h`. Skärmen ritar inget sidhuvud alls (`grep header ui/paged_paper.py` = 0), och DOCX-exporten skriver bara sidmått/marginaler (`core/doc_manager.py:573-577`), ingen header-part.

**9. Page numbering.** `core/doc_manager.py:359` `page_num = page_idx + 1` — ingen start-offset, ingen omstart per avsnitt. Fyra format (`:363-371`), fem positioner inkl. alternerande (`:373-385`). Skärmen kan bara tresiffrigt enkelt: `ui/paged_paper.py:412` `sida = i + 1`, och alterneringen är där inte implementerad — `ui/paged_paper.py:433` `elif "right" in pos or pos.endswith("alternating")` lägger alla sidnummer till höger.

**10. Footnotes/endnotes.** Fältformen finns (`core/fields.py`), men `core/fields.py:135` säger `Fotnoten blir en upphöjd länk och samlas i slutet under en rubrik` — det är slutnoter, inte noter i sidfoten. Upplösningen sker bara i exporten: `ui/main_window.py:2757` `kopia.setHtml(fields_module.resolve(...))`, anropad från `_save_document` (`:2768`). PDF-exporten går den vägen (`:2059` `self._save_document(fpath, doc)`), men Ctrl+P och förhandsgranskningen skickar rådokumentet (`:2032`, `:2045`) — där skrivs `[not: ...]` ut som text.

**11. Sections/columns.** Saknas. `grep -rniE "setColumnCount|columnSpan|section"` träffar bara tabellwidgets (`ui/chart_dialog.py:240`, `ui/insight_panel.py:81`). Ingen `QTextFrameFormat`-kolumn, inget avsnittsbegrepp utöver `PageBreak_AlwaysBefore` (`ui/editor_view.py:403`).

**12. Tabeller över sidor med upprepad header.** `ui/table_dialog.py:59` `self.chk_header` ger bara fet första rad; `grep setHeaderRowCount` = 0. Pagineringen håller hellre ihop hela tabellen: `core/pagination.py:11-14` `Block utan rader (tabeller, bilder, tomma stycken) hålls ihop ... ett block som är högre än ett ark får ligga kvar och skjuta över kanten`.

**13. Bilder, wrap/anchor.** Endast inline: `ui/editor_view.py:307` `def insert_image(self, filepath_or_qimage, width_px: int = 480, align: str = "center", caption: str = "")`, infogad som `:343` `html_chunk = f'<p style="text-align: {align}; ...'`. Ingen float, ingen wrap, ingen anchor.

**14. Tab stops med leader dots.** Saknas: `grep -rniE "tabStop|setTabStops|leader|dotleader" --include="*.py" core ui main.py` gav noll träffar.

**15. Named styles vs roller.** Appen har roller, inte stilar: `core/richtext.py:22` `ROLE_PROPERTY = QTextFormat.Property.UserProperty + 1`, med fem värden (`:25-32`: code, quote, break, verse, message). Rollerna blir namngivna Word-stilar vid export (`core/doc_manager.py:91-97`, skapas i `:485` `doc.styles.add_style(stil, WD_STYLE_TYPE.PARAGRAPH)`). Ingen användardefinierad stilhanterare — `grep add_style` träffar bara docx-vägen.

**16. TOC med sidnummer.** `ui/main_window.py:2713` `def insert_toc`, men `:2724` `rader = "\n".join(f"{n}. {r}" for n, r in zip(nummer, rubriker))` — bara kapitelnummer, inga sidnummer, och listan är text mellan `[innehåll]`/`[/innehåll]` (`:61-62`), inget fält som uppdateras vid print. EPUB har egen nav-TOC (`core/epub.py:266-271`).

**17. "Page X of Y".** Finns som tryckt sträng: `core/doc_manager.py:371` `page_str = _("pdf_page_n_of_total", n=page_num, total=page_count)`, valbar som `page_of_total` (`:363`). Det går inte att infoga ett sidnummerfält i brödtexten.

**18. Mirrored margins/gutter.** Gutter-trappan finns (`core/publishing.py:76` `def gutter_mm`), men speglingen är medvetet inte byggd: `core/publishing.py:163` `return (max(vänster, höger), max(vänster, höger))` med kommentaren `:155-158` att riktig växling kräver `en paginerad målare (sidindex → inner/ytter)`. Utskriften använder resultatet en gång för hela dokumentet (`core/doc_manager.py:277`), så alla sidor får samma marginaler. Skärmen ignorerar helt sidinställningarnas marginaler: `ui/paged_paper.py:40` `PAGE_MARGIN_X = 52` — gutter syns inte alls.

**19. Print scaling modes.** Saknas som begrepp: `core/page_format.py:12` `the size drives pagination, it does not scale the text`. Enda skalningen är large print: `core/print_style.py:362` `LARGE_PRINT_FACTOR = 1.5`, tillagd i PDF-vägen på `core/doc_manager.py:333-334`.

**20. Språk per text run.** Språk finns bara som **block**-property och bara för kod: `core/richtext.py:23` `LANG_PROPERTY = QTextFormat.Property.UserProperty + 2`, satt i `:60-64` via `set_role`. Ingen per-run-språk, ingen `QTextCharFormat`-locale, ingen `w:lang` i DOCX (`grep -n "lang" core/doc_manager.py` ger bara kodstaket och avstavning). EPUB sätter dokumentnivå: `core/epub.py:126` `root.set("lang", language)`.

## Kort sammanfattning

Det som är *färdigt* i båda kanalerna är litet men verkligt: sidformat/orientering (en sanning i `core/page_format.py`), sidnummer med fyra format, sidhuvud/sidfot som text med krympande body, manuella sidbrytningar, roller som överlever DOCX/MD/EPUB, samt PDF/X- och large print-vägen. Det som bara finns på skärmen är den radbundna pagineringen inklusive `KEEP_TOGETHER`. Det som bara finns i utskriften är avstavning och fältupplösning. Widow/orphan är en mätare med knapp, inte en funktion — och den mäter mot en annan sidmodell än den som ritar. Allt som hör till riktig boktypografi (keep-with-next, speglade marginaler, noter i sidfot, tabellhuvuden som upprepas, tab stops, TOC med sidnummer, named styles) saknas helt.
