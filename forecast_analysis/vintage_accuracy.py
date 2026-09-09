"""Common-cohort forecast accuracy across an ordered set of vintage rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence, TypedDict, cast

import polars as pl

from ._utils import require_columns
from .contracts import DEFAULT_REVISION_TOLERANCE_KL, FORECAST_SOURCES
from .metrics import calculate_revision_metrics
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
    forecast_kl: float
    actual_denominator_kl: float
    absolute_error_numerator_kl: float
    bias_numerator_kl: float


@dataclass(frozen=True)
class VintageAccuracyRow:
    """Auditable accuracy and revision components for one target month."""

    target_month: date
    forecast_accuracy_pct: float | None
    forecast_kl: float
    absolute_error_numerator_kl: float
    actual_denominator_kl: float
    bias_numerator_kl: float
    eligible_parents: int
    revision_effectiveness_pct: float | None
    effectiveness_numerator: int
    effectiveness_denominator: int
    latest_absolute_error_numerator_kl: float


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
class VintageCohortOverview:
    """Overview KPI arithmetic for the primary displayed vintage."""

    primary_rule_id: str
    primary_label: str
    forecast_accuracy_pct: float | None
    wape_pct: float | None
    bias_pct: float | None
    accuracy_numerator_kl: float | None
    accuracy_denominator_actual_kl: float | None
    bias_numerator_kl: float | None
    bias_denominator_actual_kl: float | None
    eligible_observations: int
    accuracy_delta_pp: float | None
    revision_effectiveness_pct: float | None
    effectiveness_numerator: int
    effectiveness_denominator: int
    primary_error_kl: float | None
    latest_error_kl: float | None


@dataclass(frozen=True)
class WapeExampleRow:
    """One high-error common-cohort row used to explain WAPE arithmetic."""

    parent_code: int
    parent_description: str | None
    target_month: date
    forecast_kl: float
    actual_kl: float
    absolute_error_kl: float
    direction: str


@dataclass(frozen=True)
class CommonVintageAccuracy:
    """Ordered series and overview KPIs over one shared cohort."""

    series: tuple[VintageAccuracySeries, ...]
    overview: VintageCohortOverview
    wape_examples: tuple[WapeExampleRow, ...]


@dataclass(frozen=True)
class VintageGapDriverRow:
    """One parent product's signed contribution to a monthly WAPE gap."""

    brand: str
    parent_code: int
    parent_description: str | None
    actual_kl: float
    baseline_forecast_kl: float
    latest_forecast_kl: float
    baseline_absolute_error_kl: float
    latest_absolute_error_kl: float
    error_change_kl: float
    wape_contribution_pp: float
    forecast_revision_kl: float
    baseline_direction: str
    latest_direction: str


@dataclass(frozen=True)
class VintageGapBrandRow:
    """Brand subtotal built from parent contributions on the shared denominator."""

    brand: str
    parent_count: int
    actual_kl: float
    baseline_forecast_kl: float
    latest_forecast_kl: float
    baseline_absolute_error_kl: float
    latest_absolute_error_kl: float
    error_change_kl: float
    wape_contribution_pp: float
    gross_fix_kl: float
    gross_fix_wape_pp: float
    regression_kl: float
    regression_wape_pp: float


@dataclass(frozen=True)
class VintageGapDrilldown:
    """Auditable monthly reconciliation from a historical vintage to Latest M1."""

    source: str
    target_month: date
    baseline_rule_id: str
    baseline_label: str
    latest_rule_id: str
    latest_label: str
    eligible_parents: int
    actual_denominator_kl: float
    baseline_absolute_error_kl: float
    latest_absolute_error_kl: float
    baseline_wape_pct: float | None
    latest_wape_pct: float | None
    net_wape_improvement_pp: float | None
    gross_fix_kl: float
    gross_fix_wape_pp: float | None
    regression_kl: float
    regression_wape_pp: float | None
    brands: tuple[VintageGapBrandRow, ...]
    parents: tuple[VintageGapDriverRow, ...]


@dataclass(frozen=True)
class _CommonVintageFrame:
    """Resolved forecasts and actuals shared by every requested vintage."""

    source: str
    source_frame: pl.DataFrame
    rules: tuple[VintageRule, ...]
    common: pl.DataFrame
    forecast_columns: tuple[str, ...]
    target_months: tuple[date, ...]


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


