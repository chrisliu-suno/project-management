"""Observed facts: things that happened, never typed by hand."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FactKind(StrEnum):
    """Where a fact came from."""

    COMMIT = "commit"
    PULL_REQUEST = "pull_request"


class PullRequestState(StrEnum):
    OPEN = "open"
    MERGED = "merged"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class Fact:
    """One observed event, keyed by a source-stable identifier."""

    fact_id: str
    project_slug: str
    kind: FactKind
    reference: str
    title: str
    author: str
    occurred_at: str
    state: str = ""
    url: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "fact_id": self.fact_id,
            "project_slug": self.project_slug,
            "kind": str(self.kind),
            "reference": self.reference,
            "title": self.title,
            "author": self.author,
            "occurred_at": self.occurred_at,
            "state": self.state,
            "url": self.url,
        }
