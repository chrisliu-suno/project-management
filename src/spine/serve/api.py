"""Request handling for the dashboard, independent of the socket layer."""

from __future__ import annotations

from ..dashboard import PickPreview
from ..model import Doc, Selection

ERROR_FIELD = "error"
PROJECTS_FIELD = "projects"
SESSIONS_FIELD = "sessions"
OK_FIELD = "ok"
HEALTH_UNAVAILABLE = "health analysis is unavailable"
EMPTY_TASK_MESSAGE = "describe a task to see what spine would load"


def _doc_entry(*, doc: Doc) -> dict[str, object]:
    return {
        "doc_id": doc.doc_id,
        "title": doc.title,
        "kind": str(doc.kind),
        "read_when": str(doc.read_when),
        "line_count": doc.line_count,
    }


def projects_payload() -> dict[str, object]:
    """Every registered project's snapshot, or an error the page can render."""
    try:
        from ..health import build_all_snapshots
        from ..registry import load_registry
    except ImportError:
        return {PROJECTS_FIELD: [], ERROR_FIELD: HEALTH_UNAVAILABLE}
    try:
        snapshots = build_all_snapshots(registry=load_registry())
    except Exception as cause:
        return {PROJECTS_FIELD: [], ERROR_FIELD: f"{HEALTH_UNAVAILABLE}: {cause}"}
    return {PROJECTS_FIELD: [snapshot.as_dict() for snapshot in snapshots]}


def _preview_from(*, project_slug: str, task: str, selection: Selection) -> dict[str, object]:
    return PickPreview(
        project_slug=project_slug,
        task=task,
        chosen=tuple(_doc_entry(doc=doc) for doc in selection.chosen),
        dropped=tuple(_doc_entry(doc=doc) for doc in selection.dropped),
        total_lines=selection.total_lines,
        reason=selection.reason,
    ).as_dict()


def pick_payload(*, project_slug: str, task: str, budget: int) -> dict[str, object]:
    """What the picker would inject for a task, or an error the page can render."""
    if not task.strip():
        return {ERROR_FIELD: EMPTY_TASK_MESSAGE}
    try:
        from ..index import open_graph_store
        from ..picker import BudgetedPicker
        from ..registry import load_registry
    except ImportError as cause:
        return {ERROR_FIELD: f"picker is unavailable: {cause}"}
    project = load_registry().get(project_slug)
    if project is None:
        return {ERROR_FIELD: f"no project registered under {project_slug!r}"}
    try:
        picker = BudgetedPicker(graph_store=open_graph_store())
        selection = picker.pick(project=project, task_context=task, line_budget=budget)
    except Exception as cause:
        return {ERROR_FIELD: f"selection failed: {cause}"}
    return _preview_from(project_slug=project_slug, task=task, selection=selection)


def sessions_payload() -> dict[str, object]:
    """Every session that has reported recently, plus its declared intent."""
    try:
        from ..live import LiveStore
    except ImportError:
        return {SESSIONS_FIELD: []}
    try:
        found = LiveStore().live_sessions()
    except Exception as cause:
        return {SESSIONS_FIELD: [], ERROR_FIELD: str(cause)}
    return {SESSIONS_FIELD: [session.as_dict() for session in found]}


def steer_payload(*, session_id: str, action: str, body: str) -> dict[str, object]:
    """Queue a steering instruction for a session."""
    try:
        from ..live import LiveStore, SteeringAction
    except ImportError as cause:
        return {ERROR_FIELD: f"steering is unavailable: {cause}"}
    if not session_id.strip():
        return {ERROR_FIELD: "name a session to steer"}
    try:
        chosen = SteeringAction(action)
    except ValueError:
        return {ERROR_FIELD: f"unknown action {action!r}"}
    message = LiveStore().steer(session_id=session_id, action=chosen, body=body)
    return {OK_FIELD: True, "message": message.as_dict()}
