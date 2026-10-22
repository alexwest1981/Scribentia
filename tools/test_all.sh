#!/usr/bin/env bash
# tools/test_all.sh — grinden. Samma kommando i en worktree som i live-kassan.
#
#   bash tools/test_all.sh
#
# Kör tre kontroller: att varje modul i core/ och ui/ går att importera, att
# appen startar och fungerar (ui_smoke), och att exporterade filer är rena
# (print_purity_check). Avslutar RÖTT om någon faller.
#
# Interpretern är den utvecklade .venv i live-kassan, eftersom en fräsch
# worktree inte har någon egen .venv (den är gitignorerad). Nya beroenden kan
# därför inte smygas in — vilket är avsiktligt. Sätt SCRIBENTIA_PY för att peka
# på en annan tolk.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
unset PYTHONPATH   # Hermes-skalet läcker sin egen python 3.14 hit annars

# Grinden kör utan skärm. Utan det här ärver proven skrivbordets plattform
# (QT_QPA_PLATFORM=wayland;xcb hos Alex) och ui_smoke öppnar riktiga fönster i
# sessionen — och kan hänga på en modal ruta som ingen sitter framför.
export QT_QPA_PLATFORM=offscreen
# Skrivloggen hamnar i en temp-mapp: grinden skriver riktiga ord och får inte
# fylla Alex egen skrivlogg med dem.
export SCRIBENTIA_DATA_DIR="$(mktemp -d)"

PY="${SCRIBENTIA_PY:-$HOME/Projects/scribentia/.venv/bin/python}"
if [ ! -x "$PY" ]; then
  echo "GRINDEN KAN INTE KÖRA: $PY saknas (sätt SCRIBENTIA_PY)"
  exit 2
fi

LOG="$(mktemp)"
fail=0

run() {
  local name="$1"; shift
  printf '\n### %s\n' "$name"
  if "$@" >"$LOG" 2>&1; then
    grep -E "RESULTAT|GRÖNT|ren|ok|OK" "$LOG" | tail -2
    tail -1 "$LOG"
  else
    echo "RÖTT: $name"
    tail -25 "$LOG"
    fail=1
  fi
}

run "valvet" "$PY" -m core.vault
run "ai-klienten" "$PY" -m core.ai_client
run "kodanalysen" "$PY" -m core.code_analyzer
run "direktiven" "$PY" -m core.directives

run "importkontroll" "$PY" - <<'PYEOF'
import glob, importlib, os, sys
sys.path.insert(0, os.getcwd())
bad = []
for path in sorted(glob.glob("core/*.py") + glob.glob("ui/*.py")):
    name = os.path.basename(path)[:-3]
    if name.startswith("__"):
        continue
    try:
        importlib.import_module(("core." if path.startswith("core") else "ui.") + name)
    except Exception as exc:  # noqa: BLE001 — grinden skall se allt
        bad.append(f"{path}: {type(exc).__name__}: {exc}")
print(f"importerade {len(glob.glob('core/*.py')) + len(glob.glob('ui/*.py'))} moduler")
if bad:
    print("\n".join(bad))
    raise SystemExit(1)
PYEOF

# Portabilitet: sounddevice paketerar inte PortAudio. Saknas biblioteket i
# systemet kastar importen OSError — inte ImportError — och den gick tidigare
# rakt igenom fångsten och dödade appen vid start på en maskin med ren
# Python-installation. Provet lägger en trasig sounddevice framför de riktiga
# paketen och kräver att importen ändå går igenom.
run "utan ljudbibliotek" "$PY" - <<'PYEOF'
import os, subprocess, sys, tempfile
root = tempfile.mkdtemp(prefix="scribentia-utan-ljud-")
with open(os.path.join(root, "sounddevice.py"), "w", encoding="utf-8") as f:
    f.write('raise OSError("PortAudio library not found")\n')
with open(os.path.join(root, "faster_whisper.py"), "w", encoding="utf-8") as f:
    f.write('raise OSError("libwhisper missing")\n')
env = dict(os.environ, PYTHONPATH=root)
proc = subprocess.run([sys.executable, "-c",
                       "import core.dictation_engine as d; "
                       "assert d.sd is None and d.WhisperModel is None; print('ok, dikteringen stängs av')"],
                      capture_output=True, text=True, env=env)
