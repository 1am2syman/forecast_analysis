"""Normalize the consolidated forecast-history seam."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from ._utils import (
    duplicate_keys,
    normalize_float_values,
    normalize_integer_values,
    normalize_month_values,
    normalize_text_values,
    require_columns,
)
from .contracts import (
    FORECAST_HISTORY_COLUMNS,
    FORECAST_IDENTITY_COLUMNS,
    FORECAST_SOURCES,
    NORMALIZED_FORECAST_COLUMNS,
)


def normalize_forecast_history(raw: pl.DataFrame) -> pl.DataFrame:
    """Return typed, source-aware forecast rows with derived horizon months.

    The input is the six-column consolidated CSV contract.  Source is part of
    the identity key, so equal TM and ML business keys remain valid separate
    forecasts while duplicate keys within one source fail fast.
    """
    require_columns(raw, FORECAST_HISTORY_COLUMNS, "forecast history")
    if set(raw.columns) != set(FORECAST_HISTORY_COLUMNS):
        raise ValueError(
            "forecast history validation failed: expected the six-column "
            f"contract {FORECAST_HISTORY_COLUMNS}, found {raw.columns}"
        )
    if raw.height == 0:
        raise ValueError("forecast history validation failed: input is empty")

    calculation_month = normalize_month_values(
        raw.get_column("calculation_month").to_list(),
        "calculation_month",
        "forecast history",
    )
    snop_month = normalize_month_values(
        raw.get_column("snop_month").to_list(),
        "snop_month",
        "forecast history",
    )
    parent_code = normalize_integer_values(
        raw.get_column("parent_code").to_list(), "parent_code", "forecast history"
    )
    parent_description = normalize_text_values(
        raw.get_column("parent_description").to_list(),
        "parent_description",
        "forecast history",
        required=True,
    )
    forecast_kl = normalize_float_values(
        raw.get_column("qty").to_list(),
        "qty",
        "forecast history",
        non_negative=True,
    )
    source = normalize_text_values(
        raw.get_column("source").to_list(),
        "source",
        "forecast history",
        required=True,
    ).cast(pl.String).str.to_lowercase()
    invalid_sources = source.filter(~source.is_in(FORECAST_SOURCES))
    if invalid_sources.len():
        raise ValueError(
            "forecast history validation failed: unsupported source(s): "
            f"{sorted(set(invalid_sources.to_list()))}"
        )

    normalized = pl.DataFrame(
        {
            "source": source,
            "parent_code": parent_code,
            "parent_description": parent_description,
            "calculation_month": calculation_month,
            "snop_month": snop_month,
            "forecast_kl": forecast_kl,
        }
    )
    horizon = [
        12 * (target.year - calculation.year) + target.month - calculation.month
        for calculation, target in zip(
            normalized["calculation_month"].to_list(),
            normalized["snop_month"].to_list(),
            strict=True,
        )
    ]
    if any(months < 0 for months in horizon):
        bad_rows = normalized.with_columns(
            pl.Series("forecast_horizon_months", horizon, dtype=pl.Int64)
        ).filter(pl.col("forecast_horizon_months") < 0)
        raise ValueError(
            "forecast history validation failed: forecast horizon must be "
            f"non-negative; sample rows: {bad_rows.head(3).to_dicts()}"
        )
    normalized = normalized.with_columns(
        pl.Series("forecast_horizon_months", horizon, dtype=pl.Int64)
    ).select(NORMALIZED_FORECAST_COLUMNS)

    duplicates = duplicate_keys(normalized, FORECAST_IDENTITY_COLUMNS)
    if duplicates.height:
        raise ValueError(
            "forecast history validation failed: duplicate keys within a source; "
            f"sample keys: {duplicates.head(3).to_dicts()}"
        )
    return normalized.sort(
        ["parent_code", "snop_month", "calculation_month", "source"]
    )


def load_forecast_history(path: Path) -> pl.DataFrame:
    """Read and normalize the consolidated waterfall CSV."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"forecast history CSV not found: {path}")
    try:
        raw = pl.read_csv(path)
    except Exception as exc:
        raise ValueError(f"unable to read forecast history CSV {path}: {exc}") from exc
    return normalize_forecast_history(raw)
