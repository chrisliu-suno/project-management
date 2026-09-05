"""Guards on M4: budgeted selection, deterministic ranking, and the pick record."""

from __future__ import annotations

import dataclasses
import sqlite3
from pathlib import Path

import pytest

import spine.index
import spine.picker.select as select_module
import spine.registry
from spine.cli import build_parser, main
from spine.constants import (
    EVERY_TIME_RESERVED_LINES,
    GRAPH_STORE_FACTORY_NAME,
    INJECTION_LINE_BUDGET,
    MARKDOWN_HEADING_PREFIX,
    MAX_LINES_PER_READ_WHEN,
    MIN_CONFIDENCE_FOR_SILENT_PICK,
    PICK_REASON_ALL_FIT,
    PICK_REASON_BUDGET_EXHAUSTED,
    PICK_REASON_EVERY_TIME_OVER_RESERVE,
    PICK_REASON_NO_CANDIDATES,
    PICKS_DB_FILE_NAME,
    PICKS_TABLE_NAME,
    PROJECT_REGISTRY_FACTORY_NAME,
    SPINE_HOME_ENV_VAR,
)
from spine.model import Doc, DocKind, Link, LinkType, Project, ReadWhen, Selection
from spine.paths import picks_db_path
from spine.picker import (
    EXIT_OK,
    EXIT_UNKNOWN_PROJECT,
    BudgetedPicker,
    SqlitePickRecorder,
    fill_group,
    group_allowance,
    summarize_picks,
)
from spine.picker.rank import area_score, rank_docs, terms_in
from spine.ports import ContextPicker, PickRecorder

PROJECT_SLUG = "alpha"
OTHER_PROJECT_SLUG = "beta"
TASK_CONTEXT = "tune the uplink allocator for overlapping windows"
SMALL_DOC_LINES = 100
ARGPARSE_HELP_EXIT_CODE = 0

ROUND_TRIP_SQL = (
    "SELECT session_id, project_slug, chosen_doc_ids, dropped_doc_ids, "
    f"total_lines, reason, confidence FROM {PICKS_TABLE_NAME}"
)


def make_doc(
    *,
    doc_id: str,
    read_when: ReadWhen,
    lines: int = SMALL_DOC_LINES,
    title: str = "A document",
    headings: tuple[str, ...] = (),
    area: str | None = None,
    kind: DocKind = DocKind.AREA_DESIGN,
    project_slug: str = PROJECT_SLUG,
) -> Doc:
    """A Doc with an exact line count, built without depending on the loader module."""
    heading_lines = [f"{MARKDOWN_HEADING_PREFIX} {heading}" for heading in headings]
    filler = [f"body line {number}" for number in range(lines - len(heading_lines))]
    return Doc(
        doc_id=doc_id,
        path=Path(f"{doc_id}.md"),
        kind=kind,
        read_when=read_when,
        title=title,
        body="\n".join(heading_lines + filler),
        project_slug=project_slug,
        area=area,
    )


class FakeGraphStore:
    """In-memory stand-in shaped like the GraphStore protocol."""

    def __init__(self, *, docs: tuple[Doc, ...], links: tuple[Link, ...] = ()) -> None:
        self._docs = docs
        self._links = links

    def replace_project(
        self, *, project_slug: str, docs: tuple[Doc, ...], links: tuple[Link, ...]
    ) -> None:
        self._docs = docs
        self._links = links

    def docs_for_project(self, *, project_slug: str) -> tuple[Doc, ...]:
        return tuple(doc for doc in self._docs if doc.project_slug == project_slug)

    def outbound(self, *, doc_id: str, link_type: LinkType | None = None) -> tuple[Link, ...]:
        return tuple(link for link in self._links if link.src_id == doc_id)

    def inbound(self, *, doc_id: str, link_type: LinkType | None = None) -> tuple[Link, ...]:
        return tuple(link for link in self._links if link.dst_id == doc_id)

    def orphans(self, *, project_slug: str) -> tuple[Doc, ...]:
        return ()


class FakeRegistry:
    """Registry stand-in that knows at most one slug."""

    def __init__(self, *, known: Project | None) -> None:
        self._known = known

    def all_projects(self) -> tuple[Project, ...]:
        return () if self._known is None else (self._known,)

    def get(self, slug: str) -> Project | None:
        if self._known is not None and self._known.slug == slug:
            return self._known
        return None


