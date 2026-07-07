"""Shared retrieval driver for the golden sets.

Runs the real hybrid + rerank pipeline against the live DB + gateway and returns
the reranked top-5 chunk contents. Both golden sets (self-owned + preloaded
library) assert against this, so they exercise the identical pipeline.
"""

import asyncio
from collections.abc import Awaitable, Callable

from citebear_api.db import get_session_factory
from citebear_api.rerank import get_reranker
from citebear_api.retrieval import FINAL_TOP_K, embed_query, hybrid_retrieve


async def with_retry[T](call: Callable[[], Awaitable[T]], *, attempts: int = 5) -> T:
    """Free-tier gateway bursts return 429; back off and retry so the golden run
    (and its CI workflow) is not flaky on transient rate limits."""
    for attempt in range(attempts):
        try:
            return await call()
        except Exception as exc:
            transient = "429" in str(exc) or "rate" in str(exc).lower()
            if attempt == attempts - 1 or not transient:
                raise
            await asyncio.sleep(5 * (attempt + 1))
    raise RuntimeError("unreachable")


async def top5_contents(query: str) -> list[str]:
    query_vector = await with_retry(lambda: embed_query(query))
    candidates = await hybrid_retrieve(get_session_factory(), query, query_vector)
    reranked = await with_retry(lambda: get_reranker().rerank(query, candidates))
    return [chunk.content for chunk in reranked[:FINAL_TOP_K]]
