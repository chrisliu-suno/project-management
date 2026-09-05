#!/usr/bin/env bash
# Injects a session's project context at start. Reports every failure to stderr:
# a silent no-op would ship a session without its project rules.
set -uo pipefail

[[ -n "${SPINE_DISABLED:-}" ]] && exit 0

if ! command -v spine >/dev/null 2>&1; then
  echo "spine: binary not on PATH; project context NOT injected" >&2
  exit 0
fi

session_id="${SPINE_SESSION_ID:-${CLAUDE_SESSION_ID:-}}"
if [[ -z "$session_id" ]]; then
  echo "spine: no session id in environment; project context NOT injected" >&2
  exit 0
fi

if ! stamp="$(spine session show --session "$session_id" 2>/dev/null)"; then
  echo "spine: session $session_id has no project attached; run 'spine session set --project <slug>'" >&2
  exit 0
fi

project="$(printf '%s' "$stamp" | cut -f2 | cut -d, -f1)"
if [[ -z "$project" ]]; then
  echo "spine: stamp for $session_id names no project" >&2
  exit 0
fi

if ! spine pick --project "$project" --task "${SPINE_TASK_CONTEXT:-session start}"; then
  echo "spine: pick failed for project $project; context NOT injected" >&2
fi
exit 0
