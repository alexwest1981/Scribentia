# Paragraf- och sidflöde i LibreOffice Writer 26.8 (ODF 1.3)

**Metod och källor.** Fyra källtyper används: (1) ODF 1.3 Part 3, *OpenDocument Schema* (OASIS), (2) de hjälpfiler som följer med den installerade LibreOffice 26.8.0.3 (Build:3) under `/usr/lib/libreoffice/help/en-US/text/`, (3) LibreOffice-källkoden (`github.com/LibreOffice/core`, grenen `master`, hämtad 2026-10-22), (4) egna mätningar: dokument har genererats och renderats med samma installation (`soffice --headless --convert-to pdf`, `pdftotext -bbox`); mätfilerna ligger i `/home/alex/.hermes/cache/scratch/odf/probe/`. Källhänvisningar till kod anges som `fil:rad` i master.

## 1. Widow/orphan-kontroll

Attributen är `fo:widows` (ODF 1.3 §20.228) och `fo:orphans` (§20.214), båda `nonNegativeInteger` på `<style:paragraph-properties>` (§17.6). Specen ger bara prosa för widows: "The fo:widows attribute specifies the minimum number of lines that shall be displayed at the top of a page to avoid paragraph widows"; för orphans hänvisas enbart till XSL §7.19.6.

Writers egen definition är entydig: en *widow* är en "paragraph-ending line that goes to the following page or column" (`include/editeng/widwitem.hxx`), en *orphan* är en "paragraph-starting line that is still on the previous page or column" (`include/editeng/orphitem.hxx`). Alltså: `fo:widows` = rader som måste inleda nästa sida, `fo:orphans` = rader som måste stanna i botten på den aktuella sidan.

**Default i ett Writer-dokument: ingen kontroll.** Ett dokument skapat av 26.8 skriver inga `fo:widows`/`fo:orphans` alls i `styles.xml`, och item-defaulten är 0 (`editeng/source/items/paraitem.cxx:58-59`, `SvxWidowsItem(0,0)`). Uppmätt på ett sådant dokument: med 48 enradiga fyllnadsstycken följda av ett sjuradigt stycke blev brytningen 1 rad i botten / 6 rader i toppen — en ensam rad lämnades alltså kvar. Samma sak i den andra riktningen (6/1). En läsare som tolkar frånvarande attribut enligt XSL-defaulten (2) får alltså ett annat resultat än Writer.

**Regeln när attributen är satta.** Uppmätt med `fo:widows="2" fo:orphans="2"` på ett sjuradigt stycke: brytningen hamnade på 4/3 respektive 3/4, och när bara en rad fick plats flyttades hela stycket (0 rader kvar, 7 på nästa sida). Regeln är alltså: brytning tillåts först när minst `orphans` rader lagts ut, och om färre än `widows` rader skulle hamna på nästa sida flyttas rader tillbaka till föregående sida. I koden: `WidowsAndOrphans::IsBreakNowWidAndOrp` returnerar falskt så länge `rLine.GetLineNr() <= m_nOrphLines` (`sw/source/core/text/widorp.hxx`), och `FindWidows` låter follow-framen lämna tillbaka rader till mastern via `PrepareHint::WidowsOrphans`; tröskeln är `rLine.GetLineNr() >= m_nWidLines + nExtraWidLines` (`sw/source/core/text/widorp.cxx:637`). Vid avstavning kan en extra rad behöva flyttas (`nExtraWidLines`). Keep-villkoret overrullas om stycket är större än sidan: "If paragraph should not be split but is larger than the page, then bKeep is overruled" (`widorp.cxx:322-327`).

## 2. Keep with next paragraph

`fo:keep-with-next` (§20.201, värden `auto`/`always`). Writers rubrikstilar sätter keep: basstilen `Heading` får `SvxFormatKeepItem(true)` (`sw/source/core/doc/DocumentStylePoolManager.cxx:813`), och Heading 1–10 ärver från den (`style:parent-style-name="Heading"`, se `COLL_HEADLINE1` m.fl. på rad 841 ff.). Verifierat i en exporterad 26.8-fil: `<style:style style:name="Heading" ... style:class="chapter"><style:paragraph-properties fo:margin-top="0.1665in" fo:margin-bottom="0.0835in" style:contextual-spacing="false" fo:keep-with-next="always"/>`. **Default för Heading 1/2/3 (och 4–10) är alltså `always`**; `Standard` och `Text body` saknar attributet, dvs. `auto`.

