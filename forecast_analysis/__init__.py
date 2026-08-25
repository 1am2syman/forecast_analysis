"""Pure data foundation for the forecast-analysis dashboard."""

# Keep the package seam small: adapters and population construction are the public surface.
from .actuals import aggregate_actuals, load_actuals, normalize_actuals
from .analysis_frame import build_analysis_dataset, load_analysis_inputs
from .contracts import AnalysisDataset, AnalysisInputs, HierarchyResult
from .dashboard import DashboardView, build_dashboard_view  # pyright: ignore[reportMissingImports]
from .diagnostics import build_population_diagnostics
from .filters import (  # pyright: ignore[reportMissingImports]
    DashboardFilters,
    apply_actual_filters,
    apply_dashboard_filters,
    apply_revision_filters,
    available_filter_values,
    with_display_brand,
)
from .forecast_history import load_forecast_history, normalize_forecast_history
from .hierarchy import clean_hierarchy, load_hierarchy, normalize_hierarchy
from .metrics import (  # pyright: ignore[reportMissingImports]
    MetricSummary,
    RevisionMetrics,
    build_horizon_performance,
    build_monthly_performance,
    build_revision_diagnostics,
    build_revision_scatter,
    calculate_metrics,
    calculate_revision_metrics,
    format_horizon_label,
    format_metric,
    format_revision_tolerance,
)
from .vintages import VintageRule, select_vintage_pair  # pyright: ignore[reportMissingImports]

__all__ = [
    "AnalysisDataset",
    "DashboardFilters",
    "DashboardView",
    "MetricSummary",
    "RevisionMetrics",
    "VintageRule",
    "aggregate_actuals",
    "apply_actual_filters",
    "apply_dashboard_filters",
    "apply_revision_filters",
    "available_filter_values",
    "AnalysisInputs",
    "HierarchyResult",
    "build_analysis_dataset",
    "build_dashboard_view",
    "build_horizon_performance",
    "build_monthly_performance",
    "build_population_diagnostics",
    "build_revision_diagnostics",
    "build_revision_scatter",
    "calculate_metrics",
    "calculate_revision_metrics",
    "clean_hierarchy",
    "load_actuals",
    "load_analysis_inputs",
    "load_forecast_history",
    "load_hierarchy",
    "normalize_actuals",
    "format_metric",
    "normalize_forecast_history",
    "normalize_hierarchy",
    "format_horizon_label",
    "format_revision_tolerance",
    "select_vintage_pair",
    "with_display_brand",
]
