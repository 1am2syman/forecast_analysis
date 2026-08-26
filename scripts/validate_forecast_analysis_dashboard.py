"""Validate the release contract for the forecast-analysis dashboard.

This command is read-only. It loads the approved consolidated history, builds
both standard source views and the aligned comparison view, then checks the
population, metric, quality, empty-state, and download seams used by Marimo.
It intentionally does not start a browser or execute end-to-end tests.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from math import isclose
from pathlib import Path

import polars as pl
from polars.testing import assert_frame_equal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forecast_analysis import (
    DashboardFilters,
    VintageRule,
    build_analysis_dataset,
    build_dashboard_diagnostics,
    build_dashboard_view,
    load_analysis_inputs,
)

FORECAST_HISTORY_PATH = (
    ROOT / "artifacts/forecast_history/consolidated/forecast_history_waterfall.csv"
)
HIERARCHY_PATH = ROOT / "artifacts/ph/PH_FG.xlsx"
ACTUALS_PATH = ROOT / "artifacts/secondary_sales"
DOWNLOAD_COLUMNS = [
    "source",
    "parent_code",
    "parent_description",
    "brand",
    "snop_month",
    "actual_kl",
    "actual_status",
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
]
REQUIRED_DIAGNOSTICS = {
    "forecast_rows_loaded",
    "distinct_source_parent_target_keys",
    "distinct_parent_products",
    "mapped_products",
    "hierarchy_conflict_products",
    "unmapped_products",
    "matched_actual_keys",
    "positive_actual_keys",
    "zero_actual_keys",
    "missing_actual_keys",
    "complete_pairs",
    "incomplete_pairs",
    "actual_population_volume_kl",
}


def check(condition: bool, message: str) -> None:
    """Raise a concise release-validation failure."""
    if not condition:
        raise AssertionError(message)


def _assert_single_source(view, source: str) -> None:
    """Check that a standard view never leaks the opposite source."""
    for name, frame in (
        ("filtered population", view.filtered_population),
        ("vintage pairs", view.vintage_pairs),
        ("coverage pairs", view.coverage_pairs),
        ("monthly performance", view.monthly_performance),
        ("monthly audit", view.monthly_audit),
        ("horizon performance", view.horizon_performance),
        ("horizon audit", view.horizon_audit),
        ("brand-target performance", view.brand_target_month_performance),
        ("download", view.download_frame),
    ):
        if "source" in frame.columns and frame.height:
            check(
                set(frame["source"].drop_nulls().unique().to_list()) == {source},
                f"{name} leaked a source outside {source.upper()}",
            )


def _expected_download_frame(pairs: pl.DataFrame) -> pl.DataFrame:
    """Build download values independently of the production download helper."""
    prepared = pairs.with_columns(
        pl.when(pl.col("mapping_status") == "conflict")
        .then(pl.lit("Hierarchy conflict"))
        .when(pl.col("brand").is_null())
        .then(pl.lit("Unmapped"))
        .otherwise(pl.col("brand"))
        .alias("brand")
    )
    return (
        prepared.select(
            [
                "source",
                "parent_code",
                "parent_description",
                "brand",
                "snop_month",
                "actual_kl",
                "actual_status",
                "vintage_a_calculation_month",
                "vintage_a_horizon_months",
                "vintage_a_forecast_kl",
                "vintage_b_calculation_month",
                "vintage_b_horizon_months",
                "vintage_b_forecast_kl",
                pl.col("vintage_b_absolute_error_kl").alias("absolute_error_b_kl"),
                pl.col("vintage_b_bias_kl").alias("bias_b_kl"),
                "revision_kl",
                "error_improvement_kl",
                "revision_direction",
                "revision_outcome",
                "pair_status",
                "mapping_status",
            ]
        )
        .sort(
            ["absolute_error_b_kl", "snop_month", "parent_code", "source"],
            descending=[True, False, False, False],
            nulls_last=True,
        )
    )


def _assert_download_contract(view) -> None:
    """Check schema, values, and row/key fidelity for the selected-pair download."""
    check(
        view.download_frame.columns == DOWNLOAD_COLUMNS,
        f"download schema changed: {view.download_frame.columns}",
    )
    expected = _expected_download_frame(view.vintage_pairs)
    assert_frame_equal(view.download_frame, expected, check_dtypes=False)
    download_keys = view.download_frame.select(
        ["source", "parent_code", "snop_month"]
    ).unique()
    pair_keys = view.vintage_pairs.select(
        ["source", "parent_code", "snop_month"]
    ).unique()
    assert_frame_equal(
        download_keys.sort(["source", "parent_code", "snop_month"]),
        pair_keys.sort(["source", "parent_code", "snop_month"]),
        check_dtypes=False,
    )


def _assert_exact_horizon_projection(
    frame: pl.DataFrame,
    horizon: int,
    label: str,
) -> None:
    """Ensure an exact-horizon projection never contains another horizon."""
    if frame.height == 0:
        return
    check(
        "forecast_horizon_months" in frame.columns,
        f"{label} omitted its forecast horizon column",
    )
    values = set(frame["forecast_horizon_months"].drop_nulls().unique().to_list())
    check(
        values == {horizon},
        f"{label} contains horizons {sorted(values)} instead of {horizon}",
    )


def _assert_metric_arithmetic(summary, label: str) -> None:
    """Verify every exposed ratio against its independent fields."""
    def ratio(
        value: float | None,
        numerator: float | None,
        denominator: float | None,
        expected: float,
        metric: str,
    ) -> None:
        if denominator in (None, 0):
            check(value is None, f"{label} {metric} is defined without a denominator")
            return
        if numerator is None:
            raise AssertionError(f"{label} {metric} numerator is missing")
        if value is None:
            raise AssertionError(f"{label} {metric} is missing")
        check(
            abs(value - expected) < 1e-8,
            f"{label} {metric} does not match its numerator/denominator",
        )

    ratio(
        summary.forecast_accuracy_pct,
        summary.accuracy_numerator_kl,
        summary.accuracy_denominator_actual_kl,
        (1 - summary.accuracy_numerator_kl / summary.accuracy_denominator_actual_kl) * 100
        if summary.accuracy_numerator_kl is not None
        and summary.accuracy_denominator_actual_kl not in (None, 0)
        else 0.0,
        "accuracy",
    )
    ratio(
        summary.bias_pct,
        summary.bias_numerator_kl,
        summary.bias_denominator_actual_kl,
        summary.bias_numerator_kl / summary.bias_denominator_actual_kl * 100
        if summary.bias_numerator_kl is not None
        and summary.bias_denominator_actual_kl not in (None, 0)
        else 0.0,
        "bias",
    )
    ratio(
        summary.coverage_pct,
        summary.coverage_numerator_actual_kl,
        summary.coverage_denominator_actual_kl,
        summary.coverage_numerator_actual_kl
        / summary.coverage_denominator_actual_kl
        * 100
        if summary.coverage_numerator_actual_kl is not None
        and summary.coverage_denominator_actual_kl not in (None, 0)
        else 0.0,
        "coverage",
    )
    ratio(
        summary.accuracy_delta_pp,
        summary.accuracy_delta_numerator_kl,
        summary.accuracy_delta_denominator_actual_kl,
        summary.accuracy_delta_numerator_kl
        / summary.accuracy_delta_denominator_actual_kl
        * 100
        if summary.accuracy_delta_numerator_kl is not None
        and summary.accuracy_delta_denominator_actual_kl not in (None, 0)
        else 0.0,
        "accuracy delta",
    )
    if summary.effectiveness_denominator:
        check(
            summary.revision_effectiveness_pct is not None
            and abs(
                summary.revision_effectiveness_pct
                - summary.effectiveness_numerator
                / summary.effectiveness_denominator
                * 100
            )
            < 1e-8,
            f"{label} revision effectiveness does not match its counts",
        )
    else:
        check(
            summary.revision_effectiveness_pct is None,
            f"{label} revision effectiveness is defined without materially revised rows",
        )


def _assert_quality_scope(view) -> None:
    """Check active quality counts are keyed to active evidence, not baseline."""
    quality_population = (
        view.comparison.quality_population
        if view.comparison is not None
        else view.filtered_population
    )
    forecast_keys = quality_population.select(
        ["parent_code", "snop_month"]
    ).unique()
    actual_keys = view.selected_actual_population.select(
        ["parent_code", "snop_month"]
    ).unique()
    expected_actual_keys = pl.concat([forecast_keys, actual_keys]).unique()
    check(
        view.quality.hierarchy["observations"].sum() == expected_actual_keys.height,
        "active hierarchy quality counts are not keyed to the active population",
    )
    check(
        view.quality.actual["observations"].sum() == expected_actual_keys.height,
        "active actual quality counts are not keyed to the active population",
    )
    check(
        view.quality.pairs["observations"].sum() == view.vintage_pairs.height,
        "active pair quality counts are not keyed to selected pairs",
    )
    if view.comparison is not None:
        availability_keys = pl.concat(
            [
                view.comparison.common_population,
                view.comparison.tm_only_population,
                view.comparison.ml_only_population,
            ],
            how="vertical_relaxed",
        ).select(["parent_code", "snop_month"]).unique()
    else:
        availability_keys = view.vintage_pairs.select(
            ["parent_code", "snop_month"]
        ).unique()
    check(
        view.quality.source_availability["observations"].sum()
        == availability_keys.height,
        "active source-availability counts are not keyed to active source populations",
    )


def _assert_summary_coverage(summary: dict[str, object], label: str) -> None:
    """Verify the summary's displayed coverage matches its audit fields."""
    denominator = summary.get("coverage_denominator_actual_kl")
    numerator = summary.get("coverage_numerator_actual_kl")
    percentage = summary.get("coverage_pct")
    if denominator in (None, 0):
        check(percentage is None, f"{label} summary coverage has no valid denominator")
        return
    if not isinstance(numerator, (int, float)) or isinstance(numerator, bool):
        raise AssertionError(f"{label} summary coverage numerator is missing")
    if not isinstance(percentage, (int, float)) or isinstance(percentage, bool):
        raise AssertionError(f"{label} summary coverage percentage is missing")
    if not isinstance(denominator, (int, float)) or isinstance(denominator, bool):
        raise AssertionError(f"{label} summary coverage denominator is invalid")
    check(
        abs(percentage - numerator / denominator * 100) < 1e-8,
        f"{label} summary coverage is inconsistent with its audit fields",
    )


