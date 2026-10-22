# Task Plan: Scribentia → professionellt författarverktyg

## Goal

Allt som ett professionellt författarverktyg har skall in i Scribentia — manusstruktur,
författarlagret, revision, sakprosa, publicering och AI — utan att något glöms mellan sessionerna.

Underlaget är `docs/research/author-tools/` (**elva** rapporter i två pass; 119 källänkar i
det första, 95 i det andra, plus GitHub-API:et och licensfilerna i de två sista — överlappet
passen emellan inte avräknat, och alla kodpåståenden verifierade mot fil och rad; det andra
passets källor i `VERIFIERING.md`). Varje punkt nedan bär sin källa som `R<xx>.<n>` =
rapportens avsnittsnummer, `R06`–`R11` = det andra passet, så inget är påhittat här.
`luckor.md` är sammanställningen: vad de betalda verktygen har, vad vi har, och vad som
saknas.

**Nuläge mätt:** 13 726 rader i `core/` + `ui/` + `main.py`, 38 moduler. Ett dokument i
taget (`ui/main_window.py:663`). Se `findings.md`.

## Next Step

Fas 5: utskriften. Sidhuvuden och sidfötter med jämn/udda sida (0.2 och 4.7 hör hit),
sidnumrering, marginaler per sida, formatmall för tryck och en förhandsvisning som
visar arket som det blir. Innan dess är fas 4 stängd: 4.8 (spalter och avstavning),
4.11 (teckentabell och tesaurus) och 4.13 (tabeller med formler) är de tre låga och
lämnades medvetet — de står kvar som val, inte som glömda.
(tidslinje och plot-tavla) som är nästa större punkt. Rutnätet i 2.9 bygger på
scenmodellen och på att scenens status redan finns.

**Tillagt 2026-10-08 efter det andra researchpasset:** 29 funktionsluckor mätta mot de
betalda verktygen i `luckor.md`; 17 av dem står nu som numrerade poster
(2.18–2.23, 4.17, 4.19–4.21, 5.13–5.16, 6.16–6.18) — flera luckor ryms i en post, och
några är förkastade med skäl i stället för att bli poster. `luckor.md` rankar dem:
normsidan, textelementen, repetitions-/konsistensanalysen, scenstatistiken,
beat-mallarna, kontextvisaren, uppläsningen och karaktärsintervjun är de billiga och
avgörande. Ordningen är min rekommendation, inte ett beslut — säg till om fas 5
fortsätter först eller om någon av de billiga går före.

## Current Phase

Fas 2 — Författarlagret (2.1–2.6 och 2.8–2.10 klara: skrivloggen, kvot, historik,
sprintar, skrivmaskinsläget, story biblen, plot-tavlan, samlingen som läsvy,
revisionsläget (2.12), övningarna (2.14), läsbarhetsmarkeringen (2.15),
projektinstruktionerna (2.17) och projektöversikten (2.16)).
Fas 0, 0b och 1 är klara. Sedan dess: appskalet följer v0-referensen, och
pappret delas i riktiga A4-ark (radbunden paginering, `core/pagination.py`).

**Senaste passet (2026-10-08, efter det andra researchpasset):** de billiga och
avgörande luckorna mot de betalda verktygen byggdes först — **4.17** (repetitions-
och konsistensanalys över hela boken med en panel där klicket markerar textstället,
`core/analysis.py` + `ui/insight_panel.py`), **4.19** (stilvarningar ur ordlistor,
`core/style_rules.py`), **2.20** (fyra beat sheet-mallar som data) och **5.13**
(normalsidan, modulen klar). `core/story_stats.py` (2.18) är byggd och grindad.

Analysen mättes mot **tre riktiga svenska romaner** hämtade från Project Gutenberg
(Dan Andersson, Almqvist, en novellsamling) och reglerna ändrades efter mätningen,
inte efter tycke: 552–892 fynd per bok blev **82–154**, och 80 stilfynd på 140 000
ord efter att fyllnadslistan stramats. Grinden GRÖNT med 661 kontroller i rökprovet,
54 i renhetsprovet och modulernas egna.

## Arbetsregler

- En agent = en git-worktree = ett område. Nya moduler framför ändringar i
  `ui/main_window.py` och `core/doc_manager.py`, som båda är flankerade.
- Grinden `tools/test_all.sh` skall vara grön före varje harvest, och är densamma i
  worktreen som i live-kassan.
- Ingen agent får `git push`, `git commit`, `systemctl` eller röra `~/Projects/Scribentia`
  direkt. Diffen hämtas in för hand och granskas per fil.
- Punktlista: `[ ]` = inte gjord, `[~]` = pågår, `[x]` = klar och verifierad.

## Phases

### Fas 0: Fundament — buggar, grind, projektmodell

- [x] **0.1 Bugg:** DOCX-exporten skickade inte `page_settings` (`ui/main_window.py:807`) medan PDF-exporten gjorde det. Fixat med `_save_document()` som alla sju exportvägar går genom, och `ui_smoke` har nu ett prov som faller om det går sönder igen (falsifierat: felet återinfört → rött).
- [~] **0.2** `print_document_to_printer` sätter fyra fasta marginaler (`core/doc_manager.py:230-235`) och speglar dem aldrig efter jämn/udda sida. **Detta är ingen bugg utan en saknad funktion** — hör till 5.5, inte hit. Kräver sidvis layout (sidindex → inner/ytter), inte ett par rader.
- [x] **0.3 Bugg:** `_toggle_focus_mode` låg i två kopior (`ui/main_window.py:392` och `:544`) där den sista tyst tog över, så sidopanelen slutade gömmas. Slagna ihop till en.
- [x] **0.4 Grind:** `tools/test_all.sh` — importkontroll av alla 39 moduler, `core.project`, `core.epub`, `core.snapshots`, `core.spellcheck`, `tools/ui_smoke.py` (41 kontroller), `tools/print_purity_check.py` (54 kontroller). Grön.
- [x] **0.5 Projektmodellen `core/project.py`:** projekt = mapp med `project.json` + en HTML-fil per scen + `research/`. Noder (del/kapitel/scen), flytt, omordning, synopsis/status/etiketter/POV/mål, ordräkning per scen och totalt, deadline → dagkvot, `validate()` som rapporterar trasiga träd i stället för att kasta, atomär skrivning. 27 kontroller gröna. **Nyckeln: allt annat hänger på denna.** R01.1, R01.2, R04.2
- [x] **0.6 Projektvy `ui/binder_panel.py`:** `QTreeView` mot projektmodellen, skapa/döpa/flytta/ta bort noder, val avgör aktiv scen. Kopplad i `ui/main_window.py` (Arkiv → Nytt/Öppna/Stäng projekt), Spara och autosparning skriver scenen + manifestet, titeln visar bok och scen. `ui_smoke` avsnitt 9 kör hela vägen och läser filerna från disk. R01.1
- **Status:** complete

### Fas 0b: Moduler byggda parallellt (klara, ännu inte kopplade i gränssnittet)

- [~] **0b.1 `core/epub.py`** — EPUB 3 med nav, TOC per kapitel, bilder med alt-text, tillgänglighetsmetadata, atomär skrivning. 10 egna kontroller + 13 i mitt oberoende prov (XML-välformighet med `&` i titel och text, manifest/spine-konsistens). R05.2
- [~] **0b.2 `core/snapshots.py`** — ögonblicksbilder per fil: skapa, lista, läs, återställ, diff, prune; index som återskapas ur innehållet om det är trasigt. 8 egna kontroller + 7 i mitt prov (restore ger exakt samma byte). R01.6, R02.4
- [~] **0b.3 `core/spellcheck.py`** — LanguageTool-klient med styckedelning och UTF-16-korrekta offset. Verifierad mot riktiga tjänsten: felet `teskt` i en text med emoji före fick offset 14:19 — rätt ord. Degraderar ärligt (nätfel → `available()=False`, tom lista). R02.13
- [~] **0b.4 `core/writing_log.py`** — skrivlogg i SQLite: added/removed separat, sessionsrader, historik med nollor utfyllda, sviter med vilodagar, netto per skrivdag, CSV. 9 egna + 10 i mitt prov (månadsskifte, hål i sviten, session över midnatt). R03.3–R03.5
- [~] **0b.5 `core/storybible.py`** — codex: entiteter med alias/fält, relationer, koppling till scen-id, `mentions()` som hittar namn i en text. 11 egna + 13 i mitt prov. **Mitt prov hittade att LIKE-jokertecken escapas** (`%` som sökord gav inga träffar i stället för allt). R04.1, R04.13
- [~] **0b.6 `core/find_replace.py`** — regex-sök och ersättning över ett `QTextDocument`, bakåtreferenser, ett ångra-steg per `replace_all`. 10 egna + 12 i mitt prov (50 ersättningar utan att offsetarna glider). R02.16
- [~] **0b.7 `core/autocorrect.py`** — autokorrigering och autotext: hela ord, skiftläge bevaras, webbadresser och sökvägar rörs inte, regler mot sitt eget svar avvisas, trasig regelfil degraderar. 14 egna + 14 i mitt prov. R02.12
- **Status:** modulerna är klara och grindade, men ingen av dem nås ännu från gränssnittet. Nästa steg är att koppla dem, ett i taget, med ett prov per inkoppling.



### Fas 1: Manusstruktur

- [x] **1.1** Binder: projektträd för delar → kapitel → scener. R01.1
- [x] **1.2** En scen per textdokument, laddas i editorn vid val i trädet. R01.2
- [x] **1.3** Korktavla och indexkort (`QListView` IconMode, titel + status + synopsis). R01.3
- [x] **1.4** Synopsis och sammanfattning per scen, i inspector och på kortet. R01.4
- [x] **1.5** Status och etiketter per scen, redigerbara värdelistor, färg + text. R01.5
- [x] **1.6** Dra-och-släpp och omordning i träd och kortvy, atomiskt. R01.11
- [x] **1.7** Sammanhängande läsvy (Scrivenings): flera scener som ett manus. R01.9
- [x] **1.8** Ordräkningsmål per scen, kapitel och projekt, summerat i hierarkin. R01.10
- [x] **1.9** Samlingar: manuella grupper och sparade sökningar, utan att ändra binderordningen. R01.8
- [x] **1.10** Researchmapp: källor, länkar och bilder skilda från manuset, uteslutna ur export. R01.7
- [x] **1.11** Anteckningar och kommentarer per scen (knyter ihop med valvet). R01.12
- [x] **1.12** Projektmallar: Roman, Fackbok, novell — binderstruktur + statusvärden, separat från dokumentmallarna. R01.13, R03.8
- [x] **1.13** Scener och scenkopplingar: scen som enhet med sammanfattning, POV och kopplade entiteter. R04.2
- [x] **1.14** Manusvarianter och alternativa strukturer. R01.14 — *bara ordningen förgernas (namngiven ordning + lägg på manuset); innehållsligt grenade utkast väntar på snapshots per scen (3.1), som rapporten själv rekommenderar först*
- **Status:** klar — alla punkter 1.1–1.14 avslutade

### Fas 2: Författarlagret

