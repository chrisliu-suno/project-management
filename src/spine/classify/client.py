"""Anthropic-backed classifier.

The SDK is an optional extra (`pip install spine[classify]`); importing this
module without it raises only when a classification is actually attempted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..constants import (
    ANTHROPIC_PACKAGE_NAME,
    CLASSIFIER_EFFORT,
    CLASSIFIER_MAX_TOKENS,
    CLASSIFIER_MODEL_ID,
)
from ..model import Doc, DocKind, ReadWhen
from .prompt import batch_prompt, system_prompt
from .schema import (
    AREA_FIELD,
    CONFIDENCE_FIELD,
    DOC_ID_FIELD,
    KIND_FIELD,
    READ_WHEN_FIELD,
    RESULTS_FIELD,
    classification_schema,
)

TEXT_BLOCK_TYPE = "text"
REFUSAL_STOP_REASON = "refusal"
JSON_SCHEMA_FORMAT = "json_schema"
USER_ROLE = "user"
EPHEMERAL_CACHE = {"type": "ephemeral"}
ADAPTIVE_THINKING = {"type": "adaptive"}


class ClassifierUnavailableError(RuntimeError):
    """The Anthropic SDK is not installed, or the request could not be made."""


class ClassifierRefusedError(RuntimeError):
    """The model declined the request."""


@dataclass(frozen=True, slots=True)
class Classification:
    """One verdict about a document."""

    doc_id: str
    kind: DocKind
    read_when: ReadWhen
    area: str | None
    confidence: float


def _load_anthropic_client() -> object:
    try:
        import anthropic
    except ImportError as cause:
        raise ClassifierUnavailableError(
            f"{ANTHROPIC_PACKAGE_NAME} is not installed; install spine[classify]"
        ) from cause
    return anthropic.Anthropic()


def _parse_verdict(*, entry: dict[str, object]) -> Classification | None:
    try:
        area = str(entry[AREA_FIELD]).strip()
        return Classification(
            doc_id=str(entry[DOC_ID_FIELD]),
            kind=DocKind(str(entry[KIND_FIELD])),
            read_when=ReadWhen(str(entry[READ_WHEN_FIELD])),
            area=area or None,
            confidence=float(entry[CONFIDENCE_FIELD]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def parse_response_text(*, payload: str) -> tuple[Classification, ...]:
    """Verdicts from the model's JSON, dropping any entry that does not parse."""
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as cause:
        raise ClassifierUnavailableError(f"classifier returned invalid json: {cause}") from cause
    entries = decoded.get(RESULTS_FIELD, []) if isinstance(decoded, dict) else []
    parsed = (_parse_verdict(entry=entry) for entry in entries if isinstance(entry, dict))
    return tuple(verdict for verdict in parsed if verdict is not None)


class AnthropicClassifier:
    """Classifies batches of documents with one model call per batch."""

    def __init__(self, *, client: object | None = None) -> None:
        self._client = client

    def _ensure_client(self) -> object:
        if self._client is None:
            self._client = _load_anthropic_client()
        return self._client

    def classify_batch(self, *, docs: tuple[Doc, ...]) -> tuple[Classification, ...]:
        """Verdicts for one batch. Raises rather than guessing when the call fails."""
        if not docs:
            return ()
        response = self._ensure_client().messages.create(
            model=CLASSIFIER_MODEL_ID,
            max_tokens=CLASSIFIER_MAX_TOKENS,
            thinking=ADAPTIVE_THINKING,
            output_config={
                "effort": CLASSIFIER_EFFORT,
                "format": {"type": JSON_SCHEMA_FORMAT, "schema": classification_schema()},
            },
            system=[
                {
                    "type": TEXT_BLOCK_TYPE,
                    "text": system_prompt(),
                    "cache_control": EPHEMERAL_CACHE,
                }
            ],
            messages=[{"role": USER_ROLE, "content": batch_prompt(docs=docs)}],
        )
        if getattr(response, "stop_reason", None) == REFUSAL_STOP_REASON:
            raise ClassifierRefusedError("classifier declined to classify this batch")
        return parse_response_text(payload=_first_text_block(response=response))


def _first_text_block(*, response: object) -> str:
    for block in getattr(response, "content", ()):
        if getattr(block, "type", None) == TEXT_BLOCK_TYPE:
            return str(getattr(block, "text", ""))
    raise ClassifierUnavailableError("classifier response carried no text block")
