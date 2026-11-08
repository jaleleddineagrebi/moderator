#!/usr/bin/env bash
# Daily post history for scheduled portal runs lives on the `portal-history` branch, not on `main`,
# because `main` only accepts pull requests (see GitHub rulesets).
#   load: fetch past daily posts from portal-history branch into history/daily_posts/
#   save: commit new daily posts to portal-history branch and push it (retries on races)
set -euo pipefail

BRANCH=portal-history
LOCAL_DIR=history/daily_posts

case "${1:-}" in
  load)
    mkdir -p "$LOCAL_DIR"
    if git fetch -q origin "$BRANCH" 2>/dev/null; then
      TMP_ARCHIVE="${RUNNER_TEMP:-/tmp}/portal_history_archive.tar"
      if git archive --format=tar "origin/$BRANCH" daily_posts 2>/dev/null > "$TMP_ARCHIVE"; then
        tar -xf "$TMP_ARCHIVE" -C "${RUNNER_TEMP:-/tmp}" 2>/dev/null || true
        if [ -d "${RUNNER_TEMP:-/tmp}/daily_posts" ]; then
          cp -rn "${RUNNER_TEMP:-/tmp}/daily_posts"/* "$LOCAL_DIR/" 2>/dev/null || true
        fi
      fi
    fi
    echo "Daily post history loaded: $(ls -1 "$LOCAL_DIR" 2>/dev/null | wc -l | tr -d ' ') files"
    ;;
  save)
    if [ ! -d "$LOCAL_DIR" ] || [ -z "$(ls -A "$LOCAL_DIR" 2>/dev/null)" ]; then
      echo "No daily posts to save."
      exit 0
    fi
    WT="${RUNNER_TEMP:-/tmp}/portal-history"
    for attempt in 1 2 3; do
      rm -rf "$WT"
      git worktree prune 2>/dev/null || true
      if git fetch -q origin "$BRANCH" 2>/dev/null; then
        git worktree add -q -B "$BRANCH" "$WT" "origin/$BRANCH"
      else
        git worktree add -q --orphan -b "$BRANCH" "$WT"
      fi
      mkdir -p "$WT/daily_posts"
      cp -rf "$LOCAL_DIR"/* "$WT/daily_posts/" 2>/dev/null || true
      git -C "$WT" add daily_posts/
      if [ -z "$(git -C "$WT" status --porcelain)" ]; then
        echo "Daily post history unchanged."
        exit 0
      fi
      git -C "$WT" -c user.name="moderator-bot" -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
        commit -q -m "Archive daily Psychology & AI posts ($(date -u +%F)) [skip ci]"
      if git -C "$WT" push -q origin "HEAD:$BRANCH"; then
        echo "Daily post history saved to $BRANCH";
        exit 0
      fi
      echo "Push raced with another run; retrying ($attempt)..."
      sleep $((attempt * 3))
    done
    echo "::warning::Could not save daily post history"; exit 0
    ;;
  *)
    echo "usage: $0 load|save" >&2
    exit 2
    ;;
esac
