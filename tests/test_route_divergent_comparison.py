from datetime import date

import pytest

from app.analysis.comparison import build_route_divergent_comparison
from app.analysis.schemas import (
    AnalysisOptionResult,
    DecisionClass,
    GeometryType,
    PairDivergenceInput,
)


def _option(option_id: str, label: str, incident_count: int, exposure: float = 60.0):
    return AnalysisOptionResult(
        option_id=option_id,
        option_label=label,
        geometry_type=GeometryType.ROUTE_CORRIDOR,
        radius_m=250,
        incident_count=incident_count,
        exposure=exposure,
        exposure_unit="square_km_days",
        incident_rate=incident_count / exposure if exposure > 0 else 0.0,
    )


def _build(options, pair_inputs, *, start=date(2024, 1, 1), end=date(2024, 2, 29)):
    return build_route_divergent_comparison(
        user_id_hash="user",
        radius_m=250,
        analysis_start_date=start,
        analysis_end_date=end,
        offense_category="PROPERTY",
        offense_subcategory=None,
        nibrs_group=None,
        options=options,
        pair_inputs=pair_inputs,
    )


def test_divergent_test_fires_when_whole_corridors_look_identical():
    # Whole-corridor context: 90 vs 110 on equal exposure — the OLD framing would have
    # been not_statistically_clear (rate ratio 0.82 > 0.80). The divergent numbers are
    # decisive: 8 vs 28 on equal divergent exposure.
    result = _build(
        options=[_option("a", "Route A", 90), _option("b", "Route B", 110)],
        pair_inputs=[
            PairDivergenceInput(
                option_a_id="a",
                option_b_id="b",
                count_a=8,
                count_b=28,
                exposure_a=15.0,
                exposure_b=15.0,
                period_counts_a=[4, 4],
                period_counts_b=[14, 14],
                divergent_share_a=0.3,
                divergent_share_b=0.3,
            )
        ],
    )

    assert result.geometry_type == GeometryType.ROUTE_DIVERGENT_CORRIDOR
    assert result.decision_class == DecisionClass.STATISTICALLY_LOWER
    assert result.recommendation_option_id == "a"
    assert result.overview_summary_text.startswith("Where these routes differ, Route A")
    pairwise = result.pairwise_results[0]
    assert pairwise.incident_count_a == 8  # divergent count, not the whole-corridor 90
    assert pairwise.incident_count_b == 28
    assert pairwise.winner_option_id == "a"
    assert "share ~70% of their corridors" in pairwise.caveat_text
    # Context rows still carry whole-corridor counts.
    assert [option.incident_count for option in result.options] == [90, 110]
    verdict_text = " ".join(
        [result.overview_summary_text, result.overview_caveat_text, pairwise.caveat_text]
    ).lower()
    for banned in ("safe", "unsafe", "safety", "danger", "dangerous", "risk", "risky"):
        assert banned not in verdict_text, banned


def test_effectively_identical_corridors_report_same_corridor_outcome():
    result = _build(
        options=[_option("a", "Route A", 40), _option("b", "Route B", 41)],
        pair_inputs=[
            PairDivergenceInput(
                option_a_id="a",
                option_b_id="b",
                count_a=0,
                count_b=0,
                exposure_a=0.0,
                exposure_b=0.0,
                period_counts_a=[0, 0],
                period_counts_b=[0, 0],
                divergent_share_a=0.0,
                divergent_share_b=0.01,
            )
        ],
    )

    pairwise = result.pairwise_results[0]
    assert pairwise.minimum_data_status == "corridors_effectively_identical"
    assert pairwise.method == "not_tested_minimum_data"
    assert pairwise.p_value == 1.0
    assert result.decision_class == DecisionClass.INSUFFICIENT_DATA
    assert result.recommendation_option_id is None
    assert result.overview_summary_text == (
        "These route options follow essentially the same corridor at this radius, "
        "so there is no divergent segment to compare."
    )


def test_divergent_floors_block_near_empty_candidate():
    result = _build(
        options=[_option("a", "Route A", 30), _option("b", "Route B", 60)],
        pair_inputs=[
            PairDivergenceInput(
                option_a_id="a",
                option_b_id="b",
                count_a=1,
                count_b=20,
                exposure_a=10.0,
                exposure_b=10.0,
                period_counts_a=[1, 0],
                period_counts_b=[10, 10],
                divergent_share_a=0.4,
                divergent_share_b=0.4,
            )
        ],
    )

    assert result.pairwise_results[0].minimum_data_status == "option_count_too_low"
    assert result.decision_class == DecisionClass.INSUFFICIENT_DATA
    assert result.recommendation_option_id is None


