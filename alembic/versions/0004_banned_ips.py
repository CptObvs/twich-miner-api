"""Add banned_ips table for IP ban service

Revision ID: 0004_banned_ips
Revises: 0003_v2_docker
Create Date: 2026-02-26 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_banned_ips"
down_revision = "0003_v2_docker"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS banned_ips (
            id TEXT NOT NULL,
            ip_address TEXT NOT NULL,
            banned_at DATETIME NOT NULL,
            banned_until DATETIME NOT NULL,
            hit_count INTEGER NOT NULL,
            PRIMARY KEY (id),
            UNIQUE (ip_address)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS banned_ips")
