"""Pure data foundation for the forecast-analysis dashboard."""

# Keep the package seam small: adapters and population construction are the public surface.
from .actuals import aggregate_actuals, load_actuals, normalize_actuals
from .analysis_frame import build_analysis_dataset, load_analysis_inputs
from .contracts import AnalysisDataset, AnalysisInputs, HierarchyResult
from .diagnostics import build_population_diagnostics
from .forecast_history import load_forecast_history, normalize_forecast_history
from .hierarchy import clean_hierarchy, load_hierarchy, normalize_hierarchy

__all__ = [
    "AnalysisDataset",
    "aggregate_actuals",
    "AnalysisInputs",
    "HierarchyResult",
    "build_analysis_dataset",
    "build_population_diagnostics",
    "clean_hierarchy",
    "load_actuals",
    "load_analysis_inputs",
    "load_forecast_history",
    "load_hierarchy",
    "normalize_actuals",
    "normalize_forecast_history",
    "normalize_hierarchy",
]
