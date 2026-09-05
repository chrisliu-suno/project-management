"""Maps a session's signals to the projects it belongs to."""

from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path

from ..constants import (
    BRANCH_PREFIX_MATCH_CONFIDENCE,
    EXACT_MATCH_CONFIDENCE,
    NO_MATCH_CONFIDENCE,
    PATH_GLOB_MATCH_CONFIDENCE,
    PROMPT_MENTION_CONFIDENCE,
    REPO_MATCH_CONFIDENCE,
)
from ..model import Project, ProjectMatch
from ..ports import ProjectRegistry

Signal = tuple[float, str]


class SignalResolver:
    """Scores every known project against a session's signals. Deterministic, no model call."""

    def __init__(self, *, registry: ProjectRegistry) -> None:
        self._registry = registry

    def resolve(
        self,
        *,
        cwd: Path,
        branch: str | None = None,
        repo: str | None = None,
        opening_prompt: str | None = None,
    ) -> tuple[ProjectMatch, ...]:
        """All projects scoring above no-match, strongest first. Empty means no project."""
        matches: list[ProjectMatch] = []
        for project in self._registry.all_projects():
            match = _score_project(
                project=project,
                cwd=cwd,
                branch=branch,
                repo=repo,
                opening_prompt=opening_prompt,
            )
            if match is not None:
                matches.append(match)
        return tuple(sorted(matches, key=lambda found: (-found.confidence, found.project.slug)))


def _score_project(
    *,
    project: Project,
    cwd: Path,
    branch: str | None,
    repo: str | None,
    opening_prompt: str | None,
) -> ProjectMatch | None:
    signals = [
        *_repo_signals(project=project, repo=repo),
        *_path_signals(project=project, cwd=cwd),
        *_branch_signals(project=project, branch=branch),
        *_prompt_signals(project=project, opening_prompt=opening_prompt),
    ]
    confidence = combine_signal_weights(weights=tuple(weight for weight, _ in signals))
    if confidence <= NO_MATCH_CONFIDENCE:
        return None
    return ProjectMatch(
        project=project,
        confidence=confidence,
        evidence=tuple(description for _, description in signals),
    )


def combine_signal_weights(*, weights: tuple[float, ...]) -> float:
    """Combine independent signal weights so more evidence always ranks higher.

    Summing then clamping made three matching signals indistinguishable from two
    that already reached the ceiling.
    """
    remaining_doubt = EXACT_MATCH_CONFIDENCE
    for weight in weights:
        remaining_doubt *= EXACT_MATCH_CONFIDENCE - weight
    return EXACT_MATCH_CONFIDENCE - remaining_doubt


def _repo_signals(*, project: Project, repo: str | None) -> list[Signal]:
    if repo is None:
        return []
    return [(REPO_MATCH_CONFIDENCE, f"repo {known}") for known in project.repos if known == repo]


def _path_signals(*, project: Project, cwd: Path) -> list[Signal]:
    """A glob matches the working directory itself or any ancestor of it."""
    expanded = cwd.expanduser()
    candidates = (expanded, *expanded.parents)
    signals: list[Signal] = []
    for glob in project.path_globs:
        pattern = str(Path(glob).expanduser())
        if any(fnmatchcase(str(candidate), pattern) for candidate in candidates):
            signals.append((PATH_GLOB_MATCH_CONFIDENCE, f"path glob {glob}"))
    return signals


def _branch_signals(*, project: Project, branch: str | None) -> list[Signal]:
    if branch is None:
        return []
    return [
        (BRANCH_PREFIX_MATCH_CONFIDENCE, f"branch prefix {prefix}")
        for prefix in project.branch_prefixes
        if branch.startswith(prefix)
    ]


def _prompt_signals(*, project: Project, opening_prompt: str | None) -> list[Signal]:
    """The opening prompt naming the project by slug or display name is weak corroboration."""
    if not opening_prompt:
        return []
    lowered = opening_prompt.lower()
    mentioned = [token for token in (project.slug, project.name) if token.lower() in lowered]
    if not mentioned:
        return []
    return [(PROMPT_MENTION_CONFIDENCE, f'prompt mentions "{mentioned[0]}"')]
