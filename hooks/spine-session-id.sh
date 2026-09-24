#!/usr/bin/env bash
# Prints this hook's session id, or nothing.
#
# The hook payload on stdin is authoritative — a subagent carries its own id there,
# and the environment's belongs to the session that spawned it. Callers that have
# already consumed stdin pass the payload as $1.
#
# Usage: session_id="$(spine_session_id "$payload")"
spine_session_id() {
  local payload="${1:-}"
  local from_payload=""
  if [[ -n "$payload" ]]; then
    from_payload="$(printf '%s' "$payload" | python3 -c '
import json, sys
try:
    print((json.load(sys.stdin) or {}).get("session_id") or "")
except Exception:
    pass
' 2>/dev/null)"
  fi
  printf '%s' "${SPINE_SESSION_ID:-${from_payload:-${CLAUDE_CODE_SESSION_ID:-${CLAUDE_SESSION_ID:-}}}}"
}
