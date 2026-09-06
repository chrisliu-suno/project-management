"""Corpus-level invariants applied after per-batch classification."""

from __future__ import annotations

from spine.classify.client import Classification
from spine.classify.reconcile import (
    enforce_brief_is_every_time,
    enforce_single_brief,
    reconcile,
)
from spine.model import DocKind, ReadWhen


def _verdict(
    *,
    doc_id: str,
    kind: DocKind = DocKind.BRIEF,
    read_when: ReadWhen = ReadWhen.EVERY_TIME,
    confidence: float = 0.9,
) -> Classification:
    return Classification(
        doc_id=doc_id, kind=kind, read_when=read_when, area=None, confidence=confidence
    )


def _kinds(verdicts: dict[str, Classification]) -> dict[str, DocKind]:
    return {doc_id: verdict.kind for doc_id, verdict in verdicts.items()}


def test_the_most_confident_brief_wins() -> None:
    verdicts = {
        "weak": _verdict(doc_id="weak", confidence=0.4),
        "strong": _verdict(doc_id="strong", confidence=0.95),
    }
    assert _kinds(enforce_single_brief(verdicts=verdicts)) == {
        "weak": DocKind.AREA_DESIGN,
        "strong": DocKind.BRIEF,
    }


def test_a_demoted_brief_leaves_the_every_time_group() -> None:
    verdicts = {
        "weak": _verdict(doc_id="weak", confidence=0.4),
        "strong": _verdict(doc_id="strong", confidence=0.95),
    }
    assert enforce_single_brief(verdicts=verdicts)["weak"].read_when is ReadWhen.IN_AREA


def test_a_tie_breaks_on_doc_id_not_iteration_order() -> None:
    forward = {"b": _verdict(doc_id="b"), "a": _verdict(doc_id="a")}
    backward = {"a": _verdict(doc_id="a"), "b": _verdict(doc_id="b")}
    assert _kinds(enforce_single_brief(verdicts=forward)) == _kinds(
        enforce_single_brief(verdicts=backward)
    )


def test_a_single_brief_is_left_alone() -> None:
    verdicts = {
        "hub": _verdict(doc_id="hub"),
        "other": _verdict(doc_id="other", kind=DocKind.AREA_DESIGN, read_when=ReadWhen.IN_AREA),
    }
    assert enforce_single_brief(verdicts=verdicts) == verdicts


def test_a_corpus_with_no_brief_is_left_alone() -> None:
    verdicts = {
        "one": _verdict(doc_id="one", kind=DocKind.AREA_DESIGN, read_when=ReadWhen.IN_AREA),
    }
    assert enforce_single_brief(verdicts=verdicts) == verdicts


def test_a_brief_filed_outside_every_time_is_corrected() -> None:
    verdicts = {"hub": _verdict(doc_id="hub", read_when=ReadWhen.IN_AREA)}
    assert enforce_brief_is_every_time(verdicts=verdicts)["hub"].read_when is ReadWhen.EVERY_TIME


def test_non_briefs_keep_their_group() -> None:
    verdicts = {
        "log": _verdict(doc_id="log", kind=DocKind.DECISION_LOG, read_when=ReadWhen.LOG)
    }
    assert enforce_brief_is_every_time(verdicts=verdicts)["log"].read_when is ReadWhen.LOG


def test_reconcile_applies_both_invariants_together() -> None:
    verdicts = {
        "weak": _verdict(doc_id="weak", confidence=0.4, read_when=ReadWhen.IN_AREA),
        "strong": _verdict(doc_id="strong", confidence=0.95, read_when=ReadWhen.IN_AREA),
    }
    result = reconcile(verdicts=verdicts)
    assert result["strong"].kind is DocKind.BRIEF
    assert result["strong"].read_when is ReadWhen.EVERY_TIME
    assert result["weak"].kind is DocKind.AREA_DESIGN
    assert result["weak"].read_when is ReadWhen.IN_AREA


def test_reconcile_does_not_mutate_its_input() -> None:
    verdicts = {
        "weak": _verdict(doc_id="weak", confidence=0.4),
        "strong": _verdict(doc_id="strong", confidence=0.95),
    }
    reconcile(verdicts=verdicts)
    assert verdicts["weak"].kind is DocKind.BRIEF
