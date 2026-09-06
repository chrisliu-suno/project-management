"""Persists classifications so re-indexing an unchanged corpus costs nothing."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from ..constants import (
    CLASSIFIER_CACHE_FILE_NAME,
    CLASSIFIER_MODEL_ID,
    CLASSIFIER_PROMPT_VERSION,
)
from ..model import DocKind, ReadWhen
from ..paths import ensure_spine_home, spine_home
from .client import Classification

CONTENT_ENCODING = "utf-8"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS classifications (
    content_sha256 TEXT NOT NULL,
    model_id TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    read_when TEXT NOT NULL,
    area TEXT,
    confidence REAL NOT NULL,
    PRIMARY KEY (content_sha256, model_id, prompt_version)
)
"""

SELECT_SQL = """
SELECT doc_id, kind, read_when, area, confidence
FROM classifications
WHERE content_sha256 = :content_sha256
  AND model_id = :model_id
  AND prompt_version = :prompt_version
"""

UPSERT_SQL = """
INSERT OR REPLACE INTO classifications
    (content_sha256, model_id, prompt_version, doc_id, kind, read_when, area, confidence)
VALUES
    (:content_sha256, :model_id, :prompt_version, :doc_id, :kind, :read_when, :area, :confidence)
"""

COUNT_SQL = "SELECT COUNT(*) FROM classifications"


def content_fingerprint(*, body: str) -> str:
    """Cache key for a document's text, so an edit invalidates only that document."""
    return hashlib.sha256(body.encode(CONTENT_ENCODING)).hexdigest()


def cache_db_path() -> Path:
    return spine_home() / CLASSIFIER_CACHE_FILE_NAME


class ClassificationCache:
    """SQLite cache keyed by content, model, and prompt version."""

    def __init__(self, *, db_path: Path | None = None) -> None:
        ensure_spine_home()
        self._db_path = db_path if db_path is not None else cache_db_path()
        with self._connect() as connection:
            connection.execute(CREATE_TABLE_SQL)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def get(self, *, body: str) -> Classification | None:
        parameters = {
            "content_sha256": content_fingerprint(body=body),
            "model_id": CLASSIFIER_MODEL_ID,
            "prompt_version": CLASSIFIER_PROMPT_VERSION,
        }
        with self._connect() as connection:
            row = connection.execute(SELECT_SQL, parameters).fetchone()
        if row is None:
            return None
        return Classification(
            doc_id=row["doc_id"],
            kind=DocKind(row["kind"]),
            read_when=ReadWhen(row["read_when"]),
            area=row["area"],
            confidence=row["confidence"],
        )

    def put(self, *, body: str, classification: Classification) -> None:
        parameters = {
            "content_sha256": content_fingerprint(body=body),
            "model_id": CLASSIFIER_MODEL_ID,
            "prompt_version": CLASSIFIER_PROMPT_VERSION,
            "doc_id": classification.doc_id,
            "kind": str(classification.kind),
            "read_when": str(classification.read_when),
            "area": classification.area,
            "confidence": classification.confidence,
        }
        with self._connect() as connection:
            connection.execute(UPSERT_SQL, parameters)

    def size(self) -> int:
        with self._connect() as connection:
            return int(connection.execute(COUNT_SQL).fetchone()[0])
