"""M2 — corpus loading, frontmatter parsing, and read-when size caps."""

from __future__ import annotations

from pathlib import Path

import pytest

from spine.cli import main
from spine.constants import (
    DOC_FILE_SUFFIX,
    DOC_ID_SEPARATOR,
    DOC_TEXT_ENCODING,
    DOCS_CHECK_ACTION,
    DOCS_COMMAND_NAME,
    DOCS_DIR_OPTION,
    DOCS_LIST_ACTION,
    EXIT_CAP_BREACH,
)
from spine.docs import (
    FilesystemDocSource,
    cap_for,
    corpus_paths,
    find_cap_breaches,
    first_h1,
    infer_kind_from_filename,
    parse_frontmatter,
    project_for_dir,
    resolve_read_when,
)
from spine.model import DEFAULT_READ_WHEN, Doc, DocKind, Lifecycle, Project, ReadWhen
from spine.ports import DocSource

FIXTURE_CORPUS_DIR = Path(__file__).parent.parent / "fixtures" / "corpus-alpha"
EXPECTED_FIXTURE_COUNT = 10
OVERSIZED_MULTIPLIER = 3


@pytest.fixture()
def alpha_project() -> Project:
    return project_for_dir(docs_dir=FIXTURE_CORPUS_DIR)


@pytest.fixture()
def alpha_docs(alpha_project: Project) -> tuple[Doc, ...]:
    return FilesystemDocSource().load_all(project=alpha_project)


def _doc_by_stem(*, docs: tuple[Doc, ...], stem: str) -> Doc:
    return next(doc for doc in docs if doc.path.stem == stem)


def _write_doc(*, corpus_dir: Path, name: str, text: str) -> Path:
    path = corpus_dir / name
    path.write_text(text, encoding=DOC_TEXT_ENCODING)
    return path


def _oversized_doc(*, read_when: ReadWhen) -> Doc:
    line_count = cap_for(read_when=read_when) * OVERSIZED_MULTIPLIER
    return Doc(
        doc_id=f"synthetic{DOC_ID_SEPARATOR}oversized",
        path=Path(f"oversized{DOC_FILE_SUFFIX}"),
        kind=DocKind.BRIEF,
        read_when=read_when,
        title="Oversized",
        body="\n".join("filler" for _ in range(line_count)),
        project_slug="synthetic",
    )


def test_filesystem_doc_source_satisfies_the_port() -> None:
    assert isinstance(FilesystemDocSource(), DocSource)


def test_every_fixture_doc_loads(alpha_docs: tuple[Doc, ...]) -> None:
    assert len(alpha_docs) == EXPECTED_FIXTURE_COUNT
    assert all(doc.title and doc.body for doc in alpha_docs)


def test_doc_ids_are_slug_prefixed_stems(alpha_docs: tuple[Doc, ...]) -> None:
    brief = _doc_by_stem(docs=alpha_docs, stem="brief")
    assert brief.doc_id == f"corpus-alpha{DOC_ID_SEPARATOR}brief"


def test_load_all_is_deterministic_and_path_sorted(alpha_project: Project) -> None:
    first_run = FilesystemDocSource().load_all(project=alpha_project)
    second_run = FilesystemDocSource().load_all(project=alpha_project)
    assert [doc.doc_id for doc in first_run] == [doc.doc_id for doc in second_run]
    assert [doc.path for doc in first_run] == sorted(doc.path for doc in first_run)


def test_load_all_ignores_non_markdown_files(tmp_path: Path) -> None:
    _write_doc(corpus_dir=tmp_path, name="kept.md", text="# Kept\n")
    _write_doc(corpus_dir=tmp_path, name="ignored.txt", text="not a doc")
    _write_doc(corpus_dir=tmp_path, name="ignored.yaml", text="also: not a doc")
    docs = FilesystemDocSource().load_all(project=project_for_dir(docs_dir=tmp_path))
    assert [doc.path.name for doc in docs] == ["kept.md"]


def test_load_all_on_a_missing_directory_is_empty(tmp_path: Path) -> None:
    assert corpus_paths(docs_dir=tmp_path / "absent") == ()


def test_frontmatter_fields_reach_the_doc(alpha_docs: tuple[Doc, ...]) -> None:
    milestone = _doc_by_stem(docs=alpha_docs, stem="milestone-uplink-window")
    assert milestone.kind is DocKind.MILESTONE
    assert milestone.read_when is ReadWhen.IN_AREA
    assert milestone.area == "uplink"
    assert milestone.title == "Milestone — uplink window allocation"


def test_null_area_becomes_none(alpha_docs: tuple[Doc, ...]) -> None:
    assert _doc_by_stem(docs=alpha_docs, stem="brief").area is None


def test_boolean_frontmatter_sets_is_generated(alpha_docs: tuple[Doc, ...]) -> None:
    assert _doc_by_stem(docs=alpha_docs, stem="test-coverage-uplink").is_generated is True
    assert _doc_by_stem(docs=alpha_docs, stem="brief").is_generated is False


