"""POST /chat: retrieval-grounded streaming answers over SSE (SPEC §5.4).

Event sequence: sources -> token* -> done (or error). The sources event is sent
before the first token so the UI can render citation chips immediately.
"""

import hashlib
import hmac
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sse_starlette import EventSourceResponse, ServerSentEvent

from citebear_api.auth import require_internal_key
from citebear_api.citations import build_citations, cited_markers
from citebear_api.condense import condense_question
from citebear_api.confidence import LOW, assess
from citebear_api.config import get_settings
from citebear_api.db import get_session_factory
from citebear_api.events import (
    ChatEvent,
    done_event,
    error_event,
    sources_event,
    token_event,
)
from citebear_api.generation import REFUSAL_TEXT, stream_answer
from citebear_api.models import Message, MessageCitation
from citebear_api.problems import problem, problem_response
from citebear_api.rate_limit import RATE_LIMIT_PER_HOUR, RateLimitState, check_chat_rate_limit
from citebear_api.rerank import RerankUnavailable, get_reranker
from citebear_api.retrieval import FINAL_TOP_K, RetrievedChunk, embed_query, hybrid_retrieve

logger = logging.getLogger(__name__)

router = APIRouter()

HISTORY_MESSAGES = 6  # last N turns of the session shown to the generator


class ChatRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    session_id: uuid.UUID
    message: str = Field(min_length=1, max_length=4000)


@dataclass(frozen=True)
class ChatTurn:
    session_id: uuid.UUID
    message: str
    ip_hash: str | None


ChatStream = Callable[[ChatTurn], AsyncIterator[ChatEvent]]
RateLimiter = Callable[[str], Awaitable[RateLimitState]]


def hash_ip(ip: str) -> str:
    """Keyed hash: rate-limit counting works, raw IPs are not recoverable.

    Keyed with a dedicated IP_HASH_SECRET, not the web->api key, so the two
    rotate independently and neither leaks the other (#9).
    """
    key = get_settings().ip_hash_secret.encode()
    return hmac.new(key, ip.encode(), hashlib.sha256).hexdigest()


async def persist_citations(
    session_factory: async_sessionmaker[AsyncSession],
    message_id: uuid.UUID,
    answer: str,
    chunks: list[RetrievedChunk],
) -> None:
    """Persist the answer's valid citation markers, each in its own savepoint.

    A cited chunk can be deleted between retrieval and now once documents can be
    removed (#7 delete/re-ingest lands in M4). The savepoint isolates that
    chunk's FK violation to its own marker — the other citations still commit,
    and the already-committed assistant message is never touched.

    Citations are entirely best-effort: the assistant message is already
    committed and streamed, so no failure here (a vanished chunk, or a fault at
    commit) may turn a delivered answer into an error — the turn still ends in
    `done` (#19). Failures are logged and dropped.
    """
    try:
        async with session_factory() as db:
            for marker in cited_markers(answer, len(chunks)):
                chunk = chunks[marker - 1]
                try:
                    async with db.begin_nested():
                        db.add(
                            MessageCitation(
                                message_id=message_id,
                                marker=marker,
                                chunk_id=chunk.chunk_id,
                                score=chunk.score,
                            )
                        )
                        await db.flush()
                except IntegrityError:
                    logger.warning(
                        "cited chunk %s vanished before persistence; skipping marker %s",
                        chunk.chunk_id,
                        marker,
                    )
            await db.commit()
    except Exception:
        logger.warning("failed to persist citations for message %s", message_id)


