"""Authentication (SPEC §6).

Two gates the web proxy passes: `require_internal_key` proves the request came
from the Next.js proxy (the API origin is public, so this key is what keeps it
effectively private — every proxied request carries it), and `require_admin`
proves admin identity via `Authorization: Bearer <ADMIN_PASSWORD>`. Admin
routes require both; the browser never calls the Python API directly.
"""

import hmac
from typing import Annotated

from fastapi import Header, HTTPException

from citebear_api.config import get_settings

_BEARER_PREFIX = "Bearer "


def require_internal_key(x_internal_key: Annotated[str | None, Header()] = None) -> None:
    """Reject requests that did not come through the web proxy."""
    expected = get_settings().internal_api_key
    if x_internal_key is None or not hmac.compare_digest(
        x_internal_key.encode(), expected.encode()
    ):
        raise HTTPException(status_code=401, detail="Missing or invalid internal API key")


def verify_admin_password(candidate: str) -> bool:
    """Constant-time check of a candidate against the admin password."""
    return hmac.compare_digest(candidate.encode(), get_settings().admin_password.encode())


def require_admin(authorization: Annotated[str | None, Header()] = None) -> None:
    """Reject requests without a valid admin bearer token.

    A single 401 covers both a missing and a wrong credential — leaking which
    one it is only helps a guesser. The compare is constant-time.
    """
    token = (
        authorization[len(_BEARER_PREFIX) :]
        if authorization and authorization.startswith(_BEARER_PREFIX)
        else ""
    )
    if not verify_admin_password(token):
        raise HTTPException(status_code=401, detail="Missing or invalid admin credentials")
