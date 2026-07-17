"""Statistical calibration pins for app/analysis/rate_tests.py.

Two deliverables, both pure stdlib + pytest (numpy is NOT in the venv):

  1. Numeric pins for the exact conditional two-sided p-value
     (``compare_incident_rates(...).exact_p_value``), each expected value derived
     BY HAND from the conditional binomial pmf (see per-case comments).

  2. Seeded Monte-Carlo coverage / type-I measurement at the decision floors
     (MIN_PLACE_COUNT=3, MIN_COMBINED_COUNT=10) for the single-rate interval and
     the two-sample test. Fixed seeds make the runs exactly reproducible, so the
     regression pins are one-sided bounds in the *protective* direction
     (coverage floors, type-I ceilings) set at roughly measured -/+ 2*MC-SE.

This file MEASURES the machinery. As of 2026-07-17 the estimated-phi paths carry the
quasi-likelihood Student-t correction (nu = n_periods - 1; Wedderburn 1974, McCullagh &
Nelder 1989), so the "practice" arm below is invoked exactly as production invokes it
(dispersion_periods threaded from the same monthly series phi is estimated from). The full
BEFORE/AFTER measured table and the seed live in the comment block above the MC section.
"""

from __future__ import annotations

import math
import random
import time
from fractions import Fraction

from app.analysis.rate_tests import (
    compare_incident_rates,
    dispersion_status,
    rate_confidence_interval,
)

# ======================================================================================
# Deliverable 1 — exact conditional two-sided p-value, pinned numerically.
#
# Convention (confirmed to match the implementation, no discrepancy found):
# condition on N = k_a + k_b; under H0 of equal rates k_a ~ Binomial(N, p) with
# p = exposure_a / (exposure_a + exposure_b). The two-sided p is the POINT-PROBABILITY
# (a.k.a. minimum-likelihood / "method of small p") sum of every pmf value <= pmf at the
# observed k_a. Each expected number below is the exact rational value of that sum.
# ======================================================================================


def _binom_pmf_fraction(n: int, k: int, p: Fraction) -> Fraction:
    """Exact binomial pmf as a Fraction — independent of the lgamma path under test."""
    return Fraction(math.comb(n, k)) * p**k * (1 - p) ** (n - k)


def _exact_two_sided_p_fraction(n: int, k_obs: int, p: Fraction) -> Fraction:
    """Independent exact point-probability two-sided p, for cross-checking the pins."""
    obs = _binom_pmf_fraction(n, k_obs, p)
    total = sum(
        (pmf for k in range(n + 1) if (pmf := _binom_pmf_fraction(n, k, p)) <= obs),
        Fraction(0),
    )
    return min(Fraction(1), total)


def test_exact_p_equal_exposures_point_probability():
    # p=1/2, N=10, k_a=3. pmf(k)=C(10,k)/1024, obs=C(10,3)/1024=120/1024.
    # Include every k with C(10,k) <= 120: k in {0,1,2,3,7,8,9,10} with binomials
    # {1,10,45,120,120,45,10,1}; k in {4,5,6} have {210,252,210} > 120 (excluded).
    # sum = 352/1024 = 11/32 = 0.34375.
    result = compare_incident_rates(
        count_a=3, exposure_a=100.0, count_b=7, exposure_b=100.0
    )
    assert abs(result.exact_p_value - 0.34375) < 1e-9  # 11/32
    assert _exact_two_sided_p_fraction(10, 3, Fraction(1, 2)) == Fraction(11, 32)


def test_exact_p_zero_count_equal_exposures():
    # k_a=0, p=1/2, N=5. pmf(k)=C(5,k)/32, obs=C(5,0)/32=1/32.
    # Only k with C(5,k) <= 1 are {0,5} -> sum = 2/32 = 1/16 = 0.0625.
    result = compare_incident_rates(
        count_a=0, exposure_a=50.0, count_b=5, exposure_b=50.0
    )
    assert abs(result.exact_p_value - 0.0625) < 1e-9
    assert _exact_two_sided_p_fraction(5, 0, Fraction(1, 2)) == Fraction(1, 16)


def test_exact_p_unequal_exposures_zero_count():
    # exposure_a=100, exposure_b=300 -> p=1/4, N=4, k_a=0.
    # pmf(k)=C(4,k)*3^(4-k)/4^4 -> numerators {81,108,54,12,1}/256; obs=81/256.
    # Include pmf <= 81/256: k in {0,2,3,4} -> (81+54+12+1)/256 = 148/256 = 37/64.
    result = compare_incident_rates(
        count_a=0, exposure_a=100.0, count_b=4, exposure_b=300.0
    )
    assert abs(result.exact_p_value - 37 / 64) < 1e-9  # 0.578125
    assert _exact_two_sided_p_fraction(4, 0, Fraction(1, 4)) == Fraction(37, 64)


