"""Pure, auditable SKU post-mortem projections for the forecast cockpit.

The module has one orchestration seam: :func:`build_product_postmortem`.
It accepts the canonical long analysis population and its canonical Vintage A/B
pair projection, then returns boring Polars frames plus two small value objects.
No UI, external service, or causal inference belongs here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
import math
from typing import Literal, cast

import polars as pl

from ._utils import require_columns
from .contracts import (
    ANALYSIS_COLUMNS,
    DEFAULT_REVISION_TOLERANCE_KL,
    FORECAST_SOURCES,
    REVISION_CLASSIFICATION_DECIMAL_PLACES,
    normalize_revision_tolerance,
)
from .filters import with_display_brand
from .vintages import PAIR_COLUMNS


ROLLING_COLUMNS = [
    "source",
    "parent_code",
    "snop_month",
    "calculation_month",
    "forecast_horizon_months",
    "forecast_kl",
    "actual_kl",
    "actual_status",
    "error_kl",
    "absolute_error_kl",
    "bias_kl",
    "bias_pct",
    "forecast_accuracy_pct",
]
ROLLING_SCHEMA = {
    "source": pl.String,
    "parent_code": pl.Int64,
    "snop_month": pl.Date,
    "calculation_month": pl.Date,
    "forecast_horizon_months": pl.Int64,
    "forecast_kl": pl.Float64,
    "actual_kl": pl.Float64,
    "actual_status": pl.String,
    "error_kl": pl.Float64,
    "absolute_error_kl": pl.Float64,
    "bias_kl": pl.Float64,
    "bias_pct": pl.Float64,
    "forecast_accuracy_pct": pl.Float64,
}

REVISION_OUTCOME_COLUMNS = [
    "source",
    "parent_code",
    "snop_month",
    "actual_kl",
    "vintage_a_forecast_kl",
    "vintage_b_forecast_kl",
    "revision_kl",
    "error_improvement_kl",
    "revision_direction",
    "revision_outcome",
    "pair_status",
]
REVISION_OUTCOME_SCHEMA = {
    "source": pl.String,
    "parent_code": pl.Int64,
    "snop_month": pl.Date,
    "actual_kl": pl.Float64,
    "vintage_a_forecast_kl": pl.Float64,
    "vintage_b_forecast_kl": pl.Float64,
    "revision_kl": pl.Float64,
    "error_improvement_kl": pl.Float64,
    "revision_direction": pl.String,
    "revision_outcome": pl.String,
    "pair_status": pl.String,
}

PEER_COLUMNS = [
    "cohort_type",
    "cohort_value",
    "cohort_size",
    "eligible_count",
    "median_accuracy_pct",
    "p25_accuracy_pct",
    "p75_accuracy_pct",
    "selected_accuracy_pct",
    "selected_eligible",
    "selected_rank",
    "selected_percentile_pct",
]
PEER_SCHEMA = {
    "cohort_type": pl.String,
    "cohort_value": pl.String,
    "cohort_size": pl.Int64,
    "eligible_count": pl.Int64,
    "median_accuracy_pct": pl.Float64,
    "p25_accuracy_pct": pl.Float64,
    "p75_accuracy_pct": pl.Float64,
    "selected_accuracy_pct": pl.Float64,
    "selected_eligible": pl.Boolean,
    "selected_rank": pl.Int64,
    "selected_percentile_pct": pl.Float64,
}

COMMENTARY_COLUMNS = [
    "category",
    "severity",
    "confidence",
    "headline",
    "body",
    "evidence_refs",
    "repeatability",
]
COMMENTARY_SCHEMA = {
    "category": pl.String,
    "severity": pl.String,
    "confidence": pl.String,
    "headline": pl.String,
    "body": pl.String,
    "evidence_refs": pl.List(pl.String),
    "repeatability": pl.String,
}


@dataclass(frozen=True)
class TargetMonthSummary:
    """Auditable target-month KPIs; undefined ratios are represented by ``None``."""

    vintage_count: int
    latest_calculation_month: date | None
    latest_forecast_kl: float | None
    actual_kl: float | None
    absolute_error_kl: float | None
    bias_kl: float | None
    bias_pct: float | None
    forecast_accuracy_pct: float | None
    first_to_latest_fva_kl: float | None
    revision_efficiency_pct: float | None
    material_revisions: int
    material_revision_hits: int
    material_hit_rate_pct: float | None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ForwardTreatment:
    """Planner treatment selected from the deliberately small action vocabulary."""

    action: Literal["hold", "rebase", "rephase", "scenario", "escalate"]
    impact_kl: float | None
    rationale: str
    confidence: str
    review_trigger: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ProductPostmortemView:
    """Complete post-mortem projection for one source/SKU/target-month selection."""

    parent_code: int
    target_month: date
    source: str
    parent_description: str | None
    brand: str | None
    sku_class: str | None
    status: str
    status_message: str
    rolling_performance: pl.DataFrame
    revision_outcomes: pl.DataFrame
    summary: TargetMonthSummary
    peer_benchmarks: pl.DataFrame
    commentary: pl.DataFrame
    treatment: ForwardTreatment


def _empty_frame(schema: dict[str, pl.DataType], columns: list[str]) -> pl.DataFrame:
    return pl.DataFrame(schema=schema).select(columns)


def _normalize_month(value: object) -> date:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return date(value.year, value.month, 1)
    if isinstance(value, str):
        for fmt in ("%Y-%m", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(value.strip(), fmt).date()
                return date(parsed.year, parsed.month, 1)
            except ValueError:
                continue
    raise ValueError(f"target month must be a date or YYYY-MM value, got {value!r}")


def _parent_code(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("parent_code must be an integer")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError("parent_code must be an integer")
    try:
        return int(cast(str | int | float, value))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("parent_code must be an integer") from exc


def _number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise TypeError(f"numeric post-mortem value expected, got {value!r}")
    try:
        converted = float(cast(str | int | float, value))
    except (TypeError, ValueError, OverflowError) as exc:
        raise TypeError(f"numeric post-mortem value expected, got {value!r}") from exc
    return converted if math.isfinite(converted) else None


def _required_number(value: object, field_name: str) -> float:
    converted = _number(value)
    if converted is None:
        raise TypeError(f"{field_name} must contain a finite numeric value")
    return converted


def _quantile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    result = pl.Series(values, dtype=pl.Float64).quantile(
        quantile,
        interpolation="linear",
    )
    return cast(float | None, result)


def _accuracy(forecast: float | None, actual: float | None) -> float | None:
    if forecast is None or actual is None or actual <= 0:
        return None
    return (1.0 - abs(forecast - actual) / actual) * 100.0


def _latest_forecasts(frame: pl.DataFrame) -> pl.DataFrame:
    """Keep one deterministic latest-calculation row per source/SKU/target."""
    prepared = frame
    if "sku_class" not in prepared.columns:
        prepared = prepared.with_columns(pl.lit("Unclassified").alias("sku_class"))
    prepared = with_display_brand(prepared)
    return (
        prepared.filter(
            pl.col("calculation_month").is_not_null()
            & pl.col("forecast_kl").is_not_null()
        )
        .sort(
            ["source", "parent_code", "snop_month", "calculation_month", "forecast_horizon_months"],
            descending=[False, False, False, True, True],
        )
        .unique(
            subset=["source", "parent_code", "snop_month"],
            keep="first",
            maintain_order=True,
        )
    )


def _target_vintages(
    frame: pl.DataFrame,
    source: str,
    parent_code: int,
    target: date,
) -> pl.DataFrame:
    """Return one deterministic forecast for every available target vintage."""
    selected = frame.filter(
        (pl.col("source") == source)
        & (pl.col("parent_code") == parent_code)
        & (pl.col("snop_month") == target)
        & pl.col("calculation_month").is_not_null()
        & pl.col("forecast_kl").is_not_null()
    )
    return (
        selected.sort(
            ["calculation_month", "forecast_horizon_months"],
            descending=[False, True],
        )
        .unique(subset=["calculation_month"], keep="first", maintain_order=True)
        .sort("calculation_month")
    )


def _rolling_performance(
    latest: pl.DataFrame,
    source: str,
    parent_code: int,
    target: date,
    rolling_months: int | None,
) -> pl.DataFrame:
    selected = latest.filter(
        (pl.col("source") == source)
        & (pl.col("parent_code") == parent_code)
        & (pl.col("snop_month") <= target)
    ).sort("snop_month")
    if rolling_months is not None:
        selected = selected.tail(rolling_months)
    if selected.height == 0:
        return _empty_frame(ROLLING_SCHEMA, ROLLING_COLUMNS)
    return (
        selected.with_columns(
            (pl.col("forecast_kl") - pl.col("actual_kl")).alias("error_kl"),
        )
        .with_columns(
            pl.col("error_kl").abs().alias("absolute_error_kl"),
            pl.col("error_kl").alias("bias_kl"),
            pl.when(pl.col("actual_kl") > 0)
            .then(pl.col("error_kl") / pl.col("actual_kl") * 100)
            .otherwise(pl.lit(None, dtype=pl.Float64))
            .alias("bias_pct"),
            pl.when(pl.col("actual_kl") > 0)
            .then((1 - pl.col("error_kl").abs() / pl.col("actual_kl")) * 100)
            .otherwise(pl.lit(None, dtype=pl.Float64))
            .alias("forecast_accuracy_pct"),
        )
        .select(ROLLING_COLUMNS)
    )


def _revision_outcomes(
    pairs: pl.DataFrame,
    source: str,
    parent_code: int,
    target: date,
    tolerance: float,
    rolling_months: int | None,
) -> pl.DataFrame:
    selected = pairs.filter(
        (pl.col("source") == source)
        & (pl.col("parent_code") == parent_code)
        & (pl.col("snop_month") <= target)
    ).sort("snop_month")
    if rolling_months is not None:
        selected = selected.tail(rolling_months)
    if selected.height == 0:
        return _empty_frame(REVISION_OUTCOME_SCHEMA, REVISION_OUTCOME_COLUMNS)
    revision = pl.col("revision_kl").round(
        REVISION_CLASSIFICATION_DECIMAL_PLACES
    )
    improvement = pl.col("error_improvement_kl").round(
        REVISION_CLASSIFICATION_DECIMAL_PLACES
    )
    return (
        selected.with_columns(
            pl.when(revision.is_null())
            .then(pl.lit(None, dtype=pl.String))
            .when(revision > tolerance)
            .then(pl.lit("up"))
            .when(revision < -tolerance)
            .then(pl.lit("down"))
            .otherwise(pl.lit("unchanged"))
            .alias("revision_direction"),
            pl.when(improvement.is_null())
            .then(pl.lit(None, dtype=pl.String))
            .when(improvement > tolerance)
            .then(pl.lit("improved"))
            .when(improvement < -tolerance)
            .then(pl.lit("worsened"))
            .otherwise(pl.lit("neutral"))
            .alias("revision_outcome"),
        )
        .select(REVISION_OUTCOME_COLUMNS)
    )


def _revision_summary(
    vintages: pl.DataFrame,
    tolerance: float,
) -> tuple[float | None, float | None, int, int, float | None]:
    if vintages.height < 2:
        return None, None, 0, 0, None
    rows = vintages.select(["forecast_kl", "actual_kl"]).to_dicts()
    actual = _number(rows[-1]["actual_kl"])
    errors = [
        abs(
            _required_number(row["forecast_kl"], "forecast_kl")
            - _required_number(row["actual_kl"], "actual_kl")
        )
        if row["actual_kl"] is not None
        else None
        for row in rows
    ]
    # Existing dashboard revision KPIs deliberately exclude missing and zero actuals.
    if actual is None or actual <= 0:
        return None, None, 0, 0, None
    first_to_latest = (
        errors[0] - errors[-1]
        if errors[0] is not None and errors[-1] is not None
        else None
    )
    material = 0
    hits = 0
    revised_magnitude = 0.0
    total_improvement = 0.0
    for previous, current, previous_error, current_error in zip(
        rows, rows[1:], errors, errors[1:]
    ):
        if previous_error is None or current_error is None:
            continue
        revision = round(
            _required_number(current["forecast_kl"], "forecast_kl")
            - _required_number(previous["forecast_kl"], "forecast_kl"),
            REVISION_CLASSIFICATION_DECIMAL_PLACES,
        )
        improvement = round(
            previous_error - current_error,
            REVISION_CLASSIFICATION_DECIMAL_PLACES,
        )
        if abs(revision) > tolerance:
            material += 1
            revised_magnitude += abs(revision)
            total_improvement += improvement
            if improvement > tolerance:
                hits += 1
    efficiency = (
        total_improvement / revised_magnitude * 100
        if revised_magnitude > 0
        else None
    )
    hit_rate = hits / material * 100 if material else None
    return first_to_latest, efficiency, material, hits, hit_rate


def _peer_benchmarks(
    latest: pl.DataFrame,
    source: str,
    parent_code: int,
    target: date,
) -> pl.DataFrame:
    selected = latest.filter(
        (pl.col("source") == source)
        & (pl.col("snop_month") == target)
    ).with_columns(
        pl.when(pl.col("actual_kl") > 0)
        .then(
            (
                1
                - (pl.col("forecast_kl") - pl.col("actual_kl")).abs()
                / pl.col("actual_kl")
            )
            * 100
        )
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("_accuracy")
    )
    if selected.height == 0:
        return _empty_frame(PEER_SCHEMA, PEER_COLUMNS)
    selected_code = parent_code
    selected_row = selected.filter(pl.col("parent_code") == selected_code).head(1)
    if selected_row.height == 0:
        return _empty_frame(PEER_SCHEMA, PEER_COLUMNS)

    rows: list[dict[str, object]] = []
    selected_brand = str(selected_row["brand_display"].item())
    selected_class = str(selected_row["sku_class"].item())
    cohort_keys = (
        ("brand", selected_brand),
        ("sku_class", selected_class),
        ("brand_sku_class", f"{selected_brand} · {selected_class}"),
    )
    for cohort_type, cohort_value in cohort_keys:
        if cohort_type == "brand":
            cohort = selected.filter(pl.col("brand_display") == selected_brand)
        elif cohort_type == "sku_class":
            cohort = selected.filter(pl.col("sku_class") == selected_class)
        else:
            cohort = selected.filter(
                (pl.col("brand_display") == selected_brand)
                & (pl.col("sku_class") == selected_class)
            )
        eligible = cohort.filter(pl.col("_accuracy").is_not_null()).sort(
            ["_accuracy", "parent_code"], descending=[True, False]
        )
        values = [
            _required_number(value, "forecast_accuracy_pct")
            for value in eligible["_accuracy"].to_list()
        ]
        selected_accuracy = _number(selected_row["_accuracy"].item())
        rank: int | None = None
        percentile: float | None = None
        if selected_accuracy is not None and values:
            rank = next(
                index
                for index, row in enumerate(eligible.to_dicts(), start=1)
                if row["parent_code"] == selected_code
            )
            percentile = (
                sum(value <= selected_accuracy for value in values)
                / len(values)
                * 100
            )
        rows.append(
            {
                "cohort_type": cohort_type,
                "cohort_value": cohort_value,
                "cohort_size": len(values),
                "eligible_count": len(values),
                "median_accuracy_pct": _quantile(values, 0.5),
                "p25_accuracy_pct": _quantile(values, 0.25),
                "p75_accuracy_pct": _quantile(values, 0.75),
                "selected_accuracy_pct": selected_accuracy,
                "selected_eligible": selected_accuracy is not None,
                "selected_rank": rank,
                "selected_percentile_pct": percentile,
            }
        )
    return pl.DataFrame(rows, schema=PEER_SCHEMA).select(PEER_COLUMNS)


def _commentary_row(
    category: str,
    severity: str,
    confidence: str,
    headline: str,
    body: str,
    refs: list[str],
    repeatability: str,
) -> dict[str, object]:
    return {
        "category": category,
        "severity": severity,
        "confidence": confidence,
        "headline": headline,
        "body": body,
        "evidence_refs": refs,
        "repeatability": repeatability,
    }


def _missing_external_evidence(
    external_evidence: pl.DataFrame | None,
    parent_code: int,
    target_month: date,
) -> list[str]:
    evidence_names = ("promotion", "availability", "price", "distribution")
    if external_evidence is None or external_evidence.height == 0:
        return list(evidence_names)
    scoped = external_evidence
    if "parent_code" in scoped.columns:
        scoped = scoped.filter(pl.col("parent_code") == parent_code)
    if "snop_month" in scoped.columns:
        scoped = scoped.filter(pl.col("snop_month") == target_month)
    return [
        name
        for name in evidence_names
        if name not in scoped.columns
        or scoped.get_column(name).drop_nulls().len() == 0
    ]


def _commentary(
    summary: TargetMonthSummary,
    peers: pl.DataFrame,
    *,
    external_evidence: pl.DataFrame | None,
    parent_code: int,
    target_month: date,
    tolerance: float,
) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    if summary.vintage_count == 0:
        rows.append(
            _commentary_row(
                "history",
                "critical",
                "high",
                "No forecast history",
                "The selected SKU-target month has no usable forecast vintage.",
                [],
                "not_assessed",
            )
        )
    elif summary.vintage_count < 2:
        calculation_month = (
            summary.latest_calculation_month.isoformat()
            if summary.latest_calculation_month
            else "none"
        )
        rows.append(
            _commentary_row(
                "history",
                "warning",
                "high",
                "Insufficient forecast history",
                "Only one usable vintage is available; revision behavior and "
                "repeatability cannot be assessed.",
                [f"target_history:{calculation_month}"],
                "not_assessed",
            )
        )
    if summary.actual_kl is None:
        rows.append(
            _commentary_row(
                "performance",
                "warning",
                "high",
                "Actual volume is unavailable",
                "Accuracy and bias ratios are undefined until the target-month "
                "actual is available.",
                ["target_actual:missing"],
                "not_assessed",
            )
        )
    elif summary.actual_kl == 0:
        rows.append(
            _commentary_row(
                "performance",
                "warning",
                "high",
                "Actual volume is zero",
                "Absolute error remains visible, but ratio metrics are "
                "intentionally undefined for a zero actual.",
                ["target_actual:zero"],
                "single_observation",
            )
        )
    elif summary.absolute_error_kl is not None:
        materially_missed = (
            summary.forecast_accuracy_pct is not None
            and summary.forecast_accuracy_pct < 80
        )
        direction = (
            "over-forecast"
            if summary.bias_kl is not None and summary.bias_kl > tolerance
            else "under-forecast"
            if summary.bias_kl is not None and summary.bias_kl < -tolerance
            else "near actual"
        )
        rows.append(
            _commentary_row(
                "performance",
                "critical" if materially_missed else "observation",
                "high",
                "Latest forecast materially missed"
                if materially_missed
                else f"Latest position is {direction}",
                f"Latest absolute error is {summary.absolute_error_kl:.3g} KL "
                f"against {summary.actual_kl:.3g} KL actual volume "
                f"({summary.forecast_accuracy_pct:.1f}% accuracy).",
                ["target_performance:latest"],
                "single_observation",
            )
        )
    fva = summary.first_to_latest_fva_kl
    repeatability = (
        "repeatable" if summary.material_revisions >= 2 else "single_observation"
    )
    if fva is not None and fva < -tolerance:
        rows.append(
            _commentary_row(
                "revision",
                "critical",
                "high",
                "Revisions reduced forecast value",
                f"First-to-latest error improvement is {fva:.3g} KL; later "
                "revisions left the target farther from actual.",
                ["revision_outcomes:target"],
                repeatability,
            )
        )
    elif fva is not None and fva > tolerance:
        rows.append(
            _commentary_row(
                "revision",
                "positive",
                "high",
                "Revisions improved forecast value",
                f"First-to-latest error improvement is +{fva:.3g} KL.",
                ["revision_outcomes:target"],
                repeatability,
            )
        )
    for peer in peers.to_dicts():
        selected = peer["selected_accuracy_pct"]
        median = peer["median_accuracy_pct"]
        if not isinstance(selected, (int, float)) or not isinstance(
            median, (int, float)
        ):
            continue
        if selected < median:
            rows.append(
                _commentary_row(
                    "peer",
                    "warning",
                    "medium",
                    f"SKU trails {peer['cohort_type']} peers",
                    f"Selected accuracy is {selected:.1f}% versus a "
                    f"{median:.1f}% median across {peer['eligible_count']} "
                    "eligible peers.",
                    [f"peer:{peer['cohort_type']}:{peer['cohort_value']}"],
                    "single_observation",
                )
            )
            break
    missing = _missing_external_evidence(
        external_evidence,
        parent_code,
        target_month,
    )
    if missing:
        rows.append(
            _commentary_row(
                "evidence_gap",
                "warning",
                "high",
                "External cause is unverified",
                "Promotion, availability, price, and distribution evidence are "
                "not connected to this projection; no external cause is inferred.",
                [f"missing:{name}" for name in missing],
                "not_assessed",
            )
        )
    return pl.DataFrame(rows, schema=COMMENTARY_SCHEMA).select(COMMENTARY_COLUMNS)


def _treatment(
    summary: TargetMonthSummary,
    vintages: pl.DataFrame,
    tolerance: float,
) -> ForwardTreatment:
    if summary.actual_kl is None:
        return ForwardTreatment(
            "hold",
            None,
            "Hold the current treatment because the target-month actual is "
            "unavailable.",
            "high",
            "Review when the target-month actual lands.",
        )
    if summary.actual_kl == 0:
        return ForwardTreatment(
            "hold",
            None,
            "Hold until positive-volume evidence is available; ratio-based "
            "treatment is not meaningful for a zero actual.",
            "high",
            "Review after the next positive-volume observation.",
        )
    if summary.vintage_count < 2:
        return ForwardTreatment(
            "hold",
            None,
            "Hold the baseline because forecast history is insufficient to "
            "separate level from revision behavior.",
            "high",
            "Review after at least two usable vintages are available.",
        )
    fva = summary.first_to_latest_fva_kl
    if fva is not None and fva < -tolerance:
        first_forecast = _number(vintages.head(1)["forecast_kl"].item())
        impact = (
            first_forecast - summary.latest_forecast_kl
            if first_forecast is not None
            and summary.latest_forecast_kl is not None
            else None
        )
        impact_text = f"{impact:+.3g} KL" if impact is not None else "the prior level"
        return ForwardTreatment(
            "rebase",
            impact,
            f"Use a guarded rebase of {impact_text} toward the "
            "better-supported forecast history; do not extrapolate a cause "
            "that is not evidenced.",
            "medium",
            "Review after the next two forecast updates; cancel the rebase if "
            "error improvement turns positive.",
        )
    return ForwardTreatment(
        "hold",
        0.0,
        "Hold the current baseline because available forecast history does not "
        "show a material first-to-latest deterioration.",
        "medium",
        "Review after the next material revision or actual close.",
    )


def build_product_postmortem(
    analysis_frame: pl.DataFrame,
    vintage_pair_frame: pl.DataFrame,
    parent_code: int,
    target_month: object,
    *,
    source: str = "tm",
    rolling_months: int | None = 6,
    revision_tolerance_kl: float = DEFAULT_REVISION_TOLERANCE_KL,
    external_evidence: pl.DataFrame | None = None,
) -> ProductPostmortemView:
    """Derive the complete pure post-mortem projection for one SKU.

    ``analysis_frame`` must be the canonical long analysis population and
    ``vintage_pair_frame`` must be produced by :func:`select_vintage_pair`.
    Latest forecast means the greatest available calculation month for each
    target month. Positive error improvement means the revision moved closer
    to actual; negative means it worsened the outcome. No external cause is
    inferred from forecast, actual, hierarchy, or SKU-class facts.
    """
    require_columns(
        analysis_frame,
        ANALYSIS_COLUMNS,
        "post-mortem analysis population",
    )
    require_columns(
        vintage_pair_frame,
        PAIR_COLUMNS,
        "post-mortem vintage pair population",
    )
    normalized_source = str(source).strip().lower()
    if normalized_source not in FORECAST_SOURCES:
        raise ValueError(f"unsupported post-mortem source {source!r}")
    normalized_parent = _parent_code(parent_code)
    normalized_target = _normalize_month(target_month)
    if rolling_months is not None and (
        isinstance(rolling_months, bool)
        or not isinstance(rolling_months, int)
        or rolling_months < 1
    ):
        raise ValueError("rolling_months must be a positive integer or None")
    tolerance = round(
        normalize_revision_tolerance(revision_tolerance_kl),
        REVISION_CLASSIFICATION_DECIMAL_PLACES,
    )

    latest = _latest_forecasts(analysis_frame)
    rolling = _rolling_performance(
        latest,
        normalized_source,
        normalized_parent,
        normalized_target,
        rolling_months,
    )
    revisions = _revision_outcomes(
        vintage_pair_frame,
        normalized_source,
        normalized_parent,
        normalized_target,
        tolerance,
        rolling_months,
    )
    vintages = _target_vintages(
        analysis_frame,
        normalized_source,
        normalized_parent,
        normalized_target,
    )
    latest_target = latest.filter(
        (pl.col("source") == normalized_source)
        & (pl.col("parent_code") == normalized_parent)
        & (pl.col("snop_month") == normalized_target)
    ).head(1)
    if latest_target.height:
        latest_row = latest_target.to_dicts()[0]
        description = (
            str(latest_row["parent_description"])
            if latest_row["parent_description"] is not None
            else None
        )
        brand = latest_row["brand"]
        sku_class = latest_row["sku_class"] or "Unclassified"
    else:
        description = brand = sku_class = None

    if vintages.height:
        row = vintages.tail(1).to_dicts()[0]
        latest_forecast = _number(row["forecast_kl"])
        actual = _number(row["actual_kl"])
        absolute_error = (
            abs(latest_forecast - actual)
            if latest_forecast is not None and actual is not None
            else None
        )
        bias = (
            latest_forecast - actual
            if latest_forecast is not None and actual is not None
            else None
        )
        latest_calc_value = row["calculation_month"]
        latest_calc = (
            latest_calc_value if isinstance(latest_calc_value, date) else None
        )
    else:
        latest_forecast = actual = absolute_error = bias = latest_calc = None
    first_to_latest, efficiency, material, hits, hit_rate = _revision_summary(
        vintages,
        tolerance,
    )
    summary = TargetMonthSummary(
        vintage_count=vintages.height,
        latest_calculation_month=latest_calc,
        latest_forecast_kl=latest_forecast,
        actual_kl=actual,
        absolute_error_kl=absolute_error,
        bias_kl=bias,
        bias_pct=(
            bias / actual * 100
            if bias is not None and actual is not None and actual > 0
            else None
        ),
        forecast_accuracy_pct=_accuracy(latest_forecast, actual),
        first_to_latest_fva_kl=first_to_latest,
        revision_efficiency_pct=efficiency,
        material_revisions=material,
        material_revision_hits=hits,
        material_hit_rate_pct=hit_rate,
    )
    peers = _peer_benchmarks(
        latest,
        normalized_source,
        normalized_parent,
        normalized_target,
    )
    commentary = _commentary(
        summary,
        peers,
        external_evidence=external_evidence,
        parent_code=normalized_parent,
        target_month=normalized_target,
        tolerance=tolerance,
    )
    treatment = _treatment(summary, vintages, tolerance)
    if vintages.height == 0:
        status = "no_history"
        status_message = (
            "No usable forecast vintage is available for this SKU-target month."
        )
    elif vintages.height < 2:
        status = "insufficient_history"
        status_message = (
            "At least two usable vintages are required for revision analysis."
        )
    else:
        status = "ready"
        status_message = (
            "Latest forecast, revision outcomes, peer benchmarks, and treatment "
            "are available."
        )
    return ProductPostmortemView(
        parent_code=normalized_parent,
        target_month=normalized_target,
        source=normalized_source,
        parent_description=description,
        brand=str(brand) if brand is not None else None,
        sku_class=str(sku_class) if sku_class is not None else None,
        status=status,
        status_message=status_message,
        rolling_performance=rolling,
        revision_outcomes=revisions,
        summary=summary,
        peer_benchmarks=peers,
        commentary=commentary,
        treatment=treatment,
    )


__all__ = [
    "ForwardTreatment",
    "ProductPostmortemView",
    "TargetMonthSummary",
    "build_product_postmortem",
]