@pytest.fixture
def spine_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(SPINE_HOME_ENV_VAR, str(tmp_path))
    return tmp_path


@pytest.fixture
def project() -> Project:
    return Project(slug=PROJECT_SLUG, name="Alpha", docs_dir=Path("docs"))


def picker_over(
    *,
    docs: tuple[Doc, ...],
    links: tuple[Link, ...] = (),
    should_include_rarely: bool = False,
) -> BudgetedPicker:
    return BudgetedPicker(
        graph_store=FakeGraphStore(docs=docs, links=links),
        should_include_rarely=should_include_rarely,
    )


def chosen_ids_of(*, selection: Selection) -> list[str]:
    return [doc.doc_id for doc in selection.chosen]


def dropped_ids_of(*, selection: Selection) -> list[str]:
    return [doc.doc_id for doc in selection.dropped]


def record_pick(*, session_id: str, selection: Selection, confidence: float) -> None:
    SqlitePickRecorder().record(
        session_id=session_id,
        project_slug=PROJECT_SLUG,
        selection=selection,
        confidence=confidence,
    )


def test_picker_and_recorder_satisfy_their_protocols() -> None:
    assert isinstance(picker_over(docs=()), ContextPicker)
    assert isinstance(SqlitePickRecorder(), PickRecorder)


def test_every_time_docs_are_chosen_ahead_of_in_area(project: Project) -> None:
    docs = (
        make_doc(doc_id="z-standing", read_when=ReadWhen.EVERY_TIME),
        make_doc(doc_id="a-area", read_when=ReadWhen.IN_AREA),
    )
    selection = picker_over(docs=docs).pick(
        project=project, task_context=TASK_CONTEXT, line_budget=INJECTION_LINE_BUDGET
    )
    assert chosen_ids_of(selection=selection) == ["z-standing", "a-area"]


def test_in_area_docs_are_dropped_before_any_every_time_doc(project: Project) -> None:
    docs = (
        make_doc(doc_id="standing-one", read_when=ReadWhen.EVERY_TIME),
        make_doc(doc_id="standing-two", read_when=ReadWhen.EVERY_TIME),
        make_doc(doc_id="area-one", read_when=ReadWhen.IN_AREA),
    )
    selection = picker_over(docs=docs).pick(
        project=project, task_context=TASK_CONTEXT, line_budget=SMALL_DOC_LINES * 2
    )
    assert chosen_ids_of(selection=selection) == ["standing-one", "standing-two"]
    assert dropped_ids_of(selection=selection) == ["area-one"]
    assert selection.reason == PICK_REASON_BUDGET_EXHAUSTED


def test_oversized_every_time_doc_is_dropped_and_reported(project: Project) -> None:
    docs = (
        make_doc(
            doc_id="standing-huge",
            read_when=ReadWhen.EVERY_TIME,
            lines=EVERY_TIME_RESERVED_LINES + 1,
        ),
    )
    selection = picker_over(docs=docs).pick(
        project=project, task_context=TASK_CONTEXT, line_budget=INJECTION_LINE_BUDGET
    )
    assert selection.chosen == ()
    assert dropped_ids_of(selection=selection) == ["standing-huge"]
    assert selection.reason == PICK_REASON_EVERY_TIME_OVER_RESERVE


def test_every_time_doc_of_exactly_the_reserved_size_still_fits(project: Project) -> None:
    docs = (
        make_doc(
            doc_id="standing-exact",
            read_when=ReadWhen.EVERY_TIME,
            lines=EVERY_TIME_RESERVED_LINES,
        ),
    )
    selection = picker_over(docs=docs).pick(
        project=project, task_context=TASK_CONTEXT, line_budget=INJECTION_LINE_BUDGET
    )
    assert chosen_ids_of(selection=selection) == ["standing-exact"]
    assert selection.total_lines == EVERY_TIME_RESERVED_LINES
    assert selection.reason == PICK_REASON_ALL_FIT


