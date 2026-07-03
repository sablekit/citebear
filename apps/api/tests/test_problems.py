from fastapi import FastAPI
from fastapi.testclient import TestClient

from citebear_api.problems import install_problem_handlers


def _app_with_failing_route() -> FastAPI:
    app = FastAPI()
    install_problem_handlers(app)

    @app.get("/boom")
    def boom() -> None:  # pyright: ignore[reportUnusedFunction] — registered via decorator
        raise RuntimeError("secret internals")

    return app


def test_unhandled_exception_is_problem_json() -> None:
    client = TestClient(_app_with_failing_route(), raise_server_exceptions=False)
    response = client.get("/boom")
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    payload = response.json()
    assert payload == {"type": "about:blank", "title": "Internal Server Error", "status": 500}
    assert "secret internals" not in response.text