- [x] **2.1** Mål för session och projekt, med progress i statusfältet. `ui/writing_log_panel.py` äger loggen, får ordantalet efter varje ändring (`track()` räknar skillnaden mot förra mätningen — ett ändrat ord är inte ett skrivet ord) och visar dagens netto i panelen och i statusfältet. Projektets mål och andel kommer ur `project.progress()`. R03.1, R03.14
- [x] **2.2** Deadline och dagskvot: `project.daily_quota()` räknas redan i projektmodellen; panelen visar kvoten, hur många ord som är kvar och en stapel, och etiketten bär deadline i sin verktygstext. Utan projekt visas i stället andelen av manusets mål. R03.2
- [x] **2.3** Historik, diagram och svit över faktiska ord per dag: 14 dagar som stapeldiagram (`DayChart`, ritad i widgeten, inga nya beroenden), svit och längsta svit, snitt per skrivdag. R03.3
- [x] **2.4** Sessionshistorik och skrivlogg i SQLite via `core.writing_log` (som redan fanns och nu äntligen nås): dagens rader med added/removed separat, sessioner som startar vid första ändringen och stängs vid flush/stängning, CSV-export genom en filväljare. Loggen ligger i projektmappen när ett projekt är öppet — bokens dagar hör till boken. R03.4
- [x] **2.5** Skrivsprintar och timer: 15/25/45/60 minuter, nedräkning i panelen, avbryt, och vid slut en rad i statusfältet plus `QApplication.alert` (diskret — ingen modal). Antalet ord under sprinten räknas och rapporteras. R03.5
- [x] **2.6** Skrivmaskinsläge utöver befintligt helskärmsläge: `PagedPaper.center_cursor()` håller markörens rad mitt i fönstret medan man skriver, kopplat till markörens rörelse i `ui/editor_view.py`. Läget slås på i Visa-menyn och kommer ihåg sig i configen. Maxbredden var redan satt — arket är A4 (750 px) och texten kan inte bli bredare. Nära dokumentets slut kan ingen centrering ske (det finns ingen text att skrolla förbi), precis som i Word. R03.6
- [x] **2.8** Karaktärsblad och story bible i projektet: `ui/codex_panel.py` visar projektets codex (codex.sqlite i projektmappen) med sökning och typfilter, och ett blad per entitet — namn, alias, vem det är (sparas med kort fördröjning medan man skriver), relationer till andra i boken, scenerna den är kopplad till (klick öppnar scenen) och hur ofta namnet nämns i manuset. Ny/redigera/ta bort, koppla loss scen, lägg till och ta bort relation. `core.storybible` fick `remove_relation`; dialogrutan förifylls vid redigering. R03.9
- [x] **2.9** Tidslinje, plot-tavla och scenöversikt: `ui/plot_grid.py` visar manuset som en tabell — en rad per scen med del/kapitel, tråd (etiketter), POV, status, när i berättelsen den händer, ord och ordmål. Redigerbar direkt i tabellen (status genom en meny med projektets egna statusar), ett klick på titeln öppnar scenen, och sorteringen är poängen: manusordning, **tidslinje** (scenens egen tid, tom tid sist), POV eller status — Dabbles huvudtråd och sidotrådar sida vid sida, utan att lämna projektet. Modellen fick fältet `when` (sparas i manifestet). Tavlan är en egen sida i stacken och inte en flik i sidopanelen: åtta kolumner är ~790 px och panelen är 370. *Medvetet inte gjort:* en grafisk tidslinje (band med markörer) — texten i `when` sorterad i tid är tidslinjen en ensam författare läser, och en ritad tidslinje är en egen vy den dag någon saknar den. R03.10
- [x] **2.10** Taggar, samlingar och anteckningar knutna till scen. Mestadels färdigt sedan tidigare —fas 1.5 (statusfärg), 1.9 (samlingar), 1.11 (scenanteckning) och 2.9 (tråd/etiketter i tavlan) hade redan byggt bitarna. Det som saknades var sista steget i arbetsflödet: samlingen gick att filtrera fram men inte att *arbeta igenom*. Nu har samlingspanelen en läs-knapp som öppnar samlingens scener i läsvyn (`▶`, "Läs samlingen som en text") — och `_show_scrivenings` är utbruten så att hela manuset och en samling går samma väg. R03.11
- [x] **2.12** Revisionsläge och mål per utkast: plot-tavlan har en **Utkast**-kolumn (1–9, samma gränser som sceninspektören, redigerbar direkt i tabellen och skriven till manifestet) och ett **utkastfilter** — välj utkast 2 och tabellen visar bara de scener som nått dit, med räkningen "1 av 3 scener i utkast 2". Det är revisionsläget: arbetet blir en lista i stället för ett helt manus. *Målet per utkast* blev räkningen i stället för ett talfält per utkast — målet för ett utkast är att scenerna har nått det, och nio målfält som ingen fyller i är sämre än en siffra som stämmer. Vill du ha egna ordmål per utkast är det ett fält i projektdialogen; säg till. R03.13
- [x] **2.14** Övningar mot skrivblock ("vad händer nu?"): forskningens arbetsflöde satt rakt av — välj en fråga, få tre förslag, granska, välj eller ignorera, och återgå till skrivandet. Fyra kategorier (Vad händer nu? / Dialog / Handling / Sinnesintryck, efter Sparks), `core/exercises.py` bygger frågan och tolkar svaret (rent, eget självprov på 11 kontroller), och `ui/exercise_dialog.py` visar svaren. Det valda förslaget hamnar i **scenens egen anteckning**, inte i manuset: förslagen är vägar in, inte färdig prosa — och anteckningen är samma sammanhang som AI:n läser nästa gång. Anropet går genom den befintliga AI-klienten, så ingen ny nyckel eller leverantör behövs. R03.16
- [x] **2.15** Läsbarhetsanalys och stilråd i texten: LIX fanns i `core/document_stats.py` och visades i panelen, men ingenstans i texten. Nu finns `sentence_ranges(text, max_words=20)` (ren funktion, eget självprov) och `ReadabilityHighlighter` i editorn, som markerar tunga meningar med en **prickad understrykning** — formen bär betydelsen, färgen förstärker. Markeringen är en *vy*-format (som kommentarerna): texten rörs inte och inget hamnar i scenfilen. Slås på i Visa-menyn och kommer ihåg sig i configen. Valet av enhet är inte slumpat: meningen är det LIX drivs av, så markeringen visar precis det rådet gäller. R03.17
- [x] **2.16** Projektöversikt och anteckningar: **Arkiv → Projektöversikt** (Ctrl+Shift+O) visar
      var boken står på ett ställe — ord mot mål, dagskvot mot deadline, scener, status, utkast,
      trådar (etiketterna som faktiskt används), antalet anteckningar i valvet, **länkar som inte
      leder någonstans** (kontinuitetskollen som inte kräver en tung plotmodell) och projektets
      instruktioner i kortform. Allt räknas ur projektet och valvet som redan finns —
      `overview_rows()` är ren och provas mot oberoende räkningar. Valvet är projektets
      anteckningslager i vyn; **inga filer flyttas och valvet delas inte per bok** (hans
      anteckningar och länkarna mellan dem ligger kvar som de är — att splitta valvet per bok är
      ett eget beslut, säg till om du vill ha det). R03.18
- [x] **2.17** Projektinstruktioner till AI:n: projektet har ett fält (`settings["ai_instructions"]`)
      som författaren fyller i — ton, tempus, namn, allt som ska vara lika hela vägen — och som
      läggs **sist** i systemprompten, närmast uppgiften. Ett tomt fält lämnar prompten orörd, en
      trasig källa eller ett stängt projekt stoppar inte anropet, och fönstret pekar AI:n på det
      projekt som är öppet just nu i stället för att kopiera texten. Menyväg: Arkiv →
      Projektinstruktioner. Alla tre AI-vägarna (granskning, omskrivning, övningar) går genom samma
      `_system_prompt`, så regeln bor på ett ställe. R03.18
- [~] **2.18** Scenstatistik ur modellen: **modulen är byggd och grindad**
      (`core/story_stats.py`, 13 egna kontroller): scener per karaktär, karaktärernas inträde och
      utträde, POV-fördelning, ord per scen och kapitelsummering som bara räknar sina egna scener.
      Panelen visar POV-fördelningen i sin sammanfattningsrad, och per-scen-siffrorna finns redan i
      plot-tavlan (2.9). **Kvar:** karaktärstabellen (scener, ord, första/sista scen, nämnd vs
      kopplad) nås inte i gränssnittet — den är byggd och provad men har ingen egen vy. R06
      (Fictionary, bibisco)
- [x] **2.19** Scenens story-element-checklista och Story Map: `core/story_elements.py` bär de
      **tjugo** element som researchrapporten belägger, grupperade i Fictionarys tre familjer
      (karaktär, handling, miljö) — POV-karaktär och mål, hinder, andra på plats, förändring,
      scenfunktion, öppning, hook, tension, avslöjande, bakgrund, action/sequel, läsarens vetande,
      utfall, avslutning, plats, tid, sinnen, väder, emotion. **Inte 38:** rapporten belägger
      familjerna och de namngivna elementen, inte deras fulla lista, och att fylla ut de återstående
      arton vore att hitta på en konkurrents taxonomi (står i modulens docstring).
      `ui/elements_dialog.py` (7 kontroller) frågar per familj och sparar bara besvarade element;
      sceninspektören har knappen med räknaren ("2 av 20"), plot-tavlan har en elementkolumn och en
      **Story Map-sortering med luckorna först**, och elementen följer med i `project.json`
      (verifierat av `ui_smoke` avsnitt 50, som också provar sorteringen och omläsningen från disk).
      Provet läser dessutom **båda språkfilerna** och kräver en etikett per element — en ny nyckel
      utan etikett visar en rå nyckel i gränssnittet. R06 (Fictionary StoryTeller)
- [x] **2.20** Beat sheet-mallar som data: fyra nya projektmallar i `PROJECT_TEMPLATES` — Save the
      Cat (15 beat), Tre akter, Hjältens resa (12 steg) och Mysteriet (9 beat) — där varje beat blir
      ett kapitel med en scen, så beatens namn står i trädet och kortet bär scenens synopsis. Namnen
      visas på båda språken (nya i18n-nycklar). Provat i `core.project`: rätt antal beat, en scen per
      beat, egna filer trots att flera scener heter samma sak, och att varje beat har en scen under
      sig. R07 (Plottr har 20+, Campfire fler)
- [ ] **2.21** Karaktärsintervjun: en frågesvit per codexpost som fyller posten, genom den
      befintliga AI-klienten. R07 (bibisco)
- [x] **2.22** Relationsgraf i codexet: `ui/codex_graph_dialog.py` ritar entiteterna som noder och
      relationerna som kanter, med radien efter antal kopplingar, och **ett klick på en nod väljer
      posten i codexpanelen** — grafen är en väg tillbaka till karaktärsbladet, inte en bild vid
      sidan av. Den är en tunn underklass till valvets rityta: matematiken flyttades till
      `circle_layout()` i `ui/graph_dialog.py` och delas av båda, så ritningen, hover och
      klickträffen finns på ett ställe. Knappen (🕸) står vid relationerna i codexpanelen.
      9 egna kontroller plus 4 i `ui_smoke`, som fångar dialogen genom att byta ut `exec` och
      prövar att en borttagen relation försvinner ur grafen. R07 (Campfire, World Anvil)
- [x] **2.23** Händelsetabell kopplad till scen: `core/events.py` (20 egna kontroller) ger en
      händelse en tid, en beskrivning och en **lista av scen-id:n** — samma händelse kan alltså
      återanvändas i flera scener, och en scen kan ha flera händelser. Scenens egen tid (`when`)
      säger *var* den ligger, händelsens tid *vad* som händer; de två behöver inte vara samma.
      `ui/events_dialog.py` (14 egna kontroller) är tabellen: tid och beskrivning skrivs direkt,
      och scenen som är öppen kopplas med en knapp. 📅 i plot-tavlan (där tidslinjen sorteras)
      begär den, och fönstret sparar manifestet — `ui_smoke` avsnitt 51 kör hela vägen från
      knappen till projektfilen på disk. En borttagen scen lämnar ingen tom rad i listan.
      Ingen ritad vy, som beslutet i 2.9 säger. R07 (bibisco, World Anvil, Plottr)
- **Status:** complete (två undantag flyttades till fas 4 som 4.14–4.16: pauspåminnelser, namn- och
  ordförrådsgenerator, blurb/synopsis — de hörde hemma med sakprosan). 2.18–2.23 kommer ur det andra
  researchpasset (2026-10-08) och är **inte byggda**: `[ ]` är hela sanningen om dem.

