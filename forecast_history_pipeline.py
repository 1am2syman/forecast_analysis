"""Validated forecast-history ETL and output generation.

This top-level module is imported by the Marimo report and command-line scripts.
It owns the source adapters, pure transformations, validation evidence,
and the atomic output-write boundary.  The Marimo report imports this module but
contains no ETL or output-contract implementation.
"""

from __future__ import annotations

import math
import numbers
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from pathlib import Path
from typing import NamedTuple

import polars as pl

PROJECT_ROOT = Path(__file__).resolve().parent
FORECAST_HISTORY_DIR = PROJECT_ROOT / "artifacts" / "forecast_history"
ML_HISTORY_PATH = PROJECT_ROOT / "artifacts" / "ml_history" / "forecast_history_ml.xlsx"
OUTPUT_CSV = FORECAST_HISTORY_DIR / "consolidated" / "forecast_history_waterfall.csv"

OUTPUT_COLUMNS = [
    "calculation_month",
    "snop_month",
    "parent_code",
    "parent_description",
    "qty",
    "source",
]
HISTORY_KEY_COLUMNS = [
    "parent_code",
    "calculation_month",
    "snop_month",
    "source",
]
HISTORY_SORT_COLUMNS = [
    "parent_code",
    "snop_month",
    "calculation_month",
    "source",
]
ML_REQUIRED_COLUMNS = [
    "KEY",
    "DESCRIPTION",
    "MONTH_DATE",
    "TRAIN_TILL",
    "PREDICTING_MONTH",
    "PRED_VOLUME",
    "Oth_Ch_Contr._%",
]
ML_OPTIONAL_REFERENCE_COLUMN = "Cal_forecast"
ML_FORMULA_TOLERANCE = 1e-6
FORECAST_SOURCES = {"tm", "ml"}
DEFAULT_OUTPUT_MODE = 0o644

# The folder must always hold the full set of monthly grid files; a missing file
# would silently truncate the forecast history, so the count is enforced.
EXPECTED_FILES = 16
# Melted sums are checked against each sheet's own Grand Total row; the CSV is
# only written when every file is within this tolerance.
GRAND_TOTAL_TOLERANCE = 1e-6

MONTHS = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]
MONTH_NO = {abbr: i + 1 for i, abbr in enumerate(MONTHS)}
# Anchored: the whole file name must match, nothing may precede or follow the
# S&OP pattern.
FILENAME_RE = re.compile(
    r"^S&OP_grid file_(\w{3})-(\d{2}) to (\w{3})-(\d{2})_circulation\.xlsx$"
)
INTEGER_DTYPES = {
    pl.Int8,
    pl.Int16,
    pl.Int32,
    pl.Int64,
    pl.UInt8,
    pl.UInt16,
    pl.UInt32,
    pl.UInt64,
}
FLOAT_DTYPES = {pl.Float32, pl.Float64}
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1


@dataclass(frozen=True)
class MlValidationEvidence:
    """Facts collected while validating one ML workbook.

    The object deliberately contains measurements rather than a synthetic
    status flag.  It is safe to render directly in the report and makes the
    validation result auditable after the transformation has completed.
    """

    checked_rows: int
    cal_forecast_checked_rows: int
    max_formula_difference: float | None
    formula_tolerance: float
    horizon_counts: tuple[tuple[str, int], ...]
    calculation_months: tuple[date, ...]
    snop_months: tuple[date, ...]
    duplicate_final_key_count: int

    def to_frame(self) -> pl.DataFrame:
        """Return the evidence as one report-ready row of measured facts."""
        horizon_coverage = "; ".join(
            f"{horizon}={count}" for horizon, count in self.horizon_counts
        )
        return pl.DataFrame(
            {
                "checked_rows": [self.checked_rows],
                "cal_forecast_checked_rows": [self.cal_forecast_checked_rows],
                "max_formula_difference": [self.max_formula_difference],
                "formula_tolerance": [self.formula_tolerance],
                "horizon_coverage": [horizon_coverage],
                "calculation_month_coverage": [
                    _format_month_list(self.calculation_months)
                ],
                "snop_month_coverage": [_format_month_list(self.snop_months)],
                "duplicate_final_key_count": [self.duplicate_final_key_count],
            }
        )


class MlHistoryResult(NamedTuple):
    """Normalized ML rows plus the evidence collected for them."""

    frame: pl.DataFrame
    validation: MlValidationEvidence


class ForecastHistoryBuild(NamedTuple):
    """Validated TM + ML history plus report-ready projections."""

    consolidated: pl.DataFrame
    tm: pl.DataFrame
    ml: pl.DataFrame
    tm_validation: pl.DataFrame
    ml_validation: MlValidationEvidence
    validation_status: pl.DataFrame
    source_summary: pl.DataFrame


def _format_month_list(months: tuple[date, ...]) -> str:
    """Format an exact ordered month set for validation evidence."""
    return ", ".join(month.strftime("%Y-%m") for month in months)


def _measured_float(value: object, label: str) -> float:
    """Convert a Polars scalar measurement after checking its runtime type."""
    if value is None:
        return 0.0
    if not isinstance(value, (int, float)):
        raise TypeError(f"{label} produced a non-numeric measurement: {value!r}")
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise RuntimeError(
            f"{label} produced an unusable measurement: {value!r}"
        ) from exc


def _measured_int(value: object, label: str) -> int:
    """Convert a Polars integer measurement after checking its runtime type."""
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        raise TypeError(f"{label} produced a non-integer measurement: {value!r}")
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise RuntimeError(
            f"{label} produced an unusable measurement: {value!r}"
        ) from exc