def _validate_standard_views(dataset) -> dict[str, object]:
    """Validate TM and ML standard views and their shared summary seam."""
    views = {}
    for source in ("tm", "ml"):
        view = build_dashboard_view(
            dataset.frame,
            dataset.actual_population,
            DashboardFilters(source=source),
            hierarchy_diagnostics=dataset.hierarchy_diagnostics,
        )
        views[source] = view
        _assert_single_source(view, source)
        _assert_download_contract(view)
        _assert_metric_arithmetic(view.metrics, source.upper())
        _assert_quality_scope(view)
        check(view.population_summary.height == 1, f"{source} summary is not singular")
        summary = view.population_summary.row(0, named=True)
        check(summary["mode"] == "single_source", f"{source} mode is not single_source")
        check(summary["sources"] == source.upper(), f"{source} summary source mismatch")
        check(summary["comparable_pairs"] == view.metrics.complete_pairs, f"{source} pair count mismatch")
        check(
            summary["eligible_observations"] == view.metrics.eligible_observations,
            f"{source} eligible count mismatch",
        )
        _assert_summary_coverage(summary, source.upper())
    check(
        views["tm"].metrics.forecast_kl != views["ml"].metrics.forecast_kl,
        "TM and ML standard metrics unexpectedly match on the release population",
    )
    return views


