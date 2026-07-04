"""Admin login endpoint: internal-key gate, password check, throttle wiring.

The Postgres-backed counter is exercised by the golden workflow DB; here the
rate-limit + record calls are monkeypatched so the reachable-without-DB branches
(no client IP) and the throttled/failure branches are pinned.
"""

import pytest
from fastapi.testclient import TestClient

from citebear_api import admin_login
from citebear_api.app import app
from citebear_api.rate_limit import RateLimitState

INTERNAL_HEADER = {"X-Internal-Key": "test-internal-key"}  # matches conftest env
IP_HEADER = {"X-Client-IP": "203.0.113.7"}
GOOD = {"password": "test-admin-password"}  # matches conftest env
BAD = {"password": "wrong"}


def test_login_requires_the_internal_key() -> None:
    client = TestClient(app)
    response = client.post("/admin/login", json=GOOD)
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


def test_correct_password_without_ip_succeeds() -> None:
    # no client IP (local dev): throttle is skipped, so no DB is touched
    client = TestClient(app)
    response = client.post("/admin/login", json=GOOD, headers=INTERNAL_HEADER)
    assert response.status_code == 204


def test_wrong_password_without_ip_is_401_and_records_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[str] = []

    async def spy_record(_factory: object, ip_hash: str) -> None:
        recorded.append(ip_hash)

    monkeypatch.setattr(admin_login, "record_admin_login_failure", spy_record)

    client = TestClient(app)
    response = client.post("/admin/login", json=BAD, headers=INTERNAL_HEADER)
    assert response.status_code == 401
    # without a client IP there's no bucket to attribute the miss to
    assert recorded == []


def test_wrong_password_with_ip_records_the_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[str] = []

    async def allow(_factory: object, _ip_hash: str) -> RateLimitState:
        return RateLimitState(allowed=True, retry_after=0)

    async def spy_record(_factory: object, ip_hash: str) -> None:
        recorded.append(ip_hash)

    monkeypatch.setattr(admin_login, "check_admin_login_rate_limit", allow)
    monkeypatch.setattr(admin_login, "record_admin_login_failure", spy_record)

    client = TestClient(app)
    response = client.post("/admin/login", json=BAD, headers=INTERNAL_HEADER | IP_HEADER)
    assert response.status_code == 401
    assert len(recorded) == 1 and len(recorded[0]) == 64  # the hashed IP


def test_over_limit_is_429_before_checking_password(monkeypatch: pytest.MonkeyPatch) -> None:
    async def deny(_factory: object, _ip_hash: str) -> RateLimitState:
        return RateLimitState(allowed=False, retry_after=99)

    async def explode_record(_factory: object, _ip_hash: str) -> None:
        raise AssertionError("must not record while already throttled")

    monkeypatch.setattr(admin_login, "check_admin_login_rate_limit", deny)
    monkeypatch.setattr(admin_login, "record_admin_login_failure", explode_record)

    client = TestClient(app)
    # even a correct password is refused while the IP is locked out
    response = client.post("/admin/login", json=GOOD, headers=INTERNAL_HEADER | IP_HEADER)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "99"
    assert response.json()["retryAfter"] == 99
