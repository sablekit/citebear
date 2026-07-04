"""check_chat_rate_limit decision logic, with the count query mocked.

The api CI job has no Postgres, so the SQL itself is exercised by the golden
workflow DB; here we pin the allow/deny + retry-after arithmetic.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from citebear_api.models import AdminLoginAttempt
from citebear_api.rate_limit import (
    ADMIN_LOGIN_LIMIT,
    RATE_LIMIT_PER_HOUR,
    RATE_WINDOW,
    RateLimitState,
    check_admin_login_rate_limit,
    check_chat_rate_limit,
    record_admin_login_failure,
)


class _FakeResult:
    def __init__(self, row: tuple[int, datetime | None]) -> None:
        self._row = row

    def one(self) -> tuple[int, datetime | None]:
        return self._row


class _FakeSession:
    def __init__(self, row: tuple[int, datetime | None], added: list[object]) -> None:
        self._row = row
        self._added = added

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False

    async def execute(self, *_: object, **__: object) -> _FakeResult:
        return _FakeResult(self._row)

    def add(self, obj: object) -> None:
        self._added.append(obj)

    async def commit(self) -> None:
        return None


def _factory(row: tuple[int, datetime | None], added: list[object] | None = None) -> Any:
    # typed Any so the fake stands in for async_sessionmaker without cast noise
    return lambda: _FakeSession(row, added if added is not None else [])


def _check(row: tuple[int, datetime | None]) -> RateLimitState:
    return asyncio.run(check_chat_rate_limit(_factory(row), "ip-hash"))


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


def test_admin_login_limiter_denies_at_its_own_threshold() -> None:
    # under the (separate, smaller) admin-login cap → allowed
    under = asyncio.run(
        check_admin_login_rate_limit(_factory((ADMIN_LOGIN_LIMIT - 1, datetime.now(UTC))), "ip")
    )
    assert under.allowed is True
    # at the cap → denied
    over = asyncio.run(
        check_admin_login_rate_limit(
            _factory((ADMIN_LOGIN_LIMIT, datetime.now(UTC) - timedelta(minutes=1))), "ip"
        )
    )
    assert over.allowed is False


def test_record_admin_login_failure_inserts_one_row() -> None:
    added: list[object] = []
    asyncio.run(record_admin_login_failure(_factory((0, None), added), "ip-hash"))
    assert len(added) == 1
    attempt = added[0]
    assert isinstance(attempt, AdminLoginAttempt)
    assert attempt.ip_hash == "ip-hash"
