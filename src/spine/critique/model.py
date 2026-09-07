"""What one pass of critique-and-revise produced."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..constants import CRITIQUE_MAX_GROWTH_RATIO
from ..style.rules import StyleNote


@dataclass(frozen=True, slots=True)
class Round:
    """One critique, and the text that came back from acting on it."""

    number: int
    notes: tuple[StyleNote, ...]
    text_before: str
    text_after: str

    @property
    def changed_anything(self) -> bool:
        return self.text_before != self.text_after


class RefinementStop(str):
    """Why the loop stopped, as a printable reason."""

    __slots__ = ()


CLEAN = RefinementStop("clean")
ROUNDS_EXHAUSTED = RefinementStop("rounds_exhausted")
NO_PROGRESS = RefinementStop("no_progress")


@dataclass(frozen=True, slots=True)
class Refinement:
    """The final text plus the trail that produced it."""

    text: str
    stop_reason: RefinementStop
    rounds: tuple[Round, ...] = field(default=())
    remaining: tuple[StyleNote, ...] = field(default=())

    @property
    def is_clean(self) -> bool:
        return self.stop_reason == CLEAN

    @property
    def has_grown_suspiciously(self) -> bool:
        """A revision much longer than the draft has added claims, not fixed wording."""
        if not self.rounds:
            return False
        original = len(self.rounds[0].text_before)
        return original > 0 and len(self.text) > original * CRITIQUE_MAX_GROWTH_RATIO

    def summary_lines(self) -> tuple[str, ...]:
        """One line per round, then the verdict."""
        trail = tuple(
            f"round {each.number}: {len(each.notes)} note(s), "
            f"{'revised' if each.changed_anything else 'unchanged'}"
            for each in self.rounds
        )
        verdict = f"stopped: {self.stop_reason} ({len(self.remaining)} note(s) left)"
        if not self.has_grown_suspiciously:
            return (*trail, verdict)
        growth = f"grew past {CRITIQUE_MAX_GROWTH_RATIO}x the draft; check for invented claims"
        return (*trail, verdict, growth)
