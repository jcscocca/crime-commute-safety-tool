import math

import pytest

from app.analysis.rate_tests import (
    ALPHA,
    Z_975,
    DecisionClass,
    _student_t_cdf,
    _student_t_quantile_975,
    _student_t_two_sided_p,
    benjamini_hochberg,
    classify_pairwise_result,
    compare_incident_rates,
    dispersion_status,
    rate_confidence_interval,
)

# ======================================================================================
# Student-t machinery (pure-stdlib incomplete beta -> t CDF/quantile) for the
# quasi-likelihood phi-noise correction. References are R's qt()/pt() (= scipy.stats.t),
# cross-checked independently: the two-sided tail below was reproduced to ~2e-13 by direct
# Simpson integration of the t density, and every quantile is a mutual inverse of the CDF.
# ======================================================================================


@pytest.mark.parametrize(
    ("df", "expected"),
    [
        (5, 2.5705818366),
        (11, 2.2009851601),
        (30, 2.0422724563),
    ],
)
def test_student_t_0975_quantile_matches_known_values(df, expected):
    # Achieved accuracy is ~1e-9 (dominated by the incomplete-beta evaluation, not the
    # bisection); assert to 1e-8, comfortably inside that.
    assert abs(_student_t_quantile_975(df) - expected) < 1e-8


def test_student_t_two_sided_tail_at_two_df_eleven():
    # P(|T_11| > 2.0). R: 2*pt(2, 11, lower.tail=FALSE) = 0.07080395506783...; scipy
    # stats.t.sf(2,11)*2 agrees. Reproduced here to ~2e-13 by Simpson integration of the
    # t density (see slice report). Pin to 1e-9.
    assert abs(_student_t_two_sided_p(2.0, 11) - 0.0708039550678) < 1e-9
    # t = 0 is the whole mass on both sides.
    assert _student_t_two_sided_p(0.0, 11) == 1.0


@pytest.mark.parametrize("df", [1, 5, 11, 30, 150])
def test_student_t_quantile_and_cdf_are_mutual_inverses(df):
    quantile = _student_t_quantile_975(df)
    assert abs(_student_t_cdf(quantile, df) - 0.975) < 1e-9
    # Heavier tails than the normal: the t quantile always sits at or beyond z_0.975.
    assert quantile >= Z_975


# ======================================================================================
# dispersion_periods -> Student-t widening in the rate machinery.
# ======================================================================================


def test_estimated_phi_with_periods_widens_via_t_and_preserves_duality():
    # Same inputs, once with the normal reference (no period count) and once with the t
    # reference (phi estimated from 6 bins -> nu = 5). The t interval must be strictly wider
    # and its p-value strictly larger, and "p < ALPHA" must stay dual to "CI excludes 1".
    normal = compare_incident_rates(
        count_a=8, exposure_a=30.0, count_b=28, exposure_b=30.0, overdispersion_phi=2.0
    )
    t_ref = compare_incident_rates(
        count_a=8, exposure_a=30.0, count_b=28, exposure_b=30.0,
        overdispersion_phi=2.0, dispersion_periods=6,
    )
    assert t_ref.ci_lower < normal.ci_lower
    assert t_ref.ci_upper > normal.ci_upper
    assert t_ref.p_value > normal.p_value
    for result in (normal, t_ref):
        excludes_one = result.ci_lower > 1.0 or result.ci_upper < 1.0
        assert (result.p_value < ALPHA) == excludes_one


def test_dispersion_periods_is_ignored_when_phi_is_assumed():
    # phi is None (plain Poisson assumption, not estimated) -> the period count must not
    # trigger the t correction; the z path is used exactly as before.
    with_periods = compare_incident_rates(
        count_a=8, exposure_a=30.0, count_b=28, exposure_b=30.0, dispersion_periods=6
    )
    without = compare_incident_rates(
        count_a=8, exposure_a=30.0, count_b=28, exposure_b=30.0
    )
    assert with_periods.ci_lower == without.ci_lower
    assert with_periods.ci_upper == without.ci_upper
    assert with_periods.p_value == without.p_value