def test_candidate_is_lowest_aggregate_divergent_rate_and_must_win_every_pair():
    # Aggregate divergent rates: a = (8+8)/(15+15) ≈ 0.53, b ≈ 1.87, c = 0.60 → candidate a.
    # a beats b decisively but a-vs-c is 8 vs 9 (ratio 0.89 > 0.80) → overall not clear.
    result = _build(
        options=[
            _option("a", "Route A", 90),
            _option("b", "Route B", 110),
            _option("c", "Route C", 95),
        ],
        pair_inputs=[
            PairDivergenceInput(
                option_a_id="a",
                option_b_id="b",
                count_a=8,
                count_b=28,
                exposure_a=15.0,
                exposure_b=15.0,
                period_counts_a=[4, 4],
                period_counts_b=[14, 14],
                divergent_share_a=0.3,
                divergent_share_b=0.3,
            ),
            PairDivergenceInput(
                option_a_id="a",
                option_b_id="c",
                count_a=8,
                count_b=9,
                exposure_a=15.0,
                exposure_b=15.0,
                period_counts_a=[4, 4],
                period_counts_b=[5, 4],
                divergent_share_a=0.25,
                divergent_share_b=0.25,
            ),
            PairDivergenceInput(
                option_a_id="b",
                option_b_id="c",
                count_a=28,
                count_b=9,
                exposure_a=15.0,
                exposure_b=15.0,
                period_counts_a=[14, 14],
                period_counts_b=[5, 4],
                divergent_share_a=0.3,
                divergent_share_b=0.25,
            ),
        ],
    )

    assert len(result.pairwise_results) == 2  # candidate vs each other option
    assert all(
        pairwise.option_a_id == "a" for pairwise in result.pairwise_results
    )
    assert result.decision_class == DecisionClass.NOT_STATISTICALLY_CLEAR
    assert result.recommendation_option_id is None
    assert result.overview_summary_text == (
        "Where these routes differ, no option has a statistically clear lower "
        "reported-incident rate under the selected filters."
    )


def test_requires_two_options_and_full_pair_coverage():
    with pytest.raises(ValueError):
        _build(options=[_option("a", "Route A", 10)], pair_inputs=[])
    with pytest.raises(ValueError):
        _build(
            options=[_option("a", "Route A", 10), _option("b", "Route B", 12)],
            pair_inputs=[],
        )


def test_candidate_flip_orientation_and_bh_adjustment():
    # Whole-corridor rates pick a (0.67 < 1.5 < 1.83), but divergent aggregates pick c
    # (0.40 < 1.33 < 1.87) — and c arrives as option_b in both of its pairs, so the
    # engine must flip sides before applying the candidate-side floor and labels.
    result = _build(
        options=[
            _option("a", "Route A", 40),
            _option("b", "Route B", 110),
            _option("c", "Route C", 90),
        ],
        pair_inputs=[
            PairDivergenceInput(
                option_a_id="a",
                option_b_id="b",
                count_a=20,
                count_b=28,
                exposure_a=15.0,
                exposure_b=15.0,
                period_counts_a=[10, 10],
                period_counts_b=[14, 14],
                divergent_share_a=0.3,
                divergent_share_b=0.3,
            ),
            PairDivergenceInput(
                option_a_id="a",
                option_b_id="c",
                count_a=20,
                count_b=6,
                exposure_a=15.0,
                exposure_b=15.0,
                period_counts_a=[10, 10],
                period_counts_b=[3, 3],
                divergent_share_a=0.3,
                divergent_share_b=0.3,
            ),
            PairDivergenceInput(
                option_a_id="b",
                option_b_id="c",
                count_a=28,
                count_b=6,
                exposure_a=15.0,
                exposure_b=15.0,
                period_counts_a=[14, 14],
                period_counts_b=[3, 3],
                divergent_share_a=0.3,
                divergent_share_b=0.3,
            ),
        ],
    )

    assert result.recommendation_option_id == "c"
    assert result.decision_class == DecisionClass.STATISTICALLY_LOWER
    assert all(pairwise.option_a_id == "c" for pairwise in result.pairwise_results)
    assert all(pairwise.incident_count_a == 6 for pairwise in result.pairwise_results)
    ordered = sorted(result.pairwise_results, key=lambda pairwise: pairwise.p_value)
    assert ordered[0].adjusted_p_value > ordered[0].p_value
    assert ordered[1].adjusted_p_value == ordered[1].p_value


