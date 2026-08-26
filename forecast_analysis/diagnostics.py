"""Quality diagnostics for the canonical analysis population."""

from __future__ import annotations

from collections.abc import Iterable

import polars as pl

from ._utils import require_columns
from .contracts import (
    ACTUAL_COLUMNS,
    ACTUAL_STATUSES,
    ANALYSIS_COLUMNS,
    DIAGNOSTIC_COLUMNS,
    HIERARCHY_STATUSES,
    PAIR_STATUSES,
)

_DIAGNOSTIC_SCHEMA = {
    "diagnostic_group": pl.String,
    "source": pl.String,
    "status": pl.String,
    "rows": pl.Int64,
    "products": pl.Int64,
    "sources": pl.Int64,
    "target_months": pl.Int64,
    "forecast_kl": pl.Float64,
    "actual_kl": pl.Float64,
}


def _as_float(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, float):
        return value
    if isinstance(value, int):
        return value + 0.0
    raise TypeError(f"diagnostic total is not numeric: {value!r}")


def _profile(
    frame: pl.DataFrame,
    diagnostic_group: str,
    *,
    source: str | None = None,
    status: str = "all",
) -> dict[str, object]:
    actual_values = frame.get_column("actual_kl").drop_nulls()
    actual_total = actual_values.sum()
    forecast_total = frame.get_column("forecast_kl").sum()
    return {
        "diagnostic_group": diagnostic_group,
        "source": source,
        "status": status,
        "rows": frame.height,
        "products": frame.get_column("parent_code").n_unique(),
        "sources": frame.get_column("source").n_unique(),
        "target_months": frame.get_column("snop_month").n_unique(),
        "forecast_kl": _as_float(forecast_total),
        "actual_kl": _as_float(actual_total),
    }


