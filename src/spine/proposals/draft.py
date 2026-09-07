"""Drafts document edits from observed facts, and applies accepted ones."""

from __future__ import annotations

import hashlib
from pathlib import Path

from ..constants import PROPOSAL_APPEND_HEADING
from ..facts.model import Fact, FactKind, PullRequestState
from ..live.store import now_iso
from ..model import Doc, DocKind, Project
from .model import Proposal, ProposalKind, ProposalState

CONTENT_ENCODING = "utf-8"
ID_DIGEST_LENGTH = 12
DRAFT_TARGET_KINDS = (DocKind.BRIEF, DocKind.DECISION_LOG, DocKind.MILESTONE)


def proposal_id_for(*, doc_id: str, body: str) -> str:
    """Content-stable id, so drafting the same edit twice does not queue it twice."""
    digest = hashlib.sha256(f"{doc_id}\n{body}".encode(CONTENT_ENCODING)).hexdigest()
    return f"{doc_id}:{digest[:ID_DIGEST_LENGTH]}"


def _target_doc(*, docs: tuple[Doc, ...]) -> Doc | None:
    addressable = [doc for doc in docs if not doc.is_entry]
    for kind in DRAFT_TARGET_KINDS:
        for doc in addressable:
            if doc.kind is kind:
                return doc
    return None


def _merged_lines(*, facts: tuple[Fact, ...], mentioned: frozenset[str]) -> tuple[str, ...]:
    merged = [
        fact
        for fact in facts
        if fact.kind is FactKind.PULL_REQUEST
        and fact.state == str(PullRequestState.MERGED)
        and fact.reference.lstrip("#") not in mentioned
    ]
    merged.sort(key=lambda fact: fact.reference)
    return tuple(f"- {fact.reference} — {fact.title}".rstrip() for fact in merged)


def draft_from_drift(
    *, project: Project, docs: tuple[Doc, ...], facts: tuple[Fact, ...]
) -> tuple[Proposal, ...]:
    """A proposal recording merged work the corpus does not mention."""
    from ..facts.drift import referenced_pull_requests

    target = _target_doc(docs=docs)
    if target is None or not facts:
        return ()
    mentioned = frozenset(
        number
        for numbers in referenced_pull_requests(docs=docs).values()
        for number in numbers
    )
    lines = _merged_lines(facts=facts, mentioned=mentioned)
    if not lines:
        return ()
    body = "\n".join((PROPOSAL_APPEND_HEADING, "", *lines))
    return (
        Proposal(
            proposal_id=proposal_id_for(doc_id=target.doc_id, body=body),
            project_slug=project.slug,
            doc_id=target.doc_id,
            doc_path=str(target.path),
            kind=ProposalKind.APPEND,
            headline=f"Record {len(lines)} merged pull request(s) in {target.title}",
            rationale="These shipped but no document in this project mentions them.",
            body=body,
            state=ProposalState.PENDING,
            created_at=now_iso(),
        ),
    )


def apply_proposal(*, proposal: Proposal) -> bool:
    """Append the proposed text to its document; returns False when the file is gone."""
    target = Path(proposal.doc_path)
    if not target.is_file():
        return False
    existing = target.read_text(encoding=CONTENT_ENCODING).rstrip("\n")
    target.write_text(
        f"{existing}\n\n{proposal.body}\n", encoding=CONTENT_ENCODING
    )
    return True