def test_every_time_reservation_caps_the_group_below_its_size_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        select_module.MAX_LINES_PER_READ_WHEN,
        ReadWhen.EVERY_TIME,
        EVERY_TIME_RESERVED_LINES * 2,
    )
    allowance = group_allowance(
        group=ReadWhen.EVERY_TIME, remaining_lines=INJECTION_LINE_BUDGET * 2
    )
    assert allowance == EVERY_TIME_RESERVED_LINES


def test_group_allowance_is_capped_by_the_group_size_limit() -> None:
    allowance = group_allowance(
        group=ReadWhen.IN_AREA, remaining_lines=MAX_LINES_PER_READ_WHEN[ReadWhen.IN_AREA] * 2
    )
    assert allowance == MAX_LINES_PER_READ_WHEN[ReadWhen.IN_AREA]


@pytest.mark.parametrize("line_budget", [0, 1, 99, 100, 250, INJECTION_LINE_BUDGET])
def test_budget_is_never_exceeded(project: Project, line_budget: int) -> None:
    docs = tuple(
        make_doc(
            doc_id=f"doc-{index}",
            read_when=ReadWhen.EVERY_TIME if index % 2 == 0 else ReadWhen.IN_AREA,
        )
        for index in range(8)
    )
    selection = picker_over(docs=docs).pick(
        project=project, task_context=TASK_CONTEXT, line_budget=line_budget
    )
    assert selection.total_lines <= line_budget
    assert selection.total_lines == sum(doc.line_count for doc in selection.chosen)
    assert len(selection.chosen) + len(selection.dropped) == len(docs)


def test_a_negative_budget_selects_nothing(project: Project) -> None:
    docs = (make_doc(doc_id="standing", read_when=ReadWhen.EVERY_TIME),)
    selection = picker_over(docs=docs).pick(
        project=project, task_context=TASK_CONTEXT, line_budget=-INJECTION_LINE_BUDGET
    )
    assert selection.chosen == ()
    assert selection.total_lines == 0
    assert dropped_ids_of(selection=selection) == ["standing"]


def test_an_empty_corpus_reports_no_candidates(project: Project) -> None:
    selection = picker_over(docs=()).pick(
        project=project, task_context=TASK_CONTEXT, line_budget=INJECTION_LINE_BUDGET
    )
    assert selection.chosen == ()
    assert selection.dropped == ()
    assert selection.reason == PICK_REASON_NO_CANDIDATES


def test_a_doc_that_does_not_fit_does_not_stop_smaller_ones() -> None:
    candidates = [
        make_doc(doc_id="a-big", read_when=ReadWhen.IN_AREA, lines=SMALL_DOC_LINES * 2),
        make_doc(doc_id="z-small", read_when=ReadWhen.IN_AREA, lines=SMALL_DOC_LINES),
    ]
    filled = fill_group(
        candidates=candidates,
        allowance=SMALL_DOC_LINES,
        chosen_ids=frozenset(),
        task_context=TASK_CONTEXT,
    )
    assert [doc.doc_id for doc in filled.chosen] == ["z-small"]
    assert [doc.doc_id for doc in filled.dropped] == ["a-big"]
    assert filled.lines_used == SMALL_DOC_LINES


def test_log_and_looked_up_groups_are_never_selected(project: Project) -> None:
    docs = (
        make_doc(doc_id="standing", read_when=ReadWhen.EVERY_TIME),
        make_doc(doc_id="decision-log", read_when=ReadWhen.LOG, kind=DocKind.DECISION_LOG),
        make_doc(doc_id="generated", read_when=ReadWhen.LOOKED_UP, kind=DocKind.GENERATED),
    )
    selection = picker_over(docs=docs).pick(
        project=project, task_context=TASK_CONTEXT, line_budget=INJECTION_LINE_BUDGET
    )
    touched = {doc.doc_id for doc in selection.chosen + selection.dropped}
    assert touched == {"standing"}
    assert selection.reason == PICK_REASON_ALL_FIT


def test_rarely_group_is_excluded_unless_requested(project: Project) -> None:
    docs = (make_doc(doc_id="archive", read_when=ReadWhen.RARELY),)
    default_selection = picker_over(docs=docs).pick(
        project=project, task_context=TASK_CONTEXT, line_budget=INJECTION_LINE_BUDGET
    )
    requested_selection = picker_over(docs=docs, should_include_rarely=True).pick(
        project=project, task_context=TASK_CONTEXT, line_budget=INJECTION_LINE_BUDGET
    )
    assert default_selection.chosen == ()
    assert default_selection.dropped == ()
    assert default_selection.reason == PICK_REASON_NO_CANDIDATES
    assert chosen_ids_of(selection=requested_selection) == ["archive"]


