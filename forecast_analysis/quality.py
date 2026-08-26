"""Source-aware data-quality populations and exception evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import polars as pl

from ._utils import require_columns
from .contracts import (
    ACTUAL_STATUSES,
    ANALYSIS_COLUMNS,
    HIERARCHY_STATUSES,
    PAIR_STATUSES,
    SOURCE_AVAILABILITY_STATUSES,
)

QUALITY_CATEGORIES = (
    "hierarchy",
    "actual",
    "pairs",
    "source_availability",
)
QUALITY_COUNT_COLUMNS = [
    "category",
    "status",
    "status_group",
    "observations",
    "products",
    "sources",
    "target_months",
    "forecast_kl",
    "actual_kl",
    "severity",
    "blocking",
    "explanation",
]
QUALITY_COUNT_SCHEMA = {
    "category": pl.String,
    "status": pl.String,
    "status_group": pl.String,
    "observations": pl.Int64,
    "products": pl.Int64,
    "sources": pl.Int64,
    "target_months": pl.Int64,
    "forecast_kl": pl.Float64,
    "actual_kl": pl.Float64,
    "severity": pl.String,
    "blocking": pl.Boolean,
    "explanation": pl.String,
}
QUALITY_EXCEPTION_METADATA_COLUMNS = [
    "quality_category",
    "quality_status",
    "quality_status_group",
    "quality_explanation",
]
QUALITY_GOOD_STATUSES = {
    "hierarchy": ("mapped",),
    "actual": ("matched_positive",),
    "pairs": ("complete",),
    "source_availability": ("both_sources",),
}
QUALITY_EXPLANATIONS: dict[str, dict[str, str]] = {
    "hierarchy": {
        "mapped": "The product has one cleaned, agreeing brand mapping and can be grouped by brand.",
        "unmapped": "No usable brand mapping was found; the row remains in totals under Unmapped.",
        "conflict": "Multiple brand values were found for the product; the row remains visible under Hierarchy conflict.",
    },
    "actual": {
        "matched_positive": "A positive actual exists; the row may contribute to ratio metrics.",
        "actual_only": "An actual exists without a forecast key in the selected population; it remains in the denominator and exception evidence.",
        "matched_zero": "A zero actual exists; the row contributes to volume and error counts but not ratio denominators.",
        "missing": "No actual exists for this product and target month; the row remains in coverage but not metric denominators.",
    },
    "pairs": {
        "complete": "Both selected vintages exist; positive-actual rows are eligible for comparable metrics.",
        "missing_a": "Vintage A is unavailable under the selected rule; the product-target remains in coverage.",
        "missing_b": "Vintage B is unavailable under the selected rule; the product-target remains in coverage.",
        "missing_both": "Neither selected vintage is available under the selected rule; the product-target remains in coverage.",
        "missing_actual": "Both vintages exist but the actual is missing; the pair is excluded from metric denominators.",
        "zero_actual": "Both vintages exist with a zero actual; the pair is visible but excluded from ratio denominators.",
    },
    "source_availability": {
        "tm_only": "The product-target is forecast by TM but not ML in the selected population.",
        "ml_only": "The product-target is forecast by ML but not TM in the selected population.",
        "both_sources": "The product-target is represented by both TM and ML.",
    },
}


def _deduplicate_observations(frame: pl.DataFrame) -> pl.DataFrame:
    """Reduce repeated vintages to one product-target observation for quality counts."""
    keys = ["source", "parent_code", "snop_month"]
    sort_columns = [column for column in [*keys, "calculation_month"] if column in frame.columns]
    ordered = frame.sort(sort_columns) if sort_columns else frame
    return ordered.unique(subset=keys, keep="last", maintain_order=True)


def _safe_float(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{field_name} must contain numeric values")
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must contain numeric values") from exc


def _safe_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{field_name} must contain integer values")
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must contain integer values") from exc


def _numeric_total(frame: pl.DataFrame, column: str) -> float:
    if column not in frame.columns or frame.height == 0:
        return 0.0
    values = frame.get_column(column).drop_nulls()
    if values.len() == 0:
        return 0.0
    return _safe_float(values.sum(), column)


def _profile(frame: pl.DataFrame) -> dict[str, object]:
    return {
        "observations": frame.height,
        "products": frame.get_column("parent_code").n_unique()
        if "parent_code" in frame.columns
        else 0,
        "sources": frame.get_column("source").n_unique()
        if "source" in frame.columns
        else 0,
        "target_months": frame.get_column("snop_month").n_unique()
        if "snop_month" in frame.columns
        else 0,
        "forecast_kl": _numeric_total(frame, "forecast_kl"),
        "actual_kl": _numeric_total(frame, "actual_kl"),
    }


def _actual_profile(frame: pl.DataFrame) -> dict[str, object]:
    values = _profile(frame)
    if "available_sources" in frame.columns:
        sources: set[str] = set()
        for raw in frame["available_sources"].drop_nulls().to_list():
            sources.update(str(raw).split(" | "))
        values["sources"] = len(sources)
    return values


def _status_group(category: str, status: str) -> str:
    if category == "pairs" and status in {
        "missing_a",
        "missing_b",
        "missing_both",
    }:
        return "incomplete"
    return status


def _severity(category: str, status: str) -> str:
    good_statuses = {
        "mapped",
        "matched_positive",
        "complete",
        "both_sources",
    }
    if status in good_statuses:
        return "info"
    return "warning"


def _count_table(
    category: str,
    frame: pl.DataFrame,
    status_column: str,
    statuses: tuple[str, ...],
    *,
    profile: Callable[[pl.DataFrame], dict[str, object]] = _profile,
) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for status in statuses:
        subset = frame.filter(pl.col(status_column) == status)
        values = profile(subset)
        rows.append(
            {
                "category": category,
                "status": status,
                "status_group": _status_group(category, status),
                **values,
                "severity": _severity(category, status),
                "blocking": False,
                "explanation": QUALITY_EXPLANATIONS[category][status],
            }
        )
    return pl.DataFrame(rows, schema=QUALITY_COUNT_SCHEMA).select(QUALITY_COUNT_COLUMNS)


@dataclass
class _AvailabilityRecord:
    parent_code: int
    parent_description: str | None
    hierarchy_description: str | None
    brand: str | None
    mapping_status: str | None
    mapping_diagnostic: str | None
    snop_month: object
    actual_kl: float | None
    forecast_kl: float = 0.0
    sources: set[str] = field(default_factory=set)


def _source_availability_population(frame: pl.DataFrame) -> pl.DataFrame:
    require_columns(
        frame,
        ["source", "parent_code", "snop_month"],
        "source availability population",
    )
    grouped: dict[tuple[int, object], _AvailabilityRecord] = {}
    horizon_values: dict[tuple[int, object], set[int]] = {}
    if "forecast_horizon_months" in frame.columns:
        for horizon_row in frame.select(
            ["parent_code", "snop_month", "forecast_horizon_months"]
        ).drop_nulls().unique().to_dicts():
            horizon_key = (
                _safe_int(horizon_row["parent_code"], "parent_code"),
                horizon_row["snop_month"],
            )
            horizon_value = horizon_row["forecast_horizon_months"]
            if isinstance(horizon_value, bool) or not isinstance(horizon_value, int):
                raise ValueError("forecast_horizon_months must contain integer values")
            horizon_values.setdefault(horizon_key, set()).add(horizon_value)
    observation_frame = (
        _deduplicate_observations(frame)
        if "calculation_month" in frame.columns
        else frame
    )
    sort_columns = [column for column in ["parent_code", "snop_month", "source"] if column in observation_frame.columns]
    for row in observation_frame.sort(sort_columns).to_dicts():
        key = (_safe_int(row["parent_code"], "parent_code"), row["snop_month"])
        item = grouped.setdefault(
            key,
            _AvailabilityRecord(
                parent_code=key[0],
                parent_description=row.get("parent_description"),
                hierarchy_description=row.get("hierarchy_description"),
                brand=row.get("brand"),
                mapping_status=row.get("mapping_status"),
                mapping_diagnostic=row.get("mapping_diagnostic"),
                snop_month=key[1],
                actual_kl=(
                    _safe_float(row["actual_kl"], "actual_kl")
                    if row.get("actual_kl") is not None
                    else None
                ),
            ),
        )
        item.sources.add(str(row["source"]))
        if row.get("forecast_kl") is not None:
            item.forecast_kl += _safe_float(row["forecast_kl"], "forecast_kl")
        if item.actual_kl is None and row.get("actual_kl") is not None:
            item.actual_kl = _safe_float(row["actual_kl"], "actual_kl")

    rows: list[dict[str, object]] = []
    for item in grouped.values():
        if item.sources == {"tm"}:
            status = "tm_only"
        elif item.sources == {"ml"}:
            status = "ml_only"
        elif item.sources == {"tm", "ml"}:
            status = "both_sources"
        else:
            continue
        rows.append(
            {
                "source_availability": status,
                "available_sources": " | ".join(sorted(item.sources)),
                "available_horizons": ", ".join(
                    str(value)
                    for value in sorted(
                        horizon_values.get((item.parent_code, item.snop_month), set())
                    )
                ),
                "parent_code": item.parent_code,
                "parent_description": item.parent_description,
                "hierarchy_description": item.hierarchy_description,
                "brand": item.brand,
                "mapping_status": item.mapping_status,
                "mapping_diagnostic": item.mapping_diagnostic,
                "snop_month": item.snop_month,
                "actual_kl": item.actual_kl,
                "forecast_kl": (
                    item.forecast_kl if len(item.sources) == 1 else None
                ),
            }
        )
    schema = {
        "source_availability": pl.String,
        "available_sources": pl.String,
        "available_horizons": pl.String,
        "parent_code": pl.Int64,
        "parent_description": pl.String,
        "hierarchy_description": pl.String,
        "brand": pl.String,
        "mapping_status": pl.String,
        "mapping_diagnostic": pl.String,
        "snop_month": pl.Date,
        "actual_kl": pl.Float64,
        "forecast_kl": pl.Float64,
    }
    if not rows:
        return pl.DataFrame(schema=schema)
    return pl.DataFrame(rows, schema=schema).with_columns(
        pl.col("parent_code").cast(pl.Int64),
        pl.col("snop_month").cast(pl.Date),
        pl.col("actual_kl").cast(pl.Float64),
        pl.col("forecast_kl").cast(pl.Float64),
    )


def _availability_profile(frame: pl.DataFrame) -> dict[str, object]:
    values = _profile(frame)
    if frame.height == 0:
        values["sources"] = 0
    else:
        status = frame.get_column("source_availability").item(0)
        values["sources"] = 2 if status == "both_sources" else 1
    return values


def _actual_quality_population(
    population: pl.DataFrame,
    actual_population: pl.DataFrame,
    availability_population: pl.DataFrame,
) -> pl.DataFrame:
    """Build one source-independent actual row per product-target key."""
    require_columns(
        population,
        ["parent_code", "snop_month", "forecast_kl", "source"],
        "quality forecast population",
    )
    require_columns(
        actual_population,
        ["parent_code", "snop_month", "actual_kl"],
        "quality actual population",
    )
    availability = _source_availability_population(availability_population)
    availability_by_key = {
        (row["parent_code"], row["snop_month"]): row
        for row in availability.to_dicts()
    }
    records: dict[tuple[object, object], dict[str, object]] = {}
    source_sets: dict[tuple[object, object], set[str]] = {}
    source_forecasts: dict[tuple[object, object], dict[str, float]] = {}

    def record_for(row: dict[str, object]) -> dict[str, object]:
        key = (row["parent_code"], row["snop_month"])
        record = records.setdefault(
            key,
            {
                "parent_code": key[0],
                "snop_month": key[1],
                "parent_description": row.get("parent_description"),
                "hierarchy_description": row.get("hierarchy_description"),
                "brand": row.get("brand"),
                "mapping_status": row.get("mapping_status"),
                "mapping_diagnostic": row.get("mapping_diagnostic"),
                "candidate_brands": row.get("candidate_brands"),
                "candidate_descriptions": row.get("candidate_descriptions"),
                "actual_kl": row.get("actual_kl"),
                "forecast_kl": None,
                "forecast_present": False,
            },
        )
        for field_name in (
            "parent_description",
            "hierarchy_description",
            "brand",
            "mapping_status",
            "mapping_diagnostic",
            "candidate_brands",
            "candidate_descriptions",
        ):
            if record[field_name] is None and row.get(field_name) is not None:
                record[field_name] = row[field_name]
        if record["actual_kl"] is None and row.get("actual_kl") is not None:
            record["actual_kl"] = row["actual_kl"]
        return record

    for row in _deduplicate_observations(population).to_dicts():
        record = record_for(row)
        key = (record["parent_code"], record["snop_month"])
        source_sets.setdefault(key, set()).add(str(row["source"]))
        record["forecast_present"] = True
        source_name = str(row["source"])
        source_totals = source_forecasts.setdefault(key, {})
        source_totals[source_name] = source_totals.get(source_name, 0.0) + _safe_float(
            row["forecast_kl"], "forecast_kl"
        )
        existing_forecast = record["forecast_kl"]
        existing_total = (
            0.0
            if existing_forecast is None
            else _safe_float(existing_forecast, "forecast_kl")
        )
        record["forecast_kl"] = existing_total + _safe_float(
            row["forecast_kl"], "forecast_kl"
        )

    for row in actual_population.to_dicts():
        record_for(row)

    rows: list[dict[str, object]] = []
    for key, record in records.items():
        if record["mapping_status"] is None:
            record["mapping_status"] = "unmapped"
            if record["mapping_diagnostic"] is None:
                record["mapping_diagnostic"] = "no hierarchy mapping"
        actual_value = record["actual_kl"]
        actual_status = (
            "missing"
            if actual_value is None
            else "matched_zero"
            if actual_value == 0
            else "matched_positive"
        )
        availability_row = availability_by_key.get(key)
        sources = source_sets.get(key, set())
        source_totals = source_forecasts.get(key, {})
        rows.append(
            {
                **record,
                "source": " | ".join(sorted(sources)) or None,
                "forecast_kl": (
                    record["forecast_kl"]
                    if len(source_totals) <= 1
                    else None
                ),
                "tm_forecast_kl": source_totals.get("tm"),
                "ml_forecast_kl": source_totals.get("ml"),
                "available_sources": (
                    availability_row.get("available_sources")
                    if availability_row is not None
                    else None
                ),
                "available_horizons": (
                    availability_row.get("available_horizons")
                    if availability_row is not None
                    else None
                ),
                "source_availability": (
                    availability_row.get("source_availability")
                    if availability_row is not None
                    else None
                ),
                "actual_status": actual_status,
                "actual_coverage_status": (
                    "actual_only"
                    if not record["forecast_present"]
                    else "forecast_only"
                    if actual_status == "missing"
                    else "matched"
                ),
            }
        )
    schema = {
        "source": pl.String,
        "parent_code": pl.Int64,
        "parent_description": pl.String,
        "hierarchy_description": pl.String,
        "brand": pl.String,
        "mapping_status": pl.String,
        "mapping_diagnostic": pl.String,
        "candidate_brands": pl.String,
        "candidate_descriptions": pl.String,
        "snop_month": pl.Date,
        "actual_status": pl.String,
        "actual_coverage_status": pl.String,
        "actual_kl": pl.Float64,
        "forecast_kl": pl.Float64,
        "tm_forecast_kl": pl.Float64,
        "ml_forecast_kl": pl.Float64,
        "forecast_present": pl.Boolean,
        "available_sources": pl.String,
        "available_horizons": pl.String,
        "source_availability": pl.String,
    }
    return pl.DataFrame(rows, schema=schema).sort(["parent_code", "snop_month"])


def _decorate_exceptions(
    frame: pl.DataFrame,
    category: str,
    status_column: str,
    *,
    hierarchy_diagnostics: pl.DataFrame | None = None,
    availability_evidence: pl.DataFrame | None = None,
) -> pl.DataFrame:
    require_columns(frame, [status_column], f"{category} quality population")
    prepared = frame
    if category == "hierarchy" and hierarchy_diagnostics is not None:
        require_columns(
            hierarchy_diagnostics,
            ["parent_code"],
            "hierarchy quality diagnostics",
        )
        diagnostic_columns = [
            column
            for column in ("candidate_brands", "candidate_descriptions", "diagnostic")
            if column in hierarchy_diagnostics.columns
        ]
        if diagnostic_columns:
            aliases = {
                column: f"__hierarchy_diagnostic_{column}"
                for column in diagnostic_columns
            }
            prepared = prepared.join(
                hierarchy_diagnostics.select(
                    [
                        "parent_code",
                        *[
                            pl.col(column).alias(aliases[column])
                            for column in diagnostic_columns
                        ],
                    ]
                ),
                on="parent_code",
                how="left",
            )
            prepared = prepared.with_columns(
                [
                    (
                        pl.when(pl.col(column).is_null())
                        .then(pl.col(aliases[column]))
                        .otherwise(pl.col(column))
                        .alias(column)
                        if column in prepared.columns
                        else pl.col(aliases[column]).alias(column)
                    )
                    for column in diagnostic_columns
                ]
            ).drop(list(aliases.values()))
    if availability_evidence is not None:
        require_columns(
            availability_evidence,
            ["parent_code", "snop_month", "available_sources"],
            "source availability evidence",
        )
        evidence_columns = [
            column
            for column in (
                "available_sources",
                "available_horizons",
                "source_availability",
            )
            if column in availability_evidence.columns and column not in prepared.columns
        ]
        if evidence_columns:
            prepared = prepared.join(
                availability_evidence.select(
                    ["parent_code", "snop_month", *evidence_columns]
                ),
                on=["parent_code", "snop_month"],
                how="left",
            )
    if "actual_coverage_status" not in prepared.columns:
        prepared = prepared.with_columns(
            pl.lit(None, dtype=pl.String).alias("actual_coverage_status")
        )
    exception_mask = ~pl.col(status_column).is_in(QUALITY_GOOD_STATUSES[category])
    if category == "actual":
        exception_mask = exception_mask | (
            pl.col("actual_coverage_status") == "actual_only"
        )
    prepared = prepared.filter(exception_mask)
    if "source" not in prepared.columns:
        prepared = prepared.with_columns(pl.lit(None, dtype=pl.String).alias("source"))
    for column, dtype in {
        "parent_description": pl.String,
        "hierarchy_description": pl.String,
        "brand": pl.String,
        "mapping_status": pl.String,
        "mapping_diagnostic": pl.String,
        "candidate_brands": pl.String,
        "candidate_descriptions": pl.String,
        "actual_status": pl.String,
        "actual_coverage_status": pl.String,
        "forecast_kl": pl.Float64,
        "actual_kl": pl.Float64,
        "forecast_present": pl.Boolean,
        "pair_status": pl.String,
        "available_sources": pl.String,
        "available_horizons": pl.String,
        "source_availability": pl.String,
    }.items():
        if column not in prepared.columns:
            prepared = prepared.with_columns(pl.lit(None, dtype=dtype).alias(column))
    prepared = prepared.with_columns(
        pl.lit(category).cast(pl.String).alias("quality_category"),
        pl.when(
            (pl.lit(category) == "actual")
            & (pl.col("actual_coverage_status") == "actual_only")
        )
        .then(pl.lit("actual_only"))
        .otherwise(pl.col(status_column).cast(pl.String))
        .alias("quality_status"),
        pl.when(
            (pl.lit(category) == "actual")
            & (pl.col("actual_coverage_status") == "actual_only")
        )
        .then(pl.lit("actual_only"))
        .otherwise(pl.col(status_column).cast(pl.String))
        .map_elements(
            lambda value: _status_group(category, str(value)),
            return_dtype=pl.String,
        )
        .alias("quality_status_group"),
        pl.when(
            (pl.lit(category) == "actual")
            & (pl.col("actual_coverage_status") == "actual_only")
        )
        .then(
            pl.lit(
                "An actual exists without a forecast key in the selected population; "
                "it remains in the denominator and this exception download."
            )
        )
        .otherwise(
            pl.col(status_column).map_elements(
                lambda value: QUALITY_EXPLANATIONS[category][str(value)],
                return_dtype=pl.String,
            )
        )
        .alias("quality_explanation"),
    )
    metadata = [column for column in QUALITY_EXCEPTION_METADATA_COLUMNS if column in prepared.columns]
    remaining = [column for column in prepared.columns if column not in metadata]
    return prepared.select([*metadata, *remaining])


@dataclass(frozen=True)
class QualityView:
    """All quality populations and evidence for one shared dashboard selection."""

    hierarchy: pl.DataFrame
    actual: pl.DataFrame
    pairs: pl.DataFrame
    source_availability: pl.DataFrame
    exceptions: dict[str, pl.DataFrame]
    explanations: dict[str, dict[str, str]]
    blocking_errors: tuple[str, ...] = ()

    @property
    def counts(self) -> pl.DataFrame:
        """Return every category/status count in one panel-ready table."""
        return pl.concat(
            [self.hierarchy, self.actual, self.pairs, self.source_availability],
            how="vertical_relaxed",
        ).select(QUALITY_COUNT_COLUMNS)

    @property
    def non_blocking_diagnostics(self) -> pl.DataFrame:
        """Return quality diagnostics that do not block dashboard construction."""
        return self.counts.filter(~pl.col("blocking"))

    @property
    def actuals(self) -> pl.DataFrame:
        """Plural alias for callers that name the actual population explicitly."""
        return self.actual

    def explanation_text(self, category: str) -> str:
        """Render one concise human explanation for a category."""
        return " ".join(self.explanations[category].values())


def build_quality_view(
    population: pl.DataFrame,
    actual_population: pl.DataFrame,
    coverage_pairs: pl.DataFrame,
    *,
    source_availability_population: pl.DataFrame | None = None,
    selected_sources: tuple[str, ...] | None = None,
    hierarchy_diagnostics: pl.DataFrame | None = None,
    blocking_errors: tuple[str, ...] = (),
) -> QualityView:
    """Build hierarchy, actual, pair, and source-availability quality populations.

    ``population`` and ``coverage_pairs`` are selected by the dashboard, but
    ``coverage_pairs`` must be built before pair-status filters are applied. This
    is the invariant that keeps excluded metric rows visible in quality totals.
    ``blocking_errors`` is deliberately separate from the non-blocking tables;
    malformed required inputs never become ordinary quality rows.
    """
    require_columns(population, ANALYSIS_COLUMNS, "quality analysis population")
    require_columns(
        actual_population,
        ["parent_code", "snop_month", "actual_kl"],
        "quality actual population",
    )
    require_columns(
        coverage_pairs,
        ["source", "parent_code", "snop_month", "pair_status", "actual_kl"],
        "quality coverage pairs",
    )
    availability_population = (
        source_availability_population
        if source_availability_population is not None
        else population
    )
    require_columns(
        availability_population,
        ["source", "parent_code", "snop_month"],
        "quality source availability population",
    )

    actual_quality_population = _actual_quality_population(
        population,
        actual_population,
        availability_population,
    )
    hierarchy = _count_table(
        "hierarchy",
        actual_quality_population,
        "mapping_status",
        HIERARCHY_STATUSES,
        profile=_actual_profile,
    )
    actual = _count_table(
        "actual",
        actual_quality_population,
        "actual_status",
        ACTUAL_STATUSES,
        profile=_actual_profile,
    )
    pairs = _count_table(
        "pairs",
        coverage_pairs,
        "pair_status",
        PAIR_STATUSES,
    )
    availability = _source_availability_population(availability_population)
    if selected_sources == ("tm",):
        availability = availability.filter(
            pl.col("source_availability") != "ml_only"
        )
    elif selected_sources == ("ml",):
        availability = availability.filter(
            pl.col("source_availability") != "tm_only"
        )
    availability_statuses = SOURCE_AVAILABILITY_STATUSES
    if selected_sources == ("tm",):
        availability_statuses = ("tm_only", "both_sources")
    elif selected_sources == ("ml",):
        availability_statuses = ("ml_only", "both_sources")
    source_availability = _count_table(
        "source_availability",
        availability,
        "source_availability",
        availability_statuses,
        profile=_availability_profile,
    )

    exceptions = {
        "hierarchy": _decorate_exceptions(
            actual_quality_population,
            "hierarchy",
            "mapping_status",
            hierarchy_diagnostics=hierarchy_diagnostics,
        ),
        "actual": _decorate_exceptions(
            actual_quality_population,
            "actual",
            "actual_status",
        ),
        "pairs": _decorate_exceptions(
            coverage_pairs,
            "pairs",
            "pair_status",
            availability_evidence=availability,
        ),
        "source_availability": _decorate_exceptions(
            availability,
            "source_availability",
            "source_availability",
        ),
    }
    return QualityView(
        hierarchy=hierarchy,
        actual=actual,
        pairs=pairs,
        source_availability=source_availability,
        exceptions=exceptions,
        explanations=QUALITY_EXPLANATIONS,
        blocking_errors=tuple(str(error) for error in blocking_errors),
    )
