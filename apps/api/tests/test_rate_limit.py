"""check_chat_rate_limit decision logic, with the count query mocked.

The api CI job has no Postgres, so the SQL itself is exercised by the golden
workflow DB; here we pin the allow/deny + retry-after arithmetic.
"""

import asyncio
from datetime import UTC, datetime, timedelta

from citebear_api.rate_limit import (
    RATE_LIMIT_PER_HOUR,
    RATE_WINDOW,
    RateLimitState,
    check_chat_rate_limit,
)


class _FakeResult:
    def __init__(self, row: tuple[int, datetime | None]) -> None:
        self._row = row

    def one(self) -> tuple[int, datetime | None]:
        return self._row


class _FakeSession:
    def __init__(self, row: tuple[int, datetime | None]) -> None:
        self._row = row

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False

    async def execute(self, *_: object, **__: object) -> _FakeResult:
        return _FakeResult(self._row)


def _factory(row: tuple[int, datetime | None]) -> object:
    return lambda: _FakeSession(row)


def _check(row: tuple[int, datetime | None]) -> RateLimitState:
    return asyncio.run(check_chat_rate_limit(_factory(row), "ip-hash"))  # type: ignore[arg-type]


def test_under_limit_is_allowed() -> None:
    state = _check((5, datetime.now(UTC) - timedelta(minutes=10)))
    assert state.allowed is True
    assert state.retry_after == 0


def test_no_requests_is_allowed() -> None:
    # count 0 -> min() is NULL; must not blow up on the None
    state = _check((0, None))
    assert state.allowed is True


def test_at_limit_is_denied_with_retry_after() -> None:
    # oldest request was 30 min ago; the slot frees ~30 min from now
    oldest = datetime.now(UTC) - timedelta(minutes=30)
    state = _check((RATE_LIMIT_PER_HOUR, oldest))
    assert state.allowed is False
    expected = int((RATE_WINDOW - timedelta(minutes=30)).total_seconds())
    assert expected - 2 <= state.retry_after <= expected + 1  # ~1800s, allow tiny clock drift


def test_retry_after_is_at_least_one_second() -> None:
    # oldest already at the window edge: never advertise a 0s (or negative) wait
    oldest = datetime.now(UTC) - RATE_WINDOW
    state = _check((RATE_LIMIT_PER_HOUR, oldest))
    assert state.allowed is False
    assert state.retry_after >= 1
