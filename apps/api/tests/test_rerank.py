"""Listwise reranker: score parsing and reordering (SPEC §5.2 step 4).

The model call is mocked, so these stay pure unit tests: they pin the tolerant
JSON parsing and the reorder / missing-score behaviour without a gateway.
"""

import asyncio
from uuid import uuid4

import pytest

from citebear_api import rerank
from citebear_api.rerank import LLMReranker, RerankUnavailable, parse_scores
from citebear_api.retrieval import RetrievedChunk


def _chunk(n: int) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_title=f"Doc {n}",
        source_url="",
        content=f"c{n}",
        section_path=[],
        page_start=None,
        page_end=None,
        score=0.0,
    )


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeModel:
    def __init__(self, text: str) -> None:
        self._text = text

    async def ainvoke(self, _messages: object) -> _FakeResponse:
        return _FakeResponse(self._text)


def test_parse_scores_valid() -> None:
    assert parse_scores('[{"id": 1, "score": 8}, {"id": 2, "score": 3}]', 2) == {1: 8.0, 2: 3.0}


def test_parse_scores_tolerates_fences_and_prose() -> None:
    raw = 'Here you go:\n```json\n[{"id": 1, "score": 10}]\n```'
    assert parse_scores(raw, 1) == {1: 10.0}


def test_parse_scores_clamps_and_drops_out_of_range_ids() -> None:
    raw = '[{"id": 1, "score": 15}, {"id": 9, "score": 5}, {"id": 2, "score": -4}]'
    assert parse_scores(raw, 2) == {1: 10.0, 2: 0.0}


def test_parse_scores_malformed_returns_empty() -> None:
    assert parse_scores("not json at all", 3) == {}
    assert parse_scores("", 3) == {}


def test_parse_scores_drops_non_finite() -> None:
    # json.loads accepts bare NaN/Infinity; min(10, nan) would return 10, so a
    # non-finite score must be dropped, not clamped to a perfect match
    assert parse_scores('[{"id": 1, "score": NaN}, {"id": 2, "score": Infinity}]', 2) == {}


def test_rerank_reorders_by_score_and_defaults_missing_to_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunks = [_chunk(1), _chunk(2), _chunk(3)]
    # model scores 2 highest, 1 mid, omits 3 -> 0
    monkeypatch.setattr(
        rerank,
        "get_rerank_model",
        lambda: _FakeModel('[{"id": 1, "score": 5}, {"id": 2, "score": 9}]'),
    )

    result = asyncio.run(LLMReranker().rerank("q", chunks))

    assert [c.content for c in result] == ["c2", "c1", "c3"]
    assert [c.score for c in result] == [9.0, 5.0, 0.0]


def test_rerank_empty_returns_empty() -> None:
    assert asyncio.run(LLMReranker().rerank("q", [])) == []


def test_rerank_raises_when_reply_unparseable(monkeypatch: pytest.MonkeyPatch) -> None:
    # a garbled reply must not zero every candidate (which would trip the refusal
    # threshold); it signals the caller to degrade to the fusion order
    monkeypatch.setattr(rerank, "get_rerank_model", lambda: _FakeModel("sorry, no scores here"))
    with pytest.raises(RerankUnavailable):
        asyncio.run(LLMReranker().rerank("q", [_chunk(1), _chunk(2)]))
