"""baseline

Revision ID: 74a640a96e92
Revises:
Create Date: 2026-02-14 20:44:17.759745

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '74a640a96e92'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("username", sa.String(), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role", sa.Enum("admin", "user", name="userrole"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "registration_codes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("code", sa.String(), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("used_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_registration_codes_code", "registration_codes", ["code"])

    op.create_table(
        "miner_instances",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("twitch_username", sa.String(), nullable=False),
        sa.Column("is_running", sa.Boolean(), default=False),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("last_started_at", sa.DateTime(), nullable=True),
        sa.Column("last_stopped_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("miner_instances")
    op.drop_table("registration_codes")
    op.drop_table("users")