def _rows_for_status(
    frame: pl.DataFrame,
    column: str,
    values: Iterable[str],
    diagnostic_group: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for value in values:
        subset = frame.filter(pl.col(column) == value)
        rows.append(
            _profile(
                subset,
                diagnostic_group,
                status=value,
            )
        )
    return rows


def build_dashboard_diagnostics(
    frame: pl.DataFrame,
    actual_population: pl.DataFrame,
    coverage_pairs: pl.DataFrame,
    selected_pairs: pl.DataFrame,
) -> pl.DataFrame:
    """Return a compact, machine-readable audit of one dashboard selection.

    This table is intentionally independent of Marimo. It is used by the
    release validator and can also be displayed or exported by another shell.
    Counts come from the same frames that feed the dashboard, so the command
    validates population wiring rather than only checking that files import.
    """
    require_columns(frame, ANALYSIS_COLUMNS, "dashboard analysis population")
    require_columns(actual_population, ACTUAL_COLUMNS, "dashboard actual population")
    require_columns(
        coverage_pairs,
        ["source", "parent_code", "snop_month", "pair_status"],
        "dashboard coverage pairs",
    )
    require_columns(
        selected_pairs,
        ["source", "parent_code", "snop_month", "pair_status"],
        "dashboard selected pairs",
    )

    def total(source: pl.DataFrame, column: str) -> float:
        if column not in source.columns or source.height == 0:
            return 0.0
        value = source.get_column(column).drop_nulls().sum()
        if value is None:
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{column} must contain numeric values") from exc

    rows = [
        ("forecast_rows_loaded", frame.height, "count"),
        (
            "distinct_source_parent_target_keys",
            frame.select(["source", "parent_code", "snop_month"]).unique().height,
            "count",
        ),
        ("distinct_parent_products", frame["parent_code"].n_unique(), "count"),
        (
            "mapped_products",
            frame.filter(pl.col("mapping_status") == "mapped")["parent_code"].n_unique(),
            "count",
        ),
        (
            "hierarchy_conflict_products",
            frame.filter(pl.col("mapping_status") == "conflict")["parent_code"].n_unique(),
            "count",
        ),
        (
            "unmapped_products",
            frame.filter(pl.col("mapping_status") == "unmapped")["parent_code"].n_unique(),
            "count",
        ),
        (
            "matched_actual_keys",
            frame.filter(pl.col("actual_status") != "missing")
            .select(["source", "parent_code", "snop_month"])
            .unique()
            .height,
            "count",
        ),
        (
            "positive_actual_keys",
            frame.filter(pl.col("actual_status") == "matched_positive")
            .select(["source", "parent_code", "snop_month"])
            .unique()
            .height,
            "count",
        ),
        (
            "zero_actual_keys",
            frame.filter(pl.col("actual_status") == "matched_zero")
            .select(["source", "parent_code", "snop_month"])
            .unique()
            .height,
            "count",
        ),
        (
            "missing_actual_keys",
            frame.filter(pl.col("actual_status") == "missing")
            .select(["source", "parent_code", "snop_month"])
            .unique()
            .height,
            "count",
        ),
        (
            "actual_population_rows",
            actual_population.height,
            "count",
        ),
        ("actual_population_volume_kl", total(actual_population, "actual_kl"), "KL"),
        ("coverage_pair_rows", coverage_pairs.height, "count"),
        ("selected_pair_rows", selected_pairs.height, "count"),
        (
            "complete_pairs",
            selected_pairs.filter(pl.col("pair_status") == "complete").height,
            "count",
        ),
        (
            "incomplete_pairs",
            selected_pairs.filter(
                pl.col("pair_status").is_in(
                    [status for status in PAIR_STATUSES if status != "complete"]
                )
            ).height,
            "count",
        ),
        ("forecast_volume_in_selection_kl", total(frame, "forecast_kl"), "KL"),
        ("actual_volume_in_forecast_rows_kl", total(frame, "actual_kl"), "KL"),
    ]
    return pl.DataFrame(
        [
            {
                "check": check,
                "value": value,
                "unit": unit,
                "status": "measured",
                "detail": "derived from the active dashboard population",
            }
            for check, value, unit in rows
        ],
        schema={
            "check": pl.String,
            "value": pl.Float64,
            "unit": pl.String,
            "status": pl.String,
            "detail": pl.String,
        },
    )


def build_population_diagnostics(frame: pl.DataFrame) -> pl.DataFrame:
    """Report counts and volume coverage without excluding quality states."""
    rows = [_profile(frame, "summary")]
    for source in sorted(frame.get_column("source").unique().to_list()):
        rows.append(
            _profile(
                frame.filter(pl.col("source") == source),
                "source",
                source=source,
            )
        )
    rows.extend(
        _rows_for_status(frame, "mapping_status", HIERARCHY_STATUSES, "hierarchy_status")
    )
    rows.extend(_rows_for_status(frame, "actual_status", ACTUAL_STATUSES, "actual_status"))
    for source in sorted(frame.get_column("source").unique().to_list()):
        source_frame = frame.filter(pl.col("source") == source)
        for status in ACTUAL_STATUSES:
            rows.append(
                _profile(
                    source_frame.filter(pl.col("actual_status") == status),
                    "source_coverage",
                    source=source,
                    status=status,
                )
            )

    source_keys = (
        frame.select(["source", "parent_code", "snop_month"])
        .unique()
        .to_dicts()
    )
    by_product_target: dict[tuple[int, object], set[str]] = {}
    for row in source_keys:
        key = (row["parent_code"], row["snop_month"])
        by_product_target.setdefault(key, set()).add(row["source"])
    presence_rows = []
    for status in ("tm_only", "ml_only", "both_sources"):
        keys = [
            key
            for key, sources in by_product_target.items()
            if (status == "tm_only" and sources == {"tm"})
            or (status == "ml_only" and sources == {"ml"})
            or (status == "both_sources" and sources == {"tm", "ml"})
        ]
        presence_rows.append(
            {
                "diagnostic_group": "source_coverage",
                "source": "all",
                "status": status,
                "rows": len(keys),
                "products": len({key[0] for key in keys}),
                "sources": 2 if status == "both_sources" else (1 if keys else 0),
                "target_months": len({key[1] for key in keys}),
                "forecast_kl": 0.0,
                "actual_kl": 0.0,
            }
        )
    rows.extend(presence_rows)
    return pl.DataFrame(rows, schema=_DIAGNOSTIC_SCHEMA).select(DIAGNOSTIC_COLUMNS)
