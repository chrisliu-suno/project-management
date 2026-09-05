"""Tunable limits and well-known names.

Nothing outside this module hardcodes a size, threshold, filename, or env var.
"""

from __future__ import annotations

from .model import DocKind, LinkType, ReadWhen

FRONTMATTER_DELIMITER = "---"
DOC_FILE_SUFFIX = ".md"

SPINE_HOME_ENV_VAR = "SPINE_HOME"
SPINE_SESSION_ID_ENV_VAR = "SPINE_SESSION_ID"
SPINE_PROJECT_ENV_VAR = "SPINE_PROJECT"
SPINE_DISABLED_ENV_VAR = "SPINE_DISABLED"

DEFAULT_SPINE_DIR_NAME = "spine"
REGISTRY_FILE_NAME = "registry.toml"
GRAPH_DB_FILE_NAME = "graph.sqlite3"
SESSIONS_DIR_NAME = "sessions"
PICKS_DB_FILE_NAME = "picks.sqlite3"

PROJECT_SLUG_SEPARATOR = "-"
DOC_ID_SEPARATOR = ":"

MAX_LINES_PER_READ_WHEN: dict[ReadWhen, int] = {
    ReadWhen.EVERY_TIME: 400,
    ReadWhen.IN_AREA: 1200,
    ReadWhen.RARELY: 4000,
    ReadWhen.LOOKED_UP: 4000,
    ReadWhen.LOG: 4000,
}

INJECTION_LINE_BUDGET = 900
EVERY_TIME_RESERVED_LINES = 400

MIN_CONFIDENCE_FOR_SILENT_PICK = 0.6
MIN_CONFIDENCE_FOR_AUTO_ATTACH = 0.5
EXACT_MATCH_CONFIDENCE = 1.0
NO_MATCH_CONFIDENCE = 0.0

MODEL_INFERRED_LINK_CONFIDENCE = 0.7
TEXTUAL_LINK_CONFIDENCE = 1.0

REGISTRY_PROJECTS_TABLE = "projects"
REGISTRY_KEY_NAME = "name"
REGISTRY_KEY_DOCS_DIR = "docs_dir"
REGISTRY_KEY_REPOS = "repos"
REGISTRY_KEY_PATH_GLOBS = "path_globs"
REGISTRY_KEY_BRANCH_PREFIXES = "branch_prefixes"
REGISTRY_KEY_LINEAR_PROJECT = "linear_project"
REGISTRY_BARE_KEY_EXTRA_CHARS = "-_"

REPO_MATCH_CONFIDENCE = 0.6
BRANCH_PREFIX_MATCH_CONFIDENCE = 0.5
PATH_GLOB_MATCH_CONFIDENCE = 0.4
PROMPT_MENTION_CONFIDENCE = 0.3
DOC_TEXT_ENCODING = "utf-8"

FRONTMATTER_KEY_SEPARATOR = ":"
FRONTMATTER_COMMENT_PREFIX = "#"
FRONTMATTER_NULL_LITERAL = "null"
FRONTMATTER_TRUE_LITERAL = "true"
FRONTMATTER_FALSE_LITERAL = "false"
FRONTMATTER_LIST_OPEN = "["
FRONTMATTER_LIST_CLOSE = "]"
FRONTMATTER_LIST_ITEM_SEPARATOR = ","
FRONTMATTER_QUOTE_CHARACTERS = ('"', "'")

DOC_KIND_KEY = "kind"
DOC_READ_WHEN_KEY = "read_when"
DOC_TITLE_KEY = "title"
DOC_AREA_KEY = "area"
DOC_LIFECYCLE_KEY = "lifecycle"
DOC_GENERATED_KEYS = ("generated", "is_generated")

MARKDOWN_H1_PREFIX = "# "
FILENAME_WORD_SEPARATOR = "-"
DOC_KIND_WORD_SEPARATOR = "_"

DOC_KIND_BY_FILENAME_PREFIX: dict[str, DocKind] = {
    "brief": DocKind.BRIEF,
    "rules": DocKind.PROJECT_RULES,
    "classification": DocKind.CLASSIFICATION,
    "milestone": DocKind.MILESTONE,
    "design": DocKind.AREA_DESIGN,
    "rollout": DocKind.ROLLOUT,
    "test-coverage": DocKind.TEST_COVERAGE,
    "decisions": DocKind.DECISION_LOG,
    "decision-log": DocKind.DECISION_LOG,
    "open-questions": DocKind.OPEN_QUESTIONS,
}
FALLBACK_DOC_KIND = DocKind.GENERATED

DOCS_COMMAND_NAME = "docs"
DOCS_LIST_ACTION = "list"
DOCS_CHECK_ACTION = "check"
DOCS_ACTION_DEST = "docs_action"
DOCS_DIR_OPTION = "--dir"
DOCS_DIR_DEST = "docs_dir"

DOCS_MISSING_DIR_MESSAGE = "no corpus directory at {docs_dir}"
DOCS_LIST_ROW_FORMAT = "{doc_id}\t{kind}\t{read_when}\t{line_count}\t{title}"
DOCS_BREACH_ROW_FORMAT = "{doc_id}\t{read_when}\t{line_count}/{cap_lines} lines\t+{excess_lines}"

EXIT_CAP_BREACH = 1
CITATION_LINK_TYPES: frozenset[LinkType] = frozenset(
    {
        LinkType.BLOCKS,
        LinkType.CLASSIFIES,
        LinkType.CONSTRAINS,
        LinkType.DEPENDS_ON,
        LinkType.DERIVED_FROM,
        LinkType.IMPLEMENTS,
        LinkType.MENTIONS,
        LinkType.RAMPS,
        LinkType.VERIFIES,
    }
)
