"""Standalone-question rewrite (SPEC §5.3, §5.5).

The model call is mocked; these tests pin the skip-on-first-turn fast path and
the fall-back-to-original behaviour without a gateway.
"""

import asyncio

import pytest

from citebear_api import condense
from citebear_api.condense import condense_question


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _RecordingModel:
    def __init__(self, text: str) -> None:
        self._text = text
        self.calls = 0

    async def ainvoke(self, _messages: object) -> _FakeResponse:
        self.calls += 1
        return _FakeResponse(self._text)


def test_first_turn_skips_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _RecordingModel("unused")
    monkeypatch.setattr(condense, "get_chat_model", lambda: model)

    result = asyncio.run(condense_question("What is RRF?", []))

    assert result == "What is RRF?"
    assert model.calls == 0  # no history -> no gateway call (SPEC §5.5 fast path)


def test_follow_up_is_rewritten(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _RecordingModel("  Is Neon free?  ")
    monkeypatch.setattr(condense, "get_chat_model", lambda: model)

    result = asyncio.run(
        condense_question("is it free?", [("user", "What database?"), ("assistant", "Neon.")])
    )

    assert result == "Is Neon free?"  # stripped
    assert model.calls == 1


def test_empty_rewrite_falls_back_to_original(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(condense, "get_chat_model", lambda: _RecordingModel("   "))

    result = asyncio.run(condense_question("is it free?", [("user", "hi")]))

    assert result == "is it free?"


def test_gateway_failure_falls_back_to_original(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FailingModel:
        async def ainvoke(self, _messages: object) -> object:
            raise RuntimeError("429 rate limited")

    monkeypatch.setattr(condense, "get_chat_model", lambda: _FailingModel())

    # a condense-call failure must not sink the turn — retrieval proceeds on the raw message
    result = asyncio.run(condense_question("is it free?", [("user", "What database?")]))

    assert result == "is it free?"
