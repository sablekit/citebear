"""RFC 9457 Problem Details (SPEC §6): every non-2xx response is
application/problem+json; SSE error events carry the same fields."""

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_MEDIA_TYPE = "application/problem+json"


def problem(
    status: int,
    title: str,
    detail: str | None = None,
    type_: str = "about:blank",
    **extensions: Any,
) -> dict[str, Any]:
    body: dict[str, Any] = {"type": type_, "title": title, "status": status}
    if detail is not None:
        body["detail"] = detail
    body.update(extensions)
    return body


def problem_response(
    status: int,
    title: str,
    detail: str | None = None,
    **extensions: Any,
) -> JSONResponse:
    return JSONResponse(
        problem(status, title, detail, **extensions),
        status_code=status,
        media_type=PROBLEM_MEDIA_TYPE,
    )


async def _http_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    title = HTTPStatus(exc.status_code).phrase
    detail = exc.detail if exc.detail != title else None
    return problem_response(exc.status_code, title, detail)


async def _validation_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return problem_response(422, "Unprocessable Entity", str(exc))


def install_problem_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
