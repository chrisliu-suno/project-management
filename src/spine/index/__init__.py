"""Link extraction and the persisted document graph."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..cli import EXIT_OK, EXIT_USAGE
from ..constants import DOC_FILE_SUFFIX, DOC_ID_SEPARATOR, FRONTMATTER_DELIMITER
from ..model import DEFAULT_READ_WHEN, Doc, DocKind, Link, ReadWhen
from .backlinks import backlinks, deduplicate_links, is_citation, sweep_targets
from .extract import TextualLinkExtractor
from .store import SqliteGraphStore

__all__ = [
    "SqliteGraphStore",
    "TextualLinkExtractor",
    "backlinks",
    "build_links",
    "deduplicate_links",
    "is_citation",
    "load_corpus",
    "register_subcommand",
    "sweep_targets",
]

EXIT_EMPTY_CORPUS = 1

FRONTMATTER_KIND_KEY = "kind"
FRONTMATTER_READ_WHEN_KEY = "read_when"
FRONTMATTER_TITLE_KEY = "title"
FRONTMATTER_AREA_KEY = "area"
FRONTMATTER_GENERATED_KEY = "generated"
FRONTMATTER_PAIR_SEPARATOR = ":"
FRONTMATTER_NULL_LITERAL = "null"
FRONTMATTER_TRUE_LITERAL = "true"
FALLBACK_DOC_KIND = DocKind.GENERATED


def _frontmatter_pairs(*, lines: list[str]) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for line in lines:
        key, separator, value = line.partition(FRONTMATTER_PAIR_SEPARATOR)
        cleaned = value.strip()
        if separator and cleaned and cleaned != FRONTMATTER_NULL_LITERAL:
            pairs[key.strip()] = cleaned
    return pairs


def split_frontmatter(*, text: str) -> tuple[dict[str, str], str]:
    """Split a markdown file into its frontmatter pairs and its body."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return {}, text
    for offset, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONTMATTER_DELIMITER:
            return _frontmatter_pairs(lines=lines[1:offset]), "\n".join(lines[offset + 1 :])
    return {}, text


def _doc_kind(*, raw: str | None) -> DocKind:
    try:
        return DocKind(raw)
    except ValueError:
        return FALLBACK_DOC_KIND


def _read_when(*, raw: str | None, kind: DocKind) -> ReadWhen:
    try:
        return ReadWhen(raw)
    except ValueError:
        return DEFAULT_READ_WHEN[kind]


def _doc_from_file(*, path: Path, project_slug: str) -> Doc:
    pairs, body = split_frontmatter(text=path.read_text(encoding="utf-8"))
    kind = _doc_kind(raw=pairs.get(FRONTMATTER_KIND_KEY))
    return Doc(
        doc_id=f"{project_slug}{DOC_ID_SEPARATOR}{path.stem}",
        path=path,
        kind=kind,
        read_when=_read_when(raw=pairs.get(FRONTMATTER_READ_WHEN_KEY), kind=kind),
        title=pairs.get(FRONTMATTER_TITLE_KEY, path.stem),
        body=body,
        project_slug=project_slug,
        area=pairs.get(FRONTMATTER_AREA_KEY),
        frontmatter=dict(pairs),
        is_generated=pairs.get(FRONTMATTER_GENERATED_KEY, "").lower() == FRONTMATTER_TRUE_LITERAL,
    )


def load_corpus(*, docs_dir: Path, project_slug: str) -> tuple[Doc, ...]:
    """Read a directory of markdown into Docs, standing alone from the loader module."""
    return tuple(
        _doc_from_file(path=path, project_slug=project_slug)
        for path in sorted(docs_dir.glob(f"*{DOC_FILE_SUFFIX}"))
    )


def build_links(*, docs: tuple[Doc, ...]) -> tuple[Link, ...]:
    """Run the textual extractor over a whole corpus and collapse duplicate edges."""
    extractor = TextualLinkExtractor()
    found: list[Link] = []
    for doc in docs:
        found.extend(extractor.extract(doc=doc, corpus=docs))
    return deduplicate_links(links=tuple(found))


def _handle_build(args: argparse.Namespace) -> int:
    docs = load_corpus(docs_dir=args.dir, project_slug=args.project)
    if not docs:
        print(f"no {DOC_FILE_SUFFIX} documents under {args.dir}", file=sys.stderr)
        return EXIT_EMPTY_CORPUS
    links = build_links(docs=docs)
    SqliteGraphStore().replace_project(project_slug=args.project, docs=docs, links=links)
    print(f"{args.project}: indexed {len(docs)} docs, {len(links)} links")
    return EXIT_OK


def _handle_orphans(args: argparse.Namespace) -> int:
    for doc in SqliteGraphStore().orphans(project_slug=args.project):
        print(doc.doc_id)
    return EXIT_OK


def _handle_sweep(args: argparse.Namespace) -> int:
    citing_links = SqliteGraphStore().inbound(doc_id=args.doc)
    for doc_id in sweep_targets(links=citing_links, superseded_doc_id=args.doc):
        print(doc_id)
    return EXIT_OK


def _handle_missing_verb(*, parser: argparse.ArgumentParser) -> int:
    parser.print_help()
    return EXIT_USAGE


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    """Attach `spine index` and its build, orphans, and sweep verbs."""
    parser = subparsers.add_parser("index", help="Extract links and query the document graph.")
    parser.set_defaults(handler=lambda _args: _handle_missing_verb(parser=parser))
    verbs = parser.add_subparsers(dest="index_command", metavar="VERB")

    build = verbs.add_parser("build", help="Index a corpus directory into the graph.")
    build.add_argument("--dir", required=True, type=Path, help="Directory of markdown documents.")
    build.add_argument("--project", required=True, help="Project slug the corpus belongs to.")
    build.set_defaults(handler=_handle_build)

    orphans = verbs.add_parser("orphans", help="List docs nothing links to.")
    orphans.add_argument("--project", required=True, help="Project slug to inspect.")
    orphans.set_defaults(handler=_handle_orphans)

    sweep = verbs.add_parser("sweep", help="List docs to update if a doc were superseded.")
    sweep.add_argument("--doc", required=True, help="Doc id being superseded.")
    sweep.set_defaults(handler=_handle_sweep)