def test_large_df_falls_back_to_normal_quantile():
    # At nu >= 200 the t and normal quantiles coincide numerically, so the engine uses z to
    # avoid the beta/bisection work: a huge period count reproduces the phi=None numbers.
    t_ref = compare_incident_rates(
        count_a=8, exposure_a=30.0, count_b=28, exposure_b=30.0,
        overdispersion_phi=2.0, dispersion_periods=1000,
    )
    normal = compare_incident_rates(
        count_a=8, exposure_a=30.0, count_b=28, exposure_b=30.0, overdispersion_phi=2.0
    )
    assert t_ref.ci_lower == normal.ci_lower
    assert t_ref.ci_upper == normal.ci_upper
    assert t_ref.p_value == normal.p_value


def test_rate_confidence_interval_widens_with_estimated_phi_periods():
    normal = rate_confidence_interval(count=10, exposure=100.0, overdispersion_phi=2.0)
    t_ref = rate_confidence_interval(
        count=10, exposure=100.0, overdispersion_phi=2.0, dispersion_periods=4
    )
    assert t_ref.ci_lower < normal.ci_lower
    assert t_ref.ci_upper > normal.ci_upper


def test_dispersion_status_reports_bin_count():
    assert dispersion_status([1, 2, 3, 4]).n_periods == 4
    assert dispersion_status([5]).n_periods == 1  # insufficient, but the true length
    assert dispersion_status([0, 0, 0]).n_periods == 3  # all-zero mean, still reports bins


def test_ci_and_p_value_are_dual_in_non_overdispersed_branch():
    # The decision p-value and the 95% CI now come from one phi-aware Wald SE,
    # so "p < ALPHA" must be exactly equivalent to "the 95% CI excludes 1".
    for count_a, exposure_a, count_b, exposure_b in [
        (5, 100.0, 40, 100.0),   # clearly lower
        (30, 100.0, 33, 100.0),  # borderline
        (20, 100.0, 22, 100.0),  # not clear
    ]:
        result = compare_incident_rates(
            count_a=count_a, exposure_a=exposure_a, count_b=count_b, exposure_b=exposure_b
        )
        excludes_one = result.ci_lower > 1.0 or result.ci_upper < 1.0
        assert (result.p_value < ALPHA) == excludes_one
        assert result.method == "wald_log_rate_ratio"
        assert result.exact_p_value is not None


def test_overdispersed_branch_has_no_exact_p_value():
    result = compare_incident_rates(
        count_a=8, exposure_a=100.0, count_b=40, exposure_b=100.0, overdispersion_phi=3.0
    )
    assert result.method == "quasi_poisson_log_rate_ratio"
    assert result.exact_p_value is None


def test_compare_incident_rates_finds_lower_rate_with_wald_method():
    result = compare_incident_rates(
        count_a=8,
        exposure_a=30.0,
        count_b=28,
        exposure_b=30.0,
    )

    assert result.method == "wald_log_rate_ratio"
    assert result.rate_a == 8 / 30.0
    assert result.rate_b == 28 / 30.0
    assert round(result.rate_ratio, 3) == 0.286
    assert result.p_value < 0.05
    assert result.ci_lower < result.rate_ratio < result.ci_upper


def test_compare_incident_rates_handles_zero_count_with_continuity_correction():
    result = compare_incident_rates(
        count_a=0,
        exposure_a=30.0,
        count_b=12,
        exposure_b=30.0,
    )

    assert result.used_continuity_correction is True
    assert result.rate_ratio < 0.1
    assert result.p_value < 0.05
    assert "continuity correction" in result.caveat_text


@pytest.mark.parametrize(
    ("count_a", "count_b"),
    [
        (-1, 12),
        (8, -1),
        (1.5, 12),
        (8, 2.5),
    ],
)
def test_compare_incident_rates_rejects_invalid_counts(count_a, count_b):
    with pytest.raises(ValueError, match="Incident counts must be nonnegative integers"):
        compare_incident_rates(
            count_a=count_a,
            exposure_a=30.0,
            count_b=count_b,
            exposure_b=30.0,
        )


@pytest.mark.parametrize(
    ("exposure_a", "exposure_b"),
    [
        (math.nan, 30.0),
        (30.0, math.nan),
        (math.inf, 30.0),
        (30.0, math.inf),
    ],
)
def test_compare_incident_rates_rejects_non_finite_exposures(exposure_a, exposure_b):
    with pytest.raises(ValueError, match="Exposure values must be finite and positive"):
        compare_incident_rates(
            count_a=8,
            exposure_a=exposure_a,
            count_b=28,
            exposure_b=exposure_b,
        )


