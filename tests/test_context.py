"""Session attachment and the context payload."""

from __future__ import annotations

from pathlib import Path

import pytest

from spine.constants import MAX_AUTO_ATTACH_PROJECTS, SPINE_HOME_ENV_VAR
from spine.context.attach import _best_matches
from spine.context.render import always_read, render_context, render_project
from spine.model import Doc, DocKind, Project, ProjectMatch, ReadWhen

PROJECT_SLUG = "alpha"


@pytest.fixture(autouse=True)
def isolated_spine_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SPINE_HOME_ENV_VAR, str(tmp_path))


def _project(*, slug: str) -> Project:
    return Project(slug=slug, name=slug.upper(), docs_dir=Path(f"/tmp/{slug}"))


def _match(*, slug: str, confidence: float) -> ProjectMatch:
    return ProjectMatch(project=_project(slug=slug), confidence=confidence, evidence=("x",))


def _doc(
    *,
    stem: str,
    read_when: ReadWhen = ReadWhen.EVERY_TIME,
    body: str = "# T\n\nProse.",
    parent: str | None = None,
) -> Doc:
    return Doc(
        doc_id=f"{PROJECT_SLUG}:{stem}",
        path=Path(f"{stem}.md"),
        kind=DocKind.BRIEF,
        read_when=read_when,
        title=stem,
        body=body,
        project_slug=PROJECT_SLUG,
        parent_doc_id=parent,
    )


def test_the_strongest_match_wins() -> None:
    matches = (_match(slug="strong", confidence=0.9), _match(slug="weak", confidence=0.6))
    assert [m.project.slug for m in _best_matches(matches=matches)] == ["strong"]


def test_near_ties_both_attach() -> None:
    matches = (_match(slug="one", confidence=0.80), _match(slug="two", confidence=0.78))
    assert len(_best_matches(matches=matches)) == 2


def test_too_many_ties_attach_nothing() -> None:
    matches = tuple(
        _match(slug=f"p{index}", confidence=0.6)
        for index in range(MAX_AUTO_ATTACH_PROJECTS + 1)
    )
    assert _best_matches(matches=matches) == ()


def test_nothing_below_the_threshold_attaches() -> None:
    assert _best_matches(matches=(_match(slug="faint", confidence=0.1),)) == ()


def test_only_the_every_time_group_is_always_read() -> None:
    docs = (_doc(stem="hub"), _doc(stem="area", read_when=ReadWhen.IN_AREA))
    assert [doc.doc_id for doc in always_read(docs=docs)] == [f"{PROJECT_SLUG}:hub"]


def test_log_entries_are_never_always_read() -> None:
    entry = _doc(stem="log", parent=f"{PROJECT_SLUG}:log")
    assert always_read(docs=(entry,)) == ()


def test_small_documents_survive_a_tight_budget() -> None:
    small = _doc(stem="small", body="# S\n\nShort.")
    large = _doc(stem="large", body="x\n" * 500)
    rendered = render_project(project=_project(slug=PROJECT_SLUG), docs=(large, small), budget=10)
    assert "small" in rendered
    assert "truncated" in rendered


def test_an_empty_project_renders_nothing() -> None:
    assert render_project(project=_project(slug=PROJECT_SLUG), docs=(), budget=100) == ""


def test_no_projects_render_an_empty_payload() -> None:
    assert render_context(rendered_projects=("", "  ")) == ""


def test_a_populated_payload_carries_the_header() -> None:
    assert render_context(rendered_projects=("## Project: X",)).startswith("# Project context")


def test_cli_exposes_the_context_subcommand() -> None:
    from spine.cli import build_parser

    parsed = build_parser().parse_args(["context", "--cwd", "/tmp"])
    assert parsed.handler is not None
