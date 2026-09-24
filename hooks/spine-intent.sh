#!/usr/bin/env bash
# Re-declares this session with the prompt as its intent, so the dashboard says what the
# session is doing now rather than where it started.
# Always exits 0: a declaration must never swallow a prompt.
set -uo pipefail
[[ -n "${SPINE_DISABLED:-}" ]] && exit 0
command -v spine >/dev/null 2>&1 || exit 0

payload="$(cat 2>/dev/null || true)"
source "$HOME/.claude/hooks/spine-session-id.sh"
session_id="$(spine_session_id "$payload")"
[[ -z "$session_id" ]] && exit 0

# One line, because the dashboard shows intent on one: newlines collapse and a long prompt
# is cut at the limit below rather than filling the card.
intent="$(printf '%s' "$payload" | python3 -c '
import json, re, sys

LIMIT = 160
# Turns the harness delivers as prompts. They are not what the session is doing, and they push
# the last thing the human actually asked for off the dashboard card.
MACHINE_TURN_PATTERN = re.compile(
    r"^(<task-notification>|<local-command|<command-name|<bash-input>|Replying to this part"
    r"|\[Request interrupted|Caveat:|This session is being continued)"
)
try:
    prompt = (json.load(sys.stdin) or {}).get("prompt") or ""
except Exception:
    sys.exit(0)
flat = " ".join(prompt.split())
if not flat or MACHINE_TURN_PATTERN.match(flat):
    sys.exit(0)
print(flat[:LIMIT] + ("…" if len(flat) > LIMIT else ""))
' 2>/dev/null)"
[[ -z "$intent" ]] && exit 0

projects="$(spine context which --cwd "$PWD" 2>/dev/null | awk '{print $1}' | paste -sd, -)"
[[ -z "$projects" ]] && exit 0

spine live declare --session "$session_id" --project "$projects" --intent "$intent" >/dev/null 2>&1

# Task-relevant documents, chosen once per session. Silent on every later prompt.
payload="$(spine context task --task "$intent" --cwd "$PWD" --session "$session_id" 2>/dev/null)" || exit 0
[[ -n "$payload" ]] && printf '%s\n' "$payload"
exit 0