def _validate_comparison_view(dataset):
    """Validate aligned comparison values, source coverage, and warnings."""
    view = build_dashboard_view(
        dataset.frame,
        dataset.actual_population,
        DashboardFilters(comparison_mode=True),
        hierarchy_diagnostics=dataset.hierarchy_diagnostics,
    )
    comparison = view.comparison
    check(comparison is not None, "comparison view was not constructed")
    if comparison is None:
        raise AssertionError("comparison view was not constructed")
    check(not comparison.blocked, f"default comparison is blocked: {comparison.warning}")
    if comparison.selected_horizon is None:
        raise AssertionError("default comparison has no horizon")
    for name, frame in (
        ("comparison filtered population", view.filtered_population),
        ("comparison pairs", view.vintage_pairs),
        ("comparison monthly performance", view.monthly_performance),
        ("comparison monthly audit", view.monthly_audit),
        ("comparison horizon performance", view.horizon_performance),
        ("comparison horizon audit", view.horizon_audit),
        ("comparison heatmap", view.brand_target_month_performance),
        ("comparison download", view.download_frame),
    ):
        if "source" in frame.columns and frame.height:
            check(
                set(frame["source"].drop_nulls().unique().to_list()) <= {"tm", "ml"},
                f"{name} contains an unknown source",
            )
    _assert_download_contract(view)
    _assert_metric_arithmetic(comparison.tm_metrics, "TM comparison")
    _assert_metric_arithmetic(comparison.ml_metrics, "ML comparison")
    _assert_metric_arithmetic(comparison.common_metrics, "common comparison")
    _assert_quality_scope(view)
    summary = view.population_summary.row(0, named=True)
    check(summary["mode"] == "comparison", "comparison summary mode mismatch")
    _assert_summary_coverage(summary, "common comparison")
    check(comparison.tm_metrics is not comparison.ml_metrics, "comparison metrics are not source-specific objects")
    check(comparison.source_metrics["source"].to_list() == ["tm", "ml"], "comparison source metric order changed")
    for source, metric in (("tm", comparison.tm_metrics), ("ml", comparison.ml_metrics)):
        _assert_summary_coverage(
            {
                "coverage_pct": summary[f"{source}_coverage_pct"],
                "coverage_numerator_actual_kl": summary[f"{source}_coverage_numerator_actual_kl"],
                "coverage_denominator_actual_kl": summary[f"{source}_coverage_denominator_actual_kl"],
            },
            f"{source.upper()} comparison",
        )
        check(
            summary[f"{source}_eligible_observations"] == metric.eligible_observations,
            f"{source.upper()} comparison eligible count mismatch",
        )
        summary_coverage = summary[f"{source}_coverage_pct"]
        metric_coverage = metric.coverage_pct
        if not isinstance(summary_coverage, (int, float)) or isinstance(
            summary_coverage, bool
        ):
            raise AssertionError(f"{source.upper()} comparison coverage summary is missing")
        if not isinstance(metric_coverage, (int, float)) or isinstance(
            metric_coverage, bool
        ):
            raise AssertionError(f"{source.upper()} comparison coverage metric is missing")
        check(
            abs(summary_coverage - metric_coverage) < 1e-8,
            f"{source.upper()} comparison coverage summary mismatch",
        )
    check(comparison.paired_comparison.height == comparison.comparable_pairs, "comparison pair count mismatch")
    for projection_name, projection in (
        ("comparison filtered population", view.filtered_population),
        ("comparison common population", comparison.common_population),
        ("comparison TM-only population", comparison.tm_only_population),
        ("comparison ML-only population", comparison.ml_only_population),
        ("comparison horizon performance", view.horizon_performance),
        ("comparison horizon audit", view.horizon_audit),
    ):
        _assert_exact_horizon_projection(
            projection,
            comparison.selected_horizon,
            projection_name,
        )
    check(
        summary["forecast_rows"] == view.filtered_population.height,
        "comparison summary forecast rows are not the exact-horizon population",
    )

    blocked = build_dashboard_view(
        dataset.frame,
        dataset.actual_population,
        DashboardFilters(comparison_mode=True, comparison_horizon=10_000),
        hierarchy_diagnostics=dataset.hierarchy_diagnostics,
    )
    blocked_comparison = blocked.comparison
    check(
        blocked_comparison is not None and blocked_comparison.blocked,
        "unavailable comparison horizon did not block",
    )
    if blocked_comparison is not None:
        check(
            "selected exact horizon" in (blocked_comparison.warning or ""),
            "blocked comparison warning did not explain the requested horizon",
        )
    return view


@dataclass(frozen=True)
class _CanonicalForecastRow:
    """Typed raw row used by the independent real-input validator oracle."""

    source: str
    parent_code: int
    parent_description: str
    brand: str | None
    mapping_status: str
    calculation_month: date
    snop_month: date
    horizon: int
    forecast_kl: float
    actual_kl: float | None
    actual_status: str


@dataclass(frozen=True)
class _RevisionCase:
    """One deterministic real-input product-target case."""

    parent_code: int
    target_month: date
    rows: list[_CanonicalForecastRow]
    actual_kl: float
    brand: str | None
    horizon: int
    revision_direction: str
    forecast_direction: str


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise AssertionError(f"{label} is not text")
    return value


def _required_date(value: object, label: str) -> date:
    if not isinstance(value, date):
        raise AssertionError(f"{label} is not a date")
    return value


def _required_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AssertionError(f"{label} is not an integer")
    return value


def _required_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AssertionError(f"{label} is not numeric")
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AssertionError(f"{label} is not numeric") from exc


def _canonical_forecast_row(row: dict[str, object]) -> _CanonicalForecastRow:
    actual = row.get("actual_kl")
    actual_kl = None if actual is None else _required_float(actual, "actual_kl")
    brand = row.get("brand")
    if brand is not None and not isinstance(brand, str):
        raise AssertionError("selected validator brand is not text")
    return _CanonicalForecastRow(
        source=_required_text(row.get("source"), "source"),
        parent_code=_required_int(row.get("parent_code"), "parent_code"),
        parent_description=_required_text(
            row.get("parent_description"), "parent_description"
        ),
        brand=brand,
        mapping_status=_required_text(row.get("mapping_status"), "mapping_status"),
        calculation_month=_required_date(
            row.get("calculation_month"), "calculation_month"
        ),
        snop_month=_required_date(row.get("snop_month"), "snop_month"),
        horizon=_required_int(row.get("forecast_horizon_months"), "forecast_horizon_months"),
        forecast_kl=_required_float(row.get("forecast_kl"), "forecast_kl"),
        actual_kl=actual_kl,
        actual_status=_required_text(row.get("actual_status"), "actual_status"),
    )


def _revision_case(dataset, source: str) -> _RevisionCase:
    """Find the first real-input key with positive actual and two vintages."""
    source_frame = dataset.frame.filter(pl.col("source") == source)
    groups = (
        source_frame.select(["parent_code", "snop_month"])
        .unique()
        .sort(["parent_code", "snop_month"])
        .iter_rows(named=True)
    )
    fallback: _RevisionCase | None = None
    for key in groups:
        rows = [
            _canonical_forecast_row(row)
            for row in (
                source_frame.filter(
                    (pl.col("parent_code") == key["parent_code"])
                    & (pl.col("snop_month") == key["snop_month"])
                )
                .sort("calculation_month")
                .to_dicts()
            )
        ]
        latest_actual = rows[-1].actual_kl
        if len(rows) < 2 or latest_actual is None or latest_actual <= 0:
            continue
        delta = rows[-1].forecast_kl - rows[0].forecast_kl
        revision_direction = (
            "up" if delta > 0.01 else "down" if delta < -0.01 else "unchanged"
        )
        forecast_delta = rows[-1].forecast_kl - latest_actual
        forecast_direction = (
            "over"
            if forecast_delta > 0.01
            else "under"
            if forecast_delta < -0.01
            else "within_tolerance"
        )
        case = _RevisionCase(
            parent_code=rows[-1].parent_code,
            target_month=rows[-1].snop_month,
            rows=rows,
            actual_kl=latest_actual,
            brand=rows[-1].brand,
            horizon=rows[-1].horizon,
            revision_direction=revision_direction,
            forecast_direction=forecast_direction,
        )
        if fallback is None:
            fallback = case
        if revision_direction != "unchanged":
            return case
    if fallback is None:
        raise AssertionError(f"no usable two-vintage {source.upper()} real-input key found")
    return fallback


