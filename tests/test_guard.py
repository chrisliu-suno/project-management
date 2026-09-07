"""Boundary checks and steering application."""

from __future__ import annotations

from pathlib import Path

import pytest

from spine.constants import SPINE_HOME_ENV_VAR
from spine.guard import apply_steering
from spine.guard.checks import check_edit, check_publish
from spine.live.model import LiveSession, SessionState, SteeringAction
from spine.live.store import LiveStore, now_iso

SESSION_ID = "session-one"
PROJECT_SLUG = "alpha"


@pytest.fixture(autouse=True)
def isolated_spine_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SPINE_HOME_ENV_VAR, str(tmp_path))


def _session(
    *,
    intent: str = "fix the resolver",
    state: SessionState = SessionState.WORKING,
    paths: tuple[str, ...] = (),
    slugs: tuple[str, ...] = (PROJECT_SLUG,),
) -> LiveSession:
    stamp = now_iso()
    return LiveSession(
        session_id=SESSION_ID,
        project_slugs=slugs,
        intent=intent,
        state=state,
        declared_paths=paths,
        started_at=stamp,
        updated_at=stamp,
    )


def test_an_undeclared_session_is_warned_not_blocked() -> None:
    verdict = check_edit(session=None, path="a/b.py")
    assert verdict.is_allowed is True
    assert verdict.has_message is True


def test_a_blank_intent_counts_as_undeclared() -> None:
    assert check_edit(session=_session(intent="   "), path="a/b.py").has_message is True


def test_an_edit_with_no_declared_paths_passes_quietly() -> None:
    verdict = check_edit(session=_session(), path="anywhere/at/all.py")
    assert verdict.is_allowed is True
    assert verdict.has_message is False


def test_an_edit_inside_a_declared_path_passes_quietly() -> None:
    verdict = check_edit(session=_session(paths=("studio_api/access",)), path="studio_api/access/r.py")
    assert verdict.has_message is False


def test_an_edit_exactly_at_a_declared_path_passes() -> None:
    verdict = check_edit(session=_session(paths=("studio_api/access.py",)), path="studio_api/access.py")
    assert verdict.has_message is False


def test_an_edit_outside_the_declared_paths_is_flagged() -> None:
    verdict = check_edit(session=_session(paths=("studio_api/access",)), path="frontend/App.tsx")
    assert verdict.is_allowed is True
    assert "outside" in verdict.message


def test_a_sibling_prefix_does_not_count_as_inside() -> None:
    verdict = check_edit(session=_session(paths=("studio_api/access",)), path="studio_api/accessories/x.py")
    assert "outside" in verdict.message


def test_a_paused_session_cannot_edit() -> None:
    assert check_edit(session=_session(state=SessionState.PAUSED), path="a.py").is_allowed is False


def test_a_stopped_session_cannot_edit() -> None:
    assert check_edit(session=_session(state=SessionState.STOPPED), path="a.py").is_allowed is False


def test_publishing_without_a_project_is_flagged() -> None:
    verdict = check_publish(session=_session(slugs=()))
    assert verdict.is_allowed is True
    assert verdict.has_message is True


def test_publishing_with_a_project_passes_quietly() -> None:
    assert check_publish(session=_session()).has_message is False


def test_a_stopped_session_cannot_publish() -> None:
    assert check_publish(session=_session(state=SessionState.STOPPED)).is_allowed is False


def test_no_steering_produces_no_lines() -> None:
    assert apply_steering(session_id=SESSION_ID) == ()


def test_a_stop_instruction_moves_the_session_to_stopped() -> None:
    store = LiveStore()
    store.declare(session_id=SESSION_ID, project_slugs=(PROJECT_SLUG,), intent="work")
    store.steer(session_id=SESSION_ID, action=SteeringAction.STOP, body="wrong approach")
    lines = apply_steering(session_id=SESSION_ID)
    assert lines and "stop" in lines[0]
    live = store.live_sessions(include_stale=True)[0]
    assert live.state is SessionState.STOPPED


def test_resume_returns_a_paused_session_to_working() -> None:
    store = LiveStore()
    store.declare(session_id=SESSION_ID, project_slugs=(), intent="work")
    store.steer(session_id=SESSION_ID, action=SteeringAction.PAUSE)
    apply_steering(session_id=SESSION_ID)
    store.steer(session_id=SESSION_ID, action=SteeringAction.RESUME)
    apply_steering(session_id=SESSION_ID)
    assert store.live_sessions(include_stale=True)[0].state is SessionState.WORKING


def test_a_redirect_leaves_the_state_alone() -> None:
    store = LiveStore()
    store.declare(session_id=SESSION_ID, project_slugs=(), intent="work")
    store.steer(session_id=SESSION_ID, action=SteeringAction.REDIRECT, body="do X first")
    apply_steering(session_id=SESSION_ID)
    assert store.live_sessions(include_stale=True)[0].state is SessionState.WORKING


def test_steering_is_applied_only_once() -> None:
    store = LiveStore()
    store.declare(session_id=SESSION_ID, project_slugs=(), intent="work")
    store.steer(session_id=SESSION_ID, action=SteeringAction.PAUSE)
    assert apply_steering(session_id=SESSION_ID) != ()
    assert apply_steering(session_id=SESSION_ID) == ()


def test_cli_exposes_the_guard_subcommand() -> None:
    from spine.cli import build_parser

    parsed = build_parser().parse_args(["guard", "edit", "--path", "a.py"])
    assert parsed.handler is not None
