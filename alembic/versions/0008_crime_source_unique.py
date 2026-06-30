"""crime source composite unique

Revision ID: 0008_crime_source_unique
Revises: 0007_geocode_cache
Create Date: 2026-06-29 21:29:38.547580
"""
from __future__ import annotations

from alembic import op

revision = "0008_crime_source_unique"
down_revision = "0007_geocode_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_crime_incidents_source_dataset", "crime_incidents", ["source_dataset"]
    )
    # The composite uniqueness must be created differently per backend: SQLite cannot
    # ALTER ... ADD CONSTRAINT (nor DROP the inline single-column unique from 0001) without a
    # table rebuild, but CREATE UNIQUE INDEX is portable. The repo's migration tests run the
    # whole chain on SQLite, so the SQLite branch must run cleanly; Postgres (prod) gets the
    # real UniqueConstraint that matches the model and drops the old single-column unique.
    if op.get_bind().dialect.name == "sqlite":
        op.create_index(
            "uq_crime_source_external_id",
            "crime_incidents",
            ["source_dataset", "external_incident_id"],
            unique=True,
        )
    else:
        op.create_unique_constraint(
            "uq_crime_source_external_id",
            "crime_incidents",
            ["source_dataset", "external_incident_id"],
        )
        # 0001 created this via inline unique=True; on Postgres its auto name is
        # crime_incidents_external_incident_id_key.
        op.drop_constraint(
            "crime_incidents_external_incident_id_key", "crime_incidents", type_="unique"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.drop_index("uq_crime_source_external_id", table_name="crime_incidents")
    else:
        op.create_unique_constraint(
            "crime_incidents_external_incident_id_key",
            "crime_incidents",
            ["external_incident_id"],
        )
        op.drop_constraint(
            "uq_crime_source_external_id", "crime_incidents", type_="unique"
        )
    op.drop_index("ix_crime_incidents_source_dataset", table_name="crime_incidents")
