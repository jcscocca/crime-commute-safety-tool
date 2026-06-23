from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exports.statistical import build_statistical_comparisons_csv
from app.models import StatisticalComparison, StatisticalPairwiseResult


def tableau_statistical_comparisons_csv(session: Session, user_id_hash: str) -> str:
    rows = session.execute(
        select(StatisticalComparison, StatisticalPairwiseResult)
        .join(
            StatisticalPairwiseResult,
            StatisticalPairwiseResult.comparison_id == StatisticalComparison.id,
        )
        .where(StatisticalComparison.user_id_hash == user_id_hash)
        .where(StatisticalPairwiseResult.user_id_hash == user_id_hash)
        .order_by(
            StatisticalComparison.created_at,
            StatisticalComparison.id,
            StatisticalPairwiseResult.option_a_label,
            StatisticalPairwiseResult.option_b_label,
        )
    ).all()
    return build_statistical_comparisons_csv(
        [_comparison_row(comparison, pairwise) for comparison, pairwise in rows]
    )


def _comparison_row(
    comparison: StatisticalComparison,
    pairwise: StatisticalPairwiseResult,
) -> dict[str, object]:
    return {
        "comparison_id": comparison.id,
        "comparison_type": comparison.comparison_type,
        "option_a_id": pairwise.option_a_id,
        "option_a_label": pairwise.option_a_label,
        "option_b_id": pairwise.option_b_id,
        "option_b_label": pairwise.option_b_label,
        "winner_option_id": pairwise.winner_option_id,
        "winner_label": pairwise.winner_label,
        "decision_class": pairwise.decision_class,
        "method": pairwise.method,
        "radius_m": comparison.radius_m,
        "analysis_start_date": comparison.analysis_start_date,
        "analysis_end_date": comparison.analysis_end_date,
        "offense_category": comparison.offense_category,
        "offense_subcategory": comparison.offense_subcategory,
        "incident_count_a": pairwise.incident_count_a,
        "incident_count_b": pairwise.incident_count_b,
        "exposure_a": pairwise.exposure_a,
        "exposure_b": pairwise.exposure_b,
        "exposure_unit": pairwise.exposure_unit,
        "rate_a": pairwise.rate_a,
        "rate_b": pairwise.rate_b,
        "rate_ratio": pairwise.rate_ratio,
        "ci_lower": pairwise.ci_lower,
        "ci_upper": pairwise.ci_upper,
        "p_value": pairwise.p_value,
        "adjusted_p_value": pairwise.adjusted_p_value,
        "overdispersion_phi": pairwise.overdispersion_phi,
        "overdispersion_status": pairwise.overdispersion_status,
        "minimum_data_status": pairwise.minimum_data_status,
        "overview_summary_text": comparison.overview_summary_text,
        "caveat_text": pairwise.caveat_text or comparison.full_caveat_text,
        "created_at": comparison.created_at,
    }
