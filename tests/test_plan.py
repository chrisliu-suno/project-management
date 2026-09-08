"""Deriving plan state from the conventions the corpora already use."""

from __future__ import annotations

from pathlib import Path

from spine.model import Doc, DocKind, ReadWhen
from spine.plan import (
    ItemStatus,
    open_questions_across,
    plan_in,
    plan_richness,
    primary_plan,
    project_plans,
)
from spine.plan.status import status_from

PROJECT_SLUG = "alpha"


def _doc(*, body: str, stem: str = "plan", is_entry: bool = False) -> Doc:
    return Doc(
        doc_id=f"{PROJECT_SLUG}:{stem}",
        path=Path(f"{stem}.md"),
        kind=DocKind.ROLLOUT,
        read_when=ReadWhen.IN_AREA,
        title=stem,
        body=body,
        project_slug=PROJECT_SLUG,
        parent_doc_id=f"{PROJECT_SLUG}:parent" if is_entry else None,
    )


def test_a_negated_status_is_not_read_as_its_positive() -> None:
    assert status_from(text="**NOT BUILT**") is ItemStatus.NOT_STARTED
    assert status_from(text="**SHIPPED**") is ItemStatus.DONE


def test_partial_is_its_own_status() -> None:
    assert status_from(text="**PARTIAL**") is ItemStatus.PARTIAL


def test_an_empty_cell_is_unknown() -> None:
    assert status_from(text="   ") is ItemStatus.UNKNOWN


def test_a_status_in_a_parenthetical_is_ignored() -> None:
    assert status_from(text="pending (was shipped in v1)") is ItemStatus.UNKNOWN


PHASE_DOC = """# Rollout

## Phase 0 — Denominator and detector

- [ ] Endpoint inventory generated from the router. (0.1)
- [x] Data-reader inventory too.

## Phase 1 — Shadow the decision

- [ ] Comparison called on the exact object. (1.1)
"""


def test_phase_headings_become_milestones_in_order() -> None:
    state = plan_in(doc=_doc(body=PHASE_DOC))
    assert [milestone.title for milestone in state.milestones] == [
        "Phase 0 — Denominator and detector",
        "Phase 1 — Shadow the decision",
    ]


def test_checkboxes_attach_to_the_phase_above_them() -> None:
    state = plan_in(doc=_doc(body=PHASE_DOC))
    assert len(state.items_for(milestone="Phase 0 — Denominator and detector")) == 2
    assert len(state.items_for(milestone="Phase 1 — Shadow the decision")) == 1


def test_a_ticked_box_is_done_and_an_empty_one_is_not_started() -> None:
    statuses = {item.title: item.status for item in plan_in(doc=_doc(body=PHASE_DOC)).items}
    assert statuses["Data-reader inventory too."] is ItemStatus.DONE
    assert statuses["Endpoint inventory generated from the router."] is ItemStatus.NOT_STARTED


def test_the_trailing_step_reference_is_stripped_from_a_title() -> None:
    titles = [item.title for item in plan_in(doc=_doc(body=PHASE_DOC)).items]
    assert "Endpoint inventory generated from the router." in titles


def test_the_current_milestone_is_the_first_with_unfinished_work() -> None:
    state = plan_in(doc=_doc(body=PHASE_DOC))
    assert state.current_milestone is not None
    assert state.current_milestone.title == "Phase 0 — Denominator and detector"


MILESTONE_DOC = """# Design

### AT-M1 — single-seat (target Aug 14) — **no RBAC store**

- [x] ship the thing

### AT-M2 — teams

- [ ] later work
"""


def test_a_target_date_is_read_off_the_heading() -> None:
    state = plan_in(doc=_doc(body=MILESTONE_DOC))
    assert state.milestones[0].target == "Aug 14"


def test_the_target_parenthetical_leaves_the_title() -> None:
    assert plan_in(doc=_doc(body=MILESTONE_DOC)).milestones[0].title.startswith("AT-M1")
    assert "target" not in plan_in(doc=_doc(body=MILESTONE_DOC)).milestones[0].title


def test_a_finished_milestone_is_skipped_for_the_current_one() -> None:
    state = plan_in(doc=_doc(body=MILESTONE_DOC))
    assert state.current_milestone is not None
    assert state.current_milestone.title.startswith("AT-M2")


TABLE_DOC = """# Audit

## Status table

| # | WS5 item | Status | Evidence | Remaining |
|---|---|---|---|---|
| 1 | S3 lifecycle rule | **NOT BUILT** | absent from cdk | write it |
| 2a | Admin fields (API) | **SHIPPED** | schemas.py:17 | none |
| 2c | Re-send button | **PARTIAL** | endpoint only | wire the UI |
"""


def test_a_status_table_becomes_work_items() -> None:
    state = plan_in(doc=_doc(body=TABLE_DOC))
    assert len(state.items) == 3


def test_the_table_title_column_is_preferred_over_the_index() -> None:
    titles = [item.title for item in plan_in(doc=_doc(body=TABLE_DOC)).items]
    assert "S3 lifecycle rule" in titles
    assert "1" not in titles


def test_the_table_status_column_sets_each_status() -> None:
    statuses = [item.status for item in plan_in(doc=_doc(body=TABLE_DOC)).items]
    assert statuses == [ItemStatus.NOT_STARTED, ItemStatus.DONE, ItemStatus.PARTIAL]


def test_evidence_is_carried_off_the_row() -> None:
    assert plan_in(doc=_doc(body=TABLE_DOC)).items[0].evidence == "absent from cdk"


def test_the_separator_row_is_not_an_item() -> None:
    assert all(set(item.title) != {"-"} for item in plan_in(doc=_doc(body=TABLE_DOC)).items)


