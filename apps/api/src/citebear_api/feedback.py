"""Feedback endpoint (SPEC §6): 👍/👎 on an assistant answer.

Public (internal-key only), like /chat: the browser submits through the web
proxy. One rating per message — the PK upsert makes a repeat vote an overwrite,
so a visitor can flip or correct their rating without stacking duplicates.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from citebear_api.auth import require_internal_key
from citebear_api.db import get_session_factory
from citebear_api.models import Feedback

router = APIRouter()


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    message_id: uuid.UUID
    rating: Literal[1, -1]  # anything else is a 422 before the handler runs


@router.post(
    "/feedback",
    dependencies=[Depends(require_internal_key)],
    status_code=status.HTTP_204_NO_CONTENT,
)
async def submit_feedback(body: FeedbackRequest) -> Response:
    stmt = (
        insert(Feedback)
        .values(message_id=body.message_id, rating=body.rating)
        # re-rating the same message overwrites in place (idempotent)
        .on_conflict_do_update(index_elements=["message_id"], set_={"rating": body.rating})
    )
    try:
        async with get_session_factory()() as session:
            await session.execute(stmt)
            await session.commit()
    except IntegrityError as exc:
        # the message_id FK doesn't resolve: rating an answer that doesn't exist
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Message not found"
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
