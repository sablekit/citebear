"""Retrieval (SPEC §5.2).

Hybrid first stage: a vector (cosine) and a keyword (full-text) search run in
parallel over the ready documents, then Reciprocal Rank Fusion merges their
rankings into the candidate list the reranker consumes. Vector search catches
paraphrase; keyword search catches exact identifiers and error codes that
embeddings blur.
"""

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from citebear_api.fusion import reciprocal_rank_fusion
from citebear_api.gateway import (
    INTERACTIVE_RETRY_ATTEMPTS,
    INTERACTIVE_RETRY_DELAY,
    get_embeddings,
    with_retry,
)
from citebear_api.models import Chunk, Document

VECTOR_TOP_K = 20
KEYWORD_TOP_K = 20
FUSION_TOP_K = 12
FINAL_TOP_K = 5  # chunks shown to the generator (SPEC §5.2 step 4); rerank trims to this
# HNSW candidate-list size, applied per query with SET LOCAL (never a
# server-wide GUC), must be >= the vector limit. Swept against the golden set
# (#8): at M3's small corpus recall@20 is saturated (15/15) and latency flat
# (~12-18 ms) across ef 20-200, so the value is not yet load-bearing; 100 gives
# headroom above the 20-candidate fetch for the larger M6 library — re-sweep then.
HNSW_EF_SEARCH = 100

# columns every search returns; a full Chunk row would drag each result's
# 1536-dim embedding and tsvector back over the wire unused
_COLUMNS = (
    Chunk.id,
    Chunk.content,
    Chunk.section_path,
    Chunk.page_start,
    Chunk.page_end,
    Document.title,
    Document.source_url,
)


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: UUID
    document_title: str
    source_url: str
    content: str
    section_path: list[str]
    page_start: int | None
    page_end: int | None
    # relevance score: cosine similarity or ts_rank at this stage; the reranker
    # (SPEC §5.2 step 4) overwrites it with its 0-10 score before citations
    score: float


async def embed_query(question: str) -> list[float]:
    """Kept separate from the search so callers never hold a DB
    connection across this gateway round trip."""
    return await with_retry(
        lambda: get_embeddings().aembed_query(question),
        attempts=INTERACTIVE_RETRY_ATTEMPTS,
        base_delay=INTERACTIVE_RETRY_DELAY,
    )


def _to_chunk(row: Any, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=row.id,
        document_title=row.title,
        source_url=row.source_url,
        content=row.content,
        section_path=row.section_path or [],
        page_start=row.page_start,
        page_end=row.page_end,
        score=score,
    )


async def vector_search(
    session: AsyncSession,
    query_vector: list[float],
    limit: int = VECTOR_TOP_K,
    ef_search: int = HNSW_EF_SEARCH,
) -> list[RetrievedChunk]:
    # ef_search must be set in the same transaction as the query (pgvector);
    # SET LOCAL scopes it there. int() guards the interpolation — SET takes no
    # bind parameters.
    await session.execute(text(f"SET LOCAL hnsw.ef_search = {int(ef_search)}"))
    distance = Chunk.embedding.cosine_distance(query_vector)  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
    statement = (
        select(*_COLUMNS, distance.label("distance"))
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.status == "ready")
        .order_by(distance)
        .limit(limit)
    )
    rows = (await session.execute(statement)).all()
    return [_to_chunk(row, 1.0 - row.distance) for row in rows]


async def keyword_search(
    session: AsyncSession, query_text: str, limit: int = KEYWORD_TOP_K
) -> list[RetrievedChunk]:
    tsquery = func.websearch_to_tsquery("english", query_text)
    rank = func.ts_rank(Chunk.fts, tsquery)
    statement = (
        select(*_COLUMNS, rank.label("rank"))
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.status == "ready", Chunk.fts.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(limit)
    )
    rows = (await session.execute(statement)).all()
    return [_to_chunk(row, row.rank) for row in rows]


async def hybrid_retrieve(
    session_factory: async_sessionmaker[AsyncSession],
    query_text: str,
    query_vector: list[float],
    ef_search: int = HNSW_EF_SEARCH,
) -> list[RetrievedChunk]:
    """Vector and keyword searches in parallel, fused by RRF -> top-12.

    Each search opens its own session so the two run concurrently; the caller
    has already done the embedding round trip, so no connection is held across
    a gateway call. ``ef_search`` is exposed for the tuning sweep (#8).
    """

    async def _vector() -> list[RetrievedChunk]:
        async with session_factory() as db:
            return await vector_search(db, query_vector, ef_search=ef_search)

    async def _keyword() -> list[RetrievedChunk]:
        async with session_factory() as db:
            return await keyword_search(db, query_text)

    vector_hits, keyword_hits = await asyncio.gather(_vector(), _keyword())
    # dedup across both lists; either representative row is fine since the
    # reranker re-scores every chunk — RRF rank (from `fused`) is what orders them
    by_id = {c.chunk_id: c for c in (*keyword_hits, *vector_hits)}
    fused = reciprocal_rank_fusion(
        [[c.chunk_id for c in vector_hits], [c.chunk_id for c in keyword_hits]]
    )
    return [by_id[chunk_id] for chunk_id in fused[:FUSION_TOP_K]]
