"""Confidence mapping and the refusal threshold (SPEC §5.3, §9 unit target)."""

from uuid import uuid4

from citebear_api.confidence import HIGH, LOW, assess
from citebear_api.retrieval import RetrievedChunk


def _chunk(score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_title="d",
        source_url="",
        content="x",
        section_path=[],
        page_start=None,
        page_end=None,
        score=score,
    )


def test_high_when_best_at_least_7() -> None:
    assert assess([_chunk(7.0), _chunk(2.0)]) == (HIGH, True)


def test_low_but_generates_between_thresholds() -> None:
    assert assess([_chunk(6.9), _chunk(5.0)]) == (LOW, True)


def test_refuses_when_nothing_above_4() -> None:
    assert assess([_chunk(4.0), _chunk(1.0)]) == (LOW, False)


def test_empty_refuses() -> None:
    assert assess([]) == (LOW, False)
