"""Model-backed reviser. The SDK stays an optional extra."""

from __future__ import annotations

import json

from ..classify.client import (
    ADAPTIVE_THINKING,
    JSON_SCHEMA_FORMAT,
    TEXT_BLOCK_TYPE,
    USER_ROLE,
    ModelUnavailableError,
    first_text_block,
    load_anthropic_client,
)
from ..constants import CRITIQUE_EFFORT, CRITIQUE_MAX_TOKENS, CRITIQUE_MODEL_ID
from ..style.rules import StyleNote
from .prompt import CRITIQUE_SYSTEM, REVISE_SYSTEM, critique_prompt, revise_prompt

NOTES_FIELD = "notes"
CODE_FIELD = "code"
DETAIL_FIELD = "detail"
EXCERPT_FIELD = "excerpt"
MODEL_NOTE_CODE_PREFIX = "review:"


def critique_schema() -> dict[str, object]:
    """Structured output shape for one critique pass."""
    return {
        "type": "object",
        "properties": {
            NOTES_FIELD: {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        CODE_FIELD: {"type": "string"},
                        DETAIL_FIELD: {"type": "string"},
                        EXCERPT_FIELD: {"type": "string"},
                    },
                    "required": [CODE_FIELD, DETAIL_FIELD, EXCERPT_FIELD],
                    "additionalProperties": False,
                },
            }
        },
        "required": [NOTES_FIELD],
        "additionalProperties": False,
    }


def parse_notes(*, payload: str) -> tuple[StyleNote, ...]:
    """Notes from the model's JSON, dropping entries that do not parse."""
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as cause:
        raise ModelUnavailableError(f"critique returned invalid json: {cause}") from cause
    entries = decoded.get(NOTES_FIELD, []) if isinstance(decoded, dict) else []
    return tuple(
        StyleNote(
            code=f"{MODEL_NOTE_CODE_PREFIX}{entry[CODE_FIELD]}",
            detail=str(entry[DETAIL_FIELD]),
            excerpt=str(entry.get(EXCERPT_FIELD, "")),
        )
        for entry in entries
        if isinstance(entry, dict) and CODE_FIELD in entry and DETAIL_FIELD in entry
    )


class AnthropicReviser:
    """Critiques and rewrites a document with one model call per half-round."""

    def __init__(self, *, client: object | None = None) -> None:
        self._client = client

    def _ensure_client(self) -> object:
        if self._client is None:
            self._client = load_anthropic_client()
        return self._client

    def _call(self, *, system: str, user: str, schema: dict[str, object] | None) -> str:
        output_config: dict[str, object] = {"effort": CRITIQUE_EFFORT}
        if schema is not None:
            output_config["format"] = {"type": JSON_SCHEMA_FORMAT, "schema": schema}
        try:
            response = self._ensure_client().messages.create(
                model=CRITIQUE_MODEL_ID,
                max_tokens=CRITIQUE_MAX_TOKENS,
                thinking=ADAPTIVE_THINKING,
                output_config=output_config,
                system=[{"type": TEXT_BLOCK_TYPE, "text": system}],
                messages=[{"role": USER_ROLE, "content": user}],
            )
        except ModelUnavailableError:
            raise
        except Exception as cause:
            raise ModelUnavailableError(f"critique call failed: {cause}") from cause
        return first_text_block(response=response)

    def critique(self, *, text: str) -> tuple[StyleNote, ...]:
        """Defects the model finds beyond the mechanical style checks."""
        return parse_notes(
            payload=self._call(
                system=CRITIQUE_SYSTEM, user=critique_prompt(text=text), schema=critique_schema()
            )
        )

    def revise(self, *, text: str, notes: tuple[StyleNote, ...]) -> str:
        """The document rewritten against the notes."""
        return self._call(
            system=REVISE_SYSTEM, user=revise_prompt(text=text, notes=notes), schema=None
        ).strip()
