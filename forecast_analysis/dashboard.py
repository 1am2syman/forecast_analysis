"""Composition boundary for the source-aware dashboard population and drilldowns."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

import polars as pl

from ._utils import require_columns
from .comparison import (  # pyright: ignore[reportMissingImports]
    ComparisonView,
    build_source_comparison,
)
from .filters import (
    DashboardFilters,
    apply_actual_filters,
    apply_dashboard_filters,
    apply_quality_pair_filters,
    apply_revision_filters,
    apply_performance_filters,
    normalize_filter_months,
    with_display_brand,
)  # pyright: ignore[reportMissingImports]
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
)  # pyright: ignore[reportMissingImports]
from .product_history import (  # pyright: ignore[reportMissingImports]
    ProductHistoryView,
    build_product_history,
)
from .quality import QualityView, build_quality_view  # pyright: ignore[reportMissingImports]
from .vintages import VintageRule, select_vintage_pair  # pyright: ignore[reportMissingImports]


POPULATION_SUMMARY_COLUMNS = [
    "mode",
    "sources",
    "target_month_start",
    "target_month_end",
    "target_range",
    "horizons",
    "products",
    "forecast_rows",
    "coverage_pair_rows",
    "selected_pair_rows",
    "eligible_observations",
    "comparable_pairs",
    "actual_volume_kl",
    "metric_actual_volume_kl",
    "coverage_scope",
    "coverage_pct",
    "coverage_numerator_actual_kl",
    "coverage_denominator_actual_kl",
    "tm_eligible_observations",
    "ml_eligible_observations",
    "tm_coverage_pct",
    "tm_coverage_numerator_actual_kl",
    "tm_coverage_denominator_actual_kl",
    "ml_coverage_pct",
    "ml_coverage_numerator_actual_kl",
    "ml_coverage_denominator_actual_kl",
    "vintage_a_rule",
    "vintage_b_rule",
]
POPULATION_SUMMARY_SCHEMA = {
    "mode": pl.String,
    "sources": pl.String,
    "target_month_start": pl.Date,
    "target_month_end": pl.Date,
    "target_range": pl.String,
    "horizons": pl.String,
    "products": pl.Int64,
    "forecast_rows": pl.Int64,
    "coverage_pair_rows": pl.Int64,
    "selected_pair_rows": pl.Int64,
    "eligible_observations": pl.Int64,
    "comparable_pairs": pl.Int64,
    "actual_volume_kl": pl.Float64,
    "metric_actual_volume_kl": pl.Float64,
    "coverage_scope": pl.String,
    "coverage_pct": pl.Float64,
    "coverage_numerator_actual_kl": pl.Float64,
    "coverage_denominator_actual_kl": pl.Float64,
    "tm_eligible_observations": pl.Int64,
    "ml_eligible_observations": pl.Int64,
    "tm_coverage_pct": pl.Float64,
    "tm_coverage_numerator_actual_kl": pl.Float64,
    "tm_coverage_denominator_actual_kl": pl.Float64,
    "ml_coverage_pct": pl.Float64,
    "ml_coverage_numerator_actual_kl": pl.Float64,
    "ml_coverage_denominator_actual_kl": pl.Float64,
    "vintage_a_rule": pl.String,
    "vintage_b_rule": pl.String,
}
EXCEPTION_DOWNLOAD_COLUMNS = [
    "source",
    "parent_code",
    "parent_description",
    "brand",
    "snop_month",
    "actual_kl",
    "actual_status",
    "vintage_a_calculation_month",
    "vintage_a_horizon_months",
    "vintage_a_forecast_kl",
    "vintage_b_calculation_month",
    "vintage_b_horizon_months",
    "vintage_b_forecast_kl",
    "absolute_error_b_kl",
    "bias_b_kl",
    "revision_kl",
    "error_improvement_kl",
    "revision_direction",
    "revision_outcome",
    "pair_status",
    "mapping_status",
]


@dataclass(frozen=True)
class DashboardView:
    """Dashboard outputs derived from one shared filter state.

    Standard mode remains source-isolated. Comparison mode exposes source-
    separated projections through ``comparison`` while keeping the same view
    seam for the Marimo presentation.
    """

    filters: DashboardFilters
    filtered_population: pl.DataFrame
    vintage_pairs: pl.DataFrame
    coverage_pairs: pl.DataFrame
    selected_actual_population: pl.DataFrame
    metrics: MetricSummary
    monthly_performance: pl.DataFrame
    monthly_audit: pl.DataFrame
    horizon_performance: pl.DataFrame
    horizon_audit: pl.DataFrame
    brand_target_month_performance: pl.DataFrame
    revision_diagnostics: pl.DataFrame
    revision_scatter: pl.DataFrame
    quality: QualityView
    population_summary: pl.DataFrame
    download_frame: pl.DataFrame
    comparison: ComparisonView | None = None


def _sum_or_none(frame: pl.DataFrame, column: str) -> float | None:
    if frame.height == 0 or column not in frame.columns:
        return None
    values = frame.get_column(column).drop_nulls()
    if values.len() == 0:
        return None
    total = values.sum()
    try:
        return float(total) if total is not None else None
    except (TypeError, ValueError) as exc:
        raise TypeError(f"dashboard total is not numeric: {total!r}") from exc


def _target_month_bounds(
    frame: pl.DataFrame,
    selected_months: tuple[date, ...] | None,
) -> tuple[date | None, date | None]:
    if selected_months is not None:
        if not selected_months:
            return None, None
        months = sorted(selected_months)
    elif "snop_month" in frame.columns and frame.height:
        months = sorted(frame.get_column("snop_month").unique().to_list())
    else:
        return None, None
    return months[0], months[-1]


def _format_month_range(start: date | None, end: date | None) -> str:
    if start is None or end is None:
        return "none selected"
    if start == end:
        return start.isoformat()
    return f"{start.isoformat()} → {end.isoformat()}"


def _format_horizons(filters: DashboardFilters, frame: pl.DataFrame) -> str:
    if filters.horizons is not None:
        if not filters.horizons:
            return "none selected"
        return ", ".join(str(value) for value in sorted(filters.horizons, reverse=True))
    if "forecast_horizon_months" not in frame.columns or frame.height == 0:
        return "all available (none present)"
    values = sorted(
        frame["forecast_horizon_months"].drop_nulls().unique().to_list(),
        reverse=True,
    )
    return ", ".join(str(value) for value in values) if values else "all available (none present)"


def build_population_summary(
    filters: DashboardFilters,
    filtered_population: pl.DataFrame,
    coverage_pairs: pl.DataFrame,
    selected_pairs: pl.DataFrame,
    selected_actual_population: pl.DataFrame,
    metrics: MetricSummary,
    *,
    comparable_pairs: int | None = None,
    source_metrics: dict[str, MetricSummary] | None = None,
) -> pl.DataFrame:
    """Return the single auditable population summary shown above every view."""
    target_start, target_end = _target_month_bounds(
        filtered_population,
        filters.target_months,
    )
    actual_volume = _sum_or_none(selected_actual_population, "actual_kl")
    coverage_numerator = metrics.coverage_numerator_actual_kl
    coverage_denominator = metrics.coverage_denominator_actual_kl
    coverage_pct = metrics.coverage_pct
    if coverage_denominator is None and actual_volume is not None:
        coverage_numerator = 0.0 if coverage_numerator is None else coverage_numerator
        coverage_denominator = actual_volume
        coverage_pct = (
            coverage_numerator / coverage_denominator * 100
            if coverage_denominator != 0
            else None
        )
    summary = {
        "mode": "comparison" if filters.comparison_mode else "single_source",
        "sources": " + ".join(source.upper() for source in filters.selected_sources),
        "target_month_start": target_start,
        "target_month_end": target_end,
        "target_range": _format_month_range(target_start, target_end),
        "horizons": _format_horizons(filters, filtered_population),
        "products": filtered_population["parent_code"].n_unique()
        if "parent_code" in filtered_population.columns
        else 0,
        "forecast_rows": filtered_population.height,
        "coverage_pair_rows": coverage_pairs.height,
        "selected_pair_rows": selected_pairs.height,
        "eligible_observations": metrics.eligible_observations,
        "comparable_pairs": (
            metrics.complete_pairs
            if comparable_pairs is None
            else comparable_pairs
        ),
        "actual_volume_kl": actual_volume,
        "metric_actual_volume_kl": metrics.actual_kl,
        "coverage_scope": (
            "common_aligned_population"
            if filters.comparison_mode and source_metrics is not None
            else "selected_source_population"
        ),
        "coverage_pct": coverage_pct,
        "coverage_numerator_actual_kl": coverage_numerator,
        "coverage_denominator_actual_kl": coverage_denominator,
        "tm_eligible_observations": None,
        "ml_eligible_observations": None,
        "tm_coverage_pct": None,
        "tm_coverage_numerator_actual_kl": None,
        "tm_coverage_denominator_actual_kl": None,
        "ml_coverage_pct": None,
        "ml_coverage_numerator_actual_kl": None,
        "ml_coverage_denominator_actual_kl": None,
        "vintage_a_rule": None,
        "vintage_b_rule": None,
    }
    if source_metrics is not None:
        tm = source_metrics.get("tm")
        ml = source_metrics.get("ml")
        summary["tm_eligible_observations"] = tm.eligible_observations if tm else None
        summary["ml_eligible_observations"] = ml.eligible_observations if ml else None
        summary["tm_coverage_pct"] = tm.coverage_pct if tm else None
        summary["tm_coverage_numerator_actual_kl"] = (
            tm.coverage_numerator_actual_kl if tm else None
        )
        summary["tm_coverage_denominator_actual_kl"] = (
            tm.coverage_denominator_actual_kl if tm else None
        )
        summary["ml_coverage_pct"] = ml.coverage_pct if ml else None
        summary["ml_coverage_numerator_actual_kl"] = (
            ml.coverage_numerator_actual_kl if ml else None
        )
        summary["ml_coverage_denominator_actual_kl"] = (
            ml.coverage_denominator_actual_kl if ml else None
        )
    if coverage_pairs.height:
        rules = coverage_pairs.select(
            ["vintage_a_rule", "vintage_b_rule"]
        ).unique()
        if rules.height:
            summary["vintage_a_rule"] = rules["vintage_a_rule"].item(0)
            summary["vintage_b_rule"] = rules["vintage_b_rule"].item(0)
    return pl.DataFrame([summary], schema=POPULATION_SUMMARY_SCHEMA).select(
        POPULATION_SUMMARY_COLUMNS
    )


def build_exception_download_frame(pairs: pl.DataFrame) -> pl.DataFrame:
    """Project the exact selected pair rows into the auditable download contract."""
    prepared = with_display_brand(pairs)
    return (
        prepared.select(
            [
                "source",
                "parent_code",
                "parent_description",
                pl.col("brand_display").alias("brand"),
                "snop_month",
                "actual_kl",
                "actual_status",
                "vintage_a_calculation_month",
                "vintage_a_horizon_months",
                "vintage_a_forecast_kl",
                "vintage_b_calculation_month",
                "vintage_b_horizon_months",
                "vintage_b_forecast_kl",
                pl.col("vintage_b_absolute_error_kl").alias("absolute_error_b_kl"),
                pl.col("vintage_b_bias_kl").alias("bias_b_kl"),
                "revision_kl",
                "error_improvement_kl",
                "revision_direction",
                "revision_outcome",
                "pair_status",
                "mapping_status",
            ]
        )
        .sort(
            ["absolute_error_b_kl", "snop_month", "parent_code", "source"],
            descending=[True, False, False, False],
            nulls_last=True,
        )
    )


def _filter_population_to_pairs(
    frame: pl.DataFrame,
    pairs: pl.DataFrame,
) -> pl.DataFrame:
    if pairs.height == 0:
        return frame.head(0)
    keys = pairs.select(["source", "parent_code", "snop_month"]).unique()
    return frame.join(
        keys,
        on=["source", "parent_code", "snop_month"],
        how="inner",
    ).sort(["parent_code", "snop_month", "calculation_month", "source"])


def _quality_base_filters(filters: DashboardFilters) -> DashboardFilters:
    """Keep business selection scope while removing metric-only quality filters."""
    return replace(
        filters,
        hierarchy_statuses=None,
        actual_statuses=None,
        pair_statuses=None,
        source_availability=None,
        zero_forecast_only=False,
        complete_vintage_history_only=False,
        revision_directions=None,
        revision_outcomes=None,
        forecast_directions=None,
        forecast_accuracy_band=None,
        bias_band=None,
        minimum_absolute_error_kl=0,
        top_n=None,
        minimum_actual_volume=0,
    )


def _metric_selection_filters(filters: DashboardFilters) -> DashboardFilters:
    """Select vintages before pair-level quality filters, including zero forecast."""
    return replace(
        filters,
        hierarchy_statuses=None,
        actual_statuses=None,
        pair_statuses=None,
        source_availability=None,
        zero_forecast_only=False,
        revision_directions=None,
        revision_outcomes=None,
    )


def _quality_inputs(
    frame: pl.DataFrame,
    actual_population: pl.DataFrame,
    filters: DashboardFilters,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    quality_filters = _quality_base_filters(filters)
    availability_filters = replace(
        quality_filters,
        comparison_mode=True,
        source_availability=None,
    )
    availability_population = apply_dashboard_filters(
        frame,
        availability_filters,
        availability_frame=frame,
    )
    quality_population = apply_dashboard_filters(
        frame,
        quality_filters,
        availability_frame=availability_population,
    )
    quality_actual_population = apply_actual_filters(
        actual_population,
        quality_filters,
        availability_frame=availability_population,
    )
    return quality_population, quality_actual_population


def _active_quality_availability(
    frame: pl.DataFrame,
    filters: DashboardFilters,
    active_pairs: pl.DataFrame,
) -> pl.DataFrame:
    """Build comparison availability from surviving source-specific pair keys.

    Standard-source quality keeps the ordinary active-horizon availability
    population. Comparison quality instead classifies the exact source keys
    that survived pair and source-availability filters; the pair frame is the
    durable source-composition evidence for that active scope.
    """
    if filters.comparison_mode:
        availability_pairs = active_pairs
        if filters.pair_statuses is None and active_pairs.height:
            # Without a pair-status filter, comparison populations use only
            # source keys with an exact selected-horizon forecast. Missing pair
            # rows remain in the pair diagnostics but are not availability.
            availability_pairs = active_pairs.filter(
                pl.col("vintage_b_calculation_month").is_not_null()
            )
        if availability_pairs.height == 0:
            return availability_pairs.select(
                ["source", "parent_code", "snop_month"]
            )
        return availability_pairs.select(
            [
                "source",
                "parent_code",
                "parent_description",
                "brand",
                "mapping_status",
                "mapping_diagnostic",
                "snop_month",
                "actual_kl",
                "actual_status",
                pl.col("vintage_b_horizon_months").alias("forecast_horizon_months"),
                pl.col("vintage_b_forecast_kl").alias("forecast_kl"),
            ]
        ).unique(subset=["source", "parent_code", "snop_month"])

    active_filters = replace(
        filters,
        comparison_mode=True,
        horizons=filters.horizons,
        source_availability=None,
        pair_statuses=None,
        revision_directions=None,
        revision_outcomes=None,
        forecast_directions=None,
        forecast_accuracy_band=None,
        bias_band=None,
        minimum_absolute_error_kl=0.0,
        top_n=None,
        zero_forecast_only=filters.zero_forecast_only,
        complete_vintage_history_only=False,
    )
    scoped = apply_dashboard_filters(
        frame,
        active_filters,
        include_source=False,
        availability_frame=frame,
    )
    if active_pairs.height == 0:
        return scoped.head(0)
    active_keys = active_pairs.select(["parent_code", "snop_month"]).unique()
    return scoped.join(
        active_keys,
        on=["parent_code", "snop_month"],
        how="semi",
    )


def _build_quality(
    frame: pl.DataFrame,
    actual_population: pl.DataFrame,
    filters: DashboardFilters,
    coverage_pairs: pl.DataFrame,
    hierarchy_diagnostics: pl.DataFrame | None = None,
    *,
    active_population: pl.DataFrame | None = None,
    active_actual_population: pl.DataFrame | None = None,
    active_pairs: pl.DataFrame | None = None,
    baseline_coverage_pairs: pl.DataFrame | None = None,
) -> QualityView:
    baseline_population, baseline_actual_population = _quality_inputs(
        frame,
        actual_population,
        filters,
    )
    baseline_availability_population = apply_dashboard_filters(
        frame,
        replace(
            _quality_base_filters(filters),
            comparison_mode=True,
            pair_statuses=None,
            minimum_actual_volume=0,
            source_availability=None,
        ),
        availability_frame=frame,
    )
    selected_population = (
        baseline_population if active_population is None else active_population
    )
    selected_actuals = (
        baseline_actual_population
        if active_actual_population is None
        else active_actual_population
    )
    selected_pairs = coverage_pairs if active_pairs is None else active_pairs
    active_availability_population = _active_quality_availability(
        frame,
        filters,
        selected_pairs,
    )
    return build_quality_view(
        selected_population,
        selected_actuals,
        selected_pairs,
        source_availability_population=active_availability_population,
        selected_sources=filters.selected_sources,
        hierarchy_diagnostics=hierarchy_diagnostics,
        baseline_population=baseline_population,
        baseline_actual_population=baseline_actual_population,
        baseline_coverage_pairs=(
            coverage_pairs if baseline_coverage_pairs is None else baseline_coverage_pairs
        ),
        baseline_source_availability_population=baseline_availability_population,
    )


def _product_detail_horizons(filters: DashboardFilters) -> tuple[int, ...] | None:
    """Resolve the detail horizon without weakening comparison alignment."""
    if not filters.comparison_mode:
        return filters.horizons
    if filters.comparison_horizon is None:
        raise ValueError(
            "comparison product detail requires one exact comparison horizon"
        )
    expected = (filters.comparison_horizon,)
    if filters.horizons is not None and filters.horizons != expected:
        raise ValueError(
            "comparison product detail requires one exact horizon; "
            "comparison_horizon and horizons conflict"
        )
    return expected


def build_product_detail(
    frame: pl.DataFrame,
    filters: DashboardFilters,
    parent_code: int,
    target_month: object,
    *,
    active_key_frame: pl.DataFrame | None = None,
) -> ProductHistoryView:
    """Build a history expansion for one key in the active dashboard scope.

    The product and target month are local narrowing selections. Source, brand,
    minimum-volume, horizon, quality, and source-availability filters remain
    owned by ``DashboardFilters``. ``active_key_frame`` is the selected-pair
    key projection from :func:`build_dashboard_view`; when supplied, it keeps
    revision and performance filters from reopening a product-target key that
    the active pair population removed. The returned history expands only the
    surviving key under the ordinary source/horizon scope.
    """
    normalized_target_month = normalize_filter_months((target_month,))[0]
    selected_parent_codes = (
        (parent_code,)
        if filters.parent_codes is None or parent_code in filters.parent_codes
        else ()
    )
    selected_target_months = (
        (normalized_target_month,)
        if filters.target_months is None
        or normalized_target_month in filters.target_months
        else ()
    )
    if active_key_frame is not None:
        require_columns(
            active_key_frame,
            ["parent_code", "snop_month"],
            "active product-detail key population",
        )
        active_keys = active_key_frame.filter(
            (pl.col("parent_code") == parent_code)
            & (pl.col("snop_month") == normalized_target_month)
        )
        if active_keys.height == 0:
            selected_parent_codes = ()
            selected_target_months = ()
    detail_filters = replace(
        filters,
        parent_codes=selected_parent_codes,
        target_months=selected_target_months,
        horizons=_product_detail_horizons(filters),
        revision_directions=None,
        revision_outcomes=None,
    )
    detail_availability_filters = replace(
        detail_filters,
        comparison_mode=True,
        source_availability=None,
        hierarchy_statuses=None,
        actual_statuses=None,
        pair_statuses=None,
        zero_forecast_only=False,
        complete_vintage_history_only=False,
        revision_directions=None,
        revision_outcomes=None,
        forecast_directions=None,
        forecast_accuracy_band=None,
        bias_band=None,
        minimum_absolute_error_kl=0.0,
        top_n=None,
        minimum_actual_volume=0,
    )
    detail_availability = apply_dashboard_filters(
        frame,
        detail_availability_filters,
        availability_frame=frame,
    )
    detail_population = apply_dashboard_filters(
        frame,
        detail_filters,
        availability_frame=detail_availability,
    )
    return build_product_history(
        detail_population,
        parent_code,
        target_month,
        sources=detail_filters.selected_sources,
        revision_tolerance_kl=detail_filters.revision_tolerance_kl,
    )


def _build_comparison_dashboard_view(
    frame: pl.DataFrame,
    actual_population: pl.DataFrame,
    filters: DashboardFilters,
    hierarchy_diagnostics: pl.DataFrame | None = None,
) -> DashboardView:
    """Compose exact-horizon comparison outputs without revision self-pairs."""
    comparison_filters = replace(
        filters,
        revision_directions=None,
        revision_outcomes=None,
    )
    comparison = build_source_comparison(
        frame,
        actual_population,
        comparison_filters,
    )
    quality = _build_quality(
        frame,
        actual_population,
        comparison_filters,
        comparison.coverage_pairs,
        hierarchy_diagnostics,
        active_population=comparison.quality_population,
        active_actual_population=comparison.selected_actual_population,
        active_pairs=comparison.vintage_pairs,
        baseline_coverage_pairs=comparison.baseline_coverage_pairs,
    )
    population_summary = build_population_summary(
        comparison_filters,
        comparison.filtered_population,
        comparison.coverage_pairs,
        comparison.vintage_pairs,
        comparison.selected_actual_population,
        comparison.common_metrics,
        comparable_pairs=comparison.comparable_pairs,
        source_metrics={"tm": comparison.tm_metrics, "ml": comparison.ml_metrics},
    )
    return DashboardView(
        filters=comparison_filters,
        filtered_population=comparison.filtered_population,
        vintage_pairs=comparison.vintage_pairs,
        coverage_pairs=comparison.coverage_pairs,
        selected_actual_population=comparison.selected_actual_population,
        metrics=comparison.tm_metrics,
        monthly_performance=comparison.monthly_performance,
        monthly_audit=comparison.monthly_audit,
        horizon_performance=comparison.horizon_performance,
        horizon_audit=comparison.horizon_audit,
        brand_target_month_performance=comparison.brand_target_month_performance,
        revision_diagnostics=comparison.revision_diagnostics,
        revision_scatter=comparison.revision_scatter,
        quality=quality,
        population_summary=population_summary,
        download_frame=build_exception_download_frame(comparison.vintage_pairs),
        comparison=comparison,
    )


REVISION_SCATTER_EXCLUDED_BRANDS = {
    "PA-BDYLOT",
    "JFB_POWDR",
    "RK_CLO_R",
    "RK_CLO_S",
    "SAF_HONEY",
    "BPA_PET_J",
}


def build_dashboard_view(
    frame: pl.DataFrame,
    actual_population: pl.DataFrame,
    filters: DashboardFilters | None = None,
    *,
    vintage_a: VintageRule | None = None,
    vintage_b: VintageRule | None = None,
    hierarchy_diagnostics: pl.DataFrame | None = None,
) -> DashboardView:
    """Apply shared filters, then derive source-specific dashboard views.

    Comparison mode owns one shared exact-horizon rule, so ``vintage_a`` and
    ``vintage_b`` are intentionally ignored there; those controls belong only
    to standard single-source revision analysis.
    """
    active_filters = filters or DashboardFilters()
    if active_filters.comparison_mode:
        return _build_comparison_dashboard_view(
            frame,
            actual_population,
            active_filters,
            hierarchy_diagnostics,
        )

    availability_population = apply_dashboard_filters(
        frame,
        replace(
            _quality_base_filters(active_filters),
            comparison_mode=True,
            pair_statuses=None,
            minimum_actual_volume=0,
            source_availability=None,
        ),
        availability_frame=frame,
    )
    filtered = apply_dashboard_filters(
        frame,
        active_filters,
        availability_frame=availability_population,
    )
    selection_filters = _metric_selection_filters(active_filters)
    selection_population = apply_dashboard_filters(
        frame,
        selection_filters,
        availability_frame=availability_population,
    )
    coverage_filters = replace(
        selection_filters,
        horizons=None,
        zero_forecast_only=False,
        complete_vintage_history_only=False,
    )
    coverage_population = apply_dashboard_filters(
        frame,
        coverage_filters,
        availability_frame=availability_population,
    )
    quality_pair_population = apply_dashboard_filters(
        frame,
        _quality_base_filters(active_filters),
        availability_frame=availability_population,
    )
    coverage_pairs = select_vintage_pair(
        quality_pair_population,
        active_filters.source,
        vintage_a=vintage_a,
        vintage_b=vintage_b,
        population_frame=coverage_population,
        revision_tolerance_kl=active_filters.revision_tolerance_kl,
    )
    baseline_coverage_pairs = coverage_pairs
    metric_coverage_pairs = select_vintage_pair(
        selection_population,
        active_filters.source,
        vintage_a=vintage_a,
        vintage_b=vintage_b,
        population_frame=coverage_population,
        revision_tolerance_kl=active_filters.revision_tolerance_kl,
    )
    pairs = apply_quality_pair_filters(
        metric_coverage_pairs,
        active_filters,
        availability_frame=availability_population,
    )
    pairs = apply_revision_filters(pairs, active_filters)
    pairs = apply_performance_filters(pairs, active_filters)
    selected_actual_population = apply_actual_filters(
        actual_population,
        active_filters,
        availability_frame=availability_population,
        forecast_key_frame=(
            pairs
            if (
                active_filters.zero_forecast_only
                or active_filters.pair_statuses is not None
                or active_filters.revision_directions is not None
                or active_filters.revision_outcomes is not None
                or active_filters.has_performance_filters
            )
            else selection_population
            if active_filters.complete_vintage_history_only
            else None
        ),
    )
    output_population = filtered
    if (
        active_filters.zero_forecast_only
        or active_filters.pair_statuses is not None
        or active_filters.revision_directions is not None
        or active_filters.revision_outcomes is not None
        or active_filters.has_performance_filters
    ):
        output_population = _filter_population_to_pairs(filtered, pairs)
    metrics = calculate_metrics(
        pairs,
        selected_actual_population,
        revision_tolerance_kl=active_filters.revision_tolerance_kl,
    )
    quality = _build_quality(
        frame,
        actual_population,
        active_filters,
        coverage_pairs,
        hierarchy_diagnostics,
        active_population=output_population,
        active_actual_population=selected_actual_population,
        active_pairs=pairs,
        baseline_coverage_pairs=baseline_coverage_pairs,
    )
    population_summary = build_population_summary(
        active_filters,
        output_population,
        coverage_pairs,
        pairs,
        selected_actual_population,
        metrics,
    )
    monthly_audit = build_monthly_audit(pairs, selected_actual_population)
    horizon_audit = build_horizon_audit(
        output_population,
        selected_actual_population,
    )
    scatter_filters = replace(
        active_filters.without_revision_filters().without_performance_filters(),
        target_months=None,
        horizons=None,
        pair_statuses=None,
        sku_classes=None,
        zero_forecast_only=False,
        complete_vintage_history_only=False,
    )
    scatter_population = apply_dashboard_filters(
        frame,
        scatter_filters,
        availability_frame=availability_population,
    )
    scatter_parent_scope_active = any(
        (
            active_filters.horizons is not None,
            active_filters.pair_statuses is not None,
            active_filters.zero_forecast_only,
            active_filters.complete_vintage_history_only,
            active_filters.revision_directions is not None,
            active_filters.revision_outcomes is not None,
            active_filters.has_performance_filters,
        )
    )
    if scatter_parent_scope_active:
        scatter_population = scatter_population.join(
            pairs.select(["source", "parent_code"]).unique(),
            on=["source", "parent_code"],
            how="semi",
        )
    scatter_target_end = (
        max(active_filters.target_months)
        if active_filters.target_months
        else None
    )
    revision_scatter = build_revision_scatter(
        scatter_population,
        target_end_month=scatter_target_end,
    )
    scatter_description = pl.col("parent_description").fill_null("").str.to_uppercase()
    is_pcno_ej = scatter_description.str.contains(
        "PCNO",
    ) & scatter_description.str.contains("EJ")
    revision_scatter = revision_scatter.filter(
        ~pl.col("brand").fill_null("").is_in(REVISION_SCATTER_EXCLUDED_BRANDS)
        & ~is_pcno_ej
    )
    if active_filters.sku_classes is not None:
        revision_scatter = revision_scatter.filter(
            pl.col("sku_class").is_in(active_filters.sku_classes)
        )
    return DashboardView(
        filters=active_filters,
        filtered_population=output_population,
        vintage_pairs=pairs,
        coverage_pairs=coverage_pairs,
        selected_actual_population=selected_actual_population,
        metrics=metrics,
        monthly_performance=project_monthly_performance(monthly_audit),
        monthly_audit=monthly_audit,
        horizon_performance=horizon_audit.select(HORIZON_METRIC_COLUMNS),
        horizon_audit=horizon_audit,
        brand_target_month_performance=build_brand_target_month_performance(
            pairs,
            selected_actual_population,
            revision_tolerance_kl=active_filters.revision_tolerance_kl,
        ),
        revision_diagnostics=build_revision_diagnostics(pairs),
        revision_scatter=revision_scatter,
        quality=quality,
        population_summary=population_summary,
        download_frame=build_exception_download_frame(pairs),
    )
