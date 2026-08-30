"""Browser-facing adapter for the canonical forecast-analysis view model.

The analytical core remains in :mod:`forecast_analysis`. This module owns the
HTTP/browser contract: request validation, filter construction, bounded JSON
projections, product-detail selection, and request-faithful CSV exports.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime
import json
import math
from pathlib import Path
from threading import RLock
from typing import Any, Literal, cast

import polars as pl

from forecast_analysis import (
    AnalysisDataset,
    DashboardFilters,
    VintageRule,
    available_filter_values,
    build_analysis_dataset,
    build_dashboard_view,
    build_product_detail,
    load_analysis_inputs,
)
from forecast_analysis.dashboard import DashboardView

DEFAULT_FORECAST_HISTORY = Path(
    "artifacts/forecast_history/consolidated/forecast_history_waterfall.csv"
)
DEFAULT_HIERARCHY = Path("artifacts/ph/PH_FG.xlsx")
DEFAULT_ACTUALS = Path("artifacts/secondary_sales")
QUALITY_CATEGORIES = ("hierarchy", "actual", "pairs", "source_availability")
ACCURACY_BANDS = {
    "below_0": (-1_000_000.0, 0.0),
    "0_50": (0.0, 50.0),
    "50_100": (50.0, 100.0),
    "above_100": (100.0, 1_000_000.0),
}
BIAS_BANDS = {
    "below_0": (-1_000_000.0, 0.0),
    "0_50": (0.0, 50.0),
    "above_50": (50.0, 1_000_000.0),
}


class DashboardRequestError(ValueError):
    """A browser request violated the dashboard adapter contract."""


@dataclass(frozen=True)
class _ComputedView:
    request: dict[str, Any]
    options: dict[str, Any]
    view: DashboardView
    product_detail: dict[str, Any] | None
    payload: dict[str, Any]


def _iso(value: date | datetime) -> str:
    return value.isoformat()


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, (date, datetime)):
        return _iso(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    if hasattr(value, "item"):
        try:
            return _json_value(value.item())
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _rows(
    frame: pl.DataFrame,
    *,
    columns: tuple[str, ...] | list[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    selected = frame
    if columns is not None:
        available = [column for column in columns if column in selected.columns]
        selected = selected.select(available)
    if limit is not None:
        selected = selected.head(limit)
    return [_json_value(row) for row in selected.to_dicts()]


def _frame_payload(
    frame: pl.DataFrame,
    *,
    columns: tuple[str, ...] | list[str] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    return {
        "total": frame.height,
        "rows": _rows(frame, columns=columns, limit=limit),
    }


def _parse_bool(payload: dict[str, Any], field: str, default: bool = False) -> bool:
    value = payload.get(field, default)
    if not isinstance(value, bool):
        raise DashboardRequestError(f"{field} must be a boolean")
    return value


def _parse_string(
    payload: dict[str, Any],
    field: str,
    *,
    default: str | None = None,
    allowed: set[str] | None = None,
) -> str | None:
    value = payload.get(field, default)
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise DashboardRequestError(f"{field} must be a string or null")
    value = value.strip()
    if allowed is not None and value not in allowed:
        raise DashboardRequestError(
            f"{field} must be one of {', '.join(sorted(allowed))}"
        )
    return value


def _parse_int(
    payload: dict[str, Any],
    field: str,
    *,
    minimum: int | None = None,
) -> int | None:
    value = payload.get(field)
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise DashboardRequestError(f"{field} must be an integer or null")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise DashboardRequestError(f"{field} must be an integer or null") from exc
    if isinstance(value, float) and not value.is_integer():
        raise DashboardRequestError(f"{field} must be an integer or null")
    if minimum is not None and parsed < minimum:
        raise DashboardRequestError(f"{field} must be at least {minimum}")
    return parsed


def _parse_float(
    payload: dict[str, Any],
    field: str,
    *,
    default: float = 0.0,
    minimum: float | None = None,
) -> float:
    value = payload.get(field, default)
    if value in (None, ""):
        value = default
    if isinstance(value, bool):
        raise DashboardRequestError(f"{field} must be a finite number")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise DashboardRequestError(f"{field} must be a finite number") from exc
    if not math.isfinite(parsed):
        raise DashboardRequestError(f"{field} must be a finite number")
    if minimum is not None and parsed < minimum:
        raise DashboardRequestError(f"{field} must be at least {minimum}")
    return parsed


def _parse_date(value: Any, field: str) -> date | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise DashboardRequestError(f"{field} must be an ISO date or null")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise DashboardRequestError(f"{field} must be an ISO date or null") from exc


def _single_choice(value: str | None) -> tuple[str, ...] | None:
    return None if value is None else (value,)


def _latest_timestamp(paths: tuple[Path, ...]) -> str:
    files: list[Path] = []
    for path in paths:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(candidate for candidate in path.rglob("*") if candidate.is_file())
    if not files:
        return "unknown"
    latest = max(path.stat().st_mtime for path in files)
    return datetime.fromtimestamp(latest).astimezone().isoformat(timespec="seconds")


class DashboardDataService:
    """Deep adapter from browser requests to the canonical dashboard model.

    The immutable dataset is loaded once. Computed views are cached by the
    canonical request JSON; cache access is synchronized while expensive Polars
    computation occurs outside the lock.
    """

    def __init__(
        self,
        dataset: AnalysisDataset,
        *,
        refresh_timestamp: str,
        source_label: str,
        cache_size: int = 32,
    ) -> None:
        if cache_size < 1:
            raise ValueError("cache_size must be positive")
        self.dataset = dataset
        self.refresh_timestamp = refresh_timestamp
        self.source_label = source_label
        self.cache_size = cache_size
        self._cache: OrderedDict[str, _ComputedView] = OrderedDict()
        self._cache_lock = RLock()

    @classmethod
    def from_paths(
        cls,
        forecast_history_path: Path = DEFAULT_FORECAST_HISTORY,
        hierarchy_path: Path = DEFAULT_HIERARCHY,
        actuals_path: Path = DEFAULT_ACTUALS,
        *,
        cache_size: int = 32,
    ) -> "DashboardDataService":
        paths = (
            Path(forecast_history_path).resolve(),
            Path(hierarchy_path).resolve(),
            Path(actuals_path).resolve(),
        )
        inputs = load_analysis_inputs(*paths)
        dataset = build_analysis_dataset(inputs)
        return cls(
            dataset,
            refresh_timestamp=_latest_timestamp(paths),
            source_label=" · ".join(path.name for path in paths),
            cache_size=cache_size,
        )

    def bootstrap(self) -> dict[str, Any]:
        """Return defaults, source metadata, and the initial real-data view."""
        default_request = self.default_request()
        response = self.view(default_request)
        return {**response, "defaults": default_request}

    def default_request(self) -> dict[str, Any]:
        options = available_filter_values(self.dataset.frame, "tm")
        months = cast(list[date], options["target_months"])
        return {
            "source": "tm",
            "comparison_mode": False,
            "target_start": _iso(months[0]) if months else None,
            "target_end": _iso(months[-1]) if months else None,
            "brand": None,
            "parent_code": None,
            "horizon": None,
            "minimum_actual_volume": 0.0,
            "vintage_a": {"kind": "oldest_available", "value": None},
            "vintage_b": {"kind": "latest_available", "value": None},
            "revision_direction": None,
            "revision_outcome": None,
            "revision_tolerance_kl": 0.01,
            "forecast_direction": None,
            "accuracy_band": None,
            "bias_band": None,
            "minimum_absolute_error_kl": 0.0,
            "top_n": None,
            "top_n_metric": "actual_volume",
            "hierarchy_status": None,
            "actual_status": None,
            "pair_status": None,
            "source_availability": None,
            "zero_forecast_only": False,
            "complete_vintage_history_only": False,
            "product_parent_code": None,
            "product_target_month": None,
        }

    def view(self, raw_request: dict[str, Any] | None = None) -> dict[str, Any]:
        computed = self._computed(raw_request or {})
        return computed.payload

    def product_detail(self, raw_request: dict[str, Any]) -> dict[str, Any] | None:
        """Build one product history from an already cacheable filter scope."""
        request, _, _, _, _ = self._normalize_request(raw_request)
        base_request = dict(request)
        base_request["product_parent_code"] = None
        base_request["product_target_month"] = None
        base_view = self._computed(base_request).view
        return self._build_product_payload(base_view, request)

    def export_csv(
        self,
        raw_request: dict[str, Any],
        *,
        kind: Literal["vintages", "quality", "scope_exclusions"],
        category: str | None = None,
    ) -> tuple[str, str]:
        """Return filename and CSV for the exact submitted filter request."""
        computed = self._computed(raw_request)
        view = computed.view
        source_suffix = "comparison" if view.filters.comparison_mode else view.filters.source
        if kind == "vintages":
            frame = view.download_frame
            filename = f"forecast_{source_suffix}_filtered_vintages.csv"
        elif kind == "quality":
            if category not in QUALITY_CATEGORIES:
                raise DashboardRequestError(
                    f"quality category must be one of {', '.join(QUALITY_CATEGORIES)}"
                )
            frame = view.quality.exceptions[category]
            filename = f"forecast_{source_suffix}_{category}_exceptions.csv"
        elif kind == "scope_exclusions":
            if category not in QUALITY_CATEGORIES:
                raise DashboardRequestError(
                    f"scope-exclusion category must be one of {', '.join(QUALITY_CATEGORIES)}"
                )
            frame = view.quality.scope_exclusions.get(category, pl.DataFrame())
            filename = f"forecast_{source_suffix}_{category}_scope_exclusions.csv"
        else:
            raise DashboardRequestError(f"unsupported export kind {kind!r}")
        return filename, frame.write_csv()

    def _computed(self, raw_request: dict[str, Any]) -> _ComputedView:
        if not isinstance(raw_request, dict):
            raise DashboardRequestError("request body must be a JSON object")
        request, options, filters, vintage_a, vintage_b = self._normalize_request(
            raw_request
        )
        key = json.dumps(request, sort_keys=True, separators=(",", ":"))
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                return cached

        view = build_dashboard_view(
            self.dataset.frame,
            self.dataset.actual_population,
            filters,
            vintage_a=vintage_a,
            vintage_b=vintage_b,
            hierarchy_diagnostics=self.dataset.hierarchy_diagnostics,
        )
        product_detail = self._build_product_payload(view, request)
        payload = self._build_payload(request, options, view, product_detail)
        computed = _ComputedView(request, options, view, product_detail, payload)
        with self._cache_lock:
            self._cache[key] = computed
            self._cache.move_to_end(key)
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
        return computed

    def _normalize_request(
        self, raw: dict[str, Any]
    ) -> tuple[
        dict[str, Any],
        dict[str, Any],
        DashboardFilters,
        VintageRule | None,
        VintageRule | None,
    ]:
        source = _parse_string(
            raw, "source", default="tm", allowed={"tm", "ml"}
        ) or "tm"
        comparison_mode = _parse_bool(raw, "comparison_mode")
        options = available_filter_values(
            self.dataset.frame,
            source,
            comparison_mode=comparison_mode,
        )
        available_months: list[date] = options["target_months"]  # type: ignore[assignment]
        target_start = _parse_date(raw.get("target_start"), "target_start")
        target_end = _parse_date(raw.get("target_end"), "target_end")
        if target_start is None and available_months:
            target_start = available_months[0]
        if target_end is None and available_months:
            target_end = available_months[-1]
        if target_start and target_end and target_start > target_end:
            raise DashboardRequestError("target_start must be on or before target_end")
        target_months = tuple(
            month
            for month in available_months
            if (target_start is None or month >= target_start)
            and (target_end is None or month <= target_end)
        )

        brand = _parse_string(raw, "brand")
        parent_code = _parse_int(raw, "parent_code", minimum=0)
        horizon = _parse_int(raw, "horizon", minimum=0)
        available_horizons = cast(list[int], options["horizons"])
        if horizon is not None and horizon not in available_horizons:
            raise DashboardRequestError("horizon is not available for the selected source")
        comparison_horizon: int | None = None
        if comparison_mode:
            common_horizons = cast(list[int], options["common_horizons"])
            default_comparison_horizon = cast(
                int | None, options["default_comparison_horizon"]
            )
            comparison_horizon = (
                horizon
                if horizon is not None
                else default_comparison_horizon
            )
            if comparison_horizon is not None and comparison_horizon not in common_horizons:
                raise DashboardRequestError(
                    "comparison horizon must be shared by TM and ML"
                )
            horizon = comparison_horizon

        hierarchy_status = _parse_string(
            raw,
            "hierarchy_status",
            allowed={"mapped", "unmapped", "conflict"},
        )
        actual_status = _parse_string(
            raw,
            "actual_status",
            allowed={"matched_positive", "matched_zero", "missing"},
        )
        pair_status = _parse_string(
            raw,
            "pair_status",
            allowed={
                "complete",
                "missing_a",
                "missing_b",
                "missing_both",
                "missing_actual",
                "zero_actual",
            },
        )
        source_availability = _parse_string(
            raw,
            "source_availability",
            allowed={"tm_only", "ml_only", "both_sources"},
        )
        revision_direction = _parse_string(
            raw,
            "revision_direction",
            allowed={"up", "down", "unchanged"},
        )
        revision_outcome = _parse_string(
            raw,
            "revision_outcome",
            allowed={"improved", "worsened", "neutral"},
        )
        forecast_direction = _parse_string(
            raw,
            "forecast_direction",
            allowed={"over", "under", "within_tolerance"},
        )
        accuracy_band_name = _parse_string(
            raw, "accuracy_band", allowed=set(ACCURACY_BANDS)
        )
        bias_band_name = _parse_string(raw, "bias_band", allowed=set(BIAS_BANDS))
        top_n_metric = _parse_string(
            raw,
            "top_n_metric",
            default="actual_volume",
            allowed={"actual_volume", "absolute_error", "deterioration"},
        ) or "actual_volume"
        top_n = _parse_int(raw, "top_n", minimum=1)

        vintage_a = None
        vintage_b = None
        if not comparison_mode:
            vintage_a = self._parse_vintage_rule(
                raw.get("vintage_a"), "vintage_a", "oldest_available", options
            )
            vintage_b = self._parse_vintage_rule(
                raw.get("vintage_b"), "vintage_b", "latest_available", options
            )

        normalized = {
            "source": source,
            "comparison_mode": comparison_mode,
            "target_start": _iso(target_start) if target_start else None,
            "target_end": _iso(target_end) if target_end else None,
            "brand": brand,
            "parent_code": parent_code,
            "horizon": horizon,
            "minimum_actual_volume": _parse_float(
                raw,
                "minimum_actual_volume",
                default=0.0,
                minimum=0.0,
            ),
            "vintage_a": self._rule_request(vintage_a, "oldest_available"),
            "vintage_b": self._rule_request(vintage_b, "latest_available"),
            "revision_direction": None if comparison_mode else revision_direction,
            "revision_outcome": None if comparison_mode else revision_outcome,
            "revision_tolerance_kl": _parse_float(
                raw,
                "revision_tolerance_kl",
                default=0.01,
                minimum=0.0,
            ),
            "forecast_direction": None if comparison_mode else forecast_direction,
            "accuracy_band": None if comparison_mode else accuracy_band_name,
            "bias_band": None if comparison_mode else bias_band_name,
            "minimum_absolute_error_kl": (
                0.0
                if comparison_mode
                else _parse_float(
                    raw,
                    "minimum_absolute_error_kl",
                    default=0.0,
                    minimum=0.0,
                )
            ),
            "top_n": None if comparison_mode else top_n,
            "top_n_metric": top_n_metric,
            "hierarchy_status": hierarchy_status,
            "actual_status": actual_status,
            "pair_status": pair_status,
            "source_availability": source_availability,
            "zero_forecast_only": _parse_bool(raw, "zero_forecast_only"),
            "complete_vintage_history_only": _parse_bool(
                raw, "complete_vintage_history_only"
            ),
            "product_parent_code": _parse_int(
                raw, "product_parent_code", minimum=0
            ),
            "product_target_month": (
                _iso(value)
                if (value := _parse_date(
                    raw.get("product_target_month"), "product_target_month"
                ))
                else None
            ),
        }
        filters = DashboardFilters(
            source=source,
            comparison_mode=comparison_mode,
            comparison_horizon=comparison_horizon,
            target_months=target_months,
            brands=_single_choice(brand),
            parent_codes=(parent_code,) if parent_code is not None else None,
            horizons=(horizon,) if horizon is not None else None,
            minimum_actual_volume=normalized["minimum_actual_volume"],
            hierarchy_statuses=_single_choice(hierarchy_status),
            actual_statuses=_single_choice(actual_status),
            pair_statuses=_single_choice(pair_status),
            source_availability=_single_choice(source_availability),
            zero_forecast_only=normalized["zero_forecast_only"],
            complete_vintage_history_only=normalized[
                "complete_vintage_history_only"
            ],
            revision_directions=_single_choice(normalized["revision_direction"]),
            revision_outcomes=_single_choice(normalized["revision_outcome"]),
            revision_tolerance_kl=normalized["revision_tolerance_kl"],
            forecast_directions=_single_choice(normalized["forecast_direction"]),
            forecast_accuracy_band=(
                ACCURACY_BANDS[accuracy_band_name]
                if accuracy_band_name and not comparison_mode
                else None
            ),
            bias_band=(
                BIAS_BANDS[bias_band_name]
                if bias_band_name and not comparison_mode
                else None
            ),
            minimum_absolute_error_kl=normalized["minimum_absolute_error_kl"],
            top_n=normalized["top_n"],
            top_n_metric=top_n_metric,
        )
        return normalized, options, filters, vintage_a, vintage_b

    def _parse_vintage_rule(
        self,
        raw_rule: Any,
        field: str,
        default_kind: str,
        options: dict[str, Any],
    ) -> VintageRule:
        if raw_rule is None:
            raw_rule = {"kind": default_kind, "value": None}
        if not isinstance(raw_rule, dict):
            raise DashboardRequestError(f"{field} must be an object")
        kind = _parse_string(
            raw_rule,
            "kind",
            default=default_kind,
            allowed={
                "oldest_available",
                "latest_available",
                "specific_calculation_month",
                "specific_horizon",
            },
        ) or default_kind
        value = raw_rule.get("value")
        if kind == "oldest_available":
            return VintageRule.oldest_available()
        if kind == "latest_available":
            return VintageRule.latest_available()
        if kind == "specific_calculation_month":
            month = _parse_date(value, f"{field}.value")
            if month is None or month not in options["calculation_months"]:
                raise DashboardRequestError(
                    f"{field}.value must be an available calculation month"
                )
            return VintageRule.specific_calculation_month(month)
        horizon_payload = {"value": value}
        horizon = _parse_int(horizon_payload, "value", minimum=0)
        if horizon is None or horizon not in options["horizons"]:
            raise DashboardRequestError(
                f"{field}.value must be an available forecast horizon"
            )
        return VintageRule.specific_horizon(horizon)

    @staticmethod
    def _rule_request(rule: VintageRule | None, default_kind: str) -> dict[str, Any]:
        if rule is None:
            return {"kind": default_kind, "value": None}
        return {"kind": rule.kind, "value": _json_value(rule.value)}

    def _build_product_payload(
        self, view: DashboardView, request: dict[str, Any]
    ) -> dict[str, Any] | None:
        active_keys = view.vintage_pairs.select(
            ["parent_code", "parent_description", "snop_month"]
        ).unique()
        if active_keys.height == 0:
            return None
        parent_code = request["product_parent_code"]
        target_month = (
            date.fromisoformat(request["product_target_month"])
            if request["product_target_month"]
            else None
        )
        if parent_code is None or target_month is None:
            ranked = (
                view.filtered_population.group_by(
                    ["parent_code", "parent_description", "snop_month"]
                )
                .agg(pl.len().alias("vintages"))
                .join(
                    active_keys,
                    on=["parent_code", "parent_description", "snop_month"],
                    how="semi",
                )
                .sort(
                    ["vintages", "snop_month", "parent_code"],
                    descending=[True, True, False],
                )
            )
            candidates = ranked
            if parent_code is not None:
                candidates = candidates.filter(pl.col("parent_code") == parent_code)
                candidates = candidates.sort("snop_month", descending=True)
            elif target_month is not None:
                candidates = candidates.filter(pl.col("snop_month") == target_month)
            if candidates.height == 0:
                candidates = ranked if ranked.height else active_keys
            selected = candidates.head(1).to_dicts()[0]
            parent_code = cast(int, selected["parent_code"])
            target_month = cast(date, selected["snop_month"])
        try:
            detail = build_product_detail(
                self.dataset.frame,
                view.filters,
                parent_code,
                target_month,
                active_key_frame=view.vintage_pairs,
            )
        except ValueError as exc:
            return {"error": str(exc), "parent_code": parent_code, "target_month": _iso(target_month)}
        product_options = (
            active_keys.select(["parent_code", "parent_description"])
            .unique()
            .sort(["parent_code", "parent_description"])
        )
        target_options = (
            active_keys.filter(pl.col("parent_code") == parent_code)
            .get_column("snop_month")
            .unique()
            .sort()
            .to_list()
        )
        return {
            "parent_code": detail.parent_code,
            "target_month": _iso(detail.target_month),
            "sources": list(detail.sources),
            "parent_description": detail.parent_description,
            "hierarchy_description": detail.hierarchy_description,
            "brand": detail.brand,
            "mapping_status": detail.mapping_status,
            "actual_kl": detail.actual_kl,
            "actual_status": detail.actual_status,
            "status": detail.status,
            "status_message": detail.status_message,
            "points": _frame_payload(detail.points, limit=120),
            "revisions": _frame_payload(detail.revisions, limit=40),
            "stability": _frame_payload(detail.stability),
            "product_options": _rows(product_options),
            "target_options": [_iso(month) for month in target_options],
        }

    def _build_payload(
        self,
        request: dict[str, Any],
        options: dict[str, Any],
        view: DashboardView,
        product_detail: dict[str, Any] | None,
    ) -> dict[str, Any]:
        summary = (
            _json_value(view.population_summary.head(1).to_dicts()[0])
            if view.population_summary.height
            else {}
        )
        metrics = _json_value(view.metrics.as_dict())
        comparison = self._comparison_payload(view)
        quality = self._quality_payload(view)
        empty = summary.get("forecast_rows", 0) == 0
        zero_denominator = metrics.get("accuracy_denominator_actual_kl") == 0
        blocked = bool(comparison and comparison["blocked"])
        return {
            "meta": {
                "refresh_timestamp": self.refresh_timestamp,
                "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "data_source": self.source_label,
                "dataset_rows": self.dataset.frame.height,
                "actual_population_rows": self.dataset.actual_population.height,
                "synthetic": False,
            },
            "request": request,
            "options": self._options_payload(options),
            "state": {
                "empty": empty,
                "comparison_blocked": blocked,
                "zero_denominator": zero_denominator,
                "message": (
                    "No forecast rows match the active filters."
                    if empty
                    else comparison.get("warning")
                    if blocked and comparison
                    else "Selected actual-volume denominator is zero; ratio metrics are undefined."
                    if zero_denominator
                    else None
                ),
            },
            "population_summary": summary,
            "metrics": metrics,
            "monthly_performance": _frame_payload(view.monthly_performance, limit=60),
            "monthly_audit": _frame_payload(view.monthly_audit, limit=60),
            "horizon_performance": _frame_payload(view.horizon_performance, limit=30),
            "horizon_audit": _frame_payload(view.horizon_audit, limit=30),
            "brand_target_month_performance": _frame_payload(
                view.brand_target_month_performance, limit=500
            ),
            "revision_diagnostics": _frame_payload(view.revision_diagnostics),
            "revision_scatter": _frame_payload(view.revision_scatter, limit=240),
            "exceptions": _frame_payload(view.download_frame, limit=80),
            "comparison": comparison,
            "product_detail": product_detail,
            "quality": quality,
        }

    @staticmethod
    def _options_payload(options: dict[str, Any]) -> dict[str, Any]:
        return {
            "target_months": [_iso(value) for value in options["target_months"]],
            "brands": options["brands"],
            "parent_products": options["parent_products"],
            "horizons": options["horizons"],
            "common_horizons": options["common_horizons"],
            "default_comparison_horizon": options["default_comparison_horizon"],
            "calculation_months": [
                _iso(value) for value in options["calculation_months"]
            ],
        }

    @staticmethod
    def _comparison_payload(view: DashboardView) -> dict[str, Any] | None:
        comparison = view.comparison
        if comparison is None:
            return None
        return {
            "selected_horizon": comparison.selected_horizon,
            "common_horizons": list(comparison.common_horizons),
            "alignment_rule": comparison.alignment_rule,
            "blocked": comparison.blocked,
            "ready": comparison.ready,
            "warning": comparison.warning,
            "coverage_warning": comparison.coverage_warning,
            "comparable_pairs": comparison.comparable_pairs,
            "tm_metrics": _json_value(comparison.tm_metrics.as_dict()),
            "ml_metrics": _json_value(comparison.ml_metrics.as_dict()),
            "common_metrics": _json_value(comparison.common_metrics.as_dict()),
            "deltas": _frame_payload(comparison.deltas),
            "population_summary": _frame_payload(comparison.population_summary),
            "winner_counts": _frame_payload(comparison.winner_counts),
            "paired_comparison": _frame_payload(
                comparison.paired_comparison, limit=240
            ),
        }

    @staticmethod
    def _quality_payload(view: DashboardView) -> dict[str, Any]:
        quality = view.quality
        categories: dict[str, Any] = {}
        attention_categories = 0
        for category in QUALITY_CATEGORIES:
            counts = getattr(quality, category)
            exceptions = quality.exceptions.get(category, pl.DataFrame())
            category_has_attention = (
                counts.filter(
                    (pl.col("severity") != "info") & (pl.col("observations") > 0)
                ).height
                > 0
            )
            if category_has_attention:
                attention_categories += 1
            categories[category] = {
                "counts": _frame_payload(counts),
                "exceptions": _frame_payload(exceptions, limit=12),
                "explanation": quality.explanation_text(category),
                "has_attention": category_has_attention,
            }
        return {
            "blocking_errors": list(quality.blocking_errors),
            "attention_categories": attention_categories,
            "categories": categories,
            "baseline_counts": _frame_payload(quality.baseline_counts),
            "scope_exclusion_counts": _frame_payload(
                quality.scope_exclusion_counts
            ),
        }