### Fas 3: Revision och granskning

- [x] **3.1** Snapshots per scen: modellen fanns (oföränderlig kopia + tidsstämpel + etikett +
      `diff()` + `restore()`), men **ingen UI och ingen väg in** — lagret var byggt och oanvänt. Nu:
      Arkiv → Versionshistorik (Ctrl+Shift+H) visar scenens punkter, skillnaden mot texten som
      ligger på disk nu, och en väg tillbaka. En punkt tas automatiskt **när en scen öppnas** (så
      texten finns som den såg ut när man lämnade den), och bara om den skiljer sig från den
      senaste — annars fylls historiken av kopior av samma mening. R01.6, R02.4
- [x] **3.2** Spårade ändringar som operationer, acceptera/avvisa enskilt: `core/revisions.py` gör
      ändringar till operationer (typ, gammal och ny text, ankare, stycke) och beslutar per stycke;
      `ui/review_dialog.py` visar dem med **kryssad rad = behåll**, förhandsvisar exakt den text som
      skrivs, och Arkiv → Granska ändringar sedan senaste punkten (Ctrl+Alt+R) är vägen dit. Texten
      före granskningen sparas som egen punkt, så ingreppet går att ångra. **Jämförelsen läser text,
      inte HTML** — annars vore varje sparning en ändring, eftersom Qt skriver om attributen (det är
      fällan forskningen varnar för). Ett `<ul>` med sina `<li>` är en enhet, så inget beslut kan
      lämna halv HTML. Detaljnivån finns nu också: `word_diff()` visar vilka **ord** som gick och kom
      i ett omskrivet stycke, i radens verktygstips. Besluten är kvar per stycke — en läsare får
      ordningen, men tar ställning till stycket. R02.1
- [x] **3.3** Kommentarer i marginalen med tråd och "löst": kommentarerna, markeringarna i
      texten, hoppa-till-citatet och **löst** fanns redan färdiga i scenpanelen (kontrollerat, inte
      antaget). Det som saknades var **tråden**: `add_reply()` i projektet, en ↳-knapp i panelen och
      svar som indragna rader direkt efter sin kommentar — med kommentarens id, så ett klick på ett
      svar går till samma citat. Kommentarer som sparades innan trådar fanns får sin tomma lista av
      `setdefault`, så gamla projekt öppnas som förut. Tråden hänger kvar under en löst kommentar.
      R02.2
- [x] **3.4** Jämför dokument och slå ihop versioner: granskningen kan nu köras mot **vilken punkt
      som helst**, inte bara den senaste — historiken har knappen "Granska mot texten nu", och
      fönstret kör samma väg som för senaste punkten. Originalet förblir orört: punkten läses,
      texten jämförs, och ingenting skrivs förrän granskningen är verkställd (forskningens
      blackline-arbetsflöde). Provat: mot den äldsta punkten syns ändringen sedan dess, mot den
      senaste färre och utan den äldre ändringen — det är skillnaden mellan att välja original.
      Själva sammanslagningen är densamma som acceptans per stycke gav i 3.2. R02.3
- [x] **3.5** Jämförelse av formatering, separat från textdiff: formateringen hålls utanför
      ändringarna. `formatting_changes()` räknar de stycken där **texten är oförändrad men
      markupen inte** (kursiv, indragning, rader) och rutan säger det i en rad ovanför listan i
      stället för att göra dem till ändringar man ska ta ställning till. Provat: kursiv text ger
      noll textändringar men en formateringsnot. R02.15
- [x] **3.6** Versionshistorik och återställning i ett samlat flöde: historiken öppnas med
      osparade ändringar, och de sparas först — annars jämförs punkterna mot en text på disk som är
      äldre än den man ser. En återställning sparar texten som låg där **först** som en egen punkt
      ("före återställning"), så ingreppet går att ångra med samma knapp som allt annat. R02.4
- [x] **3.7** AI-kommentarer i marginalen i stället för överskrivning: varje förslagskort i
      AI-panelen har nu en 💬-knapp som lägger förslaget som **kommentar på sitt citat** i stället
      för att skriva över texten. Texten står kvar orörd, författaren läser förslaget där hon läser
      sina egna kommentarer, och samma förslag två gånger blir en kommentar — inte två. Provat hela
      vägen: kortets knapp → signalen → kommentaren på citatet med förslaget i sig → syns i
      marginalen, och manuset tecken för tecken oförändrat. R04.14
- [x] **3.8** Acceptans per förslag, som eget undo-steg: `+`-knappen skriver in **ett** förslag i
      taget som ett enskilt `insertText` över markeringen — alltså ett steg i ångra-historiken, och
      ett ångra tar tillbaka hela förslaget. Provat: förslaget in, ett ångra ut, och ett förslag som
      inte går att hitta i texten (citatet kan ha ändrats) skriver ingenting utan säger det i
      statusfältet. R04.15
- **Status:** pending

### Fas 4: Sakprosan

- [x] **4.1** Fotnoter med automatisk numrering och navigering: markeringen `[not: …]` står i texten
      och **numret räknas fram ur ordningen**, så att flytta ett stycke är att numrera om. Panelen har
      fliken *Noter och figurer* — registret — där varje not står med sitt nummer, och ett klick sätter
      markören vid markeringen. Exporten gör markeringen till en riktig upphöjd notlänk och samlar
      noterna under "Noter" i filen. Provat: infogning, numrering i ordning, registret, klicket och
      exporten. R02.5
- [x] **4.2** Korsreferenser till rubriker (fält, inte rå text): `[ref: Rubrikens text]` blir
      "se kapitel 2" — man väljer rubrik i en lista med kapitelnumren, i stället för att skriva dess
      text och hoppas. Rubriken slås upp utan hänsyn till skiftläge och inledande nummer, och en
      hänvisning som inte hittar sin rubrik **står kvar orörd** i stället för att bli en tyst felaktig
      siffra. Provat: vägran utan rubriker, uppslagningen, och den färdiga texten i exporten. R02.6
- [x] **4.3** Genererad innehållsförteckning, uppdaterbar: rubrikerna läses ur dokumentets
      rubriknivåer, får kapitelnummer (`number_headings`: 1, 1.1, 1.2, 2 — och en överhoppad nivå blir
      1.1, inte 1.0.1), och listan står mellan `[innehåll]` och `[/innehåll]`. Trycker man en gång till
      **uppdateras listan i stället för att en ny läggs till** — provat (en förekomst, inte två).
      Klickbarheten ligger i panelens rubriklista, som hoppar till rubriken i texten. R02.7
- [x] **4.4** Rubriknavigatorn: panelens Kapitel-flik har fyllts ur dokumentets rubriknivåer sedan
      tidigare, och ett klick hoppar till rubriken. **Verifierat** i rökprovet hela vägen: en rubrik
      sätts med verktygsradens stilsättning → den hamnar i navigatorn (med indrag efter nivå, ▪ för
      nivå 2) → ett klick sätter markören exakt på rubriken (16 mot 16) → och ett vanligt stycke
      hamnar inte där. Det som saknades var provet, inte funktionen. R02.17
- [x] **4.5** Bildtexter med automatisk numrering + register: `[figur: …]` och `[tabell: …]` får
      egna serier (Figur 1, Tabell 1) och blir "Figur 1. Trappan från hallen." i filen. Registret är
      samma panelflik som noterna — figurerna och tabellerna med sina nummer, i textens ordning.
      Provat både i registret och i den exporterade texten. R02.8
- [x] **4.6** Stycke- och teckenstilar och stilmallar: styckeformaten är blockroller (rubrik 1–3,
      citat, kod) och sätts i verktygsraden; teckenformaten (fet, kursiv, understruken, genomstryken,
      upphöjd, nedsänkt) likaså; och **stilmallarna** (`core/templates.py`: roman, novell, fackbok …)
      ger ett nytt projekt sina statusar och sitt ordmål — rökprovet arbetar i ett projekt skapat med
      mallen "roman" genom hela körningen. **Provat** rubriknivån (2) och teckenformatet (vikt 700).
      Ett klick på den stil som redan gäller **tar bort den** (Alex 8/10): pillerna sitter i en
      exklusiv QButtonGroup och Qt kryssar aldrig ur den som redan är vald, så avgörandet ligger i
      handlern — och borttagningen skriver tillbaka dokumentets eget typsnitt, storlek och färg,
      eftersom rollerna sätter dem på *texten* och `mergeCharFormat` bara kan skriva över. Mätt:
      efter andra klicket på kod är rollen tom, fastbredden av och typsnittet tillbaka till
      dokumentets eget.
      Rubrikstilarna nådde förut bara blockets standardformat, inte texten: text från en sparad scen
      bär egna teckenformat, så nivån sattes medan texten stod kvar i 11 pt — "det händer inget när
      man har text markerad och klickar på h1, h2 eller h3" (Alex 8/10). Nu läggs formatet på texten
      genom `richtext.apply_block_formats`, mätt: 11 pt/vikt 400 blir 22 pt/700.
      Arket var mätt en riktig A4 (750x1060 px = 210x297 mm i 90 dpi, 2994 tecken per ark), men temats
      stilmall hade graden hårdkodad på duken, så varken `default_font_size` eller Ctrl++/Ctrl+- hade
      någon verkan (mätt: 13,0 pt och radhöjd 19 px före och efter) — och pappret stod still medan
      texten kunde ändras, så en zoomad sida rymde färre tecken än en sida. Nu äger vyn graden
      (`EditorView.set_text_point_size`), arket följer samma grad (`PagedPaper.set_scale`), zoomen
      minns sig i `zoom_level`, och autoläget ritar pappret så att en A4 fyller fönsterbredden —
      verklig storlek är Ctrl+0.
      *Medvetet inte gjort:* en stilinspektör som listar dokumentets stilar med räknare — ingen
      författare har saknat den, och en förteckning över sina egna rubriker finns i navigatorn. R02.9
- [~] **4.7** Avsnittsbrytningar med separata sidhuvuden/sidfötter — **flyttad till fas 5 (5.5)**.
      Detta hör till utskriften, inte till skrivandet: det kräver sidvis layout (sidindex → inner/
      ytter) i utskriftsvägen, samma sak som den befintliga anteckningen i 0.2 pekar på. En författare
      märker det först när boken ska tryckas, och då är 5.5 rätt plats. Att bygga det nu hade varit
      att bygga sidnumrering två gånger. R02.10
- [ ] **4.8** Spalter och avstavning. R02.11 — *låg*
- [x] **4.9** Autokorrigering och autotext: `core/autocorrect.py` har funnits sedan 0b men **nådde
      aldrig gränssnittet**. Nu ligger den i Redigera-menyn (Ctrl+Shift+K) och kör över scenen.
      Provat: `teh` → `the`, `"hej"` → `”hej”`, `...` → `…`, fler fel i samma scen, **fetstilen runt
      ordet står kvar** (vikt 700) och en gång till hittar ingenting. Bara de områden som faktiskt
      skiljer skrivs om, och allt sker i ett edit block — ett ångra tar tillbaka hela körningen.
      R02.12
- [x] **4.10** Språk per textavsnitt, stavning och grammatik: `core/spellcheck.py` har funnits
      sedan 0b (verifierad mot riktiga tjänsten, UTF-16-korrekta offset) men **nådde aldrig
      gränssnittet** — samma mönster som sök och autokorrigering. Nu i Redigera-menyn (Ctrl+Shift+G)
      och i panelens Språk-flik. **Ett språk per avsnitt:** stycken med egen språkmärkning skickas för
      sig, resten med scenens språk — provat att ett stycke märkt engelskt kontrolleras som engelskt.
      Träffarna står i panelen med ordet, meddelandet och förslagen; ett klick markerar ordet i
      texten, ett dubbelklick tar första förslaget (**ett** ångra-steg). Adressen står i panelen —
      texten lämnar datorn, det ska man veta om — och en tjänst som inte svarar säger *varför* i
      stället för att visa en tom lista. Egen server ställs in med `spellcheck_endpoint`. R02.13
