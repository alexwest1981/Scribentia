import os
import json
import locale
import shutil
from core.i18n import i18n

# Inställningarna låg tidigare under ~/.config/omascribe. Ett namnbyte får inte
# tyst börja om från en tom konfiguration — AI-nyckeln, temat, språket och de
# senaste filerna ligger där. Finns den nya filen inte men den gamla, kopieras
# den hit en gång och den gamla ligger kvar som den var.
_STANDARD_CONFIG = os.path.expanduser("~/.config/scribentia/config.json")
_GAMMAL_CONFIG = os.path.expanduser("~/.config/omascribe/config.json")


def _config_path() -> str:
    """Sökvägen till inställningsfilen.

    Prov och rökprov styr filen med SCRIBENTIA_CONFIG_PATH i stället för att
    skriva i den riktiga: en rökprovning som ändrar användarens sidinställningar
    är inte en provning, den är ett ingrepp. Den gamla variabeln läses också, så
    att skript som någon redan har inte tystnar.
    """
    for nyckel in ("SCRIBENTIA_CONFIG_PATH", "OMASCRIBE_CONFIG_PATH"):
        if os.environ.get(nyckel):
            return os.environ[nyckel]              # prov: rör aldrig användarens fil
    if not os.path.exists(_STANDARD_CONFIG) and os.path.exists(_GAMMAL_CONFIG):
        try:
            os.makedirs(os.path.dirname(_STANDARD_CONFIG), exist_ok=True)
            shutil.copy2(_GAMMAL_CONFIG, _STANDARD_CONFIG)
            return _STANDARD_CONFIG
        except OSError:
            return _GAMMAL_CONFIG                  # går det inte att kopiera, läs den gamla
    return _STANDARD_CONFIG


CONFIG_PATH = _config_path()

def get_system_default_language():
    try:
        lang_env = (os.environ.get("LANG", "") or os.environ.get("LC_ALL", "") or "").lower()
        if lang_env.startswith("sv"):
            return "sv"
        loc = locale.getdefaultlocale()[0]
        if loc and loc.lower().startswith("sv"):
            return "sv"
    except Exception:
        pass
    return "en"

# AI-standarder på ett ställe. Tidigare hade varje modul sin egen reserv
# (api.deepseek.com/v1 i två filer, localhost:8000/v1 i ai_client,
# 127.0.0.1:20128/v1 i tre) och modellreserven var "claude-3-5-sonnet" även mot
# en DeepSeek-endpoint. En ny installation kunde alltså skicka dokumentet till
# en leverantör ingen hade valt. Tom sträng = ingen AI vald, och då görs inget
# anrop alls: chat_completion säger till i klartext i stället.
DEFAULT_AI_ENDPOINT = ""
DEFAULT_AI_MODEL = ""

DEFAULT_CONFIG = {
    "language": get_system_default_language(),
    "theme": "paper",  # "paper", "dark", "nord", "amber"
    "autosave": True,
    "autosave_interval_sec": 30,
    "default_font_family": "DejaVu Serif",
    "default_font_size": 12,
    "zoom_level": 100,
    # Panelen är infälld från början: den tar 312px och texten ska ha dem.
    # Verktygsradens "Inspector"-knapp fäller ut den igen.
    "show_ai_sidebar": False,
        "typewriter_mode": False,
    "sidebar_active_tab": 0,
    # Neutral standard för den som installerar appen. Ingen privat slutpunkt
    # bakas in — användaren anger sin egen leverantör och nyckel i
    # Inställningar. (En sparad config.json vinner alltid över detta.)
    # Vilken leverantör adressen hör till (core/providers.py). Tom = härleds ur
    # adressen, så en config från före den här nyckeln fortsätter att fungera.
    "ai_provider": "",
    "ai_endpoint": DEFAULT_AI_ENDPOINT,
    "ai_key": "",
    "ai_model": DEFAULT_AI_MODEL,
    # Hur mycket text ett AI-anrop får bära (tecken). Urvalet byggs i
    # core/context.py och stryks i prioritetsordning när budgeten tar slut.
    "ai_context_budget": 8000,
    "dictation_model": "base",
    "dictation_lang": "auto",
    "dictation_auto_punctuate": True,
    "recent_files": [],
    "has_run_before": False,
    "vault_root": os.path.expanduser("~/Documents/Scribentia Vault"),
    "research_searxng_url": ""   # egen SearXNG-instans ger nyckelfri webbsökning
}

class ConfigManager:
    def __init__(self):
        self.data = DEFAULT_CONFIG.copy()
        self.load()

    def load(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self.data.update(saved)
                    if "has_run_before" not in saved:
                        self.data["has_run_before"] = True
                    if "language" in saved:
                        i18n.set_language(saved["language"])
            except Exception as e:
                print(f"[Config] Error loading config: {e}")

    def save(self):
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"[Config] Error saving config: {e}")

    def get(self, key, fallback=None):
        return self.data.get(key, fallback)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def add_recent_file(self, filepath):
        if not filepath:
            return
        recents = self.data.get("recent_files", [])
        if filepath in recents:
            recents.remove(filepath)
        recents.insert(0, filepath)
        self.data["recent_files"] = recents[:10]
        self.save()

    def remove_recent_file(self, filepath):
        recents = self.data.get("recent_files", [])
        if filepath in recents:
            recents.remove(filepath)
            self.data["recent_files"] = recents
            self.save()

    def clear_recent_files(self):
        self.data["recent_files"] = []
        self.save()
