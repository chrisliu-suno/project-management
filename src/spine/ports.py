"""Interfaces between modules.

Each module owns one implementation. Depend on the protocol, never on a sibling's
concrete class, so modules stay independently replaceable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from .model import Doc, Link, LinkType, Project, ProjectMatch, Selection, SessionStamp


@runtime_checkable
class ProjectRegistry(Protocol):
    """Knows which projects exist."""

    def all_projects(self) -> tuple[Project, ...]: ...

    def get(self, slug: str) -> Project | None: ...


@runtime_checkable
class ProjectResolver(Protocol):
    """Maps a running session to the projects it belongs to.

    Returns candidates rather than one answer: work spanning two projects is two
    attachments, not a resolution failure. An empty result means no project.
    """

    def resolve(
        self,
        *,
        cwd: Path,
        branch: str | None = None,
        repo: str | None = None,
        opening_prompt: str | None = None,
    ) -> tuple[ProjectMatch, ...]: ...


@runtime_checkable
class DocSource(Protocol):
    """Reads a project's corpus off disk."""

    def load_all(self, *, project: Project) -> tuple[Doc, ...]: ...

    def load_one(self, *, project: Project, path: Path) -> Doc: ...


@runtime_checkable
class LinkExtractor(Protocol):
    """Derives typed connections from document text."""

    def extract(self, *, doc: Doc, corpus: tuple[Doc, ...]) -> tuple[Link, ...]: ...


@runtime_checkable
class GraphStore(Protocol):
    """Persists docs and their extracted links."""

    def replace_project(
        self, *, project_slug: str, docs: tuple[Doc, ...], links: tuple[Link, ...]
    ) -> None: ...

    def docs_for_project(self, *, project_slug: str) -> tuple[Doc, ...]: ...

    def outbound(self, *, doc_id: str, link_type: LinkType | None = None) -> tuple[Link, ...]: ...

    def inbound(self, *, doc_id: str, link_type: LinkType | None = None) -> tuple[Link, ...]: ...

    def orphans(self, *, project_slug: str) -> tuple[Doc, ...]: ...


@runtime_checkable
class ContextPicker(Protocol):
    """Chooses which documents a session should be given."""

    def pick(
        self,
        *,
        project: Project,
        task_context: str,
        line_budget: int,
    ) -> Selection: ...


@runtime_checkable
class SessionStore(Protocol):
    """Reads and writes the project stamp a session carries."""

    def read(self, *, session_id: str) -> SessionStamp | None: ...

    def write(self, *, stamp: SessionStamp) -> None: ...


@runtime_checkable
class PickRecorder(Protocol):
    """Records every selection so a session's loaded context is recoverable.

    Recording is unconditional and silent; surfacing is a separate concern.
    """

    def record(
        self,
        *,
        session_id: str,
        project_slug: str,
        selection: Selection,
        confidence: float,
    ) -> None: ...
