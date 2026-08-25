"""Composition boundary for the ticket-02 dashboard population."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from .filters import (
    DashboardFilters,
    apply_actual_filters,
    apply_dashboard_filters,
)  # pyright: ignore[reportMissingImports]
from .metrics import MetricSummary, build_monthly_performance, calculate_metrics  # pyright: ignore[reportMissingImports]
from .vintages import VintageRule, select_vintage_pair  # pyright: ignore[reportMissingImports]


@dataclass(frozen=True)
class DashboardView:
    """All dashboard outputs derived from one filtered, source-isolated population."""

    filters: DashboardFilters
    filtered_population: pl.DataFrame
    vintage_pairs: pl.DataFrame
    selected_actual_population: pl.DataFrame
    metrics: MetricSummary
    monthly_performance: pl.DataFrame


def build_dashboard_view(
    frame: pl.DataFrame,
    actual_population: pl.DataFrame,
    filters: DashboardFilters | None = None,
    *,
    vintage_a: VintageRule | None = None,
    vintage_b: VintageRule | None = None,
) -> DashboardView:
    """Apply filters once, select same-source vintages, and derive every view."""
    active_filters = filters or DashboardFilters()
    filtered = apply_dashboard_filters(frame, active_filters)
    selected_actual_population = apply_actual_filters(actual_population, active_filters)
    pairs = select_vintage_pair(
        filtered,
        active_filters.source,
        vintage_a=vintage_a,
        vintage_b=vintage_b,
    )
    return DashboardView(
        filters=active_filters,
        filtered_population=filtered,
        vintage_pairs=pairs,
        selected_actual_population=selected_actual_population,
        metrics=calculate_metrics(pairs, selected_actual_population),
        monthly_performance=build_monthly_performance(
            pairs, selected_actual_population
        ),
    )
