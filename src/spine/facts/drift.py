"""Compares what the documents claim against what the facts show."""

from __future__ import annotations

import re

from ..constants import CLOSED_PR_ACKNOWLEDGED_PATTERN, CLOSED_PR_ACKNOWLEDGED_WINDOW
from ..dashboard import Finding, Severity
from ..model import Doc, Link
from .model import Fact, FactKind, PullRequestState

PR_REFERENCE_PATTERN = re.compile(r"#(\d{2,6})")
CLOSED_PR_ACKNOWLEDGED = re.compile(CLOSED_PR_ACKNOWLEDGED_PATTERN, re.IGNORECASE)
MAX_REPORTED_REFERENCES = 12


def referenced_pull_requests(*, docs: tuple[Doc, ...]) -> dict[str, tuple[str, ...]]:
    """Every pull-request number each document mentions."""
    found: dict[str, tuple[str, ...]] = {}
    for doc in docs:
        numbers = tuple(sorted(set(PR_REFERENCE_PATTERN.findall(doc.body))))
        if numbers:
            found[doc.doc_id] = numbers
    return found


def unacknowledged_references(*, doc: Doc) -> frozenset[str]:
    """Pull-request numbers the document cites without ever saying what became of them.

    Saying it once, next to any one citation, covers the document's other mentions: a note
    about a closed pull request names it many times after stating its fate.
    """
    cited: set[str] = set()
    acknowledged: set[str] = set()
    for line in doc.body.splitlines():
        for match in PR_REFERENCE_PATTERN.finditer(line):
            cited.add(match.group(1))
            if _is_acknowledged(line=line, start=match.start(), end=match.end()):
                acknowledged.add(match.group(1))
    return frozenset(cited - acknowledged)


def _is_acknowledged(*, line: str, start: int, end: int) -> bool:
    """Whether a fate word sits within the window of the citation on its own line.

    Every citation in reach counts, so a list ending "(all four closed)" covers all four.
    """
    window = line[max(0, start - CLOSED_PR_ACKNOWLEDGED_WINDOW) : end + CLOSED_PR_ACKNOWLEDGED_WINDOW]
    return CLOSED_PR_ACKNOWLEDGED.search(window) is not None


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
    """Documents citing pull requests that never merged, where no line citing it says so."""
    by_reference = _facts_by_reference(facts=facts)
    stale: list[str] = []
    for doc in docs:
        for number in sorted(unacknowledged_references(doc=doc)):
            fact = by_reference.get(number)
            if fact is not None and fact.state == str(PullRequestState.CLOSED):
                stale.append(f"{doc.doc_id} cites #{number}")
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
) -> tuple[Finding, ...]:
    """Every place the documents, the graph, and the observed facts disagree."""
    from .staleness import unswept_supersessions

    found: list[Finding] = []
    if links:
        found.extend(unswept_supersessions(docs=docs, links=links))
    if facts:
        found.extend(merged_but_undocumented(docs=docs, facts=facts))
        found.extend(documented_but_unmerged(docs=docs, facts=facts))
    return tuple(found)
