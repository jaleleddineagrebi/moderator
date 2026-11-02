"""Per-language settings shared by every agent: dialect instructions, voices and speaking rate.
To change a language (e.g. another Arabic dialect), edit it here only."""

LANGS = {
    "ar": {
        "name": "Egyptian Arabic",
        "audience": "Egyptian and wider Arabic-speaking audience (Egyptian dialect is understood across MENA)",
        "writing": ("Egyptian colloquial Arabic (العامية المصرية) exactly as people speak in Cairo, written in Arabic script, "
                    "no diacritics. Use Egyptian words and grammar (مش، إزاي، ليه، عشان، كده، بيـ، هـ for future, ده/دي), "
                    "not Modern Standard Arabic. Keep it warm, casual and easy to say aloud."),
        # first voice is used normally; the others are retry fallbacks
        "voices": ["ar-EG-ShakirNeural", "ar-EG-SalmaNeural"],
        # measured with ar-EG-ShakirNeural, including the pauses between scenes
        "words_per_second": 1.75,
    },
    "fr": {
        "name": "French",
        "audience": "French-speaking audience (France, Belgium, Switzerland, Québec, francophone Africa)",
        "writing": 'Natural spoken French, addressing the viewer as "tu". Short sentences, everyday words.',
        "voices": ["fr-FR-HenriNeural", "fr-FR-DeniseNeural", "fr-FR-RemyMultilingualNeural"],
        "words_per_second": 2.65,
    },
}


def describe(langs: list[str]) -> str:
    """Prompt block describing how to write each language."""
    return "\n".join(f"- {code} = {LANGS[code]['name']}: {LANGS[code]['writing']}" for code in langs)


def names(langs: list[str]) -> str:
    return " and ".join(LANGS[code]["name"] for code in langs)