def _build_common_vintage_frame(
    frame: pl.DataFrame,
    source: str,
    comparison_rules: Sequence[VintageRule] | None,
) -> _CommonVintageFrame:
    """Resolve one exact common cohort for all comparisons plus fixed Latest M1."""
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
    target_months = tuple(
        sorted(cast(list[date], actuals.get_column("snop_month").unique().to_list()))
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
    return _CommonVintageFrame(
        source=normalized_source,
        source_frame=source_frame,
        rules=rules,
        common=common,
        forecast_columns=tuple(forecast_columns),
        target_months=target_months,
    )


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


def _wape_examples(
    common: pl.DataFrame,
    source_frame: pl.DataFrame,
    forecast_column: str,
    *,
    limit: int = 8,
) -> tuple[WapeExampleRow, ...]:
    """Return the largest absolute-error rows from the exact KPI cohort."""
    examples = common.select(
        *_GROUP_COLUMNS,
        pl.col(forecast_column).alias("forecast_kl"),
        "actual_kl",
    ).with_columns(
        (pl.col("forecast_kl") - pl.col("actual_kl"))
        .abs()
        .alias("absolute_error_kl"),
        pl.when(pl.col("forecast_kl") > pl.col("actual_kl"))
        .then(pl.lit("over"))
        .when(pl.col("forecast_kl") < pl.col("actual_kl"))
        .then(pl.lit("under"))
        .otherwise(pl.lit("match"))
        .alias("direction"),
    )
    if "parent_description" in source_frame.columns:
        descriptions = source_frame.group_by(
            _GROUP_COLUMNS, maintain_order=True
        ).agg(
            pl.col("parent_description")
            .drop_nulls()
            .first()
            .cast(pl.String)
            .alias("parent_description")
        )
        examples = examples.join(
            descriptions,
            on=_GROUP_COLUMNS,
            how="left",
        )
    else:
        examples = examples.with_columns(
            pl.lit(None, dtype=pl.String).alias("parent_description")
        )
    rows = (
        examples.sort(
            ["absolute_error_kl", "snop_month", "parent_code"],
            descending=[True, False, False],
        )
        .unique(subset=["parent_code"], keep="first", maintain_order=True)
        .head(limit)
    )
    return tuple(
        WapeExampleRow(
            parent_code=cast(int, row["parent_code"]),
            parent_description=cast(str | None, row["parent_description"]),
            target_month=cast(date, row["snop_month"]),
            forecast_kl=cast(float, row["forecast_kl"]),
            actual_kl=cast(float, row["actual_kl"]),
            absolute_error_kl=cast(float, row["absolute_error_kl"]),
            direction=cast(str, row["direction"]),
        )
        for row in rows.to_dicts()
    )


def _monthly_aggregates(
    common: pl.DataFrame,
    forecast_column: str,
) -> dict[date, _MonthlyAggregate]:
    monthly = (
        common.group_by("snop_month")
        .agg(
            pl.len().cast(pl.Int64).alias("eligible_parents"),
            pl.col(forecast_column).sum().alias("forecast_kl"),
            pl.col("actual_kl").sum().alias("actual_denominator_kl"),
            (pl.col(forecast_column) - pl.col("actual_kl"))
            .abs()
            .sum()
            .alias("absolute_error_numerator_kl"),
            (pl.col(forecast_column) - pl.col("actual_kl"))
            .sum()
            .alias("bias_numerator_kl"),
        )
        .to_dicts()
    )
    return {
        row["snop_month"]: row
        for row in cast(list[_MonthlyAggregate], monthly)
    }


def _monthly_revision_metrics(
    common: pl.DataFrame,
    forecast_column: str,
    latest_column: str,
    target_months: Sequence[date],
    revision_tolerance_kl: float,
) -> dict[date, tuple[float | None, int, int]]:
    """Calculate revision effectiveness for each monthly chart data point."""
    metrics_by_month: dict[date, tuple[float | None, int, int]] = {}
    for target_month in target_months:
        monthly_pairs = common.filter(pl.col("snop_month") == target_month).select(
            pl.col(forecast_column).alias("vintage_a_forecast_kl"),
            pl.col(latest_column).alias("vintage_b_forecast_kl"),
            "actual_kl",
            pl.lit("complete").alias("pair_status"),
        )
        metrics = calculate_revision_metrics(
            monthly_pairs,
            revision_tolerance_kl=revision_tolerance_kl,
        )
        metrics_by_month[target_month] = (
            metrics.revision_effectiveness_pct,
            metrics.effectiveness_numerator,
            metrics.effectiveness_denominator,
        )
    return metrics_by_month


def build_common_vintage_accuracy(
    frame: pl.DataFrame,
    source: str,
    comparison_rules: Sequence[VintageRule] | None = None,
    *,
    revision_tolerance_kl: float = DEFAULT_REVISION_TOLERANCE_KL,
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
    resolved = _build_common_vintage_frame(frame, source, comparison_rules)
    rules = resolved.rules
    source_frame = resolved.source_frame
    target_months = resolved.target_months
    common = resolved.common
    forecast_columns = resolved.forecast_columns

    series: list[VintageAccuracySeries] = []
    latest_aggregates = _monthly_aggregates(common, forecast_columns[-1])
    for rule, forecast_column in zip(rules, forecast_columns, strict=True):
        aggregates = _monthly_aggregates(common, forecast_column)
        revisions = _monthly_revision_metrics(
            common,
            forecast_column,
            forecast_columns[-1],
            target_months,
            revision_tolerance_kl,
        )
        rows: list[VintageAccuracyRow] = []
        for target_month in target_months:
            aggregate = aggregates.get(target_month)
            latest_aggregate = latest_aggregates.get(target_month)
            effectiveness, effectiveness_numerator, effectiveness_denominator = (
                revisions[target_month]
            )
            if aggregate is None:
                rows.append(
                    VintageAccuracyRow(
                        target_month=target_month,
                        forecast_accuracy_pct=None,
                        forecast_kl=0.0,
                        absolute_error_numerator_kl=0.0,
                        actual_denominator_kl=0.0,
                        bias_numerator_kl=0.0,
                        eligible_parents=0,
                        revision_effectiveness_pct=effectiveness,
                        effectiveness_numerator=effectiveness_numerator,
                        effectiveness_denominator=effectiveness_denominator,
                        latest_absolute_error_numerator_kl=0.0,
                    )
                )
                continue
            denominator = aggregate["actual_denominator_kl"]
            absolute_error = aggregate["absolute_error_numerator_kl"]
            rows.append(
                VintageAccuracyRow(
                    target_month=target_month,
                    forecast_accuracy_pct=100.0 * (1.0 - absolute_error / denominator),
                    forecast_kl=aggregate["forecast_kl"],
                    absolute_error_numerator_kl=absolute_error,
                    actual_denominator_kl=denominator,
                    bias_numerator_kl=aggregate["bias_numerator_kl"],
                    eligible_parents=aggregate["eligible_parents"],
                    revision_effectiveness_pct=effectiveness,
                    effectiveness_numerator=effectiveness_numerator,
                    effectiveness_denominator=effectiveness_denominator,
                    latest_absolute_error_numerator_kl=(
                        latest_aggregate["absolute_error_numerator_kl"]
                        if latest_aggregate is not None
                        else 0.0
                    ),
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

    primary_rule = rules[0]
    primary_column = forecast_columns[0]
    latest_column = forecast_columns[-1]
    raw_denominator = common.get_column("actual_kl").sum() if common.height else None
    denominator = None if raw_denominator is None else cast(float, raw_denominator)
    primary_errors = (
        (common.get_column(primary_column) - common.get_column("actual_kl"))
        if common.height
        else pl.Series("primary_error", [], dtype=pl.Float64)
    )
    latest_errors = (
        (common.get_column(latest_column) - common.get_column("actual_kl"))
        if common.height
        else pl.Series("latest_error", [], dtype=pl.Float64)
    )
    raw_primary_error = primary_errors.abs().sum() if common.height else None
    raw_latest_error = latest_errors.abs().sum() if common.height else None
    raw_bias_numerator = primary_errors.sum() if common.height else None
    primary_error = (
        None if raw_primary_error is None else cast(float, raw_primary_error)
    )
    latest_error = None if raw_latest_error is None else cast(float, raw_latest_error)
    bias_numerator = (
        None if raw_bias_numerator is None else cast(float, raw_bias_numerator)
    )
    accuracy = wape = bias = None
    if denominator not in (None, 0) and primary_error is not None:
        accuracy = 100.0 * (1.0 - primary_error / denominator)
        wape = 100.0 * primary_error / denominator
        if bias_numerator is not None:
            bias = 100.0 * bias_numerator / denominator

    revision_frame = common.select(
        pl.col(primary_column).alias("vintage_a_forecast_kl"),
        pl.col(latest_column).alias("vintage_b_forecast_kl"),
        "actual_kl",
        pl.lit("complete").alias("pair_status"),
    )
    revision = calculate_revision_metrics(
        revision_frame,
        revision_tolerance_kl=revision_tolerance_kl,
    )
    overview = VintageCohortOverview(
        primary_rule_id=primary_rule.label,
        primary_label=_rule_display_label(primary_rule),
        forecast_accuracy_pct=accuracy,
        wape_pct=wape,
        bias_pct=bias,
        accuracy_numerator_kl=primary_error,
        accuracy_denominator_actual_kl=denominator,
        bias_numerator_kl=bias_numerator,
        bias_denominator_actual_kl=denominator,
        eligible_observations=common.height,
        accuracy_delta_pp=revision.accuracy_delta_pp,
        revision_effectiveness_pct=revision.revision_effectiveness_pct,
        effectiveness_numerator=revision.effectiveness_numerator,
        effectiveness_denominator=revision.effectiveness_denominator,
        primary_error_kl=primary_error,
        latest_error_kl=latest_error,
    )
    return CommonVintageAccuracy(
        series=tuple(series),
        overview=overview,
        wape_examples=_wape_examples(common, source_frame, primary_column),
    )


def _forecast_direction(forecast: float, actual: float) -> str:
    if forecast > actual:
        return "over"
    if forecast < actual:
        return "under"
    return "match"


def build_vintage_gap_drilldown(
    frame: pl.DataFrame,
    source: str,
    comparison_rules: Sequence[VintageRule],
    target_month: date,
) -> VintageGapDrilldown:
    """Explain one chart month's WAPE gap from the oldest requested rule to M1.

    ``comparison_rules`` must be ordered oldest first, matching the canonical
    chart option order. The common cohort still requires every requested rule,
    so selecting additional displayed vintages changes this drill-down exactly
    as it changes the chart.
    """
    if not comparison_rules:
        raise ValueError("at least one historical accuracy vintage is required")
    resolved = _build_common_vintage_frame(frame, source, comparison_rules)
    baseline_rule = resolved.rules[0]
    latest_rule = resolved.rules[-1]
    baseline_column = resolved.forecast_columns[0]
    latest_column = resolved.forecast_columns[-1]
    target = resolved.common.filter(pl.col("snop_month") == target_month)

    metadata_expressions: list[pl.Expr] = []
    if "brand_display" in resolved.source_frame.columns:
        metadata_expressions.append(
            pl.col("brand_display").drop_nulls().first().cast(pl.String).alias("brand")
        )
    if "parent_description" in resolved.source_frame.columns:
        metadata_expressions.append(
            pl.col("parent_description")
            .drop_nulls()
            .first()
            .cast(pl.String)
            .alias("parent_description")
        )
    if metadata_expressions and target.height:
        metadata = resolved.source_frame.group_by(
            _GROUP_COLUMNS, maintain_order=True
        ).agg(*metadata_expressions)
        target = target.join(metadata, on=_GROUP_COLUMNS, how="left")
    if "brand" not in target.columns:
        target = target.with_columns(pl.lit("Unmapped").alias("brand"))
    else:
        target = target.with_columns(pl.col("brand").fill_null("Unmapped"))
    if "parent_description" not in target.columns:
        target = target.with_columns(
            pl.lit(None, dtype=pl.String).alias("parent_description")
        )

    target = target.with_columns(
        pl.col(baseline_column).alias("baseline_forecast_kl"),
        pl.col(latest_column).alias("latest_forecast_kl"),
    ).with_columns(
        (pl.col("baseline_forecast_kl") - pl.col("actual_kl"))
        .abs()
        .alias("baseline_absolute_error_kl"),
        (pl.col("latest_forecast_kl") - pl.col("actual_kl"))
        .abs()
        .alias("latest_absolute_error_kl"),
        (pl.col("latest_forecast_kl") - pl.col("baseline_forecast_kl")).alias(
            "forecast_revision_kl"
        ),
    ).with_columns(
        (
            pl.col("baseline_absolute_error_kl")
            - pl.col("latest_absolute_error_kl")
        ).alias("error_change_kl")
    )

    raw_denominator = target.get_column("actual_kl").sum() if target.height else 0.0
    denominator = cast(float, raw_denominator or 0.0)
    if denominator > 0:
        target = target.with_columns(
            (100.0 * pl.col("error_change_kl") / denominator).alias(
                "wape_contribution_pp"
            )
        )
    else:
        target = target.with_columns(
            pl.lit(0.0, dtype=pl.Float64).alias("wape_contribution_pp")
        )

    parent_rows = tuple(
        VintageGapDriverRow(
            brand=str(row["brand"]),
            parent_code=cast(int, row["parent_code"]),
            parent_description=cast(str | None, row["parent_description"]),
            actual_kl=cast(float, row["actual_kl"]),
            baseline_forecast_kl=cast(float, row["baseline_forecast_kl"]),
            latest_forecast_kl=cast(float, row["latest_forecast_kl"]),
            baseline_absolute_error_kl=cast(
                float, row["baseline_absolute_error_kl"]
            ),
            latest_absolute_error_kl=cast(float, row["latest_absolute_error_kl"]),
            error_change_kl=cast(float, row["error_change_kl"]),
            wape_contribution_pp=cast(float, row["wape_contribution_pp"]),
            forecast_revision_kl=cast(float, row["forecast_revision_kl"]),
            baseline_direction=_forecast_direction(
                cast(float, row["baseline_forecast_kl"]),
                cast(float, row["actual_kl"]),
            ),
            latest_direction=_forecast_direction(
                cast(float, row["latest_forecast_kl"]),
                cast(float, row["actual_kl"]),
            ),
        )
        for row in target.sort(
            ["error_change_kl", "parent_code"], descending=[True, False]
        ).to_dicts()
    )

    brands_frame = (
        target.group_by("brand", maintain_order=True)
        .agg(
            pl.len().alias("parent_count"),
            pl.col("actual_kl").sum(),
            pl.col("baseline_forecast_kl").sum(),
            pl.col("latest_forecast_kl").sum(),
            pl.col("baseline_absolute_error_kl").sum(),
            pl.col("latest_absolute_error_kl").sum(),
            pl.col("error_change_kl").sum(),
            pl.col("wape_contribution_pp").sum(),
            pl.when(pl.col("error_change_kl") > 0)
            .then(pl.col("error_change_kl"))
            .otherwise(0.0)
            .sum()
            .alias("gross_fix_kl"),
            pl.when(pl.col("wape_contribution_pp") > 0)
            .then(pl.col("wape_contribution_pp"))
            .otherwise(0.0)
            .sum()
            .alias("gross_fix_wape_pp"),
            pl.when(pl.col("error_change_kl") < 0)
            .then(-pl.col("error_change_kl"))
            .otherwise(0.0)
            .sum()
            .alias("regression_kl"),
            pl.when(pl.col("wape_contribution_pp") < 0)
            .then(-pl.col("wape_contribution_pp"))
            .otherwise(0.0)
            .sum()
            .alias("regression_wape_pp"),
        )
        .sort(["error_change_kl", "brand"], descending=[True, False])
        if target.height
        else pl.DataFrame()
    )
    brand_rows = tuple(
        VintageGapBrandRow(
            brand=str(row["brand"]),
            parent_count=cast(int, row["parent_count"]),
            actual_kl=cast(float, row["actual_kl"]),
            baseline_forecast_kl=cast(float, row["baseline_forecast_kl"]),
            latest_forecast_kl=cast(float, row["latest_forecast_kl"]),
            baseline_absolute_error_kl=cast(
                float, row["baseline_absolute_error_kl"]
            ),
            latest_absolute_error_kl=cast(float, row["latest_absolute_error_kl"]),
            error_change_kl=cast(float, row["error_change_kl"]),
            wape_contribution_pp=cast(float, row["wape_contribution_pp"]),
            gross_fix_kl=cast(float, row["gross_fix_kl"]),
            gross_fix_wape_pp=cast(float, row["gross_fix_wape_pp"]),
            regression_kl=cast(float, row["regression_kl"]),
            regression_wape_pp=cast(float, row["regression_wape_pp"]),
        )
        for row in brands_frame.to_dicts()
    )

    baseline_error = sum(row.baseline_absolute_error_kl for row in parent_rows)
    latest_error = sum(row.latest_absolute_error_kl for row in parent_rows)
    gross_fix = sum(max(0.0, row.error_change_kl) for row in parent_rows)
    regression = sum(max(0.0, -row.error_change_kl) for row in parent_rows)
    baseline_wape = 100.0 * baseline_error / denominator if denominator else None
    latest_wape = 100.0 * latest_error / denominator if denominator else None
    net_improvement = (
        100.0 * (baseline_error - latest_error) / denominator
        if denominator
        else None
    )
    return VintageGapDrilldown(
        source=resolved.source,
        target_month=target_month,
        baseline_rule_id=baseline_rule.label,
        baseline_label=_rule_display_label(baseline_rule),
        latest_rule_id=latest_rule.label,
        latest_label=_rule_display_label(latest_rule),
        eligible_parents=len(parent_rows),
        actual_denominator_kl=denominator,
        baseline_absolute_error_kl=baseline_error,
        latest_absolute_error_kl=latest_error,
        baseline_wape_pct=baseline_wape,
        latest_wape_pct=latest_wape,
        net_wape_improvement_pp=net_improvement,
        gross_fix_kl=gross_fix,
        gross_fix_wape_pp=(100.0 * gross_fix / denominator if denominator else None),
        regression_kl=regression,
        regression_wape_pp=(100.0 * regression / denominator if denominator else None),
        brands=brand_rows,
        parents=parent_rows,
    )
