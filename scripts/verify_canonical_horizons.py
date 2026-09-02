#!/usr/bin/env python3
"""Verify canonical M1--M5 provenance and exact accuracy endpoint rules."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import forecast_history_pipeline as pipeline  # pyright: ignore[reportMissingImports]
from forecast_analysis import (  # pyright: ignore[reportMissingImports]
    VintageRule,
    build_common_vintage_accuracy,
)

OUTPUT = ROOT / "artifacts/forecast_history/consolidated/forecast_history_waterfall.csv"
TM_FIXTURE = pipeline.FORECAST_HISTORY_DIR / "S&OP_grid file_Apr-26 to Aug-26_circulation.xlsx"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify_tm_provenance() -> None:
    meta, rows = pipeline.parse_grid(TM_FIXTURE)
    check(meta["calc_month"] == "2026-03", "April-August TM file is not March vintage")
    horizons = (
        rows.select(
            (
                pl.col("snop_month").dt.year() * 12
                + pl.col("snop_month").dt.month()
                - pl.col("calculation_month").dt.year() * 12
                - pl.col("calculation_month").dt.month()
            ).alias("horizon")
        )
        .get_column("horizon")
        .unique()
        .sort()
        .to_list()
    )
    check(horizons == [1, 2, 3, 4, 5], f"unexpected TM horizons: {horizons}")
    print("TM PROVENANCE VERIFIED")


def verify_waterfall() -> None:
    check(OUTPUT.is_file(), f"waterfall output not found: {OUTPUT}")
    frame = pl.read_csv(OUTPUT)
    check(frame.columns == pipeline.OUTPUT_COLUMNS, "waterfall schema changed")
    horizon = (
        pl.col("snop_month").str.to_date("%Y-%m").dt.year() * 12
        + pl.col("snop_month").str.to_date("%Y-%m").dt.month()
        - pl.col("calculation_month").str.to_date("%Y-%m").dt.year() * 12
        - pl.col("calculation_month").str.to_date("%Y-%m").dt.month()
    )
    checked = frame.with_columns(horizon.alias("horizon"))
    invalid = checked.filter(~pl.col("horizon").is_between(1, 5))
    check(invalid.is_empty(), f"non-canonical waterfall rows: {invalid.head(3)}")
    for source in ("tm", "ml"):
        source_horizons = (
            checked.filter(pl.col("source") == source)["horizon"].unique().sort().to_list()
        )
        check(source_horizons == [1, 2, 3, 4, 5], f"{source} horizons: {source_horizons}")
    august = checked.filter(
        (pl.col("source") == "tm") & (pl.col("snop_month") == "2026-08")
    )
    check(
        set(august["horizon"].unique().to_list()) == {1, 2, 3, 4, 5},
        "TM August target does not expose M1 through M5",
    )
    check(
        august.filter(pl.col("horizon") == 5)["calculation_month"].unique().to_list()
        == ["2026-03"],
        "TM August M5 is not March",
    )
    print("WATERFALL HORIZONS VERIFIED")


def verify_accuracy() -> None:
    target = date(2026, 8, 1)
    rows = []
    for parent_code, actual, forecasts in (
        (1, 100.0, {5: 80.0, 4: 40.0, 1: 120.0}),
        (2, 50.0, {4: 20.0, 1: 60.0}),
    ):
        for horizon, forecast in forecasts.items():
            rows.append(
                {
                    "source": "tm",
                    "parent_code": parent_code,
                    "calculation_month": date(2026, 8 - horizon, 1),
                    "snop_month": target,
                    "forecast_horizon_months": horizon,
                    "forecast_kl": forecast,
                    "actual_kl": actual,
                }
            )
    frame = pl.DataFrame(rows)
    result = build_common_vintage_accuracy(
        frame,
        "tm",
        comparison_rules=(VintageRule.oldest_available(),),
    )
    oldest, latest = result.series
    oldest_row = oldest.rows[0]
    latest_row = latest.rows[0]
    check(oldest.rule.kind == "oldest_available", "oldest rule identity changed")
    check(latest.rule.kind == "latest_available", "latest rule identity changed")
    check(oldest_row.eligible_parents == 1, "Oldest fell back from M5 to M4")
    check(latest_row.eligible_parents == 1, "Latest fell back from M1 to M4")
    check(oldest_row.absolute_error_numerator_kl == 20.0, "Oldest used the wrong forecast")
    check(latest_row.absolute_error_numerator_kl == 20.0, "Latest used the wrong forecast")
    print("ACCURACY HORIZONS VERIFIED")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("tm-provenance", "waterfall", "accuracy", "all"), default="all")
    stage = parser.parse_args().stage
    try:
        if stage in ("tm-provenance", "all"):
            verify_tm_provenance()
        if stage in ("waterfall", "all"):
            verify_waterfall()
        if stage in ("accuracy", "all"):
            verify_accuracy()
    except (AssertionError, OSError, ValueError, RuntimeError) as exc:
        print(f"CANONICAL HORIZON VERIFICATION FAILED: {exc}", file=sys.stderr)
        return 1
    if stage == "all":
        print("CANONICAL HORIZONS VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