async def run_chat_turn(turn: ChatTurn) -> AsyncIterator[ChatEvent]:
    """The Milestone 1 pipeline: persist question, retrieve, generate, persist answer."""
    started = time.monotonic()
    settings = get_settings()
    session_factory = get_session_factory()
    try:
        async with session_factory() as db:
            history_rows = (
                await db.execute(
                    select(Message.role, Message.content)
                    .where(Message.session_id == turn.session_id)
                    .order_by(Message.created_at.desc())
                    .limit(HISTORY_MESSAGES)
                )
            ).all()
            history = [(role, content) for role, content in reversed(history_rows)]
            db.add(
                Message(
                    session_id=turn.session_id,
                    role="user",
                    content=turn.message,
                    ip_hash=turn.ip_hash,
                )
            )
            await db.commit()

        # follow-ups elide their subject, so retrieval runs on a standalone
        # question rewritten from the history (SPEC §5.3); the first turn has no
        # history and skips the call. Gateway round trips (condense, embed) stay
        # outside the write transaction above so no DB connection is held.
        query = await condense_question(turn.message, history)
        query_vector = await embed_query(query)

        # hybrid retrieval runs on its own sessions (vector ∥ keyword); the
        # reranker then reorders the candidates by relevance and we keep the top-5
        candidates = await hybrid_retrieve(session_factory, query, query_vector)
        try:
            reranked = await get_reranker().rerank(query, candidates)
            chunks = reranked[:FINAL_TOP_K]
            confidence, should_generate = assess(chunks)
        except RerankUnavailable:
            # scoring glitch, not a retrieval miss: answer from the fusion order
            # at low confidence rather than refusing good candidates
            chunks = candidates[:FINAL_TOP_K]
            confidence, should_generate = LOW, bool(chunks)

        parts: list[str] = []
        if should_generate:
            # sources before tokens: the UI renders citation chips while the
            # answer is still being written (SPEC §5.4)
            yield sources_event(build_citations(chunks), confidence)
            async for delta in stream_answer(turn.message, chunks, history):
                parts.append(delta)
                yield token_event(delta)
            answer = "".join(parts)
            # grounded = the answer actually cites a retrieved source. The
            # citation is structural proof it drew on the documents: a refusal —
            # the exact template or any paraphrase — cites nothing (#33), and a
            # cited answer that happens to open with the refusal wording is still
            # grounded (#59). This replaces the is_refusal string-prefix
            # heuristic, which mislabeled both cases.
            grounded = bool(cited_markers(answer, len(chunks)))
        else:
            # nothing cleared the threshold: refuse without calling the generator
            # (SPEC §5.3). No chunk is trustworthy enough to cite.
            yield sources_event([], confidence)
            answer = REFUSAL_TEXT
            yield token_event(answer)
            grounded = False

        # persist the assistant message first, in its own transaction, so a
        # citation FK failure can never discard an answer the user already saw
        async with session_factory() as db:
            assistant_message = Message(
                session_id=turn.session_id,
                role="assistant",
                content=answer,
                grounded=grounded,
                confidence=confidence,
                model=settings.chat_model,
                latency_ms=int((time.monotonic() - started) * 1000),
            )
            db.add(assistant_message)
            await db.flush()
            message_id = assistant_message.id
            await db.commit()

        # post-check: persist only the citations the answer actually used (SPEC §5.3)
        await persist_citations(session_factory, message_id, answer, chunks)

        yield done_event(message_id, grounded)
    except Exception:
        logger.exception("chat turn failed")
        yield error_event(
            problem(500, "Internal Server Error", "The answer could not be generated.")
        )


def get_chat_stream() -> ChatStream:
    return run_chat_turn


def get_rate_limiter() -> RateLimiter:
    async def limiter(ip_hash: str) -> RateLimitState:
        return await check_chat_rate_limit(get_session_factory(), ip_hash)

    return limiter


@router.post("/chat", dependencies=[Depends(require_internal_key)])
async def chat(
    request: Request,
    body: ChatRequest,
    stream: Annotated[ChatStream, Depends(get_chat_stream)],
    rate_limit: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> Response:
    # X-Client-IP is only trusted because the internal key was validated
    client_ip = request.headers.get("x-client-ip")
    ip_hash = hash_ip(client_ip) if client_ip else None

    # A request that reached here with a valid internal key but no client IP did
    # not pass Vercel's edge (which always sets x-real-ip) — in practice local
    # dev. It can't originate from the public internet without the key, so it is
    # deliberately not rate-limited rather than denied (which would wedge dev).
    if ip_hash is not None:
        state = await rate_limit(ip_hash)
        if not state.allowed:
            response = problem_response(
                429,
                "Too Many Requests",
                f"Rate limit reached: {RATE_LIMIT_PER_HOUR} questions per hour. "
                "Please try again later.",
                retryAfter=state.retry_after,
            )
            response.headers["Retry-After"] = str(state.retry_after)
            return response

    turn = ChatTurn(session_id=body.session_id, message=body.message, ip_hash=ip_hash)

    async def sse_events() -> AsyncIterator[ServerSentEvent]:
        async for event in stream(turn):
            yield ServerSentEvent(event=event.event, data=json.dumps(event.data))

    return EventSourceResponse(sse_events())