def test_mixed_identical_pair_blocks_recommendation_conservatively():
    # The candidate decisively beats B where corridors differ, but is a geometric
    # duplicate of C — recommending it as lower than EVERY alternative would be false,
    # so the engine must withhold the recommendation and report the duplicate honestly.
    result = _build(
        options=[
            _option("a", "Route A", 40),
            _option("b", "Route B", 110),
            _option("c", "Route C", 41),
        ],
        pair_inputs=[
            PairDivergenceInput(
                option_a_id="a",
                option_b_id="b",
                count_a=8,
                count_b=28,
                exposure_a=15.0,
                exposure_b=15.0,
                period_counts_a=[4, 4],
                period_counts_b=[14, 14],
                divergent_share_a=0.3,
                divergent_share_b=0.3,
            ),
            PairDivergenceInput(
                option_a_id="a",
                option_b_id="c",
                count_a=0,
                count_b=0,
                exposure_a=0.01,
                exposure_b=0.01,
                period_counts_a=[0, 0],
                period_counts_b=[0, 0],
                divergent_share_a=0.0,
                divergent_share_b=0.01,
            ),
            PairDivergenceInput(
                option_a_id="b",
                option_b_id="c",
                count_a=28,
                count_b=8,
                exposure_a=15.0,
                exposure_b=15.0,
                period_counts_a=[14, 14],
                period_counts_b=[4, 4],
                divergent_share_a=0.3,
                divergent_share_b=0.3,
            ),
        ],
    )

    assert result.decision_class == DecisionClass.INSUFFICIENT_DATA
    assert result.recommendation_option_id is None
    statuses = {pairwise.minimum_data_status for pairwise in result.pairwise_results}
    assert statuses == {"met", "corridors_effectively_identical"}
    assert "corridors_effectively_identical" in result.full_caveat_text
    identical_row = next(
        pairwise
        for pairwise in result.pairwise_results
        if pairwise.minimum_data_status == "corridors_effectively_identical"
    )
    assert "only the divergent segments were compared" not in identical_row.caveat_text


def test_short_window_identical_corridors_do_not_raise():
    # <30-day window AND zero divergent exposure: the geometry gate must short-circuit
    # before the date check, so no exposure=0 rate test is attempted.
    result = _build(
        options=[_option("a", "Route A", 40), _option("b", "Route B", 41)],
        pair_inputs=[
            PairDivergenceInput(
                option_a_id="a",
                option_b_id="b",
                count_a=0,
                count_b=0,
                exposure_a=0.0,
                exposure_b=0.0,
                period_counts_a=[0, 0],
                period_counts_b=[0, 0],
                divergent_share_a=0.0,
                divergent_share_b=0.01,
            )
        ],
        start=date(2024, 1, 1),
        end=date(2024, 1, 20),
    )

    assert result.pairwise_results[0].minimum_data_status == "corridors_effectively_identical"


def test_short_window_contained_pair_reports_non_positive_exposure():
    # <30-day window; one side has divergent geometry but zero exposure (contained).
    # The non_positive_exposure gate must fire before the date check — no rate test.
    result = _build(
        options=[_option("a", "Route A", 40), _option("b", "Route B", 60)],
        pair_inputs=[
            PairDivergenceInput(
                option_a_id="a",
                option_b_id="b",
                count_a=0,
                count_b=10,
                exposure_a=0.0,
                exposure_b=12.0,
                period_counts_a=[0, 0],
                period_counts_b=[5, 5],
                divergent_share_a=0.0,
                divergent_share_b=0.5,
            )
        ],
        start=date(2024, 1, 1),
        end=date(2024, 1, 20),
    )

    assert result.pairwise_results[0].minimum_data_status == "non_positive_exposure"


def test_short_window_with_positive_exposures_still_reports_date_range_too_short():
    # Parity with the old behavior: when both exposures are positive, a short window
    # is still reported as date_range_too_short.
    result = _build(
        options=[_option("a", "Route A", 40), _option("b", "Route B", 60)],
        pair_inputs=[
            PairDivergenceInput(
                option_a_id="a",
                option_b_id="b",
                count_a=8,
                count_b=20,
                exposure_a=15.0,
                exposure_b=15.0,
                period_counts_a=[4, 4],
                period_counts_b=[10, 10],
                divergent_share_a=0.3,
                divergent_share_b=0.3,
            )
        ],
        start=date(2024, 1, 1),
        end=date(2024, 1, 20),
    )

    assert result.pairwise_results[0].minimum_data_status == "date_range_too_short"


