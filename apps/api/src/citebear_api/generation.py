"""Grounded answer generation (SPEC §5.3).

The model sees numbered source excerpts and must answer only from them;
when they don't answer the question it replies with the refusal template.
Citation markers, the sources event, and the post-check land in Milestone 2;
confidence scoring and the refusal threshold land in Milestone 3.
"""

from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from citebear_api.gateway import get_chat_model
from citebear_api.retrieval import RetrievedChunk

REFUSAL_PREFIX = "I don't know"
REFUSAL_TEXT = "I don't know based on the provided documents."

SYSTEM_PROMPT = f"""You are CiteBear, a source-cited assistant answering questions about \
a document library.

Rules:
- Answer ONLY from the numbered source excerpts provided. Do not use outside knowledge.
- Every number, date, and name in your answer must come from the excerpts.
- Reference excerpts inline with their markers, e.g. [1] or [2][3].
- If the excerpts do not answer the question, reply exactly: "{REFUSAL_TEXT}"
- Be concise and factual."""


def _excerpt_header(marker: int, chunk: RetrievedChunk) -> str:
    location = " > ".join(chunk.section_path) if chunk.section_path else None
    if chunk.page_start is not None:
        pages = (
            f"p.{chunk.page_start}"
            if chunk.page_end in (None, chunk.page_start)
            else f"pp.{chunk.page_start}-{chunk.page_end}"
        )
        location = f"{location}, {pages}" if location else pages
    suffix = f" — {location}" if location else ""
    return f"[{marker}] {chunk.document_title}{suffix}"


def build_context(chunks: list[RetrievedChunk]) -> str:
    blocks = [f"{_excerpt_header(i + 1, chunk)}\n{chunk.content}" for i, chunk in enumerate(chunks)]
    return "\n\n".join(blocks)


def build_messages(
    question: str,
    chunks: list[RetrievedChunk],
    history: list[tuple[str, str]],
) -> list[BaseMessage]:
    """history: (role, content) pairs, oldest first, roles 'user' | 'assistant'."""
    messages: list[BaseMessage] = [SystemMessage(SYSTEM_PROMPT)]
    for role, content in history:
        messages.append(HumanMessage(content) if role == "user" else AIMessage(content))
    messages.append(
        HumanMessage(f"Source excerpts:\n\n{build_context(chunks)}\n\nQuestion: {question}")
    )
    return messages


def is_refusal(answer: str) -> bool:
    return answer.strip().startswith(REFUSAL_PREFIX)


async def stream_answer(
    question: str,
    chunks: list[RetrievedChunk],
    history: list[tuple[str, str]],
) -> AsyncIterator[str]:
    """Yield answer text deltas from the chat model."""
    async for part in get_chat_model().astream(build_messages(question, chunks, history)):
        if part.text:
            yield part.text
