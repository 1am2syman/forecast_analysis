"""Aggregate performance metrics for the filtered comparable population."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
import math
from typing import Literal

import polars as pl

from ._utils import require_columns
from .contracts import (
    ACTUAL_COLUMNS,
    DEFAULT_REVISION_TOLERANCE_KL,
    REVISION_CLASSIFICATION_DECIMAL_PLACES,
    normalize_revision_tolerance,
)
from .filters import with_display_brand

METRIC_COLUMNS = [
    "source",
    "snop_month",
    "forecast_accuracy_pct",
    "vintage_a_accuracy_pct",
    "vintage_b_accuracy_pct",
    "bias_pct",
    "absolute_error_kl",
    "actual_kl",
    "forecast_kl",
    "vintage_a_forecast_kl",
    "vintage_b_forecast_kl",
    "coverage_pct",
    "eligible_observations",
    "population_observations",
]
MONTHLY_METRIC_NAMES = {
    "accuracy": "forecast_accuracy_pct",
    "bias": "bias_pct",
    "absolute_error": "absolute_error_kl",
    "forecast_vs_actual": None,
}
MONTHLY_CHART_VALUE_COLUMNS = [
    "forecast_accuracy_pct",
    "vintage_a_accuracy_pct",
    "vintage_b_accuracy_pct",
    "bias_pct",
    "absolute_error_kl",
    "actual_kl",
    "forecast_kl",
    "vintage_a_forecast_kl",
    "vintage_b_forecast_kl",
    "coverage_pct",
]
HORIZON_METRIC_COLUMNS = [
    "source",
    "forecast_horizon_months",
    "horizon_label",
    "forecast_accuracy_pct",
    "bias_pct",
    "absolute_error_kl",
    "actual_kl",
    "forecast_kl",
    "coverage_pct",
    "eligible_observations",
    "population_observations",
    "missing_actual_observations",
    "zero_actual_observations",
]
HORIZON_METRIC_SCHEMA = {
    "source": pl.String,
    "forecast_horizon_months": pl.Int64,
    "horizon_label": pl.String,
    "forecast_accuracy_pct": pl.Float64,
    "bias_pct": pl.Float64,
    "absolute_error_kl": pl.Float64,
    "actual_kl": pl.Float64,
    "forecast_kl": pl.Float64,
    "coverage_pct": pl.Float64,
    "eligible_observations": pl.Int64,
    "population_observations": pl.Int64,
    "missing_actual_observations": pl.Int64,
    "zero_actual_observations": pl.Int64,
}
BRAND_TARGET_PERFORMANCE_COLUMNS = [
    "source",
    "brand_display",
    "snop_month",
    "forecast_accuracy_pct",
    "bias_pct",
    "absolute_error_kl",
    "vintage_a_accuracy_pct",
    "vintage_b_accuracy_pct",
    "accuracy_delta_pp",
    "revision_effectiveness_pct",
    "actual_kl",
    "forecast_kl",
    "coverage_pct",
    "eligible_observations",
    "vintage_a_eligible_observations",
    "vintage_b_eligible_observations",
    "absolute_error_observations",
    "population_observations",
    "complete_pairs",
    "improved_revisions",
    "materially_revised_observations",
    "vintage_a_actual_kl",
    "vintage_a_absolute_error_kl",
    "vintage_a_net_error_kl",
    "vintage_b_actual_kl",
    "vintage_b_absolute_error_kl",
    "vintage_b_net_error_kl",
]
BRAND_TARGET_PERFORMANCE_SCHEMA = {
    "source": pl.String,
    "brand_display": pl.String,
    "snop_month": pl.Date,
    "forecast_accuracy_pct": pl.Float64,
    "bias_pct": pl.Float64,
    "absolute_error_kl": pl.Float64,
    "vintage_a_accuracy_pct": pl.Float64,
    "vintage_b_accuracy_pct": pl.Float64,
    "accuracy_delta_pp": pl.Float64,
    "revision_effectiveness_pct": pl.Float64,
    "actual_kl": pl.Float64,
    "forecast_kl": pl.Float64,
    "coverage_pct": pl.Float64,
    "eligible_observations": pl.Int64,
    "vintage_a_eligible_observations": pl.Int64,
    "vintage_b_eligible_observations": pl.Int64,
    "absolute_error_observations": pl.Int64,
    "population_observations": pl.Int64,
    "complete_pairs": pl.Int64,
    "improved_revisions": pl.Int64,
    "materially_revised_observations": pl.Int64,
    "vintage_a_actual_kl": pl.Float64,
    "vintage_a_absolute_error_kl": pl.Float64,
    "vintage_a_net_error_kl": pl.Float64,
    "vintage_b_actual_kl": pl.Float64,
    "vintage_b_absolute_error_kl": pl.Float64,
    "vintage_b_net_error_kl": pl.Float64,
}

# column, label, unit, color scale, and worst-first sort policy
BRAND_TARGET_METRIC_DEFINITIONS: dict[str, tuple[str, str, str, str, str]] = {
    "forecast_accuracy": (
        "forecast_accuracy_pct",
        "Forecast accuracy",
        "%",
        "diverging",
        "ascending",
    ),
    "bias": ("bias_pct", "Bias", "%", "diverging", "absolute_descending"),
    "absolute_error": (
        "absolute_error_kl",
        "Absolute error",
        "KL",
        "sequential",
        "descending",
    ),
    "vintage_a_accuracy": (
        "vintage_a_accuracy_pct",
        "Vintage A accuracy",
        "%",
        "diverging",
        "ascending",
    ),
    "vintage_b_accuracy": (
        "vintage_b_accuracy_pct",
        "Vintage B accuracy",
        "%",
        "diverging",
        "ascending",
    ),
    "accuracy_delta": (
        "accuracy_delta_pp",
        "Accuracy delta",
        "pp",
        "diverging",
        "ascending",
    ),
    "revision_effectiveness": (
        "revision_effectiveness_pct",
        "Revision effectiveness",
        "%",
        "sequential",
        "ascending",
    ),
}


@dataclass(frozen=True)
class RevisionMetrics:
    """Revision KPIs calculated from complete, positive-actual pairs only."""

    accuracy_delta_pp: float | None = None
    revision_effectiveness_pct: float | None = None
    total_error_improvement_kl: float | None = None
    materially_revised_observations: int = 0
    improved_revisions: int = 0
    worsened_revisions: int = 0
    neutral_revisions: int = 0
    unchanged_revisions: int = 0
    revised_up_pct: float | None = None
    revised_down_pct: float | None = None
    effectiveness_numerator: int = 0
    effectiveness_denominator: int = 0
    accuracy_delta_numerator_kl: float | None = None
    accuracy_delta_denominator_actual_kl: float | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class MetricSummary:
    """KPI values plus the counts and arithmetic needed to audit them.

    Ratio metrics are calculated from the explicit numerator and denominator
    fields below. ``eligible_observations`` is the positive-actual row count;
    ``absolute_error_observations`` and ``mae_observations`` also include valid
    zero-actual rows because those rows have a defined error but no ratio
    denominator.
    """

    forecast_accuracy_pct: float | None
    wape_pct: float | None
    bias_pct: float | None
    absolute_error_kl: float | None
    actual_kl: float | None
    forecast_kl: float | None
    coverage_pct: float | None
    eligible_observations: int
    population_observations: int
    complete_pairs: int
    missing_vintage_pairs: int
    missing_actual_observations: int
    zero_actual_observations: int
    accuracy_delta_pp: float | None = None
    revision_effectiveness_pct: float | None = None
    total_error_improvement_kl: float | None = None
    materially_revised_observations: int = 0
    improved_revisions: int = 0
    worsened_revisions: int = 0
    neutral_revisions: int = 0
    unchanged_revisions: int = 0
    revised_up_pct: float | None = None
    revised_down_pct: float | None = None
    effectiveness_numerator: int = 0
    effectiveness_denominator: int = 0
    accuracy_delta_numerator_kl: float | None = None
    accuracy_delta_denominator_actual_kl: float | None = None
    mae_kl: float | None = None
    mae_observations: int = 0
    absolute_error_observations: int = 0
    accuracy_numerator_kl: float | None = None
    accuracy_denominator_actual_kl: float | None = None
    bias_numerator_kl: float | None = None
    bias_denominator_actual_kl: float | None = None
    coverage_numerator_actual_kl: float | None = None
    coverage_denominator_actual_kl: float | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


PAIR_METRIC_COLUMNS = [
    "vintage_a_calculation_month",
    "vintage_b_calculation_month",
    "vintage_b_forecast_kl",
    "actual_kl",
    "pair_status",
]


def _empty_summary(population_observations: int = 0) -> MetricSummary:
    return MetricSummary(
        forecast_accuracy_pct=None,
        wape_pct=None,
        bias_pct=None,
        absolute_error_kl=None,
        actual_kl=None,
        forecast_kl=None,
        coverage_pct=None,
        eligible_observations=0,
        population_observations=population_observations,
        complete_pairs=0,
        missing_vintage_pairs=0,
        missing_actual_observations=0,
        zero_actual_observations=0,
    )


def _sum_or_none(frame: pl.DataFrame, column: str) -> float | None:
    if frame.height == 0:
        return None
    value = frame.get_column(column).sum()
    if value is None:
        return None
    if isinstance(value, float):
        return value
    if isinstance(value, int):
        return value + 0.0
    raise TypeError(f"metric total is not numeric: {value!r}")


def brand_target_metric_definition(
    metric: str,
) -> tuple[str, str, str, str, str]:
    """Return the column, label, unit, scale, and sort policy for a heatmap metric."""
    try:
        return BRAND_TARGET_METRIC_DEFINITIONS[metric]
    except KeyError as exc:
        raise ValueError(
            f"unsupported brand target-month metric {metric!r}; "
            f"choose from {sorted(BRAND_TARGET_METRIC_DEFINITIONS)}"
        ) from exc


def _empty_revision_metrics() -> RevisionMetrics:
    return RevisionMetrics()


def calculate_revision_metrics(
    pair_frame: pl.DataFrame,
    revision_tolerance_kl: float = DEFAULT_REVISION_TOLERANCE_KL,
) -> RevisionMetrics:
    """Calculate accuracy delta and revision effectiveness from valid pairs.

    ``pair_status == "complete"`` is the sole revision-metric population. This
    excludes missing vintages, missing actuals, and zero actuals from both the
    effectiveness denominator and aggregate error-improvement numerator while
    leaving those rows available to coverage and exception views.
    """
    tolerance = normalize_revision_tolerance(revision_tolerance_kl)
    classification_tolerance = round(
        tolerance,
        REVISION_CLASSIFICATION_DECIMAL_PLACES,
    )
    if "vintage_a_forecast_kl" not in pair_frame.columns:
        return _empty_revision_metrics()
    require_columns(
        pair_frame,
        [
            "vintage_a_forecast_kl",
            "vintage_b_forecast_kl",
            "actual_kl",
            "pair_status",
        ],
        "revision pair population",
    )
    complete = pair_frame.filter(
        (pl.col("pair_status") == "complete")
        & pl.col("vintage_a_forecast_kl").is_not_null()
        & pl.col("vintage_b_forecast_kl").is_not_null()
        & pl.col("actual_kl").is_not_null()
    )
    if complete.height == 0:
        return _empty_revision_metrics()

    actual_total = _sum_or_none(complete, "actual_kl")
    a_absolute_error = (
        pl.col("vintage_a_forecast_kl") - pl.col("actual_kl")
    ).abs()
    b_absolute_error = (
        pl.col("vintage_b_forecast_kl") - pl.col("actual_kl")
    ).abs()
    complete_with_errors = complete.with_columns(
        a_absolute_error.alias("_a_absolute_error_kl"),
        b_absolute_error.alias("_b_absolute_error_kl"),
        (
            pl.col("vintage_b_forecast_kl")
            - pl.col("vintage_a_forecast_kl")
        ).cast(pl.Float64).alias("_revision_kl"),
    ).with_columns(
        (
            pl.col("_a_absolute_error_kl")
            - pl.col("_b_absolute_error_kl")
        ).cast(pl.Float64).alias("_error_improvement_kl")
    )
    a_error_total = _sum_or_none(complete_with_errors, "_a_absolute_error_kl")
    b_error_total = _sum_or_none(complete_with_errors, "_b_absolute_error_kl")
    total_error_improvement = _sum_or_none(
        complete_with_errors,
        "_error_improvement_kl",
    )
    accuracy_delta = None
    if (
        actual_total not in (None, 0)
        and a_error_total is not None
        and b_error_total is not None
    ):
        accuracy_delta = (a_error_total - b_error_total) / actual_total * 100

    revision_value = pl.col("_revision_kl").round(
        REVISION_CLASSIFICATION_DECIMAL_PLACES
    )
    improvement_value = pl.col("_error_improvement_kl").round(
        REVISION_CLASSIFICATION_DECIMAL_PLACES
    )
    materially_revised = complete_with_errors.filter(
        (revision_value > classification_tolerance)
        | (revision_value < -classification_tolerance)
    )
    improved = complete_with_errors.filter(
        improvement_value > classification_tolerance
    )
    worsened = complete_with_errors.filter(
        improvement_value < -classification_tolerance
    )
    neutral = complete_with_errors.filter(
        (improvement_value.abs() <= classification_tolerance)
        & (
            (revision_value > classification_tolerance)
            | (revision_value < -classification_tolerance)
        )
    )
    unchanged = complete_with_errors.filter(
        improvement_value.abs() <= classification_tolerance
    ).filter(
        revision_value.abs() <= classification_tolerance
    )
    effectiveness = None
    if materially_revised.height:
        effectiveness = improved.height / materially_revised.height * 100
    revised_up = complete_with_errors.filter(revision_value > classification_tolerance)
    revised_down = complete_with_errors.filter(
        revision_value < -classification_tolerance
    )

    return RevisionMetrics(
        accuracy_delta_pp=accuracy_delta,
        revision_effectiveness_pct=effectiveness,
        total_error_improvement_kl=total_error_improvement,
        materially_revised_observations=materially_revised.height,
        improved_revisions=improved.height,
        worsened_revisions=worsened.height,
        neutral_revisions=neutral.height,
        unchanged_revisions=unchanged.height,
        revised_up_pct=revised_up.height / complete.height * 100,
        revised_down_pct=revised_down.height / complete.height * 100,
        effectiveness_numerator=improved.height,
        effectiveness_denominator=materially_revised.height,
        accuracy_delta_numerator_kl=(
            a_error_total - b_error_total
            if a_error_total is not None and b_error_total is not None
            else None
        ),
        accuracy_delta_denominator_actual_kl=actual_total,
    )


def calculate_metrics(
    pair_frame: pl.DataFrame,
    selected_actual_population: pl.DataFrame,
    *,
    revision_tolerance_kl: float = DEFAULT_REVISION_TOLERANCE_KL,
) -> MetricSummary:
    """Calculate latest-vintage KPIs from aggregate numerators and denominators.

    Rows with a selected forecast and a real actual contribute to volume and
    absolute-error KPIs. Ratio metrics use only positive actuals. Zero actuals
    remain countable and visible but never create a zero denominator. Coverage
    uses the separately filtered actual population, which also contains
    product-target rows without a selected forecast.
    """
    require_columns(
        pair_frame,
        ["source", *PAIR_METRIC_COLUMNS],
        "vintage pair population",
    )
    require_columns(
        selected_actual_population,
        ACTUAL_COLUMNS,
        "selected actual population",
    )
    if pair_frame.height == 0:
        # Preserve a positive selected-actual denominator even when no selected
        # forecast is represented: coverage is explicitly 0 / denominator.
        total_actual = _sum_or_none(selected_actual_population, "actual_kl")
        return replace(
            _empty_summary(),
            coverage_pct=(
                0.0 if total_actual not in (None, 0) else None
            ),
            coverage_numerator_actual_kl=(
                0.0 if total_actual is not None else None
            ),
            coverage_denominator_actual_kl=total_actual,
        )
    source_series = pair_frame.get_column("source")
    if source_series.null_count():
        raise ValueError("vintage pair metrics require a non-null source column")
    sources = source_series.unique().to_list()
    if len(sources) != 1:
        raise ValueError(
            "vintage pair metrics require exactly one unique source; "
            f"received {sorted(sources)}"
        )
    revision_metrics = calculate_revision_metrics(
        pair_frame,
        revision_tolerance_kl,
    )

    selected_rows = pair_frame.filter(
        pl.col("pair_status").is_in(["complete", "zero_actual"])
        & pl.col("vintage_b_forecast_kl").is_not_null()
        & pl.col("actual_kl").is_not_null()
    )
    ratio_rows = pair_frame.filter(
        (pl.col("pair_status") == "complete")
        & (pl.col("actual_kl") > 0)
        & pl.col("vintage_b_forecast_kl").is_not_null()
    )

    if selected_rows.height:
        selected_with_error = selected_rows.with_columns(
            (pl.col("vintage_b_forecast_kl") - pl.col("actual_kl"))
            .alias("_error_kl")
        ).with_columns(pl.col("_error_kl").abs().alias("_absolute_error_kl"))
        absolute_error = _sum_or_none(selected_with_error, "_absolute_error_kl")
        actual_volume = _sum_or_none(selected_with_error, "actual_kl")
        forecast_volume = _sum_or_none(selected_with_error, "vintage_b_forecast_kl")
        mae = (
            absolute_error / selected_rows.height
            if absolute_error is not None
            else None
        )
    else:
        absolute_error = actual_volume = forecast_volume = mae = None

    accuracy = wape = bias = None
    ratio_abs_error = ratio_net_error = denominator = None
    if ratio_rows.height:
        ratio_with_error = ratio_rows.with_columns(
            (pl.col("vintage_b_forecast_kl") - pl.col("actual_kl"))
            .alias("_error_kl")
        ).with_columns(pl.col("_error_kl").abs().alias("_absolute_error_kl"))
        denominator = _sum_or_none(ratio_with_error, "actual_kl")
        if denominator not in (None, 0):
            ratio_abs_error = _sum_or_none(ratio_with_error, "_absolute_error_kl")
            ratio_net_error = _sum_or_none(ratio_with_error, "_error_kl")
            if ratio_abs_error is not None and ratio_net_error is not None:
                wape = ratio_abs_error / denominator * 100
                accuracy = (1 - ratio_abs_error / denominator) * 100
                bias = ratio_net_error / denominator * 100

    coverage_rows = pair_frame.filter(
        pl.col("vintage_b_calculation_month").is_not_null()
        & pl.col("vintage_b_forecast_kl").is_not_null()
        & pl.col("actual_kl").is_not_null()
    )
    represented_actual = _sum_or_none(coverage_rows, "actual_kl")
    total_actual = _sum_or_none(selected_actual_population, "actual_kl")
    if total_actual is not None and total_actual > 0:
        represented_actual = 0.0 if represented_actual is None else represented_actual
    coverage = None
    if total_actual not in (None, 0):
        coverage = (represented_actual or 0.0) / total_actual * 100

    complete_pairs = pair_frame.filter(pl.col("pair_status") == "complete").height
    missing_pairs = pair_frame.filter(
        pl.col("pair_status").is_in(["missing_a", "missing_b", "missing_both"])
    ).height
    missing_actual = pair_frame.filter(pl.col("pair_status") == "missing_actual").height
    zero_actual = pair_frame.filter(pl.col("pair_status") == "zero_actual").height

    return MetricSummary(
        forecast_accuracy_pct=accuracy,
        wape_pct=wape,
        bias_pct=bias,
        absolute_error_kl=absolute_error,
        actual_kl=actual_volume,
        forecast_kl=forecast_volume,
        coverage_pct=coverage,
        eligible_observations=ratio_rows.height,
        population_observations=pair_frame.height,
        complete_pairs=complete_pairs,
        missing_vintage_pairs=missing_pairs,
        missing_actual_observations=missing_actual,
        zero_actual_observations=zero_actual,
        accuracy_delta_pp=revision_metrics.accuracy_delta_pp,
        revision_effectiveness_pct=revision_metrics.revision_effectiveness_pct,
        total_error_improvement_kl=revision_metrics.total_error_improvement_kl,
        materially_revised_observations=revision_metrics.materially_revised_observations,
        improved_revisions=revision_metrics.improved_revisions,
        worsened_revisions=revision_metrics.worsened_revisions,
        neutral_revisions=revision_metrics.neutral_revisions,
        unchanged_revisions=revision_metrics.unchanged_revisions,
        revised_up_pct=revision_metrics.revised_up_pct,
        revised_down_pct=revision_metrics.revised_down_pct,
        effectiveness_numerator=revision_metrics.effectiveness_numerator,
        effectiveness_denominator=revision_metrics.effectiveness_denominator,
        accuracy_delta_numerator_kl=revision_metrics.accuracy_delta_numerator_kl,
        accuracy_delta_denominator_actual_kl=revision_metrics.accuracy_delta_denominator_actual_kl,
        mae_kl=mae,
        mae_observations=selected_rows.height,
        absolute_error_observations=selected_rows.height,
        accuracy_numerator_kl=ratio_abs_error,
        accuracy_denominator_actual_kl=denominator,
        bias_numerator_kl=ratio_net_error,
        bias_denominator_actual_kl=denominator,
        coverage_numerator_actual_kl=represented_actual,
        coverage_denominator_actual_kl=total_actual,
    )


REVISION_DIAGNOSTIC_COLUMNS = [
    "category",
    "observations",
    "share_of_complete_pairs_pct",
    "actual_kl",
    "revision_kl",
    "error_improvement_kl",
]
REVISION_DIAGNOSTIC_SCHEMA = {
    "category": pl.String,
    "observations": pl.Int64,
    "share_of_complete_pairs_pct": pl.Float64,
    "actual_kl": pl.Float64,
    "revision_kl": pl.Float64,
    "error_improvement_kl": pl.Float64,
}
REVISION_SCATTER_TARGET_MONTHS = 6
REVISION_SCATTER_VINTAGES_PER_MONTH = 5
REVISION_SCATTER_SCORE_TOLERANCE = 0.01
REVISION_SCATTER_COLUMNS = [
    "source",
    "parent_code",
    "parent_description",
    "brand",
    "sku_class",
    "snop_month",
    "window_start_month",
    "window_end_month",
    "actual_kl",
    "target_months_used",
    "vintages_per_month",
    "transitions_used",
    "revision_score_pct",
    "vintage_improvement_score_pp",
    "raw_revision_score_pct",
    "raw_vintage_improvement_score_pp",
    "winsorized_months",
    "improving_months",
    "degrading_months",
    "neutral_months",
    "revision_direction",
    "revision_outcome",
]
REVISION_SCATTER_SCHEMA = {
    "source": pl.String,
    "parent_code": pl.Int64,
    "parent_description": pl.String,
    "brand": pl.String,
    "sku_class": pl.String,
    "snop_month": pl.Date,
    "window_start_month": pl.Date,
    "window_end_month": pl.Date,
    "actual_kl": pl.Float64,
    "target_months_used": pl.Int64,
    "vintages_per_month": pl.Int64,
    "transitions_used": pl.Int64,
    "revision_score_pct": pl.Float64,
    "vintage_improvement_score_pp": pl.Float64,
    "raw_revision_score_pct": pl.Float64,
    "raw_vintage_improvement_score_pp": pl.Float64,
    "winsorized_months": pl.Int64,
    "improving_months": pl.Int64,
    "degrading_months": pl.Int64,
    "neutral_months": pl.Int64,
    "revision_direction": pl.String,
    "revision_outcome": pl.String,
}
LEGACY_REVISION_SCATTER_COLUMNS = [
    "source",
    "parent_code",
    "parent_description",
    "brand",
    "snop_month",
    "actual_kl",
    "vintage_a_calculation_month",
    "vintage_a_horizon_months",
    "vintage_a_forecast_kl",
    "vintage_b_calculation_month",
    "vintage_b_horizon_months",
    "vintage_b_forecast_kl",
    "vintage_a_absolute_error_kl",
    "vintage_b_absolute_error_kl",
    "revision_kl",
    "error_improvement_kl",
    "revision_direction",
    "revision_outcome",
]


def build_revision_diagnostics(pair_frame: pl.DataFrame) -> pl.DataFrame:
    """Summarize improved, worsened, neutral, and unchanged valid pairs."""
    require_columns(
        pair_frame,
        [
            "pair_status",
            "actual_kl",
            "revision_kl",
            "error_improvement_kl",
            "revision_direction",
            "revision_outcome",
        ],
        "revision diagnostic population",
    )
    complete = pair_frame.filter(pl.col("pair_status") == "complete")
    categories = {
        "improved": complete.filter(pl.col("revision_outcome") == "improved"),
        "worsened": complete.filter(pl.col("revision_outcome") == "worsened"),
        "neutral": complete.filter(
            (pl.col("revision_outcome") == "neutral")
            & (pl.col("revision_direction") != "unchanged")
        ),
        "unchanged": complete.filter(pl.col("revision_direction") == "unchanged"),
    }
    rows: list[dict[str, object]] = []
    for category, subset in categories.items():
        rows.append(
            {
                "category": category,
                "observations": subset.height,
                "share_of_complete_pairs_pct": (
                    subset.height / complete.height * 100
                    if complete.height
                    else None
                ),
                "actual_kl": _sum_or_none(subset, "actual_kl") or 0.0,
                "revision_kl": _sum_or_none(subset, "revision_kl") or 0.0,
                "error_improvement_kl": (
                    _sum_or_none(subset, "error_improvement_kl") or 0.0
                ),
            }
        )
    return pl.DataFrame(rows, schema=REVISION_DIAGNOSTIC_SCHEMA).select(
        REVISION_DIAGNOSTIC_COLUMNS
    )


def _empty_revision_scatter() -> pl.DataFrame:
    return pl.DataFrame(schema=REVISION_SCATTER_SCHEMA).select(
        REVISION_SCATTER_COLUMNS
    )


def _legacy_revision_scatter(pair_frame: pl.DataFrame) -> pl.DataFrame:
    """Preserve the pair-point projection used by hidden comparison payloads."""
    require_columns(
        pair_frame,
        LEGACY_REVISION_SCATTER_COLUMNS + ["pair_status"],
        "revision scatter pair population",
    )
    return pair_frame.filter(pl.col("pair_status") == "complete").select(
        LEGACY_REVISION_SCATTER_COLUMNS
    )


def build_revision_scatter(
    frame: pl.DataFrame,
    *,
    target_end_month: object | None = None,
) -> pl.DataFrame:
    """Return one robust six-month, five-vintage score per parent product.

    Each target month contributes a least-squares trend across its five latest
    forecast vintages. Forecast movement is normalized by actual volume and the
    accuracy trend is expressed in percentage points per vintage. Monthly trends
    are retained as calculated, including seasonal extremes. The parent bubble
    uses the median of the six monthly trends, so one volatile month cannot
    dominate.
    """
    history_columns = {
        "source",
        "parent_code",
        "parent_description",
        "brand",
        "snop_month",
        "calculation_month",
        "forecast_kl",
        "actual_kl",
    }
    if not history_columns.issubset(frame.columns):
        return _legacy_revision_scatter(frame)
    require_columns(frame, sorted(history_columns), "revision scatter history")
    if frame.height == 0:
        return _empty_revision_scatter()
    if "sku_class" not in frame.columns:
        frame = frame.with_columns(pl.lit("Unclassified").alias("sku_class"))

    end_month = target_end_month
    if end_month is None:
        end_month = frame.get_column("snop_month").drop_nulls().max()
    if isinstance(end_month, datetime):
        end_month = end_month.date()
    if not isinstance(end_month, date):
        return _empty_revision_scatter()
    available_months = sorted(
        frame.filter(pl.col("snop_month") <= end_month)
        .get_column("snop_month")
        .drop_nulls()
        .unique()
        .to_list()
    )[-REVISION_SCATTER_TARGET_MONTHS:]
    if len(available_months) < REVISION_SCATTER_TARGET_MONTHS:
        return _empty_revision_scatter()

    keys = ["source", "parent_code", "snop_month"]
    candidates = (
        frame.filter(
            pl.col("snop_month").is_in(available_months)
            & pl.col("calculation_month").is_not_null()
            & pl.col("forecast_kl").is_not_null()
            & pl.col("actual_kl").is_not_null()
            & (pl.col("actual_kl") > 0)
        )
        .unique(subset=[*keys, "calculation_month"], keep="last")
        .sort([*keys, "calculation_month"])
        .group_by(keys, maintain_order=True)
        .tail(REVISION_SCATTER_VINTAGES_PER_MONTH)
    )
    complete_months = (
        candidates.group_by(keys)
        .agg(pl.col("calculation_month").n_unique().alias("_vintage_count"))
        .filter(
            pl.col("_vintage_count")
            == REVISION_SCATTER_VINTAGES_PER_MONTH
        )
        .select(keys)
    )
    if complete_months.height == 0:
        return _empty_revision_scatter()

    points = (
        candidates.join(complete_months, on=keys, how="semi")
        .sort([*keys, "calculation_month"])
        .with_columns(
            (
                pl.col("calculation_month")
                .rank("ordinal")
                .over(keys)
                .cast(pl.Float64)
                - 1
            ).alias("_vintage_index"),
            (pl.col("forecast_kl") / pl.col("actual_kl") * 100).alias(
                "_forecast_pct_actual"
            ),
            (
                1
                - (pl.col("forecast_kl") - pl.col("actual_kl")).abs()
                / pl.col("actual_kl")
            )
            .mul(100)
            .alias("_forecast_accuracy_pct"),
        )
    )
    centered_index = pl.col("_vintage_index") - 2.0
    monthly = points.group_by(keys).agg(
        pl.col("parent_description").first(),
        pl.col("brand").first(),
        pl.col("sku_class").first().fill_null("Unclassified"),
        pl.col("actual_kl").first().cast(pl.Float64),
        (centered_index * pl.col("_forecast_pct_actual"))
        .sum()
        .truediv(10.0)
        .alias("_revision_score_pct"),
        (centered_index * pl.col("_forecast_accuracy_pct"))
        .sum()
        .truediv(10.0)
        .alias("_vintage_improvement_score_pp"),
    )
    parent_keys = ["source", "parent_code"]
    parent_scores = (
        monthly.group_by(parent_keys)
        .agg(
            pl.col("parent_description").first(),
            pl.col("brand").first(),
            pl.col("sku_class")
            .filter(pl.col("snop_month") == available_months[-1])
            .first()
            .fill_null("Unclassified"),
            pl.col("actual_kl").sum().cast(pl.Float64),
            pl.col("snop_month").n_unique().cast(pl.Int64).alias(
                "target_months_used"
            ),
            pl.col("_revision_score_pct").median().alias(
                "revision_score_pct"
            ),
            pl.col("_vintage_improvement_score_pp").median().alias(
                "vintage_improvement_score_pp"
            ),
            pl.col("_revision_score_pct").median().alias(
                "raw_revision_score_pct"
            ),
            pl.col("_vintage_improvement_score_pp").median().alias(
                "raw_vintage_improvement_score_pp"
            ),
            pl.lit(0, dtype=pl.Int64).alias("winsorized_months"),
            (pl.col("_vintage_improvement_score_pp") > REVISION_SCATTER_SCORE_TOLERANCE)
            .cast(pl.Int64)
            .sum()
            .alias("improving_months"),
            (pl.col("_vintage_improvement_score_pp") < -REVISION_SCATTER_SCORE_TOLERANCE)
            .cast(pl.Int64)
            .sum()
            .alias("degrading_months"),
            (pl.col("_vintage_improvement_score_pp").abs() <= REVISION_SCATTER_SCORE_TOLERANCE)
            .cast(pl.Int64)
            .sum()
            .alias("neutral_months"),
        )
        .filter(
            pl.col("target_months_used")
            == REVISION_SCATTER_TARGET_MONTHS
        )
    )
    if parent_scores.height == 0:
        return _empty_revision_scatter()

    return (
        parent_scores.with_columns(
            pl.lit(available_months[-1], dtype=pl.Date).alias("snop_month"),
            pl.lit(available_months[0], dtype=pl.Date).alias(
                "window_start_month"
            ),
            pl.lit(available_months[-1], dtype=pl.Date).alias(
                "window_end_month"
            ),
            pl.lit(REVISION_SCATTER_VINTAGES_PER_MONTH, dtype=pl.Int64).alias(
                "vintages_per_month"
            ),
            pl.lit(
                REVISION_SCATTER_TARGET_MONTHS
                * (REVISION_SCATTER_VINTAGES_PER_MONTH - 1),
                dtype=pl.Int64,
            ).alias("transitions_used"),
            pl.when(
                pl.col("revision_score_pct")
                > REVISION_SCATTER_SCORE_TOLERANCE
            )
            .then(pl.lit("up"))
            .when(
                pl.col("revision_score_pct")
                < -REVISION_SCATTER_SCORE_TOLERANCE
            )
            .then(pl.lit("down"))
            .otherwise(pl.lit("unchanged"))
            .alias("revision_direction"),
            pl.when(
                pl.col("vintage_improvement_score_pp")
                > REVISION_SCATTER_SCORE_TOLERANCE
            )
            .then(pl.lit("improved"))
            .when(
                pl.col("vintage_improvement_score_pp")
                < -REVISION_SCATTER_SCORE_TOLERANCE
            )
            .then(pl.lit("worsened"))
            .otherwise(pl.lit("neutral"))
            .alias("revision_outcome"),
        )
        .select(REVISION_SCATTER_COLUMNS)
        .sort(["source", "parent_code"])
    )


MONTHLY_METRIC_SCHEMA = {
    "source": pl.String,
    "snop_month": pl.Date,
    "forecast_accuracy_pct": pl.Float64,
    "vintage_a_accuracy_pct": pl.Float64,
    "vintage_b_accuracy_pct": pl.Float64,
    "bias_pct": pl.Float64,
    "absolute_error_kl": pl.Float64,
    "actual_kl": pl.Float64,
    "forecast_kl": pl.Float64,
    "vintage_a_forecast_kl": pl.Float64,
    "vintage_b_forecast_kl": pl.Float64,
    "coverage_pct": pl.Float64,
    "eligible_observations": pl.Int64,
    "population_observations": pl.Int64,
}


def _sum_if(condition: pl.Expr, value: pl.Expr, alias: str) -> pl.Expr:
    return (
        pl.when(condition)
        .then(value.cast(pl.Float64))
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .sum()
        .alias(alias)
    )


def _count_if(condition: pl.Expr, alias: str) -> pl.Expr:
    return condition.fill_null(False).cast(pl.Int64).sum().alias(alias)


def _aggregate_pair_metric_components(
    pair_frame: pl.DataFrame,
    group_columns: list[str],
    revision_tolerance_kl: float = DEFAULT_REVISION_TOLERANCE_KL,
) -> pl.DataFrame:
    """Aggregate pair arithmetic once for all grouped metric projections."""
    require_columns(
        pair_frame,
        [
            *group_columns,
            "actual_kl",
            "vintage_a_forecast_kl",
            "vintage_b_forecast_kl",
            "pair_status",
        ],
        "grouped vintage pair population",
    )
    tolerance = round(
        normalize_revision_tolerance(revision_tolerance_kl),
        REVISION_CLASSIFICATION_DECIMAL_PLACES,
    )
    actual = pl.col("actual_kl")
    vintage_a = pl.col("vintage_a_forecast_kl")
    vintage_b = pl.col("vintage_b_forecast_kl")
    complete = pl.col("pair_status") == "complete"
    selected_status = pl.col("pair_status").is_in(["complete", "zero_actual"])
    selected_a = selected_status & actual.is_not_null() & vintage_a.is_not_null()
    selected_b = selected_status & actual.is_not_null() & vintage_b.is_not_null()
    ratio_a = complete & (actual > 0) & vintage_a.is_not_null()
    ratio_b = complete & (actual > 0) & vintage_b.is_not_null()
    revision_valid = (
        complete
        & actual.is_not_null()
        & vintage_a.is_not_null()
        & vintage_b.is_not_null()
    )
    coverage_b = selected_b
    if "vintage_b_calculation_month" in pair_frame.columns:
        coverage_b = (
            pl.col("vintage_b_calculation_month").is_not_null()
            & vintage_b.is_not_null()
            & actual.is_not_null()
        )

    a_error = vintage_a - actual
    b_error = vintage_b - actual
    revision = (vintage_b - vintage_a).round(
        REVISION_CLASSIFICATION_DECIMAL_PLACES
    )
    error_improvement = (
        a_error.abs() - b_error.abs()
    ).round(REVISION_CLASSIFICATION_DECIMAL_PLACES)

    grouped = pair_frame.group_by(group_columns).agg(
        pl.len().cast(pl.Int64).alias("population_observations"),
        _count_if(selected_a, "_a_selected_count"),
        _sum_if(selected_a, actual, "_a_selected_actual_sum"),
        _sum_if(selected_a, vintage_a, "_a_selected_forecast_sum"),
        _sum_if(selected_a, a_error.abs(), "_a_selected_absolute_error_sum"),
        _count_if(ratio_a, "_a_ratio_count"),
        _sum_if(ratio_a, actual, "_a_ratio_actual_sum"),
        _sum_if(ratio_a, a_error.abs(), "_a_ratio_absolute_error_sum"),
        _sum_if(ratio_a, a_error, "_a_ratio_net_error_sum"),
        _count_if(selected_b, "_b_selected_count"),
        _sum_if(selected_b, actual, "_b_selected_actual_sum"),
        _sum_if(selected_b, vintage_b, "_b_selected_forecast_sum"),
        _sum_if(selected_b, b_error.abs(), "_b_selected_absolute_error_sum"),
        _count_if(ratio_b, "_b_ratio_count"),
        _sum_if(ratio_b, actual, "_b_ratio_actual_sum"),
        _sum_if(ratio_b, b_error.abs(), "_b_ratio_absolute_error_sum"),
        _sum_if(ratio_b, b_error, "_b_ratio_net_error_sum"),
        _count_if(coverage_b, "_coverage_count"),
        _sum_if(coverage_b, actual, "_coverage_actual_sum"),
        _count_if(complete, "complete_pairs"),
        _count_if(pl.col("pair_status") == "missing_actual", "missing_actual_observations"),
        _count_if(pl.col("pair_status") == "zero_actual", "zero_actual_observations"),
        _count_if(revision_valid, "_revision_count"),
        _sum_if(revision_valid, actual, "_revision_actual_sum"),
        _sum_if(revision_valid, a_error.abs(), "_revision_a_absolute_error_sum"),
        _sum_if(revision_valid, b_error.abs(), "_revision_b_absolute_error_sum"),
        _count_if(
            revision_valid & ((revision > tolerance) | (revision < -tolerance)),
            "materially_revised_observations",
        ),
        _count_if(
            revision_valid & (error_improvement > tolerance),
            "improved_revisions",
        ),
    )
    valid_a_ratio = (
        (pl.col("_a_ratio_count") > 0)
        & (pl.col("_a_ratio_actual_sum") != 0)
    )
    valid_b_ratio = (
        (pl.col("_b_ratio_count") > 0)
        & (pl.col("_b_ratio_actual_sum") != 0)
    )
    return grouped.with_columns(
        pl.when(valid_b_ratio)
        .then(
            (1 - pl.col("_b_ratio_absolute_error_sum") / pl.col("_b_ratio_actual_sum"))
            * 100
        )
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("forecast_accuracy_pct"),
        pl.when(valid_a_ratio)
        .then(
            (1 - pl.col("_a_ratio_absolute_error_sum") / pl.col("_a_ratio_actual_sum"))
            * 100
        )
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("vintage_a_accuracy_pct"),
        pl.when(valid_b_ratio)
        .then(
            (1 - pl.col("_b_ratio_absolute_error_sum") / pl.col("_b_ratio_actual_sum"))
            * 100
        )
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("vintage_b_accuracy_pct"),
        pl.when(valid_b_ratio)
        .then(pl.col("_b_ratio_net_error_sum") / pl.col("_b_ratio_actual_sum") * 100)
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("bias_pct"),
        pl.when(pl.col("_b_selected_count") > 0)
        .then(pl.col("_b_selected_absolute_error_sum"))
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("absolute_error_kl"),
        pl.when(pl.col("_b_selected_count") > 0)
        .then(pl.col("_b_selected_actual_sum"))
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("actual_kl"),
        pl.when(pl.col("_b_selected_count") > 0)
        .then(pl.col("_b_selected_forecast_sum"))
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("forecast_kl"),
        pl.when(pl.col("_a_selected_count") > 0)
        .then(pl.col("_a_selected_forecast_sum"))
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("vintage_a_forecast_kl"),
        pl.when(pl.col("_b_selected_count") > 0)
        .then(pl.col("_b_selected_forecast_sum"))
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("vintage_b_forecast_kl"),
        pl.col("_b_ratio_count").alias("eligible_observations"),
        pl.col("_a_ratio_count").alias("vintage_a_eligible_observations"),
        pl.col("_b_ratio_count").alias("vintage_b_eligible_observations"),
        pl.col("_b_selected_count").alias("absolute_error_observations"),
        pl.when(valid_a_ratio)
        .then(pl.col("_a_ratio_actual_sum"))
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("vintage_a_actual_kl"),
        pl.when(valid_a_ratio)
        .then(pl.col("_a_ratio_absolute_error_sum"))
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("vintage_a_absolute_error_kl"),
        pl.when(valid_a_ratio)
        .then(pl.col("_a_ratio_net_error_sum"))
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("vintage_a_net_error_kl"),
        pl.when(valid_b_ratio)
        .then(pl.col("_b_ratio_actual_sum"))
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("vintage_b_actual_kl"),
        pl.when(valid_b_ratio)
        .then(pl.col("_b_ratio_absolute_error_sum"))
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("vintage_b_absolute_error_kl"),
        pl.when(valid_b_ratio)
        .then(pl.col("_b_ratio_net_error_sum"))
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("vintage_b_net_error_kl"),
        pl.when(
            (pl.col("_revision_count") > 0)
            & (pl.col("_revision_actual_sum") != 0)
        )
        .then(
            (
                pl.col("_revision_a_absolute_error_sum")
                - pl.col("_revision_b_absolute_error_sum")
            )
            / pl.col("_revision_actual_sum")
            * 100
        )
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("accuracy_delta_pp"),
        pl.when(pl.col("materially_revised_observations") > 0)
        .then(
            pl.col("improved_revisions")
            / pl.col("materially_revised_observations")
            * 100
        )
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("revision_effectiveness_pct"),
        pl.when(pl.col("_b_ratio_count") > 0)
        .then(pl.col("_b_ratio_absolute_error_sum"))
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("accuracy_numerator_kl"),
        pl.when(valid_b_ratio)
        .then(pl.col("_b_ratio_actual_sum"))
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("accuracy_denominator_actual_kl"),
        pl.when(pl.col("_b_ratio_count") > 0)
        .then(pl.col("_b_ratio_net_error_sum"))
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("bias_numerator_kl"),
        pl.when(valid_b_ratio)
        .then(pl.col("_b_ratio_actual_sum"))
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("bias_denominator_actual_kl"),
        pl.when(pl.col("_b_selected_count") > 0)
        .then(
            pl.col("_b_selected_absolute_error_sum")
            / pl.col("_b_selected_count")
        )
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("mae_kl"),
        pl.col("_b_selected_count").alias("mae_observations"),
        pl.when(pl.col("_coverage_count") > 0)
        .then(pl.col("_coverage_actual_sum"))
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("_coverage_actual_kl"),
    )


def _with_coverage_metrics(
    frame: pl.DataFrame,
    numerator_column: str,
) -> pl.DataFrame:
    denominator = pl.col("coverage_denominator_actual_kl")
    numerator = pl.col(numerator_column)
    normalized_numerator = (
        pl.when(denominator.is_not_null() & (denominator > 0))
        .then(numerator.fill_null(0.0))
        .otherwise(numerator)
    )
    return frame.with_columns(
        normalized_numerator.alias("coverage_numerator_actual_kl"),
        pl.when(denominator.is_not_null() & (denominator != 0))
        .then(numerator.fill_null(0.0) / denominator * 100)
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("coverage_pct"),
    )


def _build_monthly_metric_table(
    pair_frame: pl.DataFrame,
    selected_actual_population: pl.DataFrame,
) -> pl.DataFrame:
    require_columns(
        pair_frame,
        ["source", "snop_month", *PAIR_METRIC_COLUMNS],
        "vintage pair population",
    )
    require_columns(
        selected_actual_population,
        ACTUAL_COLUMNS,
        "selected actual population",
    )
    audit_schema = {**MONTHLY_METRIC_SCHEMA, **_AUDIT_CONTEXT_SCHEMA}
    if pair_frame.height == 0:
        return pl.DataFrame(schema=audit_schema).select(
            [*METRIC_COLUMNS, *_AUDIT_CONTEXT_COLUMNS]
        )

    components = _aggregate_pair_metric_components(
        pair_frame,
        ["source", "snop_month"],
    )
    actual_totals = selected_actual_population.group_by("snop_month").agg(
        pl.col("actual_kl")
        .sum()
        .cast(pl.Float64)
        .alias("coverage_denominator_actual_kl")
    )
    return (
        _with_coverage_metrics(
            components.join(actual_totals, on="snop_month", how="left"),
            "_coverage_actual_kl",
        )
        .select([*METRIC_COLUMNS, *_AUDIT_CONTEXT_COLUMNS])
        .sort(["source", "snop_month"])
    )


def project_monthly_performance(monthly_audit: pl.DataFrame) -> pl.DataFrame:
    """Project only periods that can contribute to a monthly line chart."""
    require_columns(monthly_audit, METRIC_COLUMNS, "monthly metric audit")
    has_chart_value = pl.any_horizontal(
        [pl.col(column).is_not_null() for column in MONTHLY_CHART_VALUE_COLUMNS]
    )
    return monthly_audit.filter(has_chart_value).select(METRIC_COLUMNS)


def build_monthly_performance(
    pair_frame: pl.DataFrame,
    selected_actual_population: pl.DataFrame,
) -> pl.DataFrame:
    """Return plottable aggregate KPI columns by target month for chart reuse."""
    return project_monthly_performance(
        _build_monthly_metric_table(pair_frame, selected_actual_population)
    )


_AUDIT_CONTEXT_COLUMNS = [
    "accuracy_numerator_kl",
    "accuracy_denominator_actual_kl",
    "bias_numerator_kl",
    "bias_denominator_actual_kl",
    "coverage_numerator_actual_kl",
    "coverage_denominator_actual_kl",
    "mae_kl",
    "mae_observations",
    "absolute_error_observations",
]
_AUDIT_CONTEXT_SCHEMA = {
    "accuracy_numerator_kl": pl.Float64,
    "accuracy_denominator_actual_kl": pl.Float64,
    "bias_numerator_kl": pl.Float64,
    "bias_denominator_actual_kl": pl.Float64,
    "coverage_numerator_actual_kl": pl.Float64,
    "coverage_denominator_actual_kl": pl.Float64,
    "mae_kl": pl.Float64,
    "mae_observations": pl.Int64,
    "absolute_error_observations": pl.Int64,
}


def build_monthly_audit(
    pair_frame: pl.DataFrame,
    selected_actual_population: pl.DataFrame,
) -> pl.DataFrame:
    """Return monthly metrics with exact numerator and denominator context."""
    return _build_monthly_metric_table(pair_frame, selected_actual_population)


def _horizon_label_expression() -> pl.Expr:
    horizon = pl.col("forecast_horizon_months")
    return (
        pl.when(horizon == 0)
        .then(pl.lit("Current month"))
        .when(horizon == 1)
        .then(pl.lit("1 month ahead"))
        .otherwise(pl.concat_str([horizon.cast(pl.String), pl.lit(" months ahead")]))
        .alias("horizon_label")
    )


def _build_horizon_metric_table(
    frame: pl.DataFrame,
    selected_actual_population: pl.DataFrame,
) -> pl.DataFrame:
    require_columns(
        frame,
        [
            "source",
            "calculation_month",
            "forecast_horizon_months",
            "forecast_kl",
            "actual_kl",
            "actual_status",
        ],
        "horizon performance population",
    )
    require_columns(
        selected_actual_population,
        ACTUAL_COLUMNS,
        "selected actual population",
    )
    audit_schema = {**HORIZON_METRIC_SCHEMA, **_AUDIT_CONTEXT_SCHEMA}
    if frame.height == 0:
        return pl.DataFrame(schema=audit_schema).select(
            [*HORIZON_METRIC_COLUMNS, *_AUDIT_CONTEXT_COLUMNS]
        )

    pair_projection = frame.select(
        [
            "source",
            "forecast_horizon_months",
            pl.lit(None, dtype=pl.Float64).alias("vintage_a_forecast_kl"),
            pl.col("calculation_month").alias("vintage_b_calculation_month"),
            pl.col("forecast_kl").alias("vintage_b_forecast_kl"),
            "actual_kl",
            pl.when(pl.col("actual_status") == "missing")
            .then(pl.lit("missing_actual"))
            .when(pl.col("actual_status") == "matched_zero")
            .then(pl.lit("zero_actual"))
            .otherwise(pl.lit("complete"))
            .alias("pair_status"),
        ]
    )
    components = _aggregate_pair_metric_components(
        pair_projection,
        ["source", "forecast_horizon_months"],
    )
    total_actual = _sum_or_none(selected_actual_population, "actual_kl")
    return (
        _with_coverage_metrics(
            components.with_columns(
                pl.lit(total_actual, dtype=pl.Float64).alias(
                    "coverage_denominator_actual_kl"
                )
            ),
            "_coverage_actual_kl",
        )
        .with_columns(_horizon_label_expression())
        .select([*HORIZON_METRIC_COLUMNS, *_AUDIT_CONTEXT_COLUMNS])
        .sort(
            ["source", "forecast_horizon_months"],
            descending=[False, True],
        )
    )


def build_horizon_audit(
    frame: pl.DataFrame,
    selected_actual_population: pl.DataFrame,
) -> pl.DataFrame:
    """Return horizon metrics with exact numerator and denominator context."""
    return _build_horizon_metric_table(frame, selected_actual_population)


def build_brand_target_month_performance(
    pair_frame: pl.DataFrame,
    selected_actual_population: pl.DataFrame,
    *,
    revision_tolerance_kl: float = DEFAULT_REVISION_TOLERANCE_KL,
) -> pl.DataFrame:
    """Aggregate one comparable row per brand and target month.

    The input is the already-selected Vintage A/B pair frame, not the long
    history. That keeps each parent product and target month at one row and
    prevents repeated vintages or hierarchy records from multiplying volume.
    ``All brands`` is calculated from the same filtered pair population. Revision
    metrics use the supplied tolerance so the heatmap matches the dashboard KPIs.
    """
    require_columns(
        pair_frame,
        [
            "source",
            "brand",
            "mapping_status",
            "snop_month",
            "actual_kl",
            "vintage_a_forecast_kl",
            "vintage_b_forecast_kl",
            "pair_status",
        ],
        "brand target-month pair population",
    )
    require_columns(
        selected_actual_population,
        ACTUAL_COLUMNS,
        "selected actual population",
    )
    tolerance = normalize_revision_tolerance(revision_tolerance_kl)
    actual_population = selected_actual_population
    if "brand" not in actual_population.columns:
        actual_population = actual_population.with_columns(
            pl.lit(None, dtype=pl.String).alias("brand")
        )
    if "mapping_status" not in actual_population.columns:
        actual_population = actual_population.with_columns(
            pl.lit("unmapped").alias("mapping_status")
        )

    paired = with_display_brand(pair_frame)
    if paired.height == 0:
        return pl.DataFrame(schema=BRAND_TARGET_PERFORMANCE_SCHEMA).select(
            BRAND_TARGET_PERFORMANCE_COLUMNS
        )
    actuals = with_display_brand(actual_population)
    grouped_pairs = pl.concat(
        [
            paired.with_columns(pl.lit(False).alias("_all_brands")),
            paired.with_columns(
                pl.lit(True).alias("_all_brands"),
                pl.lit(None, dtype=pl.String).alias("brand_display"),
            ),
        ],
        how="vertical",
    )
    components = _aggregate_pair_metric_components(
        grouped_pairs,
        ["source", "_all_brands", "brand_display", "snop_month"],
        tolerance,
    )
    actual_totals = pl.concat(
        [
            actuals.with_columns(pl.lit(False).alias("_all_brands"))
            .group_by(["_all_brands", "brand_display", "snop_month"])
            .agg(
                pl.col("actual_kl")
                .sum()
                .cast(pl.Float64)
                .alias("coverage_denominator_actual_kl")
            ),
            actuals.group_by("snop_month")
            .agg(
                pl.col("actual_kl")
                .sum()
                .cast(pl.Float64)
                .alias("coverage_denominator_actual_kl")
            )
            .with_columns(
                pl.lit(True).alias("_all_brands"),
                pl.lit(None, dtype=pl.String).alias("brand_display"),
            )
            .select(
                [
                    "_all_brands",
                    "brand_display",
                    "snop_month",
                    "coverage_denominator_actual_kl",
                ]
            ),
        ],
        how="vertical",
    )
    return (
        _with_coverage_metrics(
            components.join(
                actual_totals,
                on=["_all_brands", "brand_display", "snop_month"],
                how="left",
                nulls_equal=True,
            ),
            "actual_kl",
        )
        .with_columns(
            pl.when(pl.col("_all_brands"))
            .then(pl.lit("All brands"))
            .otherwise(pl.col("brand_display"))
            .alias("brand_display")
        )
        .sort(
            ["source", "snop_month", "_all_brands", "brand_display"],
            descending=[False, False, True, False],
            nulls_last=True,
        )
        .select(BRAND_TARGET_PERFORMANCE_COLUMNS)
    )


def _aggregate_brand_sort_values(
    frame: pl.DataFrame,
    metric: str,
) -> tuple[pl.DataFrame, bool]:
    """Build brand sort keys from aggregate components, never monthly ratios."""
    brand_target_metric_definition(metric)
    brands = frame.filter(pl.col("brand_display") != "All brands")
    if metric in {"forecast_accuracy", "vintage_b_accuracy"}:
        actual_column = "vintage_b_actual_kl"
        error_column = "vintage_b_absolute_error_kl"
        descending = False
    elif metric == "vintage_a_accuracy":
        actual_column = "vintage_a_actual_kl"
        error_column = "vintage_a_absolute_error_kl"
        descending = False
    elif metric == "bias":
        aggregates = brands.group_by("brand_display").agg(
            pl.col("vintage_b_net_error_kl").sum().alias("_numerator"),
            pl.col("vintage_b_actual_kl").sum().alias("_denominator"),
        )
        return (
            aggregates.with_columns(
                pl.when(
                    pl.col("_numerator").is_not_null()
                    & pl.col("_denominator").is_not_null()
                    & (pl.col("_denominator") != 0)
                )
                .then(
                    (
                        pl.col("_numerator")
                        / pl.col("_denominator")
                        * 100
                    ).abs()
                )
                .otherwise(pl.lit(None, dtype=pl.Float64))
                .alias("_sort_value")
            ),
            True,
        )
    elif metric == "absolute_error":
        return (
            brands.group_by("brand_display").agg(
                pl.col("absolute_error_kl").sum().alias("_sort_value")
            ),
            True,
        )
    elif metric == "accuracy_delta":
        aggregates = brands.group_by("brand_display").agg(
            pl.col("vintage_a_absolute_error_kl")
            .sum()
            .alias("_vintage_a_error"),
            pl.col("vintage_b_absolute_error_kl")
            .sum()
            .alias("_vintage_b_error"),
            pl.col("vintage_b_actual_kl").sum().alias("_denominator"),
        )
        return (
            aggregates.with_columns(
                pl.when(
                    pl.col("_vintage_a_error").is_not_null()
                    & pl.col("_vintage_b_error").is_not_null()
                    & pl.col("_denominator").is_not_null()
                    & (pl.col("_denominator") != 0)
                )
                .then(
                    (
                        pl.col("_vintage_a_error")
                        - pl.col("_vintage_b_error")
                    )
                    / pl.col("_denominator")
                    * 100
                )
                .otherwise(pl.lit(None, dtype=pl.Float64))
                .alias("_sort_value")
            ),
            False,
        )
    else:
        aggregates = brands.group_by("brand_display").agg(
            pl.col("improved_revisions").sum().alias("_numerator"),
            pl.col("materially_revised_observations")
            .sum()
            .alias("_denominator"),
        )
        return (
            aggregates.with_columns(
                pl.when(
                    pl.col("_numerator").is_not_null()
                    & pl.col("_denominator").is_not_null()
                    & (pl.col("_denominator") != 0)
                )
                .then(
                    pl.col("_numerator")
                    / pl.col("_denominator")
                    * 100
                )
                .otherwise(pl.lit(None, dtype=pl.Float64))
                .alias("_sort_value")
            ),
            False,
        )

    aggregates = brands.group_by("brand_display").agg(
        pl.col(error_column).sum().alias("_numerator"),
        pl.col(actual_column).sum().alias("_denominator"),
    )
    return (
        aggregates.with_columns(
            pl.when(
                pl.col("_numerator").is_not_null()
                & pl.col("_denominator").is_not_null()
                & (pl.col("_denominator") != 0)
            )
            .then(
                (1 - pl.col("_numerator") / pl.col("_denominator")) * 100
            )
            .otherwise(pl.lit(None, dtype=pl.Float64))
            .alias("_sort_value")
        ),
        descending,
    )


def brand_target_month_order(frame: pl.DataFrame, metric: str) -> list[str]:
    """Return worst-first brand rows using selected-population aggregates."""
    require_columns(frame, ["brand_display"], "brand target-month performance")
    brands = frame.filter(pl.col("brand_display") != "All brands")
    if brands.height == 0:
        return ["All brands"] if frame.height else []

    ordered, descending = _aggregate_brand_sort_values(frame, metric)
    ordered = ordered.sort(
        ["_sort_value", "brand_display"],
        descending=[descending, False],
        nulls_last=True,
    )
    brand_order = [str(value) for value in ordered["brand_display"].to_list()]
    has_all_brands = "All brands" in frame["brand_display"].to_list()
    return ["All brands", *brand_order] if has_all_brands else brand_order


def format_horizon_label(horizon: int) -> str:
    """Return an unambiguous label for a whole-month forecast horizon."""
    if horizon == 0:
        return "Current month"
    unit = "month" if horizon == 1 else "months"
    return f"{horizon} {unit} ahead"


def build_horizon_performance(
    frame: pl.DataFrame,
    selected_actual_population: pl.DataFrame,
) -> pl.DataFrame:
    """Aggregate accuracy and volume metrics for every available horizon.

    The horizon chart uses every filtered forecast observation at its exact
    derived horizon. It does not select a nearest vintage when a horizon is
    absent; missing actuals remain visible through the observation counts.
    """
    return _build_horizon_metric_table(
        frame,
        selected_actual_population,
    ).select(HORIZON_METRIC_COLUMNS)


def format_revision_tolerance(value: float | int | None) -> str:
    """Display small tolerances without rounding accepted values to zero."""
    if value is None:
        return "—"
    try:
        tolerance = normalize_revision_tolerance(value)
        if tolerance == 0:
            return "0 KL"
        if abs(tolerance) >= 1:
            decimals = 2
        else:
            decimals = max(
                2,
                min(8, int(-math.floor(math.log10(abs(tolerance)))) + 1),
            )
    except (TypeError, ValueError, OverflowError):
        return "—"
    return f"{tolerance:,.{decimals}f} KL"


def format_metric(
    value: float | int | None, unit: Literal["", "%", "pp", "KL", "count"] = ""
) -> str:
    """Format a KPI without hiding negative values or undefined ratios."""
    if value is None:
        return "—"
    if unit == "count":
        return f"{value:,.0f}"
    if unit == "%":
        return f"{value:,.1f}%"
    if unit == "pp":
        return f"{value:,.1f} pp"
    if unit == "KL":
        return f"{value:,.1f} KL"
    return f"{value:,.1f}"