def test_body_excludes_the_frontmatter_block(alpha_docs: tuple[Doc, ...]) -> None:
    brief = _doc_by_stem(docs=alpha_docs, stem="brief")
    assert "kind: brief" not in brief.body
    assert "# Orbital Relay" in brief.body


@pytest.mark.parametrize(
    ("name", "expected_kind"),
    [
        ("project-rules.md", DocKind.PROJECT_RULES),
        ("brief.md", DocKind.BRIEF),
        ("classification.md", DocKind.CLASSIFICATION),
        ("decisions.md", DocKind.DECISION_LOG),
        ("open-questions.md", DocKind.OPEN_QUESTIONS),
        ("design-scheduler.md", DocKind.AREA_DESIGN),
        ("milestone-uplink-window.md", DocKind.MILESTONE),
        ("rollout-uplink.md", DocKind.ROLLOUT),
        ("test-coverage-uplink.md", DocKind.TEST_COVERAGE),
        ("scratch-notes.md", DocKind.GENERATED),
    ],
)
def test_kind_is_inferred_from_filename(name: str, expected_kind: DocKind) -> None:
    assert infer_kind_from_filename(path=Path(name)) is expected_kind


def test_kind_falls_back_to_filename_when_frontmatter_omits_it(tmp_path: Path) -> None:
    _write_doc(
        corpus_dir=tmp_path,
        name="project-rules.md",
        text="---\ntitle: Rules\n---\n\n# Rules\n",
    )
    doc = FilesystemDocSource().load_all(project=project_for_dir(docs_dir=tmp_path))[0]
    assert doc.kind is DocKind.PROJECT_RULES
    assert doc.read_when is DEFAULT_READ_WHEN[DocKind.PROJECT_RULES]


def test_unrecognised_kind_value_falls_back_to_the_filename(tmp_path: Path) -> None:
    _write_doc(corpus_dir=tmp_path, name="rollout-uplink.md", text="---\nkind: wat\n---\n\nbody\n")
    doc = FilesystemDocSource().load_all(project=project_for_dir(docs_dir=tmp_path))[0]
    assert doc.kind is DocKind.ROLLOUT


@pytest.mark.parametrize("kind", list(DocKind))
def test_read_when_defaults_per_kind(kind: DocKind) -> None:
    assert resolve_read_when(mapping={}, kind=kind) is DEFAULT_READ_WHEN[kind]


def test_declared_read_when_overrides_the_default(alpha_docs: tuple[Doc, ...]) -> None:
    audit = _doc_by_stem(docs=alpha_docs, stem="audit-legacy-sweep")
    assert audit.kind is DocKind.AREA_DESIGN
    assert audit.read_when is ReadWhen.RARELY
    assert DEFAULT_READ_WHEN[DocKind.AREA_DESIGN] is ReadWhen.IN_AREA


def test_title_prefers_frontmatter(tmp_path: Path) -> None:
    _write_doc(
        corpus_dir=tmp_path,
        name="brief.md",
        text="---\ntitle: From frontmatter\n---\n\n# From heading\n",
    )
    doc = FilesystemDocSource().load_all(project=project_for_dir(docs_dir=tmp_path))[0]
    assert doc.title == "From frontmatter"


def test_title_falls_back_to_the_first_h1(tmp_path: Path) -> None:
    _write_doc(
        corpus_dir=tmp_path,
        name="brief.md",
        text="---\nkind: brief\n---\n\n## Not this\n\n# From heading\n",
    )
    doc = FilesystemDocSource().load_all(project=project_for_dir(docs_dir=tmp_path))[0]
    assert doc.title == "From heading"


def test_title_falls_back_to_the_filename_stem(tmp_path: Path) -> None:
    _write_doc(corpus_dir=tmp_path, name="untitled-notes.md", text="no heading at all\n")
    doc = FilesystemDocSource().load_all(project=project_for_dir(docs_dir=tmp_path))[0]
    assert doc.title == "untitled-notes"


def test_first_h1_ignores_deeper_headings() -> None:
    assert first_h1(body="## deeper\n### deeper still\n") is None


def test_lifecycle_is_read_when_present(tmp_path: Path) -> None:
    _write_doc(
        corpus_dir=tmp_path,
        name="decisions.md",
        text="---\nlifecycle: superseded\n---\n\n# Decisions\n",
    )
    doc = FilesystemDocSource().load_all(project=project_for_dir(docs_dir=tmp_path))[0]
    assert doc.lifecycle is Lifecycle.SUPERSEDED


def test_lifecycle_is_none_when_absent(alpha_docs: tuple[Doc, ...]) -> None:
    assert all(doc.lifecycle is None for doc in alpha_docs)


def test_file_without_frontmatter_yields_an_empty_mapping() -> None:
    parsed = parse_frontmatter(text="# Just a heading\n\nBody text.\n")
    assert parsed.mapping == {}
    assert parsed.body.startswith("# Just a heading")
    assert parsed.body_start_line == 1


def test_body_start_line_points_past_the_closing_delimiter() -> None:
    parsed = parse_frontmatter(text="---\nkind: brief\n---\nbody line\n")
    assert parsed.body_start_line == 4
    assert parsed.body == "body line"


