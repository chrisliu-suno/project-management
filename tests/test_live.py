"""Session declarations, steering, broadcasts, and leases."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from spine.constants import SESSION_STALE_SECONDS, SPINE_HOME_ENV_VAR
from spine.live.model import SessionState, SteeringAction
from spine.live.store import LiveStore

FIRST_SESSION = "session-one"
SECOND_SESSION = "session-two"
PROJECT_SLUG = "alpha"
LEASE_SUBJECT = "decision:ttl"


@pytest.fixture(autouse=True)
def isolated_spine_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SPINE_HOME_ENV_VAR, str(tmp_path))


@pytest.fixture
def store() -> LiveStore:
    return LiveStore()


def test_a_session_declares_what_it_is_doing(store: LiveStore) -> None:
    declared = store.declare(
        session_id=FIRST_SESSION, project_slugs=(PROJECT_SLUG,), intent="fix the leak"
    )
    assert declared.intent == "fix the leak"
    assert declared.state is SessionState.WORKING


def test_redeclaring_keeps_the_original_start_time(store: LiveStore) -> None:
    first = store.declare(session_id=FIRST_SESSION, project_slugs=(), intent="one")
    second = store.declare(session_id=FIRST_SESSION, project_slugs=(), intent="two")
    assert second.started_at == first.started_at
    assert second.intent == "two"


def test_each_session_writes_only_its_own_line(store: LiveStore) -> None:
    store.declare(session_id=FIRST_SESSION, project_slugs=(), intent="one")
    store.declare(session_id=SECOND_SESSION, project_slugs=(), intent="two")
    assert len(store.live_sessions()) == 2


def test_declared_paths_round_trip(store: LiveStore) -> None:
    store.declare(
        session_id=FIRST_SESSION,
        project_slugs=(),
        intent="x",
        declared_paths=("a/b", "c/d"),
    )
    assert store.live_sessions()[0].declared_paths == ("a/b", "c/d")


def test_a_stale_session_drops_out_of_the_live_list(store: LiveStore) -> None:
    store.declare(session_id=FIRST_SESSION, project_slugs=(), intent="old")
    stale = (datetime.now(tz=UTC) - timedelta(seconds=SESSION_STALE_SECONDS * 2)).isoformat()
    with store._connect() as connection:
        connection.execute(
            "UPDATE live_sessions SET updated_at = ? WHERE session_id = ?",
            (stale, FIRST_SESSION),
        )
    assert store.live_sessions() == ()
    assert len(store.live_sessions(include_stale=True)) == 1


def test_steering_is_delivered_once(store: LiveStore) -> None:
    store.steer(session_id=FIRST_SESSION, action=SteeringAction.REDIRECT, body="go left")
    assert len(store.drain_steering(session_id=FIRST_SESSION)) == 1
    assert store.drain_steering(session_id=FIRST_SESSION) == ()


def test_steering_reaches_only_its_session(store: LiveStore) -> None:
    store.steer(session_id=FIRST_SESSION, action=SteeringAction.STOP)
    assert store.drain_steering(session_id=SECOND_SESSION) == ()


def test_several_instructions_arrive_in_order(store: LiveStore) -> None:
    store.steer(session_id=FIRST_SESSION, action=SteeringAction.PAUSE)
    store.steer(session_id=FIRST_SESSION, action=SteeringAction.RESUME)
    actions = [message.action for message in store.drain_steering(session_id=FIRST_SESSION)]
    assert actions == [SteeringAction.PAUSE, SteeringAction.RESUME]


def test_a_broadcast_reaches_its_project(store: LiveStore) -> None:
    store.broadcast(
        project_slug=PROJECT_SLUG,
        headline="rule discovered",
        body="never hardcode a deny",
        origin_session_id=FIRST_SESSION,
    )
    assert store.broadcasts_for(project_slug=PROJECT_SLUG)[0].headline == "rule discovered"


def test_a_broadcast_stays_on_its_own_project(store: LiveStore) -> None:
    store.broadcast(
        project_slug=PROJECT_SLUG, headline="x", body="", origin_session_id=FIRST_SESSION
    )
    assert store.broadcasts_for(project_slug="other") == ()


def test_a_lease_is_exclusive(store: LiveStore) -> None:
    assert store.acquire_lease(subject=LEASE_SUBJECT, session_id=FIRST_SESSION) is True
    assert store.acquire_lease(subject=LEASE_SUBJECT, session_id=SECOND_SESSION) is False


def test_the_holder_can_reacquire_its_own_lease(store: LiveStore) -> None:
    store.acquire_lease(subject=LEASE_SUBJECT, session_id=FIRST_SESSION)
    assert store.acquire_lease(subject=LEASE_SUBJECT, session_id=FIRST_SESSION) is True


def test_an_expired_lease_is_reclaimable(store: LiveStore) -> None:
    store.acquire_lease(subject=LEASE_SUBJECT, session_id=FIRST_SESSION)
    past = (datetime.now(tz=UTC) - timedelta(seconds=1)).isoformat()
    with store._connect() as connection:
        connection.execute(
            "UPDATE leases SET expires_at = ? WHERE subject = ?", (past, LEASE_SUBJECT)
        )
    assert store.lease_holder(subject=LEASE_SUBJECT) is None
    assert store.acquire_lease(subject=LEASE_SUBJECT, session_id=SECOND_SESSION) is True


def test_releasing_a_lease_you_do_not_hold_changes_nothing(store: LiveStore) -> None:
    store.acquire_lease(subject=LEASE_SUBJECT, session_id=FIRST_SESSION)
    assert store.release_lease(subject=LEASE_SUBJECT, session_id=SECOND_SESSION) is False
    assert store.lease_holder(subject=LEASE_SUBJECT) == FIRST_SESSION


def test_releasing_frees_the_subject(store: LiveStore) -> None:
    store.acquire_lease(subject=LEASE_SUBJECT, session_id=FIRST_SESSION)
    assert store.release_lease(subject=LEASE_SUBJECT, session_id=FIRST_SESSION) is True
    assert store.acquire_lease(subject=LEASE_SUBJECT, session_id=SECOND_SESSION) is True


def test_cli_exposes_the_live_subcommand() -> None:
    from spine.cli import build_parser

    parsed = build_parser().parse_args(["live", "list"])
    assert parsed.handler is not None
