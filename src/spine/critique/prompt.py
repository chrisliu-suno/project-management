"""Prompts for the critique and revise halves of the loop."""

from __future__ import annotations

from ..style.rules import StyleNote

CRITIQUE_SYSTEM = (
    "You review project documents before a busy engineer reads them.\n"
    "Report only defects a reader would trip on: a claim without support, "
    "a decision stated without what it rules out, a section that repeats "
    "another, wording that hides the point.\n"
    "Do not report taste. Do not restate the document. "
    "An empty list is the right answer for a document that reads well."
)

REVISE_SYSTEM = (
    "You revise a project document against a list of notes.\n"
    "Fix exactly what the notes name and change nothing else. "
    "Keep the author's structure, headings, and facts. "
    "Return the full revised document and no commentary."
)

CRITIQUE_TEMPLATE = "Review this document.\n\n---\n{text}\n---"
REVISE_TEMPLATE = "Notes:\n{notes}\n\nDocument:\n---\n{text}\n---"
NOTE_LINE_TEMPLATE = "- [{code}] {detail}"


def critique_prompt(*, text: str) -> str:
    """The user turn asking for defects in one document."""
    return CRITIQUE_TEMPLATE.format(text=text)


def revise_prompt(*, text: str, notes: tuple[StyleNote, ...]) -> str:
    """The user turn asking for a rewrite against specific notes."""
    rendered = "\n".join(
        NOTE_LINE_TEMPLATE.format(code=note.code, detail=note.detail) for note in notes
    )
    return REVISE_TEMPLATE.format(notes=rendered, text=text)
