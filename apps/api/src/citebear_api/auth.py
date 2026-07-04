"""Admin authentication (SPEC §6).

Admin routes require `Authorization: Bearer <ADMIN_PASSWORD>`. The web app
stores the password in an httpOnly cookie and forwards it through its proxy;
the browser never calls the Python API directly.
"""

import hmac
from typing import Annotated

from fastapi import Header, HTTPException

from citebear_api.config import get_settings

_BEARER_PREFIX = "Bearer "


def require_admin(authorization: Annotated[str | None, Header()] = None) -> None:
    """Reject requests without a valid admin bearer token.

    A single 401 covers both a missing and a wrong credential — leaking which
    one it is only helps a guesser. The compare is constant-time.
    """
    expected = get_settings().admin_password
    token = (
        authorization[len(_BEARER_PREFIX) :]
        if authorization and authorization.startswith(_BEARER_PREFIX)
        else ""
    )
    if not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Missing or invalid admin credentials")