def _month_sequence(
    start_abbr: str, start_year: int, end_abbr: str, end_year: int
) -> list[tuple[str, int]]:
    """Walk the month/year pairs covered by a file, e.g. Nov-25 to Mar-26.

    Raises ValueError for unknown month abbreviations and windows longer than
    12 months (reversed or unaligned ranges would otherwise loop forever).
    """
    for abbr in (start_abbr, end_abbr):
        if abbr not in MONTHS:
            raise ValueError(f"unknown month abbreviation {abbr!r}")
    sequence: list[tuple[str, int]] = []
    current, current_year = start_abbr, start_year
    while True:
        if len(sequence) >= 12:
            raise ValueError(
                f"month window {start_abbr}-{start_year} to "
                f"{end_abbr}-{end_year} is longer than 12 months "
                "(reversed range or bad years?)"
            )
        sequence.append((current, current_year))
        if current == end_abbr and current_year == end_year:
            return sequence
        current = MONTHS[(MONTHS.index(current) + 1) % 12]
        if current == "Jan":
            current_year += 1


def parse_grid(path: Path) -> tuple[dict, pl.DataFrame]:
    """Read one S&OP grid file and return metadata plus material-level rows.

    The header block differs between the 2025 and 2026 vintages, so the layout
    is auto-detected instead of assumed.  Month columns are returned as Polars
    Date values representing the first day of the month.
    """
    meta: dict = {}
    issues: list[str] = []

    raw = pl.read_excel(
        path,
        sheet_name="full_s&op",
        engine="calamine",
        read_options={"header_row": None},
    )

    # Detect the month-anchor row and the column-name row independently.
    anchor_idx = names_idx = None
    for i in range(min(6, raw.height)):
        row = raw.row(i)
        if anchor_idx is None:
            n_months = sum(
                1 for cell in row if isinstance(cell, str) and cell.strip() in MONTHS
            )
            if n_months >= 2:
                anchor_idx = i
        if names_idx is None and any(
            isinstance(cell, str) and cell.strip() == "parent_code" for cell in row
        ):
            names_idx = i
    if anchor_idx is None or names_idx is None:
        raise ValueError(
            f"{path.name}: header block not found "
            f"(anchor row={anchor_idx}, names row={names_idx})"
        )

    data_start = max(anchor_idx, names_idx) + 1
    month_positions = [
        i
        for i, cell in enumerate(raw.row(anchor_idx))
        if isinstance(cell, str) and cell.strip() in MONTHS
    ]

    # Calculation month and target-month years come from the file name.
    match = FILENAME_RE.search(path.name)
    if match is None:
        raise ValueError(f"{path.name}: file name does not match the S&OP pattern")
    try:
        start_abbr, start_year, end_abbr, end_year = (
            match.group(1),
            2000 + int(match.group(2)),
            match.group(3),
            2000 + int(match.group(4)),
        )
    except (IndexError, ValueError):
        raise ValueError(f"{path.name}: cannot parse months from file name") from None

    try:
        sequence = _month_sequence(start_abbr, start_year, end_abbr, end_year)
    except ValueError as exc:
        raise ValueError(f"{path.name}: {exc}") from None
    if len(sequence) != 5:
        raise ValueError(
            f"{path.name}: TM file must contain exactly five target months "
            f"(M1 through M5), found {len(sequence)}"
        )

    sheet_months = [raw.row(anchor_idx)[i].strip() for i in month_positions]
    expected_months = [abbr for abbr, _ in sequence]
    if sheet_months != expected_months:
        raise ValueError(
            f"{path.name}: sheet month columns {sheet_months} do not match "
            f"the file-name range {expected_months}"
        )

    # The workbook name describes the first through fifth target months.  The
    # forecast was made in the preceding month, so that preceding month is the
    # canonical calculation month for every row in this file.
    calculation_year = start_year - (1 if start_abbr == "Jan" else 0)
    calculation_month_number = 12 if start_abbr == "Jan" else MONTH_NO[start_abbr] - 1
    calculation_month = date(
        calculation_year,
        calculation_month_number,
        1,
    )
    month_dates = {
        abbr: date(year, MONTH_NO[abbr], 1)
        for abbr, (_, year) in zip(sheet_months, sequence)
    }

    # Drop pivot total rows and melt the non-empty month cells.
    data = raw[data_start:]
    leaf = data.filter(pl.nth(1).cast(pl.String).is_not_null())
    meta["total_rows_dropped"] = data.height - leaf.height

    month_exprs = []
    non_numeric = 0
    for index, abbr in zip(month_positions, sheet_months):
        non_numeric += leaf.filter(
            pl.nth(index).is_not_null()
            & ~pl.nth(index).cast(pl.String).str.contains(r"^-?\d*\.?\d+$")
        ).height
        month_exprs.append(pl.nth(index).cast(pl.Float64, strict=False).alias(abbr))
    if non_numeric:
        issues.append(f"{non_numeric} non-numeric qty cell(s) set to null")

    long = (
        leaf.select(
            pl.nth(1).cast(pl.String).alias("parent_code"),
            pl.nth(2).cast(pl.String).alias("parent_description"),
            pl.nth(3).cast(pl.String).alias("material_code"),
            *month_exprs,
        )
        .unpivot(
            index=["parent_code", "parent_description", "material_code"],
            on=sheet_months,
            variable_name="month_abbr",
            value_name="qty",
        )
        .filter(pl.col("qty").is_not_null())
        .with_columns(
            calculation_month=pl.lit(calculation_month),
            snop_month=pl.col("month_abbr").replace_strict(month_dates),
        )
        .drop("month_abbr")
        .with_columns(parent_code=pl.col("parent_code").cast(pl.Int64))
        .select(
            [
                "calculation_month",
                "snop_month",
                "parent_code",
                "parent_description",
                "material_code",
                "qty",
            ]
        )
    )

    # A material can legitimately appear on multiple type-split rows.
    multi_type = (
        leaf.group_by(
            [
                pl.nth(1).cast(pl.String).alias("parent_code"),
                pl.nth(3).cast(pl.String).alias("material_code"),
            ]
        )
        .len()
        .filter(pl.col("len") > 1)
    )
    if multi_type.height:
        issues.append(
            f"{multi_type.height} material(s) split across multiple rows/types "
            f"(e.g. {multi_type.row(0)[0]}/{multi_type.row(0)[1]})"
        )

    # Grand Total is an independent per-file reconciliation fact.
    grand_total_rows = raw.filter(pl.nth(0).cast(pl.String) == "Grand Total")
    if grand_total_rows.height != 1:
        raise ValueError(
            f"{path.name}: expected exactly 1 'Grand Total' row, "
            f"found {grand_total_rows.height}"
        )
    grand_total_row = grand_total_rows.row(0)
    grand_total: dict[date, float] = {}
    for index, abbr in zip(month_positions, sheet_months):
        cell = grand_total_row[index]
        if cell is None:
            raise ValueError(
                f"{path.name}: Grand Total row has a blank value for month {abbr} "
                "— validation would be meaningless"
            )
        try:
            value = float(cell)
        except (TypeError, ValueError):
            raise ValueError(
                f"{path.name}: Grand Total cell for month {abbr} is not numeric: "
                f"{cell!r}"
            ) from None
        if not math.isfinite(value):
            raise ValueError(
                f"{path.name}: Grand Total cell for month {abbr} must be finite: "
                f"{cell!r}"
            )
        grand_total[month_dates[abbr]] = value

    meta.update(
        {
            "file": path.name,
            "calc_month": calculation_month.strftime("%Y-%m"),
            "snop_months": [f"{year}-{MONTH_NO[abbr]:02d}" for abbr, year in sequence],
            "sheet_months": sheet_months,
            "layout": (
                "merged names+months row"
                if names_idx == anchor_idx
                else "separate header rows"
            ),
            "leaf_rows": leaf.height,
            "issues": issues,
            "grand_total": grand_total,
        }
    )
    return meta, long


