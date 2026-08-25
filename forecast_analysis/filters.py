"""Shared population filters for the source-aware dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import math
from typing import Iterable

import polars as pl

from ._utils import require_columns
from .contracts import (
    ACTUAL_COLUMNS,
    ANALYSIS_COLUMNS,
    FORECAST_SOURCES,
    DEFAULT_REVISION_TOLERANCE_KL,
    REVISION_DIRECTIONS,
    REVISION_OUTCOMES,
    normalize_revision_tolerance,
)

SOURCE_OPTIONS = {"TM": "tm", "ML": "ml"}
QUALITY_BRAND_LABELS = {
    "unmapped": "Unmapped",
    "conflict": "Hierarchy conflict",
}


def _normalize_revision_choices(
    values: tuple[str, ...] | None,
    allowed: tuple[str, ...],
    field_name: str,
) -> tuple[str, ...] | None:
    if values is None:
        return None
    normalized = tuple(str(value).strip().lower() for value in values)
    unknown = sorted(set(normalized).difference(allowed))
    if unknown:
        raise ValueError(
            f"{field_name} contains unsupported values {unknown}; "
            f"choose from {list(allowed)}"
        )
    return normalized


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


def _display_brand_expression() -> pl.Expr:
    return (
        pl.when(pl.col("mapping_status") == "conflict")
        .then(pl.lit(QUALITY_BRAND_LABELS["conflict"]))
        .when(pl.col("brand").is_null())
        .then(pl.lit(QUALITY_BRAND_LABELS["unmapped"]))
        .otherwise(pl.col("brand"))
        .alias("brand_display")
    )


def with_display_brand(frame: pl.DataFrame) -> pl.DataFrame:
    """Add the stable dashboard label used for mapped and quality-only brands."""
    require_columns(frame, ["brand", "mapping_status"], "analysis population")
    return frame.with_columns(_display_brand_expression())


@dataclass(frozen=True)
class DashboardFilters:
    """The one filter state shared by every dashboard output.

    Revision direction is classified from ``revision_kl`` and revision outcome
    from ``error_improvement_kl``. Both use the same configurable absolute KL
    tolerance; unchanged revisions and neutral outcomes are not materially
    revised for revision-effectiveness denominators.
    """

    source: str = "tm"
    target_months: tuple[date, ...] | None = None
    brands: tuple[str, ...] | None = None
    parent_codes: tuple[int, ...] | None = None
    minimum_actual_volume: float = 0.0
    horizons: tuple[int, ...] | None = None
    revision_directions: tuple[str, ...] | None = None
    revision_outcomes: tuple[str, ...] | None = None
    revision_tolerance_kl: float = DEFAULT_REVISION_TOLERANCE_KL

    def __post_init__(self) -> None:
        source = str(self.source).strip().lower()
        if source not in FORECAST_SOURCES:
            raise ValueError(
                f"unsupported dashboard source {self.source!r}; "
                f"choose one of {sorted(FORECAST_SOURCES)}"
            )
        object.__setattr__(self, "source", source)

        if self.target_months is not None:
            object.__setattr__(
                self,
                "target_months",
                tuple(_normalize_month(value) for value in self.target_months),
            )
        if self.brands is not None:
            object.__setattr__(
                self,
                "brands",
                tuple(str(value) for value in self.brands),
            )
        if self.parent_codes is not None:
            try:
                parent_codes = tuple(int(value) for value in self.parent_codes)
            except (TypeError, ValueError) as exc:
                raise ValueError("parent_codes must contain integers") from exc
            object.__setattr__(self, "parent_codes", parent_codes)
        if self.horizons is not None:
            normalized_horizons: list[int] = []
            for value in self.horizons:
                if isinstance(value, bool):
                    raise ValueError("horizons must contain non-negative integers")
                try:
                    horizon = int(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        "horizons must contain non-negative integers"
                    ) from exc
                if isinstance(value, float) and not value.is_integer():
                    raise ValueError("horizons must contain non-negative integers")
                if horizon < 0:
                    raise ValueError("horizons must contain non-negative integers")
                normalized_horizons.append(horizon)
            object.__setattr__(self, "horizons", tuple(normalized_horizons))

        object.__setattr__(
            self,
            "revision_directions",
            _normalize_revision_choices(
                self.revision_directions,
                REVISION_DIRECTIONS,
                "revision_directions",
            ),
        )
        object.__setattr__(
            self,
            "revision_outcomes",
            _normalize_revision_choices(
                self.revision_outcomes,
                REVISION_OUTCOMES,
                "revision_outcomes",
            ),
        )
        object.__setattr__(
            self,
            "revision_tolerance_kl",
            normalize_revision_tolerance(self.revision_tolerance_kl),
        )

        try:
            minimum = float(self.minimum_actual_volume)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "minimum_actual_volume must be a finite non-negative number"
            ) from exc
        if not math.isfinite(minimum) or minimum < 0:
            raise ValueError("minimum_actual_volume must be a finite non-negative number")
        object.__setattr__(self, "minimum_actual_volume", minimum)


def apply_dashboard_filters(
    frame: pl.DataFrame, filters: DashboardFilters
) -> pl.DataFrame:
    """Filter the canonical long population once for all dashboard consumers.

    Source isolation is the first operation and is repeated defensively here,
    rather than relying on callers to pre-filter a mixed TM/ML frame.  A zero
    minimum-volume filter keeps missing actual rows visible for coverage; a
    positive threshold selects only rows with an actual at or above it.
    """
    require_columns(frame, ANALYSIS_COLUMNS, "analysis population")
    filtered = with_display_brand(frame).filter(pl.col("source") == filters.source)

    if filters.target_months is not None:
        filtered = filtered.filter(pl.col("snop_month").is_in(filters.target_months))
    if filters.brands is not None:
        filtered = filtered.filter(pl.col("brand_display").is_in(filters.brands))
    if filters.horizons is not None:
        filtered = filtered.filter(
            pl.col("forecast_horizon_months").is_in(filters.horizons)
        )
    if filters.parent_codes is not None:
        filtered = filtered.filter(pl.col("parent_code").is_in(filters.parent_codes))
    if filters.minimum_actual_volume > 0:
        filtered = filtered.filter(
            pl.col("actual_kl").is_not_null()
            & (pl.col("actual_kl") >= filters.minimum_actual_volume)
        )

    return filtered.sort(
        ["parent_code", "snop_month", "calculation_month", "source"]
    )


def apply_revision_filters(
    pair_frame: pl.DataFrame, filters: DashboardFilters
) -> pl.DataFrame:
    """Apply pair-only direction and outcome filters without hiding coverage pairs."""
    require_columns(
        pair_frame,
        ["revision_direction", "revision_outcome"],
        "vintage pair population",
    )
    filtered = pair_frame
    if filters.revision_directions is not None:
        filtered = filtered.filter(
            pl.col("revision_direction").is_in(filters.revision_directions)
        )
    if filters.revision_outcomes is not None:
        filtered = filtered.filter(
            pl.col("revision_outcome").is_in(filters.revision_outcomes)
        )
    return filtered


def apply_actual_filters(
    frame: pl.DataFrame, filters: DashboardFilters
) -> pl.DataFrame:
    """Apply shared filters that have meaning on the actual population.

    Actuals have no forecast horizon, so the horizon filter is intentionally
    omitted here. Keeping the full selected actual denominator makes product-
    target combinations absent at an exact horizon visible as uncovered volume.
    """
    require_columns(frame, ACTUAL_COLUMNS, "selected actual population")
    prepared = frame
    if "brand" not in prepared.columns:
        prepared = prepared.with_columns(pl.lit(None, dtype=pl.String).alias("brand"))
    if "mapping_status" not in prepared.columns:
        prepared = prepared.with_columns(pl.lit("unmapped").alias("mapping_status"))
    if "mapping_diagnostic" not in prepared.columns:
        prepared = prepared.with_columns(
            pl.lit("no hierarchy mapping").alias("mapping_diagnostic")
        )
    filtered = with_display_brand(prepared)

    if filters.target_months is not None:
        filtered = filtered.filter(pl.col("snop_month").is_in(filters.target_months))
    if filters.brands is not None:
        filtered = filtered.filter(pl.col("brand_display").is_in(filters.brands))
    if filters.parent_codes is not None:
        filtered = filtered.filter(pl.col("parent_code").is_in(filters.parent_codes))
    if filters.minimum_actual_volume > 0:
        filtered = filtered.filter(pl.col("actual_kl") >= filters.minimum_actual_volume)

    return filtered.sort(["parent_code", "snop_month"])


def available_filter_values(frame: pl.DataFrame, source: str) -> dict[str, object]:
    """Return source-scoped control values for the Marimo filter bar."""
    require_columns(frame, ANALYSIS_COLUMNS, "analysis population")
    normalized_source = str(source).strip().lower()
    if normalized_source not in FORECAST_SOURCES:
        raise ValueError(f"unsupported dashboard source {source!r}")
    source_frame = with_display_brand(frame).filter(pl.col("source") == normalized_source)
    parent_options = (
        source_frame.select(["parent_code", "parent_description"])
        .unique()
        .sort(["parent_code", "parent_description"])
        .to_dicts()
    )
    return {
        "target_months": sorted(source_frame["snop_month"].unique().to_list()),
        "brands": sorted(source_frame["brand_display"].drop_nulls().unique().to_list()),
        "parent_products": parent_options,
        "horizons": sorted(
            source_frame["forecast_horizon_months"].unique().to_list(),
            reverse=True,
        ),
        "calculation_months": sorted(
            source_frame["calculation_month"].unique().to_list()
        ),
    }


def normalize_filter_months(values: Iterable[object]) -> tuple[date, ...]:
    """Normalize UI month values while keeping the public filter constructor small."""
    return tuple(_normalize_month(value) for value in values)
