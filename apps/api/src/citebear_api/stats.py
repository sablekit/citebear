"""Admin stats (SPEC §6, §7): GET /admin/stats.

Aggregate counters for the Stats tab — questions asked, 👍/👎 totals, refusal
rate, and document count — computed with conditional aggregates so messages need
only one pass. Simple cards, no time series.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import func, select

from citebear_api.auth import require_admin, require_internal_key
from citebear_api.db import get_session_factory
from citebear_api.models import Document, Feedback, Message

router = APIRouter()


class AdminStats(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    total_questions: int
    thumbs_up: int
    thumbs_down: int
    refusal_rate: float  # refused answers / answers, 0..1
    documents: int


def refusal_rate(refusals: int, answers: int) -> float:
    """Share of answered turns that were refusals; 0 when nothing was asked."""
    return round(refusals / answers, 4) if answers else 0.0


@router.get(
    "/admin/stats",
    dependencies=[Depends(require_internal_key), Depends(require_admin)],
)
async def get_stats() -> AdminStats:
    async with get_session_factory()() as session:
        questions, answers, refusals = (
            await session.execute(
                select(
                    func.count().filter(Message.role == "user"),
                    func.count().filter(Message.role == "assistant"),
                    func.count().filter(
                        (Message.role == "assistant") & Message.grounded.is_(False)
                    ),
                )
            )
        ).one()

        thumbs_up, thumbs_down = (
            await session.execute(
                select(
                    func.count().filter(Feedback.rating == 1),
                    func.count().filter(Feedback.rating == -1),
                )
            )
        ).one()

        documents = (await session.execute(select(func.count()).select_from(Document))).scalar_one()

    return AdminStats(
        total_questions=questions,
        thumbs_up=thumbs_up,
        thumbs_down=thumbs_down,
        refusal_rate=refusal_rate(refusals, answers),
        documents=documents,
    )
