#!/usr/bin/env bash
# Registers this session so it appears on the dashboard with its projects.
# Always exits 0: registration must never block a session from starting.
set -uo pipefail
[[ -n "${SPINE_DISABLED:-}" ]] && exit 0
command -v spine >/dev/null 2>&1 || exit 0

session_id="${SPINE_SESSION_ID:-${CLAUDE_SESSION_ID:-}}"
[[ -z "$session_id" ]] && exit 0

projects="$(spine context which --cwd "$PWD" 2>/dev/null | awk '{print $1}' | paste -sd, -)"
[[ -z "$projects" ]] && exit 0

spine live declare --session "$session_id" --project "$projects" \
  --intent "${SPINE_INTENT:-started in $(basename "$PWD")}" >/dev/null 2>&1
exit 0
