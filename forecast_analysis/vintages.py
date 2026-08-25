"""Source-safe oldest/latest vintage selection for the dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

import polars as pl

from ._utils import require_columns
from .contracts import (
    DEFAULT_REVISION_TOLERANCE_KL,
    FORECAST_SOURCES,
    REVISION_CLASSIFICATION_DECIMAL_PLACES,
    normalize_revision_tolerance,
)
from .filters import with_display_brand  # pyright: ignore[reportMissingImports]

VintageRuleKind = Literal[
    "oldest_available",
    "latest_available",
    "specific_calculation_month",
    "specific_horizon",
]
VINTAGE_RULE_KINDS = frozenset(
    {
        "oldest_available",
        "latest_available",
        "specific_calculation_month",
        "specific_horizon",
    }
)
GROUP_COLUMNS = ["source", "parent_code", "snop_month"]
PAIR_COLUMNS = [
    "source",
    "parent_code",
    "parent_description",
    "brand",
    "mapping_status",
    "mapping_diagnostic",
    "snop_month",
    "actual_kl",
    "actual_status",
    "vintage_a_rule",
    "vintage_a_calculation_month",
    "vintage_a_horizon_months",
    "vintage_a_forecast_kl",
    "vintage_b_rule",
    "vintage_b_calculation_month",
    "vintage_b_horizon_months",
    "vintage_b_forecast_kl",
    "vintage_a_absolute_error_kl",
    "vintage_b_absolute_error_kl",
    "vintage_a_bias_kl",
    "vintage_b_bias_kl",
    "revision_kl",
    "revision_pct",
    "error_improvement_kl",
    "revision_direction",
    "revision_outcome",
    "pair_status",
]
PAIR_SCHEMA = {
    "source": pl.String,
    "parent_code": pl.Int64,
    "parent_description": pl.String,
    "brand": pl.String,
    "mapping_status": pl.String,
    "mapping_diagnostic": pl.String,
    "snop_month": pl.Date,
    "actual_kl": pl.Float64,
    "actual_status": pl.String,
    "vintage_a_rule": pl.String,
    "vintage_a_calculation_month": pl.Date,
    "vintage_a_horizon_months": pl.Int64,
    "vintage_a_forecast_kl": pl.Float64,
    "vintage_b_rule": pl.String,
    "vintage_b_calculation_month": pl.Date,
    "vintage_b_horizon_months": pl.Int64,
    "vintage_b_forecast_kl": pl.Float64,
    "vintage_a_absolute_error_kl": pl.Float64,
    "vintage_b_absolute_error_kl": pl.Float64,
    "vintage_a_bias_kl": pl.Float64,
    "vintage_b_bias_kl": pl.Float64,
    "revision_kl": pl.Float64,
    "revision_pct": pl.Float64,
    "error_improvement_kl": pl.Float64,
    "revision_direction": pl.String,
    "revision_outcome": pl.String,
    "pair_status": pl.String,
}


@dataclass(frozen=True)
class VintageRule:
    """A deterministic rule for selecting one vintage per product-target group."""

    kind: VintageRuleKind
    value: date | int | None = None

    def __post_init__(self) -> None:
        if self.kind not in VINTAGE_RULE_KINDS:
            raise ValueError(
                f"unsupported vintage rule {self.kind!r}; "
                f"choose one of {sorted(VINTAGE_RULE_KINDS)}"
            )
        if self.kind in {"oldest_available", "latest_available"}:
            if self.value is not None:
                raise ValueError(f"{self.kind} does not accept a value")
        elif self.value is None:
            raise ValueError(f"{self.kind} requires a value")
        elif self.kind == "specific_calculation_month":
            if not isinstance(self.value, date):
                raise ValueError("specific_calculation_month requires a date value")
            calculation_month = (
                self.value.date() if isinstance(self.value, datetime) else self.value
            )
            object.__setattr__(
                self,
                "value",
                date(calculation_month.year, calculation_month.month, 1),
            )
        elif self.kind == "specific_horizon":
            if isinstance(self.value, bool) or not isinstance(self.value, int):
                raise ValueError("specific_horizon requires an integer value")
            if self.value < 0:
                raise ValueError("specific_horizon requires a non-negative integer")

    @classmethod
    def oldest_available(cls) -> "VintageRule":
        return cls("oldest_available")

    @classmethod
    def latest_available(cls) -> "VintageRule":
        return cls("latest_available")

    @classmethod
    def specific_calculation_month(cls, value: date) -> "VintageRule":
        return cls("specific_calculation_month", value)

    @classmethod
    def specific_horizon(cls, value: int) -> "VintageRule":
        return cls("specific_horizon", value)

    @property
    def label(self) -> str:
        if self.value is None:
            return self.kind
        return f"{self.kind}:{self.value}"


def _empty_pair_frame() -> pl.DataFrame:
    return pl.DataFrame(schema=PAIR_SCHEMA).select(PAIR_COLUMNS)


def _select_rule(frame: pl.DataFrame, rule: VintageRule) -> pl.DataFrame:
    ordered = frame.sort(GROUP_COLUMNS + ["calculation_month"])
    if rule.kind == "oldest_available":
        return ordered.group_by(GROUP_COLUMNS, maintain_order=True).first()
    if rule.kind == "latest_available":
        return ordered.group_by(GROUP_COLUMNS, maintain_order=True).last()
    if rule.kind == "specific_calculation_month":
        return ordered.filter(pl.col("calculation_month") == rule.value).group_by(
            GROUP_COLUMNS, maintain_order=True
        ).first()
    return ordered.filter(pl.col("forecast_horizon_months") == rule.value).group_by(
        GROUP_COLUMNS, maintain_order=True
    ).first()


def _project_selected(frame: pl.DataFrame, rule: VintageRule, prefix: str) -> pl.DataFrame:
    selected = _select_rule(frame, rule)
    return selected.select(
        GROUP_COLUMNS
        + [
            pl.col("calculation_month").alias(f"{prefix}_calculation_month"),
            pl.col("forecast_horizon_months").alias(f"{prefix}_horizon_months"),
            pl.col("forecast_kl").alias(f"{prefix}_forecast_kl"),
        ]
    )


def _pair_status_expression() -> pl.Expr:
    a_missing = pl.col("vintage_a_calculation_month").is_null()
    b_missing = pl.col("vintage_b_calculation_month").is_null()
    return (
        pl.when(a_missing & b_missing)
        .then(pl.lit("missing_both"))
        .when(a_missing)
        .then(pl.lit("missing_a"))
        .when(b_missing)
        .then(pl.lit("missing_b"))
        .when(pl.col("actual_status") == "missing")
        .then(pl.lit("missing_actual"))
        .when(pl.col("actual_status") == "matched_zero")
        .then(pl.lit("zero_actual"))
        .otherwise(pl.lit("complete"))
        .alias("pair_status")
    )


def _with_revision_metrics(
    pair_frame: pl.DataFrame,
    tolerance_kl: float,
) -> pl.DataFrame:
    """Add hand-calculable row metrics while preserving non-comparable statuses.

    Revision values can be displayed for zero-actual pairs when both vintages
    exist. Aggregate revision effectiveness still uses only ``complete`` rows,
    so zero-actual and missing-actual rows remain visible without entering its
    denominator.
    """
    tolerance = normalize_revision_tolerance(tolerance_kl)
    has_both_vintages = (
        pl.col("vintage_a_calculation_month").is_not_null()
        & pl.col("vintage_b_calculation_month").is_not_null()
    )
    has_actual = has_both_vintages & pl.col("actual_kl").is_not_null()
    classification_tolerance = round(
        tolerance,
        REVISION_CLASSIFICATION_DECIMAL_PLACES,
    )
    null_float = pl.lit(None, dtype=pl.Float64)
    null_string = pl.lit(None, dtype=pl.String)
    return (
        pair_frame.with_columns(
            pl.when(has_both_vintages)
            .then(
                (
                    pl.col("vintage_b_forecast_kl")
                    - pl.col("vintage_a_forecast_kl")
                ).cast(pl.Float64)
            )
            .otherwise(null_float)
            .alias("revision_kl")
        )
        .with_columns(
            pl.when(
                pl.col("revision_kl").is_not_null()
                & (pl.col("vintage_a_forecast_kl") != 0)
            )
            .then(
                (
                    pl.col("revision_kl")
                    / pl.col("vintage_a_forecast_kl")
                    * 100
                ).cast(pl.Float64)
            )
            .otherwise(null_float)
            .alias("revision_pct"),
            pl.when(has_actual)
            .then(
                (
                    pl.col("vintage_a_forecast_kl") - pl.col("actual_kl")
                ).abs().cast(pl.Float64)
            )
            .otherwise(null_float)
            .alias("vintage_a_absolute_error_kl"),
            pl.when(has_actual)
            .then(
                (
                    pl.col("vintage_b_forecast_kl") - pl.col("actual_kl")
                ).abs().cast(pl.Float64)
            )
            .otherwise(null_float)
            .alias("vintage_b_absolute_error_kl"),
            pl.when(has_actual)
            .then(
                (
                    pl.col("vintage_a_forecast_kl") - pl.col("actual_kl")
                ).cast(pl.Float64)
            )
            .otherwise(null_float)
            .alias("vintage_a_bias_kl"),
            pl.when(has_actual)
            .then(
                (
                    pl.col("vintage_b_forecast_kl") - pl.col("actual_kl")
                ).cast(pl.Float64)
            )
            .otherwise(null_float)
            .alias("vintage_b_bias_kl"),
        )
        .with_columns(
            pl.when(
                pl.col("vintage_a_absolute_error_kl").is_not_null()
                & pl.col("vintage_b_absolute_error_kl").is_not_null()
            )
            .then(
                (
                    pl.col("vintage_a_absolute_error_kl")
                    - pl.col("vintage_b_absolute_error_kl")
                ).cast(pl.Float64)
            )
            .otherwise(null_float)
            .alias("error_improvement_kl"),
            pl.when(pl.col("revision_kl").is_null())
            .then(null_string)
            .when(
                pl.col("revision_kl").round(REVISION_CLASSIFICATION_DECIMAL_PLACES)
                > classification_tolerance
            )
            .then(pl.lit("up"))
            .when(
                pl.col("revision_kl").round(REVISION_CLASSIFICATION_DECIMAL_PLACES)
                < -classification_tolerance
            )
            .then(pl.lit("down"))
            .otherwise(pl.lit("unchanged"))
            .alias("revision_direction"),
        )
        .with_columns(
            pl.when(pl.col("error_improvement_kl").is_null())
            .then(null_string)
            .when(
                pl.col("error_improvement_kl").round(
                    REVISION_CLASSIFICATION_DECIMAL_PLACES
                )
                > classification_tolerance
            )
            .then(pl.lit("improved"))
            .when(
                pl.col("error_improvement_kl").round(
                    REVISION_CLASSIFICATION_DECIMAL_PLACES
                )
                < -classification_tolerance
            )
            .then(pl.lit("worsened"))
            .otherwise(pl.lit("neutral"))
            .alias("revision_outcome"),
        )
    )


def select_vintage_pair(
    frame: pl.DataFrame,
    source: str,
    vintage_a: VintageRule | None = None,
    vintage_b: VintageRule | None = None,
    *,
    population_frame: pl.DataFrame | None = None,
    revision_tolerance_kl: float = DEFAULT_REVISION_TOLERANCE_KL,
) -> pl.DataFrame:
    """Build one source-isolated comparable row per parent product and target month.

    ``frame`` supplies the rows eligible for the selected vintage rules. When a
    filter narrows that frame to one exact horizon, ``population_frame`` keeps
    the unfiltered product-target groups as the coverage population so missing
    observations become explicit pair statuses instead of disappearing. The
    absolute tolerance controls ``revision_direction`` and ``revision_outcome``.
    """
    required = [
        "source",
        "parent_code",
        "parent_description",
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
    require_columns(frame, required, "analysis population")
    normalized_source = str(source).strip().lower()
    if normalized_source not in FORECAST_SOURCES:
        raise ValueError(f"unsupported dashboard source {source!r}")
    rule_a = vintage_a or VintageRule.oldest_available()
    rule_b = vintage_b or VintageRule.latest_available()

    selection_frame = with_display_brand(frame).filter(
        pl.col("source") == normalized_source
    )
    coverage_frame = population_frame if population_frame is not None else frame
    if population_frame is not None:
        require_columns(coverage_frame, required, "coverage analysis population")
    coverage_source_frame = with_display_brand(coverage_frame).filter(
        pl.col("source") == normalized_source
    )
    if coverage_source_frame.height == 0:
        return _empty_pair_frame()

    base = (
        coverage_source_frame.sort(GROUP_COLUMNS + ["calculation_month"])
        .group_by(GROUP_COLUMNS, maintain_order=True)
        .agg(
            pl.col("parent_description").first(),
            pl.col("brand").first(),
            pl.col("mapping_status").first(),
            pl.col("mapping_diagnostic").first(),
            pl.col("actual_kl").first(),
            pl.col("actual_status").first(),
        )
    )
    paired = (
        base.join(
            _project_selected(selection_frame, rule_a, "vintage_a"),
            on=GROUP_COLUMNS,
            how="left",
        )
        .join(
            _project_selected(selection_frame, rule_b, "vintage_b"),
            on=GROUP_COLUMNS,
            how="left",
        )
        .with_columns(
            pl.lit(rule_a.label).alias("vintage_a_rule"),
            pl.lit(rule_b.label).alias("vintage_b_rule"),
        )
        .with_columns(_pair_status_expression())
    )
    return _with_revision_metrics(
        paired,
        revision_tolerance_kl,
    ).select(PAIR_COLUMNS).sort(["parent_code", "snop_month"])
