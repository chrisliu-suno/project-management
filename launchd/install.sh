#!/usr/bin/env bash
# Renders the launchd agents for this checkout and loads them. Re-run after editing a template
# or moving the repo; each agent is booted out first so the running one is replaced, not doubled.
set -euo pipefail

readonly LAUNCHD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_DIR="$(cd "$LAUNCHD_DIR/.." && pwd)"
readonly TARGET_DIR="$HOME/Library/LaunchAgents"
readonly STATE_DIR="$HOME/.local/state/spine"
readonly GUI_DOMAIN="gui/$(id -u)"
# A booted-out service is not gone the moment the command returns. Bootstrapping into that gap
# fails with "Input/output error", and under `set -e` it takes the rest of the agents with it.
readonly BOOTSTRAP_ATTEMPTS=10
readonly BOOTSTRAP_RETRY_SECONDS=1

mkdir -p "$TARGET_DIR" "$STATE_DIR"

bootstrap_once_the_old_service_is_gone() {
  local label="$1" plist_path="$2" attempt
  for ((attempt = 1; attempt <= BOOTSTRAP_ATTEMPTS; attempt++)); do
    if launchctl bootstrap "$GUI_DOMAIN" "$plist_path" 2>/dev/null; then
      printf 'loaded %s\n' "$label"
      return 0
    fi
    sleep "$BOOTSTRAP_RETRY_SECONDS"
  done
  printf 'could not load %s after %d attempts\n' "$label" "$BOOTSTRAP_ATTEMPTS" >&2
  return 1
}

failed_labels=()

for template in "$LAUNCHD_DIR"/*.plist.template; do
  plist_name="$(basename "$template" .template)"
  label="${plist_name%.plist}"
  target="$TARGET_DIR/$plist_name"

  sed -e "s|__HOME__|$HOME|g" -e "s|__REPO__|$REPO_DIR|g" "$template" >"$target"
  plutil -lint "$target" >/dev/null

  launchctl bootout "$GUI_DOMAIN/$label" 2>/dev/null || true
  bootstrap_once_the_old_service_is_gone "$label" "$target" || failed_labels+=("$label")
done

((${#failed_labels[@]} == 0)) || exit 1
