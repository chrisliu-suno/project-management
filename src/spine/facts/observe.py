"""Reads commits and pull requests from what already exists."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from ..constants import (
    FACTS_MIN_TITLE_TERM_LENGTH,
    FACTS_COMMIT_LIMIT,
    FACTS_PR_LIMIT,
    GIT_FIELD_SEPARATOR,
    GIT_LOG_FORMAT,
    GITHUB_CLI_PATH,
    SUBPROCESS_TIMEOUT_SECONDS,
)
from ..model import Project
from .model import Fact, FactKind, PullRequestState

COMMIT_FIELD_COUNT = 4
PR_JSON_FIELDS = "number,title,author,state,createdAt,mergedAt,url,headRefName"
HEAD_REF_FIELD = "headRefName"
MERGED_AT_FIELD = "mergedAt"


def _run(*, command: tuple[str, ...], cwd: Path | None = None) -> str | None:
    try:
        finished = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return finished.stdout if finished.returncode == 0 else None


def _commit_fact(*, line: str, project_slug: str) -> Fact | None:
    parts = line.split(GIT_FIELD_SEPARATOR)
    if len(parts) != COMMIT_FIELD_COUNT:
        return None
    sha, author, occurred_at, subject = parts
    return Fact(
        fact_id=f"{project_slug}:commit:{sha}",
        project_slug=project_slug,
        kind=FactKind.COMMIT,
        reference=sha[:12],
        title=subject,
        author=author,
        occurred_at=occurred_at,
    )


def observe_commits(*, project: Project, repo_dir: Path, branch: str) -> tuple[Fact, ...]:
    """Recent commits on a branch, or nothing when the directory is not a repository."""
    output = _run(
        command=(
            "git",
            "log",
            branch,
            f"--pretty=format:{GIT_LOG_FORMAT}",
            f"--max-count={FACTS_COMMIT_LIMIT}",
        ),
        cwd=repo_dir,
    )
    if output is None:
        return ()
    found = (
        _commit_fact(line=line, project_slug=project.slug)
        for line in output.splitlines()
        if line.strip()
    )
    return tuple(fact for fact in found if fact is not None)


def _pr_state(*, entry: dict) -> PullRequestState:
    if entry.get(MERGED_AT_FIELD):
        return PullRequestState.MERGED
    return PullRequestState(str(entry.get("state", "open")).lower())


def _pr_fact(*, entry: dict, project_slug: str) -> Fact | None:
    number = entry.get("number")
    if number is None:
        return None
    author = entry.get("author") or {}
    return Fact(
        fact_id=f"{project_slug}:pr:{number}",
        project_slug=project_slug,
        kind=FactKind.PULL_REQUEST,
        reference=f"#{number}",
        title=str(entry.get("title", "")),
        author=str(author.get("login", "")),
        occurred_at=str(entry.get(MERGED_AT_FIELD) or entry.get("createdAt", "")),
        state=str(_pr_state(entry=entry)),
        url=str(entry.get("url", "")),
    )


def _project_terms(*, project: Project) -> frozenset[str]:
    words = re.findall(r"[a-z0-9]+", f"{project.slug} {project.name}".lower())
    return frozenset(word for word in words if len(word) >= FACTS_MIN_TITLE_TERM_LENGTH)


def is_relevant(*, entry: dict, project: Project) -> bool:
    """Whether a pull request plausibly belongs to this project.

    One repository holds several projects, so every merged pull request would
    otherwise read as undocumented work on all of them.
    """
    head = str(entry.get(HEAD_REF_FIELD, ""))
    if any(head.startswith(prefix) for prefix in project.branch_prefixes):
        return True
    title_words = set(re.findall(r"[a-z0-9]+", str(entry.get("title", "")).lower()))
    return bool(title_words & _project_terms(project=project))


def observe_pull_requests(*, project: Project) -> tuple[Fact, ...]:
    """Recent pull requests for the project's first repository."""
    if not project.repos:
        return ()
    output = _run(
        command=(
            GITHUB_CLI_PATH,
            "pr",
            "list",
            "--repo",
            project.repos[0],
            "--state",
            "all",
            "--limit",
            str(FACTS_PR_LIMIT),
            "--json",
            PR_JSON_FIELDS,
        )
    )
    if output is None:
        return ()
    try:
        entries = json.loads(output)
    except json.JSONDecodeError:
        return ()
    found = (
        _pr_fact(entry=entry, project_slug=project.slug)
        for entry in entries
        if is_relevant(entry=entry, project=project)
    )
    return tuple(fact for fact in found if fact is not None)