def _expected_pair_from_canonical(case: _RevisionCase) -> dict[str, object]:
    """Derive oldest/latest values without calling the pair projection."""
    oldest = case.rows[0]
    latest = case.rows[-1]
    revision = latest.forecast_kl - oldest.forecast_kl
    improvement = abs(oldest.forecast_kl - case.actual_kl) - abs(
        latest.forecast_kl - case.actual_kl
    )
    return {
        "source": latest.source,
        "parent_code": latest.parent_code,
        "parent_description": latest.parent_description,
        "brand": (
            "Hierarchy conflict"
            if latest.mapping_status == "conflict"
            else "Unmapped"
            if latest.brand is None
            else latest.brand
        ),
        "snop_month": latest.snop_month,
        "actual_kl": case.actual_kl,
        "actual_status": latest.actual_status,
        "vintage_a_calculation_month": oldest.calculation_month,
        "vintage_a_horizon_months": oldest.horizon,
        "vintage_a_forecast_kl": oldest.forecast_kl,
        "vintage_b_calculation_month": latest.calculation_month,
        "vintage_b_horizon_months": latest.horizon,
        "vintage_b_forecast_kl": latest.forecast_kl,
        "absolute_error_b_kl": abs(latest.forecast_kl - case.actual_kl),
        "bias_b_kl": latest.forecast_kl - case.actual_kl,
        "revision_kl": revision,
        "error_improvement_kl": improvement,
        "revision_direction": (
            "up" if revision > 0.01 else "down" if revision < -0.01 else "unchanged"
        ),
        "revision_outcome": (
            "improved" if improvement > 0.01 else "worsened" if improvement < -0.01 else "neutral"
        ),
        "pair_status": "complete",
        "mapping_status": latest.mapping_status,
    }


def _comparison_pair_status_facts(
    dataset,
    horizon: int,
    pair_status: str,
) -> tuple[set[tuple[str, int, date]], set[tuple[int, date]]]:
    """Derive comparison pair keys from raw rows without pair projections."""
    actual_by_key = {
        (
            _required_int(row.get("parent_code"), "actual parent code"),
            _required_date(row.get("snop_month"), "actual target month"),
        ): row.get("actual_kl")
        for row in dataset.actual_population.to_dicts()
    }
    source_keys = {
        (
            _required_text(row.get("source"), "comparison source"),
            _required_int(row.get("parent_code"), "comparison parent code"),
            _required_date(row.get("snop_month"), "comparison target month"),
        )
        for row in dataset.frame.to_dicts()
    }
    exact_keys = {
        (
            _required_text(row.get("source"), "exact comparison source"),
            _required_int(row.get("parent_code"), "exact comparison parent code"),
            _required_date(row.get("snop_month"), "exact comparison target month"),
        )
        for row in dataset.frame.filter(
            pl.col("forecast_horizon_months") == horizon
        ).to_dicts()
    }
    surviving_source_keys: set[tuple[str, int, date]] = set()
    for source, parent_code, target_month in source_keys:
        key = (parent_code, target_month)
        actual = actual_by_key.get(key)
        derived_status = (
            "missing_both"
            if (source, parent_code, target_month) not in exact_keys
            else "missing_actual"
            if actual is None
            else "zero_actual"
            if actual == 0
            else "complete"
        )
        if derived_status == pair_status:
            surviving_source_keys.add((source, parent_code, target_month))
    return surviving_source_keys, {
        (source_key[1], source_key[2]) for source_key in surviving_source_keys
    }


def _source_availability_records(
    source_keys: set[tuple[str, int, date]],
) -> set[tuple[int, date, str]]:
    """Classify source composition directly from source-specific key facts."""
    sources_by_key: dict[tuple[int, date], set[str]] = {}
    for source, parent_code, target_month in source_keys:
        sources_by_key.setdefault((parent_code, target_month), set()).add(source)
    records: set[tuple[int, date, str]] = set()
    for (parent_code, target_month), sources in sources_by_key.items():
        status = (
            "both_sources"
            if sources == {"tm", "ml"}
            else "tm_only"
            if sources == {"tm"}
            else "ml_only"
        )
        records.add((parent_code, target_month, status))
    return records


def _baseline_source_availability_records(
    dataset,
    horizon: int,
) -> set[tuple[int, date, str]]:
    """Derive ordinary active-horizon availability without dashboard outputs."""
    source_keys = {
        (
            _required_text(row.get("source"), "baseline availability source"),
            _required_int(row.get("parent_code"), "baseline availability parent code"),
            _required_date(row.get("snop_month"), "baseline availability target month"),
        )
        for row in dataset.frame.filter(
            pl.col("forecast_horizon_months") == horizon
        ).to_dicts()
    }
    return _source_availability_records(source_keys)


def _comparison_metric_facts(
    dataset,
    horizon: int,
    source_keys: set[tuple[str, int, date]],
) -> dict[str, dict[str, float | int | None]]:
    """Calculate common-source metric inputs directly from canonical rows."""
    actual_by_key = {
        (row["parent_code"], row["snop_month"]): row["actual_kl"]
        for row in dataset.actual_population.to_dicts()
    }
    exact_rows = {
        (row["source"], row["parent_code"], row["snop_month"]): row
        for row in dataset.frame.filter(
            pl.col("forecast_horizon_months") == horizon
        ).to_dicts()
    }
    source_key_sets = {
        source: {
            (parent_code, target_month)
            for current_source, parent_code, target_month in source_keys
            if current_source == source
        }
        for source in ("tm", "ml")
    }
    common_keys = source_key_sets["tm"] & source_key_sets["ml"]
    facts: dict[str, dict[str, float | int | None]] = {}
    for source in ("tm", "ml"):
        values = []
        for parent_code, target_month in common_keys:
            actual = actual_by_key.get((parent_code, target_month))
            row = exact_rows.get((source, parent_code, target_month))
            if actual is None or actual <= 0 or row is None:
                continue
            forecast = _required_float(row.get("forecast_kl"), "comparison forecast_kl")
            actual_value = _required_float(actual, "comparison actual_kl")
            values.append((forecast, actual_value))
        actual_total = sum(actual for _, actual in values)
        forecast_total = sum(forecast for forecast, _ in values)
        absolute_error = sum(abs(forecast - actual) for forecast, actual in values)
        bias = sum(forecast - actual for forecast, actual in values)
        facts[source] = {
            "eligible_observations": len(values),
            "actual_kl": actual_total if values else None,
            "forecast_kl": forecast_total if values else None,
            "absolute_error_kl": absolute_error if values else None,
            "bias_numerator_kl": bias if values else None,
        }
    return facts


