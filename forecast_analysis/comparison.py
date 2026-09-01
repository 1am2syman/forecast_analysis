"""Aligned TM-versus-ML comparison derived from one shared population."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import polars as pl

from ._utils import require_columns
from .contracts import (
    ACTUAL_COLUMNS,
    ANALYSIS_COLUMNS,
    normalize_revision_tolerance,
)
from .filters import (
    DashboardFilters,
    apply_actual_filters,
    apply_dashboard_filters,
    apply_quality_pair_filters,
)
from .metrics import (
    HORIZON_METRIC_COLUMNS,
    MetricSummary,
    build_brand_target_month_performance,
    build_horizon_audit,
    build_monthly_audit,
    build_revision_diagnostics,
    build_revision_scatter,
    calculate_metrics,
    project_monthly_performance,
)
from .vintages import VintageRule, select_vintage_pair

COMPARISON_SOURCES = ("tm", "ml")
COMPARISON_KEY_COLUMNS = ["parent_code", "snop_month"]
COMPARISON_METRIC_NAMES = (
    ("forecast_accuracy_pct", "Forecast accuracy", "pp"),
    ("bias_pct", "Bias", "pp"),
    ("absolute_error_kl", "Absolute error", "KL"),
    ("coverage_pct", "Coverage", "pp"),
)

COMPARISON_POPULATION_COLUMNS = [
    "population",
    "status",
    "observations",
    "products",
    "actual_kl",
    "tm_forecast_kl",
    "ml_forecast_kl",
]
COMPARISON_POPULATION_SCHEMA = {
    "population": pl.String,
    "status": pl.String,
    "observations": pl.Int64,
    "products": pl.Int64,
    "actual_kl": pl.Float64,
    "tm_forecast_kl": pl.Float64,
    "ml_forecast_kl": pl.Float64,
}
COMPARISON_DELTA_COLUMNS = [
    "metric",
    "unit",
    "tm_value",
    "ml_value",
    "delta_ml_minus_tm",
]
COMPARISON_DELTA_SCHEMA = {
    "metric": pl.String,
    "unit": pl.String,
    "tm_value": pl.Float64,
    "ml_value": pl.Float64,
    "delta_ml_minus_tm": pl.Float64,
}
WINNER_COLUMNS = ["winner", "winner_label", "observations"]
WINNER_SCHEMA = {
    "winner": pl.String,
    "winner_label": pl.String,
    "observations": pl.Int64,
}
COMPARISON_REVISION_COLUMNS = [
    "source",
    "category",
    "observations",
    "share_of_complete_pairs_pct",
    "actual_kl",
    "revision_kl",
    "error_improvement_kl",
]
COMPARISON_REVISION_SCHEMA = {
    "source": pl.String,
    "category": pl.String,
    "observations": pl.Int64,
    "share_of_complete_pairs_pct": pl.Float64,
    "actual_kl": pl.Float64,
    "revision_kl": pl.Float64,
    "error_improvement_kl": pl.Float64,
}


@dataclass(frozen=True)
class ComparisonView:
    """All aligned TM/ML outputs for explicit comparison mode.

    The comparison rule is always one exact horizon.  Source metrics are
    calculated independently on the common product-target population. Source-
    only populations are excluded from like-for-like accuracy, bias, and
    absolute-error KPIs, but are included in each source's aligned-horizon
    coverage KPI and retained in ``population_summary``. When pair-status
    filters are active, the surviving TM/ML pair union is the shared active key
    scope; the unfiltered pair population remains available only as
    ``baseline_coverage_pairs`` for quality scope exclusions.
    """

    selected_horizon: int | None
    common_horizons: tuple[int, ...]
    alignment_rule: str | None
    blocked: bool
    warning: str | None
    coverage_warning: str | None
    common_metrics: MetricSummary
    filtered_population: pl.DataFrame
    # Pair-status scopes keep incomplete keys in this null-forecast quality
    # projection without contaminating the selected-horizon forecast population.
    quality_population: pl.DataFrame
    vintage_pairs: pl.DataFrame
    coverage_pairs: pl.DataFrame
    baseline_coverage_pairs: pl.DataFrame
    selected_actual_population: pl.DataFrame
    common_population: pl.DataFrame
    tm_only_population: pl.DataFrame
    ml_only_population: pl.DataFrame
    tm_pairs: pl.DataFrame
    ml_pairs: pl.DataFrame
    paired_comparison: pl.DataFrame
    winner_counts: pl.DataFrame
    population_summary: pl.DataFrame
    source_metrics: pl.DataFrame
    deltas: pl.DataFrame
    tm_metrics: MetricSummary
    ml_metrics: MetricSummary
    monthly_performance: pl.DataFrame
    horizon_performance: pl.DataFrame
    brand_target_month_performance: pl.DataFrame
    revision_diagnostics: pl.DataFrame
    revision_scatter: pl.DataFrame
    monthly_audit: pl.DataFrame = field(default_factory=pl.DataFrame)
    horizon_audit: pl.DataFrame = field(default_factory=pl.DataFrame)

    @property
    def ready(self) -> bool:
        """Whether aligned source metrics can be compared."""
        return not self.blocked and self.paired_comparison.height > 0

    @property
    def comparable_pairs(self) -> int:
        """Count common product-target pairs represented by both sources."""
        return self.paired_comparison.height

    @property
    def paired(self) -> pl.DataFrame:
        """Alias for the paired winner-classification frame."""
        return self.paired_comparison

    @property
    def metrics(self) -> pl.DataFrame:
        """Alias for source-specific KPI rows."""
        return self.source_metrics


def _empty_metric_summary() -> MetricSummary:
    pair_frame = pl.DataFrame(
        schema={
            "source": pl.String,
            "vintage_a_calculation_month": pl.Date,
            "vintage_b_calculation_month": pl.Date,
            "vintage_b_forecast_kl": pl.Float64,
            "actual_kl": pl.Float64,
            "pair_status": pl.String,
        }
    )
    actual_population = pl.DataFrame(
        schema={
            "parent_code": pl.Int64,
            "snop_month": pl.Date,
            "actual_kl": pl.Float64,
        }
    )
    return calculate_metrics(pair_frame, actual_population)


def _normalize_horizon(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("comparison horizon must be a non-negative integer")
    if value < 0:
        raise ValueError("comparison horizon must be a non-negative integer")
    return value


def _key_frame(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.select(COMPARISON_KEY_COLUMNS).unique().sort(COMPARISON_KEY_COLUMNS)


def _pairs_with_forecast(pair_frame: pl.DataFrame) -> pl.DataFrame:
    return pair_frame.filter(
        pl.col("vintage_b_calculation_month").is_not_null()
        & pl.col("vintage_b_forecast_kl").is_not_null()
    )


def _keys_with_forecast(pair_frame: pl.DataFrame) -> pl.DataFrame:
    return _key_frame(_pairs_with_forecast(pair_frame))


def _intersection(left: pl.DataFrame, right: pl.DataFrame) -> pl.DataFrame:
    if left.height == 0 or right.height == 0:
        return left.head(0)
    return left.join(right, on=COMPARISON_KEY_COLUMNS, how="inner").select(
        COMPARISON_KEY_COLUMNS
    ).unique().sort(COMPARISON_KEY_COLUMNS)


def _difference(left: pl.DataFrame, right: pl.DataFrame) -> pl.DataFrame:
    if left.height == 0:
        return left
    if right.height == 0:
        return left
    return left.join(right, on=COMPARISON_KEY_COLUMNS, how="anti").sort(
        COMPARISON_KEY_COLUMNS
    )


def _union(left: pl.DataFrame, right: pl.DataFrame) -> pl.DataFrame:
    """Return the deterministic product-target union of two pair scopes."""
    if left.height == 0:
        return right
    if right.height == 0:
        return left
    return pl.concat([left, right], how="vertical").unique().sort(COMPARISON_KEY_COLUMNS)


def _filter_to_keys(frame: pl.DataFrame, keys: pl.DataFrame) -> pl.DataFrame:
    if keys.height == 0:
        return frame.head(0)
    return frame.join(keys, on=COMPARISON_KEY_COLUMNS, how="inner").sort(
        COMPARISON_KEY_COLUMNS
    )


def _filter_to_source_keys(frame: pl.DataFrame, keys: pl.DataFrame) -> pl.DataFrame:
    if keys.height == 0:
        return frame.head(0)
    return frame.join(
        keys,
        on=["source", *COMPARISON_KEY_COLUMNS],
        how="inner",
    ).sort(["source", *COMPARISON_KEY_COLUMNS])


def _quality_population_from_pairs(pair_frame: pl.DataFrame) -> pl.DataFrame:
    """Project pair evidence into quality rows without inventing forecasts."""
    return pair_frame.select(
        [
            "source",
            "parent_code",
            "parent_description",
            pl.col("parent_description").alias("hierarchy_description"),
            "brand",
            "mapping_status",
            "mapping_diagnostic",
            pl.col("vintage_b_calculation_month").alias("calculation_month"),
            "snop_month",
            pl.col("vintage_b_horizon_months").alias("forecast_horizon_months"),
            pl.col("vintage_b_forecast_kl").alias("forecast_kl"),
            "actual_kl",
            "actual_status",
        ]
    )


def _sum_column(frame: pl.DataFrame, column: str) -> float:
    if frame.height == 0:
        return 0.0
    values = frame.get_column(column).drop_nulls()
    if values.len() == 0:
        return 0.0
    value = values.sum()
    try:
        return float(value or 0.0)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"comparison total is not numeric: {value!r}") from exc


def _source_forecast_total(pair_frame: pl.DataFrame) -> float:
    return _sum_column(pair_frame, "vintage_b_forecast_kl")


def _coverage_components(
    available_keys: pl.DataFrame,
    selected_actual_population: pl.DataFrame,
) -> tuple[float | None, float | None, float | None]:
    """Return coverage numerator, denominator, and percentage as one unit."""
    if selected_actual_population.height == 0:
        return None, None, None
    total_actual = _sum_column(selected_actual_population, "actual_kl")
    represented_actual = _sum_column(
        _filter_to_keys(selected_actual_population, available_keys),
        "actual_kl",
    )
    if total_actual == 0:
        return represented_actual, total_actual, None
    return represented_actual, total_actual, represented_actual / total_actual * 100


def _population_summary(
    actual_population: pl.DataFrame,
    tm_pairs: pl.DataFrame,
    ml_pairs: pl.DataFrame,
    common_keys: pl.DataFrame,
    tm_only_keys: pl.DataFrame,
    ml_only_keys: pl.DataFrame,
) -> pl.DataFrame:
    groups = (
        ("common", "both_sources", common_keys),
        ("tm_only", "tm_only", tm_only_keys),
        ("ml_only", "ml_only", ml_only_keys),
    )
    rows: list[dict[str, object]] = []
    for population, status, keys in groups:
        actuals = _filter_to_keys(actual_population, keys)
        tm_group = _filter_to_keys(tm_pairs, keys)
        ml_group = _filter_to_keys(ml_pairs, keys)
        rows.append(
            {
                "population": population,
                "status": status,
                "observations": keys.height,
                "products": keys.get_column("parent_code").n_unique(),
                "actual_kl": _sum_column(actuals, "actual_kl"),
                "tm_forecast_kl": _source_forecast_total(tm_group),
                "ml_forecast_kl": _source_forecast_total(ml_group),
            }
        )
    return pl.DataFrame(rows, schema=COMPARISON_POPULATION_SCHEMA).select(
        COMPARISON_POPULATION_COLUMNS
    )


def _metric_rows(
    metrics_by_source: dict[str, MetricSummary],
) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for source in COMPARISON_SOURCES:
        row = metrics_by_source[source].as_dict()
        row["source"] = source
        rows.append(row)
    return pl.DataFrame(rows)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)):
        raise TypeError(f"comparison metric is not numeric: {value!r}")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"comparison metric is not numeric: {value!r}") from exc


def _metric_deltas(
    metrics_by_source: dict[str, MetricSummary],
) -> pl.DataFrame:
    tm = metrics_by_source["tm"].as_dict()
    ml = metrics_by_source["ml"].as_dict()
    rows: list[dict[str, object]] = []
    for column, label, unit in COMPARISON_METRIC_NAMES:
        raw_tm_value = tm[column]
        raw_ml_value = ml[column]
        tm_value = _optional_float(raw_tm_value)
        ml_value = _optional_float(raw_ml_value)
        rows.append(
            {
                "metric": label,
                "unit": unit,
                "tm_value": tm_value,
                "ml_value": ml_value,
                "delta_ml_minus_tm": (
                    ml_value - tm_value
                    if tm_value is not None and ml_value is not None
                    else None
                ),
            }
        )
    return pl.DataFrame(rows, schema=COMPARISON_DELTA_SCHEMA).select(
        COMPARISON_DELTA_COLUMNS
    )


def _build_paired_comparison(
    tm_pairs: pl.DataFrame,
    ml_pairs: pl.DataFrame,
    tolerance_kl: float,
) -> pl.DataFrame:
    tm = tm_pairs.select(
        [
            *COMPARISON_KEY_COLUMNS,
            "parent_description",
            "brand",
            "mapping_status",
            "mapping_diagnostic",
            "actual_kl",
            "actual_status",
            pl.col("vintage_a_horizon_months").alias("tm_horizon_months"),
            pl.col("vintage_b_horizon_months").alias("tm_b_horizon_months"),
            pl.col("vintage_b_forecast_kl").alias("tm_forecast_kl"),
            pl.col("vintage_b_absolute_error_kl").alias("tm_absolute_error_kl"),
            pl.col("pair_status").alias("tm_pair_status"),
        ]
    )
    ml = ml_pairs.select(
        [
            *COMPARISON_KEY_COLUMNS,
            pl.col("vintage_a_horizon_months").alias("ml_horizon_months"),
            pl.col("vintage_b_horizon_months").alias("ml_b_horizon_months"),
            pl.col("vintage_b_forecast_kl").alias("ml_forecast_kl"),
            pl.col("vintage_b_absolute_error_kl").alias("ml_absolute_error_kl"),
            pl.col("pair_status").alias("ml_pair_status"),
        ]
    )
    paired = tm.join(ml, on=COMPARISON_KEY_COLUMNS, how="inner").with_columns(
        (pl.col("tm_absolute_error_kl") - pl.col("ml_absolute_error_kl")).alias(
            "absolute_error_delta_kl"
        )
    )
    null_winner = pl.lit(None, dtype=pl.String)
    winner = (
        pl.when(
            pl.col("tm_absolute_error_kl").is_null()
            | pl.col("ml_absolute_error_kl").is_null()
        )
        .then(null_winner)
        .when(pl.col("absolute_error_delta_kl").abs() <= tolerance_kl)
        .then(pl.lit("tied"))
        .when(pl.col("absolute_error_delta_kl") > tolerance_kl)
        .then(pl.lit("ml_better"))
        .otherwise(pl.lit("tm_better"))
        .alias("winner")
    )
    return (
        paired.with_columns(winner)
        .with_columns(
            pl.when(pl.col("winner") == "tm_better")
            .then(pl.lit("TM better"))
            .when(pl.col("winner") == "ml_better")
            .then(pl.lit("ML better"))
            .when(pl.col("winner") == "tied")
            .then(pl.lit("Tied"))
            .otherwise(null_winner)
            .alias("winner_label"),
            pl.when(pl.col("tm_pair_status") == "missing_actual")
            .then(pl.lit("missing_actual"))
            .when(pl.col("tm_pair_status") == "zero_actual")
            .then(pl.lit("zero_actual"))
            .otherwise(pl.lit("complete"))
            .alias("pair_status"),
        )
        .select(
            [
                "parent_code",
                "parent_description",
                "brand",
                "mapping_status",
                "mapping_diagnostic",
                "snop_month",
                "actual_kl",
                "actual_status",
                "tm_horizon_months",
                "tm_b_horizon_months",
                "tm_forecast_kl",
                "tm_absolute_error_kl",
                "ml_horizon_months",
                "ml_b_horizon_months",
                "ml_forecast_kl",
                "ml_absolute_error_kl",
                "absolute_error_delta_kl",
                "pair_status",
                "winner",
                "winner_label",
            ]
        )
        .sort(COMPARISON_KEY_COLUMNS)
    )


def _winner_counts(paired: pl.DataFrame) -> pl.DataFrame:
    rows = []
    labels = {
        "tm_better": "TM better",
        "ml_better": "ML better",
        "tied": "Tied",
    }
    for winner, label in labels.items():
        rows.append(
            {
                "winner": winner,
                "winner_label": label,
                "observations": paired.filter(pl.col("winner") == winner).height,
            }
        )
    return pl.DataFrame(rows, schema=WINNER_SCHEMA).select(WINNER_COLUMNS)


def _source_revision_diagnostics(
    tm_pairs: pl.DataFrame,
    ml_pairs: pl.DataFrame,
) -> pl.DataFrame:
    tables: list[pl.DataFrame] = []
    for source, pairs in (("tm", tm_pairs), ("ml", ml_pairs)):
        tables.append(
            build_revision_diagnostics(pairs)
            .with_columns(pl.lit(source).alias("source"))
            .select(COMPARISON_REVISION_COLUMNS)
        )
    return pl.concat(tables, how="vertical").sort(["source", "category"])


def _alignment_warning(
    filters: DashboardFilters,
    requested_horizons: tuple[int, ...] | None,
    requested_horizon: int | None,
    common_horizons: tuple[int, ...],
) -> str | None:
    if requested_horizons is not None and len(requested_horizons) != 1:
        selected = ", ".join(str(value) for value in requested_horizons) or "none"
        return (
            "Comparison blocked: TM and ML comparison requires one shared exact "
            f"horizon; selected horizons are {selected}."
        )
    if (
        filters.comparison_horizon is not None
        and requested_horizons is not None
        and requested_horizons != (filters.comparison_horizon,)
    ):
        return (
            "Comparison blocked: the comparison horizon and forecast-horizon "
            "filter do not match. Select one shared exact horizon."
        )
    if requested_horizon is not None and requested_horizon not in common_horizons:
        available = ", ".join(str(value) for value in common_horizons) or "none"
        return (
            "Comparison blocked: the selected exact horizon "
            f"({requested_horizon} months ahead) is not available in both TM and ML. "
            f"Common horizons: {available}."
        )
    if not common_horizons:
        return (
            "Comparison blocked: TM and ML have no common exact forecast horizon "
            "in the current filtered population."
        )
    return None


def _coverage_warning(
    selected_horizon: int | None,
    common_keys: pl.DataFrame,
    tm_only_keys: pl.DataFrame,
    ml_only_keys: pl.DataFrame,
) -> str | None:
    if selected_horizon is None:
        return None
    if not tm_only_keys.height and not ml_only_keys.height:
        return None
    return (
        f"Aligned at {selected_horizon} month(s) ahead: "
        f"{common_keys.height:,} common observations, "
        f"{tm_only_keys.height:,} TM-only, and {ml_only_keys.height:,} ML-only. "
        "Source-only observations are excluded from like-for-like accuracy, bias, "
        "and absolute-error KPIs but are included in source coverage and remain "
        "visible in counts and actual volumes."
    )


def build_source_comparison(
    frame: pl.DataFrame,
    actual_population: pl.DataFrame,
    filters: DashboardFilters | None = None,
    *,
    comparison_horizon: int | None = None,
) -> ComparisonView:
    """Build an aligned, source-independent TM-versus-ML comparison.

    The comparison rule is always one shared exact horizon. The default is
    the common exact horizon closest to the target, with one month ahead
    preferred. A requested horizon that cannot be aligned is blocked rather
    than silently substituting another horizon. Vintage A/B and revision
    direction/outcome controls are intentionally not part of this projection.
    """
    require_columns(frame, ANALYSIS_COLUMNS, "analysis population")
    require_columns(actual_population, ACTUAL_COLUMNS, "selected actual population")
    active_filters = filters or DashboardFilters(comparison_mode=True)
    if not active_filters.comparison_mode:
        active_filters = replace(active_filters, comparison_mode=True)
    comparison_filters = replace(
        active_filters,
        revision_directions=None,
        revision_outcomes=None,
    )

    requested_horizons = comparison_filters.horizons
    requested_horizon = _normalize_horizon(
        comparison_horizon
        if comparison_horizon is not None
        else comparison_filters.comparison_horizon
    )
    if requested_horizon is None and requested_horizons is not None:
        if len(requested_horizons) == 1:
            requested_horizon = requested_horizons[0]
        elif len(requested_horizons) == 0:
            requested_horizon = None

    selection_filters = (
        comparison_filters.without_status_quality_filters().without_revision_filters()
    )
    base_filters = replace(
        selection_filters,
        horizons=None,
        zero_forecast_only=False,
        complete_vintage_history_only=False,
        pair_statuses=None,
        comparison_horizon=None,
    )
    coverage_population = apply_dashboard_filters(
        frame,
        base_filters,
        availability_frame=frame,
    )
    source_horizons = {
        source: set(
            coverage_population
            .filter(
                (pl.col("source") == source)
                & pl.col("forecast_horizon_months").is_not_null()
            )["forecast_horizon_months"].to_list()
        )
        for source in COMPARISON_SOURCES
    }
    common_horizons = tuple(sorted(source_horizons["tm"] & source_horizons["ml"]))
    warning = _alignment_warning(
        comparison_filters,
        requested_horizons,
        requested_horizon,
        common_horizons,
    )

    if warning is None:
        selected_horizon = requested_horizon
        if selected_horizon is None:
            selected_horizon = 1 if 1 in common_horizons else (
                common_horizons[0] if common_horizons else None
            )
    else:
        selected_horizon = requested_horizon
        if requested_horizon is None and requested_horizons is None:
            selected_horizon = 1 if 1 in common_horizons else (
                common_horizons[0] if common_horizons else None
            )

    active_availability_filters = replace(
        base_filters,
        comparison_mode=True,
        horizons=(selected_horizon,) if selected_horizon is not None else (),
    )
    availability_population = apply_dashboard_filters(
        frame,
        active_availability_filters,
        availability_frame=frame,
    )

    if selected_horizon is None:
        exact_population = coverage_population.head(0)
        comparison_rule = None
    else:
        exact_filters = replace(
            selection_filters,
            horizons=(selected_horizon,),
            comparison_horizon=selected_horizon,
        )
        exact_population = apply_dashboard_filters(
            frame,
            exact_filters,
            availability_frame=availability_population,
        )
        comparison_rule = VintageRule.specific_horizon(selected_horizon)

    selection_population = exact_population
    if selected_horizon is None:
        visible_population = exact_population
    else:
        visible_filters = replace(
            comparison_filters,
            horizons=(selected_horizon,),
            comparison_horizon=selected_horizon,
        )
        visible_population = apply_dashboard_filters(
            frame,
            visible_filters,
            availability_frame=availability_population,
        )

    pair_quality_filters = comparison_filters.without_quality_filters().without_revision_filters()
    pair_quality_population = apply_dashboard_filters(
        frame,
        replace(
            pair_quality_filters,
            comparison_mode=True,
            horizons=(selected_horizon,) if selected_horizon is not None else (),
        ),
        availability_frame=availability_population,
    )

    def _select_pairs(source: str, population: pl.DataFrame) -> pl.DataFrame:
        if comparison_rule is None:
            return select_vintage_pair(
                population,
                source,
                population_frame=coverage_population,
                revision_tolerance_kl=comparison_filters.revision_tolerance_kl,
            )
        return select_vintage_pair(
            population,
            source,
            vintage_a=comparison_rule,
            vintage_b=comparison_rule,
            population_frame=coverage_population,
            revision_tolerance_kl=comparison_filters.revision_tolerance_kl,
        )

    tm_coverage_pairs = _select_pairs("tm", pair_quality_population)
    ml_coverage_pairs = _select_pairs("ml", pair_quality_population)
    tm_pairs = apply_quality_pair_filters(
        _select_pairs("tm", selection_population),
        comparison_filters,
        availability_frame=availability_population,
    )
    ml_pairs = apply_quality_pair_filters(
        _select_pairs("ml", selection_population),
        comparison_filters,
        availability_frame=availability_population,
    )

    tm_available_keys = _keys_with_forecast(tm_pairs)
    ml_available_keys = _keys_with_forecast(ml_pairs)
    pair_status_scope_active = comparison_filters.pair_statuses is not None
    if pair_status_scope_active:
        tm_scope_keys = _key_frame(tm_pairs)
        ml_scope_keys = _key_frame(ml_pairs)
    else:
        tm_scope_keys = tm_available_keys
        ml_scope_keys = ml_available_keys
    common_keys = _intersection(tm_scope_keys, ml_scope_keys)
    tm_only_keys = _difference(tm_scope_keys, ml_scope_keys)
    ml_only_keys = _difference(ml_scope_keys, tm_scope_keys)
    active_union_keys = _union(tm_scope_keys, ml_scope_keys)
    if pair_status_scope_active:
        active_source_keys = pl.concat(
            [
                tm_pairs.select(["source", *COMPARISON_KEY_COLUMNS]),
                ml_pairs.select(["source", *COMPARISON_KEY_COLUMNS]),
            ],
            how="vertical",
        ).select(["source", *COMPARISON_KEY_COLUMNS]).unique()
        # Pair rows are the audit projection for incomplete keys. Forecast
        # populations must remain a strict projection of the selected horizon;
        # never substitute a historical row merely to display a missing key.
        active_visible_population = _filter_to_source_keys(
            visible_population,
            active_source_keys,
        )
    else:
        active_visible_population = visible_population
    selected_actual_population = apply_actual_filters(
        actual_population,
        comparison_filters,
        availability_frame=availability_population,
        forecast_key_frame=(
            active_union_keys
            if pair_status_scope_active
            else exact_population
            if comparison_filters.zero_forecast_only
            or comparison_filters.complete_vintage_history_only
            else None
        ),
    )

    tm_visible = _filter_to_keys(tm_pairs, common_keys)
    ml_visible = _filter_to_keys(ml_pairs, common_keys)
    tm_metric_pairs = _pairs_with_forecast(tm_visible)
    ml_metric_pairs = _pairs_with_forecast(ml_visible)
    visible_pairs = pl.concat([tm_pairs, ml_pairs], how="vertical").sort(
        ["source", *COMPARISON_KEY_COLUMNS]
    )
    quality_population = (
        _quality_population_from_pairs(visible_pairs)
        if pair_status_scope_active
        else active_visible_population
    )
    baseline_coverage_pairs = pl.concat(
        [tm_coverage_pairs, ml_coverage_pairs],
        how="vertical",
    ).sort(["source", *COMPARISON_KEY_COLUMNS])
    coverage_pairs = visible_pairs

    common_population = _filter_to_keys(active_visible_population, common_keys)
    tm_only_population = _filter_to_keys(
        active_visible_population.filter(pl.col("source") == "tm"), tm_only_keys
    )
    ml_only_population = _filter_to_keys(
        active_visible_population.filter(pl.col("source") == "ml"), ml_only_keys
    )

    common_metrics_by_source = {
        "tm": calculate_metrics(tm_metric_pairs, selected_actual_population),
        "ml": calculate_metrics(ml_metric_pairs, selected_actual_population),
    }
    coverage_by_source = {
        "tm": _coverage_components(tm_available_keys, selected_actual_population),
        "ml": _coverage_components(ml_available_keys, selected_actual_population),
    }
    metrics_by_source = {
        source: replace(
            common_metrics_by_source[source],
            coverage_pct=coverage_by_source[source][2],
            coverage_numerator_actual_kl=coverage_by_source[source][0],
            coverage_denominator_actual_kl=coverage_by_source[source][1],
        )
        for source in COMPARISON_SOURCES
    }
    paired = _build_paired_comparison(
        tm_metric_pairs,
        ml_metric_pairs,
        normalize_revision_tolerance(comparison_filters.revision_tolerance_kl),
    )
    summary = _population_summary(
        selected_actual_population,
        tm_pairs,
        ml_pairs,
        common_keys,
        tm_only_keys,
        ml_only_keys,
    )
    source_metrics = _metric_rows(metrics_by_source)
    deltas = _metric_deltas(metrics_by_source)
    winner_counts = _winner_counts(paired)
    coverage_warning = _coverage_warning(
        selected_horizon,
        common_keys,
        tm_only_keys,
        ml_only_keys,
    )
    metric_pairs = pl.concat(
        [tm_metric_pairs, ml_metric_pairs],
        how="vertical",
    )
    monthly_audit = build_monthly_audit(
        metric_pairs,
        selected_actual_population,
    )
    horizon_audit = build_horizon_audit(
        common_population,
        selected_actual_population,
    )

    return ComparisonView(
        selected_horizon=selected_horizon,
        common_horizons=common_horizons,
        alignment_rule=(
            comparison_rule.label if comparison_rule is not None else None
        ),
        blocked=warning is not None,
        warning=warning,
        coverage_warning=coverage_warning,
        common_metrics=common_metrics_by_source["tm"],
        filtered_population=active_visible_population,
        quality_population=quality_population,
        vintage_pairs=visible_pairs,
        coverage_pairs=coverage_pairs,
        baseline_coverage_pairs=baseline_coverage_pairs,
        selected_actual_population=selected_actual_population,
        common_population=common_population,
        tm_only_population=tm_only_population,
        ml_only_population=ml_only_population,
        # Expose only forecast-bearing common rows to metric/chart consumers;
        # the full status evidence remains in ``vintage_pairs``.
        tm_pairs=tm_metric_pairs,
        ml_pairs=ml_metric_pairs,
        paired_comparison=paired,
        winner_counts=winner_counts,
        population_summary=summary,
        source_metrics=source_metrics,
        deltas=deltas,
        tm_metrics=metrics_by_source["tm"],
        ml_metrics=metrics_by_source["ml"],
        monthly_performance=project_monthly_performance(monthly_audit),
        monthly_audit=monthly_audit,
        horizon_performance=horizon_audit.select(HORIZON_METRIC_COLUMNS),
        horizon_audit=horizon_audit,
        brand_target_month_performance=build_brand_target_month_performance(
            metric_pairs,
            selected_actual_population,
            revision_tolerance_kl=comparison_filters.revision_tolerance_kl,
        ),
        revision_diagnostics=_source_revision_diagnostics(
            tm_metric_pairs,
            ml_metric_pairs,
        ),
        revision_scatter=build_revision_scatter(metric_pairs),
    )
