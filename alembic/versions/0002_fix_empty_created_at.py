"""Fix empty created_at strings in users and registration_codes tables

Revision ID: 0002_fix_empty_created_at
Revises: 0001_init
Create Date: 2026-02-21 00:00:00.000000
"""

from typing import Sequence, Union
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision: str = "0002_fix_empty_created_at"
down_revision: Union[str, Sequence[str], None] = "0001_init"
branch_labels = None
depends_on = None

_FALLBACK = "2026-01-01 00:00:00.000000"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE users SET created_at = :fallback WHERE created_at = '' OR created_at IS NULL"),
        {"fallback": _FALLBACK},
    )
    conn.execute(
        sa.text(
            "UPDATE registration_codes SET created_at = :fallback"
            " WHERE created_at = '' OR created_at IS NULL"
        ),
        {"fallback": _FALLBACK},
    )
    conn.execute(
        sa.text(
            "UPDATE registration_codes SET expires_at = :fallback"
            " WHERE expires_at = '' OR expires_at IS NULL"
        ),
        {"fallback": _FALLBACK},
    )


def downgrade() -> None:
    pass
