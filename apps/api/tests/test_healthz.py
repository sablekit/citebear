from fastapi.testclient import TestClient

from citebear_api.app import app

client = TestClient(app)


def test_healthz_returns_ok() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_synthetic_load_completes() -> None:
    response = client.get("/_internal/synthetic-load", params={"seconds": 1})
    assert response.status_code == 200
    assert "done requested=1s" in response.text
