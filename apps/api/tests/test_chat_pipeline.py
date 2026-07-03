"""run_chat_turn orchestration, with the DB and gateway mocked.

The api CI job has no Postgres, so this stays a pure unit test: it proves the
event ordering (sources before tokens) and the citation post-check's
marker -> chunk mapping without touching a real database.
"""

import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest

from citebear_api import chat
from citebear_api.chat import ChatEvent, ChatTurn, run_chat_turn
from citebear_api.models import Message, MessageCitation
from citebear_api.retrieval import RetrievedChunk


def _chunk(n: int, score: float = 8.0) -> RetrievedChunk:
    # default score clears the confidence threshold so the pipeline generates;
    # refusal tests pass a low score explicitly
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_title=f"Doc {n}",
        source_url=f"https://example.com/{n}",
        content=f"Content {n}.",
        section_path=[str(n)],
        page_start=n,
        page_end=n,
        score=score,
    )


class _FakeResult:
    def all(self) -> list[object]:
        return []  # no history


class _FakeSession:
    """Minimal async session: records added rows, assigns ids on flush."""

    def __init__(self, added: list[object]) -> None:
        self._added = added

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False

    async def execute(self, *_: object, **__: object) -> _FakeResult:
        return _FakeResult()

    def add(self, obj: object) -> None:
        self._added.append(obj)

    async def flush(self) -> None:
        # the real server_default assigns ids in the DB; do it here so the
        # post-check can read assistant_message.id
        for obj in self._added:
            if isinstance(obj, Message) and getattr(obj, "id", None) is None:
                obj.id = uuid4()

    async def commit(self) -> None:
        return None


def _install_mocks(
    monkeypatch: pytest.MonkeyPatch, chunks: list[RetrievedChunk], answer: str
) -> list[object]:
    added: list[object] = []

    async def fake_embed(_question: str) -> list[float]:
        return [0.0]

    async def fake_retrieve(*_: object, **__: object) -> list[RetrievedChunk]:
        return chunks

    async def fake_stream(*_: object, **__: object) -> AsyncIterator[str]:
        for token in answer.split(" "):
            yield token + " "

    class _FakeReranker:
        async def rerank(self, _query: str, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
            return hits  # identity: keep the pipeline test independent of scoring

    monkeypatch.setattr(chat, "embed_query", fake_embed)
    monkeypatch.setattr(chat, "hybrid_retrieve", fake_retrieve)
    monkeypatch.setattr(chat, "get_reranker", lambda: _FakeReranker())
    monkeypatch.setattr(chat, "stream_answer", fake_stream)
    monkeypatch.setattr(chat, "get_session_factory", lambda: lambda: _FakeSession(added))
    return added


def _run(turn: ChatTurn) -> list[ChatEvent]:
    async def collect() -> list[ChatEvent]:
        return [event async for event in run_chat_turn(turn)]

    return asyncio.run(collect())


def _turn() -> ChatTurn:
    return ChatTurn(session_id=uuid4(), message="What is RRF?", ip_hash=None)


def test_sources_event_precedes_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = [_chunk(1), _chunk(2), _chunk(3)]
    _install_mocks(monkeypatch, chunks, "RRF fuses ranks [2] and [1].")

    events = _run(_turn())
    names = [e.event for e in events]

    assert names[0] == "sources"
    assert names[-1] == "done"
    assert "token" in names
    assert names.index("sources") < names.index("token")
    # the sources event carries every retrieved chunk as a candidate citation
    assert len(events[0].data["citations"]) == 3
    assert events[0].data["confidence"] == "high"  # default chunk score 8.0


def test_post_check_persists_only_used_valid_citations(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = [_chunk(1), _chunk(2), _chunk(3)]
    # answer cites [2] and [1] (valid, out of order) and [9] (hallucinated)
    added = _install_mocks(monkeypatch, chunks, "See [2], then [1], and also [9].")

    _run(_turn())

    citations = [row for row in added if isinstance(row, MessageCitation)]
    assert {(c.marker, c.chunk_id) for c in citations} == {
        (2, chunks[1].chunk_id),
        (1, chunks[0].chunk_id),
    }


def test_refusal_persists_no_citations(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = [_chunk(1), _chunk(2)]
    added = _install_mocks(monkeypatch, chunks, "I don't know based on the provided documents.")

    events = _run(_turn())

    assert not [row for row in added if isinstance(row, MessageCitation)]
    assert events[-1].event == "done"
    assert events[-1].data["grounded"] is False


def test_low_scores_refuse_without_calling_generator(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = [_chunk(1, score=2.0), _chunk(2, score=1.0)]
    added = _install_mocks(monkeypatch, chunks, "unused")

    called = {"stream": False}

    async def spy_stream(*_: object, **__: object) -> AsyncIterator[str]:
        called["stream"] = True
        yield "should not run"

    monkeypatch.setattr(chat, "stream_answer", spy_stream)

    events = _run(_turn())

    # the generator is never called when nothing clears the threshold
    assert called["stream"] is False
    # sources still lead, but with no citable chunks and low confidence
    assert events[0].event == "sources"
    assert events[0].data["citations"] == []
    assert events[0].data["confidence"] == "low"
    # the refusal text is streamed as a token so the UI renders it normally
    refusal = "".join(e.data["delta"] for e in events if e.event == "token")
    assert refusal.startswith("I don't know")
    assert events[-1].event == "done"
    assert events[-1].data["grounded"] is False
    assert not [row for row in added if isinstance(row, MessageCitation)]
    assistant = next(row for row in added if isinstance(row, Message) and row.role == "assistant")
    assert assistant.confidence == "low"
