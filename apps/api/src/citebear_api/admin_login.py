"""Admin login (SPEC §6): verify the password and throttle brute force.

The web proxy delegates every attempt here so both the password check and the
per-IP lockout happen server-side against the Postgres counter (#56). Gated by
the internal key (proves it came from the proxy); the candidate password rides
in the body, not the Bearer header, because this is the check that mints it.
"""

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel

from citebear_api.auth import require_internal_key, verify_admin_password
from citebear_api.client_ip import hash_ip
from citebear_api.db import get_session_factory
from citebear_api.problems import problem_response
from citebear_api.rate_limit import (
    check_admin_login_rate_limit,
    record_admin_login_failure,
)

router = APIRouter()


class AdminLoginRequest(BaseModel):
    password: str


@router.post("/admin/login", dependencies=[Depends(require_internal_key)])
async def admin_login(request: Request, body: AdminLoginRequest) -> Response:
    client_ip = request.headers.get("x-client-ip")  # trusted: the key was validated
    ip_hash = hash_ip(client_ip) if client_ip else None
    session_factory = get_session_factory()

    if ip_hash is not None:
        state = await check_admin_login_rate_limit(session_factory, ip_hash)
        if not state.allowed:
            response = problem_response(
                429,
                "Too Many Requests",
                f"Too many failed logins. Try again in {state.retry_after} seconds.",
                retryAfter=state.retry_after,
            )
            response.headers["Retry-After"] = str(state.retry_after)
            return response

    if not verify_admin_password(body.password):
        # record the miss so repeated guesses from this IP trip the limiter
        if ip_hash is not None:
            await record_admin_login_failure(session_factory, ip_hash)
        return problem_response(401, "Unauthorized", "Incorrect admin password.")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
