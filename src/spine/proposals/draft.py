"""Drafts document edits from observed facts, and applies accepted ones."""

from __future__ import annotations

import hashlib
from pathlib import Path

from ..constants import PROPOSAL_APPEND_HEADING, SHIPPED_LOG_FILE_NAME, SHIPPED_LOG_STEM
from ..facts.model import Fact, FactKind, PullRequestState
from ..live.store import now_iso
from ..model import Doc, DocKind, Project, ReadWhen
from .model import Proposal, ProposalKind, ProposalState

CONTENT_ENCODING = "utf-8"
ID_DIGEST_LENGTH = 12
FRONTMATTER_FENCE = "---"
LINE_SEPARATOR = "\n"
MARKDOWN_HEADING_PREFIX = "#"


def proposal_id_for(*, doc_id: str, body: str) -> str:
    """Content-stable id, so drafting the same edit twice does not queue it twice."""
    digest = hashlib.sha256(f"{doc_id}\n{body}".encode(CONTENT_ENCODING)).hexdigest()
    return f"{doc_id}:{digest[:ID_DIGEST_LENGTH]}"


def _shipped_log_id(*, project: Project) -> str:
    return f"{project.slug}:{SHIPPED_LOG_STEM}"


def _shipped_log_text(*, project: Project) -> str:
    """A new shipped log: looked up, never loaded whole, and generated."""
    return LINE_SEPARATOR.join(
        (
            FRONTMATTER_FENCE,
            f"title: {project.name} — shipped work",
            f"kind: {DocKind.GENERATED}",
            f"read_when: {ReadWhen.LOOKED_UP}",
            FRONTMATTER_FENCE,
            "",
            f"# {project.name} — shipped work",
            "",
            "Merged pull requests no other document here mentions, recorded as spine observed them.",
        )
    )


def _merged_lines(*, facts: tuple[Fact, ...], mentioned: frozenset[str]) -> tuple[str, ...]:
    merged = [
        fact
        for fact in facts
        if fact.kind is FactKind.PULL_REQUEST
        and fact.state == str(PullRequestState.MERGED)
        and fact.reference.lstrip("#") not in mentioned
    ]
    merged.sort(key=lambda fact: fact.reference)
    return tuple(f"- {fact.reference} — {fact.title}".rstrip() for fact in merged)


def draft_from_drift(
    *, project: Project, docs: tuple[Doc, ...], facts: tuple[Fact, ...]
) -> tuple[Proposal, ...]:
    """A proposal recording merged work the corpus does not mention."""
    from ..facts.drift import referenced_pull_requests

    if not facts:
        return ()
    mentioned = frozenset(
        number
        for numbers in referenced_pull_requests(docs=docs).values()
        for number in numbers
    )
    lines = _merged_lines(facts=facts, mentioned=mentioned)
    if not lines:
        return ()
    body = "\n".join((PROPOSAL_APPEND_HEADING, "", *lines))
    doc_id = _shipped_log_id(project=project)
    return (
        Proposal(
            proposal_id=proposal_id_for(doc_id=doc_id, body=body),
            project_slug=project.slug,
            doc_id=doc_id,
            doc_path=SHIPPED_LOG_FILE_NAME,
            kind=ProposalKind.APPEND,
            headline=f"Record {len(lines)} merged pull request(s) in {project.name}'s shipped log",
            rationale="These shipped but no document in this project mentions them.",
            body=body,
            state=ProposalState.PENDING,
            created_at=now_iso(),
        ),
    )


def _end_of_section(*, lines: list[str], heading_index: int) -> int:
    """Index one past the last line belonging to the section opened at heading_index."""
    for offset, line in enumerate(lines[heading_index + 1 :], start=heading_index + 1):
        if line.startswith(MARKDOWN_HEADING_PREFIX):
            return offset
    return len(lines)


def _folded_into(*, existing: str, body: str) -> str | None:
    """The document with the proposal folded in, or None when it adds nothing.

    A proposal is drafted against the corpus as it stood then, so its heading and
    some of its lines can already be in the document by the time it is applied.
    """
    heading, _, entries = body.partition(LINE_SEPARATOR)
    lines = existing.splitlines()
    present = frozenset(line.strip() for line in lines if line.strip())
    fresh = [
        line.strip() for line in entries.splitlines() if line.strip() and line.strip() not in present
    ]
    if not fresh:
        return None
    if heading not in present:
        return LINE_SEPARATOR.join([*lines, "", heading, "", *fresh]) + "\n"
    heading_index = lines.index(heading)
    end = _end_of_section(lines=lines, heading_index=heading_index)
    kept = [line for line in lines[heading_index:end] if line.strip()]
    rebuilt = [*lines[:heading_index], *kept, *fresh, "", *lines[end:]]
    return LINE_SEPARATOR.join(rebuilt).rstrip("\n") + "\n"


def _brief_path(*, docs_dir: Path, project_slug: str) -> Path | None:
    """The brief as the loader sees it: declared, named like an entry point, or classified."""
    from ..index import load_corpus

    briefs = sorted(
        doc.path
        for doc in load_corpus(docs_dir=docs_dir, project_slug=project_slug)
        if doc.kind is DocKind.BRIEF and doc.path.parent == docs_dir
    )
    return briefs[0] if briefs else None


def _link_from_brief(*, shipped_log: Path, project_slug: str) -> None:
    """Point the brief at the shipped log, so it is reachable like every other document.

    Idempotent, and tried on every accept: an attempt that failed is retried next time.
    """
    try:
        brief = _brief_path(docs_dir=shipped_log.parent, project_slug=project_slug)
        if brief is None:
            return
        text = brief.read_text(encoding=CONTENT_ENCODING)
    except (OSError, UnicodeDecodeError):
        return
    if SHIPPED_LOG_FILE_NAME in text:
        return
    link = f"Merged work no other document mentions is in [shipped work]({SHIPPED_LOG_FILE_NAME})."
    brief.write_text(text.rstrip("\n") + "\n\n" + link + "\n", encoding=CONTENT_ENCODING)


def apply_proposal(*, proposal: Proposal, project_name: str | None = None) -> bool:
    """Append the proposed text to its document; returns False when nothing was written.

    The shipped log is created on first use, and linked once from the brief.
    """
    target = Path(proposal.doc_path)
    is_shipped_log = target.name == SHIPPED_LOG_FILE_NAME and target.parent.is_dir()
    if is_shipped_log and not target.is_file():
        project = Project(
            slug=proposal.project_slug,
            name=project_name or proposal.project_slug,
            docs_dir=target.parent,
        )
        target.write_text(_shipped_log_text(project=project) + "\n", encoding=CONTENT_ENCODING)
    if is_shipped_log:
        _link_from_brief(shipped_log=target, project_slug=proposal.project_slug)
    if not target.is_file():
        return False
    existing = target.read_text(encoding=CONTENT_ENCODING).rstrip("\n")
    folded = _folded_into(existing=existing, body=proposal.body)
    if folded is None:
        return False
    target.write_text(folded, encoding=CONTENT_ENCODING)
    return True
