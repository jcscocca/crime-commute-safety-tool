"""layer column on route requests

Revision ID: 0010_route_layer
Revises: 0009_summary_layer
Create Date: 2026-06-30 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0010_route_layer"
down_revision = "0009_summary_layer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("route_requests", sa.Column("layer", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("route_requests", "layer")
