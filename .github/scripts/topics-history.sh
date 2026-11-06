#!/usr/bin/env bash
# Topic history for scheduled runs lives on the `topics-history` branch, not on `main`,
# because `main` only accepts pull requests (see .github/rulesets/protect-main.json).
#   load: merge the branch's topics.jsonl into history/topics.jsonl before a run
#   save: merge history/topics.jsonl back into the branch and push it (retries on races)
set -euo pipefail

BRANCH=topics-history
LOCAL_TOPICS=history/topics.jsonl
LOCAL_VISUALS=history/visuals.jsonl

merge() {  # merge <into> <from>: union of rows by run_id (or scene for visuals); rows in <from> win, order kept
  "${PYTHON:-python3}" - "$1" "$2" <<'PY'
import json, sys
from pathlib import Path
into, src = Path(sys.argv[1]), Path(sys.argv[2])
rows = {}
for p in (into, src):
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                key = f"{row.get('run_id')}:{row.get('scene', '')}" if row.get("scene") else (row.get("run_id") or line)
                rows[key] = row
into.parent.mkdir(parents=True, exist_ok=True)
into.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows.values()), encoding="utf-8")
PY
}

case "${1:-}" in
  load)
    if git fetch -q origin "$BRANCH" 2>/dev/null; then
      git show "origin/$BRANCH:topics.jsonl" > "$RUNNER_TEMP/branch_topics.jsonl" 2>/dev/null || true
      merge "$LOCAL_TOPICS" "$RUNNER_TEMP/branch_topics.jsonl"
      git show "origin/$BRANCH:visuals.jsonl" > "$RUNNER_TEMP/branch_visuals.jsonl" 2>/dev/null || true
      merge "$LOCAL_VISUALS" "$RUNNER_TEMP/branch_visuals.jsonl"
    fi
    echo "Topic history: $(grep -c . "$LOCAL_TOPICS" 2>/dev/null || echo 0) topics"
    echo "Visual history: $(grep -c . "$LOCAL_VISUALS" 2>/dev/null || echo 0) visuals"
    ;;
  save)
    WT="$RUNNER_TEMP/topics-history"
    for attempt in 1 2 3; do
      rm -rf "$WT"; git worktree prune
      if git fetch -q origin "$BRANCH" 2>/dev/null; then
        git worktree add -q -B "$BRANCH" "$WT" "origin/$BRANCH"
      else
        git worktree add -q --orphan -b "$BRANCH" "$WT"
      fi
      merge "$WT/topics.jsonl" "$LOCAL_TOPICS"
      merge "$WT/visuals.jsonl" "$LOCAL_VISUALS"
      git -C "$WT" add topics.jsonl visuals.jsonl
      if [ -z "$(git -C "$WT" status --porcelain)" ]; then echo "History unchanged"; exit 0; fi
      git -C "$WT" -c user.name="moderator-bot" -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
        commit -q -m "Record Short topic and visual history ($(date -u +%F))"
      if git -C "$WT" push -q origin "HEAD:$BRANCH"; then echo "History saved to $BRANCH"; exit 0; fi
      echo "Push raced with another run; retrying ($attempt)"; sleep $((attempt * 3))
    done
    echo "::warning::Could not save history"; exit 0
    ;;
  *) echo "usage: $0 load|save" >&2; exit 2 ;;
esac