def test_docs_from_another_project_are_not_candidates(project: Project) -> None:
    docs = (
        make_doc(doc_id="mine", read_when=ReadWhen.EVERY_TIME),
        make_doc(doc_id="theirs", read_when=ReadWhen.EVERY_TIME, project_slug=OTHER_PROJECT_SLUG),
    )
    selection = picker_over(docs=docs).pick(
        project=project, task_context=TASK_CONTEXT, line_budget=INJECTION_LINE_BUDGET
    )
    assert chosen_ids_of(selection=selection) == ["mine"]


def test_repeated_picks_are_identical_whatever_the_corpus_order(project: Project) -> None:
    docs = tuple(
        make_doc(
            doc_id=f"area-{index}",
            read_when=ReadWhen.IN_AREA,
            title=f"Uplink surface {index}",
            area="uplink" if index % 3 == 0 else "telemetry",
        )
        for index in range(6)
    )
    orderings = (docs, tuple(reversed(docs)), docs[3:] + docs[:3])
    for ordering in orderings:
        selection = picker_over(docs=ordering).pick(
            project=project, task_context=TASK_CONTEXT, line_budget=SMALL_DOC_LINES * 3
        )
        assert chosen_ids_of(selection=selection) == ["area-0", "area-3", "area-1"]
        assert dropped_ids_of(selection=selection) == ["area-2", "area-4", "area-5"]


def test_ties_break_by_doc_id(project: Project) -> None:
    docs = tuple(
        make_doc(doc_id=doc_id, read_when=ReadWhen.IN_AREA)
        for doc_id in ("echo", "delta", "charlie", "bravo", "alpha")
    )
    selection = picker_over(docs=docs).pick(
        project=project, task_context=TASK_CONTEXT, line_budget=SMALL_DOC_LINES * 2
    )
    assert chosen_ids_of(selection=selection) == ["alpha", "bravo"]
    assert dropped_ids_of(selection=selection) == ["charlie", "delta", "echo"]


def test_ranking_prefers_the_matching_area() -> None:
    docs = (
        make_doc(doc_id="a-telemetry", read_when=ReadWhen.IN_AREA, area="telemetry"),
        make_doc(doc_id="z-uplink", read_when=ReadWhen.IN_AREA, area="uplink"),
    )
    ranked = rank_docs(docs=docs, task_context=TASK_CONTEXT)
    assert ranked[0].doc_id == "z-uplink"


def test_an_area_matches_only_when_all_of_its_terms_appear() -> None:
    partly_named = make_doc(doc_id="partial", read_when=ReadWhen.IN_AREA, area="uplink scheduler")
    fully_named = make_doc(doc_id="full", read_when=ReadWhen.IN_AREA, area="uplink")
    task_terms = terms_in(text=TASK_CONTEXT)
    assert area_score(doc=partly_named, task_terms=task_terms) == 0.0
    assert area_score(doc=fully_named, task_terms=task_terms) > 0.0


def test_ranking_reads_headings_out_of_the_body() -> None:
    docs = (
        make_doc(doc_id="a-plain", read_when=ReadWhen.IN_AREA, title="Notes"),
        make_doc(
            doc_id="z-headed",
            read_when=ReadWhen.IN_AREA,
            title="Notes",
            headings=("Allocator windows",),
        ),
    )
    ranked = rank_docs(docs=docs, task_context=TASK_CONTEXT)
    assert ranked[0].doc_id == "z-headed"


def test_ranking_scores_overlap_as_a_share_not_a_count() -> None:
    docs = (
        make_doc(
            doc_id="a-verbose",
            read_when=ReadWhen.IN_AREA,
            title="Allocator billing ledger appendix",
        ),
        make_doc(doc_id="z-terse", read_when=ReadWhen.IN_AREA, title="Allocator"),
    )
    ranked = rank_docs(docs=docs, task_context=TASK_CONTEXT)
    assert ranked[0].doc_id == "z-terse"


