"""core/providers.py — AI-leverantörerna på ett ställe.

Alla AI-vägar i appen (panelen, spökförfattaren, forskningen, kodanalysen,
översättningsverktyget) läser samma tre nycklar: ``ai_endpoint``, ``ai_key`` och
``ai_model``. Det som saknades var en lista över *vilka* leverantörer som finns
och vad de heter i dag: den låg inbäddad i inställningsrutan och hade blivit
inaktuell (OpenAI:s modellista från 2024, Gemini 1.5, OpenRouter med Claude 3.5),
och en modell som slutat fungera såg ut som en fungerande anslutning ända tills
användaren skrev något.

Här finns därför tre saker, och inget mer:

* ``PROVIDERS`` — leverantörerna, deras basadress och vad nyckeln heter hos dem.
* ``fetch_models()`` — modellistan **från leverantören själv**, så appen inte
  behöver gissa namn (en gissad modell är ett 404 som ser ut som ett fel i appen).
* ``is_error_reply()`` — en del leverantörer svarar 200 med en mening i stället
  för text ("Claude Sonnet 4.6 is no longer available."); det är inte ett svar.

Ny leverantör: lägg till en rad i ``PROVIDERS``. Inget annat behöver ändras.
"""

from __future__ import annotations

import json
import re

# id, namn i gränssnittet, basadress, vart nyckeln hämtas (tom = behövs ingen).
# Adresserna är OpenAI-kompatibla /v1-slutpunkter; appen pratar inget annat.
PROVIDERS = [
    {"id": "deepseek", "name": "DeepSeek",
     "base_url": "https://api.deepseek.com/v1",
     "key_url": "https://platform.deepseek.com/api_keys",
     "note": "deepseek-flash är billig och snabb; deepseek-reasoner tänker längre."},
    {"id": "openai", "name": "OpenAI",
     "base_url": "https://api.openai.com/v1",
     "key_url": "https://platform.openai.com/api-keys",
     "note": ""},
    {"id": "anthropic", "name": "Anthropic (OpenAI-kompatibelt)",
     "base_url": "https://api.anthropic.com/v1",
     "key_url": "https://console.anthropic.com/settings/keys",
     "note": "Anthopics egen slutpunkt; /models svarar inte som OpenAI utan modellistan fylls för hand."},
    {"id": "openrouter", "name": "OpenRouter",
     "base_url": "https://openrouter.ai/api/v1",
     "key_url": "https://openrouter.ai/keys",
     "note": "En nyckel till många leverantörers modeller."},
    {"id": "groq", "name": "Groq",
     "base_url": "https://api.groq.com/openai/v1",
     "key_url": "https://console.groq.com/keys",
     "note": ""},
    {"id": "gemini", "name": "Google Gemini (OpenAI-kompatibelt)",
     "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
     "key_url": "https://aistudio.google.com/apikey",
     "note": ""},
    {"id": "mistral", "name": "Mistral",
     "base_url": "https://api.mistral.ai/v1",
     "key_url": "https://console.mistral.ai/api-keys",
     "note": ""},
    {"id": "nous", "name": "Nous Research",
     "base_url": "https://inference-api.nousresearch.com/v1",
     "key_url": "https://portal.nousresearch.com/",
     "note": ""},
    {"id": "omniroute", "name": "OmniRoute (lokal proxy)",
     "base_url": "http://127.0.0.1:20128/v1",
     "key_url": "",
     "note": "Proxyn på den här maskinen; modellistan är dess egen."},
    {"id": "ollama", "name": "Ollama (lokalt, ingen nyckel)",
     "base_url": "http://localhost:11434/v1",
     "key_url": "",
     "note": ""},
    {"id": "lmstudio", "name": "LM Studio / LocalAI (lokalt)",
     "base_url": "http://localhost:1234/v1",
     "key_url": "",
     "note": ""},
    {"id": "custom", "name": "Egen slutpunkt",
     "base_url": "",
     "key_url": "",
     "note": "Valfri OpenAI-kompatibel /v1-adress."},
]

BY_ID = {p["id"]: p for p in PROVIDERS}


def provider(provider_id: str) -> dict:
    """Leverantören med det id:t, eller 'custom' om id:t är okänt."""
    return BY_ID.get((provider_id or "").strip().lower(), BY_ID["custom"])


def detect(endpoint: str) -> str:
    """Vilken leverantör en basadress hör till (annars 'custom').

    Används när inställningarna sparades innan ``ai_provider`` fanns, och när
    adressen skrivs för hand: rutan skall visa rätt leverantör utan att någon
    behöver komma ihåg vad den valde förra gången.
    """
    adress = (endpoint or "").strip().rstrip("/").lower()
    if not adress:
        return "custom"
    for p in PROVIDERS:
        bas = p["base_url"].rstrip("/").lower()
        if bas and (adress == bas or adress.startswith(bas + "/")):
            return p["id"]
    return "custom"