- [ ] **4.11** Tecken-/symboltabell och tesaurus. R02.14 — *låg*
- [x] **4.12** Sök och ersätt med reguljära uttryck: `core/find_replace.py` har också funnits utan
      att nås. Nu i Redigera-menyn (Ctrl+F och Ctrl+H), icke-modal (man ska kunna skriva vidare) med
      räknare, mönster, skiftläge och hela ord. Provat: räknaren, sök nästa markerar träffen, Ersätt
      alla byter alla och **ett** ångra tar tillbaka hela ersättningen, mönster med bakåtreferens
      (`(skriv)en` → `\1et`). R02.16
- [ ] **4.13** Tabeller med formler och ekvationer. R02.18 — *låg*
- [x] **4.14** Pauspåminnelser, valbart: en klocka (50 minuter, `pause_minutes` i inställningarna)
      som säger till i **statusfältet** och blinkar i aktivitetsfältet — ingen modal ruta som avbryter
      mitt i en mening, samma diskreta form som sprintens slut. Valet kommer ihåg sig. Provat:
      på/av, att valet sparas, och att påminnelsen syns. *Flyttad från fas 2 (2.7).* R03.7
- [x] **4.15** Namn- och ordförrådsgenerator: två nya kategorier i "Fastnat?"-rutan — **Namn** och
      **Ord och uttryck** — som ber om tolv alternativ i stället för tre (antalet står per kategori,
      och tolkningen följer kategorin, inte ett tak i koden). Ett valt **namn läggs i codexet** med
      noten som sammanfattning — ett namn hör till boken, inte till scenen — medan en väg vidare
      fortfarande hamnar i scenens anteckning. Provat: antalen, tolkningen, codexet och att scenens
      anteckning inte rörs av ett namn. *Flyttad från fas 2 (2.11).* R03.12
- [x] **4.16** Blurb och synopsis som projektfält: baksidestext och sammanfattning ligger i
      projektöversikten (Ctrl+Shift+O) och sparas i projektfilen när rutan stängs. De hör till
      **projektet**, inte till scenen — de beskriver boken. Provat: att båda sparas och att de står i
      `project.json` på disk. *Flyttad från fas 2 (2.13).* R03.15
- **Status:** complete (556 rökprov + 54 renhetsprov + modulernas egna, GRÖNT)
- [x] **4.17** Repetitions- och konsistensanalys över **hela boken**, med klickbar rapport:
      `core/analysis.py` (15 egna kontroller) hittar upprepade ord och fraser, namnvarianter ett
      tecken från ett codexnamn, versal/gemen som glider och codexnamn som aldrig nämns — och
      `ui/insight_panel.py` (11 egna kontroller) visar dem som en lista där ett klick öppnar scenen
      och **markerar textstället** (citat + förekomst), med filtret per fyndtyp och
      POV/siffror i sammanfattningsraden. `ui_smoke` avsnitt 49 kör hela kedjan och kräver att
      markören står på ordet efter klicket.
      **Mätt, och det ändrade konstruktionen två gånger.** Först: ren förekomst-räkning gav
      **10 336 fynd** på 120 000 ord. Sedan mättes modulen mot **tre riktiga svenska romaner**
      (Dan Andersson, Almqvist och en novellsamling, 37 000–54 000 ord var) och då föll två saker:
      (a) romanerna gav 552–892 fynd och **toppen var "bara (189 gånger)"** — vanligt språk som råkar
      ha ett närbeläget par någonstans, inte en tic; (b) fraslistan dominerades av "att gå (21)",
      "att bli (15)" — grammatik, inte stil. Reglerna är därför: ett fynd kräver **två täta**
      förekomster inom 20 ord, och en fras som börjar eller slutar i ett funktionsord räknas inte.
      Efter det: **82–154 fynd per bok**, med namn och tics i toppen ("david", "nilenius", "älskar"),
      och 316 fraser blev 31. Analysen tar 0,1–1,8 s, alltså körs den när författaren ber om den.
      R06 (ProWritingAid, AutoCrit)
- [x] **4.19** Stilvarningar ur ordlistor: `core/style_rules.py` (12 egna kontroller) fångar
      fyllnadsord, klichéer, färgade dialogtaggar och adverb — de klasser som går att **lista**.
      Passiv form och ordklasser kräver taggning och lämnas åt LanguageTool (4.10): en gissning som
      pekar fel i författarens text är värre än ingen varning. Adverben täcker bara de entydiga
      ändelserna (-ligen, -ly), eftersom svenska -t-adverb (snabbt, gärna) inte går att skilja från
      adjektiv utan taggning. Båda språkens listor körs alltid — ingen språkdetektering behövs.
      **Mätt på de tre romanerna och det stramade listan:** med vanliga räkningsord och förbehåll
      (mycket 104, nästan 87, kanske 53) i fyllnadslistan toppades rapporten av dem, och en varning
      som pekar på vanligt språk lär författaren att strunta i rapporten. Efter stramningen: **80
      stilfynd på 140 000 ord** (17–34 per bok), topp "liksom", "alltså", "ganska", "riktigt" —
      och de färgade dialogtaggarna ("skrek", "mumlade", "utbrast") syns som en egen klass.
      Fyndet hamnar i den scen där ordet är tätast, och klicket markerar ordet i texten
      (`ui_smoke` avsnitt 49). R06 (ProWritingAid, AutoCrit, Papyrus)
- [ ] **4.20** *Uppskjutet efter beslut (Alex 8/10):* Uppläsning för korrekturläsning: läs upp stycket, kapitlet eller scenen med
      TTS — örat hittar det ögat hoppar över. Dabble, AutoCrit och NovelAI har det; vår diktering
      (Whisper) är bara tal→text. R06, R09
      Uppläsning kostar pengar per tecken och är inte värt det än. Ingen kod skriven.
- [x] **4.21** Analysrapport per kapitel: panelen kan gruppera samma fynd under sin kapitelrubrik
      med kapitlets ordtal ("7 fynd · 3 140 ord") — den vy en författare arbetar igenom kapitel för
      kapitel, i stället för en lista över hela boken. Grupperingen bygger på
      `core.story_stats.chapter_rows`, som nu bär sina scen-id:n (en siffra utan sina scener går
      inte att gruppera). Ett fynd i en scen utan kapitel hamnar under en egen rubrik, och ett
      codexnamn som aldrig nämns har ingen scen alls — det fyndet får ingen ordräkning i stället för
      att krascha (hittat av `ui_smoke`, inte av mig). 18 kontroller i panelen, 6 i `ui_smoke`
      avsnitt 49. R06 (ProWritingAid Chapter Critique, AutoCrit Summary Report)

- [x] **4.22** Stilanalys på alla elva språken: svenska och engelska har sina listor i
      `core/style_rules.py` (stramade efter mätningen på tre romaner), och de nio nya hämtar sina
      ur `resources/style_words.json`. Listorna **väljs av manusets språk** — elva listor samtidigt
      gör varje homograf till en falsk träff ("halt" är ett tyskt fyllnadsord och en svensk paus) —
      och de bär bara det entydiga: färgade dialogtaggar och flerordiga fraser. Rådet namnger
      manusets eget ord (`style_note_consider_said` med `{word}`, ifyllt per språk), franska taggar
      matchas före bindestrecket ("chuchota-t-elle"), och självprovet bevisar att svenskan **inte**
      larmar om tyskans tagg. **Kvar:** enkelords-fyllnadsord och adverbändelser för de nya språken
      väntar på samma mätning som svenskan fick — en gissning som pekar fel i författarens text är
      värre än ingen varning.

- [x] **4.23** Fokusläget (F11) tappade menyraden. Läget avgjordes av `isFullScreen()`, ett
      tillstånd fönsterhanteraren äger: lämnar kompositören fullskärm på egen hand (sin egen
      genväg, eller sin egen hantering av F11) svarar `isFullScreen()` nej medan menyn
      fortfarande är borta — nästa F11 går då in i samma gren och gömmer allt igen, och menyn
      kommer aldrig tillbaka. Programmet äger nu sitt eget läge (`_focus_mode`), och
      `changeEvent` ger tillbaka menyn även när fullskärmen lämnas av någon annan. Menyraden
      är inte `QMainWindow`:s egen utan en `QMenuBar` inuti menywidgeten (`setMenuWidget`), så
      den visas och göms uttryckligen. Rökprovets sektion 56 mäter hela vägen, inklusive att
      nästa F11 går *in* i läget i stället för in i samma gren som förut.

### Fas 5: Publiceringen

- [~] **5.1** Formatprofiler för KDP, IngramSpark, Lulu, Apple Books och Kobo: `core/publishing.py`
      bär kanalerna som **data med källa** (34 egna kontroller), och Arkiv → Publicering… räknar fram
      gutter, ryggbredd och omslagsmått ur trim, papper, sidantal och blöd — och skriver in trim och
      marginaler i sidinställningarna. **Kvar:** ett *sparat* publiceringsprojekt per bok (kanal, trim
      och metadata som en del av projektet, inte bara i appens inställningar). R05.1
- [x] **5.2** EPUB 3 med semantisk kapitelstruktur och TOC: `core/epub.py` har funnits sedan 0b men
      **nåddes aldrig från exportmenyn** — samma mönster som sök, autokorrigeringen och språkkontrollen.
      Nu i Arkiv → Exportera EPUB…, med kapitel delade vid rubrikerna (h1 → egen XHTML + nav), bilder
      med alt-text och en navigation document. Provat ända in i filen: EPUB:en packas upp, OPF:en läses,
      och titel, författare, språk, ISBN, tillgänglighetsmärkning, nav och båda kapitelfilerna
      kontrolleras. R05.2
- [x] **5.3** Rollerna (citat, kod) bär nu i **alla tre kanaler**: EPUB:en får `blockquote` och
      `pre` som *taggar* och en CSS som ger dem utseende (citatet indraget och kursivt, koden
      monospace med bakgrund och kant), Word får **namngivna stilar**, och utskriften får rollernas
      formatering genom dokumentet — rollen sätter både semantik och utseende när den läggs på, så
      papperet visar samma sak som skärmen. Provat i alla tre: stiltypen läst ur den skrivna
      .docx-filen, CSS:en och taggarna ur den skrivna EPUB:en. R05.3
- [~] **5.4** Metadata och ISBN: författare, förlag och ISBN är nu **projektfält** (i
      projektöversikten, där baksidestexten bor) och går rakt in i EPUB:ens metadata — `dc:creator`,
      `dc:publisher`, `dc:identifier` och baksidestexten som `dc:description`. Provat att de överlever
      till filen. **Och front matter som sidor:** EPUB:en får en genererad **titelsida** och en
      **kolofon** (förlag, ISBN, år och rättighetsrad) ur bokens egna uppgifter — bokens första sidor är
      uppgifter man *har*, inte text man skriver, och skrivna för hand ska de hållas i minne och
      uppdateras manuellt när förlaget eller ISBN:t ändras. De står först i läsordningen och listar sig
      inte själva i innehållsförteckningen. Provat: två filer, titel och författare på titelsidan,
      ISBN/förlag/år i kolofonen, fyra poster i ryggraden och ingen frontmateria i innehållet. **Kvar:**
      samma sidor i *utskriften* (där skriver författaren dem i dag) samt dedikation och tack som fält.
      R05.4
