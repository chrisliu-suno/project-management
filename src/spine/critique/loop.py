"""The unattended draft-critique-revise loop."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..constants import CRITIQUE_MAX_ROUNDS
from ..style.rules import StyleNote, review
from .model import CLEAN, NO_PROGRESS, ROUNDS_EXHAUSTED, Refinement, Round


@runtime_checkable
class Reviser(Protocol):
    """Reads a draft and rewrites it against a list of notes."""

    def critique(self, *, text: str) -> tuple[StyleNote, ...]: ...

    def revise(self, *, text: str, notes: tuple[StyleNote, ...]) -> str: ...


def _notes_for(*, text: str, reviser: Reviser | None) -> tuple[StyleNote, ...]:
    """Deterministic style notes first, then whatever a model adds."""
    mechanical = review(text=text)
    if reviser is None:
        return mechanical
    return (*mechanical, *reviser.critique(text=text))


def refine(
    *, text: str, reviser: Reviser | None = None, max_rounds: int = CRITIQUE_MAX_ROUNDS
) -> Refinement:
    """Critique and revise until the notes run out, the rounds do, or nothing changes."""
    rounds: list[Round] = []
    current = text
    for number in range(1, max_rounds + 1):
        notes = _notes_for(text=current, reviser=reviser)
        if not notes:
            return Refinement(text=current, stop_reason=CLEAN, rounds=tuple(rounds))
        if reviser is None:
            return Refinement(
                text=current, stop_reason=ROUNDS_EXHAUSTED, rounds=tuple(rounds), remaining=notes
            )
        revised = reviser.revise(text=current, notes=notes)
        rounds.append(Round(number=number, notes=notes, text_before=current, text_after=revised))
        if revised == current:
            return Refinement(
                text=current, stop_reason=NO_PROGRESS, rounds=tuple(rounds), remaining=notes
            )
        current = revised
    return Refinement(
        text=current,
        stop_reason=ROUNDS_EXHAUSTED,
        rounds=tuple(rounds),
        remaining=_notes_for(text=current, reviser=reviser),
    )
