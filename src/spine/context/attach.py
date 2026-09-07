"""Works out which projects a session belongs to.

Reading a stamp is exact and free, so it wins. Inference over cwd, branch and
repo is the fallback for sessions that started outside any project.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..constants import (
    ATTACH_CONFIDENCE_MARGIN,
    MAX_AUTO_ATTACH_PROJECTS,
    MIN_CONFIDENCE_FOR_AUTO_ATTACH,
)
from ..model import Project

GIT_BRANCH_COMMAND = ("git", "rev-parse", "--abbrev-ref", "HEAD")
GIT_REMOTE_COMMAND = ("git", "remote", "get-url", "origin")
GIT_TIMEOUT_SECONDS = 3
STAMP_SOURCE = "stamp"
INFERRED_SOURCE = "inferred"
GITHUB_SUFFIX = ".git"


@dataclass(frozen=True, slots=True)
class Attachment:
    """The projects a session is working in, and how that was decided."""

    projects: tuple[Project, ...]
    source: str
    evidence: tuple[str, ...] = ()


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


def current_branch(*, cwd: Path) -> str | None:
    """The checked-out branch, or None outside a repository."""
    return _run_git(command=GIT_BRANCH_COMMAND, cwd=cwd)


def current_repo(*, cwd: Path) -> str | None:
    """The origin remote as owner/name, or None when there is no remote."""
    url = _run_git(command=GIT_REMOTE_COMMAND, cwd=cwd)
    if url is None:
        return None
    trimmed = url.removesuffix(GITHUB_SUFFIX)
    parts = trimmed.replace(":", "/").split("/")
    if len(parts) < 2:
        return None
    return "/".join(parts[-2:])


def _from_stamp(*, session_id: str | None, registry) -> Attachment | None:
    if session_id is None:
        return None
    from ..session import resolve_stamp

    stamp = resolve_stamp(session_id=session_id)
    if stamp is None:
        return None
    found = tuple(
        project
        for slug in stamp.project_slugs
        if (project := registry.get(slug)) is not None
    )
    if not found:
        return None
    return Attachment(projects=found, source=STAMP_SOURCE, evidence=(f"stamp {session_id}",))


def _best_matches(*, matches):
    """Only the strongest matches attach.

    A signal several projects share — one repository holding several projects —
    would otherwise attach all of them to every session in that repository. Past
    MAX_AUTO_ATTACH_PROJECTS the signal is treated as ambiguous and nothing attaches.
    """
    confident = [
        match for match in matches if match.confidence >= MIN_CONFIDENCE_FOR_AUTO_ATTACH
    ]
    if not confident:
        return ()
    best = max(match.confidence for match in confident)
    top = tuple(
        match for match in confident if best - match.confidence <= ATTACH_CONFIDENCE_MARGIN
    )
    if len(top) > MAX_AUTO_ATTACH_PROJECTS:
        return ()
    return top


def _from_signals(*, cwd: Path, registry) -> Attachment:
    from ..registry import SignalResolver

    matches = SignalResolver(registry=registry).resolve(
        cwd=cwd, branch=current_branch(cwd=cwd), repo=current_repo(cwd=cwd)
    )
    confident = _best_matches(matches=matches)
    return Attachment(
        projects=tuple(match.project for match in confident),
        source=INFERRED_SOURCE,
        evidence=tuple(
            f"{match.project.slug}: {'; '.join(match.evidence)}" for match in confident
        ),
    )


def attach(*, cwd: Path, session_id: str | None = None) -> Attachment:
    """The session's projects, from its stamp if it has one and signals otherwise."""
    from ..registry import load_registry

    registry = load_registry()
    stamped = _from_stamp(session_id=session_id, registry=registry)
    if stamped is not None:
        return stamped
    return _from_signals(cwd=cwd, registry=registry)
