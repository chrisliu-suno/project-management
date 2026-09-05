"""Domain types shared by every module."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class ReadWhen(StrEnum):
    """When an agent needs a document. The axis the corpus is split on."""

    EVERY_TIME = "every_time"
    IN_AREA = "in_area"
    RARELY = "rarely"
    LOOKED_UP = "looked_up"
    LOG = "log"


class DocKind(StrEnum):
    BRIEF = "brief"
    PROJECT_RULES = "project_rules"
    CLASSIFICATION = "classification"
    MILESTONE = "milestone"
    AREA_DESIGN = "area_design"
    ROLLOUT = "rollout"
    TEST_COVERAGE = "test_coverage"
    DECISION_LOG = "decision_log"
    OPEN_QUESTIONS = "open_questions"
    GENERATED = "generated"


class LinkType(StrEnum):
    """Vocabulary the extractor labels connections as."""

    CONSTRAINS = "constrains"
    CLASSIFIES = "classifies"
    IMPLEMENTS = "implements"
    SUPERSEDES = "supersedes"
    CITED_BY = "cited_by"
    VERIFIES = "verifies"
    RAMPS = "ramps"
    DEPENDS_ON = "depends_on"
    BLOCKS = "blocks"
    DERIVED_FROM = "derived_from"
    MENTIONS = "mentions"


class Lifecycle(StrEnum):
    """Where the thinking stands on an item. Also drives the interrupt filter."""

    OPEN_QUESTION = "open_question"
    ASSUMPTION = "assumption"
    DECIDED = "decided"
    SUPERSEDED = "superseded"


DEFAULT_READ_WHEN: dict[DocKind, ReadWhen] = {
    DocKind.BRIEF: ReadWhen.EVERY_TIME,
    DocKind.PROJECT_RULES: ReadWhen.EVERY_TIME,
    DocKind.CLASSIFICATION: ReadWhen.EVERY_TIME,
    DocKind.MILESTONE: ReadWhen.IN_AREA,
    DocKind.AREA_DESIGN: ReadWhen.IN_AREA,
    DocKind.ROLLOUT: ReadWhen.IN_AREA,
    DocKind.TEST_COVERAGE: ReadWhen.IN_AREA,
    DocKind.DECISION_LOG: ReadWhen.LOG,
    DocKind.OPEN_QUESTIONS: ReadWhen.LOG,
    DocKind.GENERATED: ReadWhen.LOOKED_UP,
}


@dataclass(frozen=True, slots=True)
class Project:
    """One project's identity and the signals that map a session to it."""

    slug: str
    name: str
    docs_dir: Path
    repos: tuple[str, ...] = ()
    path_globs: tuple[str, ...] = ()
    branch_prefixes: tuple[str, ...] = ()
    linear_project: str | None = None


@dataclass(frozen=True, slots=True)
class ProjectMatch:
    """A resolver candidate, with how sure it is and what made it think so."""

    project: Project
    confidence: float
    evidence: tuple[str, ...] = ()


@dataclass(slots=True)
class Doc:
    """One document in a project corpus."""

    doc_id: str
    path: Path
    kind: DocKind
    read_when: ReadWhen
    title: str
    body: str
    project_slug: str
    area: str | None = None
    lifecycle: Lifecycle | None = None
    frontmatter: dict[str, object] = field(default_factory=dict)
    is_generated: bool = False

    @property
    def line_count(self) -> int:
        return self.body.count("\n") + 1


@dataclass(frozen=True, slots=True)
class Link:
    """An extracted connection. Confidence drops below 1.0 when a model inferred it."""

    src_id: str
    dst_id: str
    link_type: LinkType
    confidence: float = 1.0
    evidence: str = ""


@dataclass(frozen=True, slots=True)
class SessionStamp:
    """A session's project attachment, written at launch."""

    session_id: str
    project_slugs: tuple[str, ...]
    started_at: datetime
    intent: str | None = None
    source: str = "stamp"


@dataclass(frozen=True, slots=True)
class Selection:
    """What the picker chose and what it left out under budget."""

    chosen: tuple[Doc, ...]
    dropped: tuple[Doc, ...] = ()
    total_lines: int = 0
    reason: str = ""
