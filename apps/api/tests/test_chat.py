import json
from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from citebear_api.app import app
from citebear_api.chat import ChatEvent, ChatStream, ChatTurn, get_chat_stream

VALID_BODY = {"sessionId": "3f2f8f6a-1234-4abc-9def-000000000001", "message": "What is RRF?"}
KEY_HEADER = {"X-Internal-Key": "test-internal-key"}  # matches conftest env


def _fake_stream() -> tuple[ChatStream, list[ChatTurn]]:
    turns: list[ChatTurn] = []

    async def stream(turn: ChatTurn) -> AsyncIterator[ChatEvent]:
        turns.append(turn)
        yield ChatEvent("token", {"delta": "Reciprocal "})
        yield ChatEvent("token", {"delta": "Rank Fusion."})
        yield ChatEvent("done", {"messageId": "m-1", "grounded": True})

    return stream, turns


def _parse_sse(body: str) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    current_event = ""
    for line in body.splitlines():
        if line.startswith("event:"):
            current_event = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            events.append((current_event, json.loads(line.removeprefix("data:").strip())))
    return events


def test_chat_without_key_is_problem_401() -> None:
    client = TestClient(app)
    response = client.post("/chat", json=VALID_BODY)
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    payload = response.json()
    assert payload["status"] == 401
    assert payload["title"] == "Unauthorized"


def test_chat_with_wrong_key_is_401() -> None:
    client = TestClient(app)
    response = client.post("/chat", json=VALID_BODY, headers={"X-Internal-Key": "nope"})
    assert response.status_code == 401


def test_chat_validation_error_is_problem_422() -> None:
    client = TestClient(app)
    response = client.post("/chat", json={"sessionId": "not-a-uuid"}, headers=KEY_HEADER)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


def test_chat_streams_tokens_then_done() -> None:
    stream, _turns = _fake_stream()
    app.dependency_overrides[get_chat_stream] = lambda: stream
    try:
        client = TestClient(app)
        response = client.post("/chat", json=VALID_BODY, headers=KEY_HEADER)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        events = _parse_sse(response.text)
        assert [name for name, _ in events] == ["token", "token", "done"]
        assert events[0][1] == {"delta": "Reciprocal "}
        assert events[-1][1] == {"messageId": "m-1", "grounded": True}
    finally:
        app.dependency_overrides.clear()


def test_chat_passes_session_and_hashed_ip_to_pipeline() -> None:
    stream, turns = _fake_stream()
    app.dependency_overrides[get_chat_stream] = lambda: stream
    try:
        client = TestClient(app)
        client.post(
            "/chat",
            json=VALID_BODY,
            headers=KEY_HEADER | {"X-Client-IP": "203.0.113.7"},
        )
        assert len(turns) == 1
        assert str(turns[0].session_id) == VALID_BODY["sessionId"]
        assert turns[0].message == VALID_BODY["message"]
        ip_hash = turns[0].ip_hash
        assert ip_hash is not None and len(ip_hash) == 64
        assert "203.0.113.7" not in ip_hash
    finally:
        app.dependency_overrides.clear()
