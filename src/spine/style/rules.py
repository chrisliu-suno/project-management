"""Plain-wording checks for anything a human will read."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..constants import STYLE_MAX_SENTENCE_WORDS

SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z'-]*")
CODE_FENCE_PATTERN = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_PATTERN = re.compile(r"`[^`]*`")
URL_PATTERN = re.compile(r"https?://\S+")
TABLE_ROW_PREFIX = "|"
HEADING_PREFIX = "#"
QUOTE_PREFIX = ">"
LIST_ITEM_PATTERN = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")

HEDGE_WORDS = (
    "just",
    "really",
    "basically",
    "simply",
    "actually",
    "quite",
    "very",
    "somewhat",
    "arguably",
)
PUFFERY_PHRASES = (
    "carefully verified",
    "comprehensive",
    "robust",
    "seamless",
    "leverage",
    "utilize",
    "in order to",
    "it should be noted",
    "at the end of the day",
)
SHOUTING_PATTERN = re.compile(r"\b(?:CRITICAL|IMPORTANT|MUST|NEVER|ALWAYS)\b")


@dataclass(frozen=True, slots=True)
class StyleNote:
    """One thing worth changing before a human reads this."""

    code: str
    detail: str
    excerpt: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail, "excerpt": self.excerpt}


def strip_code(*, text: str) -> str:
    """Prose only: code blocks and URLs are not written for a reader."""
    without_fences = CODE_FENCE_PATTERN.sub(" ", text)
    without_inline = INLINE_CODE_PATTERN.sub(" ", without_fences)
    return URL_PATTERN.sub(" ", without_inline)


def _is_prose_line(*, line: str) -> bool:
    """Table rows, headings, and quote markers carry no sentences to measure."""
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith(
        (TABLE_ROW_PREFIX, HEADING_PREFIX, QUOTE_PREFIX)
    )


def prose_blocks(*, text: str) -> tuple[str, ...]:
    """Runs of prose, split wherever markdown starts a new one.

    A list item is its own block: without this a bulleted list reads as one
    unpunctuated sentence hundreds of words long.
    """
    blocks: list[list[str]] = []
    for line in strip_code(text=text).splitlines():
        if not _is_prose_line(line=line):
            blocks.append([])
            continue
        if LIST_ITEM_PATTERN.match(line):
            blocks.append([LIST_ITEM_PATTERN.sub("", line)])
            continue
        if not blocks:
            blocks.append([])
        blocks[-1].append(line.strip())
    return tuple(" ".join(block) for block in blocks if block)


def sentences_in(*, text: str) -> tuple[str, ...]:
    """Every sentence in the prose, ignoring markdown scaffolding."""
    return tuple(
        sentence.strip()
        for block in prose_blocks(text=text)
        for sentence in SENTENCE_SPLIT_PATTERN.split(block)
        if sentence.strip()
    )


def prose_text(*, text: str) -> str:
    """The document with markdown scaffolding removed."""
    return "\n".join(prose_blocks(text=text))


def long_sentences(*, text: str) -> tuple[StyleNote, ...]:
    """Sentences past the length a reader can hold in one pass."""
    found = []
    for sentence in sentences_in(text=text):
        count = len(WORD_PATTERN.findall(sentence))
        if count > STYLE_MAX_SENTENCE_WORDS:
            found.append(
                StyleNote(
                    code="long_sentence",
                    detail=f"{count} words; split it",
                    excerpt=sentence[:80],
                )
            )
    return tuple(found)


def _phrase_notes(*, text: str, phrases: tuple[str, ...], code: str, detail: str):
    lowered = text.lower()
    return tuple(
        StyleNote(code=code, detail=f"{detail}: {phrase!r}", excerpt=phrase)
        for phrase in phrases
        if phrase in lowered
    )


def hedges(*, text: str) -> tuple[StyleNote, ...]:
    """Filler words that weaken a sentence without adding meaning."""
    lowered = prose_text(text=text).lower()
    words = set(WORD_PATTERN.findall(lowered))
    return tuple(
        StyleNote(code="hedge", detail=f"drop {word!r}", excerpt=word)
        for word in HEDGE_WORDS
        if word in words
    )


def puffery(*, text: str) -> tuple[StyleNote, ...]:
    """Phrases that claim quality instead of showing it."""
    return _phrase_notes(
        text=prose_text(text=text),
        phrases=PUFFERY_PHRASES,
        code="puffery",
        detail="say the thing plainly",
    )


def shouting(*, text: str) -> tuple[StyleNote, ...]:
    """Emphasis carrying no information once everything is emphasised."""
    hits = SHOUTING_PATTERN.findall(prose_text(text=text))
    if not hits:
        return ()
    return (
        StyleNote(
            code="shouting",
            detail=f"{len(hits)} shouted word(s); state the constraint and the reason",
            excerpt=", ".join(sorted(set(hits))),
        ),
    )


def review(*, text: str) -> tuple[StyleNote, ...]:
    """Every style note for one piece of prose."""
    return (
        *long_sentences(text=text),
        *hedges(text=text),
        *puffery(text=text),
        *shouting(text=text),
    )
