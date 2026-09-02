"""Independent real-data oracle for the dashboard common-vintage payload."""

from __future__ import annotations

import contextlib
from datetime import date
import io
import math
from pathlib import Path
import sys
from typing import Any, cast

import polars as pl

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from dashboard.adapter import DashboardDataService


SELECTED_IDS = [
    "oldest_available",
    "specific_horizon:4",
    "specific_horizon:3",
]


def _selected_forecast(
    target: pl.DataFrame,
    rule_id: str,
) -> pl.DataFrame:
    ordered = target.sort(["parent_code", "calculation_month"])
    if rule_id == "oldest_available":
        selected = ordered.group_by("parent_code", maintain_order=True).first()
    else:
        _, separator, raw_horizon = rule_id.partition(":")
        if separator != ":" or not raw_horizon.isdecimal():
            raise AssertionError(f"invalid oracle rule ID: {rule_id}")
        try:
            horizon = int(raw_horizon)
        except ValueError as exc:
            raise AssertionError(f"invalid oracle rule ID: {rule_id}") from exc
        selected = ordered.filter(
            pl.col("forecast_horizon_months") == horizon
        ).group_by("parent_code", maintain_order=True).first()
    return selected.filter(pl.col("forecast_kl").is_not_null()).select(
        "parent_code",
        pl.col("forecast_kl").cast(pl.Float64).alias(rule_id),
    )


def _assert_equal(actual: Any, expected: Any, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: {actual!r} != {expected!r}")


def _verify_worked_series(
    service: DashboardDataService,
    payload: dict[str, Any],
) -> None:
    source = cast(str, payload["request"]["source"])
    series = [
        option
        for option in payload["accuracy_vintages"]["options"]
        if option["selected"]
    ]
    worked = series[1]
    worked_row = next(
        row
        for row in reversed(worked["rows"])
        if row["eligible_parents"] > 0
    )
    target_month = date.fromisoformat(worked_row["snop_month"])
    target = service.dataset.frame.filter(
        (pl.col("source") == source)
        & (pl.col("snop_month") == target_month)
    )
    actuals = (
        target.sort(["parent_code", "calculation_month"])
        .group_by("parent_code", maintain_order=True)
        .agg(pl.col("actual_kl").first().cast(pl.Float64).alias("actual_kl"))
        .filter(pl.col("actual_kl").is_not_null() & (pl.col("actual_kl") > 0))
    )
    common = actuals
    for rule_id in [*SELECTED_IDS, "latest_available"]:
        if rule_id == "latest_available":
            selected = (
                target.sort(["parent_code", "calculation_month"])
                .group_by("parent_code", maintain_order=True)
                .last()
                .filter(pl.col("forecast_kl").is_not_null())
                .select(
                    "parent_code",
                    pl.col("forecast_kl").cast(pl.Float64).alias(rule_id),
                )
            )
        else:
            selected = _selected_forecast(target, rule_id)
        common = common.join(selected, on="parent_code", how="inner")

    forecast = worked["id"]
    raw_denominator = common.get_column("actual_kl").sum()
    raw_numerator = (
        common.get_column(forecast) - common.get_column("actual_kl")
    ).abs().sum()
    if raw_denominator is None or raw_numerator is None:
        raise AssertionError("worked source cohort has no numeric totals")
    denominator = cast(float, raw_denominator)
    numerator = cast(float, raw_numerator)
    expected_accuracy = 100.0 * (1.0 - numerator / denominator)
    _assert_equal(common.height, worked_row["eligible_parents"], "worked count")
    if not math.isclose(
        denominator,
        worked_row["actual_denominator_kl"],
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        raise AssertionError("worked denominator differs from source-data sum")
    if not math.isclose(
        numerator,
        worked_row["absolute_error_numerator_kl"],
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        raise AssertionError("worked numerator differs from source-data sum")
    if not math.isclose(
        expected_accuracy,
        worked_row["forecast_accuracy_pct"],
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        raise AssertionError("worked accuracy differs from independent calculation")


def main() -> None:
    with contextlib.redirect_stderr(io.StringIO()):
        service = DashboardDataService.from_paths(cache_size=2)
    baseline = service.bootstrap()
    request = dict(baseline["defaults"])
    request["accuracy_vintage_ids"] = SELECTED_IDS
    payload = service.compact_view(request)

    _assert_equal(payload["metrics"], baseline["metrics"], "global metrics changed")
    _assert_equal(
        payload["monthly_performance"],
        baseline["monthly_performance"],
        "monthly performance changed",
    )
    selected = [
        option
        for option in payload["accuracy_vintages"]["options"]
        if option["selected"]
    ]
    _assert_equal([item["id"] for item in selected], SELECTED_IDS, "series order")
    series = [*selected, payload["accuracy_vintages"]["latest"]]
    rows_by_series = {
        item["id"]: {row["snop_month"]: row for row in item["rows"]}
        for item in series
    }
    months = tuple(next(iter(rows_by_series.values())))
    if not months:
        raise AssertionError("real-data payload returned no target months")
    for rows in rows_by_series.values():
        _assert_equal(tuple(rows), months, "series target months")
    for target_month in months:
        month_rows = [rows[target_month] for rows in rows_by_series.values()]
        _assert_equal(
            len({row["eligible_parents"] for row in month_rows}),
            1,
            f"eligible cohort differs for {target_month}",
        )
        _assert_equal(
            len({row["actual_denominator_kl"] for row in month_rows}),
            1,
            f"denominator differs for {target_month}",
        )

    _verify_worked_series(service, payload)
    print("COMMON VINTAGE ACCURACY VERIFIED")


if __name__ == "__main__":
    main()
