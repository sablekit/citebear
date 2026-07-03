"""Retrieval (SPEC §5.2).

Milestone 1 is vector-only: embed the query, cosine top-K over ready
documents. Keyword search, RRF fusion, and reranking land in Milestone 3.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from citebear_api.gateway import get_embeddings
from citebear_api.models import Chunk, Document

TOP_K = 5


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: UUID
    document_title: str
    content: str
    section_path: list[str]
    page_start: int | None
    page_end: int | None


async def retrieve(session: AsyncSession, question: str) -> list[RetrievedChunk]:
    query_vector = await get_embeddings().aembed_query(question)
    statement = (
        select(Chunk, Document.title)
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.status == "ready")
        .order_by(Chunk.embedding.cosine_distance(query_vector))  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
        .limit(TOP_K)
    )
    rows = (await session.execute(statement)).all()
    return [
        RetrievedChunk(
            chunk_id=chunk.id,
            document_title=title,
            content=chunk.content,
            section_path=chunk.section_path or [],
            page_start=chunk.page_start,
            page_end=chunk.page_end,
        )
        for chunk, title in rows
    ]
