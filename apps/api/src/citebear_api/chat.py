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
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy import select
from sse_starlette import EventSourceResponse, ServerSentEvent

from citebear_api.citations import build_citations, cited_markers
from citebear_api.config import get_settings
from citebear_api.db import get_session_factory
from citebear_api.events import (
    ChatEvent,
    done_event,
    error_event,
    sources_event,
    token_event,
)
from citebear_api.generation import is_refusal, stream_answer
from citebear_api.models import Message, MessageCitation
from citebear_api.problems import problem
from citebear_api.retrieval import embed_query, retrieve

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


def require_internal_key(
    x_internal_key: Annotated[str | None, Header()] = None,
) -> None:
    expected = get_settings().internal_api_key
    if x_internal_key is None or not hmac.compare_digest(
        x_internal_key.encode(), expected.encode()
    ):
        raise HTTPException(status_code=401, detail="Missing or invalid internal API key")


def hash_ip(ip: str) -> str:
    """Keyed hash: rate-limit counting works, raw IPs are not recoverable."""
    key = get_settings().internal_api_key.encode()
    return hmac.new(key, ip.encode(), hashlib.sha256).hexdigest()


async def run_chat_turn(turn: ChatTurn) -> AsyncIterator[ChatEvent]:
    """The Milestone 1 pipeline: persist question, retrieve, generate, persist answer."""
    started = time.monotonic()
    settings = get_settings()
    session_factory = get_session_factory()
    try:
        # gateway round trip first, so no DB connection is held across it
        query_vector = await embed_query(turn.message)
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
            chunks = await retrieve(db, query_vector)
            await db.commit()

        # sources before tokens: the UI renders citation chips while the answer
        # is still being written (SPEC §5.4)
        citations = build_citations(chunks)
        yield sources_event(citations)

        parts: list[str] = []
        async for delta in stream_answer(turn.message, chunks, history):
            parts.append(delta)
            yield token_event(delta)
        answer = "".join(parts)
        grounded = not is_refusal(answer)

        async with session_factory() as db:
            assistant_message = Message(
                session_id=turn.session_id,
                role="assistant",
                content=answer,
                grounded=grounded,
                model=settings.chat_model,
                latency_ms=int((time.monotonic() - started) * 1000),
            )
            db.add(assistant_message)
            await db.flush()
            message_id = assistant_message.id
            # post-check: persist only the citations the answer actually used and
            # that map to a real chunk (SPEC §5.3)
            for marker in cited_markers(answer, len(chunks)):
                chunk = chunks[marker - 1]
                db.add(
                    MessageCitation(
                        message_id=message_id,
                        marker=marker,
                        chunk_id=chunk.chunk_id,
                        score=chunk.score,
                    )
                )
            await db.commit()

        yield done_event(message_id, grounded)
    except Exception:
        logger.exception("chat turn failed")
        yield error_event(
            problem(500, "Internal Server Error", "The answer could not be generated.")
        )


def get_chat_stream() -> ChatStream:
    return run_chat_turn


@router.post("/chat", dependencies=[Depends(require_internal_key)])
async def chat(
    request: Request,
    body: ChatRequest,
    stream: Annotated[ChatStream, Depends(get_chat_stream)],
) -> EventSourceResponse:
    # X-Client-IP is only trusted because the internal key was validated
    client_ip = request.headers.get("x-client-ip")
    turn = ChatTurn(
        session_id=body.session_id,
        message=body.message,
        ip_hash=hash_ip(client_ip) if client_ip else None,
    )

    async def sse_events() -> AsyncIterator[ServerSentEvent]:
        async for event in stream(turn):
            yield ServerSentEvent(event=event.event, data=json.dumps(event.data))

    return EventSourceResponse(sse_events())
