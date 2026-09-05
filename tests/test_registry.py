"""M1 — registry storage and signal resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from spine.cli import EXIT_ERROR, EXIT_OK, build_parser, main
from spine.constants import (
    BRANCH_PREFIX_MATCH_CONFIDENCE,
    EXACT_MATCH_CONFIDENCE,
    MIN_CONFIDENCE_FOR_AUTO_ATTACH,
    PATH_GLOB_MATCH_CONFIDENCE,
    REGISTRY_FILE_NAME,
    REPO_MATCH_CONFIDENCE,
    SPINE_HOME_ENV_VAR,
)
from spine.model import Project
from spine.paths import registry_path
from spine.ports import ProjectRegistry, ProjectResolver
from spine.registry import (
    AUTO_ATTACH_MARKER,
    RegistryError,
    SignalResolver,
    TomlProjectRegistry,
)

STATE_DIR_NAME = "state"
RELAY_SLUG = "orbital-relay"
LEDGER_SLUG = "tidal-ledger"
RELAY_REPO = "chrisliu-suno/relay"
RELAY_BRANCH_PREFIX = "chris/feat/uplink"


@pytest.fixture(autouse=True)
def spine_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(SPINE_HOME_ENV_VAR, str(tmp_path / STATE_DIR_NAME))
    return tmp_path


def _relay_project(*, root: Path) -> Project:
    return Project(
        slug=RELAY_SLUG,
        name="Orbital Relay",
        docs_dir=root / "docs" / RELAY_SLUG,
        repos=(RELAY_REPO,),
        path_globs=(f"{root}/relay*",),
        branch_prefixes=(RELAY_BRANCH_PREFIX,),
        linear_project="REL",
    )


def _ledger_project(*, root: Path) -> Project:
    return Project(
        slug=LEDGER_SLUG,
        name="Tidal Ledger",
        docs_dir=root / "docs" / LEDGER_SLUG,
        repos=("chrisliu-suno/ledger",),
        path_globs=(f"{root}/relay*",),
        branch_prefixes=("chris/feat/ledger",),
    )


def _write_raw_registry(*, body: str) -> Path:
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_missing_registry_reads_as_empty() -> None:
    registry = TomlProjectRegistry()
    assert registry.all_projects() == ()
    assert registry.get(slug=RELAY_SLUG) is None


def test_empty_registry_file_reads_as_empty() -> None:
    _write_raw_registry(body="")
    assert TomlProjectRegistry().all_projects() == ()


def test_registry_path_follows_the_home_env_var(spine_home: Path) -> None:
    assert TomlProjectRegistry().path == spine_home / STATE_DIR_NAME / REGISTRY_FILE_NAME


def test_add_then_list_round_trips_every_field(spine_home: Path) -> None:
    registry = TomlProjectRegistry()
    registry.add_project(project=_relay_project(root=spine_home))
    assert registry.all_projects() == (_relay_project(root=spine_home),)


def test_add_is_idempotent_on_slug(spine_home: Path) -> None:
    registry = TomlProjectRegistry()
    registry.add_project(project=_relay_project(root=spine_home))
    renamed = Project(slug=RELAY_SLUG, name="Renamed", docs_dir=spine_home / "elsewhere")
    registry.add_project(project=renamed)
    assert registry.all_projects() == (renamed,)


def test_projects_are_listed_in_slug_order(spine_home: Path) -> None:
    registry = TomlProjectRegistry()
    registry.add_project(project=_ledger_project(root=spine_home))
    registry.add_project(project=_relay_project(root=spine_home))
    assert [project.slug for project in registry.all_projects()] == [RELAY_SLUG, LEDGER_SLUG]


def test_get_returns_the_named_project(spine_home: Path) -> None:
    registry = TomlProjectRegistry()
    registry.add_project(project=_relay_project(root=spine_home))
    assert registry.get(slug=RELAY_SLUG) == _relay_project(root=spine_home)
    assert registry.get(slug="absent") is None


def test_remove_project_reports_whether_it_removed_anything(spine_home: Path) -> None:
    registry = TomlProjectRegistry()
    registry.add_project(project=_relay_project(root=spine_home))
    assert registry.remove_project(slug="absent") is False
    assert registry.remove_project(slug=RELAY_SLUG) is True
    assert registry.all_projects() == ()


def test_quoted_values_survive_the_round_trip(spine_home: Path) -> None:
    registry = TomlProjectRegistry()
    awkward = Project(slug=RELAY_SLUG, name='Relay "v2" \\ beta', docs_dir=spine_home / "docs")
    registry.add_project(project=awkward)
    assert registry.get(slug=RELAY_SLUG) == awkward


def test_tilde_in_docs_dir_is_expanded() -> None:
    _write_raw_registry(
        body='[projects.orbital-relay]\nname = "Orbital Relay"\ndocs_dir = "~/dev/docs/relay"\n'
    )
    project = TomlProjectRegistry().get(slug=RELAY_SLUG)
    assert project is not None
    assert project.docs_dir == Path.home() / "dev/docs/relay"


def test_malformed_toml_raises_registry_error() -> None:
    _write_raw_registry(body="[projects.orbital-relay\nname = ")
    with pytest.raises(RegistryError):
        TomlProjectRegistry().all_projects()


def test_missing_required_key_raises_registry_error() -> None:
    _write_raw_registry(body='[projects.orbital-relay]\nname = "Orbital Relay"\n')
    with pytest.raises(RegistryError):
        TomlProjectRegistry().all_projects()


def test_wrong_typed_list_raises_registry_error() -> None:
    _write_raw_registry(
        body='[projects.orbital-relay]\nname = "R"\ndocs_dir = "/tmp/r"\nrepos = [1, 2]\n'
    )
    with pytest.raises(RegistryError):
        TomlProjectRegistry().all_projects()


def test_projects_key_that_is_not_a_table_raises_registry_error() -> None:
    _write_raw_registry(body='projects = "nope"\n')
    with pytest.raises(RegistryError):
        TomlProjectRegistry().all_projects()


def _resolver_with(*, projects: tuple[Project, ...]) -> SignalResolver:
    registry = TomlProjectRegistry()
    for project in projects:
        registry.add_project(project=project)
    return SignalResolver(registry=registry)


def test_repo_signal_matches_one_project(spine_home: Path) -> None:
    resolver = _resolver_with(
        projects=(_relay_project(root=spine_home), _ledger_project(root=spine_home))
    )
    matches = resolver.resolve(cwd=spine_home / "unrelated", repo=RELAY_REPO)
    assert [match.project.slug for match in matches] == [RELAY_SLUG]
    assert matches[0].confidence == REPO_MATCH_CONFIDENCE
    assert matches[0].evidence == (f"repo {RELAY_REPO}",)


def test_branch_prefix_signal_names_the_prefix_in_evidence(spine_home: Path) -> None:
    resolver = _resolver_with(projects=(_relay_project(root=spine_home),))
    matches = resolver.resolve(cwd=spine_home / "unrelated", branch=f"{RELAY_BRANCH_PREFIX}-retry")
    assert matches[0].evidence == (f"branch prefix {RELAY_BRANCH_PREFIX}",)
    assert matches[0].confidence == BRANCH_PREFIX_MATCH_CONFIDENCE


def test_path_glob_matches_a_nested_working_directory(spine_home: Path) -> None:
    resolver = _resolver_with(projects=(_relay_project(root=spine_home),))
    matches = resolver.resolve(cwd=spine_home / "relay-uplink" / "src" / "deep")
    assert matches[0].confidence == PATH_GLOB_MATCH_CONFIDENCE
    assert matches[0].evidence == (f"path glob {spine_home}/relay*",)


def test_opening_prompt_mention_is_a_signal(spine_home: Path) -> None:
    resolver = _resolver_with(projects=(_relay_project(root=spine_home),))
    matches = resolver.resolve(
        cwd=spine_home / "unrelated", opening_prompt="pick up the Orbital Relay uplink work"
    )
    assert matches[0].evidence == ('prompt mentions "Orbital Relay"',)


def test_stacked_signals_stay_below_exact_match(spine_home: Path) -> None:
    resolver = _resolver_with(projects=(_relay_project(root=spine_home),))
    matches = resolver.resolve(
        cwd=spine_home / "relay-uplink",
        branch=RELAY_BRANCH_PREFIX,
        repo=RELAY_REPO,
        opening_prompt=RELAY_SLUG,
    )
    assert matches[0].confidence < EXACT_MATCH_CONFIDENCE
    assert len(matches[0].evidence) == 4


def test_more_signals_always_rank_higher(spine_home: Path) -> None:
    resolver = _resolver_with(projects=(_relay_project(root=spine_home),))
    two_signals = resolver.resolve(cwd=spine_home / "relay-uplink", branch=RELAY_BRANCH_PREFIX)
    three_signals = resolver.resolve(
        cwd=spine_home / "relay-uplink", branch=RELAY_BRANCH_PREFIX, repo=RELAY_REPO
    )
    assert three_signals[0].confidence > two_signals[0].confidence


def test_a_single_signal_keeps_its_own_weight(spine_home: Path) -> None:
    resolver = _resolver_with(projects=(_relay_project(root=spine_home),))
    matches = resolver.resolve(cwd=spine_home / "unrelated", repo=RELAY_REPO)
    assert matches[0].confidence == REPO_MATCH_CONFIDENCE


def test_two_projects_can_match_the_same_session(spine_home: Path) -> None:
    resolver = _resolver_with(
        projects=(_relay_project(root=spine_home), _ledger_project(root=spine_home))
    )
    matches = resolver.resolve(cwd=spine_home / "relay-uplink", repo=RELAY_REPO)
    assert [match.project.slug for match in matches] == [RELAY_SLUG, LEDGER_SLUG]
    assert matches[0].confidence > matches[1].confidence


def test_no_signal_returns_no_match(spine_home: Path) -> None:
    resolver = _resolver_with(projects=(_relay_project(root=spine_home),))
    matches = resolver.resolve(
        cwd=spine_home / "unrelated", branch="chris/feat/other", repo="other/repo"
    )
    assert matches == ()


def test_empty_registry_resolves_to_no_match(spine_home: Path) -> None:
    resolver = SignalResolver(registry=TomlProjectRegistry())
    assert resolver.resolve(cwd=spine_home) == ()


def test_implementations_satisfy_the_shared_protocols() -> None:
    registry = TomlProjectRegistry()
    assert isinstance(registry, ProjectRegistry)
    assert isinstance(SignalResolver(registry=registry), ProjectResolver)


def test_registry_subcommand_is_registered() -> None:
    assert "registry" in build_parser().format_help()


def test_cli_add_then_list_and_resolve(
    spine_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    added = main(
        [
            "registry",
            "add",
            RELAY_SLUG,
            "--name",
            "Orbital Relay",
            "--docs-dir",
            str(spine_home / "docs"),
            "--repo",
            RELAY_REPO,
        ]
    )
    assert added == EXIT_OK
    assert main(["registry", "list"]) == EXIT_OK
    assert RELAY_SLUG in capsys.readouterr().out

    assert main(["registry", "resolve", "--cwd", str(spine_home), "--repo", RELAY_REPO]) == EXIT_OK
    resolved = capsys.readouterr().out
    assert RELAY_SLUG in resolved
    has_marker = AUTO_ATTACH_MARKER in resolved
    assert has_marker is (REPO_MATCH_CONFIDENCE >= MIN_CONFIDENCE_FOR_AUTO_ATTACH)


def test_cli_resolve_reports_no_match(spine_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["registry", "resolve", "--cwd", str(spine_home)]) == EXIT_OK
    assert "no project matched" in capsys.readouterr().out


def test_cli_reports_a_malformed_registry(capsys: pytest.CaptureFixture[str]) -> None:
    _write_raw_registry(body="[projects.orbital-relay\n")
    assert main(["registry", "list"]) == EXIT_ERROR
    assert capsys.readouterr().err.strip() != ""
