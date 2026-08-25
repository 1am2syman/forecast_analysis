"""Contracts for the canonical forecast-analysis population."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

FORECAST_SOURCES = frozenset({"tm", "ml"})
FORECAST_HISTORY_COLUMNS = [
    "calculation_month",
    "snop_month",
    "parent_code",
    "parent_description",
    "qty",
    "source",
]
NORMALIZED_FORECAST_COLUMNS = [
    "source",
    "parent_code",
    "parent_description",
    "calculation_month",
    "snop_month",
    "forecast_horizon_months",
    "forecast_kl",
]
FORECAST_IDENTITY_COLUMNS = [
    "source",
    "parent_code",
    "calculation_month",
    "snop_month",
]
HIERARCHY_COLUMNS = [
    "parent_code",
    "hierarchy_description",
    "brand",
    "mapping_status",
]
HIERARCHY_DIAGNOSTIC_COLUMNS = [
    "parent_code",
    "mapping_status",
    "candidate_brands",
    "candidate_descriptions",
    "diagnostic",
]
ACTUAL_COLUMNS = ["parent_code", "snop_month", "actual_kl"]
ACTUAL_POPULATION_COLUMNS = [
    "parent_code",
    "snop_month",
    "actual_kl",
    "hierarchy_description",
    "brand",
    "mapping_status",
    "mapping_diagnostic",
]
ANALYSIS_COLUMNS = [
    "source",
    "parent_code",
    "parent_description",
    "hierarchy_description",
    "brand",
    "mapping_status",
    "mapping_diagnostic",
    "calculation_month",
    "snop_month",
    "forecast_horizon_months",
    "forecast_kl",
    "actual_kl",
    "actual_status",
]
DIAGNOSTIC_COLUMNS = [
    "diagnostic_group",
    "source",
    "status",
    "rows",
    "products",
    "sources",
    "target_months",
    "forecast_kl",
    "actual_kl",
]
HIERARCHY_STATUSES = ("mapped", "unmapped", "conflict")
ACTUAL_STATUSES = ("matched_positive", "matched_zero", "missing")


@dataclass(frozen=True)
class HierarchyResult:
    """Canonical hierarchy rows plus per-parent quality diagnostics."""

    frame: pl.DataFrame
    diagnostics: pl.DataFrame


@dataclass(frozen=True)
class AnalysisInputs:
    """Normalized source frames required to build the analysis population."""

    forecast_history: pl.DataFrame
    hierarchy: pl.DataFrame
    actuals: pl.DataFrame
    hierarchy_diagnostics: pl.DataFrame | None = None


@dataclass(frozen=True)
class AnalysisDataset:
    """The shared forecast population, actual population, and quality diagnostics."""

    frame: pl.DataFrame
    diagnostics: pl.DataFrame
    actual_population: pl.DataFrame
