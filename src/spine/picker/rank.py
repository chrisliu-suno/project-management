"""Deterministic ranking of candidate documents against a task context."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Protocol

from ..constants import (
    AREA_MATCH_WEIGHT,
    GRAPH_PROXIMITY_WEIGHT,
    MARKDOWN_HEADING_PREFIX,
    MIN_RANKING_TERM_LENGTH,
    RANKING_SCORE_PRECISION,
    RANKING_TERM_PATTERN,
    TITLE_TERM_OVERLAP_WEIGHT,
)
from ..model import Doc

_TERM_PATTERN = re.compile(RANKING_TERM_PATTERN)


class NeighbourLookup(Protocol):
    """Returns the doc ids linked to a doc in either direction."""

    def __call__(self, *, doc_id: str) -> frozenset[str]: ...


def no_neighbours(*, doc_id: str) -> frozenset[str]:
    """Neighbour lookup for callers that have no graph to consult."""
    return frozenset()


def terms_in(*, text: str) -> frozenset[str]:
    """Lowercased word terms long enough to carry meaning."""
    found = _TERM_PATTERN.findall(text.lower())
    return frozenset(term for term in found if len(term) >= MIN_RANKING_TERM_LENGTH)


def heading_terms(*, doc: Doc) -> frozenset[str]:
    """Terms drawn from the title plus every markdown heading in the body."""
    headings = [
        line for line in doc.body.splitlines() if line.lstrip().startswith(MARKDOWN_HEADING_PREFIX)
    ]
    return terms_in(text=" ".join([doc.title, *headings]))


def area_score(*, doc: Doc, task_terms: frozenset[str]) -> float:
    """Full weight when every term of the doc's area appears in the task context."""
    if doc.area is None:
        return 0.0
    area_terms = terms_in(text=doc.area)
    if area_terms and area_terms <= task_terms:
        return AREA_MATCH_WEIGHT
    return 0.0


def overlap_score(*, doc: Doc, task_terms: frozenset[str]) -> float:
    """Share of the doc's title and heading terms that the task context mentions."""
    doc_terms = heading_terms(doc=doc)
    if not doc_terms or not task_terms:
        return 0.0
    return TITLE_TERM_OVERLAP_WEIGHT * len(doc_terms & task_terms) / len(doc_terms)


def proximity_score(
    *, doc: Doc, chosen_ids: frozenset[str], neighbours_of: NeighbourLookup
) -> float:
    """Share of the already-chosen docs this doc is linked to in the graph."""
    if not chosen_ids:
        return 0.0
    linked = neighbours_of(doc_id=doc.doc_id) & chosen_ids
    return GRAPH_PROXIMITY_WEIGHT * len(linked) / len(chosen_ids)


def score_doc(
    *,
    doc: Doc,
    task_terms: frozenset[str],
    chosen_ids: frozenset[str] = frozenset(),
    neighbours_of: NeighbourLookup = no_neighbours,
) -> float:
    """Area, heading-overlap and graph-proximity components, summed and quantized.

    Quantizing keeps float error from silently pre-empting the doc-id tiebreak.
    """
    total = (
        area_score(doc=doc, task_terms=task_terms)
        + overlap_score(doc=doc, task_terms=task_terms)
        + proximity_score(doc=doc, chosen_ids=chosen_ids, neighbours_of=neighbours_of)
    )
    return round(total, RANKING_SCORE_PRECISION)


def rank_docs(
    *,
    docs: Iterable[Doc],
    task_context: str,
    chosen_ids: frozenset[str] = frozenset(),
    neighbours_of: NeighbourLookup = no_neighbours,
) -> tuple[Doc, ...]:
    """Candidates ordered by descending score, ties broken by doc id."""
    task_terms = terms_in(text=task_context)
    scored = [
        (
            score_doc(
                doc=doc,
                task_terms=task_terms,
                chosen_ids=chosen_ids,
                neighbours_of=neighbours_of,
            ),
            doc,
        )
        for doc in docs
    ]
    scored.sort(key=lambda pair: (-pair[0], pair[1].doc_id))
    return tuple(doc for _, doc in scored)
