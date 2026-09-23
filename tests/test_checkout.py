"""Remembering the project choice for a linked worktree."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from spine.constants import SPINE_HOME_ENV_VAR
from spine.session.checkout import (
    FileCheckoutStore,
    linked_worktree_root,
    recall_choice,
    remember_choice,
)

PRIMARY_DIR_NAME = "primary"
WORKTREE_DIR_NAME = "feature"
WORKTREE_BRANCH = "feature-branch"
PROJECT_SLUG = "alpha"
OTHER_PROJECT_SLUG = "beta"


@pytest.fixture(autouse=True)
def isolated_spine_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SPINE_HOME_ENV_VAR, str(tmp_path / "state"))


def _git(*arguments: str, cwd: Path) -> None:
    subprocess.run(("git", *arguments), cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def primary_checkout(tmp_path: Path) -> Path:
    """A repository with one commit, so a worktree can be cut from it."""
    root = tmp_path / PRIMARY_DIR_NAME
    root.mkdir()
    _git("init", "--quiet", cwd=root)
    _git("config", "user.email", "test@example.com", cwd=root)
    _git("config", "user.name", "Test", cwd=root)
    (root / "README.md").write_text("seed", encoding="utf-8")
    _git("add", "README.md", cwd=root)
    _git("commit", "--quiet", "-m", "seed", cwd=root)
    return root


@pytest.fixture
def linked_worktree(primary_checkout: Path, tmp_path: Path) -> Path:
    root = tmp_path / WORKTREE_DIR_NAME
    _git("worktree", "add", "-b", WORKTREE_BRANCH, str(root), cwd=primary_checkout)
    return root


def test_a_primary_checkout_is_not_a_worktree(primary_checkout: Path) -> None:
    assert linked_worktree_root(cwd=primary_checkout) is None


def test_a_linked_worktree_reports_its_root(linked_worktree: Path) -> None:
    assert linked_worktree_root(cwd=linked_worktree) == linked_worktree.resolve()


def test_a_directory_outside_any_repository_is_not_a_worktree(tmp_path: Path) -> None:
    loose = tmp_path / "loose"
    loose.mkdir()
    assert linked_worktree_root(cwd=loose) is None


def test_a_choice_made_in_a_worktree_is_recalled(linked_worktree: Path) -> None:
    assert remember_choice(cwd=linked_worktree, project_slugs=(PROJECT_SLUG,)) is not None
    recalled = recall_choice(cwd=linked_worktree)
    assert recalled is not None
    assert recalled.project_slugs == (PROJECT_SLUG,)


def test_a_choice_made_in_a_primary_checkout_is_not_remembered(primary_checkout: Path) -> None:
    assert remember_choice(cwd=primary_checkout, project_slugs=(PROJECT_SLUG,)) is None
    assert recall_choice(cwd=primary_checkout) is None


def test_two_worktrees_remember_different_projects(
    primary_checkout: Path, linked_worktree: Path, tmp_path: Path
) -> None:
    second = tmp_path / "second"
    _git("worktree", "add", "-b", "second-branch", str(second), cwd=primary_checkout)
    remember_choice(cwd=linked_worktree, project_slugs=(PROJECT_SLUG,))
    remember_choice(cwd=second, project_slugs=(OTHER_PROJECT_SLUG,))

    first_recalled = recall_choice(cwd=linked_worktree)
    second_recalled = recall_choice(cwd=second)
    assert first_recalled is not None and second_recalled is not None
    assert first_recalled.project_slugs == (PROJECT_SLUG,)
    assert second_recalled.project_slugs == (OTHER_PROJECT_SLUG,)


def test_forgetting_a_worktree_stops_the_recall(linked_worktree: Path) -> None:
    remember_choice(cwd=linked_worktree, project_slugs=(PROJECT_SLUG,))
    root = linked_worktree_root(cwd=linked_worktree)
    assert root is not None
    assert FileCheckoutStore().clear(root=root) is True
    assert recall_choice(cwd=linked_worktree) is None


def test_an_empty_choice_is_not_remembered(linked_worktree: Path) -> None:
    assert remember_choice(cwd=linked_worktree, project_slugs=()) is None
    assert recall_choice(cwd=linked_worktree) is None


def test_a_corrupt_state_file_reads_as_no_choice(linked_worktree: Path) -> None:
    remember_choice(cwd=linked_worktree, project_slugs=(PROJECT_SLUG,))
    root = linked_worktree_root(cwd=linked_worktree)
    assert root is not None
    from spine.session.checkout import checkout_path

    checkout_path(root=root).write_text("{ not json", encoding="utf-8")
    assert recall_choice(cwd=linked_worktree) is None


def test_the_session_stamp_outranks_the_worktree_choice(
    linked_worktree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stamp is an answer for this session; the worktree choice is only a default."""
    from datetime import UTC, datetime

    from spine.context.attach import CHECKOUT_SOURCE, STAMP_SOURCE, attach
    from spine.model import Project, SessionStamp
    from spine.session import FileSessionStore

    registry = {
        PROJECT_SLUG: Project(
            slug=PROJECT_SLUG, name="Alpha", docs_dir=linked_worktree
        ),
        OTHER_PROJECT_SLUG: Project(
            slug=OTHER_PROJECT_SLUG, name="Beta", docs_dir=linked_worktree
        ),
    }
    monkeypatch.setattr("spine.registry.load_registry", lambda: registry)
    remember_choice(cwd=linked_worktree, project_slugs=(PROJECT_SLUG,))

    remembered = attach(cwd=linked_worktree, session_id=None)
    assert remembered.source == CHECKOUT_SOURCE
    assert tuple(project.slug for project in remembered.projects) == (PROJECT_SLUG,)

    session_id = "session-1"
    FileSessionStore().write(
        stamp=SessionStamp(
            session_id=session_id,
            project_slugs=(OTHER_PROJECT_SLUG,),
            started_at=datetime.now(tz=UTC),
        )
    )
    stamped = attach(cwd=linked_worktree, session_id=session_id)
    assert stamped.source == STAMP_SOURCE
    assert tuple(project.slug for project in stamped.projects) == (OTHER_PROJECT_SLUG,)


def test_the_ambiguity_prompt_says_the_choice_sticks_for_a_worktree() -> None:
    from spine.context.render import (
        AMBIGUITY_STAMP_HINT,
        AMBIGUITY_WORKTREE_HINT,
        render_ambiguity,
    )
    from spine.model import Project

    candidates = tuple(
        Project(slug=slug, name=slug.upper(), docs_dir=Path(f"/tmp/{slug}"))
        for slug in (PROJECT_SLUG, OTHER_PROJECT_SLUG)
    )
    assert AMBIGUITY_WORKTREE_HINT in render_ambiguity(
        projects=candidates, is_worktree=True
    )
    assert AMBIGUITY_STAMP_HINT in render_ambiguity(
        projects=candidates, is_worktree=False
    )
