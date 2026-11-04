"""Owner edit requests on a run paused at its final checkpoint (C), e.g. from a `/edit ...` comment on the
GitHub review issue. Each request is sent back to the step that owns it; everything downstream is redone and
the run pauses at the checkpoint again with the new version.

    /edit text make the hook punchier            -> script (narration and captions)
    /edit first image show a city at night       -> visuals, scene 1 only
    /edit image 2,4 darker, slower footage        -> visuals, scenes 2 and 4
    /edit last image                              -> visuals, last scene, just a different clip
    /edit images warmer colours                   -> visuals, every scene
    /edit title shorter, add a question           -> packaging (title, description, thumbnail)
    /edit voice slower and calmer                 -> audio (voiceover)
    /edit music lower                             -> edit (mix, music level, transitions, SFX)

Several `/edit` lines in one comment are applied together.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

TARGETS: dict[str, str] = {
    **dict.fromkeys(["text", "script", "narration", "words", "hook", "story"], "script"),
    **dict.fromkeys(["image", "images", "scene", "scenes", "visual", "visuals", "clip", "clips",
                     "picture", "pictures", "photo", "photos", "footage", "broll", "b-roll"], "visuals"),
    **dict.fromkeys(["title", "description", "thumbnail", "thumb", "tags", "hashtags", "seo", "metadata"],
                    "packaging"),
    **dict.fromkeys(["voice", "voiceover", "audio", "narrator"], "audio"),
    **dict.fromkeys(["music", "video", "edit", "mix", "sfx", "transitions", "cuts", "captions", "subtitles"],
                    "edit"),
}
LABELS = {"script": "text (script)", "visuals": "images", "packaging": "title / thumbnail",
          "audio": "voiceover", "edit": "video edit / music"}
ORDINALS = {w: i for i, w in enumerate(
    ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth"], start=1)}
_NUM = r"(?:\d+(?:st|nd|rd|th)?|" + "|".join(ORDINALS) + r"|last)\b"
_LINE = re.compile(rf"^/edit\s+(?:the\s+)?(?P<pre>(?:{_NUM}\s*(?:,|and|&)?\s*)*)(?P<noun>[\w-]+)"
                   rf"(?P<post>(?:\s*(?:,|and|&)?\s*#?{_NUM})*)\s*[:\-–]?\s*(?P<rest>.*)$", re.IGNORECASE)

HELP = """Edit commands (one per line, comment on the review issue):
- `/edit text <what to change>`: rewrite the script (narration + captions)
- `/edit first image <what to show>` / `/edit image 3 <...>` / `/edit images 2,4 <...>` / `/edit last image`: replace scene visuals
- `/edit images <...>`: redo every scene visual
- `/edit title <...>` / `/edit thumbnail <...>`: title, description, thumbnail
- `/edit voice <...>`: re-record the voiceover
- `/edit music lower` / `/edit video hard cuts, no sfx`: re-edit the video"""


OWNER_PREFIX = "Owner edit request"
DIFFERENT_CLIP = "use a different clip"


class EditError(ValueError):
    pass


@dataclass
class Edit:
    target: str
    instruction: str
    scenes: list[int] = field(default_factory=list)  # 1-based, visuals only; empty = every scene
    noun: str = ""  # the word used ("music", "thumbnail"...), kept so the agent knows what the request is about

    def feedback(self) -> str:
        if self.target != "visuals":
            return f"{OWNER_PREFIX} ({self.noun or LABELS[self.target]}): {self.instruction}"
        what = self.instruction or f"{DIFFERENT_CLIP} that still fits the narration"
        if not self.scenes:
            return f"{OWNER_PREFIX} (all scenes): {what}"
        return f"{OWNER_PREFIX}:\n" + "\n".join(f"scene_{n:02d}: {what}" for n in self.scenes)

    def describe(self) -> str:
        where = f" {', '.join(map(str, self.scenes))}" if self.scenes else ""
        return f"{LABELS[self.target]}{where}" + (f": {self.instruction}" if self.instruction else "")


def _numbers(text: str, n_scenes: int) -> list[int]:
    out = []
    for tok in re.findall(_NUM, text or "", re.IGNORECASE):
        tok = tok.lower()
        n = n_scenes if tok == "last" else ORDINALS.get(tok) or int(re.sub(r"\D", "", tok))
        if not 1 <= n <= n_scenes:
            raise EditError(f"there is no scene {n} (this Short has {n_scenes} scenes)")
        if n not in out:
            out.append(n)
    return out


def parse_edits(comment: str, n_scenes: int) -> list[Edit]:
    """Parse every `/edit ...` line of a comment. Raises EditError with a readable message."""
    edits = []
    for raw in comment.replace("\r", "").splitlines():
        line = raw.strip()
        if not line.lower().startswith("/edit"):
            continue
        m = _LINE.match(line)
        if not m or m["noun"].lower() not in TARGETS:
            raise EditError(f"I don't know what to edit in `{line}`.\n\n{HELP}")
        target = TARGETS[m["noun"].lower()]
        if target == "visuals":
            instruction = m["rest"].strip()
            scenes = _numbers(f"{m['pre'] or ''} {m['post'] or ''}", n_scenes)
        else:  # numbers after the noun belong to the instruction ("/edit title 5 tips ...")
            instruction = line[m.end("noun"):].strip().lstrip(":-–").strip()
            scenes = []
        if target != "visuals" and not instruction:
            raise EditError(f"Say what to change after `/edit {m['noun']}`, e.g. `/edit {m['noun']} make it shorter`.")
        edits.append(Edit(target, instruction, scenes, m["noun"].lower()))
    if not edits:
        raise EditError(HELP)
    return edits


def apply_edits(orch, edits: list[Edit], by: str = "you") -> str:
    """Send each edit to its step on the run's pending checkpoint. Returns the checkpoint id."""
    cps = orch.store.data["checkpoints"]
    pending = [cid for cid, cp in cps.items() if cp["status"] == "pending"]
    if not pending:
        raise EditError("this run is not waiting for approval, so there is nothing to edit")
    cp_id = pending[-1]
    cp_step = cps[cp_id]["step"]
    for e in edits:
        if e.target != cp_step and cp_step not in orch.workflow.downstream(e.target):
            raise EditError(f"'{LABELS[e.target]}' cannot be edited at checkpoint {cp_id}")
    targets = {e.target for e in edits}
    with orch.store.mutate() as d:
        d["checkpoints"][cp_id].update(status="changes_requested", comment="\n".join(e.describe() for e in edits))
    for e in edits:
        orch.send_back(e.target, e.feedback(), source=by, preserve_revising=targets)
    return cp_id
