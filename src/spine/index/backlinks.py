"""Pure derivations over a set of links: inversion, deduplication, sweep fan-out."""

from __future__ import annotations

from ..constants import CITATION_LINK_TYPES
from ..model import Link, LinkType


def deduplicate_links(*, links: tuple[Link, ...]) -> tuple[Link, ...]:
    """Collapse links sharing a source, destination, and type, keeping the most confident."""
    best_by_edge: dict[tuple[str, str, LinkType], Link] = {}
    for link in links:
        edge = (link.src_id, link.dst_id, link.link_type)
        current = best_by_edge.get(edge)
        if current is None or link.confidence > current.confidence:
            best_by_edge[edge] = link
    return tuple(best_by_edge.values())


def is_citation(*, link: Link) -> bool:
    """A link is a citation when its source doc points at the destination's content."""
    return link.link_type in CITATION_LINK_TYPES


def backlinks(*, links: tuple[Link, ...]) -> tuple[Link, ...]:
    """Invert every citation into a CITED_BY link pointing back at the citing doc."""
    inverted = tuple(
        Link(
            src_id=link.dst_id,
            dst_id=link.src_id,
            link_type=LinkType.CITED_BY,
            confidence=link.confidence,
            evidence=link.evidence,
        )
        for link in links
        if is_citation(link=link)
    )
    return deduplicate_links(links=inverted)


def sweep_targets(*, links: tuple[Link, ...], superseded_doc_id: str) -> tuple[str, ...]:
    """Every doc that cites the superseded one, so superseding becomes a sweep."""
    citing_ids = {
        link.src_id for link in links if link.dst_id == superseded_doc_id and is_citation(link=link)
    }
    citing_ids |= {
        link.dst_id
        for link in links
        if link.src_id == superseded_doc_id and link.link_type is LinkType.CITED_BY
    }
    citing_ids.discard(superseded_doc_id)
    return tuple(sorted(citing_ids))
