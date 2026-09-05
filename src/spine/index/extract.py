"""Derives typed links from document text alone, with no model call."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..constants import TEXTUAL_LINK_CONFIDENCE
from ..constants import ENTRY_ANCHOR_SEPARATOR
from ..docs.entries import slugify_heading
from ..model import Doc, DocKind, Link, LinkType
from .backlinks import deduplicate_links

MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]*\]\(\s*([^)\s]+)[^)]*\)")
BLOCK_SPLIT_PATTERN = re.compile(r"\n\s*\n")
SOFT_WRAP_PATTERN = re.compile(r"\s*\n\s*")
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
EXTERNAL_TARGET_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)
ANCHOR_SEPARATOR = "#"
BARE_MENTION_TEMPLATE = r"(?<![\w./-])({alternatives})(?!\w)"

SUPERSEDED_BY_PATTERN = re.compile(r"\bsuperseded\s+by\b", re.IGNORECASE)
SUPERSEDES_PATTERN = re.compile(r"\bsupersede[sd]?\b", re.IGNORECASE)
CITED_BY_PATTERN = re.compile(r"\bcited\s+by\b", re.IGNORECASE)
RAMPS_PATTERN = re.compile(r"\bramps?\b", re.IGNORECASE)
VERIFIES_PATTERN = re.compile(r"\bverif(?:ies|ied|y)\b", re.IGNORECASE)
BLOCKS_PATTERN = re.compile(r"\bblocks?\b", re.IGNORECASE)
DEPENDS_ON_PATTERN = re.compile(r"\bblocked\s+by\b|\bdepends\s+on\b", re.IGNORECASE)
IMPLEMENTS_PATTERN = re.compile(r"\bimplements?\b", re.IGNORECASE)
CLASSIFIES_PATTERN = re.compile(r"\bclassif(?:ies|ied|y)\b", re.IGNORECASE)
CONSTRAINS_PATTERN = re.compile(r"\bconstrains?\b", re.IGNORECASE)
RELEASED_BY_PATTERN = re.compile(r"\breleased\s+by\b", re.IGNORECASE)
COVERAGE_IN_PATTERN = re.compile(r"\bcoverage\s+(?:in|for)\b", re.IGNORECASE)

PhrasingRules = tuple[tuple[re.Pattern[str], LinkType], ...]

INVERSE_PHRASING_RULES: PhrasingRules = (
    (SUPERSEDED_BY_PATTERN, LinkType.SUPERSEDES),
    (CITED_BY_PATTERN, LinkType.MENTIONS),
    (RELEASED_BY_PATTERN, LinkType.RAMPS),
    (COVERAGE_IN_PATTERN, LinkType.VERIFIES),
)

FORWARD_PHRASING_RULES: PhrasingRules = ((SUPERSEDES_PATTERN, LinkType.SUPERSEDES),)

KIND_PHRASING_RULES: dict[DocKind, PhrasingRules] = {
    DocKind.PROJECT_RULES: ((CONSTRAINS_PATTERN, LinkType.CONSTRAINS),),
    DocKind.CLASSIFICATION: ((CLASSIFIES_PATTERN, LinkType.CLASSIFIES),),
    DocKind.MILESTONE: ((IMPLEMENTS_PATTERN, LinkType.IMPLEMENTS),),
    DocKind.ROLLOUT: ((RAMPS_PATTERN, LinkType.RAMPS),),
    DocKind.TEST_COVERAGE: ((VERIFIES_PATTERN, LinkType.VERIFIES),),
    DocKind.OPEN_QUESTIONS: (
        (DEPENDS_ON_PATTERN, LinkType.DEPENDS_ON),
        (BLOCKS_PATTERN, LinkType.BLOCKS),
    ),
}

KIND_DEFAULT_LINK_TYPES: dict[DocKind, LinkType] = {
    DocKind.PROJECT_RULES: LinkType.CONSTRAINS,
    DocKind.CLASSIFICATION: LinkType.CLASSIFIES,
    DocKind.MILESTONE: LinkType.IMPLEMENTS,
}

FALLBACK_LINK_TYPE = LinkType.MENTIONS


@dataclass(frozen=True, slots=True)
class FileNameIndex:
    """Maps a corpus file name to the doc id it belongs to."""

    doc_ids_by_file_name: dict[str, str]
    mention_pattern: re.Pattern[str] | None
    entry_ids: frozenset[str] = frozenset()


def build_file_name_index(*, corpus: tuple[Doc, ...]) -> FileNameIndex:
    """Index a corpus by file name so textual references resolve to doc ids."""
    doc_ids_by_file_name = {doc.path.name: doc.doc_id for doc in corpus if not doc.is_entry}
    entry_ids = frozenset(doc.doc_id for doc in corpus if doc.is_entry)
    if not doc_ids_by_file_name:
        return FileNameIndex(doc_ids_by_file_name={}, mention_pattern=None, entry_ids=entry_ids)
    alternatives = "|".join(
        re.escape(name) for name in sorted(doc_ids_by_file_name, key=len, reverse=True)
    )
    return FileNameIndex(
        doc_ids_by_file_name=doc_ids_by_file_name,
        mention_pattern=re.compile(BARE_MENTION_TEMPLATE.format(alternatives=alternatives)),
        entry_ids=entry_ids,
    )


def split_sentences(*, body: str) -> tuple[str, ...]:
    """Split markdown into sentences, joining soft-wrapped lines inside a block first."""
    sentences: list[str] = []
    for block in BLOCK_SPLIT_PATTERN.split(body):
        joined = SOFT_WRAP_PATTERN.sub(" ", block).strip()
        sentences.extend(part for part in SENTENCE_SPLIT_PATTERN.split(joined) if part)
    return tuple(sentences)


def _resolve_file_name(*, target: str, index: FileNameIndex) -> str | None:
    """The doc id a link target names, preferring a log entry when anchored."""
    if EXTERNAL_TARGET_PATTERN.match(target):
        return None
    path_part, _, anchor = target.partition(ANCHOR_SEPARATOR)
    file_doc_id = index.doc_ids_by_file_name.get(Path(path_part).name)
    if file_doc_id is None or not anchor:
        return file_doc_id
    entry_id = f"{file_doc_id}{ENTRY_ANCHOR_SEPARATOR}{slugify_heading(heading=anchor)}"
    return entry_id if entry_id in index.entry_ids else file_doc_id


def markdown_link_doc_ids(*, sentence: str, index: FileNameIndex) -> tuple[str, ...]:
    """Doc ids reached by `[text](other-doc.md)` inside one sentence."""
    resolved = (
        _resolve_file_name(target=match.group(1), index=index)
        for match in MARKDOWN_LINK_PATTERN.finditer(sentence)
    )
    return tuple(doc_id for doc_id in resolved if doc_id is not None)


def bare_mention_doc_ids(*, sentence: str, index: FileNameIndex) -> tuple[str, ...]:
    """Doc ids named by a bare file name in prose, ignoring markdown link syntax."""
    if index.mention_pattern is None:
        return ()
    prose = MARKDOWN_LINK_PATTERN.sub(" ", sentence)
    return tuple(
        index.doc_ids_by_file_name[match.group(1)]
        for match in index.mention_pattern.finditer(prose)
    )


def _referenced_doc_ids(*, sentence: str, index: FileNameIndex) -> tuple[str, ...]:
    ordered: list[str] = []
    for doc_id in (
        *markdown_link_doc_ids(sentence=sentence, index=index),
        *bare_mention_doc_ids(sentence=sentence, index=index),
    ):
        if doc_id not in ordered:
            ordered.append(doc_id)
    return tuple(ordered)


def _match_phrasing(*, sentence: str, rules: PhrasingRules) -> LinkType | None:
    for pattern, link_type in rules:
        if pattern.search(sentence):
            return link_type
    return None


def infer_link_type(*, kind: DocKind, sentence: str) -> LinkType:
    """Pick a link type from the source doc's kind, letting its own phrasing override."""
    phrased = _match_phrasing(sentence=sentence, rules=KIND_PHRASING_RULES.get(kind, ()))
    if phrased is not None:
        return phrased
    return KIND_DEFAULT_LINK_TYPES.get(kind, FALLBACK_LINK_TYPE)


