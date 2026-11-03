#!/usr/bin/env bash
set -euo pipefail

SITE_DIR="${GH_PAGES_DIR:-/tmp/moderator-gh-pages}"
if [ -n "${GH_TOKEN:-}" ] && [ -n "${GITHUB_REPOSITORY:-}" ]; then
  REMOTE_URL="https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
else
  REMOTE_URL=$(git config --get remote.origin.url)
fi

if [ ! -d "$SITE_DIR/.git" ]; then
  rm -rf "$SITE_DIR"
  if git ls-remote --exit-code --heads "$REMOTE_URL" gh-pages >/dev/null 2>&1; then
    git clone --quiet --depth 1 --branch gh-pages "$REMOTE_URL" "$SITE_DIR"
  else
    mkdir -p "$SITE_DIR"
    git -C "$SITE_DIR" init --quiet
    git -C "$SITE_DIR" checkout --quiet --orphan gh-pages
    git -C "$SITE_DIR" remote add origin "$REMOTE_URL"
  fi
  git -C "$SITE_DIR" config user.name "moderator-bot"
  git -C "$SITE_DIR" config user.email "41898282+github-actions[bot]@users.noreply.github.com"
else
  git -C "$SITE_DIR" remote set-url origin "$REMOTE_URL"
  if git ls-remote --exit-code --heads "$REMOTE_URL" gh-pages >/dev/null 2>&1; then
    git -C "$SITE_DIR" pull --rebase --quiet origin gh-pages || true
  fi
fi

uv run python -m moderator export-pages "$SITE_DIR" --repo "${GITHUB_REPOSITORY:-}" "$@"

git -C "$SITE_DIR" add -A
if [ -n "$(git -C "$SITE_DIR" status --porcelain)" ]; then
  git -C "$SITE_DIR" commit --quiet -m "Update Moderator Pages dashboard ($(date -u '+%Y-%m-%d %H:%M:%S UTC'))"
  if git ls-remote --exit-code --heads "$REMOTE_URL" gh-pages >/dev/null 2>&1; then
    git -C "$SITE_DIR" pull --rebase --quiet origin gh-pages || true
  fi
  git -C "$SITE_DIR" push --quiet origin HEAD:gh-pages
fi
