"""Shared shapes for the project dashboard.

Both the health analysis and the HTTP layer are written against these, so the
two can be built independently.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum


class Severity(StrEnum):
    """How much a finding should pull the eye."""

    OK = "ok"
    WARN = "warn"
    PROBLEM = "problem"


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing worth knowing about a project's corpus."""

    code: str
    severity: Severity
    headline: str
    detail: str
    doc_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {**asdict(self), "severity": str(self.severity), "doc_ids": list(self.doc_ids)}


@dataclass(frozen=True, slots=True)
class ProjectSnapshot:
    """Everything the dashboard shows for one project."""

    slug: str
    name: str
    docs_dir: str
    doc_count: int
    entry_count: int
    link_count: int
    total_lines: int
    kind_counts: dict[str, int] = field(default_factory=dict)
    read_when_counts: dict[str, int] = field(default_factory=dict)
    findings: tuple[Finding, ...] = ()
    plan: dict[str, object] = field(default_factory=dict)

    @property
    def worst_severity(self) -> Severity:
        if any(finding.severity is Severity.PROBLEM for finding in self.findings):
            return Severity.PROBLEM
        if any(finding.severity is Severity.WARN for finding in self.findings):
            return Severity.WARN
        return Severity.OK

    def as_dict(self) -> dict[str, object]:
        return {
            "slug": self.slug,
            "name": self.name,
            "docs_dir": self.docs_dir,
            "doc_count": self.doc_count,
            "entry_count": self.entry_count,
            "link_count": self.link_count,
            "total_lines": self.total_lines,
            "plan": self.plan,
            "kind_counts": dict(self.kind_counts),
            "read_when_counts": dict(self.read_when_counts),
            "worst_severity": str(self.worst_severity),
            "findings": [finding.as_dict() for finding in self.findings],
        }


@dataclass(frozen=True, slots=True)
class PickPreview:
    """What the picker would inject for a task, rendered for display."""

    project_slug: str
    task: str
    chosen: tuple[dict[str, object], ...]
    dropped: tuple[dict[str, object], ...]
    total_lines: int
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "project_slug": self.project_slug,
            "task": self.task,
            "chosen": [dict(entry) for entry in self.chosen],
            "dropped": [dict(entry) for entry in self.dropped],
            "total_lines": self.total_lines,
            "plan": self.plan,
            "reason": self.reason,
        }
