"""Postgres-backed rate limiting (SPEC §6).

Counter state lives in Postgres — a windowed count over a table's created_at —
because an in-memory counter doesn't survive across serverless instances (no
Redis in v1). Two limiters share the shape:

- public chat: 20 requests / hour / IP, counted over user messages (refusals
  count, since every request writes a user row before it's answered);
- admin login: failed attempts / IP, counted over admin_login_attempts, to
  throttle brute force (#56).

Both limiters are check-then-act: they count already-committed rows, and the
admitted request's own row commits slightly later. A burst of concurrent
requests from one IP can therefore each read a stale count and slip past the
cap. This bounds the *sequential* rate (the common case) but not a concurrent
burst; airtight per-IP bounding (insert-before-count in one transaction, or a
pg advisory lock) is deferred — the residual exposure is capped by the AI
Gateway's prepaid credit for chat and by a strong admin password for login.
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import InstrumentedAttribute

from citebear_api.models import AdminLoginAttempt, Message

RATE_LIMIT_PER_HOUR = 20
RATE_WINDOW = timedelta(hours=1)

ADMIN_LOGIN_LIMIT = 10
ADMIN_LOGIN_WINDOW = timedelta(minutes=15)


@dataclass(frozen=True)
class RateLimitState:
    allowed: bool
    retry_after: int  # seconds to wait; meaningful only when not allowed


async def _windowed_count(
    session_factory: async_sessionmaker[AsyncSession],
    created_at: InstrumentedAttribute[datetime],
    conditions: list[ColumnElement[bool]],
    window: timedelta,
) -> tuple[int, datetime | None]:
    """Count rows matching ``conditions`` within ``window``, with the oldest.

    The window boundary is computed in the database (``now() - interval``) so the
    count doesn't drift with the app clock.
    """
    async with session_factory() as db:
        count, oldest = (
            await db.execute(
                select(func.count(), func.min(created_at)).where(
                    *conditions, created_at >= func.now() - window
                )
            )
        ).one()
    return count, oldest


def _decide(count: int, oldest: datetime | None, limit: int, window: timedelta) -> RateLimitState:
    # `oldest is None` only when count == 0, so it can't be None past this guard
    if count < limit or oldest is None:
        return RateLimitState(allowed=True, retry_after=0)
    # at the cap: the window frees a slot when its oldest entry ages out
    remaining = (oldest + window) - datetime.now(UTC)
    return RateLimitState(allowed=False, retry_after=max(1, math.ceil(remaining.total_seconds())))


async def check_chat_rate_limit(
    session_factory: async_sessionmaker[AsyncSession], ip_hash: str
) -> RateLimitState:
    count, oldest = await _windowed_count(
        session_factory,
        Message.created_at,
        [Message.ip_hash == ip_hash, Message.role == "user"],
        RATE_WINDOW,
    )
    return _decide(count, oldest, RATE_LIMIT_PER_HOUR, RATE_WINDOW)


async def check_admin_login_rate_limit(
    session_factory: async_sessionmaker[AsyncSession], ip_hash: str
) -> RateLimitState:
    count, oldest = await _windowed_count(
        session_factory,
        AdminLoginAttempt.created_at,
        [AdminLoginAttempt.ip_hash == ip_hash],
        ADMIN_LOGIN_WINDOW,
    )
    return _decide(count, oldest, ADMIN_LOGIN_LIMIT, ADMIN_LOGIN_WINDOW)


async def record_admin_login_failure(
    session_factory: async_sessionmaker[AsyncSession], ip_hash: str
) -> None:
    async with session_factory() as db:
        db.add(AdminLoginAttempt(ip_hash=ip_hash))
        await db.commit()
