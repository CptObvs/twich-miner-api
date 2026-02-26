"""Add connected_ips table for IP tracking

Revision ID: 0005_connected_ips
Revises: 0004_banned_ips
Create Date: 2026-02-26 00:00:00.000000
"""

from alembic import op

revision = "0005_connected_ips"
down_revision = "0004_banned_ips"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS connected_ips (
            ip_address TEXT NOT NULL,
            country TEXT,
            country_code TEXT,
            first_seen DATETIME NOT NULL,
            last_seen DATETIME NOT NULL,
            request_count INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (ip_address)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS connected_ips")
