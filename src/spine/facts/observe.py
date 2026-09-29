"""Reads commits and pull requests from what already exists."""

from __future__ import annotations

import json
import re
import subprocess
from fnmatch import fnmatch
from functools import lru_cache
from pathlib import Path

from ..constants import (
    CACHED_PULL_REQUEST_QUERIES,
    CONVENTIONAL_COMMIT_TYPES,
    FACTS_AUTHOR_PR_LIMIT,
    FACTS_COMMIT_LIMIT,
    FACTS_MIN_TITLE_TERM_LENGTH,
    FACTS_PR_LIMIT,
    GIT_FIELD_SEPARATOR,
    GIT_LOG_FORMAT,
    GITHUB_CLI_PATH,
    SUBPROCESS_TIMEOUT_SECONDS,
)
from ..model import Project
from .model import Fact, FactKind, PullRequestState

COMMIT_FIELD_COUNT = 4
PR_JSON_FIELDS = "number,title,author,state,createdAt,mergedAt,url,headRefName,files"
HEAD_REF_FIELD = "headRefName"
MERGED_AT_FIELD = "mergedAt"
FILES_FIELD = "files"
FILE_PATH_KEY = "path"
PATHSPEC_SEPARATOR = "--"


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
    """Recent commits touching the project's declared paths.

    A project that declares none gets nothing: every commit on the branch is the
    wrong answer in a repository that holds several projects.
    """
    if not project.code_path_globs:
        return ()
    output = _run(
        command=(
            "git",
            "log",
            branch,
            f"--pretty=format:{GIT_LOG_FORMAT}",
            f"--max-count={FACTS_COMMIT_LIMIT}",
            PATHSPEC_SEPARATOR,
            *project.code_path_globs,
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


def get_significant_terms_from_text(*, text: str) -> frozenset[str]:
    """The words in a title specific enough to name a project.

    A conventional-commit type appears in nearly every title, so leaving `refactor`
    in makes every refactor read as work on the Access Engine Refactor.
    """
    words = re.findall(r"[a-z0-9]+", text.lower())
    return frozenset(
        word
        for word in words
        if len(word) >= FACTS_MIN_TITLE_TERM_LENGTH and word not in CONVENTIONAL_COMMIT_TYPES
    )


def get_title_terms_from_project(*, project: Project) -> frozenset[str]:
    """The words a pull-request title must share with the project to count as its work."""
    if project.title_terms:
        return frozenset(term.lower() for term in project.title_terms)
    return get_significant_terms_from_text(text=f"{project.slug} {project.name}")


def get_changed_paths_from_entry(*, entry: dict) -> tuple[str, ...]:
    """The repository-relative paths a pull request changed."""
    listed = entry.get(FILES_FIELD)
    if not isinstance(listed, list):
        return ()
    return tuple(
        str(changed[FILE_PATH_KEY])
        for changed in listed
        if isinstance(changed, dict) and FILE_PATH_KEY in changed
    )


def check_touches_code_paths(*, entry: dict, globs: tuple[str, ...]) -> bool:
    """Whether the pull request changed a file the project claims as its own."""
    return any(
        fnmatch(path, glob) for path in get_changed_paths_from_entry(entry=entry) for glob in globs
    )


def is_relevant(*, entry: dict, project: Project) -> bool:
    """Whether a pull request plausibly belongs to this project.

    One repository holds several projects, so every merged pull request would
    otherwise read as undocumented work on all of them. A project that declares its
    code paths is judged on those alone: which files a change touched is direct
    evidence where a shared title word is a guess.
    """
    head = str(entry.get(HEAD_REF_FIELD, ""))
    if any(head.startswith(prefix) for prefix in project.branch_prefixes):
        return True
    if project.code_path_globs:
        return check_touches_code_paths(entry=entry, globs=project.code_path_globs)
    title_terms = get_significant_terms_from_text(text=str(entry.get("title", "")))
    return bool(title_terms & get_title_terms_from_project(project=project))


def _listed_pull_requests(*, command: tuple[str, ...]) -> tuple[dict, ...]:
    output = _run(command=command)
    if output is None:
        return ()
    try:
        listed = json.loads(output)
    except json.JSONDecodeError:
        return ()
    return tuple(entry for entry in listed if isinstance(entry, dict))


def _list_command(*, repo: str, limit: int, author: str | None) -> tuple[str, ...]:
    author_arguments = ("--author", author) if author is not None else ()
    return (
        GITHUB_CLI_PATH,
        "pr",
        "list",
        "--repo",
        repo,
        "--state",
        "all",
        "--limit",
        str(limit),
        *author_arguments,
        "--json",
        PR_JSON_FIELDS,
    )


@lru_cache(maxsize=CACHED_PULL_REQUEST_QUERIES)
def _cached_pull_requests(*, repo: str, limit: int, author: str | None) -> tuple[dict, ...]:
    """One repository query, shared by every project that asks for it in this process.

    Several projects read the same repository on one sweep, and the query is the slow
    part. The cache lives for the process, so a sweep never asks twice and the next
    sweep starts empty.
    """
    return _listed_pull_requests(command=_list_command(repo=repo, limit=limit, author=author))


def get_entries_for_project(*, project: Project) -> tuple[dict, ...]:
    """Every pull request worth considering for this project, newest query first.

    Asking per author reaches weeks back for the handful of people whose work these
    documents track; the unfiltered query returns whatever was opened most recently,
    which in a busy repository is almost entirely still open.
    """
    repo = project.repos[0]
    if not project.authors:
        return _cached_pull_requests(repo=repo, limit=FACTS_PR_LIMIT, author=None)
    by_number: dict[object, dict] = {}
    for author in project.authors:
        for entry in _cached_pull_requests(
            repo=repo, limit=FACTS_AUTHOR_PR_LIMIT, author=author
        ):
            by_number.setdefault(entry.get("number"), entry)
    return tuple(by_number.values())


def observe_pull_requests(*, project: Project) -> tuple[Fact, ...]:
    """Recent pull requests for the project's first repository."""
    if not project.repos:
        return ()
    found = (
        _pr_fact(entry=entry, project_slug=project.slug)
        for entry in get_entries_for_project(project=project)
        if is_relevant(entry=entry, project=project)
    )
    return tuple(fact for fact in found if fact is not None)
