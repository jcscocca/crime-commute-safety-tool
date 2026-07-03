import csv
from pathlib import Path

from app.crime.nibrs_crosswalk import classify_nibrs


def test_known_descriptions_map_to_category_and_group():
    assert classify_nibrs("All Other Larceny") == ("PROPERTY", "A")
    assert classify_nibrs("Drug/Narcotic Violations") == ("SOCIETY", "A")
    assert classify_nibrs("Simple Assault") == ("PERSON", "A")
    assert classify_nibrs("Burglary/Breaking & Entering") == ("PROPERTY", "A")
    assert classify_nibrs("Weapon Law Violations") == ("SOCIETY", "A")


def test_normalizes_case_and_whitespace():
    assert classify_nibrs("  simple ASSAULT  ") == ("PERSON", "A")


def test_unmapped_and_empty_return_none_none():
    assert classify_nibrs(None) == (None, None)
    assert classify_nibrs("") == (None, None)
    assert classify_nibrs("Some Unlisted Offense") == (None, None)


def test_every_seed_arrest_description_is_mapped():
    # Coverage: every distinct nibrs_description in the arrest seed must classify (non-None),
    # so real seed/ingest data is never silently uncategorized.
    seed = Path(__file__).resolve().parent.parent / "app" / "data" / "seed_arrests.csv"
    with seed.open(newline="", encoding="utf-8-sig") as fh:
        descriptions = {row["nibrs_description"] for row in csv.DictReader(fh)}
    for desc in descriptions:
        category, group = classify_nibrs(desc)
        assert category is not None, f"unmapped seed arrest offense: {desc!r}"
        assert group in {"A", "B"}, desc
