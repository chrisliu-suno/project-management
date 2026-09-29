"""Applies already-cached classifications to a corpus.

Pure cache read: never imports the SDK and never makes a network call, so the
indexer can use classifications without taking the optional dependency.
"""

from __future__ import annotations

from dataclasses import replace

from ..model import Doc, KindSource
from .cache import ClassificationCache


def apply_cached_classifications(
    *, docs: tuple[Doc, ...], cache: ClassificationCache | None = None
) -> tuple[Doc, ...]:
    """The corpus with cached kinds filled in where the document declared none."""
    from . import needs_classification

    from .reconcile import reconcile

    from . import check_is_confident

    active_cache = cache if cache is not None else ClassificationCache()
    cached = {
        doc.doc_id: verdict
        for doc in docs
        if needs_classification(doc=doc)
        and (verdict := active_cache.get(body=doc.body)) is not None
    }
    reconciled = reconcile(verdicts=cached)
    return tuple(
        replace(
            doc,
            kind=reconciled[doc.doc_id].kind,
            read_when=reconciled[doc.doc_id].read_when,
            area=reconciled[doc.doc_id].area or doc.area,
            kind_source=KindSource.MODEL
            if check_is_confident(verdict=reconciled[doc.doc_id])
            else doc.kind_source,
        )
        if doc.doc_id in reconciled
        else doc
        for doc in docs
    )