def test_exact_p_unequal_exposures_interior_point():
    # exposure_a=200, exposure_b=300 -> p=2/5, N=15, k_a=4. Discriminating unequal case.
    # Hand value is the exact rational 13134182381 / 5^15 (= 30517578125).
    result = compare_incident_rates(
        count_a=4, exposure_a=200.0, count_b=11, exposure_b=300.0
    )
    expected = Fraction(13134182381, 30517578125)  # = 0.430380888260608
    assert abs(result.exact_p_value - float(expected)) < 1e-9
    assert _exact_two_sided_p_fraction(15, 4, Fraction(2, 5)) == expected


def test_exact_p_large_n_equal_exposures():
    # p=1/2, N=30, k_a=10. obs pmf = C(30,10)/2^30, C(30,10)=30045015.
    # C(30,11)=54627300 > C(30,10), so the excluded interior is k in {11..19}; by symmetry
    # the included set is {0..10} U {20..30}. Exact sum = 26504551/2^28.
    result = compare_incident_rates(
        count_a=10, exposure_a=100.0, count_b=20, exposure_b=100.0
    )
    expected = Fraction(26504551, 2**28)  # = 0.09873714670538988
    assert abs(result.exact_p_value - float(expected)) < 1e-9
    assert _exact_two_sided_p_fraction(30, 10, Fraction(1, 2)) == expected


def test_exact_p_clamps_to_one_at_the_mode():
    # p=1/2, N=4, k_a=2 sits at the unique mode; every other pmf is smaller, so the raw
    # sum is exactly 1 and the implementation's min(1.0, .) clamp holds.
    result = compare_incident_rates(
        count_a=2, exposure_a=100.0, count_b=2, exposure_b=100.0
    )
    assert abs(result.exact_p_value - 1.0) < 1e-9


# ======================================================================================
# Deliverable 2 — Monte-Carlo coverage / type-I at the decision floors.
#
# All draws come from random.Random(seed) with the seeds pinned below; the samplers use
# only .random() (Poisson via Knuth) and .gammavariate() (NB1 mixture), both stable across
# CPython, so every count below is exactly reproducible. Pins are one-sided bounds in the
# protective direction (coverage floors / type-I ceilings) at ~ measured -/+ 2*MC-SE.
# 2*MC-SE at n=20000, p~=0.95 is ~=0.0031; at p~=0.04 is ~=0.0028.
#
# MEASURED TABLE (this file, seeds as coded):
#
# --- BEFORE the t correction (phi estimated, but z quantile used everywhere) ------------
#   Single-rate 95% interval, ESTIMATED phi from a 12-month split, reps=10000, seed=2024:
#       phi=3: mu=5 0.9661  mu=10 0.9097  mu=15 0.9016     <-- degrades
#       phi=7: mu=5 0.9662  mu=10 0.8269  mu=15 0.8459     <-- MATERIALLY UNDER 0.90
#   Two-sample type-I, phi=3 (TRUE phi, z), reps=20000, seed=77:
#       mu=5 0.0008/0.0016 | mu=10 0.0091/0.0089 | mu=20 0.0270/0.0268   (ungated/gated)
#
# --- AFTER the t correction (2026-07-17; estimated-phi paths use t_{nu}, nu=n_periods-1) -
#   Single-rate 95% interval, Poisson (phi=None -> z, UNCHANGED), reps=20000, seed=12345:
#       mu= 3 -> 0.9677    mu= 5 -> 0.9663    mu=10 -> 0.9629    mu=15 -> 0.9486
#   Single-rate 95% interval, NB1 TRUE phi (invoked WITHOUT periods -> z, UNCHANGED),
#       reps=20000, seed=4242:   (this is the method ceiling when phi is known exactly)
#       phi=3: mu=3 0.9588  mu=5 0.9510  mu=10 0.9515  mu=15 0.9598
#       phi=7: mu=3 0.9529  mu=5 0.9554  mu=10 0.9574  mu=15 0.9519
#   Single-rate 95% interval, ESTIMATED phi from a 12-month split, periods=12 -> t_{11},
#       reps=10000, seed=2024   (the 'practice' arm, invoked exactly as production):
#       phi=3: mu=5 0.9776  mu=10 0.9441  mu=15 0.9313
#       phi=7: mu=5 0.9777  mu=10 0.8907  mu=15 0.8864     <-- STILL UNDER 0.92
#   Two-sample type-I ("p<0.05"), null equal rates, reps=20000, seed=77:
#       phi=1 (None -> z, UNCHANGED):
#           mu=5 0.0204/0.0095 | mu=10 0.0412/0.0383 | mu=20 0.0435/0.0435
#       phi=3 (true phi + periods=12 -> t_{11}, MORE CONSERVATIVE than the z 'before'):
#           mu=5 0.0001/0.0003 | mu=10 0.0019/0.0020 | mu=20 0.0104/0.0105
#   Two-sample power ("p<0.05"), alt RR=0.5, phi=1 -> z, reps=20000, seed=55 (UNCHANGED):
#       mu_a/mu_b = 5/10 0.2087/0.1565 | 10/20 0.4309/0.4296 | 20/40 0.7369/0.7369
#
# The t_{nu} correction lifts the estimated-phi single-rate coverage from ~0.83-0.91 to
# ~0.89-0.98, and makes the two-sample test uniformly more conservative (type-I <= nominal
# everywhere). It does NOT fully close the gap at HEAVY overdispersion with small monthly
# counts: phi=7, mu in {10,15} stay at ~0.89 (STILL BELOW the 0.92 acceptance target). At
# those cells the 12-bin phi-hat is so noisy that a fixed-df widening cannot absorb it, and
# the small annual counts also strain the log-normal Wald approximation. This is a documented
# residual, not a regression -- see docs/analysis/overdispersion-and-rate-intervals.md sec 5.
# The two-sample arm passes the TRUE phi with periods=12 so the exact t_{11} quantile applies
# as in production; production additionally estimates phi (adding noise), making it even more
# conservative under the null than the numbers above.
# ======================================================================================

