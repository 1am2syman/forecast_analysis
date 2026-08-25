"""Product-level forecast-vintage history, revisions, and stability."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
import math

import polars as pl

from ._utils import require_columns
from .contracts import (
    ANALYSIS_COLUMNS,
    DEFAULT_REVISION_TOLERANCE_KL,
    FORECAST_SOURCES,
    REVISION_CLASSIFICATION_DECIMAL_PLACES,
    normalize_revision_tolerance,
)

PRODUCT_SEARCH_COLUMNS = ["parent_code", "parent_description", "display_label"]
PRODUCT_SEARCH_SCHEMA = {
    "parent_code": pl.Int64,
    "parent_description": pl.String,
    "display_label": pl.String,
}

PRODUCT_POINT_COLUMNS = [
    "source",
    "parent_code",
    "parent_description",
    "hierarchy_description",
    "brand",
    "mapping_status",
    "snop_month",
    "calculation_month",
    "forecast_horizon_months",
    "forecast_kl",
    "actual_kl",
    "actual_status",
    "error_kl",
    "bias_pct",
]
PRODUCT_POINT_SCHEMA = {
    "source": pl.String,
    "parent_code": pl.Int64,
    "parent_description": pl.String,
    "hierarchy_description": pl.String,
    "brand": pl.String,
    "mapping_status": pl.String,
    "snop_month": pl.Date,
    "calculation_month": pl.Date,
    "forecast_horizon_months": pl.Int64,
    "forecast_kl": pl.Float64,
    "actual_kl": pl.Float64,
    "actual_status": pl.String,
    "error_kl": pl.Float64,
    "bias_pct": pl.Float64,
}

PRODUCT_REVISION_COLUMNS = [
    "source",
    "parent_code",
    "snop_month",
    "previous_calculation_month",
    "calculation_month",
    "previous_horizon_months",
    "forecast_horizon_months",
    "previous_forecast_kl",
    "forecast_kl",
    "previous_actual_kl",
    "actual_kl",
    "previous_error_kl",
    "error_kl",
    "revision_kl",
    "revision_direction",
    "error_improvement_kl",
    "revision_outcome",
]
PRODUCT_REVISION_SCHEMA = {
    "source": pl.String,
    "parent_code": pl.Int64,
    "snop_month": pl.Date,
    "previous_calculation_month": pl.Date,
    "calculation_month": pl.Date,
    "previous_horizon_months": pl.Int64,
    "forecast_horizon_months": pl.Int64,
    "previous_forecast_kl": pl.Float64,
    "forecast_kl": pl.Float64,
    "previous_actual_kl": pl.Float64,
    "actual_kl": pl.Float64,
    "previous_error_kl": pl.Float64,
    "error_kl": pl.Float64,
    "revision_kl": pl.Float64,
    "revision_direction": pl.String,
    "error_improvement_kl": pl.Float64,
    "revision_outcome": pl.String,
}

PRODUCT_STABILITY_COLUMNS = [
    "source",
    "parent_code",
    "snop_month",
    "vintage_count",
    "forecast_range_kl",
    "population_std_dev_kl",
    "forecast_volatility_kl",
    "revision_count",
    "maximum_absolute_revision_kl",
    "history_status",
    "history_message",
]
PRODUCT_STABILITY_SCHEMA = {
    "source": pl.String,
    "parent_code": pl.Int64,
    "snop_month": pl.Date,
    "vintage_count": pl.Int64,
    "forecast_range_kl": pl.Float64,
    "population_std_dev_kl": pl.Float64,
    "forecast_volatility_kl": pl.Float64,
    "revision_count": pl.Int64,
    "maximum_absolute_revision_kl": pl.Float64,
    "history_status": pl.String,
    "history_message": pl.String,
}

_HISTORY_STATUSES = ("ready", "partial_history", "insufficient_history", "no_history")


@dataclass(frozen=True)
class ProductHistoryView:
    """One product-target history projection for the selected source scope.

    ``points`` is chronological within each source. ``revisions`` contains
    only consecutive available vintages within one source; it does not infer
    missing calendar months. ``stability`` always has one row per requested
    source so missing or one-vintage histories remain explicit.
    """

    parent_code: int
    target_month: date
    sources: tuple[str, ...]
    parent_description: str | None
    hierarchy_description: str | None
    brand: str | None
    mapping_status: str | None
    actual_kl: float | None
    actual_status: str | None
    status: str
    status_message: str
    points: pl.DataFrame
    revisions: pl.DataFrame
    stability: pl.DataFrame

    @property
    def actual_reference(self) -> pl.DataFrame:
        """Return the target-month actual reference used by the history chart."""
        if self.points.height == 0:
            return pl.DataFrame(
                schema={
                    "snop_month": pl.Date,
                    "actual_kl": pl.Float64,
                    "actual_status": pl.String,
                }
            )
        return (
            self.points.select(["snop_month", "actual_kl", "actual_status"])
            .unique()
            .sort("snop_month")
        )


def _empty_frame(schema: dict[str, pl.DataType], columns: list[str]) -> pl.DataFrame:
    return pl.DataFrame(schema=schema).select(columns)


def _normalize_month(value: object) -> date:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return date(value.year, value.month, 1)
    if isinstance(value, str):
        text = value.strip()
        for fmt in ("%Y-%m", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt).date()
                return date(parsed.year, parsed.month, 1)
            except ValueError:
                continue
    raise ValueError(f"target month must be a date or YYYY-MM value, got {value!r}")


def _normalize_sources(
    frame: pl.DataFrame,
    sources: Iterable[str] | None,
) -> tuple[str, ...]:
    if sources is None:
        values = sorted(str(value).strip().lower() for value in frame["source"].unique())
    else:
        values = list(dict.fromkeys(str(value).strip().lower() for value in sources))
    unknown = sorted(set(values).difference(FORECAST_SOURCES))
    if unknown:
        raise ValueError(
            f"unsupported product-history source(s) {unknown}; "
            f"choose from {sorted(FORECAST_SOURCES)}"
        )
    return tuple(values)


def search_parent_products(
    frame: pl.DataFrame,
    query: str = "",
    *,
    sources: Iterable[str] | None = None,
    source: str | None = None,
    target_month: object | None = None,
) -> pl.DataFrame:
    """Find parent products by code or description within an optional scope."""
    require_columns(frame, ANALYSIS_COLUMNS, "analysis population")
    if source is not None:
        if sources is not None:
            raise ValueError("provide either source or sources, not both")
        sources = (source,)
    selected_sources = _normalize_sources(frame, sources)
    candidates = frame.filter(pl.col("source").is_in(selected_sources))
    if target_month is not None:
        candidates = candidates.filter(
            pl.col("snop_month") == _normalize_month(target_month)
        )
    if candidates.height == 0:
        return _empty_frame(PRODUCT_SEARCH_SCHEMA, PRODUCT_SEARCH_COLUMNS)

    products = (
        candidates.select(["parent_code", "parent_description"])
        .sort(["parent_code", "parent_description"])
        .unique(subset=["parent_code"], maintain_order=True)
    )
    needle = str(query).strip().casefold()
    rows: list[dict[str, object]] = []
    for row in products.iter_rows(named=True):
        parent_code = _coerce_int(row["parent_code"], "parent_code")
        description = str(row["parent_description"])
        if needle and needle not in str(parent_code).casefold() and needle not in description.casefold():
            continue
        rows.append(
            {
                "parent_code": parent_code,
                "parent_description": description,
                "display_label": f"{parent_code} — {description}",
            }
        )
    return pl.DataFrame(rows, schema=PRODUCT_SEARCH_SCHEMA).select(PRODUCT_SEARCH_COLUMNS)


def _empty_points() -> pl.DataFrame:
    return _empty_frame(PRODUCT_POINT_SCHEMA, PRODUCT_POINT_COLUMNS)


def _empty_revisions() -> pl.DataFrame:
    return _empty_frame(PRODUCT_REVISION_SCHEMA, PRODUCT_REVISION_COLUMNS)


def _empty_stability() -> pl.DataFrame:
    return _empty_frame(PRODUCT_STABILITY_SCHEMA, PRODUCT_STABILITY_COLUMNS)


def _coerce_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"{field_name} must be an integer; got {value!r}")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{field_name} must be an integer; got {value!r}")
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field_name} must be an integer; got {value!r}") from exc


def _coerce_float(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"{field_name} must be numeric; got {value!r}")
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field_name} must be numeric; got {value!r}") from exc


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return _coerce_float(value, "numeric value")


def _classify_delta(
    value: float | None,
    tolerance: float,
    positive: str,
    negative: str,
    neutral: str,
) -> str | None:
    if value is None:
        return None
    rounded_value = round(value, REVISION_CLASSIFICATION_DECIMAL_PLACES)
    rounded_tolerance = round(tolerance, REVISION_CLASSIFICATION_DECIMAL_PLACES)
    if rounded_value > rounded_tolerance:
        return positive
    if rounded_value < -rounded_tolerance:
        return negative
    return neutral


def _build_points(
    selected: pl.DataFrame,
) -> pl.DataFrame:
    return (
        selected.with_columns(
            pl.when(pl.col("actual_kl").is_null())
            .then(pl.lit("missing"))
            .when(pl.col("actual_kl") == 0)
            .then(pl.lit("matched_zero"))
            .otherwise(pl.lit("matched_positive"))
            .alias("actual_status"),
            (pl.col("forecast_kl") - pl.col("actual_kl")).alias("error_kl"),
        )
        .with_columns(
            pl.when(pl.col("actual_kl") > 0)
            .then(pl.col("error_kl") / pl.col("actual_kl") * 100)
            .otherwise(pl.lit(None, dtype=pl.Float64))
            .alias("bias_pct")
        )
        .select(PRODUCT_POINT_COLUMNS)
        .sort(["source", "calculation_month", "forecast_horizon_months"])
    )


def _build_consecutive_revisions(
    points: pl.DataFrame,
    source: str,
    tolerance: float,
) -> pl.DataFrame:
    source_points = points.filter(pl.col("source") == source).sort(
        ["calculation_month", "forecast_horizon_months"]
    )
    rows = list(source_points.iter_rows(named=True))
    if len(rows) < 2:
        return _empty_revisions()

    revisions: list[dict[str, object]] = []
    for previous, current in zip(rows, rows[1:]):
        previous_forecast = _coerce_float(previous["forecast_kl"], "forecast_kl")
        current_forecast = _coerce_float(current["forecast_kl"], "forecast_kl")
        revision = current_forecast - previous_forecast
        previous_error = _optional_float(previous["error_kl"])
        current_error = _optional_float(current["error_kl"])
        error_improvement = (
            abs(previous_error) - abs(current_error)
            if previous_error is not None and current_error is not None
            else None
        )
        revisions.append(
            {
                "source": source,
                "parent_code": _coerce_int(current["parent_code"], "parent_code"),
                "snop_month": current["snop_month"],
                "previous_calculation_month": previous["calculation_month"],
                "calculation_month": current["calculation_month"],
                "previous_horizon_months": _coerce_int(
                    previous["forecast_horizon_months"], "forecast_horizon_months"
                ),
                "forecast_horizon_months": _coerce_int(
                    current["forecast_horizon_months"], "forecast_horizon_months"
                ),
                "previous_forecast_kl": previous_forecast,
                "forecast_kl": current_forecast,
                "previous_actual_kl": _optional_float(previous["actual_kl"]),
                "actual_kl": _optional_float(current["actual_kl"]),
                "previous_error_kl": previous_error,
                "error_kl": current_error,
                "revision_kl": revision,
                "revision_direction": _classify_delta(
                    revision,
                    tolerance,
                    "up",
                    "down",
                    "unchanged",
                ),
                "error_improvement_kl": error_improvement,
                "revision_outcome": _classify_delta(
                    error_improvement,
                    tolerance,
                    "improved",
                    "worsened",
                    "neutral",
                ),
            }
        )
    return pl.DataFrame(revisions, schema=PRODUCT_REVISION_SCHEMA).select(
        PRODUCT_REVISION_COLUMNS
    )


def _stability_row(
    points: pl.DataFrame,
    source: str,
    parent_code: int,
    target_month: date,
    tolerance: float,
) -> dict[str, object]:
    source_points = points.filter(pl.col("source") == source).sort(
        ["calculation_month", "forecast_horizon_months"]
    )
    forecasts = [
        _coerce_float(value, "forecast_kl")
        for value in source_points["forecast_kl"].to_list()
    ]
    vintage_count = len(forecasts)
    if vintage_count < 2:
        if vintage_count == 0:
            message = f"No {source.upper()} vintage is available for this product-target month."
            status = "no_history"
        else:
            message = (
                f"Insufficient {source.upper()} history: only one vintage is available; "
                "at least two are required for stability metrics."
            )
            status = "insufficient_history"
        return {
            "source": source,
            "parent_code": parent_code,
            "snop_month": target_month,
            "vintage_count": vintage_count,
            "forecast_range_kl": None,
            "population_std_dev_kl": None,
            "forecast_volatility_kl": None,
            "revision_count": None,
            "maximum_absolute_revision_kl": None,
            "history_status": status,
            "history_message": message,
        }

    mean = sum(forecasts) / vintage_count
    population_std_dev = math.sqrt(
        sum((forecast - mean) ** 2 for forecast in forecasts) / vintage_count
    )
    revisions = [current - previous for previous, current in zip(forecasts, forecasts[1:])]
    materially_revised = sum(
        abs(round(revision, REVISION_CLASSIFICATION_DECIMAL_PLACES))
        > round(tolerance, REVISION_CLASSIFICATION_DECIMAL_PLACES)
        for revision in revisions
    )
    return {
        "source": source,
        "parent_code": parent_code,
        "snop_month": target_month,
        "vintage_count": vintage_count,
        "forecast_range_kl": max(forecasts) - min(forecasts),
        "population_std_dev_kl": population_std_dev,
        "forecast_volatility_kl": population_std_dev,
        "revision_count": materially_revised,
        "maximum_absolute_revision_kl": max(abs(revision) for revision in revisions),
        "history_status": "ready",
        "history_message": (
            f"{source.upper()} has {vintage_count} chronological vintages; "
            "stability metrics use all available history."
        ),
    }


def _overall_status(stability: pl.DataFrame, points: pl.DataFrame) -> tuple[str, str]:
    if points.height == 0:
        return "no_history", "No forecast vintages are available for this product-target selection."
    statuses = stability["history_status"].to_list()
    if all(status == "ready" for status in statuses):
        return "ready", "Each selected source has at least two available vintages."
    if any(status == "ready" for status in statuses):
        return "partial_history", "Some selected sources have insufficient vintage history."
    return "insufficient_history", "At least two vintages are required for source stability metrics."


def build_product_history(
    frame: pl.DataFrame,
    parent_code: int,
    target_month: object,
    *,
    sources: Iterable[str] | None = None,
    source: str | None = None,
    revision_tolerance_kl: float = DEFAULT_REVISION_TOLERANCE_KL,
) -> ProductHistoryView:
    """Build an auditable chronological history for one product-target month."""
    require_columns(frame, ANALYSIS_COLUMNS, "analysis population")
    if isinstance(parent_code, bool):
        raise ValueError("parent_code must be an integer")
    try:
        normalized_parent_code = int(parent_code)
    except (TypeError, ValueError) as exc:
        raise ValueError("parent_code must be an integer") from exc
    normalized_target_month = _normalize_month(target_month)
    if source is not None:
        if sources is not None:
            raise ValueError("provide either source or sources, not both")
        sources = (source,)
    normalized_sources = _normalize_sources(frame, sources)
    tolerance = normalize_revision_tolerance(revision_tolerance_kl)

    selected = frame.filter(
        (pl.col("parent_code") == normalized_parent_code)
        & (pl.col("snop_month") == normalized_target_month)
        & pl.col("source").is_in(normalized_sources)
    )
    points = _build_points(selected) if selected.height else _empty_points()

    metadata = (
        points.sort(["source", "calculation_month"]).row(0, named=True)
        if points.height
        else {}
    )
    actual_values = points.get_column("actual_kl").drop_nulls() if points.height else []
    actual_kl = (
        _coerce_float(actual_values[0], "actual_kl") if len(actual_values) else None
    )
    actual_status_values = points.get_column("actual_status").drop_nulls() if points.height else []
    actual_status = str(actual_status_values[0]) if len(actual_status_values) else None

    revision_tables = [
        _build_consecutive_revisions(points, source, tolerance)
        for source in normalized_sources
    ]
    revisions = (
        pl.concat(revision_tables, how="vertical")
        if any(table.height for table in revision_tables)
        else _empty_revisions()
    )
    if revisions.height:
        revisions = revisions.sort(["source", "previous_calculation_month"])

    stability_rows = [
        _stability_row(
            points,
            source,
            normalized_parent_code,
            normalized_target_month,
            tolerance,
        )
        for source in normalized_sources
    ]
    stability = (
        pl.DataFrame(stability_rows, schema=PRODUCT_STABILITY_SCHEMA).select(
            PRODUCT_STABILITY_COLUMNS
        )
        if stability_rows
        else _empty_stability()
    )
    status, status_message = _overall_status(stability, points)
    if status not in _HISTORY_STATUSES:
        raise AssertionError(f"unsupported product history status {status!r}")

    return ProductHistoryView(
        parent_code=normalized_parent_code,
        target_month=normalized_target_month,
        sources=normalized_sources,
        parent_description=str(metadata["parent_description"]) if metadata else None,
        hierarchy_description=(
            str(metadata["hierarchy_description"])
            if metadata and metadata["hierarchy_description"] is not None
            else None
        ),
        brand=(str(metadata["brand"]) if metadata and metadata["brand"] is not None else None),
        mapping_status=(
            str(metadata["mapping_status"])
            if metadata and metadata["mapping_status"] is not None
            else None
        ),
        actual_kl=actual_kl,
        actual_status=actual_status,
        status=status,
        status_message=status_message,
        points=points,
        revisions=revisions,
        stability=stability,
    )


__all__ = [
    "PRODUCT_POINT_COLUMNS",
    "PRODUCT_REVISION_COLUMNS",
    "PRODUCT_SEARCH_COLUMNS",
    "PRODUCT_STABILITY_COLUMNS",
    "ProductHistoryView",
    "build_product_history",
    "search_parent_products",
]
