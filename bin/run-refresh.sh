#!/usr/bin/env bash
# The hourly sweep, as launchd runs it.
#
# launchd starts jobs with no shell profile, so the Anthropic key exported by ~/.zshrc is not
# there and the sweep's classify step would report itself unavailable forever. This reads the
# key from the same chmod 600 file the shell does, then hands off to spine.
#
# Exits 0 whether or not the key was found: a missing key degrades the sweep to indexing only,
# which the refresh line already says out loud.
set -uo pipefail

readonly KEY_FILE="$HOME/.config/anthropic/env.zsh"
readonly SPINE_BIN="$HOME/.local/bin/spine"

if [[ -r "$KEY_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$KEY_FILE"
  export ANTHROPIC_API_KEY
fi

printf '=== refresh %s ===\n' "$(date '+%Y-%m-%d %H:%M:%S')"
"$SPINE_BIN" refresh