_UNIT_EXPOSURE = 1.0  # coverage of the rate is exposure-invariant, so fix E=1 (rate == mean)


def _poisson(rng: random.Random, mu: float) -> int:
    """Knuth's Poisson sampler using only rng.random()."""
    threshold = math.exp(-mu)
    k = 0
    product = 1.0
    while True:
        k += 1
        product *= rng.random()
        if product <= threshold:
            return k - 1


def _nb1(rng: random.Random, mu: float, phi: float) -> int:
    """NB1 (linear-variance) draw: Gamma-Poisson mixture with Var = phi*mu.

    Gamma shape r = mu/(phi-1), scale theta = phi-1 gives E[g]=mu and
    Var(k) = mu + r*theta^2 = mu + mu*(phi-1) = phi*mu, matching the engine's
    quasi-Poisson (linear) variance assumption.
    """
    shape = mu / (phi - 1.0)
    scale = phi - 1.0
    lam = rng.gammavariate(shape, scale)
    return _poisson(rng, lam)


def _rate_interval_covers(count: int, true_mean: float, phi: float | None) -> bool:
    interval = rate_confidence_interval(
        count=count, exposure=_UNIT_EXPOSURE, overdispersion_phi=phi
    )
    return interval.ci_lower <= true_mean <= interval.ci_upper


def _meets_decision_gate(count_a: int, count_b: int) -> bool:
    # Mirrors the production decision floors: combined >= MIN_COMBINED_COUNT (10) and each
    # arm >= MIN_PLACE_COUNT (3). The interval is DISPLAYED even when no verdict fires, so
    # the single-rate coverage tests deliberately do not gate.
    return (count_a + count_b) >= 10 and count_a >= 3 and count_b >= 3


def _single_rate_coverage(mu: float, reps: int, seed: int, phi: float | None) -> float:
    rng = random.Random(seed)
    covered = 0
    for _ in range(reps):
        count = _poisson(rng, mu) if phi is None else _nb1(rng, mu, phi)
        if _rate_interval_covers(count, mu, phi):
            covered += 1
    return covered / reps