def _ym(yyyymm: str) -> tuple[int, int]:
    """Parse a YYYY-MM key into (year, month), raising on malformed keys."""
    try:
        year, month = int(yyyymm[:4]), int(yyyymm[5:7])
    except (IndexError, ValueError):
        raise ValueError(f"malformed month key: {yyyymm!r}") from None
    if len(yyyymm) != 7 or yyyymm[4] != "-" or not 1 <= month <= 12:
        raise ValueError(f"malformed month key: {yyyymm!r}")
    return year, month


def parse_all(
    folder: Path = FORECAST_HISTORY_DIR,
    expected_files: int = EXPECTED_FILES,
) -> tuple[list[dict], list[pl.DataFrame]]:
    """Parse every S&OP grid and require continuous calculation coverage."""
    files = sorted(Path(folder).glob("*.xlsx"))
    if len(files) != expected_files:
        raise FileNotFoundError(
            f"expected {expected_files} S&OP grid files in {folder}, "
            f"found {len(files)}: {[path.name for path in files]}"
        )

    metas: list[dict] = []
    longs: list[pl.DataFrame] = []
    for path in files:
        meta, long = parse_grid(path)
        metas.append(meta)
        longs.append(long)

    calculation_months = sorted(meta["calc_month"] for meta in metas)
    for previous, current in pairwise(calculation_months):
        year_one, month_one = _ym(previous)
        year_two, month_two = _ym(current)
        expected = (year_one + (1 if month_one == 12 else 0), month_one % 12 + 1)
        if (year_two, month_two) != expected:
            raise ValueError(
                f"gap in calculation-month series: {previous} → {current} "
                "(expected continuous monthly coverage)"
            )
    return metas, longs


def _month_date_expr(frame: pl.DataFrame, column: str) -> pl.Expr:
    """Coerce an Excel date-like column to a first-of-month Polars Date."""
    dtype = frame.schema[column]
    if dtype == pl.Date:
        return pl.col(column)
    if isinstance(dtype, pl.Datetime):
        return pl.col(column).cast(pl.Date, strict=False)
    text = pl.col(column).cast(pl.String, strict=False).str.strip_chars()
    return pl.coalesce(
        [
            text.str.strptime(pl.Date, "%Y-%m-%d", strict=False),
            text.str.strptime(pl.Date, "%Y-%m", strict=False),
        ]
    )


def _sample_rows(frame: pl.DataFrame, columns: list[str]) -> list[dict]:
    """Return a small, readable sample for a validation error."""
    return frame.select(columns).head(3).to_dicts()


def _require_ml_columns(raw: pl.DataFrame) -> None:
    missing = [column for column in ML_REQUIRED_COLUMNS if column not in raw.columns]
    if missing:
        raise ValueError(
            "ML history validation failed: missing required column(s): "
            + ", ".join(missing)
        )
    if raw.height == 0:
        raise ValueError("ML history validation failed: the data sheet is empty")


def _normalize_key_value(value: object, source_row: int) -> int:
    """Normalize an exact integer representation without a floating-point hop."""
    if isinstance(value, bool):
        raise TypeError(
            f"data row {source_row + 2}: KEY must be an integer or integer string"
        )
    if isinstance(value, numbers.Integral):
        try:
            candidate = int(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                f"data row {source_row + 2}: KEY must be an integer or integer string"
            ) from exc
    elif isinstance(value, str):
        text = value.strip()
        if not re.fullmatch(r"[+-]?\d+", text):
            raise ValueError(
                f"data row {source_row + 2}: KEY must be an integer or integer string"
            )
        try:
            candidate = int(text)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                f"data row {source_row + 2}: KEY must be an integer or integer string"
            ) from exc
    else:
        raise TypeError(
            f"data row {source_row + 2}: KEY must be an integer or integer string"
        )

    if not INT64_MIN <= candidate <= INT64_MAX:
        raise ValueError(
            f"data row {source_row + 2}: KEY is outside the signed 64-bit range"
        )
    return candidate


def _normalize_key_column(raw: pl.DataFrame) -> list[int]:
    """Convert only exact integer or integer-string KEY values to Int64."""
    values: list[int] = []
    errors: list[str] = []
    for source_row, value in enumerate(raw.get_column("KEY").to_list()):
        try:
            values.append(_normalize_key_value(value, source_row))
        except (TypeError, ValueError) as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError(
            "ML history validation failed: invalid KEY value(s); "
            + "; ".join(errors[:3])
        )
    return values


