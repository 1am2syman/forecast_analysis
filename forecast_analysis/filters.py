"""Shared population filters for the source-aware dashboard."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
import math
from typing import Iterable

import polars as pl

from ._utils import require_columns
from .contracts import (
    ACTUAL_COLUMNS,
    ANALYSIS_COLUMNS,
    FORECAST_SOURCES,
    ACTUAL_STATUSES,
    DEFAULT_REVISION_TOLERANCE_KL,
    FORECAST_DIRECTIONS,
    HIERARCHY_STATUSES,
    PAIR_STATUSES,
    REVISION_DIRECTIONS,
    REVISION_OUTCOMES,
    SOURCE_AVAILABILITY_STATUSES,
    normalize_revision_tolerance,
)

SOURCE_OPTIONS = {"TM": "tm", "ML": "ml"}
QUALITY_BRAND_LABELS = {
    "unmapped": "Unmapped",
    "conflict": "Hierarchy conflict",
}
PERFORMANCE_TOP_N_METRICS = (
    "actual_volume",
    "absolute_error",
    "deterioration",
)


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


def _normalize_band(
    value: tuple[float, float] | None,
    field_name: str,
) -> tuple[float, float] | None:
    if value is None:
        return None
    try:
        bounds = tuple(value)
    except TypeError as exc:
        raise ValueError(f"{field_name} must contain exactly two finite bounds") from exc
    if len(bounds) != 2:
        raise ValueError(f"{field_name} must contain exactly two finite bounds")
    try:
        lower, upper = (float(bound) for bound in bounds)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must contain exactly two finite bounds") from exc
    if not math.isfinite(lower) or not math.isfinite(upper) or lower > upper:
        raise ValueError(
            f"{field_name} must contain finite bounds in ascending order"
        )
    return lower, upper


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
    revised for revision-effectiveness denominators. When ``comparison_mode``
    is true, both TM and ML are selected and ``comparison_horizon`` identifies
    the one exact horizon used for the aligned source comparison. Comparison
    mode clears revision direction/outcome filters because it is not a
    Vintage A/B revision analysis. ``zero_forecast_only`` keeps visible
    zero-forecast rows and, for Vintage A/B metrics, keeps pairs whose
    selected Vintage B forecast is zero; vintage selection still uses the
    ordinary active history. ``complete_vintage_history_only``
    keeps a product-target source key only when every horizon in ``horizons``
    is present; when ``horizons`` is omitted, every horizon in the scoped
    population is treated as selected.
    """

    source: str = "tm"
    comparison_mode: bool = False
    comparison_horizon: int | None = None
    target_months: tuple[date, ...] | None = None
    brands: tuple[str, ...] | None = None
    parent_codes: tuple[int, ...] | None = None
    minimum_actual_volume: float = 0.0
    horizons: tuple[int, ...] | None = None
    hierarchy_statuses: tuple[str, ...] | None = None
    actual_statuses: tuple[str, ...] | None = None
    pair_statuses: tuple[str, ...] | None = None
    source_availability: tuple[str, ...] | None = None
    zero_forecast_only: bool = False
    complete_vintage_history_only: bool = False
    revision_directions: tuple[str, ...] | None = None
    revision_outcomes: tuple[str, ...] | None = None
    forecast_directions: tuple[str, ...] | None = None
    forecast_accuracy_band: tuple[float, float] | None = None
    bias_band: tuple[float, float] | None = None
    minimum_absolute_error_kl: float = 0.0
    top_n: int | None = None
    top_n_metric: str = "actual_volume"
    revision_tolerance_kl: float = DEFAULT_REVISION_TOLERANCE_KL

    def __post_init__(self) -> None:
        source = str(self.source).strip().lower()
        if source not in FORECAST_SOURCES:
            raise ValueError(
                f"unsupported dashboard source {self.source!r}; "
                f"choose one of {sorted(FORECAST_SOURCES)}"
            )
        object.__setattr__(self, "source", source)
        if not isinstance(self.comparison_mode, bool):
            raise ValueError("comparison_mode must be a boolean")
        if self.comparison_horizon is not None:
            if isinstance(self.comparison_horizon, bool) or not isinstance(
                self.comparison_horizon, int
            ):
                raise ValueError(
                    "comparison_horizon must be a non-negative integer or None"
                )
            if self.comparison_horizon < 0:
                raise ValueError(
                    "comparison_horizon must be a non-negative integer or None"
                )

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
            "hierarchy_statuses",
            _normalize_revision_choices(
                self.hierarchy_statuses,
                HIERARCHY_STATUSES,
                "hierarchy_statuses",
            ),
        )
        object.__setattr__(
            self,
            "actual_statuses",
            _normalize_revision_choices(
                self.actual_statuses,
                ACTUAL_STATUSES,
                "actual_statuses",
            ),
        )
        object.__setattr__(
            self,
            "pair_statuses",
            _normalize_revision_choices(
                self.pair_statuses,
                PAIR_STATUSES,
                "pair_statuses",
            ),
        )
        object.__setattr__(
            self,
            "source_availability",
            _normalize_revision_choices(
                self.source_availability,
                SOURCE_AVAILABILITY_STATUSES,
                "source_availability",
            ),
        )
        if not isinstance(self.zero_forecast_only, bool):
            raise ValueError("zero_forecast_only must be a boolean")
        if not isinstance(self.complete_vintage_history_only, bool):
            raise ValueError("complete_vintage_history_only must be a boolean")
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
            "forecast_directions",
            _normalize_revision_choices(
                self.forecast_directions,
                FORECAST_DIRECTIONS,
                "forecast_directions",
            ),
        )
        object.__setattr__(
            self,
            "forecast_accuracy_band",
            _normalize_band(self.forecast_accuracy_band, "forecast_accuracy_band"),
        )
        object.__setattr__(
            self,
            "bias_band",
            _normalize_band(self.bias_band, "bias_band"),
        )
        try:
            minimum_absolute_error = float(self.minimum_absolute_error_kl)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "minimum_absolute_error_kl must be a finite non-negative number"
            ) from exc
        if not math.isfinite(minimum_absolute_error) or minimum_absolute_error < 0:
            raise ValueError(
                "minimum_absolute_error_kl must be a finite non-negative number"
            )
        object.__setattr__(self, "minimum_absolute_error_kl", minimum_absolute_error)
        if self.top_n is not None:
            if isinstance(self.top_n, bool) or not isinstance(self.top_n, int):
                raise ValueError("top_n must be a positive integer or None")
            if self.top_n < 1:
                raise ValueError("top_n must be a positive integer or None")
        normalized_top_n_metric = str(self.top_n_metric).strip().lower()
        if normalized_top_n_metric not in PERFORMANCE_TOP_N_METRICS:
            raise ValueError(
                f"top_n_metric must be one of {list(PERFORMANCE_TOP_N_METRICS)}"
            )
        object.__setattr__(self, "top_n_metric", normalized_top_n_metric)
        if self.comparison_mode:
            object.__setattr__(self, "revision_directions", None)
            object.__setattr__(self, "revision_outcomes", None)
            object.__setattr__(self, "forecast_directions", None)
            object.__setattr__(self, "forecast_accuracy_band", None)
            object.__setattr__(self, "bias_band", None)
            object.__setattr__(self, "minimum_absolute_error_kl", 0.0)
            object.__setattr__(self, "top_n", None)
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

    @property
    def selected_sources(self) -> tuple[str, ...]:
        """Return the source scope owned by this filter state."""
        return ("tm", "ml") if self.comparison_mode else (self.source,)

    def without_status_quality_filters(self) -> "DashboardFilters":
        """Return the same selection without categorical quality filters."""
        return replace(
            self,
            hierarchy_statuses=None,
            actual_statuses=None,
            pair_statuses=None,
            source_availability=None,
        )

    def without_quality_filters(self) -> "DashboardFilters":
        """Return the same selection without any data-quality filters."""
        return replace(
            self.without_status_quality_filters(),
            zero_forecast_only=False,
            complete_vintage_history_only=False,
        )

    def without_revision_filters(self) -> "DashboardFilters":
        """Return the same selection without pair revision filters."""
        return replace(self, revision_directions=None, revision_outcomes=None)

    @property
    def has_performance_filters(self) -> bool:
        """Whether any Vintage-B performance filter narrows pair rows."""
        return any(
            (
                self.forecast_directions is not None,
                self.forecast_accuracy_band is not None,
                self.bias_band is not None,
                self.minimum_absolute_error_kl > 0,
                self.top_n is not None,
            )
        )

    def without_performance_filters(self) -> "DashboardFilters":
        """Return the same selection without pair performance filters."""
        return replace(
            self,
            forecast_directions=None,
            forecast_accuracy_band=None,
            bias_band=None,
            minimum_absolute_error_kl=0.0,
            top_n=None,
        )


