"""Proposed document edits waiting on a decision."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ProposalState(StrEnum):
    """Where a proposal stands."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ProposalKind(StrEnum):
    """What kind of edit is being proposed."""

    APPEND = "append"


@dataclass(frozen=True, slots=True)
class Proposal:
    """One edit drafted from observed facts, for a human to accept or reject."""

    proposal_id: str
    project_slug: str
    doc_id: str
    doc_path: str
    kind: ProposalKind
    headline: str
    rationale: str
    body: str
    state: ProposalState
    created_at: str
    decided_at: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "proposal_id": self.proposal_id,
            "project_slug": self.project_slug,
            "doc_id": self.doc_id,
            "doc_path": self.doc_path,
            "kind": str(self.kind),
            "headline": self.headline,
            "rationale": self.rationale,
            "body": self.body,
            "state": str(self.state),
            "created_at": self.created_at,
            "decided_at": self.decided_at,
        }
