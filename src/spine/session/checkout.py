"""Remembered project choice for a linked git worktree.

A worktree is cut per change, so it is about one thing and the answer keeps. The primary
checkout is shared across every project in the repository, so it keeps asking.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..paths import checkouts_dir, ensure_spine_home

CHECKOUT_FILE_SUFFIX = ".json"
CHECKOUT_ENCODING = "utf-8"
CHECKOUT_KEY_LENGTH = 16
GIT_TOPLEVEL_COMMAND = ("git", "rev-parse", "--show-toplevel")
GIT_COMMON_DIR_COMMAND = ("git", "rev-parse", "--git-common-dir")
GIT_DIR_COMMAND = ("git", "rev-parse", "--git-dir")
GIT_TIMEOUT_SECONDS = 3

FIELD_ROOT = "root"
FIELD_PROJECT_SLUGS = "project_slugs"
FIELD_DECIDED_AT = "decided_at"


@dataclass(frozen=True, slots=True)
class CheckoutChoice:
    """The projects a worktree was answered with, and when."""

    root: Path
    project_slugs: tuple[str, ...]
    decided_at: datetime


def _run_git(*, command: tuple[str, ...], cwd: Path) -> str | None:
    try:
        finished = subprocess.run(
            command, cwd=cwd, capture_output=True, text=True, timeout=GIT_TIMEOUT_SECONDS
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if finished.returncode != 0:
        return None
    return finished.stdout.strip() or None


def linked_worktree_root(*, cwd: Path) -> Path | None:
    """The worktree root when cwd is in a linked worktree, and None in a primary checkout.

    A linked worktree's own git dir sits under the shared one as `worktrees/<name>`, so the
    two differ; in a primary checkout they resolve to the same directory.
    """
    toplevel = _run_git(command=GIT_TOPLEVEL_COMMAND, cwd=cwd)
    if toplevel is None:
        return None
    git_dir = _run_git(command=GIT_DIR_COMMAND, cwd=cwd)
    common_dir = _run_git(command=GIT_COMMON_DIR_COMMAND, cwd=cwd)
    if git_dir is None or common_dir is None:
        return None
    resolved_git_dir = (cwd / git_dir).resolve()
    resolved_common_dir = (cwd / common_dir).resolve()
    if resolved_git_dir == resolved_common_dir:
        return None
    return Path(toplevel)


def checkout_path(*, root: Path) -> Path:
    """State file for a worktree, named by a digest so any path length is safe."""
    digest = hashlib.sha256(str(root).encode(CHECKOUT_ENCODING)).hexdigest()
    return checkouts_dir() / f"{digest[:CHECKOUT_KEY_LENGTH]}{CHECKOUT_FILE_SUFFIX}"


class FileCheckoutStore:
    """Stores one JSON file per worktree, keyed by a digest of its root path."""

    def read(self, *, root: Path) -> CheckoutChoice | None:
        path = checkout_path(root=root)
        if not path.is_file():
            return None
        try:
            mapping = json.loads(path.read_text(encoding=CHECKOUT_ENCODING))
            slugs = mapping[FIELD_PROJECT_SLUGS]
            if not isinstance(slugs, list) or not slugs:
                return None
            return CheckoutChoice(
                root=Path(str(mapping[FIELD_ROOT])),
                project_slugs=tuple(str(slug) for slug in slugs),
                decided_at=datetime.fromisoformat(str(mapping[FIELD_DECIDED_AT])),
            )
        except (KeyError, TypeError, ValueError, OSError):
            return None

    def write(self, *, choice: CheckoutChoice) -> None:
        ensure_spine_home()
        path = checkout_path(root=choice.root)
        payload = json.dumps(
            {
                FIELD_ROOT: str(choice.root),
                FIELD_PROJECT_SLUGS: list(choice.project_slugs),
                FIELD_DECIDED_AT: choice.decided_at.isoformat(),
            },
            indent=2,
            sort_keys=True,
        )
        temporary = path.with_suffix(path.suffix + ".partial")
        temporary.write_text(payload, encoding=CHECKOUT_ENCODING)
        temporary.replace(path)

    def clear(self, *, root: Path) -> bool:
        path = checkout_path(root=root)
        if not path.is_file():
            return False
        path.unlink()
        return True


def remember_choice(*, cwd: Path, project_slugs: tuple[str, ...]) -> Path | None:
    """Record the choice for cwd's worktree. Returns the root remembered, or None if primary."""
    root = linked_worktree_root(cwd=cwd)
    if root is None or not project_slugs:
        return None
    FileCheckoutStore().write(
        choice=CheckoutChoice(
            root=root, project_slugs=project_slugs, decided_at=datetime.now(tz=UTC)
        )
    )
    return root


def recall_choice(*, cwd: Path) -> CheckoutChoice | None:
    """The choice previously recorded for cwd's worktree, if it is a linked one."""
    root = linked_worktree_root(cwd=cwd)
    if root is None:
        return None
    return FileCheckoutStore().read(root=root)
