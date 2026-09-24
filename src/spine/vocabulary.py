"""The frontmatter keys whose values are drawn from an enum, and how to spot one that is not.

The loader falls back silently on an unknown value, so a document that declares `kind: design`
looks classified and is not. Both the health report and the classifier ask this module.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from .constants import DOC_KIND_KEY, DOC_READ_WHEN_KEY
from .model import DocKind, ReadWhen

ENUM_FRONTMATTER_KEYS: tuple[tuple[str, type[StrEnum]], ...] = (
    (DOC_KIND_KEY, DocKind),
    (DOC_READ_WHEN_KEY, ReadWhen),
)


def get_unrecognised_frontmatter_keys(*, frontmatter: Mapping[str, object]) -> tuple[str, ...]:
    """The keys in this frontmatter whose declared value is outside the vocabulary they name."""
    return tuple(
        key
        for key, vocabulary in ENUM_FRONTMATTER_KEYS
        if isinstance(declared := frontmatter.get(key), str)
        and declared.strip().lower() not in frozenset(str(member) for member in vocabulary)
    )