def _single_rate_coverage_estimated_phi(
    mu: float, reps: int, seed: int, true_phi: float
) -> float:
    """Coverage when phi is ESTIMATED from a simulated 12-month split (the 'practice' arm).

    Each replicate draws 12 monthly NB1 counts (per-month mean mu/12, same true phi),
    sums them for the annual count, and estimates phi via dispersion_status (the same
    Pearson variance/mean the engine uses). Both phi_hat AND the bin count are threaded into
    rate_confidence_interval exactly as production does (comparison.py / neighborhood_service),
    so the interval carries the t_{n_periods-1} phi-noise correction (here nu = 11).
    """
    rng = random.Random(seed)
    covered = 0
    for _ in range(reps):
        months = [_nb1(rng, mu / 12.0, true_phi) for _ in range(12)]
        count = sum(months)
        dispersion = dispersion_status(months)
        interval = rate_confidence_interval(
            count=count,
            exposure=_UNIT_EXPOSURE,
            overdispersion_phi=dispersion.phi,
            dispersion_periods=dispersion.n_periods,
        )
        if interval.ci_lower <= mu <= interval.ci_upper:
            covered += 1
    return covered / reps


def _two_sample_rejection(
    mu_a: float, mu_b: float, phi: float, reps: int, seed: int, dispersion_periods: int = 12
) -> tuple[float, float, int]:
    """Return (ungated_reject_rate, gated_reject_rate, gated_n) for 'p < 0.05'.

    When phi > 1 the true phi is passed together with dispersion_periods (default 12, one
    year of monthly bins) so the engine applies the exact t_{periods-1} quantile production
    uses; when phi == 1 the plain-Poisson (None) path is exercised -> z, as before. Passing
    the TRUE phi isolates the t-widening; production additionally ESTIMATES phi from the bins,
    which only adds noise and makes it strictly more conservative under the null.
    """
    rng = random.Random(seed)
    reject_all = 0
    reject_gated = 0
    gated_n = 0
    overdispersion = None if phi == 1.0 else phi
    periods = None if phi == 1.0 else dispersion_periods
    for _ in range(reps):
        if phi == 1.0:
            count_a, count_b = _poisson(rng, mu_a), _poisson(rng, mu_b)
        else:
            count_a, count_b = _nb1(rng, mu_a, phi), _nb1(rng, mu_b, phi)
        result = compare_incident_rates(
            count_a=count_a,
            exposure_a=_UNIT_EXPOSURE,
            count_b=count_b,
            exposure_b=_UNIT_EXPOSURE,
            overdispersion_phi=overdispersion,
            dispersion_periods=periods,
        )
        reject = result.p_value < 0.05
        reject_all += reject
        if _meets_decision_gate(count_a, count_b):
            gated_n += 1
            reject_gated += reject
    gated_rate = reject_gated / gated_n if gated_n else float("nan")
    return reject_all / reps, gated_rate, gated_n


# --- 2a. Single-rate interval coverage, Poisson ---------------------------------------


def test_single_rate_poisson_coverage_at_decision_floors():
    # Wald log interval is close to nominal; mildly conservative at low mu, dips slightly
    # below nominal at mu=15 (measured 0.9486). Pin floors at ~ measured - 2*MC-SE.
    floors = {3: 0.964, 5: 0.963, 10: 0.959, 15: 0.945}
    for mu, floor in floors.items():
        coverage = _single_rate_coverage(mu, reps=20000, seed=12345, phi=None)
        assert coverage >= floor, f"Poisson mu={mu} coverage {coverage:.4f} < {floor}"
        # Sanity: the interval is not absurdly over-wide either.
        assert coverage <= 0.99


# --- 2b. Single-rate interval coverage, NB1 with TRUE phi (the method's ceiling) ------


def test_single_rate_nb1_true_phi_coverage_is_near_nominal():
    # Passing the TRUE phi, the quasi-Poisson interval recovers ~nominal coverage across
    # phi in {3,7} and mu in {3,5,10,15}. This is the achievable ceiling.
    floors = {3: 0.948, 7: 0.948}
    for phi, floor in floors.items():
        for mu in (3, 5, 10, 15):
            coverage = _single_rate_coverage(mu, reps=20000, seed=4242, phi=float(phi))
            assert coverage >= floor, (
                f"NB1 true-phi phi={phi} mu={mu} coverage {coverage:.4f} < {floor}"
            )
            assert coverage <= 0.99


# --- 2c. Single-rate interval coverage, ESTIMATED phi (the 'practice' arm) -------------


