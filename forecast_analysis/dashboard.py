"""Composition boundary for the source-aware dashboard population and drilldowns."""

from __future__ import annotations

from dataclasses import dataclass, replace

import polars as pl

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
)  # pyright: ignore[reportMissingImports]
from .metrics import (
    MetricSummary,
    build_brand_target_month_performance,
    build_horizon_performance,
    build_monthly_performance,
    build_revision_diagnostics,
    build_revision_scatter,
    calculate_metrics,
)  # pyright: ignore[reportMissingImports]
from .product_history import (  # pyright: ignore[reportMissingImports]
    ProductHistoryView,
    build_product_history,
)
from .quality import QualityView, build_quality_view  # pyright: ignore[reportMissingImports]
from .vintages import VintageRule, select_vintage_pair  # pyright: ignore[reportMissingImports]


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
    horizon_performance: pl.DataFrame
    brand_target_month_performance: pl.DataFrame
    revision_diagnostics: pl.DataFrame
    revision_scatter: pl.DataFrame
    quality: QualityView
    comparison: ComparisonView | None = None


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


def _build_quality(
    frame: pl.DataFrame,
    actual_population: pl.DataFrame,
    filters: DashboardFilters,
    coverage_pairs: pl.DataFrame,
    hierarchy_diagnostics: pl.DataFrame | None = None,
) -> QualityView:
    quality_population, quality_actual_population = _quality_inputs(
        frame,
        actual_population,
        filters,
    )
    availability_population = apply_dashboard_filters(
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
    return build_quality_view(
        quality_population,
        quality_actual_population,
        coverage_pairs,
        source_availability_population=availability_population,
        selected_sources=filters.selected_sources,
        hierarchy_diagnostics=hierarchy_diagnostics,
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
) -> ProductHistoryView:
    """Build product history from the same source and population filter state.

    The product and target month are the detail selection. Source, brand,
    minimum-volume, and horizon controls remain owned by ``DashboardFilters``.
    The detail chart inherits the shared source, target-month, brand, product,
    volume, and horizon filters. Comparison mode never substitutes Vintage A/B
    rules or combines TM and ML rows.
    """
    detail_filters = replace(
        filters,
        parent_codes=(parent_code,),
        target_months=(target_month,),
        horizons=_product_detail_horizons(filters),
        revision_directions=None,
        revision_outcomes=None,
    )
    detail_population = apply_dashboard_filters(
        frame,
        detail_filters,
        availability_frame=frame,
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
    return DashboardView(
        filters=comparison_filters,
        filtered_population=comparison.filtered_population,
        vintage_pairs=comparison.vintage_pairs,
        coverage_pairs=comparison.coverage_pairs,
        selected_actual_population=comparison.selected_actual_population,
        metrics=comparison.tm_metrics,
        monthly_performance=comparison.monthly_performance,
        horizon_performance=comparison.horizon_performance,
        brand_target_month_performance=comparison.brand_target_month_performance,
        revision_diagnostics=comparison.revision_diagnostics,
        revision_scatter=comparison.revision_scatter,
        quality=_build_quality(
            frame,
            actual_population,
            comparison_filters,
            comparison.coverage_pairs,
            hierarchy_diagnostics,
        ),
        comparison=comparison,
    )


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
    selected_actual_population = apply_actual_filters(
        actual_population,
        active_filters,
        availability_frame=availability_population,
        forecast_key_frame=(
            pairs
            if active_filters.zero_forecast_only
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
    ):
        output_population = _filter_population_to_pairs(filtered, pairs)
    return DashboardView(
        filters=active_filters,
        filtered_population=output_population,
        vintage_pairs=pairs,
        coverage_pairs=coverage_pairs,
        selected_actual_population=selected_actual_population,
        metrics=calculate_metrics(
            pairs,
            selected_actual_population,
            revision_tolerance_kl=active_filters.revision_tolerance_kl,
        ),
        monthly_performance=build_monthly_performance(
            pairs, selected_actual_population
        ),
        horizon_performance=build_horizon_performance(
            output_population, selected_actual_population
        ),
        brand_target_month_performance=build_brand_target_month_performance(
            pairs,
            selected_actual_population,
            revision_tolerance_kl=active_filters.revision_tolerance_kl,
        ),
        revision_diagnostics=build_revision_diagnostics(pairs),
        revision_scatter=build_revision_scatter(pairs),
        quality=_build_quality(
            frame,
            actual_population,
            active_filters,
            coverage_pairs,
            hierarchy_diagnostics,
        ),
    )
