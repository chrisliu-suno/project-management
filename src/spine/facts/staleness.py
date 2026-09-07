"""Drift the graph and the filesystem can see, without needing a pull request."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..constants import DRIFT_MAX_REPORTED_DOCS
from ..dashboard import Finding, Severity
from ..index.backlinks import sweep_targets
from ..model import Doc, Link, LinkType
from .model import Fact, FactKind, PullRequestState

ISO_UTC_SUFFIX = "Z"
ISO_OFFSET = "+00:00"


def _superseded_ids(*, links: tuple[Link, ...]) -> tuple[str, ...]:
    return tuple(
        sorted({link.dst_id for link in links if link.link_type is LinkType.SUPERSEDES})
    )


def unswept_supersessions(
    *, docs: tuple[Doc, ...], links: tuple[Link, ...]
) -> tuple[Finding, ...]:
    """Documents still citing a decision that something else replaced."""
    by_id = {doc.doc_id: doc for doc in docs}
    found: list[Finding] = []
    for superseded_id in _superseded_ids(links=links):
        citers = tuple(
            doc_id
            for doc_id in sweep_targets(links=links, superseded_doc_id=superseded_id)
            if doc_id in by_id
        )
        if not citers:
            continue
        replaced = by_id.get(superseded_id)
        title = replaced.title if replaced is not None else superseded_id
        found.append(
            Finding(
                code="unswept_supersession",
                severity=Severity.WARN,
                headline=f"{len(citers)} document(s) still cite a superseded decision",
                detail=f"{title!r} was superseded; everything citing it may carry the old framing.",
                doc_ids=tuple(sorted(citers)[:DRIFT_MAX_REPORTED_DOCS]),
            )
        )
    return tuple(found)


def _parsed(*, stamp: str) -> datetime | None:
    try:
        return datetime.fromisoformat(stamp.replace(ISO_UTC_SUFFIX, ISO_OFFSET))
    except ValueError:
        return None


def _latest_merge(*, facts: tuple[Fact, ...]) -> datetime | None:
    stamps = [
        parsed
        for fact in facts
        if fact.kind is FactKind.PULL_REQUEST and fact.state == str(PullRequestState.MERGED)
        and (parsed := _parsed(stamp=fact.occurred_at)) is not None
    ]
    return max(stamps) if stamps else None


def _modified_at(*, doc: Doc, docs_dir: Path) -> datetime | None:
    target = docs_dir / doc.path.name
    if not target.is_file():
        return None
    return datetime.fromtimestamp(target.stat().st_mtime).astimezone()


def stale_since_shipped(
    *, docs: tuple[Doc, ...], facts: tuple[Fact, ...], docs_dir: Path
) -> tuple[Finding, ...]:
    """Documents untouched since the project's most recent merge."""
    latest = _latest_merge(facts=facts)
    if latest is None:
        return ()
    stale = sorted(
        doc.doc_id
        for doc in docs
        if not doc.is_entry
        and (modified := _modified_at(doc=doc, docs_dir=docs_dir)) is not None
        and modified < latest
    )
    if not stale:
        return ()
    return (
        Finding(
            code="stale_since_shipped",
            severity=Severity.WARN,
            headline=f"{len(stale)} document(s) untouched since the last merge",
            detail="Work shipped after these were last edited; they may describe the old shape.",
            doc_ids=tuple(stale[:DRIFT_MAX_REPORTED_DOCS]),
        ),
    )