def test_a_table_without_a_status_column_yields_no_items() -> None:
    body = "# D\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    assert plan_in(doc=_doc(body=body)).items == ()


QUESTION_DOC = """# Design

## Open questions

- Does the export bucket need a legal hold?
- Who owns the backfill?

## Something else

- not a question
"""


def test_open_questions_are_collected_from_their_section() -> None:
    assert plan_in(doc=_doc(body=QUESTION_DOC)).open_questions == (
        "Does the export bucket need a legal hold?",
        "Who owns the backfill?",
    )


def test_bullets_outside_the_questions_section_are_not_questions() -> None:
    assert "not a question" not in plan_in(doc=_doc(body=QUESTION_DOC)).open_questions


def test_questions_are_gathered_across_the_corpus_without_duplicates() -> None:
    docs = (_doc(body=QUESTION_DOC, stem="a"), _doc(body=QUESTION_DOC, stem="b"))
    assert len(open_questions_across(docs=docs)) == 2


def test_a_prose_heading_is_not_mistaken_for_a_milestone() -> None:
    body = "# D\n\n## Ground truth (do not skip)\n\n- [ ] a thing\n"
    assert plan_in(doc=_doc(body=body)).milestones == ()


def test_a_numbered_section_is_not_a_milestone() -> None:
    body = "# D\n\n## 6. Report\n\n- [ ] a thing\n"
    assert plan_in(doc=_doc(body=body)).milestones == ()


def test_a_document_with_no_plan_states_none() -> None:
    assert not plan_in(doc=_doc(body="# D\n\nJust prose.\n")).has_plan


def test_stated_statuses_count_for_more_than_unticked_boxes() -> None:
    table = plan_in(doc=_doc(body=TABLE_DOC))
    phases = plan_in(doc=_doc(body="# D\n\n## Phase 1 — x\n\n- [ ] a\n- [ ] b\n"))
    assert plan_richness(state=table) > 0
    assert plan_richness(state=phases) >= 1


def test_the_richest_document_becomes_the_primary_plan() -> None:
    docs = (
        _doc(body="# D\n\nJust prose.\n", stem="prose"),
        _doc(body=TABLE_DOC, stem="audit"),
    )
    assert primary_plan(docs=docs, project_slug=PROJECT_SLUG).items


def test_a_corpus_with_no_plan_yields_an_empty_state() -> None:
    docs = (_doc(body="# D\n\nJust prose.\n"),)
    assert not primary_plan(docs=docs, project_slug=PROJECT_SLUG).has_plan


def test_plans_stay_separate_per_document() -> None:
    docs = (_doc(body=PHASE_DOC, stem="a"), _doc(body=MILESTONE_DOC, stem="b"))
    assert len(project_plans(docs=docs)) == 2


def test_log_entries_are_not_read_as_plans() -> None:
    docs = (_doc(body=TABLE_DOC, stem="entry", is_entry=True),)
    assert project_plans(docs=docs) == ()


def test_the_context_block_names_the_current_milestone_and_target() -> None:
    from spine.plan.render import render_plan

    block = render_plan(state=plan_in(doc=_doc(body=MILESTONE_DOC)))
    assert "AT-M2" in block
    assert "target" not in block or "Aug 14" in block


def test_the_context_block_reports_progress() -> None:
    from spine.plan.render import render_plan

    assert "1 of 3 tracked items done" in render_plan(state=plan_in(doc=_doc(body=TABLE_DOC)))


def test_a_planless_document_renders_nothing() -> None:
    from spine.plan.render import render_plan

    assert render_plan(state=plan_in(doc=_doc(body="# D\n\nProse.\n"))) == ""


def test_open_questions_reach_the_context_block() -> None:
    from spine.plan.render import render_plan

    block = render_plan(
        state=plan_in(doc=_doc(body=TABLE_DOC)), open_questions=("who owns the backfill?",)
    )
    assert "who owns the backfill?" in block


def test_settled_items_are_not_listed_as_open_work() -> None:
    from spine.plan.render import render_plan

    assert "Admin fields (API)" not in render_plan(state=plan_in(doc=_doc(body=TABLE_DOC)))


def test_cli_exposes_the_plan_subcommand() -> None:
    from spine.cli import build_parser

    assert build_parser().parse_args(["plan", "show", "--project", "x"]).handler is not None


def test_the_dashboard_page_renders_a_plan_block() -> None:
    from spine.serve.page import render_page

    page = render_page()
    assert "function planBlock" in page
    assert "where this sits" in page


LONG_UNSTARTED = "# Checklist\n\n## Phase 1 — a\n\n" + "".join(
    f"- [ ] item {n}\n" for n in range(40)
)
SHORT_WITH_PROGRESS = """# Tracker

| item | Status |
|---|---|
| a | **SHIPPED** |
| b | **NOT BUILT** |
"""


def test_a_long_unstarted_checklist_loses_to_a_short_record_of_progress() -> None:
    docs = (
        _doc(body=LONG_UNSTARTED, stem="checklist"),
        _doc(body=SHORT_WITH_PROGRESS, stem="tracker"),
    )
    doc, _ = project_plans(docs=docs)[0]
    assert doc.path.name == "tracker.md"


def test_unticked_boxes_do_not_raise_richness() -> None:
    assert plan_richness(state=plan_in(doc=_doc(body=LONG_UNSTARTED))) == 1


def test_unreadable_rows_do_not_raise_richness() -> None:
    body = "# D\n\n| item | Status |\n|---|---|\n| a |  |\n| b |  |\n"
    assert plan_richness(state=plan_in(doc=_doc(body=body))) == 0
