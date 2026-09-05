"""Budget-bounded selection of the documents a session is given."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ..constants import (
    BULK_INJECTION_GROUP_ORDER,
    EVERY_TIME_RESERVED_LINES,
    MAX_LINES_PER_READ_WHEN,
    ON_REQUEST_GROUP_ORDER,
    PICK_REASON_ALL_FIT,
    PICK_REASON_BUDGET_EXHAUSTED,
    PICK_REASON_EVERY_TIME_OVER_RESERVE,
    PICK_REASON_NO_CANDIDATES,
)
from ..model import Doc, Project, ReadWhen, Selection
from ..ports import GraphStore
from .rank import NeighbourLookup, no_neighbours, rank_docs


@dataclass(frozen=True, slots=True)
class GroupFill:
    """What one read-when group contributed to a selection."""

    chosen: tuple[Doc, ...]
    dropped: tuple[Doc, ...]
    lines_used: int


def neighbour_lookup_for(*, graph_store: GraphStore) -> NeighbourLookup:
    """Both-direction neighbour ids, read through the GraphStore protocol."""

    def lookup(*, doc_id: str) -> frozenset[str]:
        outbound = graph_store.outbound(doc_id=doc_id)
        inbound = graph_store.inbound(doc_id=doc_id)
        return frozenset(link.dst_id for link in outbound) | frozenset(
            link.src_id for link in inbound
        )

    return lookup


def group_allowance(*, group: ReadWhen, remaining_lines: int) -> int:
    """Lines a group may spend: what is left of the budget, capped by its own limit."""
    cap = MAX_LINES_PER_READ_WHEN[group]
    if group == ReadWhen.EVERY_TIME:
        cap = min(cap, EVERY_TIME_RESERVED_LINES)
    return max(0, min(remaining_lines, cap))


def fill_group(
    *,
    candidates: Iterable[Doc],
    allowance: int,
    chosen_ids: frozenset[str],
    task_context: str,
    neighbours_of: NeighbourLookup = no_neighbours,
) -> GroupFill:
    """Take the highest ranked candidates that still fit, dropping the ones that do not."""
    chosen: list[Doc] = []
    dropped: list[Doc] = []
    lines_used = 0
    taken_ids = set(chosen_ids)
    pending = list(candidates)
    while pending:
        best = rank_docs(
            docs=pending,
            task_context=task_context,
            chosen_ids=frozenset(taken_ids),
            neighbours_of=neighbours_of,
        )[0]
        pending.pop(next(index for index, doc in enumerate(pending) if doc is best))
        if lines_used + best.line_count <= allowance:
            chosen.append(best)
            taken_ids.add(best.doc_id)
            lines_used += best.line_count
        else:
            dropped.append(best)
    return GroupFill(chosen=tuple(chosen), dropped=tuple(dropped), lines_used=lines_used)


def reason_for(*, chosen: tuple[Doc, ...], dropped: tuple[Doc, ...]) -> str:
    """Machine-readable note on why the selection stopped where it did."""
    if any(doc.read_when == ReadWhen.EVERY_TIME for doc in dropped):
        return PICK_REASON_EVERY_TIME_OVER_RESERVE
    if dropped:
        return PICK_REASON_BUDGET_EXHAUSTED
    if not chosen:
        return PICK_REASON_NO_CANDIDATES
    return PICK_REASON_ALL_FIT


class BudgetedPicker:
    """Picks documents within a line budget, reserving the every-time group first.

    Candidates are the bulk-injection groups, plus RARELY when the caller asks for it.
    """

    def __init__(self, *, graph_store: GraphStore, should_include_rarely: bool = False) -> None:
        self._graph_store = graph_store
        self._should_include_rarely = should_include_rarely

    def pick(self, *, project: Project, task_context: str, line_budget: int) -> Selection:
        """Highest ranked docs that fit the budget, plus what the budget forced out."""
        corpus = self._graph_store.docs_for_project(project_slug=project.slug)
        neighbours_of = neighbour_lookup_for(graph_store=self._graph_store)
        chosen: list[Doc] = []
        dropped: list[Doc] = []
        lines_used = 0
        for group in self._group_order():
            candidates = [doc for doc in corpus if doc.read_when == group]
            if not candidates:
                continue
            fill = fill_group(
                candidates=candidates,
                allowance=group_allowance(group=group, remaining_lines=line_budget - lines_used),
                chosen_ids=frozenset(doc.doc_id for doc in chosen),
                task_context=task_context,
                neighbours_of=neighbours_of,
            )
            chosen.extend(fill.chosen)
            dropped.extend(fill.dropped)
            lines_used += fill.lines_used
        return Selection(
            chosen=tuple(chosen),
            dropped=tuple(dropped),
            total_lines=lines_used,
            reason=reason_for(chosen=tuple(chosen), dropped=tuple(dropped)),
        )

    def _group_order(self) -> tuple[ReadWhen, ...]:
        if self._should_include_rarely:
            return BULK_INJECTION_GROUP_ORDER + ON_REQUEST_GROUP_ORDER
        return BULK_INJECTION_GROUP_ORDER
