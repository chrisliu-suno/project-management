"""Sqlite-backed document graph. Several projects share one database file."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from ..model import Doc, DocKind, Lifecycle, Link, LinkType, ReadWhen
from ..paths import graph_db_path

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS docs (
        project_slug TEXT NOT NULL,
        doc_id TEXT NOT NULL,
        path TEXT NOT NULL,
        kind TEXT NOT NULL,
        read_when TEXT NOT NULL,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        area TEXT,
        lifecycle TEXT,
        frontmatter TEXT NOT NULL,
        is_generated INTEGER NOT NULL,
        PRIMARY KEY (project_slug, doc_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS links (
        project_slug TEXT NOT NULL,
        src_id TEXT NOT NULL,
        dst_id TEXT NOT NULL,
        link_type TEXT NOT NULL,
        confidence REAL NOT NULL,
        evidence TEXT NOT NULL,
        PRIMARY KEY (project_slug, src_id, dst_id, link_type)
    )
    """,
    "CREATE INDEX IF NOT EXISTS links_by_src ON links (src_id)",
    "CREATE INDEX IF NOT EXISTS links_by_dst ON links (dst_id)",
)

DELETE_PROJECT_DOCS_SQL = "DELETE FROM docs WHERE project_slug = :project_slug"
DELETE_PROJECT_LINKS_SQL = "DELETE FROM links WHERE project_slug = :project_slug"

INSERT_DOC_SQL = """
INSERT INTO docs (
    project_slug, doc_id, path, kind, read_when, title, body, area, lifecycle,
    frontmatter, is_generated
) VALUES (
    :project_slug, :doc_id, :path, :kind, :read_when, :title, :body, :area, :lifecycle,
    :frontmatter, :is_generated
)
"""

INSERT_LINK_SQL = """
INSERT INTO links (project_slug, src_id, dst_id, link_type, confidence, evidence)
VALUES (:project_slug, :src_id, :dst_id, :link_type, :confidence, :evidence)
"""

SELECT_PROJECT_DOCS_SQL = """
SELECT project_slug, doc_id, path, kind, read_when, title, body, area, lifecycle,
       frontmatter, is_generated
FROM docs
WHERE project_slug = :project_slug
ORDER BY doc_id
"""

SELECT_ORPHAN_DOCS_SQL = """
SELECT project_slug, doc_id, path, kind, read_when, title, body, area, lifecycle,
       frontmatter, is_generated
FROM docs
WHERE project_slug = :project_slug
  AND doc_id NOT IN (
      SELECT dst_id FROM links
      WHERE project_slug = :project_slug AND link_type != :cited_by
  )
ORDER BY doc_id
"""

SELECT_OUTBOUND_SQL = """
SELECT src_id, dst_id, link_type, confidence, evidence
FROM links
WHERE src_id = :doc_id AND (:link_type IS NULL OR link_type = :link_type)
ORDER BY dst_id, link_type
"""

SELECT_INBOUND_SQL = """
SELECT src_id, dst_id, link_type, confidence, evidence
FROM links
WHERE dst_id = :doc_id AND (:link_type IS NULL OR link_type = :link_type)
ORDER BY src_id, link_type
"""

TRUE_AS_INTEGER = 1
FALSE_AS_INTEGER = 0


def _doc_row(*, doc: Doc, project_slug: str) -> dict[str, object]:
    return {
        "project_slug": project_slug,
        "doc_id": doc.doc_id,
        "path": str(doc.path),
        "kind": str(doc.kind),
        "read_when": str(doc.read_when),
        "title": doc.title,
        "body": doc.body,
        "area": doc.area,
        "lifecycle": str(doc.lifecycle) if doc.lifecycle is not None else None,
        "frontmatter": json.dumps(doc.frontmatter, default=str),
        "is_generated": TRUE_AS_INTEGER if doc.is_generated else FALSE_AS_INTEGER,
    }


