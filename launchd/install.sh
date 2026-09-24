#!/usr/bin/env bash
# Renders the launchd agents for this checkout and loads them. Re-run after editing a template
# or moving the repo; each agent is booted out first so the running one is replaced, not doubled.
set -euo pipefail

readonly LAUNCHD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_DIR="$(cd "$LAUNCHD_DIR/.." && pwd)"
readonly TARGET_DIR="$HOME/Library/LaunchAgents"
readonly STATE_DIR="$HOME/.local/state/spine"
readonly GUI_DOMAIN="gui/$(id -u)"

mkdir -p "$TARGET_DIR" "$STATE_DIR"

for template in "$LAUNCHD_DIR"/*.plist.template; do
  plist_name="$(basename "$template" .template)"
  label="${plist_name%.plist}"
  target="$TARGET_DIR/$plist_name"

  sed -e "s|__HOME__|$HOME|g" -e "s|__REPO__|$REPO_DIR|g" "$template" >"$target"
  plutil -lint "$target" >/dev/null

  launchctl bootout "$GUI_DOMAIN/$label" 2>/dev/null || true
  launchctl bootstrap "$GUI_DOMAIN" "$target"
  printf 'loaded %s\n' "$label"
done
