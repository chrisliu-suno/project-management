#!/usr/bin/env bash
# Warns when an edit falls outside what this session declared, and refuses
# while the session is paused or stopped. Exits 0 on every other path so a
# guard problem never blocks ordinary work.
set -uo pipefail

[[ -n "${SPINE_DISABLED:-}" ]] && exit 0
command -v spine >/dev/null 2>&1 || exit 0

session_id="${SPINE_SESSION_ID:-${CLAUDE_SESSION_ID:-}}"
[[ -z "$session_id" ]] && exit 0

payload="$(cat 2>/dev/null || true)"
path="$(printf '%s' "$payload" | python3 -c '
import json,sys
try:
    parsed = json.load(sys.stdin)
except Exception:
    sys.exit(0)
tool_input = parsed.get("tool_input") or {}
print(tool_input.get("file_path") or tool_input.get("path") or "")
' 2>/dev/null)"
[[ -z "$path" ]] && exit 0

spine guard edit --session "$session_id" --path "$path"
exit $?
