"""Types for what a running session says it is doing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SessionState(StrEnum):
    """What a session is doing, as far as it last said."""

    WORKING = "working"
    PAUSED = "paused"
    STOPPED = "stopped"
    IDLE = "idle"


class SteeringAction(StrEnum):
    """An instruction waiting for a session to pick up."""

    REDIRECT = "redirect"
    PAUSE = "pause"
    RESUME = "resume"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class LiveSession:
    """One session's declared intent and last heartbeat."""

    session_id: str
    project_slugs: tuple[str, ...]
    intent: str
    state: SessionState
    declared_paths: tuple[str, ...]
    updated_at: str
    started_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "project_slugs": list(self.project_slugs),
            "intent": self.intent,
            "state": str(self.state),
            "declared_paths": list(self.declared_paths),
            "updated_at": self.updated_at,
            "started_at": self.started_at,
        }


@dataclass(frozen=True, slots=True)
class SteeringMessage:
    """An instruction addressed to one session."""

    message_id: str
    session_id: str
    action: SteeringAction
    body: str
    created_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "message_id": self.message_id,
            "session_id": self.session_id,
            "action": str(self.action),
            "body": self.body,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class Broadcast:
    """Something every session on a project should know."""

    broadcast_id: str
    project_slug: str
    headline: str
    body: str
    origin_session_id: str
    created_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "broadcast_id": self.broadcast_id,
            "project_slug": self.project_slug,
            "headline": self.headline,
            "body": self.body,
            "origin_session_id": self.origin_session_id,
            "created_at": self.created_at,
        }