def _textual_link(*, src_id: str, dst_id: str, link_type: LinkType, sentence: str) -> Link:
    return Link(
        src_id=src_id,
        dst_id=dst_id,
        link_type=link_type,
        confidence=TEXTUAL_LINK_CONFIDENCE,
        evidence=sentence,
    )


def _reference_links(*, doc: Doc, target_id: str, sentence: str) -> tuple[Link, ...]:
    """Links one reference asserts, keeping the plain mention when phrasing inverts direction."""
    inverse_type = _match_phrasing(sentence=sentence, rules=INVERSE_PHRASING_RULES)
    if inverse_type is not None:
        return (
            _textual_link(
                src_id=target_id, dst_id=doc.doc_id, link_type=inverse_type, sentence=sentence
            ),
            _textual_link(
                src_id=doc.doc_id,
                dst_id=target_id,
                link_type=FALLBACK_LINK_TYPE,
                sentence=sentence,
            ),
        )
    forward_type = _match_phrasing(sentence=sentence, rules=FORWARD_PHRASING_RULES)
    return (
        _textual_link(
            src_id=doc.doc_id,
            dst_id=target_id,
            link_type=forward_type or infer_link_type(kind=doc.kind, sentence=sentence),
            sentence=sentence,
        ),
    )


def links_in_sentence(*, doc: Doc, sentence: str, index: FileNameIndex) -> tuple[Link, ...]:
    """Every link one sentence of a document asserts."""
    found: list[Link] = []
    for target_id in _referenced_doc_ids(sentence=sentence, index=index):
        if target_id != doc.doc_id:
            found.extend(_reference_links(doc=doc, target_id=target_id, sentence=sentence))
    return tuple(found)


class TextualLinkExtractor:
    """Reads links straight out of the text: markdown links, bare file names, and phrasing."""

    def extract(self, *, doc: Doc, corpus: tuple[Doc, ...]) -> tuple[Link, ...]:
        """Extract every link a document asserts about the rest of its corpus."""
        index = build_file_name_index(corpus=corpus)
        found: list[Link] = []
        for sentence in split_sentences(body=doc.body):
            found.extend(links_in_sentence(doc=doc, sentence=sentence, index=index))
        return deduplicate_links(links=tuple(found))
