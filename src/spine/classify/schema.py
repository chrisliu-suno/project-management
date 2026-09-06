"""The JSON schema the classifier is constrained to, and the prompt it rides on.

Kept beside the prompt because changing either invalidates cached classifications,
which key on CLASSIFIER_PROMPT_VERSION.
"""

from __future__ import annotations

from ..model import DocKind, ReadWhen

DOC_ID_FIELD = "doc_id"
KIND_FIELD = "kind"
READ_WHEN_FIELD = "read_when"
AREA_FIELD = "area"
CONFIDENCE_FIELD = "confidence"
RESULTS_FIELD = "results"

KIND_DESCRIPTIONS: dict[DocKind, str] = {
    DocKind.BRIEF: "the hub: what this project is, why, where it stands",
    DocKind.PROJECT_RULES: "standing rules binding every task in the project",
    DocKind.CLASSIFICATION: "lookup tables that stop a judgement being re-argued",
    DocKind.MILESTONE: "what one slice must do, plus scenarios proving it",
    DocKind.AREA_DESIGN: "how one piece works, and the alternatives that lost",
    DocKind.ROLLOUT: "gate order, wait times, thresholds, blockers, backout",
    DocKind.TEST_COVERAGE: "what is checked, what is not",
    DocKind.DECISION_LOG: "append-only record of decisions and what they replaced",
    DocKind.OPEN_QUESTIONS: "unresolved questions with owners",
    DocKind.GENERATED: "none of the above, or derived from other facts",
}

READ_WHEN_DESCRIPTIONS: dict[ReadWhen, str] = {
    ReadWhen.EVERY_TIME: "needed on every task in the project, no exceptions",
    ReadWhen.IN_AREA: "needed when working on this milestone or surface",
    ReadWhen.RARELY: "on demand only — deep design, audits, frozen history",
    ReadWhen.LOOKED_UP: "queried for a fact, never read start to finish",
    ReadWhen.LOG: "appended to and queried, never bulk-read",
}


def classification_schema() -> dict[str, object]:
    """Schema constraining the model to one verdict per document."""
    return {
        "type": "object",
        "properties": {
            RESULTS_FIELD: {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        DOC_ID_FIELD: {"type": "string"},
                        KIND_FIELD: {"type": "string", "enum": [kind.value for kind in DocKind]},
                        READ_WHEN_FIELD: {
                            "type": "string",
                            "enum": [group.value for group in ReadWhen],
                        },
                        AREA_FIELD: {
                            "type": "string",
                            "description": "Short slug for the surface this covers, or empty.",
                        },
                        CONFIDENCE_FIELD: {"type": "number"},
                    },
                    "required": [
                        DOC_ID_FIELD,
                        KIND_FIELD,
                        READ_WHEN_FIELD,
                        AREA_FIELD,
                        CONFIDENCE_FIELD,
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": [RESULTS_FIELD],
        "additionalProperties": False,
    }