Effekten vid sidbrytning, enligt hjälpen: "Keeps the current paragraph and the following paragraph together when a break or column break is inserted" (`swriter/01/05030200.html`). I koden sker det i `SwFlowFrame::CheckMoveFwd` → `MoveFwd` med kommentaren "Keep together with the following frame" (`sw/source/core/layout/flowfrm.cxx:2009` och `:2060`): hamnar nästa stycke på en ny sida flyttas även detta stycke dit. Viktigt: det garanterar bara att *nästa stycke börjar på samma sida*, inte att hela nästa stycke ryms — och två rubriker efter varandra kaskaderar (rubrik 2 drar med sig rubrik 1 och brödtexten).

## 3. Do not split paragraph

`fo:keep-together` (§20.200, `auto`/`always`). Default är `auto`/frånvarande: Writers `SvxFormatSplitItem` har `bSplit = true` som default (`include/editeng/spltitem.hxx`), dvs. stycken får delas. Med `always` flyttas hela stycket till nästa sida eller kolumn om det inte ryms, med samma undantag som ovan: ett stycke som är högre än spalten/sidan kan inte hållas ihop och delas då ändå.

## 4. Spacing above/below — adderas eller kollapsar?

**I 26.8 adderas angränsande styckeavstånd som default.** Uppmätt: `fo:margin-bottom="1cm"` följt av `fo:margin-top="1cm"` gav 70,5 pt mellan baslinjerna; radhöjden är 13,28 pt, så mellanrummet blev 57,2 pt ≈ 2,02 cm — summan, inte maxvärdet. Samma resultat i både Writer-skapat dokument och ODF-importerat.

Orsaken är kompatibilitetsflaggan `DocumentSettingId::PARA_SPACE_MAX`. I `SwFlowFrame::CalcUpperSpace` gäller:

- flaggan satt: `nUpper = nPrevLowerSpace + pAttrs->GetULSpace().GetUpper()` (`sw/source/core/layout/flowfrm.cxx:1652-1660`)
- flaggan av: `nUpper = ... std::max(nPrevLowerSpace, pAttrs->GetULSpace().GetUpper())` (`flowfrm.cxx:1698-1701`)

Flaggan hämtas från `org.openoffice.Office.Compatibility` → `FormattingOptions` → `AddSpacing`, som i den installerade registret är `true` (`/usr/lib/libreoffice/share/registry/main.xcd:3530`, posten "Add spacing between paragraphs and tables"), och motsvarar kryssrutan *Tools ▸ Options ▸ LibreOffice Writer ▸ Compatibility*. Vill man ha max() i stället måste den slås av.

**Finns "don't add space between paragraphs of the same style"? Ja, dokumenterat.** Writer-hjälpen: "Do not add space between paragraphs of the same style — Makes any space specified before or after this paragraph not be applied when the preceding and following paragraphs are of the same paragraph style" (`shared/01/05030100.html`). ODF-motsvarigheten är `style:contextual-spacing` (§20.255):

> "The fo:margin-bottom ... attribute of a paragraph and the fo:margin-top ... attribute of the next paragraph are ignored, so that the space between the paragraphs is zero, if all of the following conditions hold: • The style:contextual-spacing attribute of both paragraphs has the value true. • The paragraphs belong to the same content area. • The text:style-name attribute of the paragraphs refer to the same common paragraph style."

Default är `false`. Notera att detta ger **noll**, inte `max()` — och att båda styckena måste ha flaggan.

## 5. Line spacing

Hjälpen (`shared/01/05030100.html`) räknar upp: Single, 1.15 lines, 1.5 lines, Double, **Proportional** ("Select this option and then enter a percentage value in the box, where 100% corresponds to single line spacing"), **At Least** ("Sets the minimum line spacing... adjusted to the largest font size"), **Leading** ("Sets the height of the vertical space that is inserted between two lines") och **Fixed** ("exactly match the value... can result in cropped characters").

Formeln för proportional är alltså `radhöjd = procent × single line height`. Uppmätt i 12 pt Liberation Serif: single = 13,80 pt, 150 % = 20,70 pt (exakt 1,5 × 13,80). Single line height är fontens ascent + descent + line gap, här 1,15 × fontstorleken.

I filen (verifierat genom roundtrip): Proportional → `fo:line-height="150%"`; At Least → `style:line-height-at-least="0.2756in"` (kräver `fo:line-height="normal"`); Fixed → `fo:line-height="0.2756in"` (längd; gav exakt 19,85 pt radhöjd); Leading → `style:line-spacing="0.2756in"` (gav 33,65 pt = 13,80 + 19,85, dvs. värdet läggs ovanpå radhöjden). ODF:s definitioner: `fo:line-height` §20.204 (`normal`, längd eller procent), `style:line-height-at-least` §20.317 ("specifies a minimum line height"), `style:line-spacing` §20.318 ("specifies a fixed distance between two lines").

