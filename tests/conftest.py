"""Shared test setup.

The sweep now classifies unknown documents, so an unstubbed test would reach the
Anthropic API and spend real tokens. Every test starts with that door shut.
"""

from __future__ import annotations

import pytest

from spine.classify.client import ModelUnavailableError

OFFLINE_CLASSIFIER_MESSAGE = "the classifier is offline in tests"


@pytest.fixture(autouse=True)
def offline_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make an unstubbed classifier construction fail rather than call the API."""

    def refuse_to_reach_the_api(*args: object, **keywords: object) -> None:
        raise ModelUnavailableError(OFFLINE_CLASSIFIER_MESSAGE)

    monkeypatch.setattr("spine.classify.AnthropicClassifier", refuse_to_reach_the_api)
