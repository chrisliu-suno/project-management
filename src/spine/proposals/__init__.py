"""Proposed document edits, drafted from facts and decided by a human."""

from __future__ import annotations

import argparse
import sys

from ..cli import EXIT_OK
from .draft import apply_proposal, draft_from_drift, proposal_id_for
from .model import Proposal, ProposalKind, ProposalState
from .store import ProposalStore, proposals_db_path

__all__ = [
    "Proposal",
    "ProposalKind",
    "ProposalState",
    "ProposalStore",
    "apply_proposal",
    "decide_proposal",
    "draft_from_drift",
    "generate_for_project",
    "proposal_id_for",
    "proposals_db_path",
    "register_subcommand",
]

EXIT_UNKNOWN_PROJECT = 4
EXIT_UNKNOWN_PROPOSAL = 5
EXIT_APPLY_FAILED = 6
FIELD_SEPARATOR = "\t"


def generate_for_project(*, project) -> int:
    """Draft proposals for one project; returns how many are newly queued."""
    from ..facts import FactStore
    from ..index import load_corpus

    if not project.docs_dir.is_dir():
        return 0
    docs = load_corpus(docs_dir=project.docs_dir, project_slug=project.slug)
    facts = FactStore().for_project(project_slug=project.slug)
    drafted = draft_from_drift(project=project, docs=docs, facts=facts)
    resolved = tuple(
        Proposal(**{**proposal.as_dict(), "doc_path": str(project.docs_dir / proposal.doc_path),
                    "kind": proposal.kind, "state": proposal.state})
        for proposal in drafted
    )
    return ProposalStore().add(proposals=resolved)


def decide_proposal(*, proposal_id: str, accept: bool) -> tuple[bool, str]:
    """Record a decision and, when accepting, apply the edit."""
    store = ProposalStore()
    proposal = store.get(proposal_id=proposal_id)
    if proposal is None:
        return False, f"no proposal {proposal_id!r}"
    if proposal.state is not ProposalState.PENDING:
        return False, f"already {proposal.state}"
    if not accept:
        store.decide(proposal_id=proposal_id, state=ProposalState.REJECTED)
        return True, "rejected"
    if not apply_proposal(proposal=proposal):
        return False, f"cannot write {proposal.doc_path}"
    store.decide(proposal_id=proposal_id, state=ProposalState.ACCEPTED)
    return True, f"applied to {proposal.doc_path}"


def _project_or_none(*, slug: str):
    from ..registry import load_registry

    return load_registry().get(slug)


def _handle_generate(args: argparse.Namespace) -> int:
    project = _project_or_none(slug=args.project)
    if project is None:
        print(f"no project registered under {args.project!r}", file=sys.stderr)
        return EXIT_UNKNOWN_PROJECT
    queued = generate_for_project(project=project)
    print(f"{project.slug}: {queued} new proposal(s)")
    return EXIT_OK


def _handle_list(args: argparse.Namespace) -> int:
    for proposal in ProposalStore().pending(project_slug=args.project):
        print(
            FIELD_SEPARATOR.join(
                (proposal.proposal_id, proposal.project_slug, proposal.headline)
            )
        )
    return EXIT_OK


def _handle_show(args: argparse.Namespace) -> int:
    proposal = ProposalStore().get(proposal_id=args.id)
    if proposal is None:
        print(f"no proposal {args.id!r}", file=sys.stderr)
        return EXIT_UNKNOWN_PROPOSAL
    print(f"{proposal.headline}\n{proposal.rationale}\n\n--- would append to {proposal.doc_path}")
    print(proposal.body)
    return EXIT_OK


def _handle_decide(args: argparse.Namespace) -> int:
    succeeded, message = decide_proposal(proposal_id=args.id, accept=args.accept)
    print(message, file=sys.stdout if succeeded else sys.stderr)
    return EXIT_OK if succeeded else EXIT_APPLY_FAILED


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    """Attach `spine propose` to the CLI."""
    parser = subparsers.add_parser("propose", help="Draft and decide document edits.")
    verbs = parser.add_subparsers(dest="propose_command", metavar="VERB")

    generator = verbs.add_parser("generate", help="Draft edits from observed facts.")
    generator.add_argument("--project", required=True)
    generator.set_defaults(handler=_handle_generate)

    lister = verbs.add_parser("list", help="Proposals waiting on a decision.")
    lister.add_argument("--project", default=None)
    lister.set_defaults(handler=_handle_list)

    shower = verbs.add_parser("show", help="What one proposal would change.")
    shower.add_argument("--id", required=True)
    shower.set_defaults(handler=_handle_show)

    accepter = verbs.add_parser("accept", help="Apply a proposal to its document.")
    accepter.add_argument("--id", required=True)
    accepter.set_defaults(handler=_handle_decide, accept=True)

    rejecter = verbs.add_parser("reject", help="Decline a proposal.")
    rejecter.add_argument("--id", required=True)
    rejecter.set_defaults(handler=_handle_decide, accept=False)