def _assert_real_comparison_pair_status_scope(
    dataset,
    selected_status: str,
) -> None:
    """Check one filtered comparison scope against independently derived facts."""
    horizon = 1
    expected_source_keys, expected_union_keys = _comparison_pair_status_facts(
        dataset,
        horizon,
        selected_status,
    )
    exact_source_keys = {
        (
            _required_text(row.get("source"), "exact comparison source"),
            _required_int(row.get("parent_code"), "exact comparison parent code"),
            _required_date(row.get("snop_month"), "exact comparison target month"),
        )
        for row in dataset.frame.filter(
            pl.col("forecast_horizon_months") == horizon
        ).to_dicts()
    }
    expected_visible_source_keys = expected_source_keys & exact_source_keys
    expected_visible_keys = {
        (source_key[1], source_key[2])
        for source_key in expected_visible_source_keys
    }
    check(
        bool(expected_source_keys),
        f"real comparison {selected_status} has no canonical source keys",
    )
    view = build_dashboard_view(
        dataset.frame,
        dataset.actual_population,
        DashboardFilters(
            comparison_mode=True,
            horizons=(horizon,),
            pair_statuses=(selected_status,),
        ),
        hierarchy_diagnostics=dataset.hierarchy_diagnostics,
    )
    actual_source_keys = set(
        view.vintage_pairs.select(
            ["source", "parent_code", "snop_month"]
        ).iter_rows()
    )
    actual_visible_source_keys = set(
        view.filtered_population.select(
            ["source", "parent_code", "snop_month"]
        ).iter_rows()
    )
    actual_visible_keys = set(
        view.filtered_population.select(
            ["parent_code", "snop_month"]
        ).unique().iter_rows()
    )
    actual_selected_keys = set(
        view.selected_actual_population.select(
            ["parent_code", "snop_month"]
        ).unique().iter_rows()
    )
    check(
        actual_source_keys == expected_source_keys,
        f"real comparison {selected_status} pair keys diverged from canonical rows",
    )
    check(
        actual_visible_source_keys == expected_visible_source_keys,
        f"real comparison {selected_status} visible exact-horizon source keys diverged",
    )
    check(
        actual_visible_keys == expected_visible_keys,
        f"real comparison {selected_status} visible exact-horizon product keys diverged",
    )
    actual_by_key = {
        (row["parent_code"], row["snop_month"]): row["actual_kl"]
        for row in dataset.actual_population.to_dicts()
    }
    expected_actual_keys = expected_union_keys & set(actual_by_key)
    expected_actual_volume = sum(
        _required_float(actual_by_key[key], "comparison actual_kl")
        for key in expected_actual_keys
        if actual_by_key[key] is not None
    )
    expected_tm_keys = {
        (parent_code, target_month)
        for source, parent_code, target_month in expected_source_keys
        if source == "tm"
    }
    expected_ml_keys = {
        (parent_code, target_month)
        for source, parent_code, target_month in expected_source_keys
        if source == "ml"
    }
    expected_common_keys = expected_tm_keys & expected_ml_keys
    exact_tm_keys = {
        (parent_code, target_month)
        for source, parent_code, target_month in exact_source_keys
        if source == "tm"
    }
    exact_ml_keys = {
        (parent_code, target_month)
        for source, parent_code, target_month in exact_source_keys
        if source == "ml"
    }
    expected_common_coverage_keys = (
        expected_common_keys & exact_tm_keys & exact_ml_keys
    )
    expected_availability_records = _source_availability_records(
        expected_source_keys
    )
    expected_availability_counts = {
        status: sum(
            record[2] == status for record in expected_availability_records
        )
        for status in ("tm_only", "ml_only", "both_sources")
    }
    expected_common_coverage_actual_keys = (
        expected_common_coverage_keys & set(actual_by_key)
    )
    expected_common_actual = sum(
        _required_float(actual_by_key[key], "common comparison actual_kl")
        for key in expected_common_coverage_actual_keys
        if actual_by_key[key] is not None
    )
    check(
        actual_selected_keys == expected_actual_keys,
        f"real comparison {selected_status} selected actual keys diverged",
    )
    check(
        view.filtered_population.height
        == len(view.filtered_population.select(
            ["source", "parent_code", "snop_month"]
        ).unique()),
        f"real comparison {selected_status} visible population has duplicate source keys",
    )
    for projection_name, projection in (
        ("filtered population", view.filtered_population),
        ("common population", view.comparison.common_population if view.comparison else view.filtered_population),
        ("TM-only population", view.comparison.tm_only_population if view.comparison else view.filtered_population),
        ("ML-only population", view.comparison.ml_only_population if view.comparison else view.filtered_population),
        ("horizon performance", view.horizon_performance),
        ("horizon audit", view.horizon_audit),
    ):
        _assert_exact_horizon_projection(projection, horizon, f"real comparison {selected_status} {projection_name}")
    if selected_status == "missing_both":
        for projection_name, projection in (
            ("filtered population", view.filtered_population),
            ("common population", view.comparison.common_population if view.comparison else view.filtered_population),
            ("TM-only population", view.comparison.tm_only_population if view.comparison else view.filtered_population),
            ("ML-only population", view.comparison.ml_only_population if view.comparison else view.filtered_population),
            ("monthly performance", view.monthly_performance),
            ("monthly audit", view.monthly_audit),
            ("horizon performance", view.horizon_performance),
            ("horizon audit", view.horizon_audit),
            ("brand-target performance", view.brand_target_month_performance),
            ("paired comparison", view.comparison.paired_comparison if view.comparison else view.filtered_population),
        ):
            check(
                projection.height == 0,
                f"real comparison missing_both {projection_name} should be empty",
            )
        if view.comparison is not None:
            check(
                view.comparison.vintage_pairs.height == len(expected_source_keys),
                "real comparison missing_both pair evidence should remain",
            )
            check(
                view.comparison.quality_population.height == len(expected_source_keys),
                "real comparison missing_both quality evidence should remain",
            )
            check(
                view.comparison.source_metrics.filter(
                    pl.col("population_observations") > 0
                ).height == 0,
                "real comparison missing_both source metric population should be empty",
            )
            for source, metric in (
                ("tm", view.comparison.tm_metrics),
                ("ml", view.comparison.ml_metrics),
            ):
                check(
                    metric.population_observations == 0
                    and metric.eligible_observations == 0
                    and metric.forecast_kl is None
                    and metric.actual_kl is None
                    and metric.absolute_error_kl is None,
                    f"real comparison missing_both {source.upper()} source metrics should be empty",
                )
    check(
        view.quality.hierarchy["observations"].sum() == len(expected_union_keys),
        f"real comparison {selected_status} hierarchy scope diverged",
    )
    check(
        view.quality.actual["observations"].sum() == len(expected_union_keys),
        f"real comparison {selected_status} actual scope diverged",
    )
    check(
        view.quality.pairs["observations"].sum() == len(expected_source_keys),
        f"real comparison {selected_status} pair quality scope diverged",
    )
    check(
        view.quality.source_availability["observations"].sum()
        == len(expected_union_keys),
        f"real comparison {selected_status} availability scope diverged",
    )
    actual_availability_counts = {
        row["status"]: row["observations"]
        for row in view.quality.source_availability.to_dicts()
    }
    check(
        actual_availability_counts == expected_availability_counts,
        f"real comparison {selected_status} availability categories diverged",
    )
    check(view.comparison is not None, "real comparison view is unavailable")
    if view.comparison is not None:
        quality_source_keys = set(
            view.comparison.quality_population.select(
                ["source", "parent_code", "snop_month"]
            ).iter_rows()
        )
        check(
            quality_source_keys == expected_source_keys,
            f"real comparison {selected_status} quality source keys diverged",
        )
        check(
            {
                row["status"]: row["observations"]
                for row in view.comparison.population_summary.to_dicts()
            }
            == expected_availability_counts,
            f"real comparison {selected_status} population categories diverged",
        )
        if selected_status == "missing_both":
            check(
                view.comparison.quality_population["forecast_kl"].null_count()
                == view.comparison.quality_population.height,
                "real comparison missing_both quality evidence contains a forecast",
            )
            for source, metric in (
                ("tm", view.comparison.tm_metrics),
                ("ml", view.comparison.ml_metrics),
            ):
                check(
                    metric.population_observations == 0
                    and metric.forecast_kl is None
                    and metric.absolute_error_kl is None,
                    f"real comparison missing_both {source.upper()} metrics are not empty",
                )
    download_keys = set(
        view.download_frame.select(
            ["source", "parent_code", "snop_month"]
        ).iter_rows()
    )
    check(
        download_keys == expected_source_keys,
        f"real comparison {selected_status} download keys diverged",
    )

    baseline_source_keys = {
        (
            _required_text(row.get("source"), "baseline comparison source"),
            _required_int(row.get("parent_code"), "baseline comparison parent code"),
            _required_date(row.get("snop_month"), "baseline comparison target month"),
        )
        for row in dataset.frame.to_dicts()
    }
    expected_excluded_pair_keys = baseline_source_keys - expected_source_keys
    actual_excluded_pair_keys = set(
        view.quality.scope_exclusions["pairs"]
        .select(["source", "parent_code", "snop_month"])
        .iter_rows()
    )
    check(
        actual_excluded_pair_keys == expected_excluded_pair_keys,
        f"real comparison {selected_status} pair baseline partition diverged",
    )
    check(
        bool(expected_excluded_pair_keys)
        and expected_source_keys | expected_excluded_pair_keys == baseline_source_keys,
        f"real comparison {selected_status} pair baseline partition is vacuous",
    )
    baseline_availability_records = _baseline_source_availability_records(
        dataset,
        horizon,
    )
    expected_excluded_availability = (
        baseline_availability_records - expected_availability_records
    )
    actual_excluded_availability = set(
        view.quality.scope_exclusions["source_availability"]
        .select(["parent_code", "snop_month", "source_availability"])
        .iter_rows()
    )
    check(
        actual_excluded_availability == expected_excluded_availability,
        f"real comparison {selected_status} availability baseline partition diverged",
    )
    check(
        bool(expected_excluded_availability),
        f"real comparison {selected_status} availability baseline partition is vacuous",
    )
    summary = view.population_summary.row(0, named=True)
    check(
        summary["products"] == len({key[0] for key in expected_visible_keys}),
        "real comparison summary exact-horizon product scope diverged",
    )
    check(
        summary["forecast_rows"] == view.filtered_population.height,
        "real comparison summary exact-horizon forecast scope diverged",
    )
    check(
        summary["selected_pair_rows"] == len(expected_source_keys),
        "real comparison summary pair scope diverged",
    )
    check(
        summary["coverage_pair_rows"] == len(expected_source_keys),
        "real comparison summary coverage scope diverged",
    )
    summary_actual_volume = summary["actual_volume_kl"]
    if expected_actual_keys:
        check(
            summary_actual_volume is not None
            and isclose(summary_actual_volume, expected_actual_volume, abs_tol=1e-8),
            "real comparison summary actual volume diverged",
        )
    else:
        check(
            summary_actual_volume is None,
            "real comparison summary actual volume should be empty",
        )
    check(
        summary["comparable_pairs"] == len(expected_common_coverage_keys),
        "real comparison summary exact-horizon common-pair scope diverged",
    )
    summary_coverage_numerator = summary["coverage_numerator_actual_kl"]
    if expected_actual_keys:
        check(
            summary_coverage_numerator is not None
            and isclose(
                summary_coverage_numerator,
                expected_common_actual,
                abs_tol=1e-8,
            ),
            "real comparison summary common coverage numerator diverged",
        )
    else:
        check(
            summary_coverage_numerator is None,
            "real comparison summary common coverage numerator should be empty",
        )
    summary_coverage_denominator = summary["coverage_denominator_actual_kl"]
    if expected_actual_keys:
        check(
            summary_coverage_denominator is not None
            and isclose(
                summary_coverage_denominator,
                expected_actual_volume,
                abs_tol=1e-8,
            ),
            "real comparison summary coverage denominator diverged",
        )
    else:
        check(
            summary_coverage_denominator is None,
            "real comparison summary coverage denominator should be empty",
        )
    check(
        view.comparison is not None
        and view.comparison.population_summary["observations"].sum()
        == len(expected_union_keys),
        f"real comparison {selected_status} population summary scope diverged",
    )
    expected_metric_facts = _comparison_metric_facts(
        dataset,
        horizon,
        expected_source_keys,
    )
    if view.comparison is not None:
        for source, metric in (
            ("tm", view.comparison.tm_metrics),
            ("ml", view.comparison.ml_metrics),
        ):
            facts = expected_metric_facts[source]
            check(
                metric.eligible_observations == facts["eligible_observations"],
                f"real comparison {selected_status} {source.upper()} eligible count diverged",
            )
            for field in (
                "actual_kl",
                "forecast_kl",
                "absolute_error_kl",
                "bias_numerator_kl",
            ):
                actual_value = (
                    metric.bias_numerator_kl
                    if field == "bias_numerator_kl"
                    else getattr(metric, field)
                )
                expected_value = facts[field]
                if expected_value is None:
                    check(
                        actual_value is None,
                        f"real comparison {selected_status} {source.upper()} {field} should be empty",
                    )
                else:
                    check(
                        actual_value is not None
                        and isclose(actual_value, expected_value, abs_tol=1e-8),
                        f"real comparison {selected_status} {source.upper()} {field} diverged",
                    )
            source_key_set = {
                (parent_code, target_month)
                for current_source, parent_code, target_month in expected_source_keys
                if current_source == source
            }
            represented_actual = sum(
                _required_float(actual_by_key[key], "source coverage actual_kl")
                for key in source_key_set
                if actual_by_key.get(key) is not None
            )
            expected_coverage_numerator = (
                0.0 if selected_status == "missing_both" else represented_actual
            )
            expected_coverage_denominator = (
                expected_actual_volume if expected_actual_keys else None
            )
            if expected_coverage_denominator is None:
                check(
                    metric.coverage_denominator_actual_kl is None,
                    f"real comparison {selected_status} {source.upper()} coverage denominator should be empty",
                )
            else:
                check(
                    metric.coverage_denominator_actual_kl is not None
                    and isclose(
                        metric.coverage_denominator_actual_kl,
                        expected_coverage_denominator,
                        abs_tol=1e-8,
                    ),
                    f"real comparison {selected_status} {source.upper()} coverage denominator diverged",
                )
            if expected_coverage_denominator is None:
                check(
                    metric.coverage_numerator_actual_kl is None,
                    f"real comparison {selected_status} {source.upper()} coverage numerator should be empty",
                )
            else:
                check(
                    metric.coverage_numerator_actual_kl is not None
                    and isclose(
                        metric.coverage_numerator_actual_kl,
                        expected_coverage_numerator,
                        abs_tol=1e-8,
                    ),
                    f"real comparison {selected_status} {source.upper()} coverage numerator diverged",
                )
    for name, frame in (
        ("monthly performance", view.monthly_performance),
        ("horizon performance", view.horizon_performance),
        ("brand-target performance", view.brand_target_month_performance),
    ):
        if frame.height and all(column in frame.columns for column in ("parent_code", "snop_month")):
            frame_keys = set(frame.select(["parent_code", "snop_month"]).unique().iter_rows())
            check(
                frame_keys <= expected_union_keys,
                f"real comparison {selected_status} {name} leaked inactive keys",
            )