def chat_url(endpoint: str) -> str:
    """Basadressen som en chat-completions-adress, utan dubbel /v1."""
    bas = (endpoint or "").strip().rstrip("/")
    if not bas:
        return ""
    if bas.endswith("/chat/completions"):
        return bas
    return bas + "/chat/completions"


def models_url(endpoint: str) -> str:
    bas = (endpoint or "").strip().rstrip("/")
    return (bas + "/models") if bas else ""


def fetch_models(endpoint: str, api_key: str = "", timeout: float = 8.0) -> list:
    """Modellistan från leverantören själv, sorterad.

    Kastar ValueError med leverantörens eget svar om den inte kan läsas — en
    gissad lista vore värre än ingen lista.
    """
    import httpx

    url = models_url(endpoint)
    if not url:
        raise ValueError("ingen slutpunkt angiven")
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    with httpx.Client(timeout=timeout) as client:
        svar = client.get(url, headers=headers)
    if svar.status_code != 200:
        raise ValueError(f"HTTP {svar.status_code}: {svar.text[:120]}")
    try:
        data = json.loads(svar.text)
    except ValueError:
        raise ValueError(f"svaret var inte JSON: {svar.text[:120]!r}")
    poster = data.get("data") if isinstance(data, dict) else data
    if not isinstance(poster, list):
        raise ValueError(f"ingen modellista i svaret: {svar.text[:120]!r}")
    namn = []
    for post in poster:
        if isinstance(post, dict):
            namn.append(str(post.get("id") or post.get("name") or "").strip())
    return sorted({n for n in namn if n})


# En leverantör som svarar 200 med en mening i stället för text. Mönstret är
# medvetet smalt: det skall fånga "modellen är pensionerad"-svar, inte en modell
# som råkade skriva om sitt eget namn.
_ERROR_REPLY = re.compile(
    r"\b(is no longer available|no longer supported|has been (retired|deprecated|discontinued)"
    r"|model .{0,40}(not found|does not exist)|please switch to|invalid api key"
    r"|authentication (failed|required)|insufficient (quota|credit))\b",
    re.IGNORECASE)


def is_error_reply(text: str) -> bool:
    """Sant om svaret är leverantörens felmeddelande, inte modellens text."""
    return bool(_ERROR_REPLY.search(text or ""))


def unit_check() -> int:
    """Kontrollerna som hör hit: listan, igenkänningen och felmönstret."""
    grönt = 0

    def check(namn, fick, väntat):
        nonlocal grönt
        if fick != väntat:
            raise AssertionError(f"{namn}: fick {fick!r}, väntade {väntat!r}")
        grönt += 1

    check("alla leverantörer har id och namn",
          all(p["id"] and p["name"] for p in PROVIDERS), True)
    check("och id:na är unika", len({p["id"] for p in PROVIDERS}), len(PROVIDERS))
    check("custom finns alltid sist", PROVIDERS[-1]["id"], "custom")
    check("en känd adress känns igen",
          detect("https://api.deepseek.com/v1"), "deepseek")
    check("även med snedstreck på slutet",
          detect("http://localhost:11434/v1/"), "ollama")
    check("och en egen adress blir custom",
          detect("https://ai.example.org/v1"), "custom")
    check("tom adress blir custom", detect(""), "custom")
    check("chat-adressen får inte dubbel /v1",
          chat_url("https://api.deepseek.com/v1"), "https://api.deepseek.com/v1/chat/completions")
    check("och en färdig adress rörs inte",
          chat_url("https://x/v1/chat/completions"), "https://x/v1/chat/completions")
    check("modellistan hämtas från /models",
          models_url("https://api.openai.com/v1"), "https://api.openai.com/v1/models")
    check("ett svar som säger att modellen är pensionerad är ett fel",
          is_error_reply("Claude Sonnet 4.6 is no longer available. Please switch to Claude Sonnet 5.5."),
          True)
    check("okänd modell likaså",
          is_error_reply("The model `gpt-9` does not exist"), True)
    check("men en riktig mening är ett svar",
          is_error_reply("Källaren var mörk och trappan knarrade."), False)
    check("och en modell som nämner sig själv är ett svar",
          is_error_reply("Jag är Claude, en assistent. Model no longer available? Nej."), False)
    return grönt


if __name__ == "__main__":
    antal = unit_check()
    print(f"providers: {antal} kontroller gröna")