def test_unterminated_frontmatter_does_not_crash() -> None:
    parsed = parse_frontmatter(text="---\nkind: brief\nno closing delimiter\n")
    assert parsed.mapping == {}
    assert parsed.body_start_line == 1


def test_malformed_entries_are_skipped_not_fatal() -> None:
    parsed = parse_frontmatter(
        text="---\nthis line has no separator\n: missing key\n\n# comment\nkind: brief\n---\n\nbody\n"
    )
    assert parsed.mapping == {"kind": "brief"}


def test_malformed_file_still_loads(tmp_path: Path) -> None:
    _write_doc(
        corpus_dir=tmp_path,
        name="broken.md",
        text="---\n{{ not: [yaml, at: all\nkind\n---\n\n# Broken\n",
    )
    doc = FilesystemDocSource().load_all(project=project_for_dir(docs_dir=tmp_path))[0]
    assert doc.kind is DocKind.GENERATED
    assert doc.title == "Broken"


def test_scalar_kinds_are_parsed() -> None:
    parsed = parse_frontmatter(
        text="---\narea: null\ngenerated: true\nsealed: false\ntitle: A Title\nempty:\n---\n\nbody\n"
    )
    assert parsed.mapping == {
        "area": None,
        "generated": True,
        "sealed": False,
        "title": "A Title",
        "empty": None,
    }


def test_inline_lists_are_parsed() -> None:
    parsed = parse_frontmatter(
        text="---\ntags: [uplink, scheduler, clock]\nnone: []\n---\n\nbody\n"
    )
    assert parsed.mapping["tags"] == ["uplink", "scheduler", "clock"]
    assert parsed.mapping["none"] == []


def test_quoted_values_lose_their_quotes() -> None:
    parsed = parse_frontmatter(
        text="---\ntitle: \"Quoted: with colon\"\narea: 'uplink'\n---\n\nx\n"
    )
    assert parsed.mapping["title"] == "Quoted: with colon"
    assert parsed.mapping["area"] == "uplink"


def test_fixture_corpus_is_within_its_caps(alpha_docs: tuple[Doc, ...]) -> None:
    assert find_cap_breaches(docs=alpha_docs) == ()


def test_cap_breach_reports_the_overrun() -> None:
    doc = _oversized_doc(read_when=ReadWhen.EVERY_TIME)
    breaches = find_cap_breaches(docs=[doc])
    assert len(breaches) == 1
    assert breaches[0].doc is doc
    assert breaches[0].cap_lines == cap_for(read_when=ReadWhen.EVERY_TIME)
    assert breaches[0].excess_lines == doc.line_count - breaches[0].cap_lines


def test_a_doc_at_exactly_its_cap_does_not_breach() -> None:
    read_when = ReadWhen.EVERY_TIME
    doc = _oversized_doc(read_when=read_when)
    doc.body = "\n".join("filler" for _ in range(cap_for(read_when=read_when)))
    assert find_cap_breaches(docs=[doc]) == ()


def test_breaches_are_ordered_by_worst_overrun() -> None:
    every_time = _oversized_doc(read_when=ReadWhen.EVERY_TIME)
    log = _oversized_doc(read_when=ReadWhen.LOG)
    breaches = find_cap_breaches(docs=[every_time, log])
    assert [breach.excess_lines for breach in breaches] == sorted(
        (breach.excess_lines for breach in breaches), reverse=True
    )


def test_docs_list_command_prints_a_row_per_doc(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["docs", "list", "--dir", str(FIXTURE_CORPUS_DIR)])
    printed = capsys.readouterr().out.strip().splitlines()
    assert exit_code == 0
    assert len(printed) == EXPECTED_FIXTURE_COUNT


def test_docs_check_command_passes_on_a_clean_corpus(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["docs", "check", "--dir", str(FIXTURE_CORPUS_DIR)]) == 0
    assert capsys.readouterr().out == ""


def test_docs_check_command_fails_on_a_breach(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    over_cap = cap_for(read_when=ReadWhen.EVERY_TIME) * OVERSIZED_MULTIPLIER
    body = "\n".join(f"line {number}" for number in range(over_cap))
    _write_doc(corpus_dir=tmp_path, name="brief.md", text=f"---\nkind: brief\n---\n\n{body}\n")
    assert main(["docs", "check", "--dir", str(tmp_path)]) == EXIT_CAP_BREACH
    assert "brief" in capsys.readouterr().out


@pytest.mark.parametrize("action", [DOCS_LIST_ACTION, DOCS_CHECK_ACTION])
def test_a_missing_dir_is_a_usage_error_not_a_clean_pass(
    action: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main([DOCS_COMMAND_NAME, action, DOCS_DIR_OPTION, str(tmp_path / "absent")])
    assert exit_code != 0
    assert "absent" in capsys.readouterr().err


def test_docs_help_is_available(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["docs", "--help"])
    assert raised.value.code == 0
    assert "check" in capsys.readouterr().out
