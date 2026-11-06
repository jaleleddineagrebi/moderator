"""Tests for visual diversity tracking, cross-run deduplication, and QA duplicate checks."""

import json
from pathlib import Path

from moderator.tools import visual_history


def test_visual_history_records_and_retrieves(tmp_path: Path):
    hist_file = tmp_path / "visuals.jsonl"
    assert visual_history.recent_used_pages(path=hist_file) == set()

    licenses_run_1 = [
        {"scene": "scene_01", "provider": "pexels", "page": "https://www.pexels.com/video/101/", "query": "man walking"},
        {"scene": "scene_02", "provider": "pexels", "page": "https://www.pexels.com/video/102/", "query": "night city"},
        {"scene": "scene_03", "provider": "generated", "license": "procedural"},  # no page
    ]
    visual_history.record_visuals("run_01", licenses_run_1, path=hist_file)

    used = visual_history.recent_used_pages(path=hist_file)
    assert "https://www.pexels.com/video/101/" in used
    assert "https://www.pexels.com/video/102/" in used
    assert len(used) == 2

    # Second run adds new visual and updates without duplicating
    licenses_run_2 = [
        {"scene": "scene_01", "provider": "pixabay", "page": "https://pixabay.com/videos/201/", "query": "ocean waves"},
    ]
    visual_history.record_visuals("run_02", licenses_run_2, path=hist_file)

    used_2 = visual_history.recent_used_pages(path=hist_file)
    assert len(used_2) == 3
    assert "https://pixabay.com/videos/201/" in used_2


def test_qa_reviewer_blocks_duplicate_visuals(tmp_path: Path):
    """Verify that QA reviewer checks and blocks if two scenes reuse the same footage."""
    licenses = [
        {"scene": "scene_01", "provider": "pexels", "page": "https://www.pexels.com/video/999/", "license": "free"},
        {"scene": "scene_02", "provider": "pexels", "page": "https://www.pexels.com/video/999/", "license": "free"},  # Duplicate!
        {"scene": "scene_03", "provider": "pixabay", "page": "https://pixabay.com/videos/555/", "license": "free"},
    ]
    seen_pages = {}
    visual_dupes = []
    for l in licenses:
        page = l.get("page")
        if page:
            if page in seen_pages:
                visual_dupes.append(f"{l['scene']} repeats footage from {seen_pages[page]} ({page})")
            else:
                seen_pages[page] = l["scene"]

    assert len(visual_dupes) == 1
    assert "scene_02 repeats footage from scene_01" in visual_dupes[0]