print(proc.stdout.strip() or proc.stderr.strip()[-400:])
if proc.returncode != 0:
    raise SystemExit(f"appen dog utan ljudbibliotek: {proc.stderr.strip()[-300:]}")
PYEOF

# Skal skripten är det första en ny maskin kör, och grinden såg dem inte alls.
# En syntaxmiss där är osynlig för varje annat prov i den här filen.
run "skalsyntaxen" bash -c 'for f in install.sh update.sh tools/test_all.sh; do bash -n "$f" || exit 1; done; echo "install.sh, update.sh och test_all.sh är syntaktiskt hela"'

run "projektmodellen" "$PY" -m core.project
run "epub-exporten" "$PY" -m core.epub
run "snapshots" "$PY" -m core.snapshots
run "stavningskontrollen" "$PY" -m core.spellcheck
run "revisionerna" "$PY" -m core.revisions
run "övningarna" "$PY" -m core.exercises
run "läsbarheten" "$PY" -m core.document_stats
run "analysen" "$PY" -m core.analysis
run "statistiken" "$PY" -m core.story_stats
run "normsidan" "$PY" -m core.normsida
run "leverantörerna" "$PY" -m core.providers
run "pappersformaten" "$PY" -m core.page_format
run "pagineringen" "$PY" -m core.pagination
run "skrivloggen" "$PY" -m core.writing_log
run "storybible" "$PY" -m core.storybible
run "sök och ersätt" "$PY" -m core.find_replace
run "autokorrigeringen" "$PY" -m core.autocorrect
run "fälten" "$PY" -m core.fields
run "publiceringen" "$PY" -m core.publishing
run "släppet" "$PY" -m core.release
run "omslaget" "$PY" -m core.cover
run "epubcheck" "$PY" -m core.epubcheck

# Vakten mot att i18n-funktionen `_` skuggas i en metod som använder den.
run "skuggningen av _" "$PY" tools/i18n_shadow_check.py
run "korktavlan" "$PY" -m ui.corkboard
run "läsvyn" "$PY" -m ui.scrivenings
run "samlingarna" "$PY" -m core.collections
run "samlingspanelen" "$PY" -m ui.collections_panel
run "analyspanelen" "$PY" -m ui.insight_panel
run "stilreglerna" "$PY" -m core.style_rules
run "story-elementen" "$PY" -m core.story_elements
run "elementdialogen" "$PY" -m ui.elements_dialog
run "relationsgrafen" "$PY" -m ui.codex_graph_dialog
run "händelserna" "$PY" -m core.events
run "händelsetabellen" "$PY" -m ui.events_dialog
run "kompileringen" "$PY" -m core.compile
run "tryckförberedelsen" "$PY" -m core.prepress
run "kontextlagret" "$PY" -m core.context
run "frågepanelen" "$PY" -m ui.ask_panel
run "kompilera-fönstret" "$PY" -m ui.compile_dialog
run "i18n-nycklarna" "$PY" tools/i18n_keys_check.py
run "språktabellen" "$PY" -m core.languages
run "översättningen" "$PY" tools/translate_locales.py --self-check
run "identifierarna" "$PY" tools/identifier_check.py
run "ui_smoke" "$PY" tools/ui_smoke.py
run "print_purity" "$PY" tools/print_purity_check.py

# Att applikationen *startar* prövas ingen annanstans: importkontrollen ser
# modulerna, ui_smoke bygger sin egen ruta — men själva ingången (main.py,
# plugin-laddningen, konfigvägen) är oprövad. Att den lever vidare efter åtta
# sekunder, utan traceback, är svaret; en app som dör direkt ger en annan kod.
printf '\n### startar applikationen\n'
start_log="$(mktemp)"
timeout 8 env SCRIBENTIA_CONFIG_PATH="$(mktemp)" "$PY" main.py >"$start_log" 2>&1
start_kod=$?
if [ "$start_kod" -eq 124 ] && ! grep -q "Traceback" "$start_log"; then
  echo "  ✓ applikationen startar och står kvar (stoppad efter 8 s)"
else
  echo "  ✗ applikationen startar inte (exit $start_kod)"
  tail -8 "$start_log"
  fail=1
fi
rm -f "$start_log"

rm -f "$LOG"
printf '\n==============================================\n'
if [ "$fail" -eq 0 ]; then echo "GRINDEN: GRÖNT"; else echo "GRINDEN: RÖTT"; fi
exit "$fail"
