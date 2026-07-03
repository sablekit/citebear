from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from citebear_api.generation import REFUSAL_TEXT, build_context, build_messages, is_refusal
from citebear_api.retrieval import RetrievedChunk


def _chunk(
    content: str = "Some content.",
    title: str = "CiteBear Specification",
    section_path: list[str] | None = None,
    page_start: int | None = None,
    page_end: int | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_title=title,
        source_url="https://example.com/spec",
        content=content,
        section_path=section_path or [],
        page_start=page_start,
        page_end=page_end,
        score=0.9,
    )


def test_context_numbers_excerpts_from_one() -> None:
    context = build_context([_chunk("First."), _chunk("Second.")])
    assert "[1] CiteBear Specification" in context
    assert "[2] CiteBear Specification" in context
    assert context.index("[1]") < context.index("First.") < context.index("[2]")


def test_context_includes_section_trail() -> None:
    context = build_context([_chunk(section_path=["Install", "Linux"])])
    assert "Install > Linux" in context


def test_context_includes_page_range_when_present() -> None:
    context = build_context([_chunk(page_start=3, page_end=4)])
    assert "pp.3-4" in context
    context_single = build_context([_chunk(page_start=7)])
    assert "p.7" in context_single


def test_messages_order_history_then_question() -> None:
    messages = build_messages(
        "What is RRF?",
        [_chunk()],
        history=[("user", "Hi"), ("assistant", "Hello!")],
    )
    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], HumanMessage)
    assert isinstance(messages[2], AIMessage)
    final = messages[-1]
    assert isinstance(final, HumanMessage)
    assert "Source excerpts:" in final.text
    assert "Question: What is RRF?" in final.text


def test_refusal_detection() -> None:
    assert is_refusal(REFUSAL_TEXT)
    assert is_refusal("  I don't know based on the provided documents. ")
    assert is_refusal("I don’t know based on the provided documents.")  # noqa: RUF001
    assert not is_refusal("The rate limit is 20 requests per hour. [1]")
