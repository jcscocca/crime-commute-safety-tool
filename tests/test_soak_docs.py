from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def test_compose_enables_pg_stat_statements():
    compose = (_ROOT / "docker-compose.yml").read_text()
    assert "shared_preload_libraries=pg_stat_statements" in compose


def test_runbook_documents_prereqs_and_commands():
    doc = (_ROOT / "docs" / "soak-testing.md").read_text()
    for needle in ("pg_stat_statements", "--force-recreate db",
                   "soak_driver.py", "pg_observer.py", "make soak-load", "make soak-observe"):
        assert needle in doc, f"runbook missing: {needle}"
