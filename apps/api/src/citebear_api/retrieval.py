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
    source_url: str
    content: str
    section_path: list[str]
    page_start: int | None
    page_end: int | None
    # cosine similarity (1 - distance), higher is closer. This is the relevance
    # score persisted with each citation until the reranker replaces it (M3).
    score: float


async def embed_query(question: str) -> list[float]:
    """Kept separate from the search so callers never hold a DB
    connection across this gateway round trip."""
    return await get_embeddings().aembed_query(question)


async def retrieve(session: AsyncSession, query_vector: list[float]) -> list[RetrievedChunk]:
    distance = Chunk.embedding.cosine_distance(query_vector)  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
    statement = (
        # explicit columns: a full Chunk row would drag each result's
        # 1536-dim embedding and tsvector back over the wire unused
        select(
            Chunk.id,
            Chunk.content,
            Chunk.section_path,
            Chunk.page_start,
            Chunk.page_end,
            Document.title,
            Document.source_url,
            distance.label("distance"),
        )
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.status == "ready")
        .order_by(distance)
        .limit(TOP_K)
    )
    rows = (await session.execute(statement)).all()
    return [
        RetrievedChunk(
            chunk_id=row.id,
            document_title=row.title,
            source_url=row.source_url,
            content=row.content,
            section_path=row.section_path or [],
            page_start=row.page_start,
            page_end=row.page_end,
            score=1.0 - row.distance,
        )
        for row in rows
    ]