- [~] **5.5** Trycklayout: trim, gutter och spegelmarginaler **beräknas** nu (KDP:s trappa 9,6–22,3 mm
      efter sidantal, ytterkant 6,4 mm, +3,2 mm med blöd) och skrivs in i sidinställningarna med
      `mirror_margins`, udda/ämn sidväxling och folio längst ner. **Och utskriftsvägen verkställer
      speglingen:** en speglad profil får samma marginal på båda sidor, lika med den inre (guttern),
      så att innermarginalen aldrig hamnar på fel sida i en färdig bok — provat på skrivarens egen
      sidlayout (12,7/12,7 med spegling, 6,4/12,7 utan, toppmarginalen orörd). **Kvar:** den *riktiga*
      växlingen mellan udda och jämn sida kräver en paginerad målare (sidindex → inner/ytter) — tills
      någon ska trycka är den symmetriska marginalen aldrig fel, bara frikostig — samt kapitelstart på
      höger sida och blanka fyllnadssidor. **Och papprets storlek hanteras som i Writer** (mätt där
      över UNO, LO 26.8): storleken är en *sidans* egenskap — `Width`/`Height` i 1/100 mm plus
      `IsLandscape` som flagga, aldrig ombytta tal — och den **styr pagineringen** utan att skala
      texten (samma 400-raders text blev 8 sidor på A4 och 12 på A5), ett omöjligt mått behålls som
      beställt (60×60 mm med 40 mm marginaler förblev 60×60, textyta −20 mm) och bara pappersfacket
      är skrivarberoende. Nu finns `core/page_format.py` som enda sanning (A3–A6, B5, Letter, Legal,
      Tabloid, Anpassad med egna mm); Arkets storlek på skärmen, PDF:en och DOCX:en läser samma
      funktion. Mätt: A4 595×842 pt / 9 sidor, A5 420×595 / 13 sidor, liggande A4 842×595, 6×9
      432×648 pt, Letter 612×792; DOCX `<w:pgSz>` 11906×16838 (A4), 8391×11906 (A5), 8640×12960
      (6×9) — förut skrevs ingen `pgSz` alls och Word ärvde Letter, och utskriftsvägen gjorde allt
      som inte hette Letter till A4. Måtten bor nu i **projektet** (som en sidstil i dokumentet),
      configen är bara grunden för ett nytt projekt. **Kvar:** flera sidstilar i samma dokument
      (porträtt första sida, liggande resten) — det kräver sidstilsbegreppet, inte bara en storlek.
      R05.5 (+ 0.2)
- [x] **5.6** Omslagsarket ritas: Arkiv → **Rita omslagsarket…** ger en PDF i kanalens exakta mått
      (baksida + rygg + framsida + blöd), med vikstrecken utmärkta, bokens uppgifter på plats och
      ryggbredden räknad ur sidantal och papper — och med titeln och författaren även på ryggen när
      den är bred nog (≥ 6 mm). Är ingen tryckprofil vald blir det **inget ark**: ett omslag i
      fel mått är värre än inget. Geometrin ligger som en ren funktion (`cover_layout`, millimeter
      utan Qt) och provas för sig; ritandet är ett tunt skal. **Mätt på filen:** MediaBox i den
      skrivna PDF:en är 311,1 × 234,9 mm mot uträknade 311,2 × 235,0 — alltså kanalens mått och
      liggande ark, inte A4. Omslaget följer också med i släppet när profilen är vald. R05.6
- [x] **5.7** DOCX med namngivna Word-stilar: citat blir `Quote` (finns i Words standardmall), kod blir `Code Block` — stilen **skapas i filen** när mallen inte har den, vilket är hela poängen: en redaktör ska kunna restyla bokens kodblock i ett svep i stället för att jaga direkt formatering. Rubrikerna använder redan `Heading 1–3`. Stilnamnen är språkoberoende i filen och visas på svenska i svenskt Word. Provat: `['Heading 1', 'Normal', 'Quote', 'Code Block']` läst ur den skrivna filen. R05.7
- [x] **5.8** Tillgänglighetsmetadata (`accessMode`, `accessibilityFeature`, `accessibilityHazard`)
      skrivs i OPF:en och provas i rökprovet. **Och EPUBCheck som val:** Arkiv → Kontrollera EPUB
      med EPUBCheck… kör den riktiga kontrollen — det förlag och butiker själva kör — och släppet
      kör den automatiskt när den finns. Är den inte installerad kommer ett **tydligt besked**: om
      Java finns, var `epubcheck.jar` ska läggas (fem kända platser, eller `EPUBCHECK_JAR`), och att
      boken redan är skriven — kontrollen är ett val, inte ett krav. Ett program som startar men inte
      svarar som EPUBCheck **säger det**: en trasig jar får aldrig bli "inga fel", för en ren
      förklaring på en okontrollerad bok är det farligaste svaret av alla. R05.8
- [~] **5.9** Slutkontrollen: **Arkiv → Släpp boken…** samlar EPUB:en, tryck-PDF:en och en rapport i
      en mapp. Rapporten (`RAPPORT.md` + `release.json`) säger vad som ligger där, när det byggdes,
      vad varje fil väger och dess **SHA-256**, så att frågan "är det här samma fil som i går?" går att
      svara på. Preflighten säger vad kanalen skulle klaga på *innan* filen skickas: kanalens egna
      varningar översatta till svenska, tom baksidestext, saknat ISBN, udda sidantal, ingen vald
      tryckprofil — och en fil som inte kunde skrivas **namnges i stället för att tyst försvinna**.
      Provat: fyra filer i mappen, summan är filens egen (omräknad i provet), rapporten bär titeln ur
      projektet och PDF:en är 9 109 byte. **Kvar:** själva uppladdningen till distributören (KDP:s
      API), som kräver kontouppgifter och hör till ett eget beslut. R05.10
- [x] **5.10** Svensk och engelsk boksättning: repliktankstreck och citattecken har funnits i
      `autocorrect.apply_typography` sedan fas 4 (som ett *medvetet* menyval — exporten rör aldrig
      författarens text i smyg). **Avstavningen är ny:** mjuka bindestreck (U+00AD) sätts i löptexten
      vid export till EPUB och i den tryckta kopian, med pyphens ordlistor (LibreOffice-mönstren) och
      bokens språk — `verklighetsuppfattningen` blir `verk-lig-hets-upp-fatt-nin-gen`. Ett mjukt
      bindestreck syns bara om raden faktiskt bryts där, och texten är förlustfri utan dem. Aldrig i
      kod, och aldrig i Word-exporten: redaktörens Word avstavar själv. Provat i den skrivna EPUB:en
      (i löptexten, inte i koden, och ordet intakt utan bindestrecken) och på den tryckta kopian.
      **Qt 6 har ingen avstavning** — `QTextOption.setHyphenationFactor` finns inte i PyQt6, mätt i
      den här miljön; därför pyphen. R05.11
- [x] **5.11** Efterbearbetning i Sigil/Calibre: **checksumman finns** (i rapporten, per fil),
      **mappen öppnas** ur Arkiv → Öppna utgivningsmappen (datorns filhanterare, via Qt:s egen väg
      så att det fungerar på fler skrivbord än ett), och paketet är den mapp man sedan arbetar i.
      R05.9
- [ ] **4.18** *Uppskjutet med flit:* samtalshistorik och valbar retrieval i AI-panelen (Claude/ChatGPT
      Projects-mönstret, R04.18). Projektinstruktionerna (2.17) och referensmaterialet (1.10) finns och är
      klara; det som saknas är att AI:n får *historiken* och själv får söka i materialet i stället för att
      allt klistras in i prompten. Inte byggt — ett eget beslut, och ingen har frågat efter det än.
      Se `docs/research/author-tools/tackning.md`.
- [x] **5.12** Siffertabellen ur R05 in som **data med källa**: varje kanal bär sin käll-URL i
      `SOURCES`, kanalerna delar inte varandras koefficienter (bara KDP har en publicerad formel), och
      en kanal utan belagt tal säger det i stället för att låna ett. Provat: trappans gränser steg för
      steg (150/151, 300/301, 828/829), ryggbredden per papper, och att Lulu får `None`.
- [~] **5.13** Normsidan: **modulen är byggd och grindad** (`core/normsida.py`, 12 egna kontroller).
      30 rader × max 60 tecken ur A4, med marginalerna **räknade** ur teckenbredden (12 pt Courier =
      2,54 mm/tecken → 60 tecken kräver 152,4 mm, alltså 28,8 mm marginal) och radhöjden ur
      radavståndet, plus `fits()` som förklarar på svenska varför det inte ryms (A5 och Letter klarar
      inte 30 rader — beskedet säger det i stället för att tiga). Avstavning av, som normalsidan
      kräver. Papyrus har funktionen och beskriver den som "von Verlagen erwünscht" (ordagrant
      belagt hos leverantören). **Kvar:** ingen knapp och ingen meny — ingen väg från gränssnittet
      till profilen ännu. R08
- [x] **5.14** Typografiska textelement i alla kanaler: **scenbrytning** (`ROLE_BREAK`), **versblock**
      (`ROLE_VERSE`) och **meddelandeblock** (`ROLE_MESSAGE`) är roller som citat och kod, med var sin
      knapp i verktygsraden. Rollen bär betydelsen, formen bär utseendet — och kursiven kommer från
      formen, inte från texten: teckenformen (editorn och trycket), Word-stilen `Verse`, EPUB:ens
      `p.verse`. Markdown-exporten hoppar därför över stjärnorna för versen, annars blev dikten
      kursivmarkerad text i stället för ett block. *Vers och meddelande behåller sina radbrytningar i
      alla kanaler*: Qts mjuka radbrytning blir `<br/>` i EPUB:en, `add_break()` i Word och två
      avslutande blanksteg i markdown — förut försvann dikten till en enda rad. Scenbrytningen blir ett
      eget centrerat stycke (`p.scene-break`), meddelandet en smalare spalt i fast bredd. Ingen
      avstavning rör vers eller meddelande: där ÄR radbrytningarna innehållet. Mätt i `ui_smoke`
      avsnitt 46 (Word-stilar, `<br/>`, CSS-regler, markdown) och på en riktig provsida genom PDF.
      R08 → **klart**.

      *Bonus, samma veva:* knapparnas verktygstips lovade Ctrl+Alt+0–8 utan att genvägarna fanns —
      nu finns de (nivå 0–8, där 4–8 är rollerna). Ett tips skall inte lova något som inte händer.
- [x] **5.15** Kompilera ett **urval**, med **sparade profiler per bok** → `core/compile.py` +
      `ui/compile_dialog.py`, i menyn under **Fil ▸ Kompilera…**

      *Urvalet:* allt som är öppet (draft, del eller kapitel — läsvyn visar dem redan samlade) eller
      **markeringen** i editorn. Markeringen utökas till hela block: en halv mening är inget urval,
      och stycket runt den är det författaren menar. *Delningen:* en fil, eller **en fil per kapitel**
      vid rubriknivå 1 — det som står *före* första rubriken blir ett eget kapitel, annars tappas en
      dedikation bort. *Namnen:* en mall med `{n}`, `{title}` och `{project}`, med ett **riktigt**
      filnamn i förhandsvisningen i stället för en beskrivning av mallen; tecken som `:` och `?` som
      ett filnamn inte får innehålla tas bort, och två kapitel med samma rubrik blir `…-2` i stället
      för att den ena skriver över den andra. *Profilerna:* namngivna val per bok i `project.json` —
      vad 5.1 hade kvar som "ett sparat publiceringsprojekt". Alla fyra kanalerna (EPUB, DOCX, PDF,
      Markdown) går genom de exportvägar som redan fanns — kompileringen bestämmer bara *vad* som ska
      ut och *vart*.

      Mätt: `core.compile` (20 kontroller), `ui.compile_dialog` (17) och `ui_smoke` avsnitt 52, som
      går hela vägen från menyvalet till filen på disk och profilen i projektfilen. R08 → **klart**.

      *Två fel som mätningen fångade på vägen, båda fixade:* (1) en position i dokumentets *slut* är
      utanför dokumentet (`characterCount()`, inte ett giltigt markörläge) — sista kapitlet tappade
      sin sista mening tyst; (2) **PyQt6 kraschar med segmenteringsfel** när en signal kopplas till en
      metod med å/ä/ö i namnet (`sip` klarar inte namnet). Därför bytte fem identifierare namn och
      `tools/identifier_check.py` vaktar regeln — koden skrivs på engelska, vilket råkar vara exakt
      vad PyQt kräver.
