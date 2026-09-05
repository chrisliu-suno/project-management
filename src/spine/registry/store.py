"""Reads and writes the TOML file that says which projects exist."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path

from ..constants import (
    REGISTRY_BARE_KEY_EXTRA_CHARS,
    REGISTRY_KEY_BRANCH_PREFIXES,
    REGISTRY_KEY_DOCS_DIR,
    REGISTRY_KEY_LINEAR_PROJECT,
    REGISTRY_KEY_NAME,
    REGISTRY_KEY_PATH_GLOBS,
    REGISTRY_KEY_REPOS,
    REGISTRY_PROJECTS_TABLE,
)
from ..model import Project
from ..paths import registry_path


class RegistryError(Exception):
    """Raised when the registry file exists but cannot be read as project definitions."""


class TomlProjectRegistry:
    """Project definitions backed by registry.toml, one table per project."""

    def __init__(self, *, path: Path | None = None) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        """Resolved lazily so an environment override set after construction still applies."""
        return self._path if self._path is not None else registry_path()

    def all_projects(self) -> tuple[Project, ...]:
        tables = self._read_project_tables()
        projects = [_project_from_table(slug=slug, table=table) for slug, table in tables.items()]
        return tuple(sorted(projects, key=lambda project: project.slug))

    def get(self, slug: str) -> Project | None:
        for project in self.all_projects():
            if project.slug == slug:
                return project
        return None

    def add_project(self, *, project: Project) -> None:
        """Insert the project, replacing any existing definition with the same slug."""
        kept = [known for known in self.all_projects() if known.slug != project.slug]
        self._write_projects(projects=(*kept, project))

    def remove_project(self, *, slug: str) -> bool:
        """Drop the project. Returns False when the slug was not registered."""
        known = self.all_projects()
        kept = tuple(project for project in known if project.slug != slug)
        if len(kept) == len(known):
            return False
        self._write_projects(projects=kept)
        return True

    def _read_project_tables(self) -> Mapping[str, object]:
        path = self.path
        if not path.is_file():
            return {}
        try:
            with path.open("rb") as handle:
                document = tomllib.load(handle)
        except tomllib.TOMLDecodeError as error:
            raise RegistryError(f"{path} is not valid TOML: {error}") from error
        except OSError as error:
            raise RegistryError(f"{path} could not be read: {error}") from error
        tables = document.get(REGISTRY_PROJECTS_TABLE, {})
        if not isinstance(tables, Mapping):
            raise RegistryError(f"{path}: [{REGISTRY_PROJECTS_TABLE}] must be a table")
        return tables

    def _write_projects(self, *, projects: Sequence[Project]) -> None:
        ordered = sorted(projects, key=lambda project: project.slug)
        body = "".join(_render_project(project=project) for project in ordered)
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


def _project_from_table(*, slug: str, table: object) -> Project:
    if not isinstance(table, Mapping):
        raise RegistryError(f"project {slug!r} must be a table")
    docs_dir = _required_string(slug=slug, table=table, key=REGISTRY_KEY_DOCS_DIR)
    return Project(
        slug=slug,
        name=_required_string(slug=slug, table=table, key=REGISTRY_KEY_NAME),
        docs_dir=Path(docs_dir).expanduser(),
        repos=_string_tuple(slug=slug, table=table, key=REGISTRY_KEY_REPOS),
        path_globs=_string_tuple(slug=slug, table=table, key=REGISTRY_KEY_PATH_GLOBS),
        branch_prefixes=_string_tuple(slug=slug, table=table, key=REGISTRY_KEY_BRANCH_PREFIXES),
        linear_project=_optional_string(slug=slug, table=table, key=REGISTRY_KEY_LINEAR_PROJECT),
    )


def _required_string(*, slug: str, table: Mapping[str, object], key: str) -> str:
    value = _optional_string(slug=slug, table=table, key=key)
    if value is None:
        raise RegistryError(f"project {slug!r} is missing required key {key!r}")
    return value


def _optional_string(*, slug: str, table: Mapping[str, object], key: str) -> str | None:
    value = table.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise RegistryError(f"project {slug!r}: {key!r} must be a string")
    return value


def _string_tuple(*, slug: str, table: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = table.get(key)
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RegistryError(f"project {slug!r}: {key!r} must be a list of strings")
    return tuple(value)


def _render_project(*, project: Project) -> str:
    lines = [
        f"[{REGISTRY_PROJECTS_TABLE}.{_render_key(key=project.slug)}]",
        f"{REGISTRY_KEY_NAME} = {_render_string(value=project.name)}",
        f"{REGISTRY_KEY_DOCS_DIR} = {_render_string(value=str(project.docs_dir))}",
        f"{REGISTRY_KEY_REPOS} = {_render_array(values=project.repos)}",
        f"{REGISTRY_KEY_PATH_GLOBS} = {_render_array(values=project.path_globs)}",
        f"{REGISTRY_KEY_BRANCH_PREFIXES} = {_render_array(values=project.branch_prefixes)}",
    ]
    if project.linear_project is not None:
        lines.append(
            f"{REGISTRY_KEY_LINEAR_PROJECT} = {_render_string(value=project.linear_project)}"
        )
    return "\n".join(lines) + "\n\n"


def _render_key(*, key: str) -> str:
    """Quote a table key unless every character is legal in a TOML bare key."""
    is_bare = bool(key) and all(
        char.isalnum() or char in REGISTRY_BARE_KEY_EXTRA_CHARS for char in key
    )
    return key if is_bare else _render_string(value=key)


def _render_string(*, value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _render_array(*, values: Sequence[str]) -> str:
    return "[" + ", ".join(_render_string(value=value) for value in values) + "]"
