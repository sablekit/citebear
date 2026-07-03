from fastapi.testclient import TestClient

from citebear_api.app import app
from citebear_api.db import get_session


class FakeSession:
    async def execute(self, statement: object) -> None:
        return None


async def override_get_session() -> FakeSession:
    return FakeSession()


def test_healthz_returns_ok() -> None:
    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    finally:
        app.dependency_overrides.clear()
