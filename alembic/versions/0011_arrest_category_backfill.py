"""backfill arrest offense_category / nibrs_group from the NIBRS crosswalk

Revision ID: 0011_arrest_category_backfill
Revises: 0010_route_layer
Create Date: 2026-07-02 00:00:00.000000
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

from alembic import op

revision = "0011_arrest_category_backfill"
down_revision = "0010_route_layer"
branch_labels = None
depends_on = None

# Self-contained snapshot of app/crime/nibrs_crosswalk.py::NIBRS_CROSSWALK at authoring time
# (migrations are immutable; do not import app code).
_CROSSWALK: dict[str, tuple[str, str]] = {
    # --- Group A · Crime Against PERSON ---
    "murder & nonnegligent manslaughter": ("PERSON", "A"),
    "negligent manslaughter": ("PERSON", "A"),
    "justifiable homicide": ("PERSON", "A"),
    "kidnapping/abduction": ("PERSON", "A"),
    "rape": ("PERSON", "A"),
    "sodomy": ("PERSON", "A"),
    "sexual assault with an object": ("PERSON", "A"),
    "fondling": ("PERSON", "A"),
    "incest": ("PERSON", "A"),
    "statutory rape": ("PERSON", "A"),
    "aggravated assault": ("PERSON", "A"),
    "simple assault": ("PERSON", "A"),
    "intimidation": ("PERSON", "A"),
    "human trafficking, commercial sex acts": ("PERSON", "A"),
    "human trafficking, involuntary servitude": ("PERSON", "A"),
    # --- Group A · Crime Against PROPERTY ---
    "arson": ("PROPERTY", "A"),
    "bribery": ("PROPERTY", "A"),
    "burglary/breaking & entering": ("PROPERTY", "A"),
    "counterfeiting/forgery": ("PROPERTY", "A"),
    "destruction/damage/vandalism": ("PROPERTY", "A"),
    "destruction/damage/vandalism of property": ("PROPERTY", "A"),
    "embezzlement": ("PROPERTY", "A"),
    "extortion/blackmail": ("PROPERTY", "A"),
    "false pretenses/swindle/confidence game": ("PROPERTY", "A"),
    "credit card/automated teller machine fraud": ("PROPERTY", "A"),
    "impersonation": ("PROPERTY", "A"),
    "welfare fraud": ("PROPERTY", "A"),
    "wire fraud": ("PROPERTY", "A"),
    "identity theft": ("PROPERTY", "A"),
    "hacking/computer invasion": ("PROPERTY", "A"),
    "money laundering": ("PROPERTY", "A"),
    "robbery": ("PROPERTY", "A"),
    "pocket-picking": ("PROPERTY", "A"),
    "purse-snatching": ("PROPERTY", "A"),
    "shoplifting": ("PROPERTY", "A"),
    "theft from building": ("PROPERTY", "A"),
    "theft from coin-operated machine or device": ("PROPERTY", "A"),
    "theft from motor vehicle": ("PROPERTY", "A"),
    "theft of motor vehicle parts or accessories": ("PROPERTY", "A"),
    "all other larceny": ("PROPERTY", "A"),
    "motor vehicle theft": ("PROPERTY", "A"),
    "stolen property offenses": ("PROPERTY", "A"),
    # --- Group A · Crime Against SOCIETY ---
    "drug/narcotic violations": ("SOCIETY", "A"),
    "drug equipment violations": ("SOCIETY", "A"),
    "betting/wagering": ("SOCIETY", "A"),
    "operating/promoting/assisting gambling": ("SOCIETY", "A"),
    "gambling equipment violations": ("SOCIETY", "A"),
    "sports tampering": ("SOCIETY", "A"),
    "pornography/obscene material": ("SOCIETY", "A"),
    "prostitution": ("SOCIETY", "A"),
    "assisting or promoting prostitution": ("SOCIETY", "A"),
    "purchasing prostitution": ("SOCIETY", "A"),
    "weapon law violations": ("SOCIETY", "A"),
    "animal cruelty": ("SOCIETY", "A"),
    # --- Group B (arrest-only) · best-effort ---
    "bad checks": ("PROPERTY", "B"),
    "curfew/loitering/vagrancy violations": ("SOCIETY", "B"),
    "disorderly conduct": ("SOCIETY", "B"),
    "driving under the influence": ("SOCIETY", "B"),
    "drunkenness": ("SOCIETY", "B"),
    "family offenses, nonviolent": ("PERSON", "B"),
    "liquor law violations": ("SOCIETY", "B"),
    "peeping tom": ("PERSON", "B"),
    "trespass of real property": ("PROPERTY", "B"),
    "all other offenses": ("SOCIETY", "B"),
}

_UPDATE = text(
    "UPDATE crime_incidents SET offense_category = :cat, nibrs_group = :grp "
    "WHERE source_dataset = 'seattle_spd_arrests' "
    "AND trim(lower(offense_subcategory)) = :desc "
    "AND offense_category IS NULL"
)


def _apply(bind: Connection) -> None:
    for desc, (cat, grp) in _CROSSWALK.items():
        bind.execute(_UPDATE, {"cat": cat, "grp": grp, "desc": desc})


def upgrade() -> None:
    _apply(op.get_bind())


def downgrade() -> None:
    op.get_bind().execute(
        text(
            "UPDATE crime_incidents SET offense_category = NULL, nibrs_group = NULL "
            "WHERE source_dataset = 'seattle_spd_arrests'"
        )
    )
