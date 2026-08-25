"""Normalize and aggregate secondary-sales actuals."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date
from pathlib import Path

import polars as pl

from ._utils import (
    normalize_float_values,
    normalize_integer_values,
    normalize_month_values,
)
from .contracts import ACTUAL_COLUMNS

ACTUAL_COLUMN_ALIASES = {
    "parent_code": {"parent_code", "parent_material_code"},
    "snop_month": {"snop_month", "month_year"},
    "actual_kl": {"actual_kl", "sec_vol_kl_mth_billwise"},
}
SUPPORTED_WORKBOOK_SUFFIXES = {".xls", ".xlsx", ".xlsb"}


def _column_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _canonicalize_columns(raw: pl.DataFrame) -> pl.DataFrame:
    """Map the current workbook headers to the three actuals fields."""
    matches: dict[str, str] = {}
    for canonical, aliases in ACTUAL_COLUMN_ALIASES.items():
        candidates = [
            original
            for original in raw.columns
            if _column_key(original) in aliases
        ]
        if len(candidates) != 1:
            if not candidates:
                raise ValueError(
                    "secondary-sales validation failed: missing required field "
                    f"for {canonical!r}"
                )
            raise ValueError(
                "secondary-sales validation failed: multiple columns match "
                f"{canonical!r}: {candidates}"
            )
        matches[canonical] = candidates[0]
    return raw.select([matches[column] for column in ACTUAL_COLUMNS]).rename(
        {source: canonical for canonical, source in matches.items()}
    )


def normalize_actuals(
    raw: pl.DataFrame, *, target_months: Iterable[date] | None = None
) -> pl.DataFrame:
    """Return one finite, non-negative actual per parent and target month.

    ``target_months`` is used only by the forecast-driven population loader to
    discard historical actuals outside the analysis window before validating
    actual-volume finiteness and non-negativity. Parent and month keys are still
    normalized before the window filter is applied.
    """
    canonical = _canonicalize_columns(raw)
    normalized = pl.DataFrame(
        {
            "parent_code": normalize_integer_values(
                canonical.get_column("parent_code").to_list(),
                "parent_code",
                "secondary-sales",
            ),
            "snop_month": normalize_month_values(
                canonical.get_column("snop_month").to_list(),
                "snop_month",
                "secondary-sales",
            ),
            "_actual_raw": canonical.get_column("actual_kl").alias("_actual_raw"),
        }
    )
    if target_months is not None:
        allowed_months = list(target_months)
        normalized = normalized.filter(pl.col("snop_month").is_in(allowed_months))

    normalized = normalized.with_columns(
        normalize_float_values(
            normalized.get_column("_actual_raw").to_list(),
            "actual_kl",
            "secondary-sales",
        ).alias("actual_kl")
    ).drop("_actual_raw")
    negative = normalized.filter(pl.col("actual_kl") < 0)
    if negative.height:
        raise ValueError(
            "secondary-sales validation failed: actual_kl must be non-negative; "
            f"sample rows: {negative.head(3).to_dicts()}"
        )

    aggregated = (
        normalized.group_by(["parent_code", "snop_month"])
        .agg(actual_kl=pl.col("actual_kl").sum())
        .select(ACTUAL_COLUMNS)
    )
    non_finite = aggregated.filter(~pl.col("actual_kl").is_finite())
    if non_finite.height:
        raise ValueError(
            "secondary-sales validation failed: aggregated actual_kl must be "
            f"finite; sample rows: {non_finite.head(3).to_dicts()}"
        )
    return aggregated.sort(["parent_code", "snop_month"])


# Keep the public name aligned with the domain language in the specification.
aggregate_actuals = normalize_actuals


def _input_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise FileNotFoundError(f"secondary-sales input not found: {path}")
    files = sorted(
        candidate
        for candidate in path.iterdir()
        if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_WORKBOOK_SUFFIXES
    )
    if not files:
        raise FileNotFoundError(f"no secondary-sales workbooks found in {path}")
    return files


def load_actuals(
    path: Path, *, target_months: Iterable[date] | None = None
) -> pl.DataFrame:
    """Read current secondary-sales workbooks and aggregate the analysis window."""
    files = _input_files(Path(path))
    raw_frames: list[pl.DataFrame] = []
    for workbook in files:
        try:
            raw_frames.append(
                pl.read_excel(
                    workbook,
                    engine="calamine",
                    read_options={"header_row": 5},
                )
            )
        except Exception as exc:
            raise ValueError(
                f"unable to read secondary-sales workbook {workbook}: {exc}"
            ) from exc
    return normalize_actuals(
        pl.concat(raw_frames, how="diagonal"), target_months=target_months
    )