def _source_availability_keys(frame: pl.DataFrame) -> pl.DataFrame:
    """Return one source-availability status per product-target key."""
    require_columns(
        frame,
        ["source", "parent_code", "snop_month"],
        "source availability population",
    )
    grouped: dict[tuple[int, object], set[str]] = {}
    for row in frame.select(["source", "parent_code", "snop_month"]).unique().iter_rows(named=True):
        grouped.setdefault((row["parent_code"], row["snop_month"]), set()).add(
            str(row["source"])
        )
    rows = []
    for (parent_code, snop_month), sources in grouped.items():
        if sources == {"tm"}:
            status = "tm_only"
        elif sources == {"ml"}:
            status = "ml_only"
        elif sources == {"tm", "ml"}:
            status = "both_sources"
        else:
            continue
        rows.append(
            {
                "parent_code": parent_code,
                "snop_month": snop_month,
                "source_availability": status,
            }
        )
    return pl.DataFrame(
        rows,
        schema={
            "parent_code": pl.Int64,
            "snop_month": pl.Date,
            "source_availability": pl.String,
        },
    )


def _source_scope_statuses(filters: DashboardFilters) -> set[str] | None:
    active_source_statuses = (
        None
        if filters.comparison_mode
        else {"tm_only", "both_sources"}
        if filters.source == "tm"
        else {"ml_only", "both_sources"}
    )
    if filters.source_availability is not None:
        requested = set(filters.source_availability)
        return (
            requested
            if active_source_statuses is None
            else requested.intersection(active_source_statuses)
        )
    return active_source_statuses


