"""Browser-facing adapter for the canonical forecast-analysis view model.

The analytical core remains in :mod:`forecast_analysis`. This module owns the
HTTP/browser contract: request validation, filter construction, bounded JSON
projections, product-detail selection, and request-faithful CSV exports.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
from threading import Event, RLock
from typing import Any, Literal, cast

import polars as pl

from forecast_analysis import (
    AnalysisDataset,
    DashboardFilters,
    VintageAccuracySeries,  # pyright: ignore[reportAttributeAccessIssue]
    VintageRule,
    available_filter_values,
    build_analysis_dataset,
    build_common_vintage_accuracy,  # pyright: ignore[reportAttributeAccessIssue]
    build_dashboard_view,
    build_vintage_gap_drilldown,  # pyright: ignore[reportAttributeAccessIssue]
    build_product_detail,
    build_product_postmortem,  # pyright: ignore[reportAttributeAccessIssue]
    build_product_year_overlay,  # pyright: ignore[reportAttributeAccessIssue]
    load_analysis_inputs,
    with_display_brand,
)
from forecast_analysis.dashboard import DashboardView
from forecast_analysis.filters import available_product_filter_values
from forecast_analysis.sku_classification import SKU_CLASSES  # pyright: ignore[reportMissingImports]

DEFAULT_FORECAST_HISTORY = Path(
    "artifacts/forecast_history/consolidated/forecast_history_waterfall.csv"
)
DEFAULT_HIERARCHY = Path("artifacts/ph/PH_FG.xlsx")
DEFAULT_ACTUALS = Path("artifacts/secondary_sales")
QUALITY_CATEGORIES = ("hierarchy", "actual", "pairs", "source_availability")
ACCURACY_BANDS = {
    "below_0": (-1_000_000.0, 0.0),
    "0_50": (0.0, 50.0),
    "50_100": (50.0, 100.0),
    "above_100": (100.0, 1_000_000.0),
}
BIAS_BANDS = {
    "below_0": (-1_000_000.0, 0.0),
    "0_50": (0.0, 50.0),
    "above_50": (50.0, 1_000_000.0),
}
MODULE_FIELDS = {
    "trends": (
        "monthly_performance",
        "monthly_audit",
        "horizon_performance",
        "horizon_audit",
    ),
    "heatmap": ("brand_target_month_performance",),
    "comparison": ("comparison",),
    "exceptions": (
        "metrics",
        "exceptions",
        "revision_diagnostics",
        "revision_history",
        "revision_scatter",
        "revision_actions",
        "revision_drilldown",
    ),
    "quality": ("quality",),
}


class DashboardRequestError(ValueError):
    """A browser request violated the dashboard adapter contract."""


@dataclass(frozen=True)
class _ComputedView:
    request: dict[str, Any]
    options: dict[str, Any]
    view: DashboardView
    product_detail: dict[str, Any] | None
    payload: dict[str, Any]


@dataclass
class _PendingView:
    ready: Event
    result: _ComputedView | None = None
    error: BaseException | None = None


def _iso(value: date | datetime) -> str:
    return value.isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Normalize numeric payload values used by derived dashboard projections."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, (date, datetime)):
        return _iso(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    if hasattr(value, "item"):
        try:
            return _json_value(value.item())
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _rows(
    frame: pl.DataFrame,
    *,
    columns: tuple[str, ...] | list[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    selected = frame
    if columns is not None:
        available = [column for column in columns if column in selected.columns]
        selected = selected.select(available)
    if limit is not None:
        selected = selected.head(limit)
    return [_json_value(row) for row in selected.to_dicts()]


def _frame_payload(
    frame: pl.DataFrame,
    *,
    columns: tuple[str, ...] | list[str] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    return {
        "total": frame.height,
        "rows": _rows(frame, columns=columns, limit=limit),
    }


def _revision_action_sku_rows(
    material: pl.DataFrame,
    harmful: pl.DataFrame,
) -> list[dict[str, Any]]:
    """Aggregate the action queue to one row per SKU without losing month evidence."""
    harmful_by_parent: dict[Any, list[dict[str, Any]]] = {}
    for row in _rows(harmful):
        harmful_by_parent.setdefault(row.get("parent_code"), []).append(row)

    monthly_by_parent: dict[Any, list[dict[str, Any]]] = {
        parent_code: [] for parent_code in harmful_by_parent
    }
    for row in _rows(material):
        parent_code = row.get("parent_code")
        if parent_code not in monthly_by_parent:
            continue
        error_improvement = _safe_float(row.get("error_improvement_kl"))
        monthly_by_parent[parent_code].append(
            {
                "snop_month": row.get("snop_month"),
                "actual_kl": row.get("actual_kl"),
                "revision_kl": row.get("revision_kl"),
                "error_improvement_kl": error_improvement,
                "impact_kl": max(-error_improvement, 0.0),
                "revision_direction": row.get("revision_direction"),
                "revision_outcome": row.get("revision_outcome"),
            }
        )

    sku_rows: list[dict[str, Any]] = []
    for parent_code, harmful_rows in harmful_by_parent.items():
        monthly = sorted(
            monthly_by_parent[parent_code],
            key=lambda point: str(point.get("snop_month") or ""),
        )
        latest = monthly[-1] if monthly else {}
        direction_impact = {"up": 0.0, "down": 0.0}
        for row in harmful_rows:
            direction = row.get("revision_direction")
            if direction in direction_impact:
                direction_impact[direction] += _safe_float(row.get("impact_kl"))
        revision_direction = max(
            direction_impact,
            key=lambda direction: (direction_impact[direction], direction == "up"),
        )
        first = harmful_rows[0]
        sku_rows.append(
            {
                "parent_code": parent_code,
                "parent_description": first.get("parent_description"),
                "brand": first.get("brand"),
                "latest_snop_month": latest.get("snop_month"),
                "latest_actual_kl": latest.get("actual_kl"),
                "month_count": len(monthly),
                "harmful_month_count": len(harmful_rows),
                "impact_kl": sum(
                    _safe_float(row.get("impact_kl")) for row in harmful_rows
                ),
                "net_error_improvement_kl": sum(
                    _safe_float(point.get("error_improvement_kl"))
                    for point in monthly
                ),
                "revision_direction": revision_direction,
                "planner_action": (
                    "Validate uplift"
                    if revision_direction == "up"
                    else "Check demand reduction"
                ),
                "monthly_performance": monthly,
            }
        )

    sku_rows.sort(
        key=lambda row: (-_safe_float(row["impact_kl"]), str(row["parent_code"]))
    )
    for priority_rank, row in enumerate(sku_rows, start=1):
        row["priority_rank"] = priority_rank
    return sku_rows


def _revision_action_payload(
    frame: pl.DataFrame,
    source: str,
    tolerance_kl: float,
) -> dict[str, Any]:
    """Build source-scoped planner actions from complete revision pairs."""
    if "source" in frame.columns:
        frame = frame.filter(pl.col("source") == source)
    required = {"revision_kl", "error_improvement_kl", "actual_kl"}
    if frame.height == 0 or not required.issubset(frame.columns):
        return {
            "source": source,
            "complete": 0,
            "material": 0,
            "improved": 0,
            "worsened": 0,
            "neutral": 0,
            "effectiveness_pct": None,
            "total_error_improvement_kl": 0.0,
            "harmful_error_kl": 0.0,
            "top_action_error_kl": 0.0,
            "top_action_share_pct": None,
            "harmful_up": {"count": 0, "error_kl": 0.0},
            "harmful_down": {"count": 0, "error_kl": 0.0},
            "rows": [],
            "sku_rows": [],
        }

    valid = frame.filter(
        (pl.col("pair_status") == "complete")
        & pl.col("revision_kl").is_not_null()
        & pl.col("error_improvement_kl").is_not_null()
    )
    material = valid.filter(pl.col("revision_kl").abs() > tolerance_kl)
    improved = material.filter(pl.col("error_improvement_kl") > tolerance_kl)
    worsened = material.filter(pl.col("error_improvement_kl") < -tolerance_kl)
    neutral = material.filter(pl.col("error_improvement_kl").abs() <= tolerance_kl)
    harmful = worsened.with_columns(
        (-pl.col("error_improvement_kl")).alias("impact_kl")
    ).sort(["impact_kl", "actual_kl"], descending=True)
    action_columns = [
        column
        for column in [
            "source",
            "parent_code",
            "parent_description",
            "brand",
            "snop_month",
            "actual_kl",
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
            "impact_kl",
        ]
        if column in harmful.columns
    ]
    action_rows = harmful.select(action_columns)
    top_action_rows = action_rows.head(12)
    harmful_up = harmful.filter(pl.col("revision_direction") == "up")
    harmful_down = harmful.filter(pl.col("revision_direction") == "down")
    try:
        total_error_improvement_kl = float(
            valid.get_column("error_improvement_kl").sum() or 0.0
        )
        harmful_error_kl = float(harmful.get_column("impact_kl").sum() or 0.0)
        top_action_error_kl = float(
            top_action_rows.get_column("impact_kl").sum() or 0.0
        )
        harmful_up_error_kl = float(
            harmful_up.get_column("impact_kl").sum() or 0.0
        )
        harmful_down_error_kl = float(
            harmful_down.get_column("impact_kl").sum() or 0.0
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("revision action totals must be numeric") from exc
    return {
        "source": source,
        "complete": valid.height,
        "material": material.height,
        "improved": improved.height,
        "worsened": worsened.height,
        "neutral": neutral.height,
        "effectiveness_pct": (
            improved.height / material.height * 100 if material.height else None
        ),
        "total_error_improvement_kl": total_error_improvement_kl,
        "harmful_error_kl": harmful_error_kl,
        "top_action_error_kl": top_action_error_kl,
        "top_action_share_pct": (
            top_action_error_kl / harmful_error_kl * 100
            if harmful_error_kl
            else None
        ),
        "harmful_up": {
            "count": harmful_up.height,
            "error_kl": harmful_up_error_kl,
        },
        "harmful_down": {
            "count": harmful_down.height,
            "error_kl": harmful_down_error_kl,
        },
        "rows": _rows(action_rows),
        "sku_rows": _revision_action_sku_rows(material, harmful),
    }


def _revision_drilldown_payload(
    frame: pl.DataFrame,
    source: str,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    """Rank parent-level evidence for each revision outcome card."""
    if "source" in frame.columns:
        frame = frame.filter(pl.col("source") == source)
    required = {
        "parent_code",
        "parent_description",
        "brand",
        "snop_month",
        "actual_kl",
        "absolute_error_b_kl",
        "revision_kl",
        "error_improvement_kl",
        "revision_direction",
        "revision_outcome",
        "pair_status",
    }
    empty_categories = {
        category: {"total_parents": 0, "rows": []}
        for category in ("improved", "worsened", "neutral", "unchanged")
    }
    if frame.height == 0 or not required.issubset(frame.columns):
        return {
            "source": source,
            "limit": limit,
            "ranking": "error_impact_desc",
            "categories": empty_categories,
        }

    complete = frame.filter(pl.col("pair_status") == "complete")
    subsets = {
        "improved": complete.filter(pl.col("revision_outcome") == "improved"),
        "worsened": complete.filter(pl.col("revision_outcome") == "worsened"),
        "neutral": complete.filter(
            (pl.col("revision_outcome") == "neutral")
            & (pl.col("revision_direction") != "unchanged")
        ),
        "unchanged": complete.filter(pl.col("revision_direction") == "unchanged"),
    }
    categories: dict[str, dict[str, Any]] = {}
    for category, subset in subsets.items():
        grouped = subset.group_by("parent_code").agg(
            pl.col("parent_description").drop_nulls().first(),
            pl.col("brand").drop_nulls().first(),
            pl.len().cast(pl.Int64).alias("observations"),
            pl.col("snop_month").n_unique().cast(pl.Int64).alias("target_months"),
            pl.col("actual_kl").fill_null(0.0).sum().alias("actual_kl"),
            pl.col("absolute_error_b_kl")
            .fill_null(0.0)
            .sum()
            .alias("absolute_error_kl"),
            pl.col("error_improvement_kl")
            .fill_null(0.0)
            .sum()
            .alias("net_error_improvement_kl"),
            pl.col("revision_kl").fill_null(0.0).sum().alias("revision_kl"),
        )
        if grouped.height:
            impact = (
                pl.col("net_error_improvement_kl").abs()
                if category in {"improved", "worsened"}
                else pl.col("absolute_error_kl")
            )
            grouped = (
                grouped.with_columns(
                    pl.lit(category).alias("category"),
                    impact.alias("impact_kl"),
                )
                .sort(
                    ["impact_kl", "absolute_error_kl", "parent_code"],
                    descending=[True, True, False],
                )
                .with_row_index("rank", offset=1)
            )
        categories[category] = {
            "total_parents": grouped.height,
            "rows": _rows(grouped.head(limit)),
        }
    return {
        "source": source,
        "limit": limit,
        "ranking": "error_impact_desc",
        "categories": categories,
    }


def _bounded_score(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _add_revision_effectiveness_scores(points: list[dict[str, Any]]) -> None:
    """Add cumulative, explainable effectiveness scores to vintage points.

    V1 is a neutral score baseline. Each later vintage scores the cumulative
    path from V1 through that vintage using accuracy gain (50%), error removed
    per forecast movement (30%), and movement-weighted consistency (20%).
    """
    if not points:
        return
    oldest_error = cast(float, points[0].get("absolute_error_kl") or 0.0)
    error_denominator = max(abs(oldest_error), 1.0)
    cumulative_movement = 0.0
    helpful_movement = 0.0
    harmful_movement = 0.0
    helpful_count = 0
    harmful_count = 0
    neutral_count = 0
    for index, point in enumerate(points):
        if index:
            movement = cast(float, point.get("revision_movement_kl") or 0.0)
            cumulative_movement += movement
            outcome = point.get("revision_outcome")
            if outcome == "improved":
                helpful_movement += movement
                helpful_count += 1
            elif outcome == "worsened":
                harmful_movement += movement
                harmful_count += 1
            else:
                neutral_count += 1
        current_error = cast(float, point.get("absolute_error_kl") or 0.0)
        error_removed = oldest_error - current_error
        accuracy_ratio = _bounded_score(error_removed / error_denominator)
        efficiency_ratio = (
            _bounded_score(error_removed / cumulative_movement)
            if cumulative_movement
            else 0.0
        )
        consistency_ratio = (
            (helpful_movement - harmful_movement) / cumulative_movement
            if cumulative_movement
            else 0.0
        )
        score = 50.0 + 50.0 * (
            0.50 * accuracy_ratio
            + 0.30 * efficiency_ratio
            + 0.20 * _bounded_score(consistency_ratio)
        )
        bounded_score = max(0.0, min(100.0, score))
        previous_score = (
            cast(float, points[index - 1]["revision_effectiveness_score"])
            if index
            else bounded_score
        )
        point.update(
            {
                "vintage_index": index + 1,
                "revision_effectiveness_score": bounded_score,
                "accuracy_gain_score": 50.0 + 50.0 * accuracy_ratio,
                "revision_efficiency_score": 50.0 + 50.0 * efficiency_ratio,
                "revision_consistency_score": 50.0
                + 50.0 * _bounded_score(consistency_ratio),
                "score_change": bounded_score - previous_score,
                "cumulative_error_removed_kl": error_removed,
                "cumulative_movement_kl": cumulative_movement,
                "helpful_revision_count": helpful_count,
                "harmful_revision_count": harmful_count,
                "neutral_revision_count": neutral_count,
            }
        )


def _revision_history_payload(
    view: DashboardView,
    source: str,
    *,
    month_limit: int = 6,
) -> dict[str, Any]:
    """Build fixed-cohort forecast paths through the latest actual month.

    Each target month is independent. Its five vintage points expose a
    cumulative revision-effectiveness score, while the forecast and error
    fields preserve the underlying revision evidence. Only products present in
    every displayed vintage for that target month are retained, so movement
    reflects forecast revisions rather than changing product coverage. Future
    forecast-only months are excluded by anchoring the six-month window to the
    latest selected actual month.
    """
    required = {
        "source",
        "parent_code",
        "snop_month",
        "calculation_month",
        "forecast_kl",
        "actual_kl",
    }
    frame = view.filtered_population
    actual_months = (
        view.selected_actual_population.get_column("snop_month").drop_nulls()
        if "snop_month" in view.selected_actual_population.columns
        else pl.Series([], dtype=pl.Date)
    )
    latest_actual_month = cast(
        date | datetime | None,
        actual_months.max() if actual_months.len() else None,
    )
    empty_payload = {
        "source": source,
        "month_limit": month_limit,
        "baseline": "oldest_available",
        "latest_actual_month": (
            _iso(latest_actual_month) if latest_actual_month is not None else None
        ),
        "months": [],
    }
    if (
        frame.height == 0
        or not required.issubset(frame.columns)
        or latest_actual_month is None
    ):
        return empty_payload

    frame = frame.filter(
        (pl.col("source") == source)
        & (pl.col("snop_month") <= latest_actual_month)
        & pl.col("calculation_month").is_not_null()
        & pl.col("forecast_kl").is_not_null()
        & pl.col("actual_kl").is_not_null()
    )
    target_months = sorted(frame.get_column("snop_month").unique().to_list())
    months: list[dict[str, Any]] = []
    for target_month in target_months:
        target_frame = frame.filter(pl.col("snop_month") == target_month)
        calculation_months = sorted(
            target_frame.get_column("calculation_month").unique().to_list()
        )[-5:]
        vintage_count = len(calculation_months)
        if vintage_count < 5:
            continue
        target_frame = target_frame.filter(
            pl.col("calculation_month").is_in(calculation_months)
        )
        common_products = (
            target_frame.group_by("parent_code")
            .agg(pl.col("calculation_month").n_unique().alias("vintage_count"))
            .filter(pl.col("vintage_count") == vintage_count)
            .select("parent_code")
        )
        if common_products.height == 0:
            continue
        cohort_history = (
            target_frame.join(common_products, on="parent_code", how="semi")
            .sort(["parent_code", "calculation_month"])
            .with_columns(
                (
                    pl.col("forecast_kl")
                    - pl.col("forecast_kl").shift(1).over("parent_code")
                )
                .abs()
                .fill_null(0.0)
                .alias("_revision_movement_kl")
            )
        )
        history = (
            cohort_history.group_by("calculation_month")
            .agg(
                pl.col("forecast_kl").sum().alias("forecast_kl"),
                pl.when(pl.col("actual_kl") > 0)
                .then(pl.col("actual_kl"))
                .otherwise(0.0)
                .sum()
                .alias("actual_kl"),
                pl.when(pl.col("actual_kl") > 0)
                .then((pl.col("forecast_kl") - pl.col("actual_kl")).abs())
                .otherwise(0.0)
                .sum()
                .alias("absolute_error_kl"),
                pl.col("_revision_movement_kl")
                .sum()
                .alias("revision_movement_kl"),
            )
            .sort("calculation_month")
        )
        oldest_forecast = cast(float, history.item(0, "forecast_kl"))
        oldest_actual = cast(float, history.item(0, "actual_kl"))
        oldest_absolute_error = cast(
            float, history.item(0, "absolute_error_kl")
        )
        if oldest_forecast == 0:
            history = history.with_columns(
                pl.when(pl.col("forecast_kl") == 0)
                .then(pl.lit(0.0))
                .otherwise(pl.lit(None, dtype=pl.Float64))
                .alias("delta_pct")
            )
        else:
            history = history.with_columns(
                (
                    (pl.col("forecast_kl") - oldest_forecast)
                    / abs(oldest_forecast)
                    * 100
                ).alias("delta_pct")
            )
        history = history.with_columns(
            pl.when(pl.col("actual_kl") > 0)
            .then(
                (1 - pl.col("absolute_error_kl") / pl.col("actual_kl")) * 100
            )
            .otherwise(pl.lit(None, dtype=pl.Float64))
            .alias("forecast_accuracy_pct")
        )
        history = history.with_columns(
            pl.col("calculation_month")
            .shift(1)
            .alias("previous_calculation_month"),
            pl.col("forecast_kl").shift(1).alias("previous_forecast_kl"),
            pl.col("absolute_error_kl")
            .shift(1)
            .alias("previous_absolute_error_kl"),
            (pl.col("forecast_kl") - pl.col("forecast_kl").shift(1)).alias(
                "revision_kl"
            ),
            (
                pl.col("absolute_error_kl").shift(1)
                - pl.col("absolute_error_kl")
            ).alias("error_improvement_kl"),
            (
                pl.col("forecast_accuracy_pct")
                - pl.col("forecast_accuracy_pct").shift(1)
            ).alias("fa_improvement_pp"),
            (
                pl.col("forecast_accuracy_pct")
                - pl.col("forecast_accuracy_pct").first()
            ).alias("net_fa_improvement_pp"),
        )
        tolerance = view.filters.revision_tolerance_kl
        history = history.with_columns(
            pl.when(pl.col("error_improvement_kl").is_null())
            .then(pl.lit("baseline"))
            .when(pl.col("error_improvement_kl") > tolerance)
            .then(pl.lit("improved"))
            .when(pl.col("error_improvement_kl") < -tolerance)
            .then(pl.lit("worsened"))
            .otherwise(pl.lit("neutral"))
            .alias("revision_outcome")
        )
        points = _rows(history)
        _add_revision_effectiveness_scores(points)
        latest = points[-1]
        months.append(
            {
                "snop_month": _iso(target_month),
                "vintage_count": history.height,
                "product_count": common_products.height,
                "effectiveness_baseline": 50.0,
                "latest_effectiveness_score": latest["revision_effectiveness_score"],
                "latest_accuracy_gain_score": latest["accuracy_gain_score"],
                "latest_revision_efficiency_score": latest["revision_efficiency_score"],
                "latest_revision_consistency_score": latest["revision_consistency_score"],
                "actual_kl": latest["actual_kl"],
                "oldest_calculation_month": points[0]["calculation_month"],
                "latest_calculation_month": latest["calculation_month"],
                "oldest_forecast_kl": points[0]["forecast_kl"],
                "latest_forecast_kl": latest["forecast_kl"],
                "oldest_forecast_accuracy_pct": points[0][
                    "forecast_accuracy_pct"
                ],
                "latest_forecast_accuracy_pct": latest[
                    "forecast_accuracy_pct"
                ],
                "oldest_absolute_error_kl": oldest_absolute_error,
                "latest_absolute_error_kl": latest["absolute_error_kl"],
                "net_error_improvement_kl": (
                    oldest_absolute_error - latest["absolute_error_kl"]
                ),
                "net_fa_improvement_pp": latest["net_fa_improvement_pp"],
                "latest_delta_pct": latest["delta_pct"],
                "points": points,
            }
        )
    months = months[-month_limit:]
    return {
        "source": source,
        "month_limit": month_limit,
        "baseline": "oldest_available",
        "latest_actual_month": (
            months[-1]["snop_month"] if months else _iso(latest_actual_month)
        ),
        "months": months,
    }


def _box_plot_summary(frame: pl.DataFrame, column: str) -> dict[str, Any]:
    if column not in frame.columns:
        values = pl.Series(column, [], dtype=pl.Float64)
    else:
        values = frame.get_column(column).cast(pl.Float64).drop_nulls().drop_nans()
    if values.len() == 0:
        return {
            "count": 0,
            "min": None,
            "q1": None,
            "median": None,
            "q3": None,
            "max": None,
            "whisker_low": None,
            "whisker_high": None,
        }

    q1 = cast(float, values.quantile(0.25, interpolation="linear"))
    median = cast(float, values.quantile(0.5, interpolation="linear"))
    q3 = cast(float, values.quantile(0.75, interpolation="linear"))
    spread = q3 - q1
    lower_fence = q1 - 1.5 * spread
    upper_fence = q3 + 1.5 * spread
    try:
        minimum = values.min()
        maximum = values.max()
        whisker_low = values.filter(values >= lower_fence).min()
        whisker_high = values.filter(values <= upper_fence).max()
        return {
            "count": values.len(),
            "min": float(cast(float, minimum)),
            "q1": float(q1),
            "median": float(median),
            "q3": float(q3),
            "max": float(cast(float, maximum)),
            "whisker_low": float(cast(float, whisker_low)),
            "whisker_high": float(cast(float, whisker_high)),
        }
    except (TypeError, ValueError) as exc:
        raise ValueError(f"could not summarize numeric distribution {column!r}") from exc


def _volume_distributions(view: DashboardView, source: str) -> dict[str, Any]:
    monthly = view.monthly_performance
    if "source" in monthly.columns:
        monthly = monthly.filter(pl.col("source") == source)
    selected = monthly.filter(
        pl.col("vintage_b_forecast_kl").is_not_null()
        & pl.col("actual_kl").is_not_null()
    )
    return {
        "actual": _box_plot_summary(selected, "actual_kl"),
        "forecast": _box_plot_summary(selected, "vintage_b_forecast_kl"),
    }


def _accuracy_vintage_rules(horizons: list[int]) -> tuple[VintageRule, ...]:
    """Return canonical M5-to-M2 choices, excluding fixed M1 latest."""
    unexpected = sorted(set(horizons).difference(range(1, 6)))
    if unexpected:
        raise ValueError(f"unsupported forecast accuracy horizons: {unexpected}")
    return (
        VintageRule.oldest_available(),
        VintageRule.specific_horizon(4),
        VintageRule.specific_horizon(3),
        VintageRule.specific_horizon(2),
    )


def _accuracy_vintage_rows(
    series: VintageAccuracySeries,
) -> list[dict[str, Any]]:
    return [
        {
            "snop_month": _iso(row.target_month),
            "forecast_accuracy_pct": row.forecast_accuracy_pct,
            "forecast_kl": row.forecast_kl,
            "wape_pct": (
                100.0
                * row.absolute_error_numerator_kl
                / row.actual_denominator_kl
                if row.actual_denominator_kl > 0
                else None
            ),
            "bias_pct": (
                100.0 * row.bias_numerator_kl / row.actual_denominator_kl
                if row.actual_denominator_kl > 0
                else None
            ),
            "revision_effectiveness_pct": row.revision_effectiveness_pct,
            "effectiveness_numerator": row.effectiveness_numerator,
            "effectiveness_denominator": row.effectiveness_denominator,
            "eligible_parents": row.eligible_parents,
            "actual_denominator_kl": row.actual_denominator_kl,
            "absolute_error_numerator_kl": row.absolute_error_numerator_kl,
            "latest_absolute_error_numerator_kl": (
                row.latest_absolute_error_numerator_kl
            ),
        }
        for row in series.rows
    ]


def _accuracy_vintages(
    view: DashboardView,
    source: str,
    selected_ids: list[str],
    horizons: list[int],
    revision_tolerance_kl: float,
) -> dict[str, Any]:
    """Project canonical common-cohort results without hiding unselected options."""
    option_rules = _accuracy_vintage_rules(horizons)
    rules_by_id = {rule.label: rule for rule in option_rules}
    selected_rules = tuple(rules_by_id[rule_id] for rule_id in selected_ids)
    result = build_common_vintage_accuracy(
        view.filtered_population,
        source,
        comparison_rules=selected_rules,
        revision_tolerance_kl=revision_tolerance_kl,
    )
    selected_series = {series.rule_id: series for series in result.series}

    options = []
    for rule in option_rules:
        series = selected_series.get(rule.label)
        options.append(
            {
                "id": rule.label,
                "label": (
                    "Oldest (5 months ahead)"
                    if rule.kind == "oldest_available"
                    else f"{rule.value} months ahead"
                ),
                "rule": {"kind": rule.kind, "value": _json_value(rule.value)},
                "selected": series is not None,
                "rows": _accuracy_vintage_rows(series) if series is not None else [],
            }
        )

    latest_rule = VintageRule.latest_available()
    latest = selected_series[latest_rule.label]
    primary = result.series[0]
    overview = result.overview
    cohort_monthly = pl.DataFrame(
        [
            {
                "actual_kl": row.actual_denominator_kl,
                "forecast_kl": row.forecast_kl,
            }
            for row in primary.rows
            if row.eligible_parents > 0
        ],
        schema={"actual_kl": pl.Float64, "forecast_kl": pl.Float64},
    )
    return {
        "latest": {
            "id": latest.rule_id,
            "label": latest.label,
            "rule": {"kind": latest.rule.kind, "value": _json_value(latest.rule.value)},
            "fixed": True,
            "rows": _accuracy_vintage_rows(latest),
        },
        "options": options,
        "overview": {
            "primary": {
                "id": overview.primary_rule_id,
                "label": overview.primary_label,
                "rule": {
                    "kind": primary.rule.kind,
                    "value": _json_value(primary.rule.value),
                },
            },
            "cohort_months": cohort_monthly.height,
            "wape_examples": [
                {
                    "parent_code": row.parent_code,
                    "parent_description": row.parent_description,
                    "snop_month": _iso(row.target_month),
                    "forecast_kl": row.forecast_kl,
                    "actual_kl": row.actual_kl,
                    "absolute_error_kl": row.absolute_error_kl,
                    "direction": row.direction,
                }
                for row in result.wape_examples
            ],
            "metrics": {
                "forecast_accuracy_pct": overview.forecast_accuracy_pct,
                "wape_pct": overview.wape_pct,
                "bias_pct": overview.bias_pct,
                "accuracy_numerator_kl": overview.accuracy_numerator_kl,
                "accuracy_denominator_actual_kl": (
                    overview.accuracy_denominator_actual_kl
                ),
                "bias_numerator_kl": overview.bias_numerator_kl,
                "bias_denominator_actual_kl": overview.bias_denominator_actual_kl,
                "eligible_observations": overview.eligible_observations,
                "accuracy_delta_pp": overview.accuracy_delta_pp,
                "revision_effectiveness_pct": (
                    overview.revision_effectiveness_pct
                ),
                "effectiveness_numerator": overview.effectiveness_numerator,
                "effectiveness_denominator": overview.effectiveness_denominator,
                "primary_error_kl": overview.primary_error_kl,
                "latest_error_kl": overview.latest_error_kl,
            },
            "volume_distributions": {
                "actual": _box_plot_summary(cohort_monthly, "actual_kl"),
                "forecast": _box_plot_summary(cohort_monthly, "forecast_kl"),
            },
        },
    }


def _vintage_gap_payload(
    view: DashboardView,
    source: str,
    selected_ids: list[str],
    horizons: list[int],
    target_month: date,
) -> dict[str, Any]:
    """Project one on-demand month-level WAPE reconciliation."""
    option_rules = _accuracy_vintage_rules(horizons)
    rules_by_id = {rule.label: rule for rule in option_rules}
    selected_rules = tuple(
        rule for rule in option_rules if rule.label in set(selected_ids)
    )
    if not selected_rules:
        raise DashboardRequestError(
            "select at least one historical accuracy vintage to inspect gap drivers"
        )
    result = build_vintage_gap_drilldown(
        view.filtered_population,
        source,
        selected_rules,
        target_month,
    )
    return {
        "source": result.source,
        "target_month": _iso(result.target_month),
        "baseline": {
            "id": result.baseline_rule_id,
            "label": result.baseline_label,
            "rule": {
                "kind": rules_by_id[result.baseline_rule_id].kind,
                "value": _json_value(rules_by_id[result.baseline_rule_id].value),
            },
        },
        "latest": {
            "id": result.latest_rule_id,
            "label": result.latest_label,
            "rule": {"kind": "latest_available", "value": None},
        },
        "summary": {
            "eligible_parents": result.eligible_parents,
            "actual_denominator_kl": result.actual_denominator_kl,
            "baseline_absolute_error_kl": result.baseline_absolute_error_kl,
            "latest_absolute_error_kl": result.latest_absolute_error_kl,
            "baseline_wape_pct": result.baseline_wape_pct,
            "latest_wape_pct": result.latest_wape_pct,
            "net_wape_improvement_pp": result.net_wape_improvement_pp,
            "gross_fix_kl": result.gross_fix_kl,
            "gross_fix_wape_pp": result.gross_fix_wape_pp,
            "regression_kl": result.regression_kl,
            "regression_wape_pp": result.regression_wape_pp,
        },
        "brands": [
            {
                "brand": row.brand,
                "parent_count": row.parent_count,
                "actual_kl": row.actual_kl,
                "baseline_forecast_kl": row.baseline_forecast_kl,
                "latest_forecast_kl": row.latest_forecast_kl,
                "baseline_absolute_error_kl": row.baseline_absolute_error_kl,
                "latest_absolute_error_kl": row.latest_absolute_error_kl,
                "error_change_kl": row.error_change_kl,
                "wape_contribution_pp": row.wape_contribution_pp,
                "gross_fix_kl": row.gross_fix_kl,
                "gross_fix_wape_pp": row.gross_fix_wape_pp,
                "regression_kl": row.regression_kl,
                "regression_wape_pp": row.regression_wape_pp,
            }
            for row in result.brands
        ],
        "parents": [
            {
                "brand": row.brand,
                "parent_code": row.parent_code,
                "parent_description": row.parent_description,
                "actual_kl": row.actual_kl,
                "baseline_forecast_kl": row.baseline_forecast_kl,
                "latest_forecast_kl": row.latest_forecast_kl,
                "baseline_absolute_error_kl": row.baseline_absolute_error_kl,
                "latest_absolute_error_kl": row.latest_absolute_error_kl,
                "error_change_kl": row.error_change_kl,
                "wape_contribution_pp": row.wape_contribution_pp,
                "forecast_revision_kl": row.forecast_revision_kl,
                "baseline_direction": row.baseline_direction,
                "latest_direction": row.latest_direction,
            }
            for row in result.parents
        ],
    }


def _parse_bool(payload: dict[str, Any], field: str, default: bool = False) -> bool:
    value = payload.get(field, default)
    if not isinstance(value, bool):
        raise DashboardRequestError(f"{field} must be a boolean")
    return value


def _parse_string(
    payload: dict[str, Any],
    field: str,
    *,
    default: str | None = None,
    allowed: set[str] | None = None,
) -> str | None:
    value = payload.get(field, default)
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise DashboardRequestError(f"{field} must be a string or null")
    value = value.strip()
    if allowed is not None and value not in allowed:
        raise DashboardRequestError(
            f"{field} must be one of {', '.join(sorted(allowed))}"
        )
    return value


def _parse_string_list(
    payload: dict[str, Any],
    field: str,
    *,
    allowed: set[str] | None = None,
    maximum_items: int = 500,
) -> tuple[str, ...]:
    value = payload.get(field)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise DashboardRequestError(f"{field} must be an array")
    if len(value) > maximum_items:
        raise DashboardRequestError(
            f"{field} must contain at most {maximum_items} values"
        )
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise DashboardRequestError(f"{field} must contain strings")
        item = item.strip()
        if not item:
            raise DashboardRequestError(f"{field} must not contain empty strings")
        if allowed is not None and item not in allowed:
            raise DashboardRequestError(
                f"{field} must contain only {', '.join(sorted(allowed))}"
            )
        if item not in normalized:
            normalized.append(item)
    return tuple(normalized)


def _parse_int(
    payload: dict[str, Any],
    field: str,
    *,
    minimum: int | None = None,
) -> int | None:
    value = payload.get(field)
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise DashboardRequestError(f"{field} must be an integer or null")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise DashboardRequestError(f"{field} must be an integer or null") from exc
    if isinstance(value, float) and not value.is_integer():
        raise DashboardRequestError(f"{field} must be an integer or null")
    if minimum is not None and parsed < minimum:
        raise DashboardRequestError(f"{field} must be at least {minimum}")
    return parsed


def _parse_accuracy_vintage_ids(
    payload: dict[str, Any],
    supported_rules: tuple[VintageRule, ...],
) -> list[str]:
    field = "accuracy_vintage_ids"
    value = payload.get(field, [VintageRule.oldest_available().label])
    if not isinstance(value, list):
        raise DashboardRequestError(f"{field} must be an array")
    if any(not isinstance(item, str) for item in value):
        raise DashboardRequestError(f"{field} must contain strings")
    if len(value) != len(set(value)):
        raise DashboardRequestError(f"{field} must not contain duplicates")

    supported_ids = [rule.label for rule in supported_rules]
    unsupported = [rule_id for rule_id in value if rule_id not in supported_ids]
    if unsupported:
        raise DashboardRequestError(
            f"{field} contains unsupported IDs: {', '.join(unsupported)}"
        )
    selected = set(value)
    return [rule_id for rule_id in supported_ids if rule_id in selected]


def _parse_int_list(
    payload: dict[str, Any],
    field: str,
    *,
    minimum: int | None = None,
    maximum_items: int = 100,
) -> tuple[int, ...]:
    value = payload.get(field)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise DashboardRequestError(f"{field} must be an array")
    if len(value) > maximum_items:
        raise DashboardRequestError(
            f"{field} must contain at most {maximum_items} values"
        )
    normalized: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            raise DashboardRequestError(f"{field} must contain integers")
        if minimum is not None and item < minimum:
            raise DashboardRequestError(
                f"{field} values must be greater than or equal to {minimum}"
            )
        if item not in normalized:
            normalized.append(item)
    return tuple(normalized)


def _parse_float(
    payload: dict[str, Any],
    field: str,
    *,
    default: float = 0.0,
    minimum: float | None = None,
) -> float:
    value = payload.get(field, default)
    if value in (None, ""):
        value = default
    if isinstance(value, bool):
        raise DashboardRequestError(f"{field} must be a finite number")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise DashboardRequestError(f"{field} must be a finite number") from exc
    if not math.isfinite(parsed):
        raise DashboardRequestError(f"{field} must be a finite number")
    if minimum is not None and parsed < minimum:
        raise DashboardRequestError(f"{field} must be at least {minimum}")
    return parsed


def _parse_date(value: Any, field: str) -> date | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise DashboardRequestError(f"{field} must be an ISO date or null")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise DashboardRequestError(f"{field} must be an ISO date or null") from exc


def _single_choice(value: str | None) -> tuple[str, ...] | None:
    return None if value is None else (value,)


def _latest_timestamp(paths: tuple[Path, ...]) -> str:
    files: list[Path] = []
    for path in paths:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(candidate for candidate in path.rglob("*") if candidate.is_file())
    if not files:
        return "unknown"
    latest = max(path.stat().st_mtime for path in files)
    return datetime.fromtimestamp(latest).astimezone().isoformat(timespec="seconds")


class DashboardDataService:
    """Deep adapter from browser requests to the canonical dashboard model.

    The immutable dataset is loaded once. Static options are cached by source
    and comparison mode. Full views are bounded by canonical request JSON, and
    concurrent misses for the same request share one Polars computation.
    """

    def __init__(
        self,
        dataset: AnalysisDataset,
        *,
        refresh_timestamp: str,
        source_label: str,
        cache_size: int = 32,
        today: date | None = None,
    ) -> None:
        if cache_size < 1:
            raise ValueError("cache_size must be positive")
        self.dataset = dataset
        self.refresh_timestamp = refresh_timestamp
        self.source_label = source_label
        self.cache_size = cache_size
        self.current_month = (today or date.today()).replace(day=1)
        self.dataset_version = self._build_dataset_version()
        self._cache: OrderedDict[str, _ComputedView] = OrderedDict()
        self._options_cache: dict[tuple[str, bool], dict[str, Any]] = {}
        self._inflight: dict[str, _PendingView] = {}
        self._cache_lock = RLock()
        self.prewarm_default()

    @classmethod
    def from_paths(
        cls,
        forecast_history_path: Path = DEFAULT_FORECAST_HISTORY,
        hierarchy_path: Path = DEFAULT_HIERARCHY,
        actuals_path: Path = DEFAULT_ACTUALS,
        *,
        cache_size: int = 32,
        today: date | None = None,
    ) -> "DashboardDataService":
        paths = (
            Path(forecast_history_path).resolve(),
            Path(hierarchy_path).resolve(),
            Path(actuals_path).resolve(),
        )
        inputs = load_analysis_inputs(*paths)
        dataset = build_analysis_dataset(inputs)
        return cls(
            dataset,
            refresh_timestamp=_latest_timestamp(paths),
            source_label=" · ".join(path.name for path in paths),
            cache_size=cache_size,
            today=today,
        )

    def bootstrap(self) -> dict[str, Any]:
        """Return the compact first-paint contract for the default request."""
        default_request = self.default_request()
        payload = self.compact_view(default_request)
        payload["contract"] = {**payload["contract"], "kind": "bootstrap"}
        payload["defaults"] = default_request
        return payload

    def compact_view(
        self, raw_request: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Return overview data without lazy module internals.

        After validating ``meta.dataset_version`` and exact ``request`` equality,
        the browser merges a module with ``currentPayload =
        {...currentPayload, ...moduleResponse.data}``. Each key in ``data``
        replaces the complete top-level projection; there is no deep merge.
        """
        computed = self._computed(raw_request or {})
        return self._build_compact_payload(computed)

    def default_request(self) -> dict[str, Any]:
        options = self._filter_options("ml", False)
        months = self._actual_target_months(
            options,
            source="ml",
            comparison_mode=False,
        )
        default_target_end = self._latest_completed_target_month(months)
        return {
            "source": "ml",
            "comparison_mode": False,
            "target_start": _iso(months[0]) if months else None,
            "target_end": _iso(default_target_end) if default_target_end else None,
            "brands": [],
            "sku_classes": [],
            "parent_codes": [],
            "horizon": None,
            "minimum_actual_volume": 0.0,
            "vintage_a": {"kind": "oldest_available", "value": None},
            "vintage_b": {"kind": "latest_available", "value": None},
            "accuracy_vintage_ids": ["oldest_available"],
            "revision_direction": None,
            "revision_outcome": None,
            "revision_tolerance_kl": 0.01,
            "forecast_direction": None,
            "accuracy_band": None,
            "bias_band": None,
            "minimum_absolute_error_kl": 0.0,
            "top_n": None,
            "top_n_metric": "actual_volume",
            "hierarchy_status": None,
            "actual_status": None,
            "pair_status": None,
            "source_availability": None,
            "zero_forecast_only": False,
            "complete_vintage_history_only": False,
            "drilldown_parent_codes": [],
            "product_parent_code": None,
            "product_target_month": None,
        }

    def view(self, raw_request: dict[str, Any] | None = None) -> dict[str, Any]:
        computed = self._computed(raw_request or {})
        return computed.payload

    def prewarm_default(self) -> None:
        """Compute the canonical default view, failing construction on errors."""
        self._computed(self.default_request())

    def module(self, module_name: str, raw_request: dict[str, Any]) -> dict[str, Any]:
        """Return one named slice of the cached full view.

        The browser shallow-merges ``data`` into its compact view. Every field
        replaces one complete top-level projection; no rows or nested objects are
        deep-merged. The normalized request and dataset version let the browser
        reject stale or mixed responses before applying that merge.
        """
        if module_name not in {*MODULE_FIELDS, "product"}:
            raise DashboardRequestError(
                f"unsupported dashboard module {module_name!r}"
            )
        request, _, _, _, _, _ = self._normalize_request(raw_request)
        if module_name == "product":
            base_request = dict(request)
            base_request["product_parent_code"] = None
            base_request["product_target_month"] = None
            computed = self._computed(base_request)
            data = {
                "product_detail": self._build_product_payload(computed.view, request)
            }
        else:
            computed = self._computed(request)
            data = self._module_data(module_name, computed)
        return {
            "contract": {
                "name": "dashboard-module",
                "version": 1,
                "merge": "shallow-root",
            },
            "module": module_name,
            "meta": self._meta_payload(computed),
            "request": request,
            "data": data,
        }

    def product_detail(self, raw_request: dict[str, Any]) -> dict[str, Any] | None:
        """Build one product history from an already cacheable filter scope."""
        request, _, _, _, _, _ = self._normalize_request(raw_request)
        base_request = dict(request)
        base_request["product_parent_code"] = None
        base_request["product_target_month"] = None
        base_view = self._computed(base_request).view
        return self._build_product_payload(base_view, request)

    def vintage_gap_drilldown(self, raw_request: dict[str, Any]) -> dict[str, Any]:
        """Return one month of brand and parent WAPE-gap contributions."""
        target_month = _parse_date(
            raw_request.get("vintage_gap_target_month"),
            "vintage_gap_target_month",
        )
        if target_month is None:
            raise DashboardRequestError("vintage_gap_target_month is required")
        request, options, _, _, _, _ = self._normalize_request(raw_request)
        computed = self._computed(request)
        drilldown = _vintage_gap_payload(
            computed.view,
            request["source"],
            request["accuracy_vintage_ids"],
            cast(list[int], options["horizons"]),
            target_month,
        )
        return {
            "contract": {"name": "vintage-gap-drilldown", "version": 1},
            "meta": self._meta_payload(computed),
            "request": request,
            "drilldown": drilldown,
        }

    def export_csv(
        self,
        raw_request: dict[str, Any],
        *,
        kind: Literal[
            "vintages",
            "revision_actions",
            "quality",
            "scope_exclusions",
        ],
        category: str | None = None,
    ) -> tuple[str, str]:
        """Return filename and CSV for the exact submitted filter request."""
        computed = self._computed(raw_request)
        view = computed.view
        source_suffix = "comparison" if view.filters.comparison_mode else view.filters.source
        if kind == "vintages":
            frame = view.download_frame
            filename = f"forecast_{source_suffix}_filtered_vintages.csv"
        elif kind == "revision_actions":
            source = view.filters.source
            tolerance_kl = view.filters.revision_tolerance_kl
            frame = view.download_frame
            if "source" in frame.columns:
                frame = frame.filter(pl.col("source") == source)
            frame = (
                frame.filter(
                    (pl.col("pair_status") == "complete")
                    & (pl.col("revision_kl").abs() > tolerance_kl)
                    & (pl.col("error_improvement_kl") < -tolerance_kl)
                )
                .with_columns(
                    (-pl.col("error_improvement_kl")).alias("impact_kl"),
                    pl.when(pl.col("revision_direction") == "up")
                    .then(pl.lit("Validate uplift"))
                    .otherwise(pl.lit("Check demand reduction"))
                    .alias("planner_action"),
                )
                .sort(["impact_kl", "actual_kl"], descending=True)
                .with_row_index("priority_rank", offset=1)
            )
            filename = f"forecast_{source}_revision_action_queue.csv"
        elif kind == "quality":
            if category not in QUALITY_CATEGORIES:
                raise DashboardRequestError(
                    f"quality category must be one of {', '.join(QUALITY_CATEGORIES)}"
                )
            frame = view.quality.exceptions[category]
            filename = f"forecast_{source_suffix}_{category}_exceptions.csv"
        elif kind == "scope_exclusions":
            if category not in QUALITY_CATEGORIES:
                raise DashboardRequestError(
                    f"scope-exclusion category must be one of {', '.join(QUALITY_CATEGORIES)}"
                )
            frame = view.quality.scope_exclusions.get(category, pl.DataFrame())
            filename = f"forecast_{source_suffix}_{category}_scope_exclusions.csv"
        else:
            raise DashboardRequestError(f"unsupported export kind {kind!r}")
        return filename, frame.write_csv()

    def _computed(self, raw_request: dict[str, Any]) -> _ComputedView:
        if not isinstance(raw_request, dict):
            raise DashboardRequestError("request body must be a JSON object")
        (
            request,
            options,
            filters,
            vintage_a,
            vintage_b,
            filter_adjustments,
        ) = self._normalize_request(raw_request)
        analysis_request = dict(request)
        analysis_request.pop("accuracy_vintage_ids")
        key = json.dumps(analysis_request, sort_keys=True, separators=(",", ":"))
        cached: _ComputedView | None = None
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
            pending = self._inflight.get(key)
            if pending is None:
                pending = _PendingView(Event())
                self._inflight[key] = pending
                owner = True
            else:
                owner = False
        if cached is not None:
            selected = self._with_accuracy_selection(cached, request)
            return self._with_filter_adjustments(selected, filter_adjustments)
        if not owner:
            pending.ready.wait()
            if pending.error is not None:
                raise pending.error
            if pending.result is None:
                raise RuntimeError("dashboard computation completed without a result")
            selected = self._with_accuracy_selection(pending.result, request)
            return self._with_filter_adjustments(selected, filter_adjustments)

        try:
            view = build_dashboard_view(
                self.dataset.frame,
                self.dataset.actual_population,
                filters,
                vintage_a=vintage_a,
                vintage_b=vintage_b,
                hierarchy_diagnostics=self.dataset.hierarchy_diagnostics,
            )
            product_detail = self._build_product_payload(view, request)
            payload = self._build_payload(request, options, view, product_detail)
            computed = _ComputedView(request, options, view, product_detail, payload)
        except BaseException as exc:
            with self._cache_lock:
                self._inflight.pop(key, None)
                pending.error = exc
                pending.ready.set()
            raise

        with self._cache_lock:
            self._cache[key] = computed
            self._cache.move_to_end(key)
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
            self._inflight.pop(key, None)
            pending.result = computed
            pending.ready.set()
        return self._with_filter_adjustments(computed, filter_adjustments)

    @staticmethod
    def _with_filter_adjustments(
        computed: _ComputedView,
        filter_adjustments: dict[str, dict[str, int]],
    ) -> _ComputedView:
        payload = {**computed.payload, "filter_adjustments": filter_adjustments}
        return _ComputedView(
            computed.request,
            computed.options,
            computed.view,
            computed.product_detail,
            payload,
        )

    def _with_accuracy_selection(
        self,
        computed: _ComputedView,
        request: dict[str, Any],
    ) -> _ComputedView:
        """Reuse the analytical view when only the chart cohort selection changes."""
        if computed.request["accuracy_vintage_ids"] == request["accuracy_vintage_ids"]:
            return computed
        payload = {
            **computed.payload,
            "request": request,
            "accuracy_vintages": _accuracy_vintages(
                computed.view,
                request["source"],
                request["accuracy_vintage_ids"],
                cast(list[int], computed.options["horizons"]),
                request["revision_tolerance_kl"],
            ),
        }
        return _ComputedView(
            request,
            computed.options,
            computed.view,
            computed.product_detail,
            payload,
        )

    def _normalize_request(
        self, raw: dict[str, Any]
    ) -> tuple[
        dict[str, Any],
        dict[str, Any],
        DashboardFilters,
        VintageRule | None,
        VintageRule | None,
        dict[str, dict[str, int]],
    ]:
        source = _parse_string(
            raw, "source", default="ml", allowed={"tm", "ml"}
        ) or "ml"
        comparison_mode = _parse_bool(raw, "comparison_mode")
        options = self._filter_options(source, comparison_mode)

        requested_brands = _parse_string_list(raw, "brands")
        if not requested_brands and (
            legacy_brand := _parse_string(raw, "brand")
        ) is not None:
            requested_brands = (legacy_brand,)
        requested_sku_classes = _parse_string_list(
            raw,
            "sku_classes",
            allowed=set(SKU_CLASSES),
        )
        if not requested_sku_classes and (
            legacy_sku_class := _parse_string(
                raw,
                "sku_class",
                allowed=set(SKU_CLASSES),
            )
        ) is not None:
            requested_sku_classes = (legacy_sku_class,)
        requested_parent_codes = _parse_int_list(
            raw,
            "parent_codes",
            minimum=0,
            maximum_items=500,
        )
        if not requested_parent_codes and (
            legacy_parent_code := _parse_int(raw, "parent_code", minimum=0)
        ) is not None:
            requested_parent_codes = (legacy_parent_code,)
        drilldown_parent_codes = _parse_int_list(
            raw,
            "drilldown_parent_codes",
            minimum=0,
        )

        source_product_availability = available_product_filter_values(
            self.dataset.frame,
            source,
            comparison_mode=comparison_mode,
        )
        available_brands = set(cast(list[str], options["brands"]))
        available_sku_classes = set(
            cast(list[str], source_product_availability["sku_classes"])
        )
        available_parent_codes = {
            cast(int, row["parent_code"])
            for row in cast(list[dict[str, Any]], options["parent_products"])
        }
        brands = tuple(
            value for value in requested_brands if value in available_brands
        )
        sku_classes = tuple(
            value
            for value in requested_sku_classes
            if value in available_sku_classes
        )
        parent_codes = tuple(
            value
            for value in requested_parent_codes
            if value in available_parent_codes
        )
        filter_adjustments = {
            "removed_product_selections": {
                "brands": len(requested_brands) - len(brands),
                "sku_classes": len(requested_sku_classes) - len(sku_classes),
                "parent_codes": len(requested_parent_codes) - len(parent_codes),
            }
        }

        product_availability = available_product_filter_values(
            self.dataset.frame,
            source,
            comparison_mode=comparison_mode,
            brands=brands or None,
            sku_classes=sku_classes or None,
            parent_codes=parent_codes or None,
        )
        incompatible_fields: list[str] = []
        if set(brands) - set(cast(list[str], product_availability["brands"])):
            incompatible_fields.append("brands")
        if set(sku_classes) - set(
            cast(list[str], product_availability["sku_classes"])
        ):
            incompatible_fields.append("sku_classes")
        if set(parent_codes) - set(
            cast(list[int], product_availability["parent_codes"])
        ):
            incompatible_fields.append("parent_codes")
        if incompatible_fields:
            raise DashboardRequestError(
                "product filters are mutually incompatible: "
                + ", ".join(incompatible_fields)
            )

        compatible_parent_codes = set(
            cast(list[int], product_availability["parent_codes"])
        )
        options = {
            **options,
            "parent_products": [
                row
                for row in cast(list[dict[str, Any]], options["parent_products"])
                if cast(int, row["parent_code"]) in compatible_parent_codes
            ],
            "product_availability": product_availability,
        }
        horizon = _parse_int(raw, "horizon", minimum=0)
        available_horizons = cast(list[int], options["horizons"])
        accuracy_vintage_ids = _parse_accuracy_vintage_ids(
            raw,
            _accuracy_vintage_rules(available_horizons),
        )
        if horizon is not None and horizon not in available_horizons:
            raise DashboardRequestError("horizon is not available for the selected source")
        comparison_horizon: int | None = None
        if comparison_mode:
            common_horizons = cast(list[int], options["common_horizons"])
            default_comparison_horizon = cast(
                int | None, options["default_comparison_horizon"]
            )
            comparison_horizon = (
                horizon
                if horizon is not None
                else default_comparison_horizon
            )
            if comparison_horizon is not None and comparison_horizon not in common_horizons:
                raise DashboardRequestError(
                    "comparison horizon must be shared by TM and ML"
                )
            horizon = comparison_horizon

        hierarchy_status = _parse_string(
            raw,
            "hierarchy_status",
            allowed={"mapped", "unmapped", "conflict"},
        )
        actual_status = _parse_string(
            raw,
            "actual_status",
            allowed={"matched_positive", "matched_zero", "missing"},
        )
        pair_status = _parse_string(
            raw,
            "pair_status",
            allowed={
                "complete",
                "missing_a",
                "missing_b",
                "missing_both",
                "missing_actual",
                "zero_actual",
            },
        )
        source_availability = _parse_string(
            raw,
            "source_availability",
            allowed={"tm_only", "ml_only", "both_sources"},
        )
        revision_direction = _parse_string(
            raw,
            "revision_direction",
            allowed={"up", "down", "unchanged"},
        )
        revision_outcome = _parse_string(
            raw,
            "revision_outcome",
            allowed={"improved", "worsened", "neutral"},
        )
        forecast_direction = _parse_string(
            raw,
            "forecast_direction",
            allowed={"over", "under", "within_tolerance"},
        )
        accuracy_band_name = _parse_string(
            raw, "accuracy_band", allowed=set(ACCURACY_BANDS)
        )
        bias_band_name = _parse_string(raw, "bias_band", allowed=set(BIAS_BANDS))
        top_n_metric = _parse_string(
            raw,
            "top_n_metric",
            default="actual_volume",
            allowed={"actual_volume", "absolute_error", "deterioration"},
        ) or "actual_volume"
        top_n = _parse_int(raw, "top_n", minimum=1)

        available_months = self._actual_target_months(
            options,
            source=source,
            comparison_mode=comparison_mode,
            brands=brands or None,
            sku_classes=sku_classes or None,
            parent_codes=parent_codes or drilldown_parent_codes or None,
            horizon=horizon,
            hierarchy_status=hierarchy_status,
            actual_status=actual_status,
            minimum_actual_volume=_parse_float(
                raw,
                "minimum_actual_volume",
                default=0.0,
                minimum=0.0,
            ),
        )
        latest_completed_target_month = self._latest_completed_target_month(
            available_months
        )
        options = {
            **options,
            "target_months": available_months,
            "latest_completed_target_month": latest_completed_target_month,
        }
        target_start = _parse_date(raw.get("target_start"), "target_start")
        target_end = _parse_date(raw.get("target_end"), "target_end")
        if available_months:
            latest_actual_month = available_months[-1]
            if target_start is None:
                target_start = available_months[0]
            elif target_start > latest_actual_month:
                target_start = latest_actual_month
            if target_end is None:
                target_end = latest_completed_target_month
            elif target_end > latest_actual_month:
                target_end = latest_actual_month
        if target_start and target_end and target_start > target_end:
            raise DashboardRequestError("target_start must be on or before target_end")
        target_months = tuple(
            month
            for month in available_months
            if (target_start is None or month >= target_start)
            and (target_end is None or month <= target_end)
        )

        vintage_a = None
        vintage_b = None
        if not comparison_mode:
            vintage_a = self._parse_vintage_rule(
                raw.get("vintage_a"), "vintage_a", "oldest_available", options
            )
            vintage_b = self._parse_vintage_rule(
                raw.get("vintage_b"), "vintage_b", "latest_available", options
            )

        normalized = {
            "source": source,
            "comparison_mode": comparison_mode,
            "target_start": _iso(target_start) if target_start else None,
            "target_end": _iso(target_end) if target_end else None,
            "brands": list(brands),
            "sku_classes": list(sku_classes),
            "parent_codes": list(parent_codes),
            "horizon": horizon,
            "minimum_actual_volume": _parse_float(
                raw,
                "minimum_actual_volume",
                default=0.0,
                minimum=0.0,
            ),
            "vintage_a": self._rule_request(vintage_a, "oldest_available"),
            "vintage_b": self._rule_request(vintage_b, "latest_available"),
            "accuracy_vintage_ids": accuracy_vintage_ids,
            "revision_direction": None if comparison_mode else revision_direction,
            "revision_outcome": None if comparison_mode else revision_outcome,
            "revision_tolerance_kl": _parse_float(
                raw,
                "revision_tolerance_kl",
                default=0.01,
                minimum=0.0,
            ),
            "forecast_direction": None if comparison_mode else forecast_direction,
            "accuracy_band": None if comparison_mode else accuracy_band_name,
            "bias_band": None if comparison_mode else bias_band_name,
            "minimum_absolute_error_kl": (
                0.0
                if comparison_mode
                else _parse_float(
                    raw,
                    "minimum_absolute_error_kl",
                    default=0.0,
                    minimum=0.0,
                )
            ),
            "top_n": None if comparison_mode else top_n,
            "top_n_metric": top_n_metric,
            "hierarchy_status": hierarchy_status,
            "actual_status": actual_status,
            "pair_status": pair_status,
            "source_availability": source_availability,
            "zero_forecast_only": _parse_bool(raw, "zero_forecast_only"),
            "complete_vintage_history_only": _parse_bool(
                raw, "complete_vintage_history_only"
            ),
            "drilldown_parent_codes": (
                [] if comparison_mode else list(drilldown_parent_codes)
            ),
            "product_parent_code": _parse_int(
                raw, "product_parent_code", minimum=0
            ),
            "product_target_month": (
                _iso(value)
                if (value := _parse_date(
                    raw.get("product_target_month"), "product_target_month"
                ))
                else None
            ),
        }
        filters = DashboardFilters(
            source=source,
            comparison_mode=comparison_mode,
            comparison_horizon=comparison_horizon,
            target_months=target_months,
            brands=brands or None,
            sku_classes=sku_classes or None,
            parent_codes=parent_codes or tuple(normalized["drilldown_parent_codes"]) or None,
            horizons=(horizon,) if horizon is not None else None,
            minimum_actual_volume=normalized["minimum_actual_volume"],
            hierarchy_statuses=_single_choice(hierarchy_status),
            actual_statuses=_single_choice(actual_status),
            pair_statuses=_single_choice(pair_status),
            source_availability=_single_choice(source_availability),
            zero_forecast_only=normalized["zero_forecast_only"],
            complete_vintage_history_only=normalized[
                "complete_vintage_history_only"
            ],
            revision_directions=_single_choice(normalized["revision_direction"]),
            revision_outcomes=_single_choice(normalized["revision_outcome"]),
            revision_tolerance_kl=normalized["revision_tolerance_kl"],
            forecast_directions=_single_choice(normalized["forecast_direction"]),
            forecast_accuracy_band=(
                ACCURACY_BANDS[accuracy_band_name]
                if accuracy_band_name and not comparison_mode
                else None
            ),
            bias_band=(
                BIAS_BANDS[bias_band_name]
                if bias_band_name and not comparison_mode
                else None
            ),
            minimum_absolute_error_kl=normalized["minimum_absolute_error_kl"],
            top_n=normalized["top_n"],
            top_n_metric=top_n_metric,
        )
        return normalized, options, filters, vintage_a, vintage_b, filter_adjustments

    def _parse_vintage_rule(
        self,
        raw_rule: Any,
        field: str,
        default_kind: str,
        options: dict[str, Any],
    ) -> VintageRule:
        if raw_rule is None:
            raw_rule = {"kind": default_kind, "value": None}
        if not isinstance(raw_rule, dict):
            raise DashboardRequestError(f"{field} must be an object")
        kind = _parse_string(
            raw_rule,
            "kind",
            default=default_kind,
            allowed={
                "oldest_available",
                "latest_available",
                "specific_calculation_month",
                "specific_horizon",
            },
        ) or default_kind
        value = raw_rule.get("value")
        if kind == "oldest_available":
            return VintageRule.oldest_available()
        if kind == "latest_available":
            return VintageRule.latest_available()
        if kind == "specific_calculation_month":
            month = _parse_date(value, f"{field}.value")
            if month is None or month not in options["calculation_months"]:
                raise DashboardRequestError(
                    f"{field}.value must be an available calculation month"
                )
            return VintageRule.specific_calculation_month(month)
        horizon_payload = {"value": value}
        horizon = _parse_int(horizon_payload, "value", minimum=0)
        if horizon is None or horizon not in options["horizons"]:
            raise DashboardRequestError(
                f"{field}.value must be an available forecast horizon"
            )
        return VintageRule.specific_horizon(horizon)

    def _latest_completed_target_month(self, months: list[date]) -> date | None:
        """Return the latest month before the running month, with a safe fallback."""
        if not months:
            return None
        completed = [month for month in months if month < self.current_month]
        return completed[-1] if completed else months[-1]

    def _actual_target_months(
        self,
        options: dict[str, Any],
        *,
        source: str,
        comparison_mode: bool,
        brands: tuple[str, ...] | None = None,
        sku_classes: tuple[str, ...] | None = None,
        parent_codes: tuple[int, ...] | None = None,
        horizon: int | None = None,
        hierarchy_status: str | None = None,
        actual_status: str | None = None,
        minimum_actual_volume: float = 0.0,
    ) -> list[date]:
        """Return forecast target months through the scoped latest actual month."""
        selected_sources = ("ml", "tm") if comparison_mode else (source,)
        actual_frame = with_display_brand(self.dataset.frame).filter(
            pl.col("source").is_in(selected_sources)
            & pl.col("actual_kl").is_not_null()
        )
        if brands is not None:
            actual_frame = actual_frame.filter(pl.col("brand_display").is_in(brands))
        if sku_classes is not None:
            actual_frame = actual_frame.filter(pl.col("sku_class").is_in(sku_classes))
        if parent_codes is not None:
            actual_frame = actual_frame.filter(pl.col("parent_code").is_in(parent_codes))
        if horizon is not None:
            actual_frame = actual_frame.filter(
                pl.col("forecast_horizon_months") == horizon
            )
        if hierarchy_status is not None:
            actual_frame = actual_frame.filter(
                pl.col("mapping_status") == hierarchy_status
            )
        if actual_status is not None:
            actual_frame = actual_frame.filter(pl.col("actual_status") == actual_status)
        if minimum_actual_volume > 0:
            actual_frame = actual_frame.filter(
                pl.col("actual_kl") >= minimum_actual_volume
            )

        latest_actual_month = cast(
            date | None,
            actual_frame.get_column("snop_month").max()
            if actual_frame.height
            else None,
        )
        forecast_months = cast(list[date], options["target_months"])
        if latest_actual_month is None:
            return []
        return [month for month in forecast_months if month <= latest_actual_month]

    def _filter_options(self, source: str, comparison_mode: bool) -> dict[str, Any]:
        key = (source, comparison_mode)
        with self._cache_lock:
            cached = self._options_cache.get(key)
            if cached is not None:
                return cached
        options = available_filter_values(
            self.dataset.frame,
            source,
            comparison_mode=comparison_mode,
        )
        with self._cache_lock:
            existing = self._options_cache.setdefault(key, options)
            return existing

    def _build_dataset_version(self) -> str:
        identity = json.dumps(
            {
                "source": self.source_label,
                "refresh": self.refresh_timestamp,
                "forecast_rows": self.dataset.frame.height,
                "actual_rows": self.dataset.actual_population.height,
                "actual_history_rows": self.dataset.actual_history.height,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(identity).hexdigest()[:16]

    def _meta_payload(self, computed: _ComputedView | None = None) -> dict[str, Any]:
        return {
            "refresh_timestamp": self.refresh_timestamp,
            "generated_at": (
                computed.payload["meta"]["generated_at"]
                if computed is not None
                else datetime.now().astimezone().isoformat(timespec="seconds")
            ),
            "data_source": self.source_label,
            "dataset_version": self.dataset_version,
            "dataset_rows": self.dataset.frame.height,
            "actual_population_rows": self.dataset.actual_population.height,
            "actual_history_rows": self.dataset.actual_history.height,
            "synthetic": False,
        }

    @staticmethod
    def _module_data(module_name: str, computed: _ComputedView) -> dict[str, Any]:
        fields = MODULE_FIELDS.get(module_name)
        if fields is None:
            raise DashboardRequestError(f"unsupported dashboard module {module_name!r}")
        # These values are the exact bounded projections held by the full-view cache.
        return {field: computed.payload[field] for field in fields}

    def _build_compact_payload(self, computed: _ComputedView) -> dict[str, Any]:
        payload = computed.payload
        return {
            "contract": {
                "name": "dashboard-view",
                "version": 2,
                "kind": "compact",
                "module_endpoint": "/api/module/{module}",
                "module_merge": "shallow-root",
                "modules": [*MODULE_FIELDS, "product"],
            },
            "meta": self._meta_payload(computed),
            "request": computed.request,
            "options": self._options_payload(computed.options),
            "filter_adjustments": payload["filter_adjustments"],
            "state": payload["state"],
            "population_summary": payload["population_summary"],
            "metrics": payload["metrics"],
            "volume_distributions": payload["volume_distributions"],
            "monthly_performance": payload["monthly_performance"],
            "accuracy_vintages": payload["accuracy_vintages"],
        }

    @staticmethod
    def _rule_request(rule: VintageRule | None, default_kind: str) -> dict[str, Any]:
        if rule is None:
            return {"kind": default_kind, "value": None}
        return {"kind": rule.kind, "value": _json_value(rule.value)}

    def _build_product_payload(
        self, view: DashboardView, request: dict[str, Any]
    ) -> dict[str, Any] | None:
        active_keys = view.vintage_pairs.select(
            ["parent_code", "parent_description", "snop_month"]
        ).unique()
        if active_keys.height == 0:
            return None
        parent_code = request["product_parent_code"]
        target_month = (
            date.fromisoformat(request["product_target_month"])
            if request["product_target_month"]
            else None
        )
        if parent_code is None or target_month is None:
            ranked = (
                view.filtered_population.group_by(
                    ["parent_code", "parent_description", "snop_month"]
                )
                .agg(pl.len().alias("vintages"))
                .join(
                    active_keys,
                    on=["parent_code", "parent_description", "snop_month"],
                    how="semi",
                )
                .sort(
                    ["vintages", "snop_month", "parent_code"],
                    descending=[True, True, False],
                )
            )
            candidates = ranked
            if parent_code is not None:
                candidates = candidates.filter(pl.col("parent_code") == parent_code)
                candidates = candidates.sort("snop_month", descending=True)
            elif target_month is not None:
                candidates = candidates.filter(pl.col("snop_month") == target_month)
            if candidates.height == 0:
                candidates = ranked if ranked.height else active_keys
            selected = candidates.head(1).to_dicts()[0]
            parent_code = cast(int, selected["parent_code"])
            target_month = cast(date, selected["snop_month"])
        try:
            detail = build_product_detail(
                self.dataset.frame,
                view.filters,
                parent_code,
                target_month,
                active_key_frame=view.vintage_pairs,
            )
        except ValueError as exc:
            return {
                "error": str(exc),
                "parent_code": parent_code,
                "target_month": _iso(target_month),
            }
        product_options = (
            active_keys.select(["parent_code", "parent_description"])
            .unique()
            .sort(["parent_code", "parent_description"])
        )
        target_options = (
            active_keys.filter(pl.col("parent_code") == parent_code)
            .get_column("snop_month")
            .unique()
            .sort()
            .to_list()
        )
        postmortem = build_product_postmortem(
            view.filtered_population,
            view.vintage_pairs,
            parent_code,
            target_month,
            source=request["source"],
            rolling_months=12,
            revision_tolerance_kl=request["revision_tolerance_kl"],
        )
        year_overlay = build_product_year_overlay(
            self.dataset.frame,
            self.dataset.actual_history,
            parent_code,
            source=request["source"],
            completed_before=self.current_month,
        )
        return {
            "parent_code": detail.parent_code,
            "target_month": _iso(detail.target_month),
            "sources": list(detail.sources),
            "parent_description": detail.parent_description,
            "hierarchy_description": detail.hierarchy_description,
            "brand": detail.brand,
            "sku_class": postmortem.sku_class,
            "mapping_status": detail.mapping_status,
            "actual_kl": detail.actual_kl,
            "actual_status": detail.actual_status,
            "status": detail.status,
            "status_message": detail.status_message,
            "points": _frame_payload(detail.points, limit=120),
            "revisions": _frame_payload(detail.revisions, limit=40),
            "stability": _frame_payload(detail.stability),
            "year_overlay": {
                "source": year_overlay.source,
                "forecast_run": (
                    _iso(year_overlay.forecast_run)
                    if year_overlay.forecast_run is not None
                    else None
                ),
                "actual_through": (
                    _iso(year_overlay.actual_through)
                    if year_overlay.actual_through is not None
                    else None
                ),
                "points": _frame_payload(year_overlay.points),
            },
            "postmortem": {
                "source": postmortem.source,
                "sku_class": postmortem.sku_class,
                "status": postmortem.status,
                "status_message": postmortem.status_message,
                "rolling_performance": _frame_payload(
                    postmortem.rolling_performance
                ),
                "revision_outcomes": _frame_payload(
                    postmortem.revision_outcomes
                ),
                "summary": _json_value(postmortem.summary.as_dict()),
                "peer_benchmarks": _frame_payload(
                    postmortem.peer_benchmarks
                ),
                "commentary": _frame_payload(postmortem.commentary),
                "treatment": _json_value(postmortem.treatment.as_dict()),
            },
            "product_options": _rows(product_options),
            "target_options": [_iso(month) for month in target_options],
        }

    def _build_payload(
        self,
        request: dict[str, Any],
        options: dict[str, Any],
        view: DashboardView,
        product_detail: dict[str, Any] | None,
    ) -> dict[str, Any]:
        summary = (
            _json_value(view.population_summary.head(1).to_dicts()[0])
            if view.population_summary.height
            else {}
        )
        metrics = _json_value(view.metrics.as_dict())
        comparison = self._comparison_payload(view)
        quality = self._quality_payload(view)
        revision_frame = view.revision_scatter
        if "source" in revision_frame.columns:
            revision_frame = revision_frame.filter(
                pl.col("source") == request["source"]
            )
        diagnostics_frame = view.revision_diagnostics
        if "source" in diagnostics_frame.columns:
            diagnostics_frame = diagnostics_frame.filter(
                pl.col("source") == request["source"]
            )
        empty = summary.get("forecast_rows", 0) == 0
        zero_denominator = metrics.get("accuracy_denominator_actual_kl") == 0
        blocked = bool(comparison and comparison["blocked"])
        return {
            "meta": self._meta_payload(),
            "request": request,
            "options": self._options_payload(options),
            "state": {
                "empty": empty,
                "comparison_blocked": blocked,
                "zero_denominator": zero_denominator,
                "message": (
                    "No forecast rows match the active filters."
                    if empty
                    else comparison.get("warning")
                    if blocked and comparison
                    else "Selected actual-volume denominator is zero; ratio metrics are undefined."
                    if zero_denominator
                    else None
                ),
            },
            "population_summary": summary,
            "metrics": metrics,
            "volume_distributions": _volume_distributions(view, request["source"]),
            "monthly_performance": _frame_payload(view.monthly_performance, limit=60),
            "accuracy_vintages": _accuracy_vintages(
                view,
                request["source"],
                request["accuracy_vintage_ids"],
                cast(list[int], options["horizons"]),
                request["revision_tolerance_kl"],
            ),
            "monthly_audit": _frame_payload(view.monthly_audit, limit=60),
            "horizon_performance": _frame_payload(view.horizon_performance, limit=30),
            "horizon_audit": _frame_payload(view.horizon_audit, limit=30),
            "brand_target_month_performance": _frame_payload(
                view.brand_target_month_performance, limit=500
            ),
            "revision_diagnostics": _frame_payload(diagnostics_frame),
            "revision_history": _revision_history_payload(
                view,
                request["source"],
            ),
            "revision_scatter": _frame_payload(revision_frame, limit=2_000),
            "revision_actions": _revision_action_payload(
                view.download_frame,
                request["source"],
                request["revision_tolerance_kl"],
            ),
            "revision_drilldown": _revision_drilldown_payload(
                view.download_frame,
                request["source"],
            ),
            "exceptions": _frame_payload(view.download_frame, limit=80),
            "comparison": comparison,
            "product_detail": product_detail,
            "quality": quality,
        }

    @staticmethod
    def _options_payload(options: dict[str, Any]) -> dict[str, Any]:
        return {
            "target_months": [_iso(value) for value in options["target_months"]],
            "latest_completed_target_month": (
                _iso(value)
                if (value := options["latest_completed_target_month"])
                else None
            ),
            "brands": options["brands"],
            "sku_classes": options["sku_classes"],
            "parent_products": options["parent_products"],
            "product_availability": options["product_availability"],
            "horizons": options["horizons"],
            "common_horizons": options["common_horizons"],
            "default_comparison_horizon": options["default_comparison_horizon"],
            "calculation_months": [
                _iso(value) for value in options["calculation_months"]
            ],
        }

    @staticmethod
    def _comparison_payload(view: DashboardView) -> dict[str, Any] | None:
        comparison = view.comparison
        if comparison is None:
            return None
        return {
            "selected_horizon": comparison.selected_horizon,
            "common_horizons": list(comparison.common_horizons),
            "alignment_rule": comparison.alignment_rule,
            "blocked": comparison.blocked,
            "ready": comparison.ready,
            "warning": comparison.warning,
            "coverage_warning": comparison.coverage_warning,
            "comparable_pairs": comparison.comparable_pairs,
            "tm_metrics": _json_value(comparison.tm_metrics.as_dict()),
            "ml_metrics": _json_value(comparison.ml_metrics.as_dict()),
            "common_metrics": _json_value(comparison.common_metrics.as_dict()),
            "deltas": _frame_payload(comparison.deltas),
            "population_summary": _frame_payload(comparison.population_summary),
            "winner_counts": _frame_payload(comparison.winner_counts),
            "paired_comparison": _frame_payload(
                comparison.paired_comparison, limit=240
            ),
        }

    @staticmethod
    def _quality_payload(view: DashboardView) -> dict[str, Any]:
        quality = view.quality
        categories: dict[str, Any] = {}
        attention_categories = 0
        for category in QUALITY_CATEGORIES:
            counts = getattr(quality, category)
            exceptions = quality.exceptions.get(category, pl.DataFrame())
            category_has_attention = (
                counts.filter(
                    (pl.col("severity") != "info") & (pl.col("observations") > 0)
                ).height
                > 0
            )
            if category_has_attention:
                attention_categories += 1
            categories[category] = {
                "counts": _frame_payload(counts),
                "exceptions": _frame_payload(exceptions, limit=12),
                "explanation": quality.explanation_text(category),
                "has_attention": category_has_attention,
            }
        return {
            "blocking_errors": list(quality.blocking_errors),
            "attention_categories": attention_categories,
            "categories": categories,
            "baseline_counts": _frame_payload(quality.baseline_counts),
            "scope_exclusion_counts": _frame_payload(
                quality.scope_exclusion_counts
            ),
        }
