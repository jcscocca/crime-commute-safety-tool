from app.schemas import CrimeIncidentData
from app.services.neighborhood_service import _category_breakdown


def _inc(subcategory: str | None = None, category: str | None = None) -> CrimeIncidentData:
    return CrimeIncidentData(offense_subcategory=subcategory, offense_category=category)


# ---------------------------------------------------------------------------
# Bucketing / label fallback
# ---------------------------------------------------------------------------

def test_bucketing_prefers_subcategory():
    incidents = [_inc(subcategory="Theft", category="PROPERTY")]
    rows = _category_breakdown(incidents, None)
    assert rows[0]["label"] == "Theft"


def test_bucketing_falls_back_to_category():
    incidents = [_inc(subcategory=None, category="PROPERTY")]
    rows = _category_breakdown(incidents, None)
    assert rows[0]["label"] == "PROPERTY"


def test_bucketing_falls_back_to_uncategorized():
    incidents = [_inc(subcategory=None, category=None)]
    rows = _category_breakdown(incidents, None)
    assert rows[0]["label"] == "Uncategorized"


# ---------------------------------------------------------------------------
# Top-N + Other fold
# ---------------------------------------------------------------------------

def test_top_n_default_is_6_and_other_folds_remainder():
    # 7 distinct labels → top 6 by count, "Other" for the 7th.
    incidents = (
        [_inc(subcategory="A")] * 7
        + [_inc(subcategory="B")] * 6
        + [_inc(subcategory="C")] * 5
        + [_inc(subcategory="D")] * 4
        + [_inc(subcategory="E")] * 3
        + [_inc(subcategory="F")] * 2
        + [_inc(subcategory="G")] * 1  # lowest → folded into Other
    )
    rows = _category_breakdown(incidents, None)
    labels = [r["label"] for r in rows]
    assert "Other" in labels
    assert "G" not in labels
    assert labels[-1] == "Other"  # Other is always last
    other = rows[-1]
    assert other["place_count"] == 1


def test_fewer_than_top_n_labels_produces_no_other():
    incidents = [_inc(subcategory="A")] * 3 + [_inc(subcategory="B")] * 2
    rows = _category_breakdown(incidents, None)
    assert all(r["label"] != "Other" for r in rows)


def test_custom_top_n():
    incidents = [_inc(subcategory="A")] * 3 + [_inc(subcategory="B")] * 2 + [_inc(subcategory="C")] * 1
    rows = _category_breakdown(incidents, None, top_n=2)
    labels = [r["label"] for r in rows]
    assert "A" in labels
    assert "B" in labels
    assert "C" not in labels
    assert labels[-1] == "Other"
    assert rows[-1]["place_count"] == 1


# ---------------------------------------------------------------------------
# Share math
# ---------------------------------------------------------------------------

def test_place_share_sums_to_1_for_top_rows_plus_other():
    incidents = (
        [_inc(subcategory="A")] * 3
        + [_inc(subcategory="B")] * 2
        + [_inc(subcategory="C")] * 1
    )
    rows = _category_breakdown(incidents, None, top_n=2)
    total_share = sum(r["place_share"] for r in rows)
    assert abs(total_share - 1.0) < 1e-9


def test_place_share_is_zero_when_total_is_zero():
    rows = _category_breakdown([], None)
    assert rows == []


def test_beat_share_is_none_when_baseline_is_none():
    incidents = [_inc(subcategory="Theft")]
    rows = _category_breakdown(incidents, None)
    assert rows[0]["beat_share"] is None


def test_beat_share_is_none_when_baseline_is_empty():
    incidents = [_inc(subcategory="Theft")]
    rows = _category_breakdown(incidents, [])
    assert rows[0]["beat_share"] is None


def test_beat_share_is_fraction_of_beat_total():
    place = [_inc(subcategory="Theft")] * 3
    baseline = [_inc(subcategory="Theft")] * 2 + [_inc(subcategory="Burglary")] * 8
    rows = _category_breakdown(place, baseline)
    theft_row = next(r for r in rows if r["label"] == "Theft")
    assert abs(theft_row["beat_share"] - 2 / 10) < 1e-9


def test_beat_only_label_does_not_appear_as_a_row():
    # "Assault" exists only in the beat, not the place — must NOT appear as a row.
    place = [_inc(subcategory="Theft")] * 3
    baseline = [_inc(subcategory="Theft")] * 2 + [_inc(subcategory="Assault")] * 5
    rows = _category_breakdown(place, baseline)
    assert all(r["label"] != "Assault" for r in rows)


def test_label_in_place_but_absent_in_beat_has_beat_share_zero():
    place = [_inc(subcategory="Theft")] * 3
    baseline = [_inc(subcategory="Burglary")] * 8  # Theft absent in baseline
    rows = _category_breakdown(place, baseline)
    theft_row = next(r for r in rows if r["label"] == "Theft")
    assert theft_row["beat_share"] == 0.0


# ---------------------------------------------------------------------------
# Other row beat_share uses the same top-N label set
# ---------------------------------------------------------------------------

def test_other_row_beat_share_aggregates_non_top_labels_in_beat():
    # top_n=2 → top labels are "A" (3) and "B" (2). "C" folds to Other.
    # Baseline: A=1, B=2, C=4. Other beat_share = C_in_beat / beat_total = 4/7.
    place = [_inc(subcategory="A")] * 3 + [_inc(subcategory="B")] * 2 + [_inc(subcategory="C")] * 1
    baseline = (
        [_inc(subcategory="A")] * 1
        + [_inc(subcategory="B")] * 2
        + [_inc(subcategory="C")] * 4
    )
    rows = _category_breakdown(place, baseline, top_n=2)
    other = next(r for r in rows if r["label"] == "Other")
    assert abs(other["beat_share"] - 4 / 7) < 1e-9


# ---------------------------------------------------------------------------
# Deterministic ordering
# ---------------------------------------------------------------------------

def test_ordering_is_place_count_desc_then_label_asc_other_last():
    place = (
        [_inc(subcategory="Burglary")] * 3
        + [_inc(subcategory="Assault")] * 3  # tie with Burglary → label asc
        + [_inc(subcategory="Theft")] * 2
    )
    rows = _category_breakdown(place, None, top_n=10)
    labels = [r["label"] for r in rows]
    # Both Assault and Burglary have count=3 → alphabetical puts Assault first.
    assert labels[0] == "Assault"
    assert labels[1] == "Burglary"
    assert labels[2] == "Theft"


def test_empty_place_list_returns_empty():
    rows = _category_breakdown([], None)
    assert rows == []
