"""layer column on analysis runs and place crime summaries

Revision ID: 0009_summary_layer
Revises: 0008_crime_source_unique
Create Date: 2026-06-30 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0009_summary_layer"
down_revision = "0008_crime_source_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable add is portable on both SQLite and Postgres; existing rows stay null and are
    # read as the "reported" layer.
    op.add_column("analysis_runs", sa.Column("layer", sa.Text(), nullable=True))
    op.add_column("place_crime_summaries", sa.Column("layer", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("place_crime_summaries", "layer")
    op.drop_column("analysis_runs", "layer")
