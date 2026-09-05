"""Session stamp round-trips, fallbacks, and failure modes."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from spine.constants import SPINE_PROJECT_ENV_VAR, SPINE_SESSION_ID_ENV_VAR, SPINE_HOME_ENV_VAR
from spine.model import SessionStamp
from spine.session import resolve_stamp
from spine.session.stamp import (
    FileSessionStore,
    MalformedStampError,
    stamp_from_environment,
    stamp_path,
)

SESSION_ID = "session-alpha"
PROJECT_SLUG = "orbital-relay"
SECOND_PROJECT_SLUG = "ground-net"


@pytest.fixture(autouse=True)
def isolated_spine_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(SPINE_HOME_ENV_VAR, str(tmp_path))
    monkeypatch.delenv(SPINE_SESSION_ID_ENV_VAR, raising=False)
    monkeypatch.delenv(SPINE_PROJECT_ENV_VAR, raising=False)
    return tmp_path


def _stamp(*, slugs: tuple[str, ...] = (PROJECT_SLUG,)) -> SessionStamp:
    return SessionStamp(
        session_id=SESSION_ID,
        project_slugs=slugs,
        started_at=datetime.now(tz=UTC),
        intent="wire the allocator",
    )


def test_missing_stamp_reads_as_none() -> None:
    assert FileSessionStore().read(session_id=SESSION_ID) is None


def test_write_then_read_round_trips() -> None:
    store = FileSessionStore()
    store.write(stamp=_stamp())
    loaded = store.read(session_id=SESSION_ID)
    assert loaded is not None
    assert loaded.session_id == SESSION_ID
    assert loaded.project_slugs == (PROJECT_SLUG,)
    assert loaded.intent == "wire the allocator"


def test_a_session_may_attach_to_several_projects() -> None:
    store = FileSessionStore()
    store.write(stamp=_stamp(slugs=(PROJECT_SLUG, SECOND_PROJECT_SLUG)))
    loaded = store.read(session_id=SESSION_ID)
    assert loaded is not None
    assert loaded.project_slugs == (PROJECT_SLUG, SECOND_PROJECT_SLUG)


def test_write_leaves_no_partial_file() -> None:
    store = FileSessionStore()
    store.write(stamp=_stamp())
    leftovers = list(stamp_path(session_id=SESSION_ID).parent.glob("*.partial"))
    assert leftovers == []


def test_malformed_stamp_raises_rather_than_returning_none() -> None:
    store = FileSessionStore()
    store.write(stamp=_stamp())
    stamp_path(session_id=SESSION_ID).write_text("{not json", encoding="utf-8")
    with pytest.raises(MalformedStampError):
        store.read(session_id=SESSION_ID)


def test_stamp_missing_a_required_field_raises() -> None:
    store = FileSessionStore()
    store.write(stamp=_stamp())
    stamp_path(session_id=SESSION_ID).write_text('{"session_id": "x"}', encoding="utf-8")
    with pytest.raises(MalformedStampError):
        store.read(session_id=SESSION_ID)


def test_clear_reports_whether_anything_was_removed() -> None:
    store = FileSessionStore()
    assert store.clear(session_id=SESSION_ID) is False
    store.write(stamp=_stamp())
    assert store.clear(session_id=SESSION_ID) is True
    assert store.read(session_id=SESSION_ID) is None


def test_environment_fallback_needs_both_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SPINE_SESSION_ID_ENV_VAR, SESSION_ID)
    assert stamp_from_environment() is None
    monkeypatch.setenv(SPINE_PROJECT_ENV_VAR, PROJECT_SLUG)
    from_env = stamp_from_environment()
    assert from_env is not None
    assert from_env.project_slugs == (PROJECT_SLUG,)
    assert from_env.source == "environment"


def test_environment_fallback_splits_several_projects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SPINE_SESSION_ID_ENV_VAR, SESSION_ID)
    monkeypatch.setenv(SPINE_PROJECT_ENV_VAR, f"{PROJECT_SLUG}, {SECOND_PROJECT_SLUG}")
    from_env = stamp_from_environment()
    assert from_env is not None
    assert from_env.project_slugs == (PROJECT_SLUG, SECOND_PROJECT_SLUG)


def test_written_stamp_wins_over_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SPINE_SESSION_ID_ENV_VAR, SESSION_ID)
    monkeypatch.setenv(SPINE_PROJECT_ENV_VAR, SECOND_PROJECT_SLUG)
    FileSessionStore().write(stamp=_stamp())
    resolved = resolve_stamp(session_id=SESSION_ID)
    assert resolved is not None
    assert resolved.project_slugs == (PROJECT_SLUG,)
    assert resolved.source == "stamp"


def test_resolve_falls_back_when_nothing_written(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SPINE_SESSION_ID_ENV_VAR, SESSION_ID)
    monkeypatch.setenv(SPINE_PROJECT_ENV_VAR, SECOND_PROJECT_SLUG)
    resolved = resolve_stamp(session_id=SESSION_ID)
    assert resolved is not None
    assert resolved.source == "environment"


def test_resolve_returns_none_with_no_stamp_and_no_environment() -> None:
    assert resolve_stamp(session_id=SESSION_ID) is None


def test_cli_exposes_the_session_subcommand() -> None:
    from spine.cli import build_parser

    parsed = build_parser().parse_args(["session", "show", "--session", SESSION_ID])
    assert parsed.handler is not None
