import json
from datetime import date
from pathlib import Path
import unittest

import polars as pl

from forecast_analysis import (
    DashboardFilters,
    build_dashboard_diagnostics,
    build_dashboard_view,
    build_product_history,
    build_source_comparison,
    calculate_metrics,
    calculate_revision_metrics,
    select_vintage_pair,
)
from forecast_analysis.dashboard import build_exception_download_frame
from forecast_analysis.filters import apply_performance_filters

FIXTURE_PATH = Path(__file__).parent / "fixtures/ticket_09_hand_calculated.json"
DOWNLOAD_COLUMNS = [
    "source",
    "parent_code",
    "parent_description",
    "brand",
    "snop_month",
    "actual_kl",
    "actual_status",
    "vintage_a_calculation_month",
    "vintage_a_horizon_months",
    "vintage_a_forecast_kl",
    "vintage_b_calculation_month",
    "vintage_b_horizon_months",
    "vintage_b_forecast_kl",
    "absolute_error_b_kl",
    "bias_b_kl",
    "revision_kl",
    "error_improvement_kl",
    "revision_direction",
    "revision_outcome",
    "pair_status",
    "mapping_status",
]


def _read_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _metric_pairs(fixture: dict) -> pl.DataFrame:
    return pl.DataFrame(fixture["metric_pair_rows"]).with_columns(
        pl.col("vintage_a_calculation_month").str.to_date("%Y-%m-%d"),
        pl.col("vintage_b_calculation_month").str.to_date("%Y-%m-%d"),
        pl.col("parent_code").cast(pl.Int64),
        pl.col("vintage_a_forecast_kl").cast(pl.Float64),
        pl.col("vintage_b_forecast_kl").cast(pl.Float64),
        pl.col("actual_kl").cast(pl.Float64),
    )


def _actual_population(fixture: dict) -> pl.DataFrame:
    return pl.DataFrame(fixture["metric_actual_population"]).with_columns(
        pl.col("snop_month").str.to_date("%Y-%m-%d"),
        pl.col("parent_code").cast(pl.Int64),
        pl.col("actual_kl").cast(pl.Float64),
    )


def _analysis_frame(rows: list[dict]) -> pl.DataFrame:
    frame = pl.DataFrame(rows).with_columns(
        pl.col("calculation_month").str.to_date("%Y-%m-%d"),
        pl.col("snop_month").str.to_date("%Y-%m-%d"),
        pl.col("parent_code").cast(pl.Int64),
        pl.col("forecast_horizon_months").cast(pl.Int64),
        pl.col("forecast_kl").cast(pl.Float64),
        pl.col("actual_kl").cast(pl.Float64),
    )
    return frame.with_columns(
        pl.lit(None, dtype=pl.String).alias("mapping_diagnostic"),
        pl.when(pl.col("actual_kl").is_null())
        .then(pl.lit("missing"))
        .when(pl.col("actual_kl") == 0)
        .then(pl.lit("matched_zero"))
        .otherwise(pl.lit("matched_positive"))
        .alias("actual_status"),
    )


def _comparison_frame(fixture: dict) -> pl.DataFrame:
    rows = []
    for row in fixture["comparison_rows"]:
        rows.append(
            {
                **row,
                "hierarchy_description": row["parent_description"],
                "mapping_status": "mapped",
            }
        )
    return _analysis_frame(rows)


def _assert_optional_float(
    test_case: unittest.TestCase,
    actual: float | None,
    expected: float | None,
) -> None:
    test_case.assertIsNotNone(actual)
    if actual is not None and expected is not None:
        test_case.assertAlmostEqual(actual, expected)


class ForecastAnalysisReleaseFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = _read_fixture()

    def test_core_metrics_match_hand_calculated_numerators_and_denominators(self):
        summary = calculate_metrics(
            _metric_pairs(self.fixture),
            _actual_population(self.fixture),
        )
        expected = self.fixture["metric_expected"]
        for field in (
            "forecast_accuracy_pct",
            "wape_pct",
            "bias_pct",
            "absolute_error_kl",
            "mae_kl",
            "actual_kl",
            "forecast_kl",
            "coverage_pct",
            "accuracy_numerator_kl",
            "accuracy_denominator_actual_kl",
            "bias_numerator_kl",
            "bias_denominator_actual_kl",
            "coverage_numerator_actual_kl",
            "coverage_denominator_actual_kl",
        ):
            with self.subTest(field=field):
                actual = getattr(summary, field)
                self.assertIsNotNone(actual)
                if actual is not None:
                    self.assertAlmostEqual(actual, expected[field])
        for field in (
            "mae_observations",
            "eligible_observations",
            "absolute_error_observations",
            "complete_pairs",
            "missing_vintage_pairs",
            "missing_actual_observations",
            "zero_actual_observations",
            "effectiveness_numerator",
            "effectiveness_denominator",
            "neutral_revisions",
            "unchanged_revisions",
        ):
            with self.subTest(field=field):
                self.assertEqual(getattr(summary, field), expected[field])

    def test_revision_metrics_match_hand_calculated_effectiveness(self):
        summary = calculate_revision_metrics(_metric_pairs(self.fixture))
        expected = self.fixture["metric_expected"]
        self.assertAlmostEqual(summary.accuracy_delta_pp, expected["accuracy_delta_pp"])
        self.assertAlmostEqual(
            summary.total_error_improvement_kl,
            expected["total_error_improvement_kl"],
        )
        self.assertAlmostEqual(
            summary.revision_effectiveness_pct,
            expected["revision_effectiveness_pct"],
        )
        self.assertEqual(
            summary.materially_revised_observations,
            expected["materially_revised_observations"],
        )
        self.assertEqual(summary.improved_revisions, expected["improved_revisions"])
        self.assertEqual(summary.worsened_revisions, expected["worsened_revisions"])
        _assert_optional_float(
            self,
            summary.accuracy_delta_numerator_kl,
            expected["accuracy_delta_numerator_kl"],
        )
        _assert_optional_float(
            self,
            summary.accuracy_delta_denominator_actual_kl,
            expected["accuracy_delta_denominator_actual_kl"],
        )
        _assert_optional_float(self, summary.revised_up_pct, expected["revised_up_pct"])
        _assert_optional_float(self, summary.revised_down_pct, expected["revised_down_pct"])

    def test_source_comparison_uses_common_population_and_source_specific_coverage(self):
        comparison = build_source_comparison(
            _comparison_frame(self.fixture),
            pl.DataFrame(
                {
                    "parent_code": [1, 2, 3, 4],
                    "snop_month": [date(2026, 1, 1)] * 4,
                    "actual_kl": [100.0, 50.0, 25.0, 25.0],
                }
            ).with_columns(pl.col("parent_code").cast(pl.Int64)),
            DashboardFilters(comparison_mode=True),
        )
        expected = self.fixture["comparison_expected"]
        self.assertEqual(comparison.selected_horizon, expected["selected_horizon"])
        self.assertEqual(comparison.comparable_pairs, expected["common_observations"])
        self.assertAlmostEqual(
            comparison.tm_metrics.forecast_accuracy_pct,
            expected["tm_accuracy_pct"],
        )
        self.assertAlmostEqual(
            comparison.ml_metrics.forecast_accuracy_pct,
            expected["ml_accuracy_pct"],
        )
        self.assertAlmostEqual(
            comparison.tm_metrics.coverage_pct,
            expected["tm_coverage_pct"],
        )
        self.assertAlmostEqual(
            comparison.ml_metrics.coverage_pct,
            expected["ml_coverage_pct"],
        )
        for source, summary in (
            ("tm", comparison.tm_metrics),
            ("ml", comparison.ml_metrics),
        ):
            with self.subTest(source=source):
                expected_prefix = f"{source}_coverage_"
                _assert_optional_float(
                    self,
                    summary.coverage_numerator_actual_kl,
                    expected[expected_prefix + "numerator_actual_kl"],
                )
                _assert_optional_float(
                    self,
                    summary.coverage_denominator_actual_kl,
                    expected[expected_prefix + "denominator_actual_kl"],
                )
                if (
                    summary.coverage_pct is None
                    or summary.coverage_numerator_actual_kl is None
                    or summary.coverage_denominator_actual_kl in (None, 0)
                ):
                    self.fail(f"{source} coverage components are incomplete")
                self.assertAlmostEqual(
                    summary.coverage_pct,
                    summary.coverage_numerator_actual_kl
                    / summary.coverage_denominator_actual_kl
                    * 100,
                )
        common = comparison.common_metrics
        _assert_optional_float(self, common.coverage_pct, 75.0)
        _assert_optional_float(self, common.coverage_numerator_actual_kl, 150.0)
        _assert_optional_float(self, common.coverage_denominator_actual_kl, 200.0)
        self.assertEqual(
            comparison.winner_counts["winner"].to_list(),
            ["tm_better", "ml_better", "tied"],
        )
        self.assertEqual(
            comparison.paired_comparison["winner"].to_list(),
            expected["winner_order"],
        )

    def test_coverage_edge_cases_match_explicit_numerator_denominator_contract(self):
        for name, fixture in self.fixture["coverage_edge_cases"].items():
            with self.subTest(case=name):
                summary = calculate_metrics(
                    pl.DataFrame(fixture["pair_rows"]).with_columns(
                        pl.col("vintage_a_calculation_month")
                        .cast(pl.String)
                        .str.to_date("%Y-%m-%d", strict=False),
                        pl.col("vintage_b_calculation_month")
                        .cast(pl.String)
                        .str.to_date("%Y-%m-%d", strict=False),
                        pl.col("parent_code").cast(pl.Int64),
                        pl.col("vintage_a_forecast_kl").cast(pl.Float64),
                        pl.col("vintage_b_forecast_kl").cast(pl.Float64),
                        pl.col("actual_kl").cast(pl.Float64),
                    ),
                    pl.DataFrame(fixture["actual_population"]).with_columns(
                        pl.col("snop_month").str.to_date("%Y-%m-%d"),
                        pl.col("parent_code").cast(pl.Int64),
                        pl.col("actual_kl").cast(pl.Float64),
                    ),
                )
                expected = fixture["expected"]
                self.assertEqual(summary.coverage_pct, expected["coverage_pct"])
                self.assertEqual(
                    summary.coverage_numerator_actual_kl,
                    expected["coverage_numerator_actual_kl"],
                )
                self.assertEqual(
                    summary.coverage_denominator_actual_kl,
                    expected["coverage_denominator_actual_kl"],
                )
                if expected["coverage_denominator_actual_kl"]:
                    if (
                        summary.coverage_pct is None
                        or summary.coverage_numerator_actual_kl is None
                        or summary.coverage_denominator_actual_kl in (None, 0)
                    ):
                        self.fail(f"{name} coverage components are incomplete")
                    self.assertAlmostEqual(
                        summary.coverage_pct,
                        summary.coverage_numerator_actual_kl
                        / summary.coverage_denominator_actual_kl
                        * 100,
                    )

    def test_product_history_stability_uses_chronological_population_standard_deviation(self):
        history_rows = []
        for row in self.fixture["stability_rows"]:
            history_rows.append(
                {
                    **row,
                    "hierarchy_description": row["parent_description"],
                    "brand": "Alpha",
                    "mapping_status": "mapped",
                }
            )
        history = build_product_history(
            _analysis_frame(history_rows),
            1,
            date(2026, 1, 1),
            sources=("tm", "ml"),
        )
        expected = self.fixture["stability_expected"]
        stability = {
            row["source"]: row for row in history.stability.iter_rows(named=True)
        }
        self.assertEqual(stability["tm"]["vintage_count"], expected["tm_vintage_count"])
        self.assertEqual(stability["tm"]["forecast_range_kl"], expected["tm_forecast_range_kl"])
        self.assertAlmostEqual(
            stability["tm"]["population_std_dev_kl"],
            expected["tm_population_std_dev_kl"],
        )
        self.assertEqual(stability["tm"]["revision_count"], expected["tm_revision_count"])
        self.assertEqual(
            stability["tm"]["maximum_absolute_revision_kl"],
            expected["tm_maximum_absolute_revision_kl"],
        )
        self.assertEqual(stability["ml"]["vintage_count"], expected["ml_vintage_count"])
        self.assertEqual(stability["ml"]["forecast_range_kl"], expected["ml_forecast_range_kl"])
        self.assertEqual(stability["ml"]["population_std_dev_kl"], expected["ml_population_std_dev_kl"])
        self.assertEqual(
            stability["ml"]["maximum_absolute_revision_kl"],
            expected["ml_maximum_absolute_revision_kl"],
        )

    def test_performance_filters_and_download_share_exact_selected_pair_keys(self):
        rows = []
        for parent_code, actual, vintage_a, vintage_b in (
            (1, 100.0, 80.0, 120.0),
            (2, 100.0, 80.0, 70.0),
            (3, 100.0, 100.0, 100.0),
        ):
            for calculation_month, forecast in (
                ("2025-01-01", vintage_a),
                ("2025-02-01", vintage_b),
            ):
                rows.append(
                    {
                        "source": "tm",
                        "parent_code": parent_code,
                        "parent_description": f"Product {parent_code}",
                        "hierarchy_description": f"Product {parent_code}",
                        "brand": "Alpha",
                        "mapping_status": "mapped",
                        "calculation_month": calculation_month,
                        "snop_month": "2026-01-01",
                        "forecast_horizon_months": 12,
                        "forecast_kl": forecast,
                        "actual_kl": actual,
                    }
                )
        frame = _analysis_frame(rows)
        pair = select_vintage_pair(frame, "tm")
        filtered = apply_performance_filters(
            pair,
            DashboardFilters(source="tm", forecast_directions=("over",)),
        )
        self.assertEqual(filtered["parent_code"].to_list(), [1])
        download = build_exception_download_frame(filtered)
        self.assertEqual(download.columns, DOWNLOAD_COLUMNS)
        self.assertEqual(
            download.select(["source", "parent_code", "snop_month"]).to_dicts(),
            [{"source": "tm", "parent_code": 1, "snop_month": date(2026, 1, 1)}],
        )

    def test_dashboard_view_exposes_population_summary_and_machine_readable_diagnostics(self):
        rows = []
        for parent_code, actual, vintage_a, vintage_b in (
            (1, 100.0, 80.0, 120.0),
            (2, 100.0, 80.0, 70.0),
        ):
            for calculation_month, forecast in (
                ("2025-01-01", vintage_a),
                ("2025-02-01", vintage_b),
            ):
                rows.append(
                    {
                        "source": "tm",
                        "parent_code": parent_code,
                        "parent_description": f"Product {parent_code}",
                        "hierarchy_description": f"Product {parent_code}",
                        "brand": "Alpha",
                        "mapping_status": "mapped",
                        "calculation_month": calculation_month,
                        "snop_month": "2026-01-01",
                        "forecast_horizon_months": 12,
                        "forecast_kl": forecast,
                        "actual_kl": actual,
                    }
                )
        frame = _analysis_frame(rows)
        actuals = pl.DataFrame(
            {
                "parent_code": [1, 2, 99],
                "snop_month": [date(2026, 1, 1)] * 3,
                "actual_kl": [100.0, 100.0, 50.0],
            }
        ).with_columns(pl.col("parent_code").cast(pl.Int64))
        view = build_dashboard_view(frame, actuals)
        summary = view.population_summary.row(0, named=True)
        self.assertEqual(summary["mode"], "single_source")
        self.assertEqual(summary["sources"], "TM")
        self.assertEqual(summary["products"], 2)
        self.assertEqual(summary["comparable_pairs"], view.metrics.complete_pairs)
        self.assertIn("accuracy_numerator_kl", view.monthly_audit.columns)
        self.assertIn("accuracy_denominator_actual_kl", view.horizon_audit.columns)
        self.assertEqual(
            view.monthly_audit.filter(pl.col("snop_month") == date(2026, 1, 1))
            .select("accuracy_numerator_kl")
            .item(),
            50.0,
        )
        diagnostics = build_dashboard_diagnostics(
            view.filtered_population,
            view.selected_actual_population,
            view.coverage_pairs,
            view.vintage_pairs,
        )
        self.assertIn("actual_population_volume_kl", diagnostics["check"].to_list())
        self.assertTrue(all(value == "measured" for value in diagnostics["status"].to_list()))

    def test_empty_selection_is_typed_and_explanatory(self):
        rows = []
        for calculation_month, forecast in (
            ("2025-01-01", 80.0),
            ("2025-02-01", 90.0),
        ):
            rows.append(
                {
                    "source": "tm",
                    "parent_code": 1,
                    "parent_description": "Product 1",
                    "hierarchy_description": "Product 1",
                    "brand": "Alpha",
                    "mapping_status": "mapped",
                    "calculation_month": calculation_month,
                    "snop_month": "2026-01-01",
                    "forecast_horizon_months": 12,
                    "forecast_kl": forecast,
                    "actual_kl": 100.0,
                }
            )
        view = build_dashboard_view(
            _analysis_frame(rows),
            pl.DataFrame(
                {
                    "parent_code": [1],
                    "snop_month": [date(2026, 1, 1)],
                    "actual_kl": [100.0],
                }
            ).with_columns(pl.col("parent_code").cast(pl.Int64)),
            DashboardFilters(source="tm", target_months=()),
        )
        self.assertEqual(view.filtered_population.height, 0)
        self.assertIsNone(view.metrics.forecast_accuracy_pct)
        self.assertEqual(
            view.population_summary["target_range"].item(),
            "none selected",
        )


if __name__ == "__main__":
    unittest.main()
