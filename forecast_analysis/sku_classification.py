"""Rolling national ABC classification derived from parent-level actuals."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from typing import cast

import polars as pl

from ._utils import require_columns
from .contracts import ACTUAL_COLUMNS

SKU_CLASS_A = "A"
SKU_CLASS_B = "B"
SKU_CLASS_C = "C"
SKU_CLASS_UNCLASSIFIED = "Unclassified"
SKU_CLASSES = (
    SKU_CLASS_A,
    SKU_CLASS_B,
    SKU_CLASS_C,
    SKU_CLASS_UNCLASSIFIED,
)
SKU_CLASS_LOOKBACK_MONTHS = 6
SKU_CLASS_A_CUMULATIVE_SHARE = 0.70
SKU_CLASS_B_CUMULATIVE_SHARE = 0.90
SKU_CLASS_COLUMNS = [
    "parent_code",
    "snop_month",
    "sku_class",
    "sku_class_as_of_month",
    "sku_class_window_start",
    "sku_class_actual_6m_kl",
    "sku_class_contribution_pct",
    "sku_class_cumulative_pct",
    "sku_class_is_carried_forward",
]
SKU_CLASS_SCHEMA = {
    "parent_code": pl.Int64,
    "snop_month": pl.Date,
    "sku_class": pl.String,
    "sku_class_as_of_month": pl.Date,
    "sku_class_window_start": pl.Date,
    "sku_class_actual_6m_kl": pl.Float64,
    "sku_class_contribution_pct": pl.Float64,
    "sku_class_cumulative_pct": pl.Float64,
    "sku_class_is_carried_forward": pl.Boolean,
}


def _month(value: object) -> date:
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        raise ValueError(f"SKU class month must be a date, got {value!r}")
    return date(value.year, value.month, 1)


def _shift_month(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, zero_based_month = divmod(month_index, 12)
    return date(year, zero_based_month + 1, 1)


def _month_range(start: date, end: date) -> tuple[date, ...]:
    months: list[date] = []
    current = start
    while current <= end:
        months.append(current)
        current = _shift_month(current, 1)
    return tuple(months)


def required_sku_class_actual_months(
    target_months: Iterable[object],
) -> tuple[date, ...]:
    """Return analysis months plus the six completed months before the first target."""
    targets = sorted({_month(value) for value in target_months})
    if not targets:
        return ()
    history_start = _shift_month(targets[0], -SKU_CLASS_LOOKBACK_MONTHS)
    return _month_range(history_start, targets[-1])


def _empty_classifications() -> pl.DataFrame:
    return pl.DataFrame(schema=SKU_CLASS_SCHEMA).select(SKU_CLASS_COLUMNS)


def build_sku_classifications(
    actuals: pl.DataFrame,
    target_months: Iterable[object],
) -> pl.DataFrame:
    """Classify parent products monthly from national rolling actual contribution.

    Each target month uses the preceding six completed actual months. Parents are
    ranked by six-month actual KL descending with ``parent_code`` as the stable
    tie-breaker. The parent that crosses 70% remains A; the parent that crosses
    90% remains B; remaining positive-volume parents are C. Targets beyond the
    latest actual month carry forward the latest complete classification snapshot.
    Parents without positive rolling actuals are attached later as Unclassified.
    """
    require_columns(actuals, ACTUAL_COLUMNS, "SKU class actual history")
    targets = sorted({_month(value) for value in target_months})
    if not targets or actuals.height == 0:
        return _empty_classifications()

    history = actuals.select(ACTUAL_COLUMNS).with_columns(
        pl.col("parent_code").cast(pl.Int64),
        pl.col("snop_month").cast(pl.Date),
        pl.col("actual_kl").cast(pl.Float64),
    )
    invalid = history.filter(
        pl.col("actual_kl").is_null()
        | ~pl.col("actual_kl").is_finite()
        | (pl.col("actual_kl") < 0)
    )
    if invalid.height:
        raise ValueError(
            "SKU class actual history must contain finite non-negative actual_kl; "
            f"sample rows: {invalid.head(3).to_dicts()}"
        )

    latest_actual_value = history.get_column("snop_month").max()
    if latest_actual_value is None:
        return _empty_classifications()
    latest_actual_month = cast(date, latest_actual_value)

    available_actual_months = set(
        history.get_column("snop_month").unique().to_list()
    )
    rows: list[dict[str, object]] = []
    for target_month in targets:
        requested_as_of = _shift_month(target_month, -1)
        as_of_month = min(requested_as_of, latest_actual_month)
        window_start = _shift_month(
            as_of_month,
            -(SKU_CLASS_LOOKBACK_MONTHS - 1),
        )
        required_window = set(_month_range(window_start, as_of_month))
        if not required_window.issubset(available_actual_months):
            continue
        rolling = (
            history.filter(
                pl.col("snop_month").is_between(
                    window_start,
                    as_of_month,
                    closed="both",
                )
            )
            .group_by("parent_code")
            .agg(sku_class_actual_6m_kl=pl.col("actual_kl").sum())
            .filter(pl.col("sku_class_actual_6m_kl") > 0)
            .sort(
                ["sku_class_actual_6m_kl", "parent_code"],
                descending=[True, False],
            )
        )
        national_actual_value = rolling.get_column("sku_class_actual_6m_kl").sum()
        if national_actual_value is None:
            continue
        national_actual = cast(float, national_actual_value)
        if national_actual <= 0:
            continue

        cumulative_share = 0.0
        carried_forward = requested_as_of > latest_actual_month
        for parent_code_value, rolling_actual_value in rolling.iter_rows():
            parent_code = cast(int, parent_code_value)
            rolling_actual = cast(float, rolling_actual_value)
            contribution_share = rolling_actual / national_actual
            threshold_share = round(cumulative_share, 12)
            if threshold_share < SKU_CLASS_A_CUMULATIVE_SHARE:
                sku_class = SKU_CLASS_A
            elif threshold_share < SKU_CLASS_B_CUMULATIVE_SHARE:
                sku_class = SKU_CLASS_B
            else:
                sku_class = SKU_CLASS_C
            cumulative_share = round(cumulative_share + contribution_share, 12)
            rows.append(
                {
                    "parent_code": parent_code,
                    "snop_month": target_month,
                    "sku_class": sku_class,
                    "sku_class_as_of_month": as_of_month,
                    "sku_class_window_start": window_start,
                    "sku_class_actual_6m_kl": rolling_actual,
                    "sku_class_contribution_pct": contribution_share * 100,
                    "sku_class_cumulative_pct": cumulative_share * 100,
                    "sku_class_is_carried_forward": carried_forward,
                }
            )

    if not rows:
        return _empty_classifications()
    return pl.DataFrame(rows, schema=SKU_CLASS_SCHEMA).select(SKU_CLASS_COLUMNS).sort(
        ["snop_month", "sku_class_actual_6m_kl", "parent_code"],
        descending=[False, True, False],
    )


def attach_sku_classification(
    frame: pl.DataFrame,
    classifications: pl.DataFrame,
) -> pl.DataFrame:
    """Attach monthly SKU class facts and preserve missing history explicitly."""
    require_columns(frame, ["parent_code", "snop_month"], "SKU class population")
    require_columns(
        classifications,
        SKU_CLASS_COLUMNS,
        "SKU class classification table",
    )
    return frame.join(
        classifications,
        on=["parent_code", "snop_month"],
        how="left",
    ).with_columns(
        pl.col("sku_class").fill_null(SKU_CLASS_UNCLASSIFIED)
    )