def _validate_real_input_filters(dataset) -> None:
    """Exercise deterministic non-default scopes and compare against raw facts."""
    status_order = (
        "complete",
        "missing_a",
        "missing_b",
        "missing_both",
        "missing_actual",
        "zero_actual",
    )
    populated_statuses = []
    for pair_status in status_order:
        expected_source_keys, _ = _comparison_pair_status_facts(
            dataset,
            1,
            pair_status,
        )
        if expected_source_keys:
            _assert_real_comparison_pair_status_scope(dataset, pair_status)
            populated_statuses.append(pair_status)
    check(
        bool(populated_statuses),
        "no usable real-input comparison pair status found",
    )
    check(
        "missing_both" in populated_statuses,
        "real-input comparison missing_both status must be validated",
    )
    case = _revision_case(dataset, "tm")
    target_month = case.target_month
    parent_code = case.parent_code
    actual_kl = case.actual_kl
    brand = case.brand or "Unmapped"
    filtered = build_dashboard_view(
        dataset.frame,
        dataset.actual_population,
        DashboardFilters(
            source="tm",
            target_months=(target_month,),
            brands=(brand,),
            parent_codes=(parent_code,),
            minimum_actual_volume=actual_kl,
            revision_directions=(case.revision_direction,),
            forecast_directions=(case.forecast_direction,),
        ),
        hierarchy_diagnostics=dataset.hierarchy_diagnostics,
    )
    check(filtered.vintage_pairs.height == 1, "real-input filtered TM case is not singular")
    expected_pair = _expected_pair_from_canonical(case)
    actual_pair = filtered.download_frame.row(0, named=True)
    for column in DOWNLOAD_COLUMNS:
        check(
            actual_pair[column] == expected_pair[column],
            f"filtered TM download value mismatch for {column}",
        )
    _assert_single_source(filtered, "tm")
    _assert_download_contract(filtered)
    _assert_metric_arithmetic(filtered.metrics, "filtered TM")
    _assert_quality_scope(filtered)

    ml_case = _revision_case(dataset, "ml")
    ml_filtered = build_dashboard_view(
        dataset.frame,
        dataset.actual_population,
        DashboardFilters(
            source="ml",
            target_months=(ml_case.target_month,),
            brands=(ml_case.brand or "Unmapped",),
            parent_codes=(ml_case.parent_code,),
            minimum_actual_volume=ml_case.actual_kl,
            revision_directions=(ml_case.revision_direction,),
            forecast_directions=(ml_case.forecast_direction,),
        ),
        hierarchy_diagnostics=dataset.hierarchy_diagnostics,
    )
    check(ml_filtered.vintage_pairs.height == 1, "real-input filtered ML case is not singular")
    ml_actual_pair = ml_filtered.download_frame.row(0, named=True)
    for column in DOWNLOAD_COLUMNS:
        check(
            ml_actual_pair[column] == _expected_pair_from_canonical(ml_case)[column],
            f"filtered ML download value mismatch for {column}",
        )
    _assert_single_source(ml_filtered, "ml")
    _assert_download_contract(ml_filtered)
    _assert_metric_arithmetic(ml_filtered.metrics, "filtered ML")
    _assert_quality_scope(ml_filtered)

    quality_status = "unmapped"
    if not dataset.frame.filter(pl.col("mapping_status") == quality_status).height:
        quality_status = "mapped"
    quality_view = build_dashboard_view(
        dataset.frame,
        dataset.actual_population,
        DashboardFilters(source="tm", hierarchy_statuses=(quality_status,)),
        hierarchy_diagnostics=dataset.hierarchy_diagnostics,
    )
    expected_quality_keys = (
        dataset.frame.filter(
            (pl.col("source") == "tm")
            & (pl.col("mapping_status") == quality_status)
        )
        .select(["parent_code", "snop_month"])
        .unique()
    )
    actual_quality_keys = quality_view.filtered_population.select(
        ["parent_code", "snop_month"]
    ).unique()
    assert_frame_equal(
        actual_quality_keys.sort(["parent_code", "snop_month"]),
        expected_quality_keys.sort(["parent_code", "snop_month"]),
        check_dtypes=False,
    )
    _assert_quality_scope(quality_view)
    check(
        quality_view.quality.hierarchy.filter(pl.col("status") != quality_status)[
            "observations"
        ].sum()
        == 0,
        "quality-filtered hierarchy counts contain inactive statuses",
    )

    horizon = case.horizon
    horizon_view = build_dashboard_view(
        dataset.frame,
        dataset.actual_population,
        DashboardFilters(
            source="tm",
            target_months=(target_month,),
            parent_codes=(parent_code,),
            horizons=(horizon,),
        ),
        vintage_a=VintageRule.specific_horizon(horizon),
        vintage_b=VintageRule.specific_horizon(horizon),
        hierarchy_diagnostics=dataset.hierarchy_diagnostics,
    )
    check(
        horizon_view.filtered_population.height > 0,
        "real-input exact-horizon filter produced no rows",
    )
    check(
        set(horizon_view.filtered_population["forecast_horizon_months"].to_list()) == {horizon},
        "real-input exact-horizon filter leaked another horizon",
    )
    _assert_single_source(horizon_view, "tm")

    positive_zero_candidates = (
        dataset.actual_population.filter(pl.col("actual_kl") == 0)
        .join(
            dataset.frame.filter(pl.col("source") == "tm").select(
                ["parent_code", "snop_month"]
            ).unique(),
            on=["parent_code", "snop_month"],
            how="inner",
        )
        .sort(["parent_code", "snop_month"])
    )
    if positive_zero_candidates.height:
        zero_case = positive_zero_candidates.row(0, named=True)
        zero_target_month = _required_date(
            zero_case["snop_month"], "zero-case target month"
        )
        zero_parent_code = _required_int(
            zero_case["parent_code"], "zero-case parent code"
        )
        zero_view = build_dashboard_view(
            dataset.frame,
            dataset.actual_population,
            DashboardFilters(
                source="tm",
                target_months=(zero_target_month,),
                parent_codes=(zero_parent_code,),
                actual_statuses=("matched_zero",),
            ),
            hierarchy_diagnostics=dataset.hierarchy_diagnostics,
        )
        check(zero_view.metrics.coverage_denominator_actual_kl == 0.0, "zero-actual denominator is not zero")
        check(zero_view.metrics.coverage_pct is None, "zero-actual coverage should be undefined")
        check(zero_view.metrics.forecast_accuracy_pct is None, "zero-actual accuracy should be undefined")

    missing_vintage = build_dashboard_view(
        dataset.frame,
        dataset.actual_population,
        DashboardFilters(source="tm"),
        vintage_a=VintageRule.specific_calculation_month(date(1900, 1, 1)),
        vintage_b=VintageRule.specific_calculation_month(date(1900, 1, 1)),
        hierarchy_diagnostics=dataset.hierarchy_diagnostics,
    )
    check(
        missing_vintage.metrics.coverage_denominator_actual_kl not in (None, 0),
        "missing-vintage case did not retain a positive actual denominator",
    )
    check(missing_vintage.metrics.coverage_numerator_actual_kl == 0.0, "missing-vintage numerator is not zero")
    check(missing_vintage.metrics.coverage_pct == 0.0, "missing-vintage coverage is not zero percent")
    check(
        missing_vintage.metrics.missing_vintage_pairs > 0,
        "missing-vintage case did not expose incomplete pairs",
    )


