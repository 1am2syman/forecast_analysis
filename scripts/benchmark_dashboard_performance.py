"""Measure analytical computation and service-cache response performance.

The benchmark intentionally rebuilds each analytical view from the same
immutable in-memory dataset. Input parsing and analysis-dataset construction are
reported separately and excluded from the default/comparison thresholds. The
service measurements cover a prewarmed exact request and compact bootstrap JSON.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from time import perf_counter
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forecast_analysis.analysis_frame import (  # noqa: E402
    build_analysis_dataset,
    load_analysis_inputs,
)
from dashboard.adapter import DashboardDataService  # noqa: E402
from forecast_analysis.dashboard import build_dashboard_view  # noqa: E402
from forecast_analysis.filters import DashboardFilters  # noqa: E402

DEFAULT_FORECAST_HISTORY = (
    ROOT / "artifacts/forecast_history/consolidated/forecast_history_waterfall.csv"
)
DEFAULT_HIERARCHY = ROOT / "artifacts/ph/PH_FG.xlsx"
DEFAULT_ACTUALS = (
    ROOT
    / "artifacts/secondary_sales/Mode_Sec_Month on Month_2026_04_30.xlsb"
)


def _positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("iterations must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("iterations must be at least 1")
    return parsed


def _non_negative_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("thresholds must be numeric") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("thresholds must be finite and non-negative")
    return parsed


def _measure_ms(operation: Callable[[], object], iterations: int) -> list[float]:
    timings: list[float] = []
    for _ in range(iterations):
        started = perf_counter()
        operation()
        timings.append((perf_counter() - started) * 1000)
    return timings


def _timing_summary(timings: list[float]) -> dict[str, object]:
    return {
        "iterations_ms": [round(value, 3) for value in timings],
        "median_ms": round(statistics.median(timings), 3),
        "min_ms": round(min(timings), 3),
        "max_ms": round(max(timings), 3),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--forecast-history",
        type=Path,
        default=DEFAULT_FORECAST_HISTORY,
    )
    parser.add_argument("--hierarchy", type=Path, default=DEFAULT_HIERARCHY)
    parser.add_argument("--actuals", type=Path, default=DEFAULT_ACTUALS)
    parser.add_argument("--iterations", type=_positive_integer, default=3)
    parser.add_argument(
        "--assert-default-ms",
        type=_non_negative_float,
        default=None,
        help="fail when the median default-view computation exceeds this value",
    )
    parser.add_argument(
        "--assert-comparison-ms",
        type=_non_negative_float,
        default=None,
        help="fail when the median comparison-view computation exceeds this value",
    )
    parser.add_argument(
        "--assert-cache-hit-ms",
        type=_non_negative_float,
        default=None,
        help="fail when the median exact service-cache hit exceeds this value",
    )
    parser.add_argument(
        "--assert-bootstrap-kib",
        type=_non_negative_float,
        default=None,
        help="fail when compact bootstrap JSON exceeds this size",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()

    load_started = perf_counter()
    inputs = load_analysis_inputs(
        args.forecast_history,
        args.hierarchy,
        args.actuals,
    )
    dataset = build_analysis_dataset(inputs)
    load_ms = (perf_counter() - load_started) * 1000

    default_timings = _measure_ms(
        lambda: build_dashboard_view(
            dataset.frame,
            dataset.actual_population,
            DashboardFilters(source="tm"),
            hierarchy_diagnostics=dataset.hierarchy_diagnostics,
        ),
        args.iterations,
    )
    comparison_timings = _measure_ms(
        lambda: build_dashboard_view(
            dataset.frame,
            dataset.actual_population,
            DashboardFilters(comparison_mode=True),
            hierarchy_diagnostics=dataset.hierarchy_diagnostics,
        ),
        args.iterations,
    )

    prewarm_started = perf_counter()
    service = DashboardDataService(
        dataset,
        refresh_timestamp="benchmark",
        source_label="benchmark-inputs",
        cache_size=8,
    )
    service_prewarm_ms = (perf_counter() - prewarm_started) * 1000
    default_request = service.default_request()
    cache_hit_timings = _measure_ms(
        lambda: service.view(default_request),
        args.iterations,
    )
    bootstrap = service.bootstrap()
    bootstrap_bytes = len(
        json.dumps(bootstrap, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    bootstrap_kib = bootstrap_bytes / 1024

    default_summary = _timing_summary(default_timings)
    comparison_summary = _timing_summary(comparison_timings)
    cache_hit_summary = _timing_summary(cache_hit_timings)
    report = {
        "input_loading_ms": round(load_ms, 3),
        "forecast_rows": dataset.frame.height,
        "actual_rows": dataset.actual_population.height,
        "iterations": args.iterations,
        "default": default_summary,
        "comparison": comparison_summary,
        "service_prewarm_ms": round(service_prewarm_ms, 3),
        "service_cache_hit": cache_hit_summary,
        "compact_bootstrap": {
            "bytes": bootstrap_bytes,
            "kib": round(bootstrap_kib, 3),
        },
        "thresholds_ms": {
            "default": args.assert_default_ms,
            "comparison": args.assert_comparison_ms,
        },
        "service_thresholds": {
            "cache_hit_ms": args.assert_cache_hit_ms,
            "bootstrap_kib": args.assert_bootstrap_kib,
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))

    failures: list[str] = []
    default_median = statistics.median(default_timings)
    comparison_median = statistics.median(comparison_timings)
    cache_hit_median = statistics.median(cache_hit_timings)
    if (
        args.assert_default_ms is not None
        and default_median > args.assert_default_ms
    ):
        failures.append(
            f"default median {default_median:.3f} ms exceeds "
            f"{args.assert_default_ms:.3f} ms"
        )
    if (
        args.assert_comparison_ms is not None
        and comparison_median > args.assert_comparison_ms
    ):
        failures.append(
            f"comparison median {comparison_median:.3f} ms exceeds "
            f"{args.assert_comparison_ms:.3f} ms"
        )
    if (
        args.assert_cache_hit_ms is not None
        and cache_hit_median >= args.assert_cache_hit_ms
    ):
        failures.append(
            f"cache-hit median {cache_hit_median:.3f} ms exceeds "
            f"{args.assert_cache_hit_ms:.3f} ms"
        )
    if (
        args.assert_bootstrap_kib is not None
        and bootstrap_kib >= args.assert_bootstrap_kib
    ):
        failures.append(
            f"compact bootstrap {bootstrap_kib:.3f} KiB exceeds "
            f"{args.assert_bootstrap_kib:.3f} KiB"
        )
    if failures:
        for failure in failures:
            print(f"PERFORMANCE ASSERTION FAILED: {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
