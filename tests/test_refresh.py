"""The one-command sweep that brings a project's derived state up to date."""

from __future__ import annotations

from pathlib import Path

import pytest

from spine.constants import SPINE_HOME_ENV_VAR
from spine.refresh import ProjectRefresh, refresh_all, refresh_project

PROJECT_SLUG = "alpha"


@pytest.fixture(autouse=True)
def isolated_spine_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SPINE_HOME_ENV_VAR, str(tmp_path / "home"))


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "brief.md").write_text("# Brief\n\nProse.\n", encoding="utf-8")
    return docs


@pytest.fixture
def corpus_with_an_unknown_doc(tmp_path: Path) -> Path:
    """A corpus whose one document neither declares a kind nor implies one by filename."""
    docs = tmp_path / "unknown-docs"
    docs.mkdir()
    (docs / "random-thoughts.md").write_text("# Random thoughts\n\nProse.\n", encoding="utf-8")
    return docs


def _project(*, docs_dir: Path):
    from spine.model import Project

    return Project(slug=PROJECT_SLUG, name="Alpha", docs_dir=docs_dir)


def test_a_sweep_reports_what_it_indexed(corpus: Path) -> None:
    result = refresh_project(project=_project(docs_dir=corpus))
    assert result.slug == PROJECT_SLUG
    assert result.doc_count == 1
    assert result.error is None


def test_a_missing_corpus_is_reported_not_raised(tmp_path: Path) -> None:
    result = refresh_project(project=_project(docs_dir=tmp_path / "gone"))
    assert result.doc_count == 0
    assert result.error is None


def test_an_unknown_project_sweeps_nothing() -> None:
    assert refresh_all(slug="no-such-project") == ()


def test_a_successful_line_names_the_counts() -> None:
    line = ProjectRefresh(
        slug=PROJECT_SLUG, doc_count=3, fact_count=7, proposals_queued=1
    ).as_line()
    assert "3 docs" in line
    assert "1 new proposal(s)" in line


def test_an_errored_line_says_error() -> None:
    line = ProjectRefresh(
        slug=PROJECT_SLUG, doc_count=0, fact_count=0, proposals_queued=0, error="boom"
    ).as_line()
    assert "error" in line
    assert "boom" in line


def test_cli_exposes_the_refresh_subcommand() -> None:
    from spine.cli import build_parser

    assert build_parser().parse_args(["refresh"]).handler is not None


def test_a_sweep_classifies_a_document_that_declares_no_kind(
    corpus_with_an_unknown_doc: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from spine.classify.client import Classification
    from spine.model import DocKind, ReadWhen

    class OneVerdictClassifier:
        """Answers every batch with the same kind, so the sweep has something to cache."""

        def classify_batch(self, *, docs):
            return tuple(
                Classification(
                    doc_id=doc.doc_id,
                    kind=DocKind.BRIEF,
                    read_when=ReadWhen.EVERY_TIME,
                    area=None,
                    confidence=1.0,
                )
                for doc in docs
            )

    monkeypatch.setattr("spine.classify.AnthropicClassifier", OneVerdictClassifier)

    result = refresh_project(project=_project(docs_dir=corpus_with_an_unknown_doc))

    assert result.docs_classified == 1
    assert result.classifier_error is None
    assert "1 newly classified" in result.as_line()


def test_a_second_sweep_spends_nothing_on_an_unchanged_corpus(
    corpus_with_an_unknown_doc: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from spine.classify.client import Classification
    from spine.model import DocKind, ReadWhen

    calls: list[int] = []

    class CountingClassifier:
        """Records each batch so a cache hit is visible as a batch that never happened."""

        def classify_batch(self, *, docs):
            calls.append(len(docs))
            return tuple(
                Classification(
                    doc_id=doc.doc_id,
                    kind=DocKind.BRIEF,
                    read_when=ReadWhen.EVERY_TIME,
                    area=None,
                    confidence=1.0,
                )
                for doc in docs
            )

    monkeypatch.setattr("spine.classify.AnthropicClassifier", CountingClassifier)
    project = _project(docs_dir=corpus_with_an_unknown_doc)
    refresh_project(project=project)

    second = refresh_project(project=project)

    assert calls == [1]
    assert second.docs_classified == 0


def test_an_unavailable_classifier_does_not_stop_the_sweep(corpus_with_an_unknown_doc: Path) -> None:
    result = refresh_project(project=_project(docs_dir=corpus_with_an_unknown_doc))

    assert result.error is None
    assert result.doc_count == 1
    assert result.classifier_error is not None
    assert "classifier unavailable" in result.as_line()
