"""Pure data foundation for the forecast-analysis dashboard."""

# Keep the package seam small: adapters and population construction are the public surface.
from .actuals import aggregate_actuals, load_actuals, normalize_actuals
from .analysis_frame import build_analysis_dataset, load_analysis_inputs
from .contracts import AnalysisDataset, AnalysisInputs, HierarchyResult
from .comparison import ComparisonView, build_source_comparison  # pyright: ignore[reportMissingImports]
from .dashboard import (  # pyright: ignore[reportMissingImports]
    DashboardView,
    build_dashboard_view,
    build_product_detail,
)
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
    brand_target_metric_definition,
    brand_target_month_order,
    build_brand_target_month_performance,
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
from .product_history import (  # pyright: ignore[reportMissingImports]
    ProductHistoryView,
    build_product_history,
    search_parent_products,
)
from .vintages import VintageRule, select_vintage_pair  # pyright: ignore[reportMissingImports]

__all__ = [
    "AnalysisDataset",
    "ComparisonView",
    "DashboardFilters",
    "DashboardView",
    "MetricSummary",
    "ProductHistoryView",
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
    "build_brand_target_month_performance",
    "build_dashboard_view",
    "build_product_detail",
    "build_horizon_performance",
    "build_source_comparison",
    "build_monthly_performance",
    "build_population_diagnostics",
    "build_product_history",
    "build_revision_diagnostics",
    "build_revision_scatter",
    "brand_target_metric_definition",
    "brand_target_month_order",
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
    "search_parent_products",
    "select_vintage_pair",
    "with_display_brand",
]
