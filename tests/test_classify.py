"""Classifier precedence, batching, caching, and response parsing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from spine.classify import classify_corpus, needs_classification
from spine.classify.cache import ClassificationCache, content_fingerprint
from spine.classify.client import (
    AnthropicClassifier,
    Classification,
    ClassifierRefusedError,
    ModelUnavailableError,
    parse_response_text,
)
from spine.classify.prompt import batch_prompt, describe_document, system_prompt
from spine.constants import CLASSIFIER_BATCH_SIZE, SPINE_HOME_ENV_VAR
from spine.model import Doc, DocKind, ReadWhen

PROJECT_SLUG = "alpha"


@pytest.fixture(autouse=True)
def isolated_spine_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SPINE_HOME_ENV_VAR, str(tmp_path))


def _doc(
    *,
    stem: str,
    body: str = "# Title\n\nProse.",
    kind: DocKind = DocKind.GENERATED,
    frontmatter: dict[str, object] | None = None,
    parent: str | None = None,
) -> Doc:
    return Doc(
        doc_id=f"{PROJECT_SLUG}:{stem}",
        path=Path(f"{stem}.md"),
        kind=kind,
        read_when=ReadWhen.LOOKED_UP,
        title=stem,
        body=body,
        project_slug=PROJECT_SLUG,
        frontmatter=frontmatter or {},
        parent_doc_id=parent,
    )


def _verdict(*, stem: str, kind: DocKind = DocKind.AREA_DESIGN, area: str = "uplink") -> dict:
    return {
        "doc_id": f"{PROJECT_SLUG}:{stem}",
        "kind": kind.value,
        "read_when": ReadWhen.IN_AREA.value,
        "area": area,
        "confidence": 0.9,
    }


@dataclass
class _RecordingClassifier:
    """Stands in for the model; records every batch it was asked to classify."""

    batches: list[tuple[Doc, ...]]

    def classify_batch(self, *, docs: tuple[Doc, ...]) -> tuple[Classification, ...]:
        self.batches.append(docs)
        payload = json.dumps({"results": [_verdict(stem=doc.path.stem) for doc in docs]})
        return parse_response_text(payload=payload)


def test_a_doc_declaring_its_kind_is_never_sent() -> None:
    declared = _doc(stem="brief", kind=DocKind.BRIEF, frontmatter={"kind": "brief"})
    assert needs_classification(doc=declared) is False


def test_a_doc_with_an_inferred_kind_is_never_sent() -> None:
    inferred = _doc(stem="project-rules", kind=DocKind.PROJECT_RULES)
    assert needs_classification(doc=inferred) is False


def test_an_unknown_doc_is_sent() -> None:
    assert needs_classification(doc=_doc(stem="permissions-v2-design")) is True


def test_log_entries_are_never_sent() -> None:
    entry = _doc(stem="decisions", parent=f"{PROJECT_SLUG}:decisions")
    assert needs_classification(doc=entry) is False


def test_classification_is_applied_to_the_corpus() -> None:
    unknown = _doc(stem="permissions-v2-design")
    classifier = _RecordingClassifier(batches=[])
    result = classify_corpus(
        docs=(unknown,), classifier=classifier, cache=ClassificationCache()
    )
    assert result[0].kind is DocKind.AREA_DESIGN
    assert result[0].read_when is ReadWhen.IN_AREA
    assert result[0].area == "uplink"


def test_already_known_docs_pass_through_untouched() -> None:
    known = _doc(stem="brief", kind=DocKind.BRIEF, frontmatter={"kind": "brief"})
    classifier = _RecordingClassifier(batches=[])
    result = classify_corpus(docs=(known,), classifier=classifier, cache=ClassificationCache())
    assert result[0] is known
    assert classifier.batches == []


def test_the_second_run_makes_no_model_calls() -> None:
    docs = (_doc(stem="permissions-v2-design"),)
    cache = ClassificationCache()
    first = _RecordingClassifier(batches=[])
    classify_corpus(docs=docs, classifier=first, cache=cache)
    second = _RecordingClassifier(batches=[])
    classify_corpus(docs=docs, classifier=second, cache=cache)
    assert len(first.batches) == 1
    assert second.batches == []


def test_editing_a_doc_invalidates_only_that_doc() -> None:
    cache = ClassificationCache()
    original = _doc(stem="permissions-v2-design", body="# One\n\nOriginal.")
    classify_corpus(docs=(original,), classifier=_RecordingClassifier(batches=[]), cache=cache)
    edited = _doc(stem="permissions-v2-design", body="# One\n\nEdited.")
    second = _RecordingClassifier(batches=[])
    classify_corpus(docs=(edited,), classifier=second, cache=cache)
    assert len(second.batches) == 1


def test_batching_respects_the_configured_size() -> None:
    docs = tuple(_doc(stem=f"doc-{index}") for index in range(CLASSIFIER_BATCH_SIZE + 3))
    classifier = _RecordingClassifier(batches=[])
    classify_corpus(docs=docs, classifier=classifier, cache=ClassificationCache())
    assert [len(batch) for batch in classifier.batches] == [CLASSIFIER_BATCH_SIZE, 3]


def test_a_verdict_for_an_unknown_doc_id_is_ignored() -> None:
    class StrayClassifier:
        def classify_batch(self, *, docs: tuple[Doc, ...]) -> tuple[Classification, ...]:
            return parse_response_text(
                payload=json.dumps({"results": [_verdict(stem="not-in-this-batch")]})
            )

    unknown = _doc(stem="permissions-v2-design")
    result = classify_corpus(
        docs=(unknown,), classifier=StrayClassifier(), cache=ClassificationCache()
    )
    assert result[0].kind is DocKind.GENERATED


def test_malformed_entries_are_dropped_not_fatal() -> None:
    payload = json.dumps(
        {"results": [_verdict(stem="good"), {"doc_id": "x", "kind": "not-a-kind"}]}
    )
    parsed = parse_response_text(payload=payload)
    assert [verdict.doc_id for verdict in parsed] == [f"{PROJECT_SLUG}:good"]


def test_invalid_json_raises_rather_than_returning_nothing() -> None:
    with pytest.raises(ModelUnavailableError):
        parse_response_text(payload="{not json")


def test_an_empty_area_becomes_none() -> None:
    payload = json.dumps({"results": [_verdict(stem="wide", area="")]})
    assert parse_response_text(payload=payload)[0].area is None


def test_a_refusal_raises_rather_than_classifying_wrongly() -> None:
    class RefusingMessages:
        def create(self, **_kwargs: object) -> object:
            return type("Response", (), {"stop_reason": "refusal", "content": []})()

    client = type("Client", (), {"messages": RefusingMessages()})()
    with pytest.raises(ClassifierRefusedError):
        AnthropicClassifier(client=client).classify_batch(docs=(_doc(stem="x"),))


def test_an_empty_batch_makes_no_call() -> None:
    class ExplodingClient:
        @property
        def messages(self) -> object:
            raise AssertionError("should not be called")

    assert AnthropicClassifier(client=ExplodingClient()).classify_batch(docs=()) == ()


def test_the_document_description_carries_id_filename_and_headings() -> None:
    described = describe_document(doc=_doc(stem="design", body="# Big\n\n## Small\n\nProse."))
    assert f"{PROJECT_SLUG}:design" in described
    assert "design.md" in described
    assert "# Big" in described
    assert "## Small" in described


def test_the_batch_prompt_contains_every_document() -> None:
    docs = (_doc(stem="one"), _doc(stem="two"))
    prompt = batch_prompt(docs=docs)
    assert all(doc.doc_id in prompt for doc in docs)


def test_the_system_prompt_names_every_kind_and_group() -> None:
    prompt = system_prompt()
    assert all(kind.value in prompt for kind in DocKind)
    assert all(group.value in prompt for group in ReadWhen)


def test_fingerprints_differ_for_different_bodies() -> None:
    assert content_fingerprint(body="one") != content_fingerprint(body="two")


def test_cli_exposes_the_classify_subcommand() -> None:
    from spine.cli import build_parser

    parsed = build_parser().parse_args(["classify", "pending", "--dir", ".", "--project", "p"])
    assert parsed.handler is not None


def test_cached_classifications_are_reconciled_on_apply() -> None:
    from spine.classify.apply import apply_cached_classifications
    from spine.classify.cache import ClassificationCache

    cache = ClassificationCache()
    first = _doc(stem="hub-one", body="# One\n\nBody one.")
    second = _doc(stem="hub-two", body="# Two\n\nBody two.")
    for doc, confidence in ((first, 0.4), (second, 0.95)):
        cache.put(
            body=doc.body,
            classification=Classification(
                doc_id=doc.doc_id,
                kind=DocKind.BRIEF,
                read_when=ReadWhen.EVERY_TIME,
                area=None,
                confidence=confidence,
            ),
        )
    applied = apply_cached_classifications(docs=(first, second), cache=cache)
    briefs = [doc.doc_id for doc in applied if doc.kind is DocKind.BRIEF]
    assert briefs == [second.doc_id]
