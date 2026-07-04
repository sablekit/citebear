"""Admin stats: refusal-rate math, camelCase serialization, admin auth.

The aggregate query needs a real Postgres (SPEC §9 integration) and runs against
docker-compose / the golden DB; these cover what's reachable without one.
"""

from fastapi.testclient import TestClient

from citebear_api.app import app
from citebear_api.stats import AdminStats, refusal_rate

INTERNAL_HEADER = {"X-Internal-Key": "test-internal-key"}


def test_refusal_rate_is_share_of_answers() -> None:
    assert refusal_rate(3, 12) == 0.25
    assert refusal_rate(0, 5) == 0.0


def test_refusal_rate_is_zero_when_nothing_asked() -> None:
    # no answers must not divide by zero
    assert refusal_rate(0, 0) == 0.0


def test_stats_serializes_camelcase() -> None:
    payload = AdminStats(
        total_questions=10,
        thumbs_up=4,
        thumbs_down=1,
        refusal_rate=0.2,
        documents=3,
    ).model_dump(by_alias=True)
    assert set(payload) == {
        "totalQuestions",
        "thumbsUp",
        "thumbsDown",
        "refusalRate",
        "documents",
    }


def test_stats_requires_admin_and_internal_key() -> None:
    client = TestClient(app)
    assert client.get("/admin/stats").status_code == 401
    # internal key alone (a chat visitor) must not reach the admin stats
    assert client.get("/admin/stats", headers=INTERNAL_HEADER).status_code == 401
