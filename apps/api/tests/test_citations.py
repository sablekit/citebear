from uuid import uuid4

from citebear_api.citations import build_citations, cited_markers
from citebear_api.events import sources_event
from citebear_api.retrieval import RetrievedChunk


def _chunk(marker_hint: int) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_title=f"Doc {marker_hint}",
        source_url=f"https://example.com/{marker_hint}",
        content=f"Content {marker_hint}.",
        section_path=["Section", str(marker_hint)],
        page_start=marker_hint,
        page_end=marker_hint,
        score=0.5,
    )


def test_build_citations_numbers_from_one() -> None:
    citations = build_citations([_chunk(1), _chunk(2)])
    assert [c.marker for c in citations] == [1, 2]
    assert citations[0].doc_title == "Doc 1"
    assert citations[0].page == 1
    assert citations[0].snippet == "Content 1."
    assert citations[0].source_url == "https://example.com/1"


def test_sources_event_is_camelcase() -> None:
    event = sources_event(build_citations([_chunk(1)]), "high")
    assert event.event == "sources"
    assert event.data["confidence"] == "high"
    citation = event.data["citations"][0]
    assert set(citation) == {
        "marker",
        "chunkId",
        "docTitle",
        "page",
        "sectionPath",
        "sourceUrl",
        "snippet",
    }
    assert isinstance(citation["chunkId"], str)  # uuid serialized for the wire


def test_cited_markers_keeps_used_valid_markers_in_order() -> None:
    answer = "RRF fuses ranks [2]. Vector search finds paraphrase [1][2]."
    assert cited_markers(answer, chunk_count=5) == [2, 1]


def test_cited_markers_drops_out_of_range() -> None:
    # the model referenced [9] but only 5 chunks were retrieved
    assert cited_markers("See [9] and [3].", chunk_count=5) == [3]


def test_cited_markers_empty_for_refusal() -> None:
    assert cited_markers("I don't know based on the provided documents.", chunk_count=5) == []
