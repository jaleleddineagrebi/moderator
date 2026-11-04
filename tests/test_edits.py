import pytest

from moderator.edits import EditError, parse_edits


def _p(text, n=8):
    return [(e.target, e.scenes, e.instruction) for e in parse_edits(text, n)]


@pytest.mark.parametrize("text, expected", [
    ("/edit first image show a man running at sunrise", [("visuals", [1], "show a man running at sunrise")]),
    ("/edit image 2,4 darker city", [("visuals", [2, 4], "darker city")]),
    ("/edit Image 2 and 5 - ocean waves", [("visuals", [2, 5], "ocean waves")]),
    ("/edit the 3rd image: a calm lake", [("visuals", [3], "a calm lake")]),
    ("/edit last image", [("visuals", [8], "")]),
    ("/edit images warmer colours", [("visuals", [], "warmer colours")]),
    ("/edit text make the hook punchier", [("script", [], "make the hook punchier")]),
    ("/edit title 5 tips, shorter", [("packaging", [], "5 tips, shorter")]),
    ("/edit voice slower", [("audio", [], "slower")]),
    ("/edit music lower", [("edit", [], "lower")]),
])
def test_parse_single_edit(text, expected):
    assert _p(text) == expected


def test_parse_several_lines_and_feedback_format():
    edits = parse_edits("thanks!\r\n/edit text shorter hook\n/edit image 3 a lake\n/edit music lower", 5)
    assert [e.target for e in edits] == ["script", "visuals", "edit"]
    assert edits[1].feedback() == "Owner edit request:\nscene_03: a lake"
    assert "music" in edits[2].feedback()
    assert parse_edits("/edit last image", 5)[0].feedback().startswith("Owner edit request:\nscene_05: use a different clip")


@pytest.mark.parametrize("text, message", [
    ("/edit image 12", "no scene 12"),
    ("/edit banana now", "don't know what to edit"),
    ("/edit text", "Say what to change"),
    ("hello", "Edit commands"),
])
def test_parse_errors(text, message):
    with pytest.raises(EditError, match=message):
        parse_edits(text, 8)