def test_single_rate_estimated_phi_coverage_with_t_correction_is_pinned():
    # The estimated-phi interval now carries the quasi-likelihood t_{11} correction (12 bins ->
    # nu = 11), invoked exactly as production. That lifts coverage from the pre-fix ~0.83-0.91
    # to the values below; we PIN WHAT IS TRUE. floors ~ measured - 2*MC-SE (reps=10000 ->
    # 2*MC-SE ~= 0.006 near 0.89, ~0.003 near 0.98).
    floors = {
        (3, 5): 0.974,
        (3, 10): 0.939,
        (3, 15): 0.926,
        (7, 5): 0.974,
        (7, 10): 0.884,  # heavy overdispersion + small counts: still short of the 0.92 target
        (7, 15): 0.880,  # heavy overdispersion + small counts: still short of the 0.92 target
    }
    coverage = {
        (phi, mu): _single_rate_coverage_estimated_phi(
            mu, reps=10000, seed=2024, true_phi=float(phi)
        )
        for (phi, mu) in floors
    }
    for cell, floor in floors.items():
        assert coverage[cell] >= floor, f"estimated-phi {cell} {coverage[cell]:.4f} < {floor}"
    # ACCEPTANCE-GATE STATE (0.92 target). Four cells clear it; the two heavy-overdispersion
    # cells (phi=7, mu in {10,15}) remain below -- a documented residual of a fixed-df widening
    # against a very noisy 12-bin phi-hat. Pin that exact partition so it can't silently drift.
    clears_gate = {cell for cell, c in coverage.items() if c >= 0.92}
    assert clears_gate == {(3, 5), (3, 10), (3, 15), (7, 5)}
    assert coverage[(7, 10)] < 0.92 and coverage[(7, 15)] < 0.92
    # But the t correction is a real improvement over the z 'before' (0.8269 / 0.8459 there).
    assert coverage[(7, 10)] > 0.87 and coverage[(7, 15)] > 0.87


# --- 2d. Two-sample type-I under the null (must stay at or below nominal) --------------


def test_two_sample_type_i_is_conservative_under_null():
    # Equal true rates. In every cell the false-positive rate stays at or below nominal
    # 0.05 (ceiling pinned at ~ measured + 2*MC-SE, never exceeding ~0.05). Poisson tests
    # are mildly conservative at low counts; passing a true phi>1 is strongly conservative.
    # ceilings keyed by (mu, phi) -> (ungated_ceiling, gated_ceiling). The phi=1 cells use the
    # plain-Poisson (None) path -> z, so they are UNCHANGED by the t correction; the phi=3 cells
    # now apply t_{11} (periods=12) and are markedly MORE conservative than the z-'before'.
    ceilings = {
        (5, 1.0): (0.024, 0.013),
        (10, 1.0): (0.045, 0.042),
        (20, 1.0): (0.048, 0.048),
        (5, 3.0): (0.001, 0.001),
        (10, 3.0): (0.004, 0.004),
        (20, 3.0): (0.014, 0.014),
    }
    for (mu, phi), (ungated_ceiling, gated_ceiling) in ceilings.items():
        ungated, gated, gated_n = _two_sample_rejection(
            mu, mu, phi, reps=20000, seed=77
        )
        assert ungated <= ungated_ceiling, (
            f"type-I mu={mu} phi={phi} ungated {ungated:.4f} > {ungated_ceiling}"
        )
        assert gated <= gated_ceiling, (
            f"type-I mu={mu} phi={phi} gated {gated:.4f} > {gated_ceiling}"
        )
        # No cell may exceed the nominal alpha it advertises.
        assert ungated <= 0.05 and gated <= 0.05
        assert gated_n > 0


# --- 2e. Two-sample power under RR=0.5 (context only; power is low at the floor) -------


def test_two_sample_power_under_alternative_is_low_at_the_floor():
    # RR=0.5. Power ("p<0.05") is low at floor counts and climbs with mu; recorded here so
    # the engine's limited sensitivity at the decision floor is regression-pinned, not to
    # assert any adequacy. Floors at ~ measured - 2*MC-SE.
    # (mu_a, mu_b) -> gated power floor
    floors = {(5.0, 10.0): 0.149, (10.0, 20.0): 0.423, (20.0, 40.0): 0.730}
    prev = 0.0
    for (mu_a, mu_b), floor in floors.items():
        _ungated, gated, gated_n = _two_sample_rejection(
            mu_a, mu_b, 1.0, reps=20000, seed=55
        )
        assert gated >= floor, f"power mu_a={mu_a} mu_b={mu_b} {gated:.4f} < {floor}"
        assert gated > prev  # power increases with the count scale
        prev = gated
        assert gated_n > 0


def test_calibration_suite_runtime_is_fast():
    # The whole MC suite must stay well under the 10s budget; this bounds the heaviest cell.
    start = time.perf_counter()
    _single_rate_coverage_estimated_phi(10, reps=10000, seed=2024, true_phi=7.0)
    assert time.perf_counter() - start < 5.0
