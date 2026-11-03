"""Per-language settings shared by every agent: dialect instructions, voices and speaking rate.
To change or add a language (e.g. another dialect), edit it here only."""

from __future__ import annotations

LANGS = {
    "en": {
        "name": "English",
        "audience": "Global English-speaking audience (US, UK, Canada, Australia, international viewers)",
        "writing": ("Natural spoken English, addressing the viewer directly as 'you'. "
                    "Short punchy sentences, everyday words, active voice, easy to say aloud."),
        # first voice is used normally; the others are retry fallbacks
        "voices": ["en-US-AndrewMultilingualNeural", "en-US-AriaNeural", "en-GB-RyanNeural"],
        "words_per_second": 2.75,
        "sensitive_notes": "Avoid misleading medical/financial claims, hate speech, or graphic topics.",
    },
    "fr": {
        "name": "French",
        "audience": "French-speaking audience (France, Belgium, Switzerland, Québec, francophone Africa)",
        "writing": 'Natural spoken French, addressing the viewer as "tu". Short sentences, everyday words.',
        "voices": ["fr-FR-HenriNeural", "fr-FR-DeniseNeural", "fr-FR-RemyMultilingualNeural"],
        "words_per_second": 2.65,
        "sensitive_notes": "Avoid misleading medical/financial claims or sensationalist clickbait.",
    },
    "ar": {
        "name": "Egyptian Arabic",
        "audience": "Egyptian and wider Arabic-speaking audience (Egyptian dialect is understood across MENA)",
        "writing": ("Egyptian colloquial Arabic (العامية المصرية) exactly as people speak in Cairo, written in Arabic script, "
                    "no diacritics. Use Egyptian words and grammar (مش، إزاي، ليه، عشان، كده، بيـ، هـ for future, ده/دي), "
                    "not Modern Standard Arabic. Keep it warm, casual and easy to say aloud."),
        "voices": ["ar-EG-ShakirNeural", "ar-EG-SalmaNeural"],
        # measured with ar-EG-ShakirNeural, including the pauses between scenes
        "words_per_second": 1.75,
        "sensitive_notes": "Avoid topics sensitive in MENA: religion debates, politics, alcohol, or dating.",
    },
}


def normalize_langs(raw: list[str] | str | None, default: tuple[str, ...] = ("ar", "fr")) -> list[str]:
    """Normalize CLI/YAML language params ('en', 'en,fr', ['en', 'fr']) and validate codes."""
    if raw is None:
        langs = list(default)
    elif isinstance(raw, str):
        langs = [part.strip().lower() for part in raw.split(",") if part.strip()]
    elif isinstance(raw, (list, tuple)):
        langs = [str(part).strip().lower() for part in raw if str(part).strip()]
    else:
        raise ValueError(f"Invalid languages value: {raw!r}")
    if not langs:
        raise ValueError("At least one language is required")
    unknown = [c for c in langs if c not in LANGS]
    if unknown:
        raise ValueError(f"Unsupported language(s): {', '.join(unknown)}. Supported: {', '.join(LANGS)}")
    # Preserve order while deduplicating
    return list(dict.fromkeys(langs))


def lang_schema(langs: list[str], value_schema: dict | None = None, description: str | None = None) -> dict:
    """Build a strict JSON Schema object with one required property per active language."""
    prop = value_schema or {"type": "string"}
    schema: dict = {
        "type": "object",
        "additionalProperties": False,
        "required": list(langs),
        "properties": {code: prop for code in langs},
    }
    if description:
        schema["description"] = description
    return schema


def describe(langs: list[str]) -> str:
    """Prompt block describing how to write each language."""
    return "\n".join(f"- {code} = {LANGS[code]['name']}: {LANGS[code]['writing']}" for code in langs)


def sensitivity_guidance(langs: list[str]) -> str:
    """Combine audience sensitivity rules for the active languages."""
    notes = list(dict.fromkeys(LANGS[code]["sensitive_notes"] for code in langs if LANGS[code].get("sensitive_notes")))
    return " ".join(notes)


def names(langs: list[str]) -> str:
    items = [LANGS[code]["name"] for code in langs]
    if len(items) <= 2:
        return " and ".join(items)
    return ", ".join(items[:-1]) + f" and {items[-1]}"
