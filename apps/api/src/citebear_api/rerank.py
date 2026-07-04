"""Listwise LLM reranking (SPEC §5.2 step 4).

The hybrid stage optimises recall; the reranker optimises precision. A single
listwise gateway call scores every candidate 0-10 on relevance to the question,
then the candidates are reordered by that score. Kept behind a ``Reranker``
protocol so a cross-encoder can replace the LLM later without touching the
pipeline (SPEC §5.2 rationale). No separate rerank vendor in v1.
"""

import json
import logging
import math
from dataclasses import replace
from functools import lru_cache
from typing import Any, Protocol, cast

from langchain_core.messages import HumanMessage, SystemMessage

from citebear_api.gateway import get_rerank_model, with_retry
from citebear_api.retrieval import RetrievedChunk

logger = logging.getLogger(__name__)

MAX_SCORE = 10.0


class RerankUnavailable(Exception):
    """The reranker produced no usable scores (unparseable/garbled reply).

    Raised instead of returning all-zero scores, which would trip the refusal
    threshold and turn good retrieval into an "I don't know". The caller should
    degrade to the fusion order at low confidence.
    """


SYSTEM_PROMPT = """You rate how well each source excerpt answers a user's question.

Assign every excerpt an integer relevance score from 0 to 10:
- 10 = directly and completely answers the question
- 5 = related and partially useful
- 0 = irrelevant

Judge topical relevance to the question only, not writing quality or length.
Return ONLY a JSON array of objects like [{"id": 1, "score": 8}], exactly one
object per excerpt, no prose and no code fences."""


class Reranker(Protocol):
    async def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Return chunks reordered best-first, each carrying its 0-10 rerank score."""
        ...


def build_prompt(query: str, chunks: list[RetrievedChunk]) -> str:
    excerpts = "\n\n".join(f"[{i + 1}] {chunk.content}" for i, chunk in enumerate(chunks))
    return f"Question: {query}\n\nExcerpts:\n\n{excerpts}"


def parse_scores(raw: str, count: int) -> dict[int, float]:
    """Parse the model's reply into ``{excerpt id (1-based) -> score}``.

    Tolerant of surrounding prose or code fences and of unknown/duplicate ids;
    ids the model omits are simply absent, and the caller scores them 0.
    """
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end <= start:
        return {}
    try:
        parsed: Any = json.loads(raw[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(parsed, list):
        return {}
    items = cast("list[Any]", parsed)

    scores: dict[int, float] = {}
    for item in items:  # json values are dynamic; every access below is guarded
        try:
            idx = int(item["id"])
            score = float(item["score"])
        except (KeyError, TypeError, ValueError):
            continue
        # drop NaN/inf: json.loads accepts a bare NaN literal, and min(10, nan)
        # returns 10 — an unscored chunk would masquerade as a perfect match
        if 1 <= idx <= count and math.isfinite(score):
            scores[idx] = max(0.0, min(MAX_SCORE, score))
    return scores


class LLMReranker:
    async def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not chunks:
            return []
        messages = [SystemMessage(SYSTEM_PROMPT), HumanMessage(build_prompt(query, chunks))]
        response = await with_retry(lambda: get_rerank_model().ainvoke(messages))
        scores = parse_scores(response.text, len(chunks))
        if not scores:
            # a garbled reply must not zero every candidate (which reads as
            # "all irrelevant" -> refuse); let the caller keep the fusion order
            logger.warning("reranker returned no parseable scores; degrading to fusion order")
            raise RerankUnavailable
        # unscored candidates fall to 0; a stable sort keeps RRF order among ties
        scored = [replace(chunk, score=scores.get(i + 1, 0.0)) for i, chunk in enumerate(chunks)]
        scored.sort(key=lambda chunk: chunk.score, reverse=True)
        return scored


@lru_cache
def get_reranker() -> Reranker:
    return LLMReranker()
