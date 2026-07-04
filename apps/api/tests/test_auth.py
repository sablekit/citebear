import pytest
from fastapi import HTTPException

from citebear_api.auth import require_admin

# matches ADMIN_PASSWORD in conftest env
VALID = "Bearer test-admin-password"


def test_require_admin_accepts_valid_bearer() -> None:
    require_admin(VALID)  # does not raise


@pytest.mark.parametrize(
    "header",
    [
        None,  # missing
        "test-admin-password",  # no scheme
        "Bearer wrong-password",  # wrong secret
        "Basic test-admin-password",  # wrong scheme
        "Bearer ",  # empty token
    ],
)
def test_require_admin_rejects(header: str | None) -> None:
    with pytest.raises(HTTPException) as exc:
        require_admin(header)
    assert exc.value.status_code == 401
