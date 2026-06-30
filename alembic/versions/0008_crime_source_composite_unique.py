"""crime source composite unique

Revision ID: 0008_crime_source_composite_unique
Revises: 0007_geocode_cache
Create Date: 2026-06-29 21:29:38.547580
"""
from __future__ import annotations

from alembic import op

revision = "0008_crime_source_composite_unique"
down_revision = "0007_geocode_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Old single-column unique was created inline (unique=True) in 0001; on Postgres its
    # auto name is crime_incidents_external_incident_id_key. Replace with the composite.
    op.drop_constraint(
        "crime_incidents_external_incident_id_key", "crime_incidents", type_="unique"
    )
    op.create_unique_constraint(
        "uq_crime_source_external_id",
        "crime_incidents",
        ["source_dataset", "external_incident_id"],
    )
    op.create_index(
        "ix_crime_incidents_source_dataset", "crime_incidents", ["source_dataset"]
    )


def downgrade() -> None:
    op.drop_index("ix_crime_incidents_source_dataset", table_name="crime_incidents")
    op.drop_constraint("uq_crime_source_external_id", "crime_incidents", type_="unique")
    op.create_unique_constraint(
        "crime_incidents_external_incident_id_key",
        "crime_incidents",
        ["external_incident_id"],
    )