@pytest.mark.parametrize("phi", [-1.0, math.inf, math.nan])
def test_compare_incident_rates_rejects_invalid_overdispersion_phi(phi):
    with pytest.raises(ValueError, match="Overdispersion phi must be finite and nonnegative"):
        compare_incident_rates(
            count_a=8,
            exposure_a=30.0,
            count_b=28,
            exposure_b=30.0,
            overdispersion_phi=phi,
        )


def test_dispersion_status_marks_high_variance_periods_as_overdispersed():
    status = dispersion_status([0, 0, 0, 12, 0, 12])

    assert status.status == "overdispersed"
    assert status.phi > 1.2


def test_dispersion_status_marks_short_series_as_insufficient_periods():
    status = dispersion_status([2])

    assert status.status == "insufficient_periods"
    assert status.phi is None


def test_dispersion_status_rejects_negative_period_counts():
    with pytest.raises(ValueError, match="Period counts must be nonnegative integers"):
        dispersion_status([1, -1, 2])


@pytest.mark.parametrize("period_counts", [[1, 1.5, 2], [1, True, 2]])
def test_dispersion_status_rejects_non_integer_period_counts(period_counts):
    with pytest.raises(ValueError, match="Period counts must be nonnegative integers"):
        dispersion_status(period_counts)


def test_quasi_poisson_adjustment_weakens_high_dispersion_significance():
    poisson = compare_incident_rates(
        count_a=8,
        exposure_a=30.0,
        count_b=28,
        exposure_b=30.0,
        overdispersion_phi=1.0,
    )
    adjusted = compare_incident_rates(
        count_a=8,
        exposure_a=30.0,
        count_b=28,
        exposure_b=30.0,
        overdispersion_phi=4.0,
    )

    assert poisson.method == "wald_log_rate_ratio"
    assert adjusted.method == "quasi_poisson_log_rate_ratio"
    assert adjusted.p_value > poisson.p_value
    assert adjusted.ci_lower < poisson.ci_lower
    assert adjusted.ci_upper > poisson.ci_upper


def test_compare_incident_rates_floors_under_dispersion_at_poisson():
    # phi < 1 (apparent under-dispersion, usually noise in sparse bins) must not shrink the SE
    # below plain Poisson — otherwise it can manufacture a spurious "statistically lower" verdict.
    floored = compare_incident_rates(
        count_a=15, exposure_a=30.0, count_b=22, exposure_b=30.0, overdispersion_phi=0.3
    )
    poisson = compare_incident_rates(
        count_a=15, exposure_a=30.0, count_b=22, exposure_b=30.0, overdispersion_phi=1.0
    )

    assert floored.ci_lower == poisson.ci_lower
    assert floored.ci_upper == poisson.ci_upper
    assert floored.p_value == poisson.p_value


def test_benjamini_hochberg_adjusts_p_values_monotonically():
    adjusted = benjamini_hochberg([0.01, 0.04, 0.03])

    assert adjusted == [0.03, 0.04, 0.04]


def test_benjamini_hochberg_makes_no_correction_for_a_single_or_empty_comparison():
    # A lone comparison (e.g. analyzing one place against its beat) has no multiplicity to
    # correct, so the adjusted p must equal the raw p; an empty set yields an empty result.
    assert benjamini_hochberg([0.037]) == [0.037]
    assert benjamini_hochberg([]) == []


@pytest.mark.parametrize("p_value", [-0.01, 1.01, math.inf, math.nan])
def test_benjamini_hochberg_rejects_invalid_p_values(p_value):
    with pytest.raises(ValueError, match="P-values must be finite values between 0 and 1"):
        benjamini_hochberg([0.01, p_value])


def test_classify_requires_statistical_and_practical_thresholds():
    statistically_lower = classify_pairwise_result(
        rate_ratio=0.5,
        adjusted_p_value=0.01,
        minimum_data_met=True,
        model_warning=False,
    )
    weak_practical_difference = classify_pairwise_result(
        rate_ratio=0.9,
        adjusted_p_value=0.01,
        minimum_data_met=True,
        model_warning=False,
    )
    weak_statistical_difference = classify_pairwise_result(
        rate_ratio=0.5,
        adjusted_p_value=0.20,
        minimum_data_met=True,
        model_warning=False,
    )

    assert statistically_lower == DecisionClass.STATISTICALLY_LOWER
    assert weak_practical_difference == DecisionClass.NOT_STATISTICALLY_CLEAR
    assert weak_statistical_difference == DecisionClass.NOT_STATISTICALLY_CLEAR


