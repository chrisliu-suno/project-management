"""Where spine keeps its state on disk."""

from __future__ import annotations

import os
from pathlib import Path

from .constants import (
    DEFAULT_SPINE_DIR_NAME,
    GRAPH_DB_FILE_NAME,
    PICKS_DB_FILE_NAME,
    REGISTRY_FILE_NAME,
    SESSIONS_DIR_NAME,
    SPINE_HOME_ENV_VAR,
)

XDG_STATE_HOME_ENV_VAR = "XDG_STATE_HOME"
DEFAULT_STATE_DIR = Path(".local/state")


def spine_home() -> Path:
    """Root of spine's own state, overridable for tests and alternate setups."""
    override = os.environ.get(SPINE_HOME_ENV_VAR)
    if override:
        return Path(override).expanduser()
    state_root = os.environ.get(XDG_STATE_HOME_ENV_VAR)
    base = Path(state_root).expanduser() if state_root else Path.home() / DEFAULT_STATE_DIR
    return base / DEFAULT_SPINE_DIR_NAME


def registry_path() -> Path:
    return spine_home() / REGISTRY_FILE_NAME


def graph_db_path() -> Path:
    return spine_home() / GRAPH_DB_FILE_NAME


def picks_db_path() -> Path:
    return spine_home() / PICKS_DB_FILE_NAME


def sessions_dir() -> Path:
    return spine_home() / SESSIONS_DIR_NAME


def ensure_spine_home() -> Path:
    """Create the state directory tree if it is missing."""
    home = spine_home()
    home.mkdir(parents=True, exist_ok=True)
    sessions_dir().mkdir(parents=True, exist_ok=True)
    return home
