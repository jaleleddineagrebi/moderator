"""Channel rules for what people may appear in images and video. Edit here only; every agent reads it.

Rule: no women or girls in the visuals. If a woman is truly needed, only her face in a tight close-up
(head only, no body). Applied at four points:
- Scriptwriter: scene descriptions and stock search terms avoid women.
- Visual Producer: drops stock results whose tags / page slug mention women, rewrites female search terms,
  and tells the image model the rule.
- Packaging: thumbnail image prompt carries the rule.
- QA Reviewer: looks at frames from every scene and the thumbnails; a violation blocks the video and
  sends the scene back to Visual Producer (or the thumbnail back to Packaging).
"""

from __future__ import annotations

import re

PEOPLE_RULE = (
    "Do not show women or girls. Prefer men, hands, objects, places, animals or nature. "
    "If a woman is truly necessary, show only her face in a tight close-up (head only, no body, nothing below the chin)."
)

IMAGE_PROMPT_RULE = (
    "STRICT RULE: no women or girls anywhere in the image (no female bodies, silhouettes, figures or hands). "
    "If people appear, show men only. The single exception: if a woman is essential to the idea, show only her face "
    "in a tight head-only close-up, nothing below the chin."
)

REVIEW_RULE = (
    "A violation is any frame showing a woman or girl beyond a tight face-only close-up: her body, shoulders, "
    "full figure, silhouette or a crowd where women are clearly visible. A face-only close-up is allowed. "
    "Men, children who are clearly boys, hands of unclear gender, objects and places are fine."
)

_FEMALE = re.compile(
    r"\b(wom[ae]n|girls?|female|ladies|lady|mothers?|moms?|mums?|wife|wives|brides?|sisters?|daughters?|"
    r"girlfriends?|businesswom[ae]n|femmes?|filles?|mujer(es)?|chica)\b|\w*wom[ae]n\b",
    re.IGNORECASE,
)
_SWAPS = {"woman": "man", "women": "men", "girl": "boy", "girls": "boys", "female": "male", "lady": "man",
          "ladies": "men", "businesswoman": "businessman", "businesswomen": "businessmen", "mother": "father",
          "mom": "dad", "wife": "husband", "sister": "brother", "daughter": "son", "girlfriend": "friend"}


def mentions_women(text: str) -> bool:
    return bool(_FEMALE.search((text or "").replace("-", " ").replace("_", " ")))


def stock_allowed(result: dict) -> bool:
    """False when a stock result's tags, title or page slug mention women (heuristic; QA does the visual check)."""
    text = " ".join(str(result.get(k) or "") for k in ("tags", "title", "page", "alt"))
    return not mentions_women(text)


def safe_query(term: str) -> str:
    """Rewrite a stock search query so it does not ask for women ("woman walking" -> "man walking")."""
    def swap(m: re.Match) -> str:
        word = m.group(0)
        repl = _SWAPS.get(word.lower(), "person")
        return repl.capitalize() if word[0].isupper() else repl
    return re.sub(r"\b[A-Za-z]+\b", lambda m: swap(m) if mentions_women(m.group(0)) else m.group(0), term)