- [x] **5.16** Tryckförberedelsen → `core/prepress.py` + knappar i **Fil ▸ Publicera…**

      *Ensamma rader:* `widows_and_orphans()` mäter stycken vars första eller sista rad hamnar
      ensam över ett sidbrott, mot **samma sidmodell som förhandsvisningen ritar med** (radens y i
      dokumentet delat med textytans höjd, marginalerna omräknade från millimeter till punkter) —
      siffran i rutan och sidan på skärmen säger alltså samma sak. Knappen *Håll ihop ensamma rader*
      sätter Qts `setNonBreakableLines` på exakt de styckena, i **ett** ångringssteg; texten rörs
      inte, och priset (ett stycke som flyttas helt kan lämna tomrum) står i docstringen.

      *PDF/X-1a:2003:* Qt skriver en PDF men ingen tryckfärdig — ingen OutputIntent, ingen
      CMYK-konvertering. `to_pdfx()` gör om den med Ghostscript (`-dPDFX`, DeviceCMYK, inbäddade
      teckensnitt, ICC-profil ur Ghostscripts eget paket) och **verifierar resultatet i filen**:
      PDF/X-versionen läses ur filen själv och alla teckensnitt kontrolleras med `pdffonts`. Saknas
      Ghostscript sägs det rakt ut och knappen är avstängd; en halvfärdig fil blir aldrig liggande
      som om den vore klar. *Mätt:* vanlig PDF (13 578 byte) → PDF/X (8 249 byte) med
      `GTS_PDFXVersion` i filen och teckensnitten inbäddade.

      *Large print:* `print_style.scale_for_large_print()` skalar teckengrad och radavstånd i
      tryckklonen (1,5 ×, Atticus-nivå), valt med en kryssruta i publiceringsrutan och buret av
      `page_settings["large_print"]`. **Två fällor, båda mätta i utdata och inte i avsikten:**
      (1) graden sitter i *teckensnittet*, inte i `fontPointSize()` — den senare är 0 för text som
      ärver sin grad, och att bara sätta den gjorde ingenting (10 sidor före, 10 efter); (2)
      utskriftsvägen gör sin **egen** klon och gick därför förbi `_export_clone`. Den första
      versionen skalade dessutom två gånger — blockets teckenformat skalades först, och fragmentet
      läste då blockets *nya* grad och skalade en gång till: 1,5 blev 2,0 i den färdiga PDF:en
      (72 tecken per rad blev 36). Nu sker det i två faser, storlekarna läses innan något skrivs, och
      `ui_smoke` prövar **förhållandet** i texten (72 → 48 tecken per rad, 3 → 6 sidor) — att bara
      kräva "fler sidor" gick igenom även med dubbelskalningen. R08 → **klart**.
- **Status:** pending

- [x] **5.17** Installation på andra distributioner än den här maskinen. `install.sh` **installerar
      det som saknas i stället för att bara tala om det**: pythonpaketen i `.venv` (och skapar
      miljön själv med pip när `uv` inte finns — pip läggs in med `ensurepip` när venven kommer från
      en uv-installation), och systembiblioteken via maskinens egen pakethanterare (pacman/apt/dnf/
      zypper, med sudo). Ordningen är rättad: Qt:s behov mäts med `ldd` på `libqxcb.so`, och den
      filen kommer med PyQt6 — mätte man före beroendena tittade kontrollen på en fil som inte fanns
      och sa att allt var bra, vilket är varför en ren maskin aldrig upptäckte de saknade
      X11-biblioteken. PortAudio kontrolleras på samma sätt (det saknades på den här maskinen).
      Applikationen **provstartas huvudlöst i åtta sekunder** så att en installation som inte kan
      starta programmet inte rapporteras som lyckad, och frivilliga paket (Ghostscript, Java) listas
      i stället för att installeras. `--check` och `--uninstall` finns, och `update.sh` hämtar nyare
      version från GitHub och kör om installationen — men **vägrar** över ocommittade ändringar i
      spårade filer eller lokala commits som GitHub inte har. Tre fel som var verkliga, inte
      befarade: systemets `python3` saknade PyQt6 när `uv` inte fanns, `sounddevice` kastar `OSError`
      (inte `ImportError`) när PortAudio saknas och dödade appen vid start, och hjulet innehöll inte
      `locales/`, `resources/`, `main.py` eller `icon.png` — `packages = [...]` i hatchling betyder
      "bara de mapparna", så en pip-installerad kopia skulle visa i18n-nycklar i stället för text.
      Provat i färsk venv (översättningarna läses ur paketet), i fejkad hemkatalog med
      `desktop-file-validate`, och uppdateringsvägen i en klon. **Kvar:** AUR/CachyOS-paket eller
      Flatpak, och en fryst beroendelista.

### Fas 6: AI som författarverktyg

- [x] **6.1** Story bible / Codex: entiteter, typer, alias, sammanfattning, **fria attribut**,
      relationer och scenkopplingar i SQLite (`core/storybible.py` + `ui/codex_panel.py`).
      Attributen var det som fattades: modellen och API:t har burit `fields` hela tiden, men
      panelen hade ingen väg till dem. Nu finns en namn/värde-tabell på karaktärsbladet
      ("Ögonfärg: grå"), en tom rad blir inget attribut, och en borttagen rad försvinner ur
      codexet — provat i `ui_smoke`. Relationsgraf: se 2.22. R04.1
- [x] **6.2** Kontinuitet och aktiverat berättelseminne: de scenkopplade posterna finns —
      codexpanelen visar vilka entiteter scenen är kopplad till, vilka som nämns i texten
      (även via alias) och räknar omnämnandena. Att visa *vilken* kontext som skickas är 6.16,
      och den är byggd (se nedan). R04.13
- [x] **6.3** Manusfrågor: frågan byggs till ett urval i `core/context.py` och svaret kommer med
      **källhänvisning** — varje scen som låg bakom står som en länk i svaret, och ett klick öppnar
      den. Hämtningen är nyckelordsöverlapp mellan frågan och scenerna, inte embeddings: en författare
      frågar "var nämns nyckeln?" och då räcker orden (`# ponytail`-noten i `relevant_scenes` säger
      när det skall bytas). Mätt mot en riktig modell: frågan "Vem hade nyckeln, och hur fick Anna
      den?" gav ett svar med `[Nyckeln][Anna]` och `[Stranden][Bo]` — alla fyra etiketterna blev
      länkar till rätt scen. R04.3
- [x] **6.4** Fråga hela manuset eller bara scenen du har öppen, med **historik** och klickbara
      citat (`ui/ask_panel.py`, fliken *Fråga manuset*, Ctrl+Shift+Q). Anropet går genom samma
      `AIWorker` som resten av appen, och urvalet står i panelen innan det skickas. R04.4
- [ ] **6.5** Recap per scen och kapitel, redigerbar, aldrig automatisk kanon. R04.5
- [ ] **6.6** Kapitelplan, disposition och synopsis genererad som strukturerad data. R04.6
- [ ] **6.7** Brainstorm: konflikt, twist, karaktärsbåge, med "får inte ändras". R04.7
- [ ] **6.8** Skrivhjälp på markerad text (beskriv, skriv om, utöka, korta) — utöka befintlig Ctrl+K. R04.8
- [ ] **6.9** Prosakritik och redaktörspass med ankare, motivering och förslag. R04.9
- [ ] **6.10** Röstbevarande och stilprofil, ärligt formulerad som stöd. R04.10
- [ ] **6.11** Promptbibliotek och återanvändbara instruktioner. R04.11
- [ ] **6.12** Modellval och kostnad per uppgift. R04.12
- [ ] **6.13** Flerboks-seriebibel och återanvändning. R04.16 — *låg till medel*
- [ ] **6.14** Genre, åldersgräns, röst och innehållsgränser som projektprofil. R04.17
- [ ] **6.15** Diktering in i rätt scen/anteckning (befintlig Whisper kopplas till projektmodellen). R04.19
- [x] **6.16** Kontextvisaren (**Vad skickas?** i frågepanelen): varje del med sitt **slag**, sin
      **etikett**, **skälet** till att den är med ("nämns i scenen", "frågan pekar hit (styrka 1,2)",
      "scenen du har öppen") och sin **tokenräkning**, plus summan för hela anropet. Färgen per slag
      förstärker bara — raden säger sitt slag i klartext. Budgeten (`ai_context_budget`, 8000 tecken)
      stryker i prioritetsordning och **säger vad som ströks**; ett objekt som är för stort kortas med
      en anteckning i stället för att försvinna tyst. Designkravet "Visa vilka textdelar som faktiskt
      skickas" är därmed uppfyllt. R09
- [~] **6.17** Per codexpost: **alltid / vid omnämning / aldrig**, valt i kontextvisaren och sparat på
      boken (`project.json` → `context_policy`) — mätt hela vägen till filen, och posten stryks ur
      nästa urval. **Kvar:** bocka i scener, kapitel, akter och snippets för hand; nu styr omfånget
      (scenen / hela manuset) och hämtningen vilka scener som följer med. R09
- [ ] **6.18** Story Bible-genereringen som flöde: braindump → genre → stil → synopsis →
      karaktärer → värld → outline → scener, där varje steg skriver i codexet och går att ändra
      efteråt (Sudowrite). 6.1 och 6.6 täcker delarna, inte ordningen. R09
- **Status:** pending

## Bordet — kategorins minimikrav (acceptanskriterier)

Varje rapport listar vad som krävs för att verktyget skall kallas professionellt. Detta är
kontrollistan när faserna är klara.

- [ ] Manusobjekt ordnas hierarkiskt, flyttbara utan klipp-och-klistra. R01
- [ ] Varje scen är ett självständigt redigerbart dokument med metadata. R01
- [ ] Växla mellan detalj och helhet: träd, kort, sammanhängande läsvy. R01
- [ ] Mål och arbetsläge följer dokumenten (ordmål, status, etiketter). R01
- [ ] Research och versioner överlever manusredigering, separerade från texten. R01
- [ ] Redaktionell kontroll: ändringar och acceptera/avvisa enskilt, kommentarer med tråd. R02
- [ ] Struktur för långa dokument: rubrikstilar, navigator, uppdaterbar TOC, noter, korsreferenser. R02
- [ ] Pålitlig redigering över tid: versionshistorik och dokumentjämförelse. R02
- [ ] Manusberedskap: automatiska bildtexter, register, konsekvent typografi, sidlayout per avsnitt. R02
- [ ] Språkverktyg: språk per stycke, stavning, egen ordlista, mönstersök. R02
- [ ] Mål per session och projekt med synlig status. R03
- [ ] Måldatum → dagskvot med valda skrivdagar. R03
- [ ] Fokus-/helskärmsläge och centrerad markör. R03
- [ ] Romanmall som inte kräver planering före skrivandet. R03
- [ ] Historik över faktiska ord per dag, inte bara totalsumma. R03
- [ ] Manus, instruktioner och referensmaterial hålls ihop för AI:n. R04
- [ ] Strukturerade berättelseposter och scener som grundmönster. R04
- [ ] Skrivhjälp täcker idéarbete, generering och revision. R04
- [ ] Användaren väljer kontext och modell. R04
- [ ] Historik och acceptans som skyddsräcken mot överskrivning. R04
- [ ] En och samma bok exporteras till EPUB, print-PDF och DOCX. R05
- [ ] EPUB har giltigt paket, metadata och navigation. R05
- [ ] Tryckexport: enkelsidiga sidor, inbäddade typsnitt, 300 DPI, trim, sidordning, marginalregler. R05
- [ ] Omslag som sammanhängande PDF med baksida, rygg och framsida. R05
- [ ] Tillgänglighetsmetadata kan anges (accessMode, accessibilityFeature, accessibilityHazard). R05
- [ ] Kanalprofiler, eftersom mått, blöd och metadataregler skiljer sig. R05

