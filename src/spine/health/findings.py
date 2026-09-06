"""Per-check analysis of a project's corpus."""

from __future__ import annotations

from difflib import SequenceMatcher

from ..constants import (
    EVERY_TIME_RESERVED_LINES,
    HEALTH_DUPLICATE_TITLE_SIMILARITY,
    HEALTH_MAX_EVERY_TIME_DOCS,
)
from ..dashboard import Finding, Severity
from ..docs.limits import find_cap_breaches
from ..model import Doc, DocKind, Link, LinkType, ReadWhen

AGENT_SUFFIX_SEPARATOR = "--"
CITATION_EXCLUDED_TYPE = LinkType.CITED_BY


def _addressable(*, docs: tuple[Doc, ...]) -> tuple[Doc, ...]:
    return tuple(doc for doc in docs if not doc.is_entry)


def brief_findings(*, docs: tuple[Doc, ...]) -> tuple[Finding, ...]:
    """Exactly one document should be the project's starting point."""
    briefs = [doc for doc in _addressable(docs=docs) if doc.kind is DocKind.BRIEF]
    if not briefs:
        return (
            Finding(
                code="no_brief",
                severity=Severity.PROBLEM,
                headline="No brief",
                detail=(
                    "Nothing in this corpus is the starting point for the whole project, "
                    "so a session has no anchor to load first."
                ),
            ),
        )
    if len(briefs) > 1:
        return (
            Finding(
                code="many_briefs",
                severity=Severity.PROBLEM,
                headline=f"{len(briefs)} documents claim to be the brief",
                detail="Only one document should be the project's starting point.",
                doc_ids=tuple(sorted(doc.doc_id for doc in briefs)),
            ),
        )
    return (
        Finding(
            code="brief",
            severity=Severity.OK,
            headline=f"Brief: {briefs[0].title}",
            detail="One document is the project's starting point, as it should be.",
            doc_ids=(briefs[0].doc_id,),
        ),
    )


def orphan_findings(*, docs: tuple[Doc, ...], links: tuple[Link, ...]) -> tuple[Finding, ...]:
    """Documents nothing links to are reachable only by luck."""
    linked_to = {link.dst_id for link in links if link.link_type is not CITATION_EXCLUDED_TYPE}
    orphans = sorted(
        doc.doc_id for doc in _addressable(docs=docs) if doc.doc_id not in linked_to
    )
    if not orphans:
        return ()
    return (
        Finding(
            code="orphans",
            severity=Severity.WARN,
            headline=f"{len(orphans)} document(s) nothing links to",
            detail="An unlinked document is found only by walking the directory.",
            doc_ids=tuple(orphans),
        ),
    )


def cap_breach_findings(*, docs: tuple[Doc, ...]) -> tuple[Finding, ...]:
    """Documents over their read-when group's line cap."""
    breaches = find_cap_breaches(docs=_addressable(docs=docs))
    if not breaches:
        return ()
    return (
        Finding(
            code="over_cap",
            severity=Severity.WARN,
            headline=f"{len(breaches)} document(s) over their size cap",
            detail="Split them, or they crowd out everything else in their group.",
            doc_ids=tuple(sorted(breach.doc.doc_id for breach in breaches)),
        ),
    )


def every_time_findings(*, docs: tuple[Doc, ...]) -> tuple[Finding, ...]:
    """The always-injected group is what makes or breaks selection."""
    group = [
        doc for doc in _addressable(docs=docs) if doc.read_when is ReadWhen.EVERY_TIME
    ]
    total = sum(doc.line_count for doc in group)
    found: list[Finding] = []
    if total > EVERY_TIME_RESERVED_LINES:
        found.append(
            Finding(
                code="every_time_over_reserve",
                severity=Severity.PROBLEM,
                headline=f"Always-read group is {total} lines, over the {EVERY_TIME_RESERVED_LINES} reserve",
                detail="One of these is silently dropped from every selection.",
                doc_ids=tuple(sorted(doc.doc_id for doc in group)),
            )
        )
    elif len(group) > HEALTH_MAX_EVERY_TIME_DOCS:
        found.append(
            Finding(
                code="every_time_crowded",
                severity=Severity.WARN,
                headline=f"{len(group)} documents are read on every task",
                detail="This group is paid for on every task; keep it small.",
                doc_ids=tuple(sorted(doc.doc_id for doc in group)),
            )
        )
    return tuple(found)


def _base_name(*, doc: Doc) -> str:
    return doc.path.stem.split(AGENT_SUFFIX_SEPARATOR, maxsplit=1)[0]


def _cluster_key(*, doc: Doc) -> str:
    return _base_name(doc=doc).lower()


def _title_clusters(*, docs: tuple[Doc, ...]) -> list[list[Doc]]:
    clusters: list[list[Doc]] = []
    for doc in docs:
        placed = False
        for cluster in clusters:
            head = cluster[0]
            same_base = _cluster_key(doc=doc) == _cluster_key(doc=head)
            similar = (
                SequenceMatcher(None, doc.title.lower(), head.title.lower()).ratio()
                >= HEALTH_DUPLICATE_TITLE_SIMILARITY
            )
            if same_base or similar:
                cluster.append(doc)
                placed = True
                break
        if not placed:
            clusters.append([doc])
    return [cluster for cluster in clusters if len(cluster) > 1]


def duplicate_findings(*, docs: tuple[Doc, ...]) -> tuple[Finding, ...]:
    """Near-duplicate documents competing to answer the same question."""
    ordered = sorted(_addressable(docs=docs), key=lambda doc: doc.doc_id)
    return tuple(
        Finding(
            code="duplicate_titles",
            severity=Severity.WARN,
            headline=f"{len(cluster)} near-duplicate documents",
            detail="One question should have one document; merge or delete the rest.",
            doc_ids=tuple(sorted(doc.doc_id for doc in cluster)),
        )
        for cluster in _title_clusters(docs=ordered)
    )


def unclassified_findings(*, docs: tuple[Doc, ...]) -> tuple[Finding, ...]:
    """Documents with no known kind can never be selected."""
    unknown = sorted(
        doc.doc_id
        for doc in _addressable(docs=docs)
        if doc.kind is DocKind.GENERATED and doc.read_when is ReadWhen.LOOKED_UP
    )
    if not unknown:
        return ()
    return (
        Finding(
            code="unclassified",
            severity=Severity.WARN,
            headline=f"{len(unknown)} document(s) have no known kind",
            detail="Run `spine classify run` so these become selectable.",
            doc_ids=tuple(unknown),
        ),
    )


def all_findings(*, docs: tuple[Doc, ...], links: tuple[Link, ...]) -> tuple[Finding, ...]:
    """Every check, in the order they should be read."""
    return (
        *brief_findings(docs=docs),
        *every_time_findings(docs=docs),
        *unclassified_findings(docs=docs),
        *duplicate_findings(docs=docs),
        *orphan_findings(docs=docs, links=links),
        *cap_breach_findings(docs=docs),
    )