def _coerce_ml_rows(raw: pl.DataFrame, parent_codes: list[int]) -> pl.DataFrame:
    """Create typed working columns while keeping KEY conversion exact."""
    work = raw
    if ML_OPTIONAL_REFERENCE_COLUMN not in work.columns:
        work = work.with_columns(
            pl.lit(None, dtype=pl.Float64).alias(ML_OPTIONAL_REFERENCE_COLUMN)
        )
    cal_forecast_text = (
        pl.col(ML_OPTIONAL_REFERENCE_COLUMN)
        .cast(pl.String, strict=False)
        .str.strip_chars()
    )
    return work.with_row_index("_source_row").with_columns(
        [
            pl.Series("_parent_code", parent_codes, dtype=pl.Int64),
            pl.col("DESCRIPTION")
            .cast(pl.String, strict=False)
            .alias("_parent_description"),
            _month_date_expr(work, "MONTH_DATE").alias("_snop_month"),
            _month_date_expr(work, "TRAIN_TILL").alias("_train_till"),
            pl.col("PREDICTING_MONTH")
            .cast(pl.String, strict=False)
            .alias("_predicting_month"),
            pl.col("PRED_VOLUME").cast(pl.Float64, strict=False).alias("_pred_volume"),
            pl.col("Oth_Ch_Contr._%")
            .cast(pl.Float64, strict=False)
            .alias("_other_channel_contribution"),
            pl.col(ML_OPTIONAL_REFERENCE_COLUMN)
            .cast(pl.Float64, strict=False)
            .alias("_cal_forecast"),
            (
                cal_forecast_text.is_not_null()
                & (cal_forecast_text != "")
            ).alias("_cal_forecast_supplied"),
        ]
    )


def _validate_ml_mapping_fields(work: pl.DataFrame) -> None:
    """Reject null or unparseable required mapping fields."""
    bad_mapping = work.filter(
        pl.any_horizontal(
            pl.col("_parent_code").is_null(),
            pl.col("_parent_description").is_null(),
            pl.col("_snop_month").is_null(),
            pl.col("_train_till").is_null(),
            pl.col("_predicting_month").is_null(),
            pl.col("_pred_volume").is_null(),
            pl.col("_other_channel_contribution").is_null(),
        )
    )
    if bad_mapping.height:
        raise ValueError(
            "ML history validation failed: required mapping fields are null or "
            "malformed; sample rows: "
            + repr(_sample_rows(bad_mapping, ["_source_row"] + ML_REQUIRED_COLUMNS))
        )


def _validate_ml_dates(work: pl.DataFrame) -> None:
    """Require both authoritative workbook dates to be first-of-month dates."""
    bad_dates = work.filter(
        (pl.col("_snop_month").dt.day() != 1) | (pl.col("_train_till").dt.day() != 1)
    )
    if bad_dates.height:
        raise ValueError(
            "ML history validation failed: MONTH_DATE and TRAIN_TILL must be "
            "valid first-of-month dates; sample rows: "
            + repr(_sample_rows(bad_dates, ["_source_row", "MONTH_DATE", "TRAIN_TILL"]))
        )


def _validate_ml_numeric_bounds(work: pl.DataFrame) -> None:
    """Validate the forecast value and optional reference numeric bounds."""
    bad_forecast = work.filter(
        pl.col("_pred_volume").is_null()
        | (~pl.col("_pred_volume").is_finite())
        | (pl.col("_pred_volume") < 0)
    )
    if bad_forecast.height:
        raise ValueError(
            "ML history validation failed: PRED_VOLUME must be finite and "
            "non-negative; sample rows: "
            + repr(_sample_rows(bad_forecast, ["_source_row", "PRED_VOLUME"]))
        )

    bad_reference = work.filter(
        pl.col("_cal_forecast_supplied")
        & (
            pl.col("_cal_forecast").is_null()
            | (~pl.col("_cal_forecast").is_finite())
            | (pl.col("_cal_forecast") < 0)
        )
    )
    if bad_reference.height:
        raise ValueError(
            "ML history validation failed: supplied Cal_forecast reference "
            "values must be finite and non-negative; sample rows: "
            + repr(
                _sample_rows(
                    bad_reference,
                    ["_source_row", ML_OPTIONAL_REFERENCE_COLUMN],
                )
            )
        )

    bad_contribution = work.filter(
        (~pl.col("_other_channel_contribution").is_finite())
        | (pl.col("_other_channel_contribution") < 0)
        | (pl.col("_other_channel_contribution") >= 1)
    )
    if bad_contribution.height:
        raise ValueError(
            "ML history validation failed: Oth_Ch_Contr._% must be in [0, 1); "
            "sample rows: "
            + repr(_sample_rows(bad_contribution, ["_source_row", "Oth_Ch_Contr._%"]))
        )


def _derive_ml_periods(work: pl.DataFrame) -> pl.DataFrame:
    """Derive authoritative periods and parse the declared horizon."""
    return work.with_columns(
        [
            pl.col("_snop_month").alias("snop_month"),
            pl.col("_train_till").dt.offset_by("1mo").alias("calculation_month"),
            pl.col("_predicting_month")
            .str.extract(r"^M\+([1-5])$", 1)
            .cast(pl.Int64, strict=False)
            .alias("_horizon"),
        ]
    ).with_columns(
        (
            pl.col("snop_month").dt.year() * 12
            + pl.col("snop_month").dt.month()
            - pl.col("calculation_month").dt.year() * 12
            - pl.col("calculation_month").dt.month()
        ).alias("_expected_horizon")
    )


def _validate_ml_horizons(work: pl.DataFrame) -> None:
    """Require M+1 through M+5 syntax and agreement with derived dates."""
    bad_horizons = work.filter(
        pl.col("_horizon").is_null()
        | (pl.col("_horizon") != pl.col("_expected_horizon"))
    )
    if bad_horizons.height:
        raise ValueError(
            "ML history validation failed: PREDICTING_MONTH must be M+1 through "
            "M+5 and match the derived month interval; sample rows: "
            + repr(
                _sample_rows(
                    bad_horizons,
                    [
                        "_source_row",
                        "PREDICTING_MONTH",
                        "TRAIN_TILL",
                        "MONTH_DATE",
                    ],
                )
            )
        )