def test_terms_shorter_than_the_minimum_are_ignored() -> None:
    assert terms_in(text="go up allocator") == frozenset({"allocator"})


def test_proximity_is_a_share_of_the_docs_already_chosen() -> None:
    docs = (
        make_doc(doc_id="a-one-link", read_when=ReadWhen.IN_AREA),
        make_doc(doc_id="z-both-links", read_when=ReadWhen.IN_AREA),
    )
    neighbours = {
        "a-one-link": frozenset({"standing-one"}),
        "z-both-links": frozenset({"standing-one", "standing-two"}),
    }

    def neighbours_of(*, doc_id: str) -> frozenset[str]:
        return neighbours[doc_id]

    ranked = rank_docs(
        docs=docs,
        task_context=TASK_CONTEXT,
        chosen_ids=frozenset({"standing-one", "standing-two"}),
        neighbours_of=neighbours_of,
    )
    assert ranked[0].doc_id == "z-both-links"


def test_picker_uses_graph_proximity_to_break_an_otherwise_equal_choice(
    project: Project,
) -> None:
    docs = (
        make_doc(doc_id="standing", read_when=ReadWhen.EVERY_TIME),
        make_doc(doc_id="a-far", read_when=ReadWhen.IN_AREA),
        make_doc(doc_id="z-near", read_when=ReadWhen.IN_AREA),
    )
    links = (Link(src_id="standing", dst_id="z-near", link_type=LinkType.CONSTRAINS),)
    selection = picker_over(docs=docs, links=links).pick(
        project=project, task_context=TASK_CONTEXT, line_budget=SMALL_DOC_LINES * 2
    )
    assert chosen_ids_of(selection=selection) == ["standing", "z-near"]


def test_recorder_round_trip(spine_home: Path, project: Project) -> None:
    selection = Selection(
        chosen=(make_doc(doc_id="standing", read_when=ReadWhen.EVERY_TIME),),
        dropped=(make_doc(doc_id="area-one", read_when=ReadWhen.IN_AREA),),
        total_lines=SMALL_DOC_LINES,
        reason=PICK_REASON_BUDGET_EXHAUSTED,
    )
    SqlitePickRecorder().record(
        session_id="session-one",
        project_slug=project.slug,
        selection=selection,
        confidence=MIN_CONFIDENCE_FOR_SILENT_PICK,
    )
    connection = sqlite3.connect(picks_db_path())
    try:
        row = connection.execute(ROUND_TRIP_SQL).fetchone()
    finally:
        connection.close()
    assert row == (
        "session-one",
        PROJECT_SLUG,
        "standing",
        "area-one",
        SMALL_DOC_LINES,
        PICK_REASON_BUDGET_EXHAUSTED,
        MIN_CONFIDENCE_FOR_SILENT_PICK,
    )


