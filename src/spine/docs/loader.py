"""Reads a project's markdown corpus off disk into Doc objects."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from ..constants import (
    DOC_AREA_KEY,
    DOC_FILE_SUFFIX,
    DOC_GENERATED_KEYS,
    DOC_ID_SEPARATOR,
    DOC_KIND_BY_FILENAME_PREFIX,
    DOC_KIND_KEY,
    DOC_KIND_WORD_SEPARATOR,
    DOC_LIFECYCLE_KEY,
    DOC_READ_WHEN_KEY,
    DOC_TEXT_ENCODING,
    DOC_TITLE_KEY,
    FALLBACK_DOC_KIND,
    FILENAME_WORD_SEPARATOR,
    MARKDOWN_FENCE_PREFIX,
    MARKDOWN_H1_PREFIX,
    PROJECT_SLUG_SEPARATOR,
)
from ..model import DEFAULT_READ_WHEN, Doc, DocKind, Lifecycle, Project, ReadWhen
from .frontmatter import parse_frontmatter


class FilesystemDocSource:
    """Loads a corpus from a directory of markdown files. Satisfies the DocSource port."""

    def load_all(self, *, project: Project) -> tuple[Doc, ...]:
        """Every markdown file in the project's docs directory, ordered by path."""
        return tuple(
            self.load_one(project=project, path=path)
            for path in corpus_paths(docs_dir=project.docs_dir)
        )

    def load_one(self, *, project: Project, path: Path) -> Doc:
        """Read one file into a Doc, filling absent frontmatter from filename and body."""
        parsed = parse_frontmatter(text=path.read_text(encoding=DOC_TEXT_ENCODING))
        kind = resolve_kind(mapping=parsed.mapping, path=path)
        return Doc(
            doc_id=doc_id_for(project_slug=project.slug, path=path),
            path=path,
            kind=kind,
            read_when=resolve_read_when(mapping=parsed.mapping, kind=kind),
            title=resolve_title(mapping=parsed.mapping, body=parsed.body, path=path),
            body=parsed.body,
            project_slug=project.slug,
            area=_optional_text(mapping=parsed.mapping, key=DOC_AREA_KEY),
            lifecycle=_coerce_enum(raw=parsed.mapping.get(DOC_LIFECYCLE_KEY), enum_type=Lifecycle),
            frontmatter=dict(parsed.mapping),
            is_generated=_resolve_is_generated(mapping=parsed.mapping),
        )


def corpus_paths(*, docs_dir: Path) -> tuple[Path, ...]:
    """Markdown files directly under the corpus directory, sorted for determinism."""
    if not docs_dir.is_dir():
        return ()
    markdown = (
        entry for entry in docs_dir.iterdir() if entry.is_file() and entry.suffix == DOC_FILE_SUFFIX
    )
    return tuple(sorted(markdown))


def doc_id_for(*, project_slug: str, path: Path) -> str:
    return f"{project_slug}{DOC_ID_SEPARATOR}{path.stem}"


def project_for_dir(*, docs_dir: Path) -> Project:
    """Ad-hoc project for CLI runs pointed straight at a corpus directory."""
    resolved = docs_dir.expanduser().resolve()
    return Project(
        slug=PROJECT_SLUG_SEPARATOR.join(resolved.name.lower().split()),
        name=resolved.name,
        docs_dir=resolved,
    )


def resolve_kind(*, mapping: dict[str, object], path: Path) -> DocKind:
    """Declared kind, else inferred from the filename, else the generated fallback."""
    declared = _coerce_enum(raw=mapping.get(DOC_KIND_KEY), enum_type=DocKind)
    return declared if declared is not None else infer_kind_from_filename(path=path)


def infer_kind_from_filename(*, path: Path) -> DocKind:
    """Match the stem against the kind vocabulary, then against known filename prefixes."""
    stem = path.stem.lower()
    as_kind_value = stem.replace(FILENAME_WORD_SEPARATOR, DOC_KIND_WORD_SEPARATOR)
    direct = _coerce_enum(raw=as_kind_value, enum_type=DocKind)
    if direct is not None:
        return direct
    by_prefix = _kind_from_filename_prefix(stem=stem)
    return by_prefix if by_prefix is not None else FALLBACK_DOC_KIND


def _kind_from_filename_prefix(*, stem: str) -> DocKind | None:
    for prefix in sorted(DOC_KIND_BY_FILENAME_PREFIX, key=len, reverse=True):
        if stem == prefix or stem.startswith(f"{prefix}{FILENAME_WORD_SEPARATOR}"):
            return DOC_KIND_BY_FILENAME_PREFIX[prefix]
    return None


def resolve_read_when(*, mapping: dict[str, object], kind: DocKind) -> ReadWhen:
    """Declared read-when group, else the default for the kind."""
    declared = _coerce_enum(raw=mapping.get(DOC_READ_WHEN_KEY), enum_type=ReadWhen)
    return declared if declared is not None else DEFAULT_READ_WHEN[kind]


def resolve_title(*, mapping: dict[str, object], body: str, path: Path) -> str:
    """Frontmatter title, else the first markdown H1, else the filename stem."""
    declared = _optional_text(mapping=mapping, key=DOC_TITLE_KEY)
    if declared:
        return declared
    heading = first_h1(body=body)
    return heading if heading else path.stem


def first_h1(*, body: str) -> str | None:
    """The first real H1, skipping fenced blocks where `#` starts a comment."""
    is_inside_fence = False
    for line in body.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(MARKDOWN_FENCE_PREFIX):
            is_inside_fence = not is_inside_fence
            continue
        if not is_inside_fence and stripped.startswith(MARKDOWN_H1_PREFIX):
            return stripped.removeprefix(MARKDOWN_H1_PREFIX).strip() or None
    return None


def _resolve_is_generated(*, mapping: dict[str, object]) -> bool:
    for key in DOC_GENERATED_KEYS:
        value = mapping.get(key)
        if isinstance(value, bool):
            return value
    return False


def _optional_text(*, mapping: dict[str, object], key: str) -> str | None:
    value = mapping.get(key)
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _coerce_enum[EnumT: StrEnum](*, raw: object, enum_type: type[EnumT]) -> EnumT | None:
    """Enum member for a frontmatter value, or None when it is absent or unrecognised."""
    if not isinstance(raw, str):
        return None
    try:
        return enum_type(raw.strip().lower())
    except ValueError:
        return None
