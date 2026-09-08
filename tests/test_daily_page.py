"""Session collisions and logged decisions awaiting review."""

from __future__ import annotations

from pathlib import Path

import pytest

from spine.constants import SPINE_HOME_ENV_VAR
from spine.decisions.store import DecisionStore, decision_entries
from spine.live.collisions import collisions_among, paths_overlap
from spine.live.model import LiveSession, SessionState
from spine.model import Doc, DocKind, ReadWhen

PROJECT_SLUG = "alpha"
STAMP = "2026-09-08T00:00:00+00:00"


@pytest.fixture(autouse=True)
def isolated_spine_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SPINE_HOME_ENV_VAR, str(tmp_path))


def _session(
    *, session_id: str, paths: tuple[str, ...], state: SessionState = SessionState.WORKING
) -> LiveSession:
    return LiveSession(
        session_id=session_id,
        project_slugs=(PROJECT_SLUG,),
        intent=f"{session_id} work",
        state=state,
        declared_paths=paths,
        updated_at=STAMP,
        started_at=STAMP,
    )


def test_a_path_contained_by_another_overlaps() -> None:
    assert paths_overlap(left="studio_api/dsar", right="studio_api/dsar/views.py")


def test_sibling_paths_do_not_overlap() -> None:
    assert not paths_overlap(left="studio_api/dsar", right="studio_api/admin")


def test_an_empty_path_never_overlaps() -> None:
    assert not paths_overlap(left="", right="studio_api")


def test_two_sessions_on_the_same_tree_collide() -> None:
    sessions = (
        _session(session_id="a", paths=("studio_api/dsar",)),
        _session(session_id="b", paths=("studio_api/dsar/exports.py",)),
    )
    found = collisions_among(sessions=sessions)
    assert len(found) == 1
    assert found[0].path == "studio_api/dsar/exports.py"


def test_sessions_on_different_trees_do_not_collide() -> None:
    sessions = (
        _session(session_id="a", paths=("studio_api/dsar",)),
        _session(session_id="b", paths=("frontend/",)),
    )
    assert collisions_among(sessions=sessions) == ()


def test_a_paused_session_does_not_collide() -> None:
    sessions = (
        _session(session_id="a", paths=("studio_api/dsar",)),
        _session(session_id="b", paths=("studio_api/dsar",), state=SessionState.PAUSED),
    )
    assert collisions_among(sessions=sessions) == ()


def test_sessions_on_different_projects_do_not_collide() -> None:
    left = _session(session_id="a", paths=("shared/",))
    right = LiveSession(
        session_id="b",
        project_slugs=("beta",),
        intent="other",
        state=SessionState.WORKING,
        declared_paths=("shared/",),
        updated_at=STAMP,
        started_at=STAMP,
    )
    assert collisions_among(sessions=(left, right)) == ()


def test_one_session_collides_with_nobody() -> None:
    assert collisions_among(sessions=(_session(session_id="a", paths=("x/",)),)) == ()


def _log(*, stem: str = "decisions") -> Doc:
    return Doc(
        doc_id=f"{PROJECT_SLUG}:{stem}",
        path=Path(f"{stem}.md"),
        kind=DocKind.DECISION_LOG,
        read_when=ReadWhen.LOG,
        title=stem,
        body="# Log",
        project_slug=PROJECT_SLUG,
    )


def _entry(*, slug: str, parent: str) -> Doc:
    return Doc(
        doc_id=f"{PROJECT_SLUG}:{parent}#{slug}",
        path=Path(f"{parent}.md"),
        kind=DocKind.DECISION_LOG,
        read_when=ReadWhen.LOG,
        title=f"Decision {slug}",
        body="prose",
        project_slug=PROJECT_SLUG,
        parent_doc_id=f"{PROJECT_SLUG}:{parent}",
    )


def test_only_entries_inside_a_decision_log_are_decisions() -> None:
    docs = (_log(), _entry(slug="one", parent="decisions"))
    assert len(decision_entries(docs=docs)) == 1


def test_an_entry_of_another_document_is_not_a_decision() -> None:
    docs = (_log(), _entry(slug="one", parent="somewhere-else"))
    assert decision_entries(docs=docs) == ()


def test_a_recorded_decision_is_pending_until_acknowledged() -> None:
    store = DecisionStore()
    store.record(project_slug=PROJECT_SLUG, entries=(_entry(slug="one", parent="decisions"),))
    assert len(store.pending()) == 1


def test_recording_the_same_decision_twice_registers_it_once() -> None:
    store = DecisionStore()
    entries = (_entry(slug="one", parent="decisions"),)
    store.record(project_slug=PROJECT_SLUG, entries=entries)
    assert store.record(project_slug=PROJECT_SLUG, entries=entries) == 0
    assert len(store.pending()) == 1


def test_acknowledging_removes_it_from_pending() -> None:
    store = DecisionStore()
    entry = _entry(slug="one", parent="decisions")
    store.record(project_slug=PROJECT_SLUG, entries=(entry,))
    assert store.acknowledge(entry_id=entry.doc_id) is True
    assert store.pending() == ()


def test_acknowledging_twice_is_refused() -> None:
    store = DecisionStore()
    entry = _entry(slug="one", parent="decisions")
    store.record(project_slug=PROJECT_SLUG, entries=(entry,))
    store.acknowledge(entry_id=entry.doc_id)
    assert store.acknowledge(entry_id=entry.doc_id) is False


def test_acknowledging_an_unknown_decision_is_refused() -> None:
    assert DecisionStore().acknowledge(entry_id="nope") is False


def test_pending_can_be_filtered_to_one_project() -> None:
    store = DecisionStore()
    store.record(project_slug=PROJECT_SLUG, entries=(_entry(slug="one", parent="decisions"),))
    assert store.pending(project_slug="beta") == ()


def test_cli_exposes_the_decisions_subcommand() -> None:
    from spine.cli import build_parser

    assert build_parser().parse_args(["decisions", "list"]).handler is not None


def test_the_page_renders_both_new_surfaces() -> None:
    from spine.serve.page import render_page

    page = render_page()
    assert "Decisions logged" in page
    assert "Sessions colliding" in page


def test_acknowledging_over_get_is_refused() -> None:
    from spine.serve.server import ACK_PATH, MUTATING_PATHS

    assert ACK_PATH in MUTATING_PATHS
