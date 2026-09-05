"""Supersession between entries of the same log.

Log entries reference each other in prose ("supersedes the closed-interval entry
below") rather than by markdown link, so targets resolve by matching the sentence
against sibling entry titles.
"""

from __future__ import annotations

import re

from ..constants import (
    MIN_ENTRY_MATCH_TERMS,
    MIN_ENTRY_TITLE_TERM_LENGTH,
    TEXTUAL_LINK_CONFIDENCE,
)
from ..model import Doc, Link, LinkType
from .backlinks import deduplicate_links
from .extract import SUPERSEDED_BY_PATTERN, SUPERSEDES_PATTERN, split_sentences

PLURAL_SUFFIX = "s"
TERM_PATTERN = re.compile(r"[a-z]+")


def title_terms(*, title: str) -> frozenset[str]:
    """Distinctive lowercase words of a heading, singularized."""
    found = TERM_PATTERN.findall(title.lower())
    return frozenset(
        term.removesuffix(PLURAL_SUFFIX)
        for term in found
        if len(term) >= MIN_ENTRY_TITLE_TERM_LENGTH
    )


def score_against(*, sentence: str, title: str, ignored_terms: frozenset[str] = frozenset()) -> int:
    """How many of a heading's distinctive terms the sentence mentions.

    Terms the source entry's own heading already carries are ignored, since an
    entry body repeats its heading and would otherwise match itself.
    """
    lowered = sentence.lower()
    distinctive = title_terms(title=title) - ignored_terms
    return sum(1 for term in distinctive if term in lowered)


def _best_sibling(*, sentence: str, siblings: tuple[Doc, ...], own_title: str) -> Doc | None:
    ignored_terms = title_terms(title=own_title)
    scored = [
        (score_against(sentence=sentence, title=other.title, ignored_terms=ignored_terms), other)
        for other in siblings
    ]
    scored.sort(key=lambda pair: (-pair[0], pair[1].doc_id))
    if not scored or scored[0][0] < MIN_ENTRY_MATCH_TERMS:
        return None
    return scored[0][1]


def _siblings_of(*, entry: Doc, entries: tuple[Doc, ...]) -> tuple[Doc, ...]:
    return tuple(
        other
        for other in entries
        if other.parent_doc_id == entry.parent_doc_id and other.doc_id != entry.doc_id
    )


def _links_for_sentence(*, entry: Doc, sentence: str, siblings: tuple[Doc, ...]) -> list[Link]:
    is_inverted = bool(SUPERSEDED_BY_PATTERN.search(sentence))
    if not is_inverted and not SUPERSEDES_PATTERN.search(sentence):
        return []
    target = _best_sibling(sentence=sentence, siblings=siblings, own_title=entry.title)
    if target is None:
        return []
    replacement, replaced = (target, entry) if is_inverted else (entry, target)
    return [
        Link(
            src_id=replacement.doc_id,
            dst_id=replaced.doc_id,
            link_type=LinkType.SUPERSEDES,
            confidence=TEXTUAL_LINK_CONFIDENCE,
            evidence=sentence.strip(),
        )
    ]


def entry_supersede_links(*, corpus: tuple[Doc, ...]) -> tuple[Link, ...]:
    """Supersede edges between entries sharing a parent log."""
    entries = tuple(doc for doc in corpus if doc.is_entry)
    found: list[Link] = []
    for entry in entries:
        siblings = _siblings_of(entry=entry, entries=entries)
        for sentence in split_sentences(body=entry.body):
            found.extend(_links_for_sentence(entry=entry, sentence=sentence, siblings=siblings))
    return deduplicate_links(links=tuple(found))
