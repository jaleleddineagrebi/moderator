"""People rule for visuals: stock filtering and search-term rewriting (moderator/tools/visual_rules.py)."""

from moderator.tools import visual_rules as vr


def test_mentions_women():
    for text in ("young woman walking", "Girls laughing", "businesswoman typing", "femme qui marche",
                 "https://www.pexels.com/video/a-woman-using-her-phone-12345/", "mother and son", "Woman"):
        assert vr.mentions_women(text), text
    for text in ("man walking", "crowd at night", "human brain scan", "romantic sunset", "womb", "omen"):
        assert not vr.mentions_women(text), text


def test_stock_allowed_checks_tags_slug_and_alt():
    assert vr.stock_allowed({"page": "https://pixabay.com/videos/city-night-123/", "tags": "city, night, lights"})
    assert not vr.stock_allowed({"page": "https://pixabay.com/videos/city-123/", "tags": "city, girl, smile"})
    assert not vr.stock_allowed({"page": "https://www.pexels.com/video/woman-on-phone-99/"})
    assert not vr.stock_allowed({"page": "https://www.pexels.com/photo/1/", "alt": "Lady reading a book"})


def test_safe_query_rewrites_female_terms():
    assert vr.safe_query("woman scrolling phone") == "man scrolling phone"
    assert vr.safe_query("Girls laughing") == "Boys laughing"
    assert vr.safe_query("mother cooking") == "father cooking"
    assert vr.safe_query("clock hands moving") == "clock hands moving"
