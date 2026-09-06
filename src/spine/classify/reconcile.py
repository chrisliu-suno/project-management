"""Corpus-level invariants the per-batch classifier cannot enforce.

A batch sees at most CLASSIFIER_BATCH_SIZE documents, so no single call can tell
whether another batch already claimed the brief.
"""

from __future__ import annotations

from dataclasses import replace

from ..model import DocKind, ReadWhen
from .client import Classification

DEMOTED_BRIEF_KIND = DocKind.AREA_DESIGN
DEMOTED_BRIEF_READ_WHEN = ReadWhen.IN_AREA


def _brief_ids(*, verdicts: dict[str, Classification]) -> tuple[str, ...]:
    return tuple(
        doc_id for doc_id, verdict in verdicts.items() if verdict.kind is DocKind.BRIEF
    )


def enforce_single_brief(*, verdicts: dict[str, Classification]) -> dict[str, Classification]:
    """Keep the most confident brief; demote the rest.

    Ties break on doc id so the winner does not depend on iteration order.
    """
    claimants = _brief_ids(verdicts=verdicts)
    if len(claimants) <= 1:
        return dict(verdicts)
    winner = min(claimants, key=lambda doc_id: (-verdicts[doc_id].confidence, doc_id))
    reconciled = dict(verdicts)
    for doc_id in claimants:
        if doc_id == winner:
            continue
        reconciled[doc_id] = replace(
            verdicts[doc_id],
            kind=DEMOTED_BRIEF_KIND,
            read_when=DEMOTED_BRIEF_READ_WHEN,
        )
    return reconciled


def enforce_brief_is_every_time(
    *, verdicts: dict[str, Classification]
) -> dict[str, Classification]:
    """The brief is read on every task by definition; a brief filed elsewhere is incoherent."""
    return {
        doc_id: (
            replace(verdict, read_when=ReadWhen.EVERY_TIME)
            if verdict.kind is DocKind.BRIEF
            else verdict
        )
        for doc_id, verdict in verdicts.items()
    }


def reconcile(*, verdicts: dict[str, Classification]) -> dict[str, Classification]:
    """Apply every corpus-level invariant, in order."""
    return enforce_brief_is_every_time(verdicts=enforce_single_brief(verdicts=verdicts))
