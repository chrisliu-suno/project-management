"""Session attachment and the context payload."""

from __future__ import annotations

from pathlib import Path

import pytest

from spine.constants import MAX_AUTO_ATTACH_PROJECTS, SPINE_HOME_ENV_VAR
from spine.context.attach import _best_matches
from spine.context import task_context_for
from spine.context.render import (
    always_read,
    render_ambiguity,
    render_context,
    render_project,
    render_task_context,
)
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
    chosen, ambiguous = _best_matches(matches=matches)
    assert [found.project.slug for found in chosen] == ["strong"]
    assert ambiguous == ()


def test_near_ties_both_attach() -> None:
    matches = (_match(slug="one", confidence=0.80), _match(slug="two", confidence=0.78))
    chosen, ambiguous = _best_matches(matches=matches)
    assert len(chosen) == 2
    assert ambiguous == ()


def test_too_many_ties_attach_nothing_and_report_ambiguity() -> None:
    matches = tuple(
        _match(slug=f"p{index}", confidence=0.6)
        for index in range(MAX_AUTO_ATTACH_PROJECTS + 1)
    )
    chosen, ambiguous = _best_matches(matches=matches)
    assert chosen == ()
    assert len(ambiguous) == MAX_AUTO_ATTACH_PROJECTS + 1


def test_nothing_below_the_threshold_attaches() -> None:
    assert _best_matches(matches=(_match(slug="faint", confidence=0.1),)) == ((), ())


def test_ambiguity_prompt_offers_one_stamp_command_per_candidate() -> None:
    matches = tuple(
        _match(slug=f"p{index}", confidence=0.6)
        for index in range(MAX_AUTO_ATTACH_PROJECTS + 1)
    )
    _, ambiguous = _best_matches(matches=matches)
    prompt = render_ambiguity(projects=tuple(found.project for found in ambiguous))
    for found in ambiguous:
        assert f"spine session set --project {found.project.slug}" in prompt


def test_no_candidates_renders_no_ambiguity_prompt() -> None:
    assert render_ambiguity(projects=()) == ""


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


def test_cli_exposes_the_task_subcommand() -> None:
    from spine.cli import build_parser

    parsed = build_parser().parse_args(["context", "task", "--task", "close the leak"])
    assert parsed.handler is not None
    assert parsed.task == "close the leak"


def test_task_context_carries_every_chosen_document() -> None:
    chosen = (_doc(stem="hub"), _doc(stem="area", read_when=ReadWhen.IN_AREA))
    rendered = render_task_context(project=_project(slug=PROJECT_SLUG), docs=chosen)
    assert rendered.startswith(f"## {PROJECT_SLUG.upper()}")
    for doc in chosen:
        assert doc.doc_id in rendered


def test_a_selection_with_no_documents_renders_nothing() -> None:
    assert render_task_context(project=_project(slug=PROJECT_SLUG), docs=()) == ""


def test_a_blank_task_selects_nothing() -> None:
    assert task_context_for(cwd=Path("/tmp"), session_id="s-1", task="   ", budget=100) == ""


def test_a_session_without_an_id_selects_nothing() -> None:
    assert task_context_for(cwd=Path("/tmp"), session_id=None, task="real task", budget=100) == ""


def test_a_session_that_already_picked_does_not_pick_again(tmp_path: Path) -> None:
    from spine.picker.record import SqlitePickRecorder, has_pick_for_session
    from spine.model import Selection

    db_path = tmp_path / "picks.sqlite3"
    assert has_pick_for_session(session_id="s-1", db_path=db_path) is False
    SqlitePickRecorder(db_path=db_path).record(
        session_id="s-1",
        project_slug=PROJECT_SLUG,
        selection=Selection(chosen=(_doc(stem="hub"),)),
        confidence=1.0,
    )
    assert has_pick_for_session(session_id="s-1", db_path=db_path) is True
    assert has_pick_for_session(session_id="s-2", db_path=db_path) is False


def test_a_tied_session_is_recorded_so_its_cost_can_be_traced(tmp_path, monkeypatch) -> None:
    """A tied session picks nothing, so without this it leaves no trace at all."""
    from spine.constants import AMBIGUOUS_PICK_CONFIDENCE, PICK_REASON_AMBIGUOUS_INDEX
    from spine.context import record_attachment
    from spine.picker.record import SqlitePickRecorder

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    projects = (
        Project(slug="alpha", name="Alpha", docs_dir=tmp_path / "alpha"),
        Project(slug="beta", name="Beta", docs_dir=tmp_path / "beta"),
    )
    record_attachment(
        session_id="tied-1",
        projects=projects,
        confidence=AMBIGUOUS_PICK_CONFIDENCE,
        reason=PICK_REASON_AMBIGUOUS_INDEX,
    )

    import sqlite3

    rows = sqlite3.connect(SqlitePickRecorder().db_path).execute(
        "SELECT project_slug, confidence, reason FROM picks WHERE session_id = 'tied-1'"
        " ORDER BY project_slug"
    ).fetchall()
    assert [row[0] for row in rows] == ["alpha", "beta"]
    assert {row[1] for row in rows} == {0.0}
    assert {row[2] for row in rows} == {PICK_REASON_AMBIGUOUS_INDEX}


def test_a_session_with_no_id_records_nothing() -> None:
    """Recording under the placeholder id would attribute every anonymous session to one bucket."""
    from spine.constants import AMBIGUOUS_PICK_CONFIDENCE, PICK_REASON_AMBIGUOUS_INDEX
    from spine.context import record_attachment

    record_attachment(
        session_id=None,
        projects=(),
        confidence=AMBIGUOUS_PICK_CONFIDENCE,
        reason=PICK_REASON_AMBIGUOUS_INDEX,
    )


def test_an_attachment_row_does_not_count_as_a_task_pick(tmp_path: Path) -> None:
    """A session-start attachment must leave the task path free to choose documents."""
    from spine.constants import EXACT_MATCH_CONFIDENCE, PICK_REASON_ATTACHED
    from spine.model import Selection
    from spine.picker.record import SqlitePickRecorder, has_pick_for_session

    db_path = tmp_path / "picks.sqlite3"
    SqlitePickRecorder(db_path=db_path).record(
        session_id="s-1",
        project_slug=PROJECT_SLUG,
        selection=Selection(chosen=(), dropped=(), total_lines=0, reason=PICK_REASON_ATTACHED),
        confidence=EXACT_MATCH_CONFIDENCE,
    )
    assert has_pick_for_session(session_id="s-1", db_path=db_path) is False


def test_a_resolved_session_records_the_project_it_attached_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without this the project join only ever sees tied sessions."""
    import sqlite3

    import spine.context as context_module
    from spine.constants import PICK_REASON_ATTACHED
    from spine.context.attach import Attachment
    from spine.picker.record import SqlitePickRecorder

    docs_dir = tmp_path / "alpha-docs"
    docs_dir.mkdir()
    (docs_dir / "start-here.md").write_text("# Start here\n\nWhat this project is.\n")
    project = Project(slug=PROJECT_SLUG, name="Alpha", docs_dir=docs_dir)
    monkeypatch.setattr(
        context_module,
        "attach",
        lambda **_: Attachment(projects=(project,), source="inferred"),
    )

    context_module.context_for(cwd=tmp_path, session_id="resolved-1", budget=100)

    rows = (
        sqlite3.connect(SqlitePickRecorder().db_path)
        .execute(
            "SELECT project_slug, confidence, reason FROM picks WHERE session_id = 'resolved-1'"
        )
        .fetchall()
    )
    assert rows == [(PROJECT_SLUG, 1.0, PICK_REASON_ATTACHED)]
