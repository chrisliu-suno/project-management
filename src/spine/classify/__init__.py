"""Model-backed document classification.

Precedence is frontmatter, then cache, then model. A document that declares its
own kind is never sent to the model.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from ..cli import EXIT_OK, EXIT_USAGE
from ..constants import CLASSIFIER_BATCH_SIZE, CLASSIFIER_MIN_CONFIDENCE, DOC_KIND_KEY
from ..model import Doc, DocKind
from .cache import ClassificationCache
from .client import (
    AnthropicClassifier,
    Classification,
    ClassifierRefusedError,
    ClassifierUnavailableError,
)
from .prompt import batch_prompt, system_prompt
from .schema import classification_schema

__all__ = [
    "AnthropicClassifier",
    "Classification",
    "ClassificationCache",
    "ClassifierRefusedError",
    "ClassifierUnavailableError",
    "batch_prompt",
    "classification_schema",
    "classify_corpus",
    "needs_classification",
    "register_subcommand",
    "system_prompt",
]

EXIT_CLASSIFIER_UNAVAILABLE = 3
FIELD_SEPARATOR = "\t"
LOW_CONFIDENCE_MARKER = "low-confidence"


def needs_classification(*, doc: Doc) -> bool:
    """True when the document neither declares its kind nor is a log entry."""
    if doc.is_entry:
        return False
    if DOC_KIND_KEY in doc.frontmatter:
        return False
    return doc.kind is DocKind.GENERATED


def _batches(*, docs: tuple[Doc, ...]) -> tuple[tuple[Doc, ...], ...]:
    return tuple(
        tuple(docs[start : start + CLASSIFIER_BATCH_SIZE])
        for start in range(0, len(docs), CLASSIFIER_BATCH_SIZE)
    )


def _applied(*, doc: Doc, verdict: Classification) -> Doc:
    return replace(
        doc,
        kind=verdict.kind,
        read_when=verdict.read_when,
        area=verdict.area if verdict.area else doc.area,
    )


def _from_cache(
    *, docs: tuple[Doc, ...], cache: ClassificationCache
) -> tuple[dict[str, Classification], tuple[Doc, ...]]:
    cached: dict[str, Classification] = {}
    missing: list[Doc] = []
    for doc in docs:
        found = cache.get(body=doc.body)
        if found is None:
            missing.append(doc)
        else:
            cached[doc.doc_id] = found
    return cached, tuple(missing)


def classify_corpus(
    *,
    docs: tuple[Doc, ...],
    classifier: AnthropicClassifier,
    cache: ClassificationCache,
) -> tuple[Doc, ...]:
    """The corpus with model-assigned kinds filled in where they were unknown."""
    pending = tuple(doc for doc in docs if needs_classification(doc=doc))
    verdicts, uncached = _from_cache(docs=pending, cache=cache)
    for batch in _batches(docs=uncached):
        by_id = {doc.doc_id: doc for doc in batch}
        for verdict in classifier.classify_batch(docs=batch):
            source = by_id.get(verdict.doc_id)
            if source is None:
                continue
            cache.put(body=source.body, classification=verdict)
            verdicts[verdict.doc_id] = verdict
    return tuple(
        _applied(doc=doc, verdict=verdicts[doc.doc_id]) if doc.doc_id in verdicts else doc
        for doc in docs
    )


def _handle_classify(args: argparse.Namespace) -> int:
    from ..docs import FilesystemDocSource
    from ..model import Project

    docs_dir = Path(args.dir).expanduser()
    project = Project(slug=args.project, name=args.project, docs_dir=docs_dir)
    loaded = FilesystemDocSource().load_all(project=project)
    try:
        classified = classify_corpus(
            docs=loaded, classifier=AnthropicClassifier(), cache=ClassificationCache()
        )
    except (ClassifierUnavailableError, ClassifierRefusedError) as error:
        print(str(error), file=sys.stderr)
        return EXIT_CLASSIFIER_UNAVAILABLE
    for doc in classified:
        print(FIELD_SEPARATOR.join((doc.doc_id, str(doc.kind), str(doc.read_when))))
    return EXIT_OK


def _handle_pending(args: argparse.Namespace) -> int:
    from ..docs import FilesystemDocSource
    from ..model import Project

    docs_dir = Path(args.dir).expanduser()
    project = Project(slug=args.project, name=args.project, docs_dir=docs_dir)
    pending = [
        doc
        for doc in FilesystemDocSource().load_all(project=project)
        if needs_classification(doc=doc)
    ]
    for doc in pending:
        print(doc.doc_id)
    print(f"{len(pending)} document(s) need classification", file=sys.stderr)
    return EXIT_OK


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    """Attach `spine classify` to the CLI."""
    parser = subparsers.add_parser("classify", help="Assign kinds to unannotated documents.")
    parser.set_defaults(handler=lambda _args: _print_help(parser=parser))
    verbs = parser.add_subparsers(dest="classify_command", metavar="VERB")

    runner = verbs.add_parser("run", help="Classify a corpus, using the cache where possible.")
    runner.add_argument("--dir", required=True, help="Directory of markdown documents.")
    runner.add_argument("--project", required=True, help="Project slug.")
    runner.set_defaults(handler=_handle_classify)

    pending = verbs.add_parser("pending", help="List documents whose kind is unknown.")
    pending.add_argument("--dir", required=True)
    pending.add_argument("--project", required=True)
    pending.set_defaults(handler=_handle_pending)


def _print_help(*, parser: argparse.ArgumentParser) -> int:
    parser.print_help()
    return EXIT_USAGE