def _apply_source_availability(
    frame: pl.DataFrame,
    filters: DashboardFilters,
    availability_frame: pl.DataFrame,
    *,
    preserve_unclassified: bool = False,
) -> pl.DataFrame:
    allowed = _source_scope_statuses(filters)
    if allowed is None:
        return frame
    keys = _source_availability_keys(availability_frame).filter(
        pl.col("source_availability").is_in(sorted(allowed))
    )
    matched = frame.join(keys, on=["parent_code", "snop_month"], how="semi")
    if not preserve_unclassified:
        return matched
    unclassified = frame.join(
        _source_availability_keys(availability_frame),
        on=["parent_code", "snop_month"],
        how="anti",
    )
    return pl.concat([matched, unclassified], how="vertical_relaxed")


def _complete_history_keys(
    frame: pl.DataFrame,
    filters: DashboardFilters,
) -> pl.DataFrame:
    schema = {
        "source": pl.String,
        "parent_code": pl.Int64,
        "snop_month": pl.Date,
    }
    if not filters.complete_vintage_history_only:
        return pl.DataFrame(schema=schema)
    scoped = with_display_brand(frame).filter(
        pl.col("source").is_in(filters.selected_sources)
    )
    if filters.target_months is not None:
        scoped = scoped.filter(pl.col("snop_month").is_in(filters.target_months))
    if filters.brands is not None:
        scoped = scoped.filter(pl.col("brand_display").is_in(filters.brands))
    if filters.parent_codes is not None:
        scoped = scoped.filter(pl.col("parent_code").is_in(filters.parent_codes))
    required_horizons = tuple(
        filters.horizons
        if filters.horizons is not None
        else scoped["forecast_horizon_months"].drop_nulls().unique().to_list()
    )
    if not required_horizons:
        return pl.DataFrame(schema=schema)
    observed: dict[tuple[str, int, object], set[int]] = {}
    for row in scoped.select(
        ["source", "parent_code", "snop_month", "forecast_horizon_months"]
    ).iter_rows(named=True):
        key = (str(row["source"]), row["parent_code"], row["snop_month"])
        observed.setdefault(key, set()).add(row["forecast_horizon_months"])
    rows = [
        {
            "source": source,
            "parent_code": parent_code,
            "snop_month": snop_month,
        }
        for (source, parent_code, snop_month), horizons in observed.items()
        if set(required_horizons).issubset(horizons)
    ]
    return pl.DataFrame(rows, schema=schema)


