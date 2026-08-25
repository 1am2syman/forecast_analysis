"""Composition boundary for the ticket-02 dashboard population."""

from __future__ import annotations

from dataclasses import dataclass, replace

import polars as pl

from .filters import (
    DashboardFilters,
    apply_actual_filters,
    apply_dashboard_filters,
    apply_revision_filters,
)  # pyright: ignore[reportMissingImports]
from .metrics import (
    MetricSummary,
    build_horizon_performance,
    build_monthly_performance,
    build_revision_diagnostics,
    build_revision_scatter,
    calculate_metrics,
)  # pyright: ignore[reportMissingImports]
from .vintages import VintageRule, select_vintage_pair  # pyright: ignore[reportMissingImports]


@dataclass(frozen=True)
class DashboardView:
    """All dashboard outputs derived from one filtered, source-isolated population."""

    filters: DashboardFilters
    filtered_population: pl.DataFrame
    vintage_pairs: pl.DataFrame
    coverage_pairs: pl.DataFrame
    selected_actual_population: pl.DataFrame
    metrics: MetricSummary
    monthly_performance: pl.DataFrame
    horizon_performance: pl.DataFrame
    revision_diagnostics: pl.DataFrame
    revision_scatter: pl.DataFrame


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


def build_dashboard_view(
    frame: pl.DataFrame,
    actual_population: pl.DataFrame,
    filters: DashboardFilters | None = None,
    *,
    vintage_a: VintageRule | None = None,
    vintage_b: VintageRule | None = None,
) -> DashboardView:
    """Apply shared filters, then derive pair and revision views consistently."""
    active_filters = filters or DashboardFilters()
    filtered = apply_dashboard_filters(frame, active_filters)
    coverage_filters = replace(active_filters, horizons=None)
    coverage_population = apply_dashboard_filters(frame, coverage_filters)
    selected_actual_population = apply_actual_filters(actual_population, active_filters)
    coverage_pairs = select_vintage_pair(
        filtered,
        active_filters.source,
        vintage_a=vintage_a,
        vintage_b=vintage_b,
        population_frame=coverage_population,
        revision_tolerance_kl=active_filters.revision_tolerance_kl,
    )
    pairs = apply_revision_filters(coverage_pairs, active_filters)
    output_population = filtered
    if (
        active_filters.revision_directions is not None
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
        revision_diagnostics=build_revision_diagnostics(pairs),
        revision_scatter=build_revision_scatter(pairs),
    )
