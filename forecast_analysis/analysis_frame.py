"""Build the source-aware long analysis population."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from .actuals import load_actuals
from .contracts import (
    ACTUAL_POPULATION_COLUMNS,
    ANALYSIS_DATASET_COLUMNS,
    AnalysisDataset,
    AnalysisInputs,
)
from .diagnostics import build_population_diagnostics
from .forecast_history import load_forecast_history
from .hierarchy import load_hierarchy
from .sku_classification import (  # pyright: ignore[reportMissingImports]
    attach_sku_classification,
    build_sku_classifications,
    required_sku_class_actual_months,
)


def load_analysis_inputs(
    forecast_history_path: Path,
    hierarchy_path: Path,
    actuals_path: Path,
) -> AnalysisInputs:
    """Load and normalize all three approved input seams."""
    hierarchy_result = load_hierarchy(hierarchy_path)
    forecast_history = load_forecast_history(forecast_history_path)
    target_months = forecast_history.get_column("snop_month").unique().to_list()
    actual_history = load_actuals(
        actuals_path,
        target_months=required_sku_class_actual_months(target_months),
    )
    actuals = actual_history.filter(pl.col("snop_month").is_in(target_months))
    return AnalysisInputs(
        forecast_history=forecast_history,
        hierarchy=hierarchy_result.frame,
        actuals=actuals,
        hierarchy_diagnostics=hierarchy_result.diagnostics,
        actual_history=actual_history,
    )


def _mapping_diagnostics(inputs: AnalysisInputs) -> pl.DataFrame | None:
    diagnostics = inputs.hierarchy_diagnostics
    if diagnostics is None:
        return None
    return diagnostics.select(
        ["parent_code", pl.col("diagnostic").alias("mapping_diagnostic")]
    )


def _build_actual_population(
    inputs: AnalysisInputs,
    sku_classifications: pl.DataFrame,
) -> pl.DataFrame:
    """Join hierarchy and SKU class context to every actual row."""
    joined = attach_sku_classification(
        inputs.actuals.join(inputs.hierarchy, on="parent_code", how="left"),
        sku_classifications,
    )
    mapping_diagnostics = _mapping_diagnostics(inputs)
    if mapping_diagnostics is not None:
        joined = joined.join(mapping_diagnostics, on="parent_code", how="left")
    else:
        joined = joined.with_columns(
            pl.lit(None, dtype=pl.String).alias("mapping_diagnostic")
        )

    return (
        joined.with_columns(pl.col("mapping_status").fill_null("unmapped"))
        .with_columns(
            pl.when(pl.col("mapping_diagnostic").is_null())
            .then(
                pl.when(pl.col("mapping_status") == "unmapped")
                .then(pl.lit("no hierarchy mapping"))
                .otherwise(pl.lit(None, dtype=pl.String))
            )
            .otherwise(pl.col("mapping_diagnostic"))
            .alias("mapping_diagnostic")
        )
        .select(ACTUAL_POPULATION_COLUMNS)
        .sort(["parent_code", "snop_month"])
    )


def build_analysis_dataset(inputs: AnalysisInputs) -> AnalysisDataset:
    """Left-join hierarchy, actuals, and monthly SKU classes to every forecast row."""
    target_months = inputs.forecast_history.get_column("snop_month").unique().to_list()
    actual_history = (
        inputs.actuals if inputs.actual_history is None else inputs.actual_history
    )
    sku_classifications = build_sku_classifications(actual_history, target_months)
    joined = inputs.forecast_history.join(
        inputs.hierarchy,
        on="parent_code",
        how="left",
    )
    mapping_diagnostics = _mapping_diagnostics(inputs)
    if mapping_diagnostics is not None:
        joined = joined.join(mapping_diagnostics, on="parent_code", how="left")
    else:
        joined = joined.with_columns(
            pl.lit(None, dtype=pl.String).alias("mapping_diagnostic")
        )

    joined = joined.join(
        inputs.actuals,
        on=["parent_code", "snop_month"],
        how="left",
    )
    joined = attach_sku_classification(joined, sku_classifications)
    frame = (
        joined.with_columns(pl.col("mapping_status").fill_null("unmapped"))
        .with_columns(
            pl.when(pl.col("mapping_diagnostic").is_null())
            .then(
                pl.when(pl.col("mapping_status") == "unmapped")
                .then(pl.lit("no hierarchy mapping"))
                .otherwise(pl.lit(None, dtype=pl.String))
            )
            .otherwise(pl.col("mapping_diagnostic"))
            .alias("mapping_diagnostic"),
            pl.when(pl.col("actual_kl").is_null())
            .then(pl.lit("missing"))
            .when(pl.col("actual_kl") == 0)
            .then(pl.lit("matched_zero"))
            .otherwise(pl.lit("matched_positive"))
            .alias("actual_status"),
        )
        .select(ANALYSIS_DATASET_COLUMNS)
        .sort(["parent_code", "snop_month", "calculation_month", "source"])
    )
    return AnalysisDataset(
        frame=frame,
        diagnostics=build_population_diagnostics(frame),
        actual_population=_build_actual_population(inputs, sku_classifications),
        hierarchy_diagnostics=inputs.hierarchy_diagnostics,
    )
