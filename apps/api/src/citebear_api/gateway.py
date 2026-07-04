"""Model access via an OpenAI-compatible gateway (SPEC §2 goal 7).

Chat and embedding models are provider/model strings resolved by the
gateway; switching providers is a config change, not a code change.
"""

import asyncio
from functools import lru_cache

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import SecretStr

from citebear_api.config import get_settings

# A full-length document produces thousands of chunks. Sending them as a single
# embedding request risks the gateway's payload limit and serializes the whole
# ingest, so they go out as fixed-size batches, a few requests in flight at once.
EMBED_BATCH_SIZE = 128
EMBED_CONCURRENCY = 4


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
            return await embeddings.aembed_documents(batch)

    batched = await asyncio.gather(*(run(batch) for batch in batches))
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
