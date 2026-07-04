"""Question log: pairing logic, camelCase serialization, admin auth.

The paged query needs a real Postgres (SPEC §9 integration) and runs against
docker-compose / the golden DB; these cover what's reachable without one.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from citebear_api.app import app
from citebear_api.questions import QuestionLogEntry, UserMessage, question_for

INTERNAL_HEADER = {"X-Internal-Key": "test-internal-key"}
BEARER_HEADER = {"Authorization": "Bearer test-admin-password"}


def _user(session_id: uuid.UUID, content: str, minutes_ago: int) -> UserMessage:
    return UserMessage(session_id, content, datetime.now(UTC) - timedelta(minutes=minutes_ago))


def test_question_for_picks_latest_user_before_the_answer() -> None:
    sid = uuid.uuid4()
    answer_at = datetime.now(UTC)
    session_users = [
        _user(sid, "first question", minutes_ago=20),
        _user(sid, "second question", minutes_ago=5),  # the most recent before the answer
    ]
    assert question_for(answer_at, session_users) == "second question"


def test_question_for_ignores_users_after_the_answer() -> None:
    sid = uuid.uuid4()
    answer_at = datetime.now(UTC) - timedelta(minutes=10)
    # the caller groups by session, so question_for only sees this session's
    # users; a user message created after the answer is not its prompt
    session_users = [_user(sid, "after the answer", minutes_ago=1)]
    assert question_for(answer_at, session_users) == ""


def test_entry_serializes_camelcase() -> None:
    payload = QuestionLogEntry(
        message_id=uuid.uuid4(),
        question="q",
        answer="a",
        grounded=True,
        confidence="high",
        rating=-1,
        created_at=datetime.now(UTC),
    ).model_dump(by_alias=True)
    assert set(payload) >= {"messageId", "createdAt", "grounded", "confidence", "rating"}
    assert payload["rating"] == -1


def test_questions_requires_admin_and_internal_key() -> None:
    client = TestClient(app)
    assert client.get("/admin/questions").status_code == 401
    # internal key alone (a chat visitor) must not reach the admin log
    assert client.get("/admin/questions", headers=INTERNAL_HEADER).status_code == 401
