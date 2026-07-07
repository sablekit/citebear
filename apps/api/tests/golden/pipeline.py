"""Shared retrieval driver and corpus gate for the golden sets.

Runs the real hybrid + rerank pipeline against the live DB + gateway and returns
the reranked top-5 chunk contents. Both golden sets (self-owned + preloaded
library) assert against this, so they exercise the identical pipeline.
"""

import asyncio
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import select

from citebear_api.db import get_session_factory, run_async
from citebear_api.models import Document
from citebear_api.rerank import get_reranker
from citebear_api.retrieval import FINAL_TOP_K, embed_query, hybrid_retrieve


async def with_retry[T](call: Callable[[], Awaitable[T]], *, attempts: int = 5) -> T:
    """Free-tier gateway bursts return 429; back off and retry so the golden run
    (and its CI workflow) is not flaky on transient rate limits. Classify on the
    rate-limit phrase, not a bare "rate" (which matches "generate"/"duplicate")."""
    for attempt in range(attempts):
        try:
            return await call()
        except Exception as exc:
            message = str(exc).lower()
            transient = "429" in message or "rate limit" in message or "rate_limit" in message
            if attempt == attempts - 1 or not transient:
                raise
            await asyncio.sleep(5 * (attempt + 1))
    raise RuntimeError("unreachable")


async def _ready_titles() -> set[str]:
    async with get_session_factory()() as db:
        titles = (
            await db.execute(select(Document.title).where(Document.status == "ready"))
        ).scalars()
        return set(titles)


def require_corpus(required_titles: set[str]) -> None:
    """Gate a golden set on its corpus being ingested.

    Skip when *none* of the corpus is present (the set isn't provisioned here —
    e.g. local dev, or the other set's DB) or the DB is unreachable. But *fail*
    when it's only partially present: a load step that was supposed to ingest
    the whole corpus didn't, and skipping there would let the job go green
    having asserted nothing — the exact silent no-op this guard prevents.
    """
    try:
        titles = run_async(_ready_titles())
    except Exception as exc:  # DB unreachable / not migrated
        pytest.skip(f"golden set needs a live database: {exc}")
    if not required_titles & titles:
        pytest.skip("golden set needs its corpus ingested (run the ingest/load step)")
    missing = required_titles - titles
    if missing:
        pytest.fail(f"golden corpus only partially ingested; missing: {sorted(missing)}")


async def top5_contents(query: str) -> list[str]:
    query_vector = await with_retry(lambda: embed_query(query))
    candidates = await hybrid_retrieve(get_session_factory(), query, query_vector)
    reranked = await with_retry(lambda: get_reranker().rerank(query, candidates))
    return [chunk.content for chunk in reranked[:FINAL_TOP_K]]
