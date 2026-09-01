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
    VintageRule,
    available_filter_values,
    build_analysis_dataset,
    build_dashboard_view,
    build_product_detail,
    load_analysis_inputs,
    with_display_brand,
)
from forecast_analysis.dashboard import DashboardView
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
        pl.col("revision_kl").is_not_null()
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


def _revision_history_payload(
    view: DashboardView,
    source: str,
    *,
    month_limit: int = 6,
) -> dict[str, Any]:
    """Build fixed-cohort forecast paths through the latest actual month.

    Each target month is independent. Its oldest aggregate forecast is indexed
    to zero, and later vintages show percentage movement from that baseline.
    Only products present in every displayed vintage for that target month are
    retained, so path movement reflects forecast revisions rather than changing
    product coverage. Future forecast-only months are excluded by anchoring the
    six-month window to the latest selected actual month.
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
    target_months = sorted(frame.get_column("snop_month").unique().to_list())[
        -month_limit:
    ]
    months: list[dict[str, Any]] = []
    for target_month in target_months:
        target_frame = frame.filter(pl.col("snop_month") == target_month)
        calculation_months = sorted(
            target_frame.get_column("calculation_month").unique().to_list()
        )
        vintage_count = len(calculation_months)
        if vintage_count == 0:
            continue
        common_products = (
            target_frame.group_by("parent_code")
            .agg(pl.col("calculation_month").n_unique().alias("vintage_count"))
            .filter(pl.col("vintage_count") == vintage_count)
            .select("parent_code")
        )
        if common_products.height == 0:
            continue
        history = (
            target_frame.join(common_products, on="parent_code", how="semi")
            .group_by("calculation_month")
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
        latest = points[-1]
        months.append(
            {
                "snop_month": _iso(target_month),
                "vintage_count": history.height,
                "product_count": common_products.height,
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
    return {
        "source": source,
        "month_limit": month_limit,
        "baseline": "oldest_available",
        "latest_actual_month": _iso(latest_actual_month),
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
    ) -> None:
        if cache_size < 1:
            raise ValueError("cache_size must be positive")
        self.dataset = dataset
        self.refresh_timestamp = refresh_timestamp
        self.source_label = source_label
        self.cache_size = cache_size
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
        return {
            "source": "ml",
            "comparison_mode": False,
            "target_start": _iso(months[0]) if months else None,
            "target_end": _iso(months[-1]) if months else None,
            "brand": None,
            "sku_class": None,
            "parent_code": None,
            "horizon": None,
            "minimum_actual_volume": 0.0,
            "vintage_a": {"kind": "oldest_available", "value": None},
            "vintage_b": {"kind": "latest_available", "value": None},
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
        request, _, _, _, _ = self._normalize_request(raw_request)
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
        request, _, _, _, _ = self._normalize_request(raw_request)
        base_request = dict(request)
        base_request["product_parent_code"] = None
        base_request["product_target_month"] = None
        base_view = self._computed(base_request).view
        return self._build_product_payload(base_view, request)

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
        request, options, filters, vintage_a, vintage_b = self._normalize_request(
            raw_request
        )
        key = json.dumps(request, sort_keys=True, separators=(",", ":"))
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                return cached
            pending = self._inflight.get(key)
            if pending is None:
                pending = _PendingView(Event())
                self._inflight[key] = pending
                owner = True
            else:
                owner = False
        if not owner:
            pending.ready.wait()
            if pending.error is not None:
                raise pending.error
            if pending.result is None:
                raise RuntimeError("dashboard computation completed without a result")
            return pending.result

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
        return computed

    def _normalize_request(
        self, raw: dict[str, Any]
    ) -> tuple[
        dict[str, Any],
        dict[str, Any],
        DashboardFilters,
        VintageRule | None,
        VintageRule | None,
    ]:
        source = _parse_string(
            raw, "source", default="ml", allowed={"tm", "ml"}
        ) or "ml"
        comparison_mode = _parse_bool(raw, "comparison_mode")
        options = self._filter_options(source, comparison_mode)

        brand = _parse_string(raw, "brand")
        sku_class = _parse_string(
            raw,
            "sku_class",
            allowed=set(SKU_CLASSES),
        )
        parent_code = _parse_int(raw, "parent_code", minimum=0)
        drilldown_parent_codes = _parse_int_list(
            raw,
            "drilldown_parent_codes",
            minimum=0,
        )
        horizon = _parse_int(raw, "horizon", minimum=0)
        available_horizons = cast(list[int], options["horizons"])
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
            brand=brand,
            sku_class=sku_class,
            parent_codes=(
                (parent_code,)
                if parent_code is not None
                else drilldown_parent_codes or None
            ),
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
        options = {**options, "target_months": available_months}
        target_start = _parse_date(raw.get("target_start"), "target_start")
        target_end = _parse_date(raw.get("target_end"), "target_end")
        if available_months:
            latest_actual_month = available_months[-1]
            if target_start is None:
                target_start = available_months[0]
            elif target_start > latest_actual_month:
                target_start = latest_actual_month
            if target_end is None or target_end > latest_actual_month:
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
            "brand": brand,
            "sku_class": sku_class,
            "parent_code": parent_code,
            "horizon": horizon,
            "minimum_actual_volume": _parse_float(
                raw,
                "minimum_actual_volume",
                default=0.0,
                minimum=0.0,
            ),
            "vintage_a": self._rule_request(vintage_a, "oldest_available"),
            "vintage_b": self._rule_request(vintage_b, "latest_available"),
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
            brands=_single_choice(brand),
            sku_classes=_single_choice(sku_class),
            parent_codes=(
                (parent_code,)
                if parent_code is not None
                else tuple(normalized["drilldown_parent_codes"]) or None
            ),
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
        return normalized, options, filters, vintage_a, vintage_b

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

    def _actual_target_months(
        self,
        options: dict[str, Any],
        *,
        source: str,
        comparison_mode: bool,
        brand: str | None = None,
        sku_class: str | None = None,
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
        if brand is not None:
            actual_frame = actual_frame.filter(pl.col("brand_display") == brand)
        if sku_class is not None:
            actual_frame = actual_frame.filter(pl.col("sku_class") == sku_class)
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
            "state": payload["state"],
            "population_summary": payload["population_summary"],
            "metrics": payload["metrics"],
            "volume_distributions": payload["volume_distributions"],
            "monthly_performance": payload["monthly_performance"],
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
        return {
            "parent_code": detail.parent_code,
            "target_month": _iso(detail.target_month),
            "sources": list(detail.sources),
            "parent_description": detail.parent_description,
            "hierarchy_description": detail.hierarchy_description,
            "brand": detail.brand,
            "mapping_status": detail.mapping_status,
            "actual_kl": detail.actual_kl,
            "actual_status": detail.actual_status,
            "status": detail.status,
            "status_message": detail.status_message,
            "points": _frame_payload(detail.points, limit=120),
            "revisions": _frame_payload(detail.revisions, limit=40),
            "stability": _frame_payload(detail.stability),
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
            "brands": options["brands"],
            "sku_classes": options["sku_classes"],
            "parent_products": options["parent_products"],
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
