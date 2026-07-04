"""run_chat_turn orchestration, with the DB and gateway mocked.

The api CI job has no Postgres, so this stays a pure unit test: it proves the
event ordering (sources before tokens) and the citation post-check's
marker -> chunk mapping without touching a real database.
"""

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

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


class _FakeSavepoint:
    """Models session.begin_nested(): on error, roll back to the savepoint
    (drop rows added inside it) and let the exception propagate."""

    def __init__(self, session: "_FakeSession") -> None:
        self._session = session

    async def __aenter__(self) -> "_FakeSavepoint":
        self._mark = len(self._session.added)
        return self

    async def __aexit__(self, exc_type: object, *_: object) -> bool:
        if exc_type is not None:
            del self._session.added[self._mark :]
        return False  # propagate so the caller's except clause runs


class _FakeSession:
    """Minimal async session: records added rows, assigns ids on flush."""

    def __init__(
        self,
        added: list[object],
        deleted: frozenset[UUID] = frozenset(),
        exploded: frozenset[UUID] = frozenset(),
    ) -> None:
        self.added = added
        self._deleted = deleted  # chunk ids that FK-fail on insert (deleted mid-turn)
        self._exploded = exploded  # chunk ids that raise a non-IntegrityError on insert

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False

    async def execute(self, *_: object, **__: object) -> _FakeResult:
        return _FakeResult()

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def begin_nested(self) -> _FakeSavepoint:
        return _FakeSavepoint(self)

    async def flush(self) -> None:
        # the real server_default assigns ids in the DB; do it here so the
        # post-check can read assistant_message.id
        for obj in self.added:
            if isinstance(obj, Message) and getattr(obj, "id", None) is None:
                obj.id = uuid4()
            if isinstance(obj, MessageCitation) and obj.chunk_id in self._deleted:
                raise IntegrityError("INSERT message_citations", {}, Exception("FK violation"))
            if isinstance(obj, MessageCitation) and obj.chunk_id in self._exploded:
                raise RuntimeError("connection reset mid-persist")

    async def commit(self) -> None:
        return None


def _install_mocks(
    monkeypatch: pytest.MonkeyPatch,
    chunks: list[RetrievedChunk],
    answer: str,
    deleted_chunk_ids: frozenset[UUID] = frozenset(),
    exploded_chunk_ids: frozenset[UUID] = frozenset(),
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
    monkeypatch.setattr(
        chat,
        "get_session_factory",
        lambda: lambda: _FakeSession(added, deleted_chunk_ids, exploded_chunk_ids),
    )
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


def test_deleted_chunk_citation_is_skipped_not_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    # a document re-ingested mid-answer deletes chunk [1] before the post-check
    chunks = [_chunk(1), _chunk(2), _chunk(3)]
    added = _install_mocks(
        monkeypatch,
        chunks,
        "See [1] and [2].",
        deleted_chunk_ids=frozenset({chunks[0].chunk_id}),
    )

    events = _run(_turn())

    # the answer still lands: the assistant message persists and done fires (#19)
    assert events[-1].event == "done"
    assert any(isinstance(row, Message) and row.role == "assistant" for row in added)
    # the vanished chunk's marker is dropped; the surviving citation persists
    citations = [row for row in added if isinstance(row, MessageCitation)]
    assert {(c.marker, c.chunk_id) for c in citations} == {(2, chunks[1].chunk_id)}


def test_citation_persist_failure_still_completes_the_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # a non-IntegrityError fault (e.g. connection reset) while persisting citations
    chunks = [_chunk(1), _chunk(2)]
    added = _install_mocks(
        monkeypatch,
        chunks,
        "See [1] and [2].",
        exploded_chunk_ids=frozenset({chunks[0].chunk_id}),
    )

    events = _run(_turn())

    # the streamed answer must not become an error: the turn still ends in done (#19)
    assert events[-1].event == "done"
    assert any(isinstance(row, Message) and row.role == "assistant" for row in added)


def test_refusal_persists_no_citations(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = [_chunk(1), _chunk(2)]
    added = _install_mocks(monkeypatch, chunks, "I don't know based on the provided documents.")

    events = _run(_turn())

    assert not [row for row in added if isinstance(row, MessageCitation)]
    assert events[-1].event == "done"
    assert events[-1].data["grounded"] is False


def test_cited_answer_is_grounded_despite_refusal_wording(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # the #59 derail shape: opens with the refusal template but ends with a real
    # citation. The old is_refusal prefix check flagged it grounded=false; the
    # structural rule keeps it grounded because it cites a source.
    chunks = [_chunk(1)]
    added = _install_mocks(
        monkeypatch,
        chunks,
        "I don't know. Actually, the answer is 512 documents [1].",
    )

    events = _run(_turn())

    assert events[-1].data["grounded"] is True
    assert [(c.marker, c.chunk_id) for c in added if isinstance(c, MessageCitation)] == [
        (1, chunks[0].chunk_id)
    ]


def test_uncited_real_answer_is_grounded(monkeypatch: pytest.MonkeyPatch) -> None:
    # the model answers from the sources but omits the [n] marker (it happens).
    # This is a real answer, not a refusal, so it must not be logged/counted as
    # one — grounded stays true because it isn't the refusal template (#33).
    chunks = [_chunk(1)]
    _install_mocks(monkeypatch, chunks, "The maximum batch size is 512.")

    events = _run(_turn())

    assert events[-1].data["grounded"] is True


def test_template_refusal_from_generator_is_not_grounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # retrieval cleared the threshold but the model still emitted the refusal
    # template: no citation and it IS the refusal string, so grounded=false.
    chunks = [_chunk(1)]
    _install_mocks(monkeypatch, chunks, "I don't know based on the provided documents.")

    events = _run(_turn())

    assert events[-1].data["grounded"] is False


def test_condensed_query_feeds_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = [_chunk(1)]
    _install_mocks(monkeypatch, chunks, "answer [1].")
    seen: dict[str, str] = {}

    async def fake_condense(_message: str, _history: list[tuple[str, str]]) -> str:
        return "standalone question"

    async def capture_retrieve(
        _factory: object, query: str, _vector: object
    ) -> list[RetrievedChunk]:
        seen["query"] = query
        return chunks

    monkeypatch.setattr(chat, "condense_question", fake_condense)
    monkeypatch.setattr(chat, "hybrid_retrieve", capture_retrieve)

    _run(_turn())

    # retrieval runs on the condensed standalone question, not the raw message
    assert seen["query"] == "standalone question"


def test_rerank_unavailable_degrades_to_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    from citebear_api.rerank import RerankUnavailable

    chunks = [_chunk(1), _chunk(2)]
    _install_mocks(monkeypatch, chunks, "answer from fusion [1].")

    class _FailingReranker:
        async def rerank(self, _query: str, _hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
            raise RerankUnavailable

    monkeypatch.setattr(chat, "get_reranker", lambda: _FailingReranker())

    events = _run(_turn())

    # a scoring glitch answers from the fusion order at low confidence, not refuse
    assert events[0].event == "sources"
    assert events[0].data["confidence"] == "low"
    assert len(events[0].data["citations"]) == 2
    assert "token" in [e.event for e in events]
    assert events[-1].data["grounded"] is True


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
