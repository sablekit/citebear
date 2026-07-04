"""Admin question log (SPEC §6, §7): GET /admin/questions.

Each entry is one answered turn: the assistant message (grounded, confidence,
model) plus its 👍/👎 and the question that prompted it. Question and answer are
separate `messages` rows linked by session + order, so the question is the
latest user message in the same session before the answer — paired in Python
(two plain selects) rather than a lateral join.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import func, select

from citebear_api.auth import require_admin, require_internal_key
from citebear_api.db import get_session_factory
from citebear_api.models import Feedback, Message

router = APIRouter()

PAGE_DEFAULT = 50
PAGE_MAX = 100


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class QuestionLogEntry(_CamelModel):
    message_id: uuid.UUID  # the assistant message; also the feedback target
    question: str
    answer: str
    grounded: bool | None
    confidence: str | None
    rating: int | None  # feedback: +1 / -1 / null (unrated)
    created_at: datetime


class QuestionLogPage(_CamelModel):
    entries: list[QuestionLogEntry]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class UserMessage:
    session_id: uuid.UUID
    content: str
    created_at: datetime


def question_for(before: datetime, session_users: list[UserMessage]) -> str:
    """The latest of this session's user messages asked before the answer."""
    best: UserMessage | None = None
    for user in session_users:
        if user.created_at < before and (best is None or user.created_at > best.created_at):
            best = user
    return best.content if best is not None else ""


@router.get(
    "/admin/questions",
    dependencies=[Depends(require_internal_key), Depends(require_admin)],
)
async def list_questions(
    limit: int = Query(PAGE_DEFAULT, ge=1, le=PAGE_MAX),
    offset: int = Query(0, ge=0),
) -> QuestionLogPage:
    async with get_session_factory()() as session:
        total = (
            await session.execute(
                select(func.count()).select_from(Message).where(Message.role == "assistant")
            )
        ).scalar_one()

        answers = (
            await session.execute(
                select(Message, Feedback.rating)
                .outerjoin(Feedback, Feedback.message_id == Message.id)
                .where(Message.role == "assistant")
                .order_by(Message.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()

        session_ids = {answer.session_id for answer, _ in answers}
        # group the page's user messages by session, so pairing each answer is a
        # lookup into its own session's (small) list rather than a scan of every
        # user row across every session on the page
        users_by_session: dict[uuid.UUID, list[UserMessage]] = defaultdict(list)
        if session_ids:
            user_rows = (
                await session.execute(
                    select(Message.session_id, Message.content, Message.created_at).where(
                        Message.role == "user", Message.session_id.in_(session_ids)
                    )
                )
            ).all()
            for sid, content, created in user_rows:
                users_by_session[sid].append(UserMessage(sid, content, created))

    entries = [
        QuestionLogEntry(
            message_id=answer.id,
            question=question_for(answer.created_at, users_by_session[answer.session_id]),
            answer=answer.content,
            grounded=answer.grounded,
            confidence=answer.confidence,
            rating=rating,
            created_at=answer.created_at,
        )
        for answer, rating in answers
    ]
    return QuestionLogPage(entries=entries, total=total, limit=limit, offset=offset)