## 6. Justified och sista raden

`fo:text-align="justify"` — "Aligns the paragraph to the left and to the right page margins" (`shared/01/05030700.html`). Sista raden styrs av `fo:text-align-last` (§20.224): "If no value is specified for this attribute, the value is set to `start`", dvs. sista raden vänsterställs och dras inte ut. Ett ensamt ord på sista raden sträcks inte heller, eftersom `style:justify-single-word` (§20.301) default är `false` ("single word should not be justified when the last line in a paragraph is justified"); Writer skriver dessutom ut `style:justify-single-word="false"` explicit när stycket är justerat. Motsvarande kryssruta i Writer heter "Expand single word" (`shared/01/05030700.html`).

## 7. Hyphenation — defaults för ett nytt dokument

`fo:hyphenate` (§20.195) hör till `<style:text-properties>` (inte paragraph-properties) och default är `false`, dvs. **avstängd**. Ett nytt 26.8-dokument skriver följande i `style:default-style style:family="paragraph"`:

```
<style:paragraph-properties fo:hyphenation-ladder-count="no-limit"
    fo:hyphenation-keep="auto" loext:hyphenation-keep-type="column" .../>
<style:text-properties fo:hyphenate="false"
    fo:hyphenation-remain-char-count="2" fo:hyphenation-push-char-count="2"
    loext:hyphenation-no-caps="false" loext:hyphenation-no-last-word="false"
    loext:hyphenation-word-char-count="5" loext:hyphenation-zone="no-limit"
    loext:hyphenation-compound-remain-char-count="2"
    loext:hyphenation-compound-push-char-count="2"/>
```

Alltså: minsta ordlängd **5** tecken, minst **2** tecken före och **2** efter brytningen, **obegränsat** antal konsekutiva avstavade rader (`no-limit`; internt 255, se `editeng/source/items/paraitem.cxx:638`), avstavningszon 0, inga versaler och inte sista ordet. Samma siffror finns i registret: `main.xcd:5050` (`MinLeading` 2), `:5054` (`MinTrailing` 2), `:5058` (`MinWordLength` 5), `:5064` (`IsHyphAuto` false).

## 8. Var värdena lagras i .odt

- `styles.xml`: `<style:default-style style:family="paragraph">` för standarden, `<style:style style:family="paragraph">` för namngivna stilar; attributen ligger på `<style:paragraph-properties>` respektive `<style:text-properties>`.
- `content.xml`: `<office:automatic-styles>` för direktformatering på enskilda stycken.
- `settings.xml`: dokumentövergripande `config:config-item` (t.ex. `AddParaSpacingToTableCells`).
- Attributnamn: `fo:widows`, `fo:orphans`, `fo:keep-with-next`, `fo:keep-together`, `fo:margin-top`, `fo:margin-bottom`, `style:contextual-spacing`, `fo:line-height`, `style:line-height-at-least`, `style:line-spacing`, `fo:text-align`, `fo:text-align-last`, `style:justify-single-word`, `fo:hyphenate`, `fo:hyphenation-keep`, `fo:hyphenation-ladder-count`, `fo:hyphenation-remain-char-count`, `fo:hyphenation-push-char-count`.
- Writer skriver bara avvikelser från default: standardstilen innehåller därför inga `fo:widows`, `fo:orphans`, `fo:keep-together` eller `fo:keep-with-next`.

## UNVERIFIED

- **Config-item-namnet i `settings.xml` för `PARA_SPACE_MAX`.** Ett försök att sätta `AddParaSpacing` där hade ingen effekt på layouten; det exakta ODF-namnet kunde inte verifieras. Sökt i: `sw/source/filter/xml/xmlimp.cxx`, `main.xcd`, `libswlo.so` (strings).
- **Källradnummer** gäller grenen `master` (hämtad 2026-10-22), inte 26.8-taggen; radnummer kan skilja något.
- **Om Writers 0-default för widows/orphans är avsiktlig** finns ingen dokumentation; beteendet är mätt, inte dokumenterat. Sökt i: LO-hjälpen ("widow"), ODF 1.3 Part 3, `sw/source/core/text/widorp.cxx`.
- **Avstavningszonens exakta export** (`loext:hyphenation-zone="no-limit"`) tolkades inte i detalj; endast att den är 0/oändlig som default.