## Writer som facit — mätt mot LibreOffice 26.8 (2026-10-22)

Alex: "ta allt Writer gör rätt, som vi ännu gör fel, ta Writer som facit." Två rapporter ligger i
`docs/research/author-tools/12-writer-paragraf-och-sidflode.md` (Writers regler, källbelagda) och
`13-layoutinventering.md` (vad vi har i dag, `fil:rad`).

**Mätmetoden är en invariant-svep, inte ett omdöme:** 120 avsnitt (fyllnad → rubrik → sjuradigt
stycke) renderade i Writer och i vår PDF, och två regler prövas över alla sidor: *rubriken får
aldrig stå sist på ett ark* och *ett stycke får aldrig lämna en ensam rad över ett brott*.

| | sidor | rubrik sist | ensam rad |
|---|---|---|---|
| Writer, rubrikstil (dess regel) | 30 | **0** | 0 |
| Writer, samma text i brödstil (kontroll) | 26 | **6** | 0 |
| Scribentia före | 26 | **5** | 0 (men 1 rad vid 228 px, separat svep) |
| Scribentia efter | 27 | **0** | 0 |

- [x] **Brytreglerna är Writers, inte våra.** `core/pagination.py`: `keep_with_next` för rubriker
      (Writers rubrikstilar har `fo:keep-with-next="always"`) och widow/orphan 2/2 (Writers
      standardstil: `ParaOrphans`/`ParaWidows` = 2, mätt över UNO; 120 stycken gav aldrig en
      ensam rad, minst 2 rader per fragment). Reglerna prövas som invarianter i modulens egenkontroll
      över 57 ark-höjder — innan de fanns: 5 rubriker sist av 120 avsnitt, och en ensam rad vid
      228 px textyta.
- [x] **Ett flöde, inte två.** Utskriften satte en sidhöjd och lät Qt paginera själv, medan skärmen
      använde `page_offsets` — alltså bröt PDF:en på andra rader än arket (och `KEEP_TOGETHER` nådde
      aldrig papperet). Nu läggs klonen i löpande höjd och samma paginering skär båda. Mätt: Writer 30
      sidor / vi 27 för samma innehåll (typsnitt och radavstånd skiljer, reglerna gör det inte).
- [x] **Ingen dubblett på arken.** `layout.draw` klipper på blocknivå, så ett stycke som börjar
      innanför kanten ritades i sin helhet även över nästa ark. En vit remsa under arkets sista rad
      tar bort det synliga överskottet; **kvar:** de överskjutande raderna finns som *osynlig text*
      i PDF:en (mätt: 3 av 123 rubriker), och en riktig lösning kräver att varje ark ritas ur en
      klippt kopia av styckena, inte ur hela dokumentet.

**Kvar mot Writer** (numrerade, ur inventeringen — ingen av dem är byggd):

- [ ] **W1 Speglade marginaler.** Udda/jämn sida får samma marginal i dag
      (`core/publishing.py:163`); Writer växlar inner/ytter per sida. Kräver paginerad målare —
      sidindex finns nu i utskriftsvägen, så hindret är borta.
- [ ] **W2 Noter i sidfoten.** Vi har slutnoter (`core/fields.py:135`); Writer sätter fotnoten längst
      ned på samma sida och krymper textytan.
- [ ] **W3 Upprepade tabellhuvuden** över sidbrott (`setHeaderRowCount` = 0) och tabeller som delas.
- [ ] **W4 Tab stops med ledarpunkter** (innehållsförteckningens punktrader) — saknas helt.
- [ ] **W5 TOC med sidnummer** — vi skriver kapitelnummer som text (`ui/main_window.py:2724`).
- [ ] **W6 Namngivna stilar** — vi har roller; Writer har ärvbara stycke-/teckenstilar.
- [ ] **W7 Språk per textparti** (stavning och avstavning följer stycket, inte manuset).
- [ ] **W8 Utskriftsskalning** ("fit to printable page", procent) — vi har bara large print 1,5×.
- [ ] **W9 Avstavning på skärmen** och rätt språk i `page_settings` (`cfg.get("language")` faller
      alltid tillbaka på svenska, `core/doc_manager.py:336`).
- [x] **W11 Leverantören går att byta** (Alex 22/10: "så vi inte låser oss någonstans").
      `core/providers.py` äger listan (12 leverantörer + egen slutpunkt), modellistan hämtas ur
      leverantörens egen `/models` i stället för att appen gissar namn, och anslutningsprovet underkänner
      ett svar som *är* ett felmeddelande — förut blev "Claude Sonnet 4.6 is no longer available." en grön
      bock. Sparat val (`ai_provider`) skrivs ner; en config från före nyckeln visas ändå rätt, eftersom
      leverantören härleds ur adressen. Mätt: 14 kontroller i modulen, 9 i rökprovet (846 totalt).
- [ ] **W10 Sidnumrering:** startvärde/omstart per avsnitt, och alternerande läge på skärmen
      (`ui/paged_paper.py:433` lägger allt till höger).

## Att åtgärda senare (rapporterat av Alex, ej gjort)

- [ ] **H2 → H1 tappar texten — kunde inte återskapas.** Rapporterat av Alex 2026-10-08: "Om något är
      h2 och jag väljer h1, så försvinner texten. Kommer tillbaka efter ctrl+z." Hans facit säger
      alltså att det är en **ångringsbar** ändring, inte en ritningsmiss. **Mätt:** dokumentet,
      HTML-rundturen, filen efter Ctrl+S, omläsningen och hela matrisen av stilknappar — 12
      kombinationer, dels markering inne i stycket, dels markering som slutar exakt på ett blockgräns —
      behåller varje tecken, och rubriknivån går 2 → 1 som den skall. Rubrikbytet h2→1, h2→0, h3→1 och
      h1→2 har därför egna kontroller i rökprovets sektion 57 (778 gröna), så en riktig regression syns
      i grinden. **Obevisat:** vilken *vy* han såg det i (editorn, pappersarket eller läsvyn — bara
      editorn är en levande canvas, de andra arken ritas statiskt), och om ordantalet i statusfältet
      sjunker när det händer. Det skiljer en radering från att texten slutar ritas, och det är nästa
      mätning — den kräver hans svar.

- [x] **Ctrl+A såg ut att bara markera sista sidan.** Rapporterat av Alex 2026-10-08, mätt och fixat
      samma dag. Han öppnade `sprint-4-vad-jag-gjorde-2026-10-08.md` (15 ark), satte markören i
      slutet och tryckte Ctrl+A: allt bleknade utom sista arket. **Mätt i hans fil:** markeringen
      *var* komplett — 12 005 av 12 006 tecken — men bara det ark editorn satt i ritade den: 1,7 %
      av ytan ändrades, exakt ett ark. Orsaken är att `PagedPaper` lägger **en** editor över det
      aktiva arket och ritar de övriga arken statiskt ur dokumentets layout; den statiska målningen
      skickade ingen markering till Qt (`PaintContext.selections` var tom), så markeringen fanns
      utan att synas. Fixen ger `PaintContext` samma markering som editorn har, med editorns egna
      färger, så arken ser likadana ut. **Mätt efteråt:** 14,0 % av ytan ändras och ett ark som inte
      är aktivt ändras med 36 046 pixlar (0 utan fixen). Rökprovet mäter det i pixlar per ark.

- [ ] **Rökprovets sidlayout kräver att dokumentet får en bredd.** I huvudlöst läge (offscreen) får
      editorns dokument ibland aldrig sin `textWidth` — Qt sätter den vid en storleksändring, och
      utan skärm kommer ingen. Då blir dokumentets höjd 0, allt räknas som **ett** ark och proven som
      rör sidor mäter ingenting (mätt: `textWidth` 0,0 mot 646,0 i samma körning med färsk respektive
      befintlig inställningsfil). Rökprovets nya Ctrl+A-prov sätter därför bredden själv, med samma
      tal som Qt skulle gett. Kvar att utreda: om appen kan hamna i samma läge på en riktig skärm —
      då vore fixen att `refresh()` alltid sätter dokumentets bredd ur arkets innermått.

- [ ] **Analysens notiser är svenska i båda gränssnitten.** `core/analysis.py` och
      `core/style_rules.py` bygger notistexten ("4 gånger tätt, 5 i boken, tätast 1 ord isär") som
      färdig svensk text, och panelen visar den rakt av. Med engelskt gränssnitt blir listan
      halvsvensk. Texten skall bli i18n-nycklar med tal som parametrar, precis som resten av
      gränssnittet — men det rör `Finding`-modellen och panelens kolumn, så det görs som en egen
      vända och inte inuti en funktionsvända.

- [ ] **Flikraden och etiketterna i sidopanelen klipps vid ~390 px bredd.** Sett i skärmdumpar
      2026-10-07 (samma familj som flikklippningen): de fyra flikarna i panelen ("Anteckningar",
      "Scen", "Skrivlogg", "Story bib") ryms inte, och etiketten för antalet öppna kommentarer
      klipps till "1 kva…". Panelens bredd är satt för fyra flikar och etiketten ligger i en
      formkolumn som är för smal. En egen layoutvända: kortare fliknamn eller ikoner med tooltip,
      och etiketten på egen rad. Inget av detta hindrar arbetet — det ser bara trångt ut.

- [ ] **Teckensnittsväljaren visar menyrubriken i stället för typsnittet.** Sett i skärmdump
      2026-10-07: rutan visar "—— ⭐ Popular Writing Fonts ——" tills man väljer ett typsnitt.
      `populate_fonts` lägger rubrikerna först i listan, och ingen väljer den aktuella skriften
      vid start — index står kvar på rubriken. Fixen är att ställa in den aktuella familjen
      efter `populate_fonts` (eller att göra rubrikerna ovalbara).


- [ ] **Rökprovet kraschar ibland i städningen (signal 11) efter grön resultatrad.** Sett 2 gånger
      2026-10-07 (gate35 och gate39), aldrig tidigare i någon gate-logg. Alla 376 kontroller är
      gröna och krashen kommer *efter* sammanfattningen. Det troliga var stilen som lades på
      widgeten (`use_dropdown`) — den ägs nu av applikationen (`install_dropdown_style()`) i stället
      för av en widget, och 10 körningar i rad är gröna. Om det kommer tillbaka: kör rökprovet i en
      slinga och läs sista raden, och misstänk Qt-objekt som dör före sina användare.


