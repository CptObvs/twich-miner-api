"""V2 Docker migration: drop subprocess fields, normalize miner_type values

- Removes pid, enable_analytics, analytics_port (V2 now runs as Docker container)
- Normalizes miner_type column to enum values (docker/subprocess) in case any
  rows were written with enum names (TwitchDropsMiner/TwitchDropsMinerV2)

Revision ID: 0003_v2_docker
Revises: 0002_add_miner_type
Create Date: 2026-02-24 00:00:00.000000
"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0003_v2_docker"
down_revision: Union[str, Sequence[str], None] = "0002_add_miner_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("miner_instances", "pid")
    op.drop_column("miner_instances", "enable_analytics")
    op.drop_column("miner_instances", "analytics_port")

def downgrade() -> None:
    op.add_column("miner_instances", sa.Column("analytics_port", sa.Integer(), nullable=True))
    op.add_column("miner_instances", sa.Column("enable_analytics", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column("miner_instances", sa.Column("pid", sa.Integer(), nullable=True))
