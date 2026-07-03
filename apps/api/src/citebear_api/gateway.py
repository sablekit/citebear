"""Model access via an OpenAI-compatible gateway (SPEC §2 goal 7).

Chat and embedding models are provider/model strings resolved by the
gateway; switching providers is a config change, not a code change.
"""

from functools import lru_cache

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import SecretStr

from citebear_api.config import get_settings


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


@lru_cache
def get_chat_model() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.chat_model,
        base_url=settings.gateway_base_url,
        api_key=SecretStr(settings.gateway_api_key),
        temperature=0.0,  # grounded QA: no creativity wanted
    )
