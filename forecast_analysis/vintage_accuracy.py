"""Common-cohort forecast accuracy across an ordered set of vintage rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence, TypedDict, cast

import polars as pl

from ._utils import require_columns
from .contracts import FORECAST_SOURCES
from .vintages import VintageRule

_GROUP_COLUMNS = ["parent_code", "snop_month"]
_REQUIRED_COLUMNS = [
    "source",
    "parent_code",
    "calculation_month",
    "snop_month",
    "forecast_horizon_months",
    "forecast_kl",
    "actual_kl",
]
CANONICAL_OLDEST_HORIZON = 5
CANONICAL_LATEST_HORIZON = 1


class _MonthlyAggregate(TypedDict):
    snop_month: date
    eligible_parents: int
    actual_denominator_kl: float
    absolute_error_numerator_kl: float


@dataclass(frozen=True)
class VintageAccuracyRow:
    """Auditable accuracy components for one rule and target month."""

    target_month: date
    forecast_accuracy_pct: float | None
    absolute_error_numerator_kl: float
    actual_denominator_kl: float
    eligible_parents: int


@dataclass(frozen=True)
class VintageAccuracySeries:
    """Rule identity and its monthly values over the shared cohort."""

    rule: VintageRule
    rule_id: str
    label: str
    fixed: bool
    selected_by_default: bool
    rows: tuple[VintageAccuracyRow, ...]


@dataclass(frozen=True)
class CommonVintageAccuracy:
    """Ordered historical comparison series followed by fixed latest."""

    series: tuple[VintageAccuracySeries, ...]


def _rule_display_label(rule: VintageRule) -> str:
    if rule.kind == "oldest_available":
        return "Oldest (5 months ahead)"
    if rule.kind == "latest_available":
        return "Latest (1 month ahead)"
    if rule.kind == "specific_horizon":
        unit = "month" if rule.value == 1 else "months"
        return f"{rule.value} {unit} ahead"
    return f"Calculation month {cast(date, rule.value):%Y-%m}"


def _ordered_rules(
    comparison_rules: Sequence[VintageRule] | None,
) -> tuple[VintageRule, ...]:
    comparisons = (
        (VintageRule.oldest_available(),)
        if comparison_rules is None
        else tuple(comparison_rules)
    )
    rules = (*comparisons, VintageRule.latest_available())
    seen: set[VintageRule] = set()
    for rule in rules:
        if rule in seen:
            raise ValueError(f"duplicate vintage rule: {rule.label}")
        seen.add(rule)
    return rules


def _select_forecasts(
    frame: pl.DataFrame,
    rule: VintageRule,
    forecast_column: str,
) -> pl.DataFrame:
    ordered = frame.sort([*_GROUP_COLUMNS, "calculation_month"])
    if rule.kind == "oldest_available":
        selected = ordered.filter(
            pl.col("forecast_horizon_months") == CANONICAL_OLDEST_HORIZON
        )
    elif rule.kind == "latest_available":
        selected = ordered.filter(
            pl.col("forecast_horizon_months") == CANONICAL_LATEST_HORIZON
        )
    elif rule.kind == "specific_calculation_month":
        selected = ordered.filter(pl.col("calculation_month") == rule.value).group_by(
            _GROUP_COLUMNS, maintain_order=True
        ).first()
    else:
        selected = ordered.filter(
            pl.col("forecast_horizon_months") == rule.value
        ).group_by(_GROUP_COLUMNS, maintain_order=True).first()
    return selected.filter(pl.col("forecast_kl").is_not_null()).select(
        *_GROUP_COLUMNS,
        pl.col("forecast_kl").cast(pl.Float64).alias(forecast_column),
    )


def _monthly_aggregates(
    common: pl.DataFrame,
    forecast_column: str,
) -> dict[date, _MonthlyAggregate]:
    monthly = (
        common.group_by("snop_month")
        .agg(
            pl.len().cast(pl.Int64).alias("eligible_parents"),
            pl.col("actual_kl").sum().alias("actual_denominator_kl"),
            (pl.col(forecast_column) - pl.col("actual_kl"))
            .abs()
            .sum()
            .alias("absolute_error_numerator_kl"),
        )
        .to_dicts()
    )
    return {
        row["snop_month"]: row
        for row in cast(list[_MonthlyAggregate], monthly)
    }


def build_common_vintage_accuracy(
    frame: pl.DataFrame,
    source: str,
    comparison_rules: Sequence[VintageRule] | None = None,
) -> CommonVintageAccuracy:
    """Calculate monthly FA for all rules from one common parent cohort.

    ``comparison_rules`` retain caller order and are followed by the fixed
    latest rule. In this canonical forecast-accuracy context, oldest resolves
    only M5 and latest resolves only M1; neither rule falls back to another
    available horizon. Omitting the argument selects oldest by default, while
    an empty tuple intentionally calculates latest only. For each target month,
    a parent contributes only when actual volume is positive and every requested
    rule resolves to a non-null forecast.
    """
    require_columns(frame, _REQUIRED_COLUMNS, "vintage accuracy population")
    normalized_source = str(source).strip().lower()
    if normalized_source not in FORECAST_SOURCES:
        raise ValueError(f"unsupported dashboard source {source!r}")
    rules = _ordered_rules(comparison_rules)

    source_frame = frame.filter(pl.col("source") == normalized_source)
    ordered = source_frame.sort([*_GROUP_COLUMNS, "calculation_month"])
    actuals = (
        ordered.group_by(_GROUP_COLUMNS, maintain_order=True)
        .agg(pl.col("actual_kl").first().cast(pl.Float64).alias("actual_kl"))
        .filter(pl.col("actual_kl").is_not_null() & (pl.col("actual_kl") > 0))
    )
    target_months = sorted(
        cast(list[date], actuals.get_column("snop_month").unique().to_list())
    )

    common = actuals
    forecast_columns: list[str] = []
    for index, rule in enumerate(rules):
        forecast_column = f"_forecast_{index}"
        forecast_columns.append(forecast_column)
        common = common.join(
            _select_forecasts(source_frame, rule, forecast_column),
            on=_GROUP_COLUMNS,
            how="inner",
        )

    series: list[VintageAccuracySeries] = []
    for rule, forecast_column in zip(rules, forecast_columns, strict=True):
        aggregates = _monthly_aggregates(common, forecast_column)
        rows: list[VintageAccuracyRow] = []
        for target_month in target_months:
            aggregate = aggregates.get(target_month)
            if aggregate is None:
                rows.append(VintageAccuracyRow(target_month, None, 0.0, 0.0, 0))
                continue
            denominator = aggregate["actual_denominator_kl"]
            absolute_error = aggregate["absolute_error_numerator_kl"]
            rows.append(
                VintageAccuracyRow(
                    target_month=target_month,
                    forecast_accuracy_pct=100.0 * (1.0 - absolute_error / denominator),
                    absolute_error_numerator_kl=absolute_error,
                    actual_denominator_kl=denominator,
                    eligible_parents=aggregate["eligible_parents"],
                )
            )
        series.append(
            VintageAccuracySeries(
                rule=rule,
                rule_id=rule.label,
                label=_rule_display_label(rule),
                fixed=rule.kind == "latest_available",
                selected_by_default=rule.kind == "oldest_available",
                rows=tuple(rows),
            )
        )

    return CommonVintageAccuracy(series=tuple(series))
