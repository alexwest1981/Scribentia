"""tools/translate_locales.py — fyller locales/<kod>.json ur engelskan.

Ett språk är en fil. Skriptet översätter nycklarna i satser om `--batch` nycklar
(60 som standard), kontrollerar varje sats och skriver filen efter varje sats.
Avbryts körningen fortsätter nästa gång på det som redan är översatt — en halv
fil är en giltig fil, och den engelska texten är alltid fallback i appen.

    python tools/translate_locales.py                 # alla språk som saknar fil
    python tools/translate_locales.py de fr es        # bara dessa
    python tools/translate_locales.py de --dry-run    # visa satsen, inget anrop
    python tools/translate_locales.py --all           # gör om allt från grunden

Leverantören är appens egen (Inställningar → AI): samma slutpunkt, nyckel och
modell som appen använder. Är slutpunkten tom skickas ingenting, och skriptet
säger det i stället för att gissa.

Kontrollen är det som gör filen användbar: samma nycklar, samma platshållare
({name}, {n}) och minst lika många flertalsformer ('|') som källan. En sats som
faller på kontrollen skrivs inte — nycklarna står kvar i engelska, och satsen
rapporteras.

Identifierarna och utskrifterna är engelska (Alex regel 23/9); prosan i
kommentarerna följer filerna bredvid, som är skrivna på svenska.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ai_client import chat_completion          # noqa: E402
from core.config import ConfigManager               # noqa: E402
from core.languages import LANGUAGES, ai_name        # noqa: E402

LOCALES = Path(__file__).resolve().parent.parent / "locales"
SOURCE = "en"
BATCH_DEFAULT = 60
TIMEOUT = 180.0

SYSTEM = (
    "You are a professional software localizer. You translate the user-interface "
    "strings of Scribentia, a book-writing application used by novelists, from "
    "English into {language}.\n"
    "\n"
    "Rules:\n"
    "1. Answer with ONE strict JSON object and nothing else — same keys as the "
    "input, no explanations, no code fences.\n"
    "2. Keep every key byte for byte as it is. Never translate a key.\n"
    "3. Keep placeholders exactly: {{name}}, {{n}}, {{count}}, {{title}}. They are "
    "filled in by the program afterwards.\n"
    "4. Keep HTML tags, emoji, keyboard shortcuts (Ctrl+K), file extensions "
    "(.docx), and unit symbols unchanged.\n"
    "5. Plurals: when a string counts something and the noun changes with the "
    "number, write both forms separated by one '|' — singular first: "
    "\"1 note|{{n}} notes\". Never add a '|' to a string that has none.\n"
    "6. This is calm, plain application language. Short sentences, no marketing, "
    "no exclamation marks, no \"we are excited\". Use {language} typographic "
    "conventions (quotation marks, spacing) — not English ones.\n"
    "7. Strings ending in ':' keep the colon. Strings starting with a capital or "
    "lower-case letter keep that case pattern, adjusted to {language} grammar.\n"
)

PLACEHOLDER = re.compile(r"\{(\w+)\}")


def placeholders(text: str) -> set[str]:
    """Namnen inuti {klamrar} i en sträng."""
    return set(PLACEHOLDER.findall(text))


def form_count(text: str) -> int:
    """Hur många flertalsformer strängen bär (1 = ingen)."""
    return text.count("|") + 1


def validate_batch(source: dict, translated: dict) -> list[str]:
    """Vad som är fel med en översatt sats. Tom lista = godkänd."""
    errors = []
    missing = [k for k in source if k not in translated]
    if missing:
        errors.append(f"{len(missing)} keys missing ({', '.join(missing[:3])})")
    unknown = [k for k in translated if k not in source]
    if unknown:
        errors.append(f"{len(unknown)} unknown keys ({', '.join(str(e) for e in unknown[:3])})")
    for key, value in translated.items():
        if key not in source:
            continue
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{key}: empty")
            continue
        if placeholders(value) != placeholders(source[key]):
            errors.append(f"{key}: placeholders {sorted(placeholders(value))} "
                          f"against {sorted(placeholders(source[key]))}")
        if form_count(value) < form_count(source[key]):
            # Fler former är tillåtna: engelskan skriver "{count} note(s)" och
            # tyskan vill ha "1 Notiz|{n} Notizen". Färre är ett fel — då tappar
            # en form sin text.
            errors.append(f"{key}: {form_count(value)} forms against {form_count(source[key])}")
    return errors


def parse_json(text: str):
    """Modellens svar som dict: staket och prat runt omkring klipps bort."""
    body = (text or "").strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[-1] if "\n" in body else body
        body = body.rsplit("```", 1)[0]
    first, last = body.find("{"), body.rfind("}")
    if first < 0 or last <= first:
        # Ett svar utan JSON är nästan alltid slutpunktens eget felmeddelande,
        # levererat som ett vanligt svar: "Claude Sonnet 4.6 is no longer
        # available." Ordagrant, för det var det som hände och det gick inte att
        # läsa sig till ur "the reply could not be read as JSON".
        raise ValueError(f"the endpoint replied without JSON: {body[:200]!r}")
    return json.loads(body[first:last + 1])


def batches(keys: list, size: int):
    for i in range(0, len(keys), size):
        yield keys[i:i + size]


def write_locale(code: str, order: list, done: dict) -> None:
    """Filen i källans nyckelordning — läsbar och diffbar."""
    out = {k: done[k] for k in order if k in done}
    (LOCALES / f"{code}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def translate_language(code: str, source: dict, cfg, args) -> tuple[str, int, list]:
    """Ett språk. Returnerar (kod, antal klara, problem)."""
    path = LOCALES / f"{code}.json"
    done: dict = {}
    if path.exists() and not args.all:
        try:
            done = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            print(f"[{code}] the file could not be read — starting over")
    todo = [k for k in source if k not in done]
    if not todo:
        return code, len(done), []
    print(f"[{code}] {len(todo)} keys left of {len(source)}", flush=True)
    system = SYSTEM.format(language=ai_name(code))
    problems: list = []
    for batch in batches(todo, args.batch):
        batch_source = {k: source[k] for k in batch}
        if args.dry_run:
            print(json.dumps(batch_source, ensure_ascii=False, indent=2)[:1200])
            return code, 0, []
        try:
            translated = None
            for _attempt in range(2):          # ett omtag: en trasig sats är oftast otur
                reply = chat_completion(cfg.get("ai_endpoint", ""), cfg.get("ai_key", ""),
                                        cfg.get("ai_model", ""), system,
                                        json.dumps(batch_source, ensure_ascii=False),
                                        timeout=TIMEOUT, temperature=0.2)
                try:
                    translated = parse_json(reply)
                    break
                except ValueError:
                    continue
            if translated is None:
                raise ValueError("the reply could not be read as JSON")
        except Exception as e:
            problems.append(f"batch at {batch[0]}: {type(e).__name__}: {str(e)[:120]}")
            print(f"[{code}] batch at {batch[0]} failed ({type(e).__name__})", flush=True)
            continue
        errors = (validate_batch(batch_source, translated) if isinstance(translated, dict)
                  else ["the reply was not a JSON object"])
        if errors:
            problems.extend(errors[:6])
            print(f"[{code}] batch at {batch[0]}: {errors[0]}", flush=True)
            continue
        done.update({k: translated[k] for k in batch})
        write_locale(code, list(source), done)
        print(f"[{code}] {len([k for k in source if k in done])}/{len(source)}", flush=True)
    return code, len([k for k in source if k in done]), problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate the locale files from English.")
    parser.add_argument("languages", nargs="*", help="language codes; empty = every one without a file")
    parser.add_argument("--all", action="store_true", help="redo everything, not only what is missing")
    parser.add_argument("--batch", type=int, default=BATCH_DEFAULT,
                        help=f"keys per request ({BATCH_DEFAULT})")
    parser.add_argument("--jobs", type=int, default=4, help="languages in parallel (4)")
    parser.add_argument("--dry-run", action="store_true", help="show the first batch, send nothing")
    args = parser.parse_args()

    source = json.loads((LOCALES / f"{SOURCE}.json").read_text(encoding="utf-8"))
    if args.languages:
        targets = args.languages
    else:
        targets = [k for k in LANGUAGES if k != SOURCE and not (LOCALES / f"{k}.json").exists()]
    if not targets:
        print("nothing to do: every language in the table has a file")
        return 0

    cfg = ConfigManager()
    if not args.dry_run and not str(cfg.get("ai_endpoint", "") or "").strip():
        print("No AI endpoint is chosen (Settings → AI). Nothing was sent.")
        return 2

    print(f"source {SOURCE}.json: {len(source)} keys -> {', '.join(targets)}")
    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        for code, complete, problems in pool.map(
                lambda k: translate_language(k, source, cfg, args), targets):
            results.append((code, complete, problems))

    print("\nreport")
    incomplete = 0
    for code, complete, problems in sorted(results):
        flag = "ok" if complete == len(source) and not problems else "INCOMPLETE"
        if flag != "ok":
            incomplete += 1
        print(f"  {code}: {complete}/{len(source)} {flag}"
              + (f" — {len(problems)} problems, first: {problems[0]}" if problems else ""))
    print(f"  {len(targets) - incomplete} of {len(targets)} languages complete")
    return 1 if incomplete else 0


def self_check() -> int:
    """Kontrollen är det enda som avgör om en sats får skrivas."""
    source = {"a": "Hello {name}, you have {n} note|{n} notes.", "b": "Plain."}
    good = {"a": "Hej {name}, du har {n} anteckning|{n} anteckningar.", "b": "Vanlig."}
    assert validate_batch(source, good) == []
    assert validate_batch(source, {"a": "Hej {name} {n} note|{n} notes."})[0].startswith("1 keys missing")
    assert any("placeholders" in f for f in validate_batch(source, {**good, "a": "Hej {name}."}))
    assert any("forms" in f for f in validate_batch(source, {**good, "a": "Hej {name} {n}."}))
    assert any("unknown" in f for f in validate_batch(source, {**good, "c": "?"}))
    assert any("empty" in f for f in validate_batch(source, {**good, "b": "  "}))
    # Fler former än källan är tillåtet: "1 Notiz|{n} Notizen" mot "{n} notes".
    assert validate_batch({"a": "{n} notes"}, {"a": "1 Notiz|{n} Notizen"}) == []
    assert placeholders("Hej {name} {n}") == {"name", "n"}
    assert form_count("en|flera") == 2 and form_count("en") == 1
    assert [len(b) for b in batches(["a", "b", "c"], 2)] == [2, 1]
    assert parse_json('```json\n{"a": "b"}\n```') == {"a": "b"}
    assert parse_json('Visst: {"a": "b"} klart.') == {"a": "b"}
    # Slutpunkten kan svara 200 med en mening i stället för JSON (mätt: "Claude
    # Sonnet 4.6 is no longer available."), och då skall felet citera meningen i
    # stället för att säga att svaret inte gick att läsa.
    try:
        parse_json("Claude Sonnet 4.6 is no longer available. Please switch to Claude Sonnet 5.5.")
        raise AssertionError("ett svar utan JSON skall kastas")
    except ValueError as e:
        assert "no longer available" in str(e)
    print("translate_locales: 13 kontroller gröna")
    return 0


if __name__ == "__main__":
    if "--self-check" in sys.argv or (len(sys.argv) == 1 and sys.stdin.isatty()):
        sys.exit(self_check())
    sys.exit(main())
