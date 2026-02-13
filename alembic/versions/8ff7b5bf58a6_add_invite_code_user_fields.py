"""add invite code user fields

Revision ID: 8ff7b5bf58a6
Revises: 74a640a96e92
Create Date: 2026-02-14 20:44:24.454324

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8ff7b5bf58a6'
down_revision: Union[str, Sequence[str], None] = '74a640a96e92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite requires batch mode for ALTER TABLE
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("max_invite_codes", sa.Integer(), nullable=False, server_default="2")
        )

    with op.batch_alter_table("registration_codes") as batch_op:
        batch_op.add_column(
            sa.Column("created_by", sa.String(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_registration_codes_created_by",
            "users",
            ["created_by"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("registration_codes") as batch_op:
        batch_op.drop_constraint("fk_registration_codes_created_by", type_="foreignkey")
        batch_op.drop_column("created_by")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("max_invite_codes")