def _validate_empty_state(dataset) -> None:
    """Ensure empty selections return typed views instead of tracebacks."""
    empty = build_dashboard_view(
        dataset.frame,
        dataset.actual_population,
        DashboardFilters(source="tm", target_months=()),
        hierarchy_diagnostics=dataset.hierarchy_diagnostics,
    )
    check(empty.filtered_population.height == 0, "empty target selection retained forecast rows")
    check(empty.vintage_pairs.height == 0, "empty target selection retained pair rows")
    check(empty.metrics.forecast_accuracy_pct is None, "empty target selection produced accuracy")
    check(empty.population_summary.row(0, named=True)["target_range"] == "none selected", "empty summary lost its explanation")


def _validate_diagnostics(dataset, tm_view) -> None:
    """Check the machine-readable coverage audit used by release tooling."""
    diagnostics = build_dashboard_diagnostics(
        tm_view.filtered_population,
        tm_view.selected_actual_population,
        tm_view.coverage_pairs,
        tm_view.vintage_pairs,
    )
    check(set(diagnostics["check"].to_list()) >= REQUIRED_DIAGNOSTICS, "dashboard diagnostics omitted a required coverage check")
    check(set(diagnostics["status"].unique().to_list()) == {"measured"}, "dashboard diagnostics contain an unexpected status")


def validate() -> None:
    """Run all read-only release invariants against the real input artifacts."""
    for path in (FORECAST_HISTORY_PATH, HIERARCHY_PATH, ACTUALS_PATH):
        check(path.exists(), f"required dashboard input does not exist: {path}")
    inputs = load_analysis_inputs(FORECAST_HISTORY_PATH, HIERARCHY_PATH, ACTUALS_PATH)
    dataset = build_analysis_dataset(inputs)
    views = _validate_standard_views(dataset)
    _validate_comparison_view(dataset)
    _validate_real_input_filters(dataset)
    _validate_empty_state(dataset)
    _validate_diagnostics(dataset, views["tm"])
    print(
        "Dashboard release validation measured "
        f"{dataset.frame.height:,} forecast rows, "
        f"{dataset.actual_population.height:,} actual rows, "
        f"{dataset.frame['parent_code'].n_unique():,} parent products."
    )


def main() -> int:
    """Run validation and convert expected failures into a process status."""
    try:
        validate()
    except (AssertionError, FileNotFoundError, OSError, TypeError, ValueError) as exc:
        print(f"DASHBOARD RELEASE VALIDATION FAILED: {exc}", file=sys.stderr)
        return 1
    print("DASHBOARD RELEASE VALIDATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