def test_candidate_selection_skips_not_tested_pairs():
    # A and C are near-duplicates (their pair is effectively identical) but the A-C row
    # carries polluting outer-flank counts on ~zero divergent exposure. Pre-fix, summing
    # those into A's aggregate exploded A's rate and flipped the candidate away from A.
    # A is genuinely the lowest divergent rate on its real (A-B) pair.
    result = _build(
        options=[
            _option("a", "Route A", 90),
            _option("b", "Route B", 110),
            _option("c", "Route C", 91),
        ],
        pair_inputs=[
            PairDivergenceInput(
                option_a_id="a",
                option_b_id="b",
                count_a=8,
                count_b=28,
                exposure_a=15.0,
                exposure_b=15.0,
                period_counts_a=[4, 4],
                period_counts_b=[14, 14],
                divergent_share_a=0.3,
                divergent_share_b=0.3,
            ),
            PairDivergenceInput(
                option_a_id="a",
                option_b_id="c",
                count_a=61,
                count_b=110,
                exposure_a=0.01,
                exposure_b=0.01,
                period_counts_a=[30, 31],
                period_counts_b=[55, 55],
                divergent_share_a=0.0,
                divergent_share_b=0.01,
            ),
            PairDivergenceInput(
                option_a_id="b",
                option_b_id="c",
                count_a=28,
                count_b=8,
                exposure_a=15.0,
                exposure_b=15.0,
                period_counts_a=[14, 14],
                period_counts_b=[4, 4],
                divergent_share_a=0.3,
                divergent_share_b=0.3,
            ),
        ],
    )

    # Candidate is A (pre-fix the outer-flank pollution flips it to B or C).
    assert all(pairwise.option_a_id == "a" for pairwise in result.pairwise_results)
    ab_row = next(
        pairwise for pairwise in result.pairwise_results if pairwise.option_b_id == "b"
    )
    assert ab_row.minimum_data_status == "met"
    assert ab_row.incident_count_a == 8
    assert ab_row.incident_count_b == 28
    ac_row = next(
        pairwise for pairwise in result.pairwise_results if pairwise.option_b_id == "c"
    )
    assert ac_row.minimum_data_status == "corridors_effectively_identical"


def test_pairwise_caveat_reports_both_route_percentages():
    # Asymmetric shares 0.10 / 0.60: route A shares ~90% of ITS corridor, route B ~40%.
    # A single "~40%" number would mislead for A, so both figures must appear.
    result = _build(
        options=[_option("a", "Route A", 90), _option("b", "Route B", 110)],
        pair_inputs=[
            PairDivergenceInput(
                option_a_id="a",
                option_b_id="b",
                count_a=8,
                count_b=28,
                exposure_a=15.0,
                exposure_b=15.0,
                period_counts_a=[4, 4],
                period_counts_b=[14, 14],
                divergent_share_a=0.10,
                divergent_share_b=0.60,
            )
        ],
    )

    caveat = result.pairwise_results[0].caveat_text
    assert "90%" in caveat
    assert "40%" in caveat
    assert "only the divergent segments were compared" in caveat
    lowered = caveat.lower()
    for banned in ("safe", "unsafe", "safety", "danger", "dangerous", "risk", "risky"):
        assert banned not in lowered, banned


def test_not_tested_rows_excluded_from_bh_family():
    # One identical (not-tested) pair + one decisively-tested pair. The not-tested row's
    # structural p=1.0 must NOT enter the BH family — otherwise the tested pair's
    # adjusted p roughly doubles (family of 2 instead of 1).
    result = _build(
        options=[
            _option("a", "Route A", 40),
            _option("b", "Route B", 110),
            _option("c", "Route C", 41),
        ],
        pair_inputs=[
            PairDivergenceInput(
                option_a_id="a",
                option_b_id="b",
                count_a=8,
                count_b=28,
                exposure_a=15.0,
                exposure_b=15.0,
                period_counts_a=[4, 4],
                period_counts_b=[14, 14],
                divergent_share_a=0.3,
                divergent_share_b=0.3,
            ),
            PairDivergenceInput(
                option_a_id="a",
                option_b_id="c",
                count_a=0,
                count_b=0,
                exposure_a=0.01,
                exposure_b=0.01,
                period_counts_a=[0, 0],
                period_counts_b=[0, 0],
                divergent_share_a=0.0,
                divergent_share_b=0.01,
            ),
            PairDivergenceInput(
                option_a_id="b",
                option_b_id="c",
                count_a=28,
                count_b=8,
                exposure_a=15.0,
                exposure_b=15.0,
                period_counts_a=[14, 14],
                period_counts_b=[4, 4],
                divergent_share_a=0.3,
                divergent_share_b=0.3,
            ),
        ],
    )

    tested = next(
        pairwise
        for pairwise in result.pairwise_results
        if pairwise.minimum_data_status == "met"
    )
    not_tested = next(
        pairwise
        for pairwise in result.pairwise_results
        if pairwise.minimum_data_status == "corridors_effectively_identical"
    )
    assert tested.adjusted_p_value == pytest.approx(tested.p_value)
    assert not_tested.adjusted_p_value == 1.0
