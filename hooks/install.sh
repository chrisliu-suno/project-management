#!/usr/bin/env bash
# Symlinks every spine session hook into ~/.claude/hooks, so the copy Claude Code runs is the
# copy in this repository. Registering them in settings.json stays manual: that file is shared
# with other tools and merging it blindly is how a hook gets registered twice.
set -euo pipefail

readonly HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly TARGET_DIR="${CLAUDE_HOOKS_DIR:-$HOME/.claude/hooks}"

mkdir -p "$TARGET_DIR"
for hook in "$HOOKS_DIR"/spine-*.sh; do
  ln -sf "$hook" "$TARGET_DIR/$(basename "$hook")"
  printf 'linked %s\n' "$(basename "$hook")"
done
