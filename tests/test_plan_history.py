"""Plan state recorded over time, so progress reads as a series."""

from __future__ import annotations

from pathlib import Path

import pytest

from spine.constants import SPINE_HOME_ENV_VAR
from spine.model import Doc, DocKind, ReadWhen
from spine.plan import plan_in
from spine.plan.history import PlanHistoryStore, PlanPoint, point_from

PROJECT_SLUG = "alpha"
FIRST_STAMP = "2026-09-01T00:00:00+00:00"
SECOND_STAMP = "2026-09-02T00:00:00+00:00"


@pytest.fixture(autouse=True)
def isolated_spine_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SPINE_HOME_ENV_VAR, str(tmp_path))


def _point(*, taken_at: str, done: int = 1, items: int = 4, blocked: int = 0) -> PlanPoint:
    return PlanPoint(
        project_slug=PROJECT_SLUG,
        taken_at=taken_at,
        done_count=done,
        item_count=items,
        blocked_count=blocked,
        milestone="Phase 1",
    )


def test_remaining_is_items_minus_done() -> None:
    assert _point(taken_at=FIRST_STAMP, done=1, items=4).remaining == 3


def test_remaining_never_goes_negative() -> None:
    assert _point(taken_at=FIRST_STAMP, done=9, items=4).remaining == 0


def test_the_first_reading_is_stored() -> None:
    assert PlanHistoryStore().record(point=_point(taken_at=FIRST_STAMP)) is True


def test_an_unchanged_reading_is_dropped() -> None:
    store = PlanHistoryStore()
    store.record(point=_point(taken_at=FIRST_STAMP))
    assert store.record(point=_point(taken_at=SECOND_STAMP)) is False
    assert len(store.series(project_slug=PROJECT_SLUG)) == 1


def test_a_changed_reading_is_stored() -> None:
    store = PlanHistoryStore()
    store.record(point=_point(taken_at=FIRST_STAMP, done=1))
    assert store.record(point=_point(taken_at=SECOND_STAMP, done=2)) is True
    assert len(store.series(project_slug=PROJECT_SLUG)) == 2


def test_a_changed_blocked_count_counts_as_movement() -> None:
    store = PlanHistoryStore()
    store.record(point=_point(taken_at=FIRST_STAMP, blocked=0))
    assert store.record(point=_point(taken_at=SECOND_STAMP, blocked=1)) is True


def test_a_new_milestone_counts_as_movement() -> None:
    store = PlanHistoryStore()
    store.record(point=_point(taken_at=FIRST_STAMP))
    moved = PlanPoint(
        project_slug=PROJECT_SLUG,
        taken_at=SECOND_STAMP,
        done_count=1,
        item_count=4,
        blocked_count=0,
        milestone="Phase 2",
    )
    assert store.record(point=moved) is True


def test_the_series_is_oldest_first() -> None:
    store = PlanHistoryStore()
    store.record(point=_point(taken_at=SECOND_STAMP, done=2))
    store.record(point=_point(taken_at=FIRST_STAMP, done=1))
    stamps = [point.taken_at for point in store.series(project_slug=PROJECT_SLUG)]
    assert stamps == sorted(stamps)


def test_another_project_has_its_own_series() -> None:
    store = PlanHistoryStore()
    store.record(point=_point(taken_at=FIRST_STAMP))
    assert store.series(project_slug="beta") == ()


def test_a_project_with_no_readings_has_an_empty_series() -> None:
    assert PlanHistoryStore().series(project_slug=PROJECT_SLUG) == ()


TABLE_DOC = """# Audit

| item | Status |
|---|---|
| a | **SHIPPED** |
| b | **NOT BUILT** |
"""


def test_a_reading_is_taken_from_plan_state() -> None:
    doc = Doc(
        doc_id=f"{PROJECT_SLUG}:audit",
        path=Path("audit.md"),
        kind=DocKind.ROLLOUT,
        read_when=ReadWhen.IN_AREA,
        title="audit",
        body=TABLE_DOC,
        project_slug=PROJECT_SLUG,
    )
    point = point_from(state=plan_in(doc=doc), taken_at=FIRST_STAMP)
    assert point.done_count == 1
    assert point.item_count == 2
    assert point.remaining == 1


def test_cli_exposes_the_history_verb() -> None:
    from spine.cli import build_parser

    parsed = build_parser().parse_args(["plan", "history", "--project", "x"])
    assert parsed.handler is not None


def test_the_page_draws_a_burndown() -> None:
    from spine.serve.page import render_page

    page = render_page()
    assert "function burndown" in page
    assert "polyline" in page
