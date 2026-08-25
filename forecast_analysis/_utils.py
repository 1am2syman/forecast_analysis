"""Small, strict normalization helpers shared by source adapters."""

from __future__ import annotations

import math
import numbers
import re
from datetime import date, datetime
from typing import Iterable

import polars as pl

INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1


def require_columns(frame: pl.DataFrame, required: Iterable[str], label: str) -> None:
    """Fail clearly when a source frame does not have its required columns."""
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(
            f"{label} validation failed: missing required column(s): "
            + ", ".join(missing)
        )


def normalize_integer_values(
    values: Iterable[object], column: str, label: str
) -> pl.Series:
    """Convert exact integer values without a lossy floating-point cast."""
    normalized: list[int] = []
    errors: list[str] = []
    for index, value in enumerate(values):
        try:
            if isinstance(value, bool):
                raise ValueError("boolean is not an integer")
            if isinstance(value, numbers.Integral):
                candidate = int(value)
            elif isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
                candidate = int(value.strip())
            else:
                raise ValueError(f"unsupported value {value!r}")
            if not INT64_MIN <= candidate <= INT64_MAX:
                raise ValueError("outside signed 64-bit range")
            normalized.append(candidate)
        except (TypeError, ValueError, OverflowError) as exc:
            errors.append(f"row {index + 1}: {exc}")
            normalized.append(0)
    if errors:
        raise ValueError(
            f"{label} validation failed: {column} must contain exact Int64 values; "
            + "; ".join(errors[:3])
        )
    return pl.Series(column, normalized, dtype=pl.Int64)


def normalize_text_values(
    values: Iterable[object], column: str, label: str, *, required: bool = False
) -> pl.Series:
    """Trim text values and convert blanks to null where appropriate."""
    normalized: list[str | None] = []
    errors: list[str] = []
    for index, value in enumerate(values):
        if value is None:
            normalized.append(None)
            if required:
                errors.append(f"row {index + 1}: value is null")
            continue
        text = str(value).strip()
        if not text:
            normalized.append(None)
            if required:
                errors.append(f"row {index + 1}: value is blank")
            continue
        normalized.append(text)
    if errors:
        raise ValueError(
            f"{label} validation failed: {column} must be non-null text; "
            + "; ".join(errors[:3])
        )
    return pl.Series(column, normalized, dtype=pl.String)


def normalize_float_values(
    values: Iterable[object], column: str, label: str, *, non_negative: bool = False
) -> pl.Series:
    """Convert finite numeric values and optionally reject negatives."""
    normalized: list[float] = []
    errors: list[str] = []
    for index, value in enumerate(values):
        try:
            if value is None or isinstance(value, bool):
                raise ValueError("value is missing or not numeric")
            if not isinstance(value, (str, int, float)):
                raise ValueError(f"unsupported value {value!r}")
            candidate = float(value)
            if not math.isfinite(candidate):
                raise ValueError("value is not finite")
            if non_negative and candidate < 0:
                raise ValueError("value must be non-negative")
            normalized.append(candidate)
        except (TypeError, ValueError, OverflowError) as exc:
            errors.append(f"row {index + 1}: {exc}")
            normalized.append(0.0)
    if errors:
        rule = "finite non-negative" if non_negative else "finite numeric"
        raise ValueError(
            f"{label} validation failed: {column} must contain {rule} values; "
            + "; ".join(errors[:3])
        )
    return pl.Series(column, normalized, dtype=pl.Float64)


def _parse_month(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    for fmt in ("%Y-%m", "%Y-%m-%d", "%b-%Y", "%B-%Y", "%d-%b-%Y", "%d-%B-%Y"):
        try:
            return datetime.strptime(text.title(), fmt).date()
        except ValueError:
            continue
    return None


def normalize_month_values(
    values: Iterable[object], column: str, label: str
) -> pl.Series:
    """Parse month keys and dates, requiring the first day of each month."""
    normalized: list[date] = []
    invalid: list[str] = []
    not_first: list[str] = []
    for index, value in enumerate(values):
        parsed = _parse_month(value)
        if parsed is None:
            invalid.append(f"row {index + 1}: {value!r}")
            normalized.append(date(1970, 1, 1))
        elif parsed.day != 1:
            not_first.append(f"row {index + 1}: {value!r}")
            normalized.append(date(parsed.year, parsed.month, 1))
        else:
            normalized.append(parsed)
    if invalid:
        raise ValueError(
            f"{label} validation failed: {column} contains invalid month values; "
            + "; ".join(invalid[:3])
        )
    if not_first:
        raise ValueError(
            f"{label} validation failed: {column} must contain first-of-month dates; "
            + "; ".join(not_first[:3])
        )
    return pl.Series(column, normalized, dtype=pl.Date)


def duplicate_keys(frame: pl.DataFrame, keys: list[str]) -> pl.DataFrame:
    """Return only key groups that occur more than once."""
    return frame.group_by(keys).len().filter(pl.col("len") > 1)
