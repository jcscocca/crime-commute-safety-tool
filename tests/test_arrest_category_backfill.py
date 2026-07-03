import importlib.util
from datetime import UTC, datetime
from pathlib import Path

from app.db import get_sessionmaker
from app.main import create_app
from app.models import CrimeIncident

_MIG_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic" / "versions" / "0011_arrest_category_backfill.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_0011", _MIG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed(session, *, id_, source, subcat, category=None, group=None):
    session.add(
        CrimeIncident(
            id=id_, external_incident_id=id_, source_dataset=source,
            offense_start_utc=datetime(2024, 1, 5, tzinfo=UTC),
            offense_category=category, offense_subcategory=subcat, nibrs_group=group,
            latitude=47.6, longitude=-122.3,
        )
    )


def test_backfill_categorizes_existing_arrests_only(tmp_path):
    create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'bf.sqlite3'}")
    mig = _load_migration()
    session = get_sessionmaker()()
    try:
        _seed(session, id_="a1", source="seattle_spd_arrests", subcat="All Other Larceny")
        _seed(session, id_="a2", source="seattle_spd_arrests", subcat="Simple Assault")
        _seed(session, id_="a3", source="seattle_spd_arrests", subcat="Totally Unknown Offense")
        _seed(session, id_="a4", source="seattle_spd_arrests", subcat="  Simple Assault  ")
        _seed(session, id_="c1", source="seattle_spd_crime", subcat="LARCENY-THEFT",
              category="PROPERTY", group="A")
        session.commit()

        mig._apply(session.connection())  # same transaction as the session
        session.expire_all()

        rows = {r.id: r for r in session.query(CrimeIncident).all()}
        assert (rows["a1"].offense_category, rows["a1"].nibrs_group) == ("PROPERTY", "A")
        assert (rows["a2"].offense_category, rows["a2"].nibrs_group) == ("PERSON", "A")
        # Unmapped arrest stays null.
        assert rows["a3"].offense_category is None
        # Crime row untouched (category preserved, not re-derived).
        assert rows["c1"].offense_category == "PROPERTY"
        # Whitespace-padded description is trimmed to match the crosswalk (mirrors the mapper).
        assert (rows["a4"].offense_category, rows["a4"].nibrs_group) == ("PERSON", "A")

        # Idempotent: a second run changes nothing.
        mig._apply(session.connection())
        session.expire_all()
        assert session.get(CrimeIncident, "a1").offense_category == "PROPERTY"
    finally:
        session.close()