def _validate_ml_formula(work: pl.DataFrame) -> pl.DataFrame:
    """Validate each supplied Cal_forecast reference against its formula."""
    checked = work.with_columns(
        (pl.col("_pred_volume") / (1 - pl.col("_other_channel_contribution"))).alias(
            "_expected_cal_forecast"
        )
    ).with_columns(
        pl.when(pl.col("_cal_forecast_supplied"))
        .then((pl.col("_cal_forecast") - pl.col("_expected_cal_forecast")).abs())
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("_formula_diff")
    )
    bad_formula = checked.filter(
        pl.col("_cal_forecast_supplied")
        & (
            (~pl.col("_expected_cal_forecast").is_finite())
            | pl.col("_formula_diff").is_null()
            | (~pl.col("_formula_diff").is_finite())
            | (pl.col("_formula_diff") > ML_FORMULA_TOLERANCE)
        )
    )
    if bad_formula.height:
        raise ValueError(
            "ML history validation failed: Cal_forecast does not match "
            "PRED_VOLUME / (1 - Oth_Ch_Contr._%) within "
            f"{ML_FORMULA_TOLERANCE:.0e}; sample rows: "
            + repr(
                _sample_rows(
                    bad_formula,
                    [
                        "_source_row",
                        "PRED_VOLUME",
                        "Oth_Ch_Contr._%",
                        "Cal_forecast",
                        "_formula_diff",
                    ],
                )
            )
        )
    return checked


def _build_ml_frame(work: pl.DataFrame) -> pl.DataFrame:
    """Project validated working rows into the six-column ML contract."""
    return (
        work.select(
            [
                pl.col("calculation_month"),
                pl.col("snop_month"),
                pl.col("_parent_code").alias("parent_code"),
                pl.col("_parent_description").alias("parent_description"),
                pl.col("_pred_volume").alias("qty"),
            ]
        )
        .with_columns(source=pl.lit("ml"))
        .select(OUTPUT_COLUMNS)
    )


def _duplicate_key_count(frame: pl.DataFrame) -> int:
    """Count distinct final keys that occur more than once."""
    return frame.group_by(HISTORY_KEY_COLUMNS).len().filter(pl.col("len") > 1).height


def _validate_ml_unique_keys(frame: pl.DataFrame) -> int:
    """Reject duplicate ML final keys and return the measured duplicate count."""
    duplicate_keys = frame.group_by(HISTORY_KEY_COLUMNS).len().filter(pl.col("len") > 1)
    if duplicate_keys.height:
        raise ValueError(
            "ML history validation failed: duplicate final keys; sample keys: "
            + repr(duplicate_keys.head(3).to_dicts())
        )
    return duplicate_keys.height


def validate_and_normalize_ml_history(raw: pl.DataFrame) -> MlHistoryResult:
    """Validate and normalize ML rows through named, ordered validation phases."""
    _require_ml_columns(raw)
    parent_codes = _normalize_key_column(raw)
    work = _coerce_ml_rows(raw, parent_codes)
    _validate_ml_mapping_fields(work)
    _validate_ml_dates(work)
    _validate_ml_numeric_bounds(work)
    work = _derive_ml_periods(work)
    _validate_ml_horizons(work)
    work = _validate_ml_formula(work)
    normalized = _build_ml_frame(work)
    duplicate_count = _validate_ml_unique_keys(normalized)

    horizon_counts = tuple(
        (
            f"M+{_measured_int(row['_horizon'], 'horizon')}",
            _measured_int(row["len"], "horizon count"),
        )
        for row in work.group_by("_horizon").len().sort("_horizon").to_dicts()
    )
    cal_forecast_checked_rows = work.filter(
        pl.col("_cal_forecast_supplied")
    ).height
    formula_difference = work.get_column("_formula_diff").max()
    max_formula_difference = (
        None
        if formula_difference is None
        else _measured_float(formula_difference, "formula difference")
    )
    evidence = MlValidationEvidence(
        checked_rows=raw.height,
        cal_forecast_checked_rows=cal_forecast_checked_rows,
        max_formula_difference=max_formula_difference,
        formula_tolerance=ML_FORMULA_TOLERANCE,
        horizon_counts=horizon_counts,
        calculation_months=tuple(sorted(work.get_column("calculation_month").unique())),
        snop_months=tuple(sorted(work.get_column("snop_month").unique())),
        duplicate_final_key_count=duplicate_count,
    )
    return MlHistoryResult(
        frame=normalized.sort(HISTORY_SORT_COLUMNS),
        validation=evidence,
    )


def normalize_ml_history(raw: pl.DataFrame) -> pl.DataFrame:
    """Validate and normalize an ML ``data`` sheet, returning only its frame."""
    return validate_and_normalize_ml_history(raw).frame


