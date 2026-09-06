"""Builds the classifier's system prompt and per-document payload."""

from __future__ import annotations

from ..constants import CLASSIFIER_EXCERPT_CHARS
from ..model import Doc
from .schema import KIND_DESCRIPTIONS, READ_WHEN_DESCRIPTIONS

EXCERPT_ELLIPSIS = "..."
DOCUMENT_SEPARATOR = "\n\n---\n\n"
HEADING_MARKER = "#"
MAX_HEADINGS_PER_DOC = 8


def _vocabulary_lines() -> str:
    kinds = "\n".join(f"- {kind.value}: {why}" for kind, why in KIND_DESCRIPTIONS.items())
    groups = "\n".join(f"- {group.value}: {why}" for group, why in READ_WHEN_DESCRIPTIONS.items())
    return f"Document kinds:\n{kinds}\n\nRead-when groups:\n{groups}"


def system_prompt() -> str:
    """Stable instruction block, cached across every classification request."""
    return (
        "You classify documents from an engineering project's corpus so an agent can "
        "decide which ones to load for a given task.\n\n"
        "For each document you are given a filename, its headings, and an excerpt. "
        "Assign the kind that best fits what the document is FOR, and the read-when "
        "group describing when an agent would need it.\n\n"
        f"{_vocabulary_lines()}\n\n"
        "Guidance:\n"
        "- The every_time group is expensive; reserve it for the brief, the standing "
        "rules, and lookup tables. Most documents are not every_time.\n"
        "- A document about one surface or milestone is in_area, and its area is a "
        "short slug naming that surface.\n"
        "- Audits, deep design, and frozen history are rarely.\n"
        "- Set area to an empty string when the document is project-wide.\n"
        "- confidence is 0 to 1: how sure you are of the kind. Use a low value when "
        "the document could plausibly be two kinds.\n"
        "- Exactly one document in a project is the brief. Mark a document brief only "
        "if it is the single best starting point for someone new to the whole project. "
        "A brief is always every_time. If nothing in this batch is that, use no brief.\n"
        "- A document that hands work between sessions or people — handoffs, status "
        "reports, sign-offs, worklogs, leadership summaries — is generated: its content "
        "is derived from commits, PRs, and tickets rather than authored. Never milestone.\n"
        "- classification means a lookup table an agent reads a value out of. A "
        "requirements or product document is not a classification, however structured.\n"
        "- Classify every document you are given, keyed by the doc_id supplied."
    )


def _headings_of(*, doc: Doc) -> str:
    found = [line.strip() for line in doc.body.splitlines() if line.startswith(HEADING_MARKER)]
    return "\n".join(found[:MAX_HEADINGS_PER_DOC])


def _excerpt_of(*, doc: Doc) -> str:
    stripped = doc.body.strip()
    if len(stripped) <= CLASSIFIER_EXCERPT_CHARS:
        return stripped
    return stripped[:CLASSIFIER_EXCERPT_CHARS] + EXCERPT_ELLIPSIS


def describe_document(*, doc: Doc) -> str:
    """One document rendered for the model: id, filename, headings, excerpt."""
    return (
        f"doc_id: {doc.doc_id}\n"
        f"filename: {doc.path.name}\n"
        f"headings:\n{_headings_of(doc=doc)}\n"
        f"excerpt:\n{_excerpt_of(doc=doc)}"
    )


def batch_prompt(*, docs: tuple[Doc, ...]) -> str:
    """The user-turn payload for one batch of documents."""
    return DOCUMENT_SEPARATOR.join(describe_document(doc=doc) for doc in docs)
