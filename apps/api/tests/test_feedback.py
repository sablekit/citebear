"""Feedback endpoint: auth, request validation, camelCase parsing.

The happy-path upsert needs a real Postgres (SPEC §9 integration) and runs
against docker-compose / the golden DB; these cover what's reachable without one.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from citebear_api.app import app
from citebear_api.feedback import FeedbackRequest

INTERNAL_HEADER = {"X-Internal-Key": "test-internal-key"}  # matches conftest env


def test_feedback_parses_camelcase_and_valid_ratings() -> None:
    mid = uuid.uuid4()
    assert FeedbackRequest.model_validate({"messageId": str(mid), "rating": 1}).rating == 1
    assert FeedbackRequest.model_validate({"messageId": str(mid), "rating": -1}).rating == -1


@pytest.mark.parametrize("rating", [0, 2, -2, "up"])
def test_feedback_rejects_ratings_other_than_plus_minus_one(rating: object) -> None:
    with pytest.raises(ValidationError):
        FeedbackRequest.model_validate({"messageId": str(uuid.uuid4()), "rating": rating})


def test_feedback_requires_the_internal_key() -> None:
    # public but proxied: a request without the internal key is rejected
    client = TestClient(app)
    body = {"messageId": str(uuid.uuid4()), "rating": 1}
    response = client.post("/feedback", json=body)
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


def test_feedback_rejects_invalid_rating_over_http() -> None:
    # with a valid key, a bad rating is a 422 before the handler touches the DB
    client = TestClient(app)
    body = {"messageId": str(uuid.uuid4()), "rating": 5}
    response = client.post("/feedback", json=body, headers=INTERNAL_HEADER)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
