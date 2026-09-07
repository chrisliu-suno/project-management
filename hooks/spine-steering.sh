#!/usr/bin/env bash
# Picks up queued instructions at a turn boundary and applies pause/stop/resume.
# Always exits 0: a steering failure must not wedge the session.
set -uo pipefail
[[ -n "${SPINE_DISABLED:-}" ]] && exit 0
command -v spine >/dev/null 2>&1 || exit 0

session_id="${SPINE_SESSION_ID:-${CLAUDE_SESSION_ID:-}}"
[[ -z "$session_id" ]] && exit 0

lines="$(spine guard steering --session "$session_id" 2>/dev/null)" || exit 0
[[ -n "$lines" ]] && printf 'Steering instruction for this session:\n%s\n' "$lines"
exit 0
