"""Aggregate performance metrics for the filtered comparable population."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
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
    "bias_pct",
    "absolute_error_kl",
    "actual_kl",
    "forecast_kl",
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

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class MetricSummary:
    """KPI values and counts derived from one selected vintage pair population."""

    forecast_accuracy_pct: float | None
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


@dataclass(frozen=True)
class _ForecastMetricSnapshot:
    accuracy_pct: float | None
    bias_pct: float | None
    absolute_error_kl: float | None
    actual_kl: float | None
    forecast_kl: float | None
    eligible_observations: int
    absolute_error_observations: int
    ratio_actual_kl: float | None
    ratio_absolute_error_kl: float | None
    ratio_net_error_kl: float | None


def _calculate_forecast_snapshot(
    frame: pl.DataFrame,
    forecast_column: str,
) -> _ForecastMetricSnapshot:
    require_columns(
        frame,
        ["pair_status", forecast_column, "actual_kl"],
        "brand target-month metric population",
    )
    selected_rows = frame.filter(
        pl.col("pair_status").is_in(["complete", "zero_actual"])
        & pl.col(forecast_column).is_not_null()
        & pl.col("actual_kl").is_not_null()
    )
    ratio_rows = frame.filter(
        (pl.col("pair_status") == "complete")
        & (pl.col("actual_kl") > 0)
        & pl.col(forecast_column).is_not_null()
    )
    if selected_rows.height:
        with_error = selected_rows.with_columns(
            (pl.col(forecast_column) - pl.col("actual_kl")).alias("_error_kl")
        ).with_columns(pl.col("_error_kl").abs().alias("_absolute_error_kl"))
        absolute_error = _sum_or_none(with_error, "_absolute_error_kl")
        actual_volume = _sum_or_none(with_error, "actual_kl")
        forecast_volume = _sum_or_none(with_error, forecast_column)
    else:
        absolute_error = actual_volume = forecast_volume = None

    accuracy = bias = None
    ratio_actual = ratio_abs_error = ratio_net_error = None
    if ratio_rows.height:
        with_ratio_error = ratio_rows.with_columns(
            (pl.col(forecast_column) - pl.col("actual_kl")).alias("_error_kl")
        ).with_columns(pl.col("_error_kl").abs().alias("_absolute_error_kl"))
        denominator = _sum_or_none(with_ratio_error, "actual_kl")
        if denominator not in (None, 0):
            ratio_abs_error = _sum_or_none(with_ratio_error, "_absolute_error_kl")
            ratio_net_error = _sum_or_none(with_ratio_error, "_error_kl")
            if ratio_abs_error is not None and ratio_net_error is not None:
                ratio_actual = denominator
                accuracy = (1 - ratio_abs_error / denominator) * 100
                bias = ratio_net_error / denominator * 100

    return _ForecastMetricSnapshot(
        accuracy_pct=accuracy,
        bias_pct=bias,
        absolute_error_kl=absolute_error,
        actual_kl=actual_volume,
        forecast_kl=forecast_volume,
        eligible_observations=ratio_rows.height,
        absolute_error_observations=selected_rows.height,
        ratio_actual_kl=ratio_actual,
        ratio_absolute_error_kl=ratio_abs_error,
        ratio_net_error_kl=ratio_net_error,
    )


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
        # An empty selection has no unique values by definition; the source
        # column is still required so non-empty metric populations are isolated.
        return _empty_summary()
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
    else:
        absolute_error = actual_volume = forecast_volume = None

    accuracy = bias = None
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
                accuracy = (1 - ratio_abs_error / denominator) * 100
                bias = ratio_net_error / denominator * 100

    represented_actual = actual_volume
    total_actual = _sum_or_none(selected_actual_population, "actual_kl")
    coverage = None
    if represented_actual is not None and total_actual not in (None, 0):
        coverage = represented_actual / total_actual * 100

    complete_pairs = pair_frame.filter(pl.col("pair_status") == "complete").height
    missing_pairs = pair_frame.filter(
        pl.col("pair_status").is_in(["missing_a", "missing_b", "missing_both"])
    ).height
    missing_actual = pair_frame.filter(pl.col("pair_status") == "missing_actual").height
    zero_actual = pair_frame.filter(pl.col("pair_status") == "zero_actual").height

    return MetricSummary(
        forecast_accuracy_pct=accuracy,
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
REVISION_SCATTER_COLUMNS = [
    "source",
    "parent_code",
    "parent_description",
    "brand",
    "snop_month",
    "actual_kl",
    "revision_kl",
    "error_improvement_kl",
    "revision_direction",
    "revision_outcome",
]
REVISION_SCATTER_SCHEMA = {
    "source": pl.String,
    "parent_code": pl.Int64,
    "parent_description": pl.String,
    "brand": pl.String,
    "snop_month": pl.Date,
    "actual_kl": pl.Float64,
    "revision_kl": pl.Float64,
    "error_improvement_kl": pl.Float64,
    "revision_direction": pl.String,
    "revision_outcome": pl.String,
}


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


def build_revision_scatter(pair_frame: pl.DataFrame) -> pl.DataFrame:
    """Return valid pair points for the revision-versus-improvement chart."""
    require_columns(
        pair_frame,
        REVISION_SCATTER_COLUMNS + ["pair_status"],
        "revision scatter population",
    )
    if pair_frame.height == 0:
        return pl.DataFrame(schema=REVISION_SCATTER_SCHEMA).select(
            REVISION_SCATTER_COLUMNS
        )
    return pair_frame.filter(pl.col("pair_status") == "complete").select(
        REVISION_SCATTER_COLUMNS
    )


def build_monthly_performance(
    pair_frame: pl.DataFrame,
    selected_actual_population: pl.DataFrame,
) -> pl.DataFrame:
    """Return aggregate KPI columns by target month for chart reuse."""
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
    rows: list[dict[str, object]] = []
    groups = (
        pair_frame.select(["source", "snop_month"])
        .unique()
        .sort(["source", "snop_month"])
        .iter_rows(named=True)
    )
    for group in groups:
        subset = pair_frame.filter(
            (pl.col("source") == group["source"])
            & (pl.col("snop_month") == group["snop_month"])
        )
        actual_subset = selected_actual_population.filter(
            pl.col("snop_month") == group["snop_month"]
        )
        summary = calculate_metrics(subset, actual_subset)
        rows.append(
            {
                "source": group["source"],
                "snop_month": group["snop_month"],
                "forecast_accuracy_pct": summary.forecast_accuracy_pct,
                "bias_pct": summary.bias_pct,
                "absolute_error_kl": summary.absolute_error_kl,
                "actual_kl": summary.actual_kl,
                "forecast_kl": summary.forecast_kl,
                "coverage_pct": summary.coverage_pct,
                "eligible_observations": summary.eligible_observations,
                "population_observations": summary.population_observations,
            }
        )
    schema = {
        "source": pl.String,
        "snop_month": pl.Date,
        "forecast_accuracy_pct": pl.Float64,
        "bias_pct": pl.Float64,
        "absolute_error_kl": pl.Float64,
        "actual_kl": pl.Float64,
        "forecast_kl": pl.Float64,
        "coverage_pct": pl.Float64,
        "eligible_observations": pl.Int64,
        "population_observations": pl.Int64,
    }
    return pl.DataFrame(rows, schema=schema).select(METRIC_COLUMNS)


def _build_brand_target_summary(
    pair_frame: pl.DataFrame,
    actual_population: pl.DataFrame,
    source: str,
    brand_display: str,
    target_month: date,
    revision_tolerance_kl: float,
) -> dict[str, object]:
    vintage_a = _calculate_forecast_snapshot(
        pair_frame,
        "vintage_a_forecast_kl",
    )
    vintage_b = _calculate_forecast_snapshot(
        pair_frame,
        "vintage_b_forecast_kl",
    )
    revision = calculate_revision_metrics(
        pair_frame,
        revision_tolerance_kl=revision_tolerance_kl,
    )
    total_actual = _sum_or_none(actual_population, "actual_kl")
    coverage = None
    if vintage_b.actual_kl is not None and total_actual not in (None, 0):
        coverage = vintage_b.actual_kl / total_actual * 100

    return {
        "source": source,
        "brand_display": brand_display,
        "snop_month": target_month,
        "forecast_accuracy_pct": vintage_b.accuracy_pct,
        "bias_pct": vintage_b.bias_pct,
        "absolute_error_kl": vintage_b.absolute_error_kl,
        "vintage_a_accuracy_pct": vintage_a.accuracy_pct,
        "vintage_b_accuracy_pct": vintage_b.accuracy_pct,
        "accuracy_delta_pp": revision.accuracy_delta_pp,
        "revision_effectiveness_pct": revision.revision_effectiveness_pct,
        "actual_kl": vintage_b.actual_kl,
        "forecast_kl": vintage_b.forecast_kl,
        "coverage_pct": coverage,
        "eligible_observations": vintage_b.eligible_observations,
        "vintage_a_eligible_observations": vintage_a.eligible_observations,
        "vintage_b_eligible_observations": vintage_b.eligible_observations,
        "absolute_error_observations": vintage_b.absolute_error_observations,
        "population_observations": pair_frame.height,
        "complete_pairs": pair_frame.filter(
            pl.col("pair_status") == "complete"
        ).height,
        "improved_revisions": revision.improved_revisions,
        "materially_revised_observations": revision.materially_revised_observations,
        "vintage_a_actual_kl": vintage_a.ratio_actual_kl,
        "vintage_a_absolute_error_kl": vintage_a.ratio_absolute_error_kl,
        "vintage_a_net_error_kl": vintage_a.ratio_net_error_kl,
        "vintage_b_actual_kl": vintage_b.ratio_actual_kl,
        "vintage_b_absolute_error_kl": vintage_b.ratio_absolute_error_kl,
        "vintage_b_net_error_kl": vintage_b.ratio_net_error_kl,
    }


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
    actuals = with_display_brand(actual_population)
    rows: list[dict[str, object]] = []

    for group in (
        paired.select(["source", "brand_display", "snop_month"])
        .unique()
        .sort(["source", "brand_display", "snop_month"])
        .iter_rows(named=True)
    ):
        group_pairs = paired.filter(
            (pl.col("source") == group["source"])
            & (pl.col("brand_display") == group["brand_display"])
            & (pl.col("snop_month") == group["snop_month"])
        )
        group_actuals = actuals.filter(
            (pl.col("brand_display") == group["brand_display"])
            & (pl.col("snop_month") == group["snop_month"])
        )
        rows.append(
            _build_brand_target_summary(
                group_pairs,
                group_actuals,
                group["source"],
                group["brand_display"],
                group["snop_month"],
                tolerance,
            )
        )

    for group in (
        paired.select(["source", "snop_month"])
        .unique()
        .sort(["source", "snop_month"])
        .iter_rows(named=True)
    ):
        group_pairs = paired.filter(
            (pl.col("source") == group["source"])
            & (pl.col("snop_month") == group["snop_month"])
        )
        group_actuals = actuals.filter(pl.col("snop_month") == group["snop_month"])
        rows.append(
            _build_brand_target_summary(
                group_pairs,
                group_actuals,
                group["source"],
                "All brands",
                group["snop_month"],
                tolerance,
            )
        )

    if not rows:
        return pl.DataFrame(schema=BRAND_TARGET_PERFORMANCE_SCHEMA).select(
            BRAND_TARGET_PERFORMANCE_COLUMNS
        )
    return (
        pl.DataFrame(rows, schema=BRAND_TARGET_PERFORMANCE_SCHEMA)
        .select(BRAND_TARGET_PERFORMANCE_COLUMNS)
        .with_columns(
            (pl.col("brand_display") == "All brands").alias("_all_brands")
        )
        .sort(
            ["source", "snop_month", "_all_brands", "brand_display"],
            descending=[False, False, True, False],
            nulls_last=True,
        )
        .drop("_all_brands")
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
    if frame.height == 0:
        return pl.DataFrame(schema=HORIZON_METRIC_SCHEMA).select(
            HORIZON_METRIC_COLUMNS
        )

    rows: list[dict[str, object]] = []
    groups = (
        frame.select(["source", "forecast_horizon_months"])
        .unique()
        .sort(
            ["source", "forecast_horizon_months"],
            descending=[False, True],
        )
        .iter_rows(named=True)
    )
    for group in groups:
        subset = frame.filter(
            (pl.col("source") == group["source"])
            & (pl.col("forecast_horizon_months") == group["forecast_horizon_months"])
        )
        pair_subset = subset.select(
            [
                "source",
                pl.lit(None, dtype=pl.Date).alias("vintage_a_calculation_month"),
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
        summary = calculate_metrics(pair_subset, selected_actual_population)
        horizon = group["forecast_horizon_months"]
        if not isinstance(horizon, int):
            raise TypeError(f"forecast horizon is not an integer: {horizon!r}")
        rows.append(
            {
                "source": group["source"],
                "forecast_horizon_months": horizon,
                "horizon_label": format_horizon_label(horizon),
                "forecast_accuracy_pct": summary.forecast_accuracy_pct,
                "bias_pct": summary.bias_pct,
                "absolute_error_kl": summary.absolute_error_kl,
                "actual_kl": summary.actual_kl,
                "forecast_kl": summary.forecast_kl,
                "coverage_pct": summary.coverage_pct,
                "eligible_observations": summary.eligible_observations,
                "population_observations": summary.population_observations,
                "missing_actual_observations": summary.missing_actual_observations,
                "zero_actual_observations": summary.zero_actual_observations,
            }
        )

    return pl.DataFrame(rows, schema=HORIZON_METRIC_SCHEMA).select(
        HORIZON_METRIC_COLUMNS
    )


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
