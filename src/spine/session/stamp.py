"""Per-session project attachment, written at launch and read by the hooks."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from ..constants import (
    SPINE_PROJECT_ENV_VAR,
    SPINE_SESSION_ID_ENV_VAR,
)
from ..model import SessionStamp
from ..paths import ensure_spine_home, sessions_dir

STAMP_FILE_SUFFIX = ".json"
STAMP_ENCODING = "utf-8"
PROJECT_LIST_SEPARATOR = ","
SOURCE_STAMP = "stamp"
SOURCE_ENVIRONMENT = "environment"

FIELD_SESSION_ID = "session_id"
FIELD_PROJECT_SLUGS = "project_slugs"
FIELD_STARTED_AT = "started_at"
FIELD_INTENT = "intent"
FIELD_SOURCE = "source"


class MalformedStampError(ValueError):
    """A stamp file exists but cannot be read as one."""


def stamp_path(*, session_id: str) -> Path:
    return sessions_dir() / f"{session_id}{STAMP_FILE_SUFFIX}"


def _to_mapping(*, stamp: SessionStamp) -> dict[str, object]:
    return {
        FIELD_SESSION_ID: stamp.session_id,
        FIELD_PROJECT_SLUGS: list(stamp.project_slugs),
        FIELD_STARTED_AT: stamp.started_at.isoformat(),
        FIELD_INTENT: stamp.intent,
        FIELD_SOURCE: stamp.source,
    }


def _from_mapping(*, mapping: dict[str, object]) -> SessionStamp:
    raw_intent = mapping.get(FIELD_INTENT)
    try:
        raw_slugs = mapping[FIELD_PROJECT_SLUGS]
        if not isinstance(raw_slugs, list):
            raise TypeError(f"{FIELD_PROJECT_SLUGS} must be a list")
        return SessionStamp(
            session_id=str(mapping[FIELD_SESSION_ID]),
            project_slugs=tuple(str(slug) for slug in raw_slugs),
            started_at=datetime.fromisoformat(str(mapping[FIELD_STARTED_AT])),
            intent=None if raw_intent is None else str(raw_intent),
            source=str(mapping.get(FIELD_SOURCE, SOURCE_STAMP)),
        )
    except (KeyError, TypeError, ValueError) as cause:
        raise MalformedStampError(f"unreadable stamp: {cause}") from cause


class FileSessionStore:
    """Stores one JSON stamp per session so concurrent sessions never contend."""

    def read(self, *, session_id: str) -> SessionStamp | None:
        path = stamp_path(session_id=session_id)
        if not path.is_file():
            return None
        raw = path.read_text(encoding=STAMP_ENCODING)
        try:
            mapping = json.loads(raw)
        except json.JSONDecodeError as cause:
            raise MalformedStampError(f"invalid json in {path}: {cause}") from cause
        return _from_mapping(mapping=mapping)

    def write(self, *, stamp: SessionStamp) -> None:
        ensure_spine_home()
        path = stamp_path(session_id=stamp.session_id)
        payload = json.dumps(_to_mapping(stamp=stamp), indent=2, sort_keys=True)
        temporary = path.with_suffix(path.suffix + ".partial")
        temporary.write_text(payload, encoding=STAMP_ENCODING)
        temporary.replace(path)

    def clear(self, *, session_id: str) -> bool:
        path = stamp_path(session_id=session_id)
        if not path.is_file():
            return False
        path.unlink()
        return True


def stamp_from_environment() -> SessionStamp | None:
    """Build a stamp from the launch environment when no file has been written yet."""
    session_id = os.environ.get(SPINE_SESSION_ID_ENV_VAR)
    project_value = os.environ.get(SPINE_PROJECT_ENV_VAR)
    if not session_id or not project_value:
        return None
    slugs = tuple(
        slug.strip() for slug in project_value.split(PROJECT_LIST_SEPARATOR) if slug.strip()
    )
    if not slugs:
        return None
    return SessionStamp(
        session_id=session_id,
        project_slugs=slugs,
        started_at=datetime.now(tz=UTC),
        source=SOURCE_ENVIRONMENT,
    )