def parse_ml_history_result(path: Path = ML_HISTORY_PATH) -> MlHistoryResult:
    """Read and validate the ML workbook's ``data`` sheet."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"ML history workbook not found: {path}")
    try:
        raw = pl.read_excel(path, sheet_name="data", engine="calamine")
    except Exception as exc:
        raise ValueError(
            f"unable to read ML history workbook {path} sheet 'data': {exc}"
        ) from exc
    return validate_and_normalize_ml_history(raw)


def parse_ml_history(path: Path = ML_HISTORY_PATH) -> pl.DataFrame:
    """Read and validate the ML workbook, returning its normalized rows."""
    return parse_ml_history_result(path).frame


def validate_tm_history(metas: list[dict], longs: list[pl.DataFrame]) -> pl.DataFrame:
    """Cross-check every melted TM month against its Grand Total row."""
    if len(metas) != len(longs):
        raise ValueError("TM validation failed: metadata and row-frame counts differ")

    validation_rows = []
    for meta, long in zip(metas, longs):
        per_month = long.group_by("snop_month").agg(s=pl.col("qty").sum())
        grand_total = meta["grand_total"]
        expected = pl.DataFrame(
            {
                "snop_month": list(grand_total),
                "gt": list(grand_total.values()),
            }
        )
        joined = per_month.join(expected, on="snop_month", how="full").fill_null(0)
        difference = (joined["s"] - joined["gt"]).abs().max()
        max_difference = _measured_float(difference, "Grand Total difference")
        validation_rows.append(
            {
                "file": meta["file"],
                "leaf_rows": meta["leaf_rows"],
                "total_rows_dropped": meta["total_rows_dropped"],
                "max_abs_diff_vs_grand_total": max_difference,
                "issues": "; ".join(meta["issues"]) or "none",
            }
        )

    validation = pl.DataFrame(validation_rows)
    offenders = validation.filter(
        pl.col("max_abs_diff_vs_grand_total") > GRAND_TOTAL_TOLERANCE
    )
    if offenders.height:
        raise RuntimeError(
            f"grand-total validation failed for {offenders.height} file(s) — "
            "CSV not written:\n"
            f"{offenders.select(['file', 'max_abs_diff_vs_grand_total'])}"
        )
    return validation


def build_tm_history(longs: list[pl.DataFrame]) -> pl.DataFrame:
    """Aggregate material-level TM rows to deterministic parent-level rows."""
    if not longs:
        raise ValueError("TM history validation failed: no parsed source frames")
    all_long = pl.concat(longs)
    parent_qty = all_long.group_by(
        ["parent_code", "calculation_month", "snop_month"]
    ).agg(qty=pl.col("qty").sum())
    descriptions = (
        # Most common description per parent, one literal vote per file:
        # within a file, a parent's description is the one covering the most
        # distinct materials; ties are lexicographically smallest. Across files
        # the description with the most votes wins, with the same tie-break.
        all_long.select(
            [
                "calculation_month",
                "parent_code",
                "parent_description",
                "material_code",
            ]
        )
        .unique()
        .group_by(["calculation_month", "parent_code", "parent_description"])
        .len()
        .sort(
            ["calculation_month", "parent_code", "len", "parent_description"],
            descending=[False, False, True, False],
        )
        .group_by(["calculation_month", "parent_code"], maintain_order=True)
        .first()
        .group_by(["parent_code", "parent_description"])
        .len()
        .sort(
            ["parent_code", "len", "parent_description"],
            descending=[False, True, False],
        )
        .group_by("parent_code", maintain_order=True)
        .first()
        .select(["parent_code", "parent_description"])
    )
    return (
        parent_qty.join(descriptions, on="parent_code", how="left")
        .with_columns(source=pl.lit("tm"))
        .select(OUTPUT_COLUMNS)
        .sort(HISTORY_SORT_COLUMNS)
    )


def _validate_canonical_horizons(frame: pl.DataFrame, label: str) -> None:
    """Require every source row to represent exactly one of M1 through M5."""
    horizon = (
        pl.col("snop_month").dt.year() * 12
        + pl.col("snop_month").dt.month()
        - pl.col("calculation_month").dt.year() * 12
        - pl.col("calculation_month").dt.month()
    )
    invalid = frame.filter(~horizon.is_between(1, 5))
    if invalid.height:
        raise ValueError(
            f"{label} validation failed: canonical forecast horizon must be M1 "
            "through M5; sample rows: "
            + repr(
                invalid.select(
                    ["calculation_month", "snop_month", "parent_code", "source"]
                ).head(3).to_dicts()
            )
        )


def _validate_internal_history(frame: pl.DataFrame, label: str) -> None:
    """Validate the in-memory Date-based history before CSV formatting."""
    if frame.columns != OUTPUT_COLUMNS:
        raise ValueError(
            f"{label} validation failed: expected columns {OUTPUT_COLUMNS}, "
            f"found {frame.columns}"
        )
    if (
        frame.schema["calculation_month"] != pl.Date
        or frame.schema["snop_month"] != pl.Date
    ):
        raise ValueError(
            f"{label} validation failed: month columns must be Polars Date"
        )
    if frame.schema["parent_code"] not in INTEGER_DTYPES:
        raise ValueError(f"{label} validation failed: parent_code must be an integer")
    if frame.schema["parent_description"] != pl.String:
        raise ValueError(
            f"{label} validation failed: parent_description must be a string"
        )
    if frame.schema["qty"] not in FLOAT_DTYPES:
        raise ValueError(f"{label} validation failed: qty must be a float")
    if frame.schema["source"] != pl.String:
        raise ValueError(f"{label} validation failed: source must be a string")
    if frame.height == 0:
        raise ValueError(f"{label} validation failed: frame is empty")

    null_columns = [
        column for column in OUTPUT_COLUMNS if frame.get_column(column).null_count()
    ]
    if null_columns:
        raise ValueError(
            f"{label} validation failed: null values in {', '.join(null_columns)}"
        )
    bad_dates = frame.filter(
        (pl.col("calculation_month").dt.day() != 1)
        | (pl.col("snop_month").dt.day() != 1)
    )
    if bad_dates.height:
        raise ValueError(
            f"{label} validation failed: month values must be first-of-month"
        )
    _validate_canonical_horizons(frame, label)
    if not frame.get_column("qty").is_finite().all():
        raise ValueError(f"{label} validation failed: qty contains non-finite values")
    invalid_sources = frame.filter(~pl.col("source").is_in(FORECAST_SOURCES))
    if invalid_sources.height:
        raise ValueError(
            f"{label} validation failed: unsupported source(s): "
            f"{invalid_sources.get_column('source').unique().to_list()}"
        )
    if _duplicate_key_count(frame):
        raise ValueError(f"{label} validation failed: duplicate final keys")
    if not frame.equals(frame.sort(HISTORY_SORT_COLUMNS)):
        raise ValueError(
            f"{label} validation failed: rows must be sorted by "
            f"{', '.join(HISTORY_SORT_COLUMNS)}"
        )


def _validate_expected_source(
    frame: pl.DataFrame, expected_source: str, label: str
) -> None:
    """Require a source-specific frame to contain exactly one source family."""
    actual_sources = set(frame.get_column("source").unique().to_list())
    if actual_sources != {expected_source}:
        raise ValueError(
            f"{label} validation failed: expected only source "
            f"{expected_source!r}, found {sorted(actual_sources)}"
        )


def combine_forecast_history(tm: pl.DataFrame, ml: pl.DataFrame) -> pl.DataFrame:
    """Append TM and ML alternatives without cross-source aggregation."""
    # Source order is an input detail; only the returned combined frame needs
    # to be deterministic.
    tm = tm.sort(HISTORY_SORT_COLUMNS)
    ml = ml.sort(HISTORY_SORT_COLUMNS)
    _validate_internal_history(tm, "TM source")
    _validate_expected_source(tm, "tm", "TM source")
    _validate_internal_history(ml, "ML source")
    _validate_expected_source(ml, "ml", "ML source")
    combined = pl.concat([tm.select(OUTPUT_COLUMNS), ml.select(OUTPUT_COLUMNS)])
    if combined.height != tm.height + ml.height:
        raise RuntimeError(
            "combined forecast history validation failed: rows were lost while "
            "combining TM and ML sources"
        )
    combined = combined.sort(HISTORY_SORT_COLUMNS)
    _validate_internal_history(combined, "combined forecast history")
    return combined


def _is_valid_month_string(frame: pl.DataFrame, column: str) -> bool:
    values = frame.get_column(column)
    return bool(values.str.contains(r"^\d{4}-(0[1-9]|1[0-2])$").fill_null(False).all())


def validate_formatted_history(
    frame: pl.DataFrame, required_sources: set[str] | None = None
) -> None:
    """Validate the CSV contract and the explicitly required source families.

    By default this validates the published consolidated contract, which must
    contain both TM and ML rows. Source-specific intermediate frames must pass
    their expected family explicitly, for example ``required_sources={"tm"}``.
    """
    if frame.columns != OUTPUT_COLUMNS:
        raise ValueError(
            f"formatted forecast history validation failed: expected columns "
            f"{OUTPUT_COLUMNS}, found {frame.columns}"
        )
    if (
        frame.schema["calculation_month"] != pl.String
        or frame.schema["snop_month"] != pl.String
    ):
        raise ValueError(
            "formatted forecast history validation failed: month columns must be strings"
        )
    if frame.schema["parent_code"] not in INTEGER_DTYPES:
        raise ValueError(
            "formatted forecast history validation failed: parent_code must be an integer"
        )
    if frame.schema["parent_description"] != pl.String:
        raise ValueError(
            "formatted forecast history validation failed: parent_description "
            "must be a string"
        )
    if frame.schema["qty"] not in FLOAT_DTYPES:
        raise ValueError(
            "formatted forecast history validation failed: qty must be a float"
        )
    if frame.schema["source"] != pl.String:
        raise ValueError(
            "formatted forecast history validation failed: source must be a string"
        )
    if frame.height == 0:
        raise ValueError(
            "formatted forecast history validation failed: output is empty"
        )

    null_columns = [
        column for column in OUTPUT_COLUMNS if frame.get_column(column).null_count()
    ]
    if null_columns:
        raise ValueError(
            "formatted forecast history validation failed: null values in "
            + ", ".join(null_columns)
        )
    for column in ("calculation_month", "snop_month"):
        if not _is_valid_month_string(frame, column):
            raise ValueError(
                "formatted forecast history validation failed: "
                f"{column} must use YYYY-MM month keys"
            )
    if not frame.get_column("qty").is_finite().all():
        raise ValueError(
            "formatted forecast history validation failed: qty contains non-finite values"
        )
    formatted_horizon = (
        pl.col("snop_month").str.strptime(pl.Date, "%Y-%m")
        .dt.year() * 12
        + pl.col("snop_month").str.strptime(pl.Date, "%Y-%m").dt.month()
        - pl.col("calculation_month").str.strptime(pl.Date, "%Y-%m").dt.year() * 12
        - pl.col("calculation_month").str.strptime(pl.Date, "%Y-%m").dt.month()
    )
    invalid_horizons = frame.filter(~formatted_horizon.is_between(1, 5))
    if invalid_horizons.height:
        raise ValueError(
            "formatted forecast history validation failed: canonical forecast "
            "horizon must be M1 through M5; sample rows: "
            + repr(
                invalid_horizons.select(
                    ["calculation_month", "snop_month", "parent_code", "source"]
                ).head(3).to_dicts()
            )
        )
    invalid_sources = frame.filter(~pl.col("source").is_in(FORECAST_SOURCES))
    if invalid_sources.height:
        raise ValueError(
            "formatted forecast history validation failed: unsupported source(s): "
            f"{invalid_sources.get_column('source').unique().to_list()}"
        )
    expected_sources = (
        set(FORECAST_SOURCES) if required_sources is None else set(required_sources)
    )
    if not expected_sources:
        raise ValueError(
            "formatted forecast history validation failed: at least one required "
            "source family must be specified"
        )
    actual_sources = set(frame.get_column("source").unique().to_list())
    if actual_sources != expected_sources:
        raise ValueError(
            "formatted forecast history validation failed: expected source "
            f"families {sorted(expected_sources)}, found {sorted(actual_sources)}"
        )
    if _duplicate_key_count(frame):
        raise ValueError(
            "formatted forecast history validation failed: duplicate final keys"
        )
    if not frame.equals(frame.sort(HISTORY_SORT_COLUMNS)):
        raise ValueError(
            "formatted forecast history validation failed: rows must be sorted by "
            f"{', '.join(HISTORY_SORT_COLUMNS)}"
        )


def format_forecast_history_output(
    history: pl.DataFrame, required_sources: set[str] | None = None
) -> pl.DataFrame:
    """Format internal Date month columns for the six-column CSV contract."""
    _validate_internal_history(history, "history formatting")
    formatted = history.with_columns(
        [
            pl.col("calculation_month").dt.strftime("%Y-%m"),
            pl.col("snop_month").dt.strftime("%Y-%m"),
        ]
    ).select(OUTPUT_COLUMNS)
    validate_formatted_history(formatted, required_sources=required_sources)
    return formatted


def _source_summary_row(source: str, frame: pl.DataFrame) -> dict[str, object]:
    """Collect factual source-level row and date coverage measurements."""
    calculation_months = tuple(sorted(frame.get_column("calculation_month").unique()))
    snop_months = tuple(sorted(frame.get_column("snop_month").unique()))
    return {
        "source": source,
        "rows": frame.height,
        "parents": frame.get_column("parent_code").n_unique(),
        "calculation_months": len(calculation_months),
        "calculation_month_start": calculation_months[0].strftime("%Y-%m"),
        "calculation_month_end": calculation_months[-1].strftime("%Y-%m"),
        "snop_months": len(snop_months),
        "snop_month_start": snop_months[0].strftime("%Y-%m"),
        "snop_month_end": snop_months[-1].strftime("%Y-%m"),
    }


def build_source_summary(tm: pl.DataFrame, ml: pl.DataFrame) -> pl.DataFrame:
    """Summarize measured source rows and date coverage without status synthesis."""
    return pl.DataFrame(
        [_source_summary_row("tm", tm), _source_summary_row("ml", ml)]
    ).sort("source")


def build_validation_status(
    tm_validation: pl.DataFrame, ml_validation: MlValidationEvidence
) -> pl.DataFrame:
    """Build explicit passed statuses from completed validation evidence."""
    if tm_validation.is_empty():
        raise ValueError("TM validation status requires completed validation evidence")
    if "max_abs_diff_vs_grand_total" not in tm_validation.columns:
        raise ValueError("TM validation status is missing Grand Total evidence")
    tm_max_difference = _measured_float(
        tm_validation.get_column("max_abs_diff_vs_grand_total").max(),
        "TM validation difference",
    )
    if tm_max_difference > GRAND_TOTAL_TOLERANCE:
        raise ValueError("TM validation status cannot pass failed Grand Total evidence")
    if ml_validation.checked_rows <= 0:
        raise ValueError("ML validation status requires checked rows")
    reference_rows = ml_validation.cal_forecast_checked_rows
    formula_difference = ml_validation.max_formula_difference
    formula_tolerance = ml_validation.formula_tolerance
    if not 0 <= reference_rows <= ml_validation.checked_rows:
        raise ValueError("ML validation status has invalid Cal_forecast evidence")
    if (reference_rows == 0) != (formula_difference is None):
        raise ValueError("ML validation status has inconsistent Cal_forecast evidence")
    if not math.isfinite(formula_tolerance) or formula_tolerance < 0:
        raise ValueError("ML validation status has invalid formula tolerance evidence")
    if formula_difference is not None and (
        not math.isfinite(formula_difference)
        or formula_difference < 0
        or formula_difference > formula_tolerance
    ):
        raise ValueError("ML validation status cannot pass failed formula evidence")
    if ml_validation.duplicate_final_key_count != 0:
        raise ValueError("ML validation status cannot pass duplicate-key evidence")
    return pl.DataFrame(
        {"source": ["tm", "ml"], "status": ["passed", "passed"]}
    )


def build_forecast_history(
    metas: list[dict],
    longs: list[pl.DataFrame],
    ml_path: Path = ML_HISTORY_PATH,
) -> ForecastHistoryBuild:
    """Validate both pipelines and derive the report-ready combined output."""
    tm_validation = validate_tm_history(metas, longs)
    tm = build_tm_history(longs)
    _validate_internal_history(tm, "TM source")
    ml_result = parse_ml_history_result(ml_path)
    ml = ml_result.frame
    _validate_internal_history(ml, "ML source")
    combined_internal = combine_forecast_history(tm, ml)
    consolidated = format_forecast_history_output(combined_internal)
    return ForecastHistoryBuild(
        consolidated=consolidated,
        tm=tm,
        ml=ml,
        tm_validation=tm_validation,
        ml_validation=ml_result.validation,
        validation_status=build_validation_status(tm_validation, ml_result.validation),
        source_summary=build_source_summary(tm, ml),
    )


def build_forecast_history_from_paths(
    tm_folder: Path = FORECAST_HISTORY_DIR,
    ml_path: Path = ML_HISTORY_PATH,
    expected_files: int = EXPECTED_FILES,
) -> ForecastHistoryBuild:
    """Load both source families and return a fully validated build."""
    metas, longs = parse_all(tm_folder, expected_files=expected_files)
    return build_forecast_history(metas, longs, ml_path=ml_path)


def write_forecast_history_atomically(
    history: pl.DataFrame,
    output_path: Path = OUTPUT_CSV,
) -> Path:
    """Atomically publish validated CSV bytes with stable permissions.

    Existing output permission bits are preserved. A new output uses
    ``DEFAULT_OUTPUT_MODE`` (0644). All in-memory and round-trip validation
    happens before ``os.replace``, so failed validation never opens or
    truncates the prior output.
    """
    validate_formatted_history(history)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_mode = (
        stat.S_IMODE(output_path.stat().st_mode)
        if output_path.exists()
        else DEFAULT_OUTPUT_MODE
    )

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)
    try:
        history.write_csv(temporary_path)
        round_trip = pl.read_csv(temporary_path)
        validate_formatted_history(round_trip)
        if not round_trip.equals(history):
            raise RuntimeError(
                "forecast history validation failed: CSV round-trip changed output"
            )
        os.chmod(temporary_path, output_mode)
        with temporary_path.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return output_path


def generate_forecast_history(
    output_path: Path = OUTPUT_CSV,
    tm_folder: Path = FORECAST_HISTORY_DIR,
    ml_path: Path = ML_HISTORY_PATH,
    expected_files: int = EXPECTED_FILES,
) -> ForecastHistoryBuild:
    """Build and atomically publish a validated current forecast history."""
    build = build_forecast_history_from_paths(
        tm_folder=tm_folder,
        ml_path=ml_path,
        expected_files=expected_files,
    )
    write_forecast_history_atomically(build.consolidated, output_path=output_path)
    return build
