#!/usr/bin/env bash
# Injects the always-read documents for whichever projects this session belongs to.
# Always exits 0: a context failure must never block a session from starting.
set -uo pipefail

[[ -n "${SPINE_DISABLED:-}" ]] && exit 0
command -v spine >/dev/null 2>&1 || exit 0

# The hook payload carries the session id and the directory the session started in. Without the
# id every pick spine records is filed under "unknown", which is the whole left side of the
# graphd join; $PWD is the fallback for the directory because a payload may carry neither.
session_cwd="$PWD"
if command -v jq >/dev/null 2>&1; then
  payload_json="$(cat)"
  session_id="$(jq -r '.session_id // empty' <<<"$payload_json" 2>/dev/null)"
  payload_cwd="$(jq -r '.cwd // empty' <<<"$payload_json" 2>/dev/null)"
  [[ -n "${session_id:-}" ]] && export SPINE_SESSION_ID="$session_id"
  [[ -n "${payload_cwd:-}" && -d "$payload_cwd" ]] && session_cwd="$payload_cwd"
fi

payload="$(spine context --cwd "$session_cwd" ${SPINE_SESSION_ID:+--session "$SPINE_SESSION_ID"} 2>/dev/null)" || exit 0
[[ -n "$payload" ]] && printf '%s\n' "$payload"
exit 0