def _link_row(*, link: Link, project_slug: str) -> dict[str, object]:
    return {
        "project_slug": project_slug,
        "src_id": link.src_id,
        "dst_id": link.dst_id,
        "link_type": str(link.link_type),
        "confidence": link.confidence,
        "evidence": link.evidence,
    }


def _doc_from_row(*, row: sqlite3.Row) -> Doc:
    lifecycle = row["lifecycle"]
    return Doc(
        doc_id=row["doc_id"],
        path=Path(row["path"]),
        kind=DocKind(row["kind"]),
        read_when=ReadWhen(row["read_when"]),
        title=row["title"],
        body=row["body"],
        project_slug=row["project_slug"],
        area=row["area"],
        lifecycle=Lifecycle(lifecycle) if lifecycle else None,
        frontmatter=json.loads(row["frontmatter"]),
        is_generated=bool(row["is_generated"]),
    )


def _link_from_row(*, row: sqlite3.Row) -> Link:
    return Link(
        src_id=row["src_id"],
        dst_id=row["dst_id"],
        link_type=LinkType(row["link_type"]),
        confidence=row["confidence"],
        evidence=row["evidence"],
    )


class SqliteGraphStore:
    """Persists docs and links in one sqlite file, keyed by project."""

    def __init__(self, *, db_path: Path | None = None) -> None:
        self._db_path = db_path

    @property
    def db_path(self) -> Path:
        """Database location, resolved late so the state root stays overridable."""
        return self._db_path if self._db_path is not None else graph_db_path()

    def _connect(self) -> sqlite3.Connection:
        path = self.db_path
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
        return connection

    def replace_project(
        self, *, project_slug: str, docs: tuple[Doc, ...], links: tuple[Link, ...]
    ) -> None:
        """Swap a project's whole graph in one transaction, so a failed reindex changes nothing."""
        doc_rows = [_doc_row(doc=doc, project_slug=project_slug) for doc in docs]
        link_rows = [_link_row(link=link, project_slug=project_slug) for link in links]
        with closing(self._connect()) as connection, connection:
            connection.execute(DELETE_PROJECT_LINKS_SQL, {"project_slug": project_slug})
            connection.execute(DELETE_PROJECT_DOCS_SQL, {"project_slug": project_slug})
            connection.executemany(INSERT_DOC_SQL, doc_rows)
            connection.executemany(INSERT_LINK_SQL, link_rows)

    def docs_for_project(self, *, project_slug: str) -> tuple[Doc, ...]:
        """Every doc stored for one project."""
        return self._query_docs(
            sql=SELECT_PROJECT_DOCS_SQL, parameters={"project_slug": project_slug}
        )

    def orphans(self, *, project_slug: str) -> tuple[Doc, ...]:
        """Docs nothing points at, findable only by walking the directory."""
        return self._query_docs(
            sql=SELECT_ORPHAN_DOCS_SQL,
            parameters={"project_slug": project_slug, "cited_by": str(LinkType.CITED_BY)},
        )

    def outbound(self, *, doc_id: str, link_type: LinkType | None = None) -> tuple[Link, ...]:
        """Links leaving a doc, optionally narrowed to one type."""
        return self._query_links(sql=SELECT_OUTBOUND_SQL, doc_id=doc_id, link_type=link_type)

    def inbound(self, *, doc_id: str, link_type: LinkType | None = None) -> tuple[Link, ...]:
        """Links arriving at a doc, optionally narrowed to one type."""
        return self._query_links(sql=SELECT_INBOUND_SQL, doc_id=doc_id, link_type=link_type)

    def _query_docs(self, *, sql: str, parameters: dict[str, object]) -> tuple[Doc, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return tuple(_doc_from_row(row=row) for row in rows)

    def _query_links(
        self, *, sql: str, doc_id: str, link_type: LinkType | None
    ) -> tuple[Link, ...]:
        parameters = {
            "doc_id": doc_id,
            "link_type": str(link_type) if link_type is not None else None,
        }
        with closing(self._connect()) as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return tuple(_link_from_row(row=row) for row in rows)
