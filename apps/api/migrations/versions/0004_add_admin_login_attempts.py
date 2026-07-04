"""admin_login_attempts: per-IP failed admin logins, for throttling

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_login_attempts",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("ip_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_admin_login_attempts_ip_hash_created_at",
        "admin_login_attempts",
        ["ip_hash", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_admin_login_attempts_ip_hash_created_at", table_name="admin_login_attempts")
    op.drop_table("admin_login_attempts")
