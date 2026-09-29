"""Drift the graph and the filesystem can see, without needing a pull request."""

from __future__ import annotations

from ..constants import DRIFT_MAX_REPORTED_DOCS
from ..dashboard import Finding, Severity
from ..index.backlinks import sweep_targets
from ..model import Doc, Link, LinkType


def _superseded_ids(*, links: tuple[Link, ...]) -> tuple[str, ...]:
    return tuple(
        sorted({link.dst_id for link in links if link.link_type is LinkType.SUPERSEDES})
    )


def _label_for(*, doc: Doc | None, doc_id: str) -> str:
    """Title plus filename, so two documents sharing a title stay distinguishable."""
    if doc is None:
        return repr(doc_id)
    return f"{doc.title!r} ({doc.path.name})"


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
        found.append(
            Finding(
                code="unswept_supersession",
                severity=Severity.WARN,
                headline=f"{len(citers)} document(s) still cite a superseded decision",
                detail=(
                    f"{_label_for(doc=by_id.get(superseded_id), doc_id=superseded_id)} was "
                    "superseded; everything citing it may carry the old framing."
                ),
                doc_ids=tuple(sorted(citers)[:DRIFT_MAX_REPORTED_DOCS]),
            )
        )
    return tuple(found)