- [x] **Teckensnittsväljarens meny sprängde hela fönstret.** Fixat 2026-10-07. Orsaken var
      stilmallens fyra regler för `QComboBox QAbstractItemView` (i `ui/theme_manager.py`): de får
      Qt att svara ja på `SH_ComboBox_Popup`, och då fyller menyn hela den lediga höjden med
      skrollpilar och listan läggs mitt i — mätt 800 px meny med listen 390 px på y=133, alltså
      de två tomma fälten i skärmdumpen. Reglerna stängde dessutom av menyvyns egen skrollist, så
      bara de första elva av 37 typsnitt gick att nå. Reglerna är borta (färgerna kommer från
      appens palett, som redan sätts ur temat, och radhöjden från `FontItemDelegate.sizeHint`),
      och `core.font_manager.use_dropdown` svarar nej på menyläget för teckensnitts- och
      storleksmenyn. Mätt efteråt: 366 px meny för 14 rader à 26 px, listen från y=0, skrollist
      med 23 rader kvar — och läsbar även i temat dark (#1e222b bakgrund, #f8fafc text). Tre
      kontroller i rökprovet vaktar mekanismen (bit-testade: utan fixen blir de röda).
- [ ] **Inspektörens första flik klipps.** Sett i skärmdumpar 2026-10-07: flikraden visar "…ingar"
      längst till vänster — det är `sidebar_tab_notes` ("Anteckningar", `ui/main_window.py:150`) som
      skjutits ut när den aktiva fliken är den sista. Raden har `setUsesScrollButtons(True)` och
      pilarna är 10 px men osynliga: stilmallen tar bort plattformens pilar, så det finns ingen synlig
      väg tillbaka till första fliken. Fixen: stila `QTabBar::scroller` och dess
      `QToolButton::left-arrow/right-arrow` (samma fallgrop som tidigare, se Designkrav), eller visa
      flikarna i två rader när de inte får plats.
- [ ] **Verktygsradens emoji blir svarta fyrkanter.** Sett i skärmdumpar 2026-10-07: rutor i stället
      för ikon där emoji används — `ui/toolbar.py`: `🌐` (`act_gfonts`), `🎨 Color`, `🖍️ Highlight`,
      `🧹 Tx`, `📊` (`btn_table`). Vanliga glyfer (`𝐁`, `𝐼`, `≡`, `⇤`) ritas korrekt, så det är
      emojin och typsnittet, inte knapparna. `ui/icons.py` med Lucide-SVG:er finns redan och används
      i toppbaren och vänsterrail sedan `6e44ecb` — byt emojin mot dem (eller mot ren text).

## Designkrav (fallgropar som styr bygget)

- [ ] Visa källpassager; låt aldrig AI-genererade fakta bli kanon automatiskt. R04
- [ ] Stilprofilen är stöd och jämförelseunderlag — inte ett löfte om "skriver som du". R04
- [ ] Inga AI-ändringar som ersätter text direkt: linjemarkering, diff, undo, versionshistorik. R04
- [ ] Stilprofilen byggs av användarens egna texter, aldrig av en levande författares verk. R04
- [ ] Visa vilka textdelar som faktiskt skickas med varje AI-anrop. R04
- [ ] "Giltig EPUB" betyder inte "tillgänglig EPUB" — två separata kontroller. R05

## Avfört

- **Inworld/Storyteller som författarprodukt** (R04.19): rapporten kunde inte belägga att det
  är ett manusverktyg — det är tal- och modell-API:er. Det användbara i punkten (röst → text i
  rätt sammanhang) ligger i 6.15.

## Förkastat efter det andra researchpasset (2026-10-08)

Dessa finns hos de betalda verktygen och skall **inte** byggas. Skälet står i varje rad, så
frågan inte behöver ställas igen:

| Funktion | Vem har den | Skäl |
|---|---|---|
| Molnsynk, realtidssamarbete, iOS-app | Dabble, Ulysses, Campfire | Kräver backend och drift. Boken är en lokal mapp — det är hela poängen |
| Kartredigerare med lager och markörer | World Anvil, Campfire | Dyrt och nischat; ett tillägg den dag någon frågar |
| Marknadsplats, community, kursakademi, läsarprenumeration | World Anvil, AutoCrit | Distribution och community, inte författarens verktyg |
| Kreditvaluta och egen grundmodell | Sudowrite, NovelAI, Squibler | Dubblar leverantörens infrastruktur; vi använder användarens egen nyckel |
| Plagiatdatabas och AI-textdetektion | ProWritingAid, Grammarly | Kräver extern databas, och detektorns utfall är inte ett bevis |
| Genrepoäng och marketability-betyg | ProWritingAid, AutoCrit | Går inte att belägga lokalt; AutoCrit säger själv att 100 % inte är målet |
| Direktpublicering till WordPress/Ghost/Medium | Ulysses | Nätverksskrivning med användarens credentials i ett program som lovar offline |
| AI-bildgenerering, screenplay-konvertering, butiksuppladdning | NovelAI, LivingWriter, Scrivener | Integrationskostnad utanför kärnan. Omslagsarket är geometri och stannar |
| Teamfunktioner, varumärkeston, analytics | Grammarly | En användare, en bok |

## Key Questions

1. Hur mycket av `ui/main_window.py` (1216 rader) skall projektmodellen ta över? Besvaras i fas 0.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Projektmodellen först, allt annat efter | Mål, status, snapshots, story bible och kompilering hänger alla på att scenen är ett eget objekt (R01) |
| Nya moduler framför ändringar i `main_window.py` / `doc_manager.py` | Två flankerade filer; fem agenter som redigerar samma fil ger en oläsbar harvest |
| En worktree per agent, diffen hämtas in för hand | Mätt: agenters egen självrapport är inte verifiering, och worktreen är isolerad från live-kassan |
| `core/project.py` utan Qt | Självprovet skall kunna köras utan skärm, och modellen skall kunna läsas av kommandoradsverktyg senare |
| Nya moduler får engelska kommentarer | Alex regel 23/9 är kod på engelska; äldre moduler lämnas i fred (ingen storskalig omskrivning) |
| Licensen är GPL-3.0-only | PyQt6 distribueras under GPL v3 endast (mätt ur paketmetadatan i `.venv`), så ett program som länkar den kan inte vara MIT — vilket README påstod. Copyleft var dessutom önskat: en bearbetning måste förbli öppen och bära upphovsrätten |
| Fyra nya rapporter per PRODUKT, inte per tema | Det första passet var tematiskt och missade de betalda specialistverktygen (ProWritingAid, AutoCrit, Fictionary, Plottr, Campfire, bibisco, Papyrus). Funktionslista per produkt gav 29 mätta luckor som de fem första rapporterna inte hade, varav 17 blev nya planposter (`luckor.md`) |
| Ritad tidslinje fortfarande inte byggd, men händelsetabellen är en post (2.23) | Tre betalda verktyg har tidslinjen och Fictionary rankar scenkopplade händelser högt. Datadelen är billig och vyn är ett eget steg — beslutet väntar på Alex |
| Inget externt typsättningsprogram (Pandoc, Typst, Calibre) som backend | R10 föreslår det och kallar det billigt. Kedjan finns redan och grinden läser tillbaka EPUB/DOCX/PDF; ett externt program är dessutom ett nytt krav på användarens maskin. Kvar som *val* för PDF/X-1a (5.16) om det visar sig kräva en riktig typsättningsmotor |
| Analysen mäter **närhet**, inte totalsumma | Mätt två gånger. På syntetisk text: ren förekomst-räkning gav 10 336 fynd på 120 000 ord; ett avståndskrav gav 723. På **tre riktiga svenska romaner** höll inte engångskravet: 552–892 fynd, med "bara (189 gånger)" i toppen — vanligt språk som råkar ha ett närbeläget par. Ett fynd kräver nu **två täta** förekomster inom 20 ord → 82–154 per bok, namn och tics i toppen. En fras som börjar eller slutar i ett funktionsord räknas inte ("att gå", "såg han" står tätt i varenda bok: 316 fraser blev 31). En lista en författare kan arbeta igenom slår en fullständig lista |
| Stilvarningarna är ordlistor, inte taggning | Passiv form och ordklasser kräver en taggare; LanguageTool (4.10) äger grammatiken. Vi listar de fyra klasser som går att lista (fyllnadsord, klichéer, färgade dialogtaggar, adverb på -ligen/-ly) och säger det i modulen. Adverben är medvetet bara de entydiga ändelserna: svenska -t-adverb går inte att skilja från adjektiv utan taggning, och falska träffar i författarens text kostar mer än uteblivna |

| Elva språk ur samma motor, översatta av en pipeline | i18n-motorn var redan generisk (`locales/<kod>.json` upptäcks automatiskt), men nio saker utanför språkfilerna antog sv/en: analysens notiser, prompt-språket, avstavningskoden, decimaltecknet, stavningsspråket, mallarna. Allt sådant bor nu i en tabell (`core/languages.py`) och översättningen körs av `tools/translate_locales.py` mot appens egen leverantör — 11 språk × 1090 nycklar, kontrollerade per sats (nycklar, platshållare, flertalsformer). Finska och isländska saknar stavningskontroll (LanguageTool) och finskan avstavning (pyphen): det står i README i stället för att tigas ihjäl |
| Flertal i i18n-motorn, två former | 64 av nycklarna räknar något och substantivet böjs ("1 bok" mot "2 böcker"). Motorn tar nu `singular|plural` och väljer form efter antalet i anropet, så inga anropsställen behövde skrivas om. Källan bar samma lathet som engelskan ("{n} notes", "{n} anteckningar" — alltså "1 notes"): 53 nycklar i sv.json och en.json fick båda formerna, och de nio andra språken gjordes om för just de nycklarna. Polska och ryska behöver tre former — byggs ut när de språken kommer, inte förr |
| Nyckelordning i språkfilerna, inte sorterad | Första skrivningen sorterade om hela `sv.json` (2 171 rader brus i diffen). Filerna behåller sin ordning, som är grupperad per funktion, och nya nycklar läggs sist — samma stil som tidigare tillägg |

## Errors Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| `numpy._core._multiarray_umath` saknas | 1 | Hermes-skalet läcker `PYTHONPATH` mot sin egen python 3.14, som skuggade projektets 3.12-paket. `unset PYTHONPATH` (och i grinden) löste det. Ominstallation av numpy gjorde ingen skillnad. |
| `python -m core.project` dör i `validate()` | 1 | Cirkelkontrollen anropade `by_id()` på en okänd förälder och kastade i stället för att rapportera. Vandringen bryter nu på okänd förälder. |
| `move_node` dubblerar noden | 1 | `children()` räknade redan in noden med sin gamla ordning, och den sattes in en gång till. Filtreras bort före insättning. Hittades av självprovet. |
| EPUB: kapitlens `lang` hårdkodad till engelska | 1 | Hittades av mitt oberoende prov, inte av agentens. Språket följer nu metadata; en kontroll i modulens självprov hindrar återfall. |
| Typsnittsmenyn stod på sin rubrikrad, storleken på ett gammalt värde | 1 | Mätt 2026-10-08 när README-bilderna ritades: `sync_toolbar_state` körde bara på `cursor_format_changed`, och när en scen eller ett dokument laddas rör sig ingen markör. Formatraden synkas nu också när texten byts ut, faller tillbaka på dokumentets typsnitt och storlek, och en rubrikrad kan aldrig vara menyns värde. |
| QSS-trianglarna för pilar ritades inte av Qt | 1 | Mätt samma dag: combons pil blev en svart rektangel, spinboxens steg streck, dialogens pil en vinkel. Qt har ingen border-modell för `::down-arrow`. Pilarna skrivs nu som små PNG-ikoner i temats färg (`caret_image_path`) — combo, spinbox och flikradens pilar. |

| Finskan kraschade utskriften | 1 | `_HYPHEN_LANGS` föll tillbaka på `sv_SE` för varje språk den inte kände, och pyphen har ingen finsk ordlista: `pyphen.Pyphen(lang="fi_FI")` kastar `KeyError` och felet nådde PDF-vägen. Ordboken slås nu upp i språktabellen, och ett språk utan ordlista avstavas inte alls — ingen svensk eller engelsk ordlista lånas in |
| Analysens självprov föll på fyra kontroller | 1 | Provets text är svensk, men språket kom från körningens inställning (engelska i grinden): noten skrevs på engelska och "att gå" slutade filtreras eftersom engelskans stoppordlista inte har "att". Provet sätter nu svenska först — språkberoende prov skall säga vilket språk de mäter |

## Notes

- Uppdatera fasstatus när arbetet fortskrider: `pending` → `in_progress` → `complete`.
- Läs om Goal och Next Step före varje större beslut.
- Logga fel direkt så att en misslyckad väg inte upprepas.
