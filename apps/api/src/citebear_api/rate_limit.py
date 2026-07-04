"""Public chat rate limiting (SPEC §6): 20 requests / hour / IP.

Counter state lives in Postgres — a count of user messages by ip_hash over the
trailing hour — because an in-memory counter doesn't survive across serverless
instances (no Redis in v1). Refusals still count: every chat request writes a
user row before we know whether it will be answered or refused.
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from citebear_api.models import Message

RATE_LIMIT_PER_HOUR = 20
RATE_WINDOW = timedelta(hours=1)


@dataclass(frozen=True)
class RateLimitState:
    allowed: bool
    retry_after: int  # seconds to wait; meaningful only when not allowed


async def check_chat_rate_limit(
    session_factory: async_sessionmaker[AsyncSession], ip_hash: str
) -> RateLimitState:
    """Count this IP's requests in the trailing hour and decide if one more fits.

    The window boundary is computed in the database (`now() - interval`) so the
    count doesn't drift with the app clock.
    """
    async with session_factory() as db:
        count, oldest = (
            await db.execute(
                select(func.count(), func.min(Message.created_at)).where(
                    Message.ip_hash == ip_hash,
                    Message.role == "user",
                    Message.created_at >= func.now() - RATE_WINDOW,
                )
            )
        ).one()

    # `oldest is None` only when count == 0, so it can't be None past this guard
    if count < RATE_LIMIT_PER_HOUR or oldest is None:
        return RateLimitState(allowed=True, retry_after=0)

    # at the cap: the window frees a slot when its oldest request ages out
    remaining = (oldest + RATE_WINDOW) - datetime.now(UTC)
    return RateLimitState(allowed=False, retry_after=max(1, math.ceil(remaining.total_seconds())))