def apply_dashboard_filters(
    frame: pl.DataFrame,
    filters: DashboardFilters,
    *,
    include_source: bool = True,
    include_horizons: bool = True,
    include_minimum_actual: bool = True,
    availability_frame: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Apply shared selection filters while keeping quality filters explicit.

    ``include_horizons=False`` and ``include_minimum_actual=False`` are used
    for coverage populations. Quality populations keep the active horizon
    selection but remove metric-only quality filters. Source availability is
    computed from the mixed active-horizon frame passed via
    ``availability_frame``. Comparison mode keeps all three statuses; standard
    mode hides opposite-source-only rows and retains only the active source's
    TM-only/ML-only and both-source keys.
    """
    require_columns(frame, ANALYSIS_COLUMNS, "analysis population")
    if availability_frame is None and filters.source_availability is not None:
        availability_population = apply_dashboard_filters(
            frame,
            replace(
                filters,
                comparison_mode=True,
                hierarchy_statuses=None,
                actual_statuses=None,
                pair_statuses=None,
                source_availability=None,
                zero_forecast_only=False,
                complete_vintage_history_only=False,
                revision_directions=None,
                revision_outcomes=None,
                minimum_actual_volume=0,
            ),
            availability_frame=frame,
        )
    else:
        availability_population = availability_frame if availability_frame is not None else frame
    filtered = with_display_brand(frame)
    if include_source:
        filtered = filtered.filter(pl.col("source").is_in(filters.selected_sources))

    if filters.target_months is not None:
        filtered = filtered.filter(pl.col("snop_month").is_in(filters.target_months))
    if filters.brands is not None:
        filtered = filtered.filter(pl.col("brand_display").is_in(filters.brands))
    if include_horizons and filters.complete_vintage_history_only:
        history_keys = _complete_history_keys(frame, filters)
        if history_keys.height == 0:
            return filtered.head(0)
        filtered = filtered.join(
            history_keys,
            on=["source", "parent_code", "snop_month"],
            how="semi",
        )
    if include_horizons and filters.horizons is not None:
        filtered = filtered.filter(
            pl.col("forecast_horizon_months").is_in(filters.horizons)
        )
    if filters.parent_codes is not None:
        filtered = filtered.filter(pl.col("parent_code").is_in(filters.parent_codes))
    if filters.hierarchy_statuses is not None:
        filtered = filtered.filter(
            pl.col("mapping_status").is_in(filters.hierarchy_statuses)
        )
    if filters.actual_statuses is not None:
        filtered = filtered.filter(pl.col("actual_status").is_in(filters.actual_statuses))
    if filters.source_availability is not None:
        filtered = _apply_source_availability(
            filtered,
            filters,
            availability_population,
        )
    if filters.zero_forecast_only:
        filtered = filtered.filter(pl.col("forecast_kl") == 0)
    if include_minimum_actual and filters.minimum_actual_volume > 0:
        filtered = filtered.filter(
            pl.col("actual_kl").is_not_null()
            & (pl.col("actual_kl") >= filters.minimum_actual_volume)
        )

    return filtered.sort(
        ["parent_code", "snop_month", "calculation_month", "source"]
    )


def apply_quality_pair_filters(
    pair_frame: pl.DataFrame,
    filters: DashboardFilters,
    *,
    availability_frame: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Apply hierarchy, actual, pair, and source-availability status filters."""
    require_columns(
        pair_frame,
        ["mapping_status", "actual_status", "pair_status", "parent_code", "snop_month"],
        "vintage pair population",
    )
    filtered = pair_frame
    if filters.hierarchy_statuses is not None:
        filtered = filtered.filter(
            pl.col("mapping_status").is_in(filters.hierarchy_statuses)
        )
    if filters.actual_statuses is not None:
        filtered = filtered.filter(pl.col("actual_status").is_in(filters.actual_statuses))
    if filters.pair_statuses is not None:
        filtered = filtered.filter(pl.col("pair_status").is_in(filters.pair_statuses))
    if filters.source_availability is not None:
        filtered = _apply_source_availability(
            filtered,
            filters,
            availability_frame if availability_frame is not None else pair_frame,
        )
    if filters.zero_forecast_only:
        require_columns(
            filtered,
            ["vintage_b_forecast_kl"],
            "vintage pair forecast population",
        )
        filtered = filtered.filter(pl.col("vintage_b_forecast_kl") == 0)
    if filters.complete_vintage_history_only and availability_frame is not None:
        history_keys = _complete_history_keys(availability_frame, filters)
        if history_keys.height == 0:
            return filtered.head(0)
        filtered = filtered.join(
            history_keys.select(["source", "parent_code", "snop_month"]),
            on=["source", "parent_code", "snop_month"],
            how="semi",
        )
    return filtered


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


def apply_performance_filters(
    pair_frame: pl.DataFrame,
    filters: DashboardFilters,
) -> pl.DataFrame:
    """Apply Vintage-B performance filters after deterministic pair selection.

    Accuracy and bias are row-level projections of the same aggregate formulas:
    they are used only to select rows, while KPI aggregation still recomputes
    its numerators and denominators from the surviving detail population.
    """
    if not filters.has_performance_filters:
        return pair_frame
    required_columns = [
        "vintage_b_forecast_kl",
        "vintage_b_absolute_error_kl",
        "actual_kl",
        "pair_status",
    ]
    if filters.top_n_metric == "deterioration":
        required_columns.append("error_improvement_kl")
    require_columns(
        pair_frame,
        required_columns,
        "vintage pair performance population",
    )
    filtered = pair_frame
    if filters.forecast_directions is not None:
        filtered = filtered.with_columns(
            pl.when(
                pl.col("actual_kl").is_null()
                | pl.col("vintage_b_forecast_kl").is_null()
            )
            .then(pl.lit(None, dtype=pl.String))
            .when(
                pl.col("vintage_b_forecast_kl") - pl.col("actual_kl")
                > filters.revision_tolerance_kl
            )
            .then(pl.lit("over"))
            .when(
                pl.col("vintage_b_forecast_kl") - pl.col("actual_kl")
                < -filters.revision_tolerance_kl
            )
            .then(pl.lit("under"))
            .otherwise(pl.lit("within_tolerance"))
            .alias("_forecast_direction")
        ).filter(pl.col("_forecast_direction").is_in(filters.forecast_directions))
    if filters.forecast_accuracy_band is not None:
        lower, upper = filters.forecast_accuracy_band
        filtered = filtered.with_columns(
            pl.when(
                (pl.col("pair_status") == "complete")
                & (pl.col("actual_kl") > 0)
            )
            .then(
                (
                    1
                    - pl.col("vintage_b_absolute_error_kl") / pl.col("actual_kl")
                )
                * 100
            )
            .otherwise(pl.lit(None, dtype=pl.Float64))
            .alias("_row_accuracy_pct")
        ).filter(pl.col("_row_accuracy_pct").is_between(lower, upper, closed="both"))
    if filters.bias_band is not None:
        lower, upper = filters.bias_band
        filtered = filtered.with_columns(
            pl.when(
                (pl.col("pair_status") == "complete")
                & (pl.col("actual_kl") > 0)
            )
            .then(
                (
                    pl.col("vintage_b_forecast_kl") - pl.col("actual_kl")
                )
                / pl.col("actual_kl")
                * 100
            )
            .otherwise(pl.lit(None, dtype=pl.Float64))
            .alias("_row_bias_pct")
        ).filter(pl.col("_row_bias_pct").is_between(lower, upper, closed="both"))
    if filters.minimum_absolute_error_kl > 0:
        filtered = filtered.filter(
            pl.col("vintage_b_absolute_error_kl").is_not_null()
            & (
                pl.col("vintage_b_absolute_error_kl")
                >= filters.minimum_absolute_error_kl
            )
        )
    if filters.top_n is not None:
        top_n_column = {
            "actual_volume": "actual_kl",
            "absolute_error": "vintage_b_absolute_error_kl",
            "deterioration": "error_improvement_kl",
        }[filters.top_n_metric]
        if filters.top_n_metric == "deterioration":
            filtered = filtered.with_columns(
                (-pl.col(top_n_column)).alias("_top_n_value")
            )
            sort_column = "_top_n_value"
        else:
            filtered = filtered.with_columns(
                pl.col(top_n_column).alias("_top_n_value")
            )
            sort_column = "_top_n_value"
        filtered = filtered.sort(
            [sort_column, "parent_code", "snop_month"],
            descending=[True, False, False],
            nulls_last=True,
        ).head(filters.top_n)
    return filtered.drop(
        [
            column
            for column in (
                "_forecast_direction",
                "_row_accuracy_pct",
                "_row_bias_pct",
                "_top_n_value",
            )
            if column in filtered.columns
        ]
    )


def apply_actual_filters(
    frame: pl.DataFrame,
    filters: DashboardFilters,
    *,
    availability_frame: pl.DataFrame | None = None,
    forecast_key_frame: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Apply shared filters that have meaning on the actual population.

    Actuals have no forecast horizon. The active horizon population is supplied
    separately through ``availability_frame`` so actual-only and uncovered keys
    remain visible without classifying source availability across inactive
    horizons. ``forecast_key_frame`` is used only by forecast-quality filters
    that intentionally narrow the denominator to eligible forecast keys.
    """
    require_columns(frame, ACTUAL_COLUMNS, "selected actual population")
    prepared = frame
    if availability_frame is not None:
        context_columns = [
            column
            for column in (
                "parent_code",
                "snop_month",
                "brand",
                "mapping_status",
                "mapping_diagnostic",
            )
            if column in availability_frame.columns
        ]
        if len(context_columns) > 2:
            context = (
                availability_frame
                .select(context_columns)
                .unique(subset=["parent_code", "snop_month"], maintain_order=True)
            )
            missing_context_columns = [
                column
                for column in context_columns[2:]
                if column not in prepared.columns
            ]
            if missing_context_columns:
                prepared = prepared.join(
                    context.select(
                        ["parent_code", "snop_month", *missing_context_columns]
                    ),
                    on=["parent_code", "snop_month"],
                    how="left",
                )
    if "brand" not in prepared.columns:
        prepared = prepared.with_columns(pl.lit(None, dtype=pl.String).alias("brand"))
    if "mapping_status" not in prepared.columns:
        prepared = prepared.with_columns(pl.lit("unmapped").alias("mapping_status"))
    if "mapping_diagnostic" not in prepared.columns:
        prepared = prepared.with_columns(
            pl.lit("no hierarchy mapping").alias("mapping_diagnostic")
        )
    prepared = prepared.with_columns(
        pl.col("mapping_status").fill_null("unmapped"),
        pl.when(pl.col("mapping_diagnostic").is_null())
        .then(
            pl.when(pl.col("mapping_status") == "unmapped")
            .then(pl.lit("no hierarchy mapping"))
            .otherwise(pl.lit(None, dtype=pl.String))
        )
        .otherwise(pl.col("mapping_diagnostic"))
        .alias("mapping_diagnostic"),
    )
    filtered = with_display_brand(prepared)
    if "actual_status" not in filtered.columns:
        filtered = filtered.with_columns(
            pl.when(pl.col("actual_kl").is_null())
            .then(pl.lit("missing"))
            .when(pl.col("actual_kl") == 0)
            .then(pl.lit("matched_zero"))
            .otherwise(pl.lit("matched_positive"))
            .alias("actual_status")
        )

    if filters.target_months is not None:
        filtered = filtered.filter(pl.col("snop_month").is_in(filters.target_months))
    if filters.brands is not None:
        filtered = filtered.filter(pl.col("brand_display").is_in(filters.brands))
    if filters.parent_codes is not None:
        filtered = filtered.filter(pl.col("parent_code").is_in(filters.parent_codes))
    if filters.hierarchy_statuses is not None:
        filtered = filtered.filter(
            pl.col("mapping_status").is_in(filters.hierarchy_statuses)
        )
    if filters.actual_statuses is not None:
        filtered = filtered.filter(pl.col("actual_status").is_in(filters.actual_statuses))
    if availability_frame is not None:
        filtered = _apply_source_availability(
            filtered,
            filters,
            availability_frame,
            preserve_unclassified=filters.source_availability is None,
        )
    if forecast_key_frame is not None:
        require_columns(
            forecast_key_frame,
            ["parent_code", "snop_month"],
            "forecast key population",
        )
        filtered = filtered.join(
            forecast_key_frame.select(["parent_code", "snop_month"]).unique(),
            on=["parent_code", "snop_month"],
            how="semi",
        )
    if filters.minimum_actual_volume > 0:
        filtered = filtered.filter(pl.col("actual_kl") >= filters.minimum_actual_volume)

    return filtered.sort(["parent_code", "snop_month"])


def available_filter_values(
    frame: pl.DataFrame,
    source: str,
    *,
    comparison_mode: bool = False,
) -> dict[str, object]:
    """Return source-scoped or comparison-scoped control values."""
    require_columns(frame, ANALYSIS_COLUMNS, "analysis population")
    normalized_source = str(source).strip().lower()
    if normalized_source not in FORECAST_SOURCES:
        raise ValueError(f"unsupported dashboard source {source!r}")
    selected_sources = (
        tuple(sorted(FORECAST_SOURCES)) if comparison_mode else (normalized_source,)
    )
    source_frame = with_display_brand(frame).filter(
        pl.col("source").is_in(selected_sources)
    )
    parent_options = (
        source_frame.select(["parent_code", "parent_description"])
        .unique()
        .sort(["parent_code", "parent_description"])
        .to_dicts()
    )
    horizons = sorted(
        source_frame["forecast_horizon_months"].drop_nulls().unique().to_list(),
        reverse=True,
    )
    if comparison_mode:
        source_horizons = {
            selected_source: set(
                source_frame.filter(pl.col("source") == selected_source)[
                    "forecast_horizon_months"
                ].drop_nulls().to_list()
            )
            for selected_source in selected_sources
        }
        common_horizons = sorted(
            set.intersection(*source_horizons.values())
            if source_horizons
            else set(),
            reverse=True,
        )
    else:
        common_horizons = []
    default_comparison_horizon = (
        1
        if 1 in common_horizons
        else min(common_horizons)
        if common_horizons
        else None
    )
    return {
        "target_months": sorted(source_frame["snop_month"].unique().to_list()),
        "brands": sorted(source_frame["brand_display"].drop_nulls().unique().to_list()),
        "parent_products": parent_options,
        "horizons": horizons,
        "hierarchy_statuses": ["mapped", "unmapped", "conflict"],
        "actual_statuses": ["matched_positive", "matched_zero", "missing"],
        "pair_statuses": [
            "complete",
            "missing_a",
            "missing_b",
            "missing_both",
            "missing_actual",
            "zero_actual",
        ],
        "source_availability": ["tm_only", "ml_only", "both_sources"],
        "common_horizons": common_horizons,
        "default_comparison_horizon": default_comparison_horizon,
        "calculation_months": sorted(
            source_frame["calculation_month"].unique().to_list()
        ),
    }


def normalize_filter_months(values: Iterable[object]) -> tuple[date, ...]:
    """Normalize UI month values while keeping the public filter constructor small."""
    return tuple(_normalize_month(value) for value in values)
