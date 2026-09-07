"""Compares what the documents claim against what the facts show."""

from __future__ import annotations

import re

from ..dashboard import Finding, Severity
from pathlib import Path

from ..model import Doc, Link
from .model import Fact, FactKind, PullRequestState

PR_REFERENCE_PATTERN = re.compile(r"#(\d{2,6})")
MAX_REPORTED_REFERENCES = 12


def referenced_pull_requests(*, docs: tuple[Doc, ...]) -> dict[str, tuple[str, ...]]:
    """Every pull-request number each document mentions."""
    found: dict[str, tuple[str, ...]] = {}
    for doc in docs:
        numbers = tuple(sorted(set(PR_REFERENCE_PATTERN.findall(doc.body))))
        if numbers:
            found[doc.doc_id] = numbers
    return found


def _facts_by_reference(*, facts: tuple[Fact, ...]) -> dict[str, Fact]:
    return {
        fact.reference.lstrip("#"): fact
        for fact in facts
        if fact.kind is FactKind.PULL_REQUEST
    }


def merged_but_undocumented(
    *, docs: tuple[Doc, ...], facts: tuple[Fact, ...]
) -> tuple[Finding, ...]:
    """Merged pull requests no document mentions."""
    mentioned = {
        number for numbers in referenced_pull_requests(docs=docs).values() for number in numbers
    }
    merged = [
        fact
        for fact in facts
        if fact.kind is FactKind.PULL_REQUEST
        and fact.state == str(PullRequestState.MERGED)
        and fact.reference.lstrip("#") not in mentioned
    ]
    if not merged:
        return ()
    shown = sorted(fact.reference for fact in merged)[:MAX_REPORTED_REFERENCES]
    return (
        Finding(
            code="merged_undocumented",
            severity=Severity.WARN,
            headline=f"{len(merged)} merged pull request(s) no document mentions",
            detail="The plan does not reflect work that already shipped: " + ", ".join(shown),
        ),
    )


def documented_but_unmerged(
    *, docs: tuple[Doc, ...], facts: tuple[Fact, ...]
) -> tuple[Finding, ...]:
    """Documents citing pull requests that never merged."""
    by_reference = _facts_by_reference(facts=facts)
    stale: list[str] = []
    for doc_id, numbers in referenced_pull_requests(docs=docs).items():
        for number in numbers:
            fact = by_reference.get(number)
            if fact is not None and fact.state == str(PullRequestState.CLOSED):
                stale.append(f"{doc_id} cites #{number}")
    if not stale:
        return ()
    return (
        Finding(
            code="cites_closed_pr",
            severity=Severity.WARN,
            headline=f"{len(stale)} citation(s) of a pull request that never merged",
            detail="A closed pull request left its claim behind: " + "; ".join(
                sorted(stale)[:MAX_REPORTED_REFERENCES]
            ),
        ),
    )


def drift_findings(
    *,
    docs: tuple[Doc, ...],
    facts: tuple[Fact, ...],
    links: tuple[Link, ...] = (),
    docs_dir: Path | None = None,
) -> tuple[Finding, ...]:
    """Every place the documents, the graph, and the observed facts disagree."""
    from .staleness import stale_since_shipped, unswept_supersessions

    found: list[Finding] = []
    if links:
        found.extend(unswept_supersessions(docs=docs, links=links))
    if facts:
        found.extend(merged_but_undocumented(docs=docs, facts=facts))
        found.extend(documented_but_unmerged(docs=docs, facts=facts))
        if docs_dir is not None:
            found.extend(stale_since_shipped(docs=docs, facts=facts, docs_dir=docs_dir))
    return tuple(found)