def test_recording_prints_nothing(spine_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    record_pick(
        session_id="session-one",
        selection=Selection(
            chosen=(make_doc(doc_id="standing", read_when=ReadWhen.EVERY_TIME),),
            reason=PICK_REASON_ALL_FIT,
        ),
        confidence=1.0,
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_recording_survives_an_unusable_database(tmp_path: Path) -> None:
    blocking_file = tmp_path / "blocking-file"
    blocking_file.write_text("not a directory")
    recorder = SqlitePickRecorder(db_path=blocking_file / PICKS_DB_FILE_NAME)
    recorder.record(
        session_id="session-one",
        project_slug=PROJECT_SLUG,
        selection=Selection(chosen=(), reason=PICK_REASON_NO_CANDIDATES),
        confidence=1.0,
    )
    assert summarize_picks(db_path=recorder.db_path).total_picks == 0


def test_summary_is_zeroed_before_anything_is_recorded(spine_home: Path) -> None:
    summary = summarize_picks()
    assert summary.total_picks == 0
    assert summary.low_confidence_picks == 0
    assert summary.every_time_dropped_picks == 0
    assert summary.no_in_area_match_picks == 0


def test_summary_returns_grouped_counts(spine_home: Path) -> None:
    every_time_doc = make_doc(doc_id="standing", read_when=ReadWhen.EVERY_TIME)
    in_area_doc = make_doc(doc_id="area-one", read_when=ReadWhen.IN_AREA)
    record_pick(
        session_id="low-confidence",
        selection=Selection(chosen=(every_time_doc, in_area_doc), reason=PICK_REASON_ALL_FIT),
        confidence=MIN_CONFIDENCE_FOR_SILENT_PICK / 2,
    )
    record_pick(
        session_id="dropped-standing",
        selection=Selection(
            chosen=(in_area_doc,),
            dropped=(every_time_doc,),
            reason=PICK_REASON_EVERY_TIME_OVER_RESERVE,
        ),
        confidence=1.0,
    )
    record_pick(
        session_id="no-area-match",
        selection=Selection(chosen=(every_time_doc,), reason=PICK_REASON_ALL_FIT),
        confidence=1.0,
    )
    summary = summarize_picks()
    assert summary.total_picks == 3
    assert summary.low_confidence_picks == 1
    assert summary.every_time_dropped_picks == 1
    assert summary.no_in_area_match_picks == 1


def test_a_pick_exactly_at_the_confidence_threshold_is_not_low_confidence(
    spine_home: Path,
) -> None:
    selection = Selection(
        chosen=(make_doc(doc_id="standing", read_when=ReadWhen.EVERY_TIME),),
        reason=PICK_REASON_ALL_FIT,
    )
    record_pick(
        session_id="at-threshold",
        selection=selection,
        confidence=MIN_CONFIDENCE_FOR_SILENT_PICK,
    )
    record_pick(
        session_id="below-threshold",
        selection=selection,
        confidence=MIN_CONFIDENCE_FOR_SILENT_PICK / 2,
    )
    assert summarize_picks().low_confidence_picks == 1


def test_summary_exposes_categories_only_never_rows(spine_home: Path) -> None:
    record_pick(
        session_id="session-one",
        selection=Selection(
            chosen=(make_doc(doc_id="standing", read_when=ReadWhen.EVERY_TIME),),
            reason=PICK_REASON_ALL_FIT,
        ),
        confidence=1.0,
    )
    summary = summarize_picks()
    assert {field.name for field in dataclasses.fields(summary)} == {
        "total_picks",
        "low_confidence_picks",
        "every_time_dropped_picks",
        "no_in_area_match_picks",
    }
    assert summary.total_picks == 1
    assert all(
        isinstance(getattr(summary, field.name), int) for field in dataclasses.fields(summary)
    )


def test_cli_registers_the_pick_subcommands() -> None:
    with pytest.raises(SystemExit) as exited:
        build_parser().parse_args(["pick", "--help"])
    assert exited.value.code == ARGPARSE_HELP_EXIT_CODE


def test_cli_pick_records_the_selection(
    spine_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    docs = (make_doc(doc_id="standing", read_when=ReadWhen.EVERY_TIME),)
    monkeypatch.setattr(
        spine.index, GRAPH_STORE_FACTORY_NAME, lambda: FakeGraphStore(docs=docs), raising=False
    )
    monkeypatch.setattr(spine.registry, PROJECT_REGISTRY_FACTORY_NAME, None, raising=False)
    exit_code = main(["pick", "--project", PROJECT_SLUG, "--task", TASK_CONTEXT])
    assert exit_code == EXIT_OK
    assert "standing" in capsys.readouterr().out
    assert summarize_picks().total_picks == 1


def test_cli_pick_refuses_a_slug_the_registry_does_not_know(
    spine_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        spine.index, GRAPH_STORE_FACTORY_NAME, lambda: FakeGraphStore(docs=()), raising=False
    )
    monkeypatch.setattr(
        spine.registry,
        PROJECT_REGISTRY_FACTORY_NAME,
        lambda: FakeRegistry(known=None),
        raising=False,
    )
    exit_code = main(["pick", "--project", PROJECT_SLUG, "--task", TASK_CONTEXT])
    assert exit_code == EXIT_UNKNOWN_PROJECT
    assert summarize_picks().total_picks == 0


def test_cli_picks_summary_prints_grouped_counts(
    spine_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["picks", "summary"]) == EXIT_OK
    printed = capsys.readouterr().out
    assert "total: 0" in printed
    assert "low_confidence: 0" in printed
