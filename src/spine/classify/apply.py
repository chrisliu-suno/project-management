"""Applies already-cached classifications to a corpus.

Pure cache read: never imports the SDK and never makes a network call, so the
indexer can use classifications without taking the optional dependency.
"""

from __future__ import annotations

from dataclasses import replace

from ..model import Doc
from .cache import ClassificationCache


def apply_cached_classifications(
    *, docs: tuple[Doc, ...], cache: ClassificationCache | None = None
) -> tuple[Doc, ...]:
    """The corpus with cached kinds filled in where the document declared none."""
    from . import needs_classification

    active_cache = cache if cache is not None else ClassificationCache()
    applied: list[Doc] = []
    for doc in docs:
        verdict = active_cache.get(body=doc.body) if needs_classification(doc=doc) else None
        if verdict is None:
            applied.append(doc)
            continue
        applied.append(
            replace(
                doc,
                kind=verdict.kind,
                read_when=verdict.read_when,
                area=verdict.area if verdict.area else doc.area,
            )
        )
    return tuple(applied)
