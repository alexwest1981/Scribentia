#!/usr/bin/env python3
"""tools/screenshots.py — draws the README images from the app itself.

Builds a demo project with invented text (never anyone's manuscript) in a temp
folder, opens it in MainWindow offscreen and saves one PNG per view and
language. Nothing is shown on screen.

    env -u PYTHONPATH .venv/bin/python tools/screenshots.py --lang sv
    env -u PYTHONPATH .venv/bin/python tools/screenshots.py --lang en

Output: docs/images/<lang>/workspace.png, corkboard.png, publish.png — the
images the README points at. Re-run after a UI change instead of editing them.
"""

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

# Rendering must stay headless: a pre-set QT_QPA_PLATFORM (this machine exports
# "wayland;xcb") would otherwise put real windows on the user's screen — measured
# 2026-10-08, the shots came out as tiled windows at 941x1030.
os.environ["QT_QPA_PLATFORM"] = "offscreen"
# The tool must never read or write the user's own config or writing log.
_DATA = tempfile.mkdtemp(prefix="scribentia-shots-")
os.environ.setdefault("SCRIBENTIA_DATA_DIR", _DATA)
os.environ.setdefault("SCRIBENTIA_CONFIG_PATH", os.path.join(_DATA, "config.json"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

WINDOW = (1600, 1000)

DEMO = {
    "sv": {
        "title": "Skuggan över skogsbrynet",
        "part": "Del I — Skogsbrynet",
        "chapters": ["1. Stugan", "2. Spåret"],
        "scenes": ["Morgonljus", "Kaffet", "Fotspåren", "Mötet vid bäcken"],
        "prose": """
<p>Regnet hade slutat någon gång före gryningen, men skogen höll kvar vattnet
i sina grenar. Varje gång vinden tog i föll en ny skur över trappan.</p>
<p>Ingrid stod kvar i dörren med koppen i handen och lät kaffet svalna. Hon hade
bott i stugan i nio år och kände igen ljuden: bäcken därnere, gärdsgården som
knakade, och under allt det andra det där tysta som inte hörde hit.</p>
<blockquote><p>Det finns en sorts tystnad som inte är frånvaron av ljud, utan av
någon som lyssnar.</p></blockquote>
<p>Hon satte ner koppen på trappsteget och gick ut. Gräset blötte strumporna
direkt. Vid staketet stod spåren kvar efter natten — djupa, jämna, och de
slutade tvärt, som om någon lyft sig och flugit.</p>
""",
        "corkboard_note": "Korttavlan visar scenerna som kort: titel, synopsis och status.",
    },
    "en": {
        "title": "The shadow at the treeline",
        "part": "Part I — The Treeline",
        "chapters": ["1. The cabin", "2. The tracks"],
        "scenes": ["Morning light", "The coffee", "The footprints", "The meeting"],
        "prose": """
<p>The rain had stopped some time before dawn, but the forest kept the water in
its branches. Every time the wind moved, a fresh shower came down the stairs.</p>
<p>Ingrid stayed in the doorway with the cup in her hand and let the coffee go
cold. She had lived in the cabin for nine years and knew the sounds: the stream
below, the fence creaking, and beneath all of it that quiet that did not belong
here.</p>
<blockquote><p>There is a kind of silence that is not the absence of sound, but of
someone listening.</p></blockquote>
<p>She set the cup down on the step and went outside. The grass soaked through her
socks at once. By the fence the tracks from the night were still there — deep,
even, and they stopped dead, as if someone had lifted off the ground.</p>
""",
        "corkboard_note": "The corkboard shows the scenes as cards: title, synopsis and status.",
    },
}


def build_demo(root: Path, spec: dict) -> None:
    """A small project with real-looking structure: parts, chapters, scenes."""
    from core.project import Project
    from core.project import CHAPTER, PART, SCENE

    project = Project.create(root, spec["title"], template="roman")
    # create() lays out the template's skeleton; name it the way a book looks.
    part = next(n for n in project.nodes if n.type == PART)
    part.title = spec["part"]
    chapters = [n for n in project.nodes if n.type == CHAPTER]
    chapter = chapters[0]
    chapter.title = spec["chapters"][0]
    second = project.add_node(CHAPTER, spec["chapters"][1], parent=part.id)
    first_scene = next(n for n in project.nodes if n.type == SCENE)
    for i, name in enumerate(spec["scenes"]):
        parent = chapter if i < 2 else second
        node = first_scene if i == 0 else project.add_node(SCENE, name, parent=parent.id)
        node.title = name
        project.write(node.id, f"<h1>{name}</h1>{spec['prose']}")
    project.save()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", default="sv", choices=sorted(DEMO))
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "docs/images"))
    args = parser.parse_args()

    spec = DEMO[args.lang]
    out_dir = Path(args.out) / args.lang
    out_dir.mkdir(parents=True, exist_ok=True)

    # Settings file exists before ConfigManager reads it, as in ui_smoke.
    with open(os.environ["SCRIBENTIA_CONFIG_PATH"], "w", encoding="utf-8") as handle:
        handle.write('{"language": "%s", "theme": "oma"}' % args.lang)

    # Aldrig fönster på Alex skrivbord: skalet ärver hans QT_QPA_PLATFORM.
    if not os.environ.get("SCRIBENTIA_SHOW_WINDOWS"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])
    from core.ai_client import AIClient
    from core.config import ConfigManager
    from core.dictation_engine import DictationEngine
    from core.font_manager import FontManager
    from core.i18n import i18n
    from core.project import Project
    from ui.main_window import MainWindow
    from ui.theme_manager import ThemeManager

    FontManager.load_custom_fonts()
    config = ConfigManager()
    theme = ThemeManager(config)
    theme.apply_theme_to_app(app)
    i18n.set_language(args.lang)

    window = MainWindow(AIClient(config), DictationEngine(config), theme, config)
    # The offscreen platform fits a top-level window to its layout hint, so a
    # plain resize() is undone on the next event. A minimum pins the size the
    # shot is taken at; at 1600 wide the A4 page fits next to both panels.
    window.setMinimumSize(*WINDOW)
    window.show()

    project_root = Path(_DATA) / "demo"
    build_demo(project_root, spec)
    window._activate_project(Project.load(project_root))

    def settle(rounds: int = 8) -> None:
        """Let the page actually paint: one processEvents() is not enough — the
        paper came out blank in a grab taken right after loading (measured
        2026-10-08), and the same grab has the text once the event loop has run
        for a moment."""
        for _ in range(rounds):
            app.processEvents()
            time.sleep(0.03)

    settle()

    def grab(name: str) -> None:
        settle(4)
        path = out_dir / name
        window.grab().save(str(path))
        print(f"{path}  ({path.stat().st_size // 1024} kB)")

    grab("workspace.png")

    # Corkboard: the second tab of the binder panel.
    window.binder.tabs.setCurrentIndex(1)
    grab("corkboard.png")
    window.binder.tabs.setCurrentIndex(0)

    # Publishing profile — built directly, never exec'd (a modal would hang here).
    from ui.publish_dialog import PublishDialog

    dialog = PublishDialog(window._page_count() or 300, window.page_settings, window)
    dialog.show()
    app.processEvents()
    path = out_dir / "publish.png"
    dialog.grab().save(str(path))
    print(f"{path}  ({path.stat().st_size // 1024} kB)")
    dialog.close()

    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
