"""Whether the corpus can actually bring someone up to speed.

Structural checks pass on a corpus nobody can read. These ask the reader's
question instead: starting from the entry point and following links, what do you
learn, and how old is it.
"""

from __future__ import annotations

import re

from ..constants import ONBOARDING_MAX_REPORTED_DOCS, ONBOARDING_STALE_ENTRY_DAYS
from ..dashboard import Finding, Severity
from ..model import Doc, Link, ReadWhen

DATE_PATTERN = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
ENTRY_HEADER_CHARS = 600


def _standalone(*, docs: tuple[Doc, ...]) -> tuple[Doc, ...]:
    return tuple(doc for doc in docs if not doc.is_entry)


def entry_points(*, docs: tuple[Doc, ...]) -> tuple[Doc, ...]:
    """Documents a session is always given, which is where a reader starts."""
    return tuple(doc for doc in _standalone(docs=docs) if doc.read_when is ReadWhen.EVERY_TIME)


def _dates_in(*, text: str) -> tuple[str, ...]:
    return tuple("-".join(match) for match in DATE_PATTERN.findall(text))


def newest_date(*, docs: tuple[Doc, ...]) -> str | None:
    """The latest date the corpus mentions anywhere."""
    found = [date for doc in docs for date in _dates_in(text=doc.body)]
    return max(found) if found else None


def _days_between(*, earlier: str, later: str) -> int:
    from datetime import date

    start = date.fromisoformat(earlier)
    end = date.fromisoformat(later)
    return (end - start).days


def missing_entry_point(*, docs: tuple[Doc, ...]) -> tuple[Finding, ...]:
    """A corpus with no always-read document gives a reader nowhere to start."""
    if entry_points(docs=docs) or not _standalone(docs=docs):
        return ()
    return (
        Finding(
            code="no_entry_point",
            severity=Severity.PROBLEM,
            headline="no document is marked as the place to start",
            detail="Set one document's read-when to every_time so a reader has an entry point.",
            doc_ids=(),
        ),
    )


def stale_entry_point(*, docs: tuple[Doc, ...]) -> tuple[Finding, ...]:
    """An entry point far older than the work around it teaches the wrong system."""
    standalone = _standalone(docs=docs)
    latest = newest_date(docs=standalone)
    if latest is None:
        return ()
    found: list[Finding] = []
    for entry in entry_points(docs=standalone):
        stamped = _dates_in(text=entry.body[:ENTRY_HEADER_CHARS])
        if not stamped:
            continue
        age = _days_between(earlier=max(stamped), later=latest)
        if age <= ONBOARDING_STALE_ENTRY_DAYS:
            continue
        found.append(
            Finding(
                code="stale_entry_point",
                severity=Severity.WARN,
                headline=f"the entry point is {age} days behind the corpus",
                detail=(
                    f"{entry.path.name} is dated {max(stamped)} while the corpus "
                    f"reaches {latest}; a reader starting here learns the old system."
                ),
                doc_ids=(entry.doc_id,),
            )
        )
    return tuple(found)


def reachable_from(*, docs: tuple[Doc, ...], links: tuple[Link, ...]) -> frozenset[str]:
    """Doc ids a reader can arrive at by starting at an entry point and following links."""
    outbound: dict[str, list[str]] = {}
    for link in links:
        outbound.setdefault(link.src_id, []).append(link.dst_id)
    parents = {doc.doc_id: doc.parent_doc_id for doc in docs}
    children: dict[str, list[str]] = {}
    for doc in docs:
        if doc.parent_doc_id is not None:
            children.setdefault(doc.parent_doc_id, []).append(doc.doc_id)
    seen: set[str] = set()
    queue = [entry.doc_id for entry in entry_points(docs=docs)]
    while queue:
        current = queue.pop()
        if current in seen:
            continue
        seen.add(current)
        queue.extend(outbound.get(current, ()))
        queue.extend(children.get(current, ()))
        parent = parents.get(current)
        if parent is not None:
            queue.append(parent)
    return frozenset(seen)


def unreachable_findings(*, docs: tuple[Doc, ...], links: tuple[Link, ...]) -> tuple[Finding, ...]:
    """Documents a reader following links from the entry point never arrives at."""
    standalone = _standalone(docs=docs)
    if not entry_points(docs=standalone):
        return ()
    seen = reachable_from(docs=docs, links=links)
    stranded = sorted(doc.doc_id for doc in standalone if doc.doc_id not in seen)
    if not stranded:
        return ()
    return (
        Finding(
            code="unreachable_from_entry",
            severity=Severity.WARN,
            headline=f"{len(stranded)} document(s) a reader never reaches",
            detail="Nothing on a path from the entry point links to these; link them or retire them.",
            doc_ids=tuple(stranded[:ONBOARDING_MAX_REPORTED_DOCS]),
        ),
    )


def onboarding_findings(*, docs: tuple[Doc, ...], links: tuple[Link, ...]) -> tuple[Finding, ...]:
    """Every check about whether the corpus can bring a reader up to speed."""
    return (
        *missing_entry_point(docs=docs),
        *stale_entry_point(docs=docs),
        *unreachable_findings(docs=docs, links=links),
    )
