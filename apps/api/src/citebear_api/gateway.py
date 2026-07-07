"""Model access via an OpenAI-compatible gateway (SPEC §2 goal 7).

Chat and embedding models are provider/model strings resolved by the
gateway; switching providers is a config change, not a code change.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from functools import lru_cache

import openai
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import SecretStr

from citebear_api.config import get_settings

logger = logging.getLogger(__name__)

# A full-length document produces thousands of chunks. Sending them as a single
# embedding request risks the gateway's payload limit and serializes the whole
# ingest, so they go out as fixed-size batches, a few requests in flight at once.
EMBED_BATCH_SIZE = 128
EMBED_CONCURRENCY = 4

# Transient gateway faults worth retrying: rate limits (429s the free tier trips
# on bursts), timeouts, dropped connections, and upstream 5xx.
_TRANSIENT_ERRORS = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)
RETRY_ATTEMPTS = 4
RETRY_BASE_DELAY = 1.0  # seconds; doubled each attempt
# the interactive chat path is latency-sensitive: one quick retry salvages a
# transient blip without stacking multi-second backoff across the serial
# embed → rerank calls of a single turn (ingest keeps the patient default)
INTERACTIVE_RETRY_ATTEMPTS = 2
INTERACTIVE_RETRY_DELAY = 0.5


def _is_transient(exc: BaseException) -> bool:
    # match the exception type where langchain surfaces it cleanly, and fall back
    # to the status code in the message for anything that arrives wrapped
    return isinstance(exc, _TRANSIENT_ERRORS) or "429" in str(exc)


async def with_retry[T](
    call: Callable[[], Awaitable[T]],
    *,
    attempts: int = RETRY_ATTEMPTS,
    base_delay: float = RETRY_BASE_DELAY,
) -> T:
    """Run an async gateway call, retrying transient faults with exponential
    backoff. Non-transient errors (and the final attempt) propagate unchanged."""
    for attempt in range(attempts):
        try:
            return await call()
        except Exception as exc:
            if attempt == attempts - 1 or not _is_transient(exc):
                raise
            delay = base_delay * (2**attempt)
            logger.warning(
                "transient gateway error, retrying in %.1fs (attempt %d/%d)",
                delay,
                attempt + 1,
                attempts,
            )
            await asyncio.sleep(delay)
    raise RuntimeError("unreachable")  # pragma: no cover


@lru_cache
def get_embeddings() -> OpenAIEmbeddings:
    settings = get_settings()
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        base_url=settings.gateway_base_url,
        api_key=SecretStr(settings.gateway_api_key),
        # send plain strings: gateways don't all accept OpenAI's
        # pre-tokenized (token-array) embedding request format
        check_embedding_ctx_length=False,
    )


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed many texts as bounded-concurrency batches, preserving input order."""
    if not texts:
        return []
    embeddings = get_embeddings()
    batches = [texts[i : i + EMBED_BATCH_SIZE] for i in range(0, len(texts), EMBED_BATCH_SIZE)]
    semaphore = asyncio.Semaphore(EMBED_CONCURRENCY)

    async def run(batch: list[str]) -> list[list[float]]:
        async with semaphore:
            return await with_retry(lambda: embeddings.aembed_documents(batch))

    tasks = [asyncio.create_task(run(batch)) for batch in batches]
    try:
        batched = await asyncio.gather(*tasks)
    except Exception:
        # bare gather leaves siblings running on the first failure; cancel them so
        # a failed ingest doesn't keep burning gateway credits (and retries) after
        # the document is already marked failed
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    return [vector for batch_vectors in batched for vector in batch_vectors]


@lru_cache
def get_chat_model() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.chat_model,
        base_url=settings.gateway_base_url,
        api_key=SecretStr(settings.gateway_api_key),
        temperature=0.0,  # grounded QA: no creativity wanted
    )


@lru_cache
def get_rerank_model() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.rerank_model,
        base_url=settings.gateway_base_url,
        api_key=SecretStr(settings.gateway_api_key),
        temperature=0.0,  # deterministic scoring
    )
