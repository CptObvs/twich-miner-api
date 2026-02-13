"""replace is_running with status enum

Revision ID: a1b2c3d4e5f6
Revises: 8ff7b5bf58a6
Create Date: 2026-02-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '8ff7b5bf58a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite requires batch mode for ALTER TABLE
    with op.batch_alter_table("miner_instances") as batch_op:
        # Add the new status column with default 'stopped'
        batch_op.add_column(
            sa.Column("status", sa.String(), nullable=False, server_default="stopped")
        )

    # Migrate existing data: is_running=True -> 'running', is_running=False -> 'stopped'
    op.execute(
        "UPDATE miner_instances SET status = CASE "
        "WHEN is_running = 1 THEN 'running' "
        "ELSE 'stopped' END"
    )

    # Drop the old is_running column
    with op.batch_alter_table("miner_instances") as batch_op:
        batch_op.drop_column("is_running")


def downgrade() -> None:
    with op.batch_alter_table("miner_instances") as batch_op:
        batch_op.add_column(
            sa.Column("is_running", sa.Boolean(), default=False)
        )

    # Migrate back: 'running' -> True, everything else -> False
    op.execute(
        "UPDATE miner_instances SET is_running = CASE "
        "WHEN status = 'running' THEN 1 "
        "ELSE 0 END"
    )

    with op.batch_alter_table("miner_instances") as batch_op:
        batch_op.drop_column("status")
