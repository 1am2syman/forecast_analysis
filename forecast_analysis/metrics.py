"""Aggregate performance metrics for the filtered comparable population."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Literal

import polars as pl

from ._utils import require_columns
from .contracts import ACTUAL_COLUMNS

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


def calculate_metrics(
    pair_frame: pl.DataFrame,
    selected_actual_population: pl.DataFrame,
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


def format_metric(
    value: float | int | None, unit: Literal["", "%", "KL", "count"] = ""
) -> str:
    """Format a KPI without hiding negative values or undefined ratios."""
    if value is None:
        return "—"
    if unit == "count":
        return f"{value:,.0f}"
    if unit == "%":
        return f"{value:,.1f}%"
    if unit == "KL":
        return f"{value:,.1f} KL"
    return f"{value:,.1f}"