def test_classify_returns_insufficient_data_before_other_decisions():
    result = classify_pairwise_result(
        rate_ratio=0.5,
        adjusted_p_value=0.01,
        minimum_data_met=False,
        model_warning=True,
    )

    assert result == DecisionClass.INSUFFICIENT_DATA


def test_classify_returns_model_warning_when_data_is_sufficient():
    result = classify_pairwise_result(
        rate_ratio=0.5,
        adjusted_p_value=0.01,
        minimum_data_met=True,
        model_warning=True,
    )

    assert result == DecisionClass.MODEL_WARNING


def test_rate_confidence_interval_brackets_the_rate_with_wald_log_method():
    result = rate_confidence_interval(count=10, exposure=100.0)

    assert result.rate == 10 / 100.0
    assert result.method == "poisson_rate_interval"
    assert result.used_continuity_correction is False
    assert result.ci_lower < result.rate < result.ci_upper
    # exp(log(0.1) +/- 1.96 * sqrt(1/10)) — single-rate analogue of the pairwise SE.
    assert round(result.ci_lower, 4) == 0.0538
    assert round(result.ci_upper, 4) == 0.1859


def test_rate_confidence_interval_widens_with_overdispersion():
    poisson = rate_confidence_interval(count=20, exposure=100.0, overdispersion_phi=1.0)
    overdispersed = rate_confidence_interval(count=20, exposure=100.0, overdispersion_phi=4.0)

    assert poisson.method == "poisson_rate_interval"
    assert overdispersed.method == "quasi_poisson_rate_interval"
    assert overdispersed.ci_lower < poisson.ci_lower
    assert overdispersed.ci_upper > poisson.ci_upper


def test_rate_confidence_interval_zero_count_clamps_lower_bound_to_zero():
    result = rate_confidence_interval(count=0, exposure=50.0)

    assert result.rate == 0.0
    assert result.used_continuity_correction is True
    # The exact-Poisson lower bound at k=0 is 0, so the interval starts at the point estimate
    # (the continuity correction only powers an honest positive upper bound). The rate stays
    # inside its own interval — the number-line dot sits at the left edge of the bar, not
    # detached to its left.
    assert result.ci_lower == 0.0
    assert result.rate == result.ci_lower
    assert result.ci_upper > 0.0


def test_rate_confidence_interval_floors_under_dispersion_at_poisson():
    # An estimated phi < 1 is treated as noise: the interval must not shrink below the plain
    # Poisson (phi=1) interval.
    floored = rate_confidence_interval(count=15, exposure=100.0, overdispersion_phi=0.3)
    poisson = rate_confidence_interval(count=15, exposure=100.0, overdispersion_phi=1.0)

    assert floored.ci_lower == poisson.ci_lower
    assert floored.ci_upper == poisson.ci_upper


def test_rate_confidence_interval_tightens_relative_interval_as_count_grows():
    sparse = rate_confidence_interval(count=5, exposure=100.0)
    dense = rate_confidence_interval(count=200, exposure=100.0)

    assert dense.ci_upper / dense.ci_lower < sparse.ci_upper / sparse.ci_lower


@pytest.mark.parametrize("count", [-1, 1.5, True])
def test_rate_confidence_interval_rejects_invalid_counts(count):
    with pytest.raises(ValueError, match="Incident counts must be nonnegative integers"):
        rate_confidence_interval(count=count, exposure=100.0)


@pytest.mark.parametrize("exposure", [0.0, -1.0, math.nan, math.inf])
def test_rate_confidence_interval_rejects_non_positive_or_non_finite_exposure(exposure):
    with pytest.raises(ValueError, match="Exposure values must be finite and positive"):
        rate_confidence_interval(count=10, exposure=exposure)


@pytest.mark.parametrize("phi", [-1.0, math.inf, math.nan])
def test_rate_confidence_interval_rejects_invalid_overdispersion_phi(phi):
    with pytest.raises(ValueError, match="Overdispersion phi must be finite and nonnegative"):
        rate_confidence_interval(count=10, exposure=100.0, overdispersion_phi=phi)
