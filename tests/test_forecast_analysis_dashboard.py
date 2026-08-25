import unittest
from datetime import date
from pathlib import Path

import polars as pl

from forecast_analysis.analysis_frame import (
    build_analysis_dataset,
    load_analysis_inputs,
)
from forecast_analysis.dashboard import DashboardView, build_dashboard_view  # pyright: ignore[reportMissingImports]
from forecast_analysis.filters import (  # pyright: ignore[reportMissingImports]
    DashboardFilters,
    apply_dashboard_filters,
    available_filter_values,
)
from forecast_analysis.metrics import (  # pyright: ignore[reportMissingImports]
    calculate_metrics,
)
from forecast_analysis.vintages import VintageRule, select_vintage_pair  # pyright: ignore[reportMissingImports]


class DashboardFixtureTests(unittest.TestCase):
    @staticmethod
    def frame() -> pl.DataFrame:
        rows = [
            # Same product-target keys exist in both sources but must stay isolated.
            ("tm", 100, "A", "Brand A", "mapped", "2025-01", "2026-01", 80.0, 100.0),
            ("tm", 100, "A", "Brand A", "mapped", "2025-02", "2026-01", 110.0, 100.0),
            ("ml", 100, "A", "Brand A", "mapped", "2025-01", "2026-01", 40.0, 100.0),
            ("ml", 100, "A", "Brand A", "mapped", "2025-02", "2026-01", 50.0, 100.0),
            ("tm", 200, "B", "Brand B", "mapped", "2025-01", "2026-01", 0.0, 10.0),
            ("tm", 200, "B", "Brand B", "mapped", "2025-02", "2026-01", 20.0, 10.0),
            ("ml", 200, "B", "Brand B", "mapped", "2025-01", "2026-01", 20.0, 10.0),
            ("ml", 200, "B", "Brand B", "mapped", "2025-02", "2026-01", 5.0, 10.0),
            # Zero actual remains a valid, non-ratio observation.
            ("tm", 300, "C", "Brand C", "mapped", "2025-01", "2026-02", 0.0, 0.0),
            ("tm", 300, "C", "Brand C", "mapped", "2025-02", "2026-02", 5.0, 0.0),
            ("ml", 300, "C", "Brand C", "mapped", "2025-01", "2026-02", 0.0, 0.0),
            ("ml", 300, "C", "Brand C", "mapped", "2025-02", "2026-02", 1.0, 0.0),
            # Missing actual remains visible for coverage diagnostics.
            ("tm", 400, "D", "Brand D", "mapped", "2025-01", "2026-03", 10.0, None),
            ("tm", 400, "D", "Brand D", "mapped", "2025-02", "2026-03", 12.0, None),
            # A quality-only brand is still selectable as a defined group.
            ("tm", 500, "E", None, "unmapped", "2025-01", "2026-04", 10.0, 20.0),
            ("tm", 500, "E", None, "unmapped", "2025-02", "2026-04", 15.0, 20.0),
        ]
        return pl.DataFrame(
            {
                "source": [row[0] for row in rows],
                "parent_code": [row[1] for row in rows],
                "parent_description": [row[2] for row in rows],
                "hierarchy_description": [row[2] for row in rows],
                "brand": [row[3] for row in rows],
                "mapping_status": [row[4] for row in rows],
                "mapping_diagnostic": [
                    None if row[4] == "mapped" else "no hierarchy mapping" for row in rows
                ],
                "calculation_month": [row[5] for row in rows],
                "snop_month": [row[6] for row in rows],
                "forecast_horizon_months": [12 for _ in rows],
                "forecast_kl": [row[7] for row in rows],
                "actual_kl": [row[8] for row in rows],
                "actual_status": [
                    "missing"
                    if row[8] is None
                    else "matched_zero"
                    if row[8] == 0
                    else "matched_positive"
                    for row in rows
                ],
            }
        ).with_columns(
            pl.col("calculation_month").str.to_date("%Y-%m"),
            pl.col("snop_month").str.to_date("%Y-%m"),
            pl.col("parent_code").cast(pl.Int64),
            pl.col("forecast_horizon_months").cast(pl.Int64),
            pl.col("forecast_kl").cast(pl.Float64),
            pl.col("actual_kl").cast(pl.Float64),
        )

    @staticmethod
    def actual_population() -> pl.DataFrame:
        frame = DashboardFixtureTests.frame()
        forecast_actuals = (
            frame.filter(
                (pl.col("source") == "tm") & pl.col("actual_kl").is_not_null()
            )
            .select(
                [
                    "parent_code",
                    "snop_month",
                    "actual_kl",
                    "hierarchy_description",
                    "brand",
                    "mapping_status",
                    "mapping_diagnostic",
                ]
            )
            .unique(subset=["parent_code", "snop_month"], maintain_order=True)
        )
        actual_only = pl.DataFrame(
            {
                "parent_code": [900],
                "snop_month": [date(2026, 1, 1)],
                "actual_kl": [100.0],
                "hierarchy_description": ["Actual-only product"],
                "brand": ["Brand A"],
                "mapping_status": ["mapped"],
                "mapping_diagnostic": pl.Series([None], dtype=pl.String),
            }
        )
        return pl.concat([forecast_actuals, actual_only], how="vertical").sort(
            ["parent_code", "snop_month"]
        )

    @staticmethod
    def metric_actual_population(values: list[float]) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "parent_code": list(range(1, len(values) + 1)),
                "snop_month": [date(2026, 1, 1)] * len(values),
                "actual_kl": values,
            }
        )

    @staticmethod
    def horizon_frame() -> pl.DataFrame:
        rows = [
            ("tm", 100, "Product 100", "Brand A", date(2025, 11, 1), 80.0),
            ("tm", 100, "Product 100", "Brand A", date(2025, 12, 1), 90.0),
            ("tm", 200, "Product 200", "Brand B", date(2025, 12, 1), 20.0),
            ("tm", 300, "Product 300", "Brand C", date(2025, 11, 1), 120.0),
            ("ml", 400, "Product 400", "Brand D", date(2025, 10, 1), 70.0),
        ]
        target = date(2026, 1, 1)
        return pl.DataFrame(
            {
                "source": [row[0] for row in rows],
                "parent_code": [row[1] for row in rows],
                "parent_description": [row[2] for row in rows],
                "hierarchy_description": [row[2] for row in rows],
                "brand": [row[3] for row in rows],
                "mapping_status": ["mapped"] * len(rows),
                "mapping_diagnostic": [None] * len(rows),
                "calculation_month": [row[4] for row in rows],
                "snop_month": [target] * len(rows),
                "forecast_horizon_months": [
                    (
                        2
                        if row[4] == date(2025, 11, 1)
                        else 1
                        if row[4] == date(2025, 12, 1)
                        else 3
                    )
                    for row in rows
                ],
                "forecast_kl": [row[5] for row in rows],
                "actual_kl": [100.0] * len(rows),
                "actual_status": ["matched_positive"] * len(rows),
            }
        ).with_columns(
            pl.col("parent_code").cast(pl.Int64),
            pl.col("forecast_horizon_months").cast(pl.Int64),
            pl.col("forecast_kl").cast(pl.Float64),
            pl.col("actual_kl").cast(pl.Float64),
        )

    @staticmethod
    def horizon_actual_population() -> pl.DataFrame:
        return pl.DataFrame(
            {
                "parent_code": [100, 200, 300, 400],
                "snop_month": [date(2026, 1, 1)] * 4,
                "actual_kl": [100.0] * 4,
            }
        )


class DashboardPopulationTests(unittest.TestCase):
    def test_default_source_is_tm_and_source_switch_recalculates_every_output(self):
        frame = DashboardFixtureTests.frame()
        actual_population = DashboardFixtureTests.actual_population()
        tm = build_dashboard_view(frame, actual_population)
        ml = build_dashboard_view(
            frame, actual_population, DashboardFilters(source="ml")
        )

        self.assertIsInstance(tm, DashboardView)
        self.assertEqual(tm.filters.source, "tm")
        self.assertEqual(set(tm.filtered_population["source"].unique()), {"tm"})
        self.assertEqual(set(tm.vintage_pairs["source"].unique()), {"tm"})
        self.assertEqual(set(tm.monthly_performance["source"].unique()), {"tm"})
        self.assertEqual(set(tm.horizon_performance["source"].unique()), {"tm"})
        self.assertEqual(tm.horizon_performance["forecast_kl"].to_list(), [240.0])
        self.assertEqual(tm.metrics.forecast_kl, 150.0)
        self.assertEqual(tm.metrics.actual_kl, 130.0)
        self.assertEqual(tm.metrics.absolute_error_kl, 30.0)
        assert tm.metrics.coverage_pct is not None
        self.assertAlmostEqual(tm.metrics.coverage_pct, 130 / 230 * 100)

        self.assertEqual(set(ml.filtered_population["source"].unique()), {"ml"})
        self.assertEqual(set(ml.vintage_pairs["source"].unique()), {"ml"})
        self.assertEqual(set(ml.monthly_performance["source"].unique()), {"ml"})
        self.assertEqual(set(ml.horizon_performance["source"].unique()), {"ml"})
        self.assertEqual(ml.horizon_performance["forecast_kl"].to_list(), [116.0])
        self.assertEqual(ml.metrics.forecast_kl, 56.0)
        self.assertEqual(ml.metrics.actual_kl, 110.0)
        self.assertEqual(ml.metrics.absolute_error_kl, 56.0)
        assert ml.metrics.coverage_pct is not None
        self.assertAlmostEqual(ml.metrics.coverage_pct, 110 / 230 * 100)
        self.assertNotEqual(tm.metrics.forecast_accuracy_pct, ml.metrics.forecast_accuracy_pct)
        self.assertNotEqual(
            tm.horizon_performance["forecast_accuracy_pct"].to_list(),
            ml.horizon_performance["forecast_accuracy_pct"].to_list(),
        )

    def test_default_oldest_and_latest_are_independent_within_each_source(self):
        frame = DashboardFixtureTests.frame()
        tm_pair = select_vintage_pair(frame, "tm")
        ml_pair = select_vintage_pair(frame, "ml")

        tm_100 = tm_pair.filter(pl.col("parent_code") == 100).row(0, named=True)
        ml_100 = ml_pair.filter(pl.col("parent_code") == 100).row(0, named=True)
        self.assertEqual(tm_100["vintage_a_calculation_month"], date(2025, 1, 1))
        self.assertEqual(tm_100["vintage_b_calculation_month"], date(2025, 2, 1))
        self.assertEqual(tm_100["vintage_a_forecast_kl"], 80.0)
        self.assertEqual(tm_100["vintage_b_forecast_kl"], 110.0)
        self.assertEqual(ml_100["vintage_a_forecast_kl"], 40.0)
        self.assertEqual(ml_100["vintage_b_forecast_kl"], 50.0)
        self.assertEqual(set(tm_pair["source"].unique()), {"tm"})
        self.assertEqual(set(ml_pair["source"].unique()), {"ml"})

    def test_target_brand_product_and_minimum_volume_filters_share_one_population(self):
        frame = DashboardFixtureTests.frame()
        view = build_dashboard_view(
            frame,
            DashboardFixtureTests.actual_population(),
            DashboardFilters(
                source="tm",
                target_months=(date(2026, 1, 1),),
                brands=("Brand B",),
                parent_codes=(200,),
                minimum_actual_volume=5,
            ),
        )

        self.assertEqual(view.filtered_population["parent_code"].unique().to_list(), [200])
        self.assertEqual(view.vintage_pairs["parent_code"].unique().to_list(), [200])
        self.assertEqual(view.monthly_performance["snop_month"].to_list(), [date(2026, 1, 1)])
        self.assertEqual(view.metrics.population_observations, 1)
        self.assertEqual(view.metrics.eligible_observations, 1)

        empty = build_dashboard_view(
            frame,
            DashboardFixtureTests.actual_population(),
            DashboardFilters(source="tm", brands=()),
        )
        self.assertEqual(empty.filtered_population.height, 0)
        self.assertEqual(empty.vintage_pairs.height, 0)
        self.assertEqual(empty.monthly_performance.height, 0)
        self.assertIsNone(empty.metrics.forecast_accuracy_pct)

    def test_quality_brand_label_is_filterable_without_losing_source_isolation(self):
        filtered = apply_dashboard_filters(
            DashboardFixtureTests.frame(),
            DashboardFilters(source="tm", brands=("Unmapped",)),
        )
        self.assertEqual(filtered["parent_code"].unique().to_list(), [500])
        self.assertEqual(filtered["brand_display"].unique().to_list(), ["Unmapped"])

    def test_horizon_controls_are_scoped_to_the_selected_source(self):
        frame = DashboardFixtureTests.horizon_frame()

        self.assertEqual(available_filter_values(frame, "tm")["horizons"], [2, 1])
        self.assertEqual(available_filter_values(frame, "ml")["horizons"], [3])

    def test_exact_horizon_filter_keeps_missing_product_targets_in_coverage_pairs(self):
        frame = DashboardFixtureTests.horizon_frame()
        actuals = DashboardFixtureTests.horizon_actual_population()
        view = build_dashboard_view(
            frame,
            actuals,
            DashboardFilters(source="tm", horizons=(2,)),
        )

        self.assertEqual(
            set(view.filtered_population["forecast_horizon_months"].to_list()), {2}
        )
        self.assertEqual(set(view.vintage_pairs["parent_code"].to_list()), {100, 200, 300})
        missing = view.vintage_pairs.filter(pl.col("parent_code") == 200).row(
            0, named=True
        )
        self.assertEqual(missing["pair_status"], "missing_both")
        self.assertIsNone(missing["vintage_a_horizon_months"])
        self.assertIsNone(missing["vintage_b_horizon_months"])
        self.assertEqual(view.metrics.complete_pairs, 2)
        self.assertEqual(view.metrics.missing_vintage_pairs, 1)
        self.assertEqual(view.metrics.forecast_kl, 200.0)
        self.assertEqual(view.metrics.actual_kl, 200.0)
        assert view.metrics.coverage_pct is not None
        self.assertAlmostEqual(view.metrics.coverage_pct, 200 / 400 * 100)
        self.assertEqual(
            view.monthly_performance["population_observations"].to_list(), [3]
        )
        self.assertEqual(
            view.horizon_performance["forecast_horizon_months"].to_list(), [2]
        )
        self.assertEqual(
            view.horizon_performance["population_observations"].to_list(), [2]
        )
        horizon_metrics = view.horizon_performance.row(0, named=True)
        self.assertEqual(horizon_metrics["forecast_accuracy_pct"], 80.0)
        self.assertEqual(horizon_metrics["bias_pct"], 0.0)
        self.assertEqual(horizon_metrics["actual_kl"], 200.0)
        self.assertEqual(horizon_metrics["forecast_kl"], 200.0)

        all_horizons = build_dashboard_view(
            frame,
            actuals,
            DashboardFilters(source="tm"),
        )
        self.assertEqual(
            all_horizons.horizon_performance["forecast_horizon_months"].to_list(),
            [2, 1],
        )
        self.assertEqual(
            all_horizons.horizon_performance["horizon_label"].to_list(),
            ["2 months ahead", "1 month ahead"],
        )
        exact_pair = select_vintage_pair(
            frame.filter(pl.col("source") == "tm"),
            "tm",
            vintage_a=VintageRule.specific_horizon(2),
            vintage_b=VintageRule.specific_horizon(2),
        )
        self.assertEqual(
            set(exact_pair.filter(pl.col("parent_code") == 200)["pair_status"]),
            {"missing_both"},
        )


class DashboardMetricTests(unittest.TestCase):
    def test_accuracy_and_bias_use_aggregate_numerators_not_subgroup_averages(self):
        pair = pl.DataFrame(
            {
                "source": ["tm", "tm"],
                "vintage_a_calculation_month": [date(2025, 1, 1), date(2025, 1, 1)],
                "vintage_b_calculation_month": [date(2025, 2, 1), date(2025, 2, 1)],
                "vintage_b_forecast_kl": [50.0, 10.0],
                "actual_kl": [100.0, 10.0],
                "pair_status": ["complete", "complete"],
            }
        )
        summary = calculate_metrics(
            pair, DashboardFixtureTests.metric_actual_population([100.0, 10.0])
        )
        assert summary.forecast_accuracy_pct is not None
        assert summary.bias_pct is not None
        self.assertAlmostEqual(summary.forecast_accuracy_pct, (1 - 50 / 110) * 100)
        self.assertAlmostEqual(summary.bias_pct, (-50 / 110) * 100)
        self.assertNotAlmostEqual(summary.forecast_accuracy_pct, 75.0)

    def test_metrics_reject_mixed_source_pairs_at_the_metric_boundary(self):
        mixed = pl.DataFrame(
            {
                "source": ["tm", "ml"],
                "vintage_a_calculation_month": [date(2025, 1, 1)] * 2,
                "vintage_b_calculation_month": [date(2025, 2, 1)] * 2,
                "vintage_b_forecast_kl": [100.0, 100.0],
                "actual_kl": [100.0, 100.0],
                "pair_status": ["complete", "complete"],
            }
        )
        with self.assertRaisesRegex(ValueError, "exactly one unique source"):
            calculate_metrics(
                mixed, DashboardFixtureTests.metric_actual_population([100.0, 100.0])
            )

    def test_metrics_require_source_column_and_non_null_values(self):
        pair = pl.DataFrame(
            {
                "source": ["tm"],
                "vintage_a_calculation_month": [date(2025, 1, 1)],
                "vintage_b_calculation_month": [date(2025, 2, 1)],
                "vintage_b_forecast_kl": [100.0],
                "actual_kl": [100.0],
                "pair_status": ["complete"],
            }
        )
        actuals = DashboardFixtureTests.metric_actual_population([100.0])
        with self.assertRaisesRegex(ValueError, "missing required column"):
            calculate_metrics(pair.drop("source"), actuals)
        with self.assertRaisesRegex(ValueError, "non-null source"):
            calculate_metrics(
                pair.with_columns(pl.lit(None, dtype=pl.String).alias("source")),
                actuals,
            )

    def test_negative_accuracy_zero_denominator_and_defined_quality_states(self):
        negative = pl.DataFrame(
            {
                "source": ["tm"],
                "vintage_a_calculation_month": [date(2025, 1, 1)],
                "vintage_b_calculation_month": [date(2025, 2, 1)],
                "vintage_b_forecast_kl": [300.0],
                "actual_kl": [100.0],
                "pair_status": ["complete"],
            }
        )
        summary = calculate_metrics(
            negative, DashboardFixtureTests.metric_actual_population([100.0])
        )
        self.assertEqual(summary.forecast_accuracy_pct, -100.0)
        self.assertEqual(summary.bias_pct, 200.0)

        zero = negative.with_columns(
            pl.lit(0.0).alias("actual_kl"), pl.lit("zero_actual").alias("pair_status")
        )
        zero_summary = calculate_metrics(
            zero, DashboardFixtureTests.metric_actual_population([0.0])
        )
        self.assertIsNone(zero_summary.forecast_accuracy_pct)
        self.assertIsNone(zero_summary.bias_pct)
        self.assertEqual(zero_summary.zero_actual_observations, 1)

        empty = calculate_metrics(
            negative.head(0), DashboardFixtureTests.metric_actual_population([])
        )
        self.assertIsNone(empty.forecast_accuracy_pct)
        self.assertIsNone(empty.coverage_pct)
        self.assertEqual(empty.eligible_observations, 0)

    def test_missing_vintage_pairs_are_statuses_not_exceptions(self):
        frame = DashboardFixtureTests.frame().filter(pl.col("source") == "tm")
        custom = pl.concat(
            [
                frame.filter(pl.col("parent_code") == 100),
                frame.filter(
                    (pl.col("parent_code") == 200)
                    & (pl.col("calculation_month") == date(2025, 2, 1))
                ),
                frame.filter(
                    (pl.col("parent_code") == 500)
                    & (pl.col("calculation_month") == date(2025, 1, 1))
                ),
                frame.filter(pl.col("parent_code") == 400).head(1).with_columns(
                    pl.lit(600).cast(pl.Int64).alias("parent_code"),
                    pl.lit("F").alias("parent_description"),
                    pl.lit(date(2025, 4, 1)).alias("calculation_month"),
                ),
            ],
            how="vertical",
        )
        pair = select_vintage_pair(
            custom,
            "tm",
            vintage_a=VintageRule.specific_calculation_month(date(2025, 1, 1)),
            vintage_b=VintageRule.specific_calculation_month(date(2025, 2, 1)),
        )
        statuses = set(pair["pair_status"].to_list())
        self.assertIn("missing_a", statuses)
        self.assertIn("missing_b", statuses)
        self.assertIn("missing_both", statuses)
        summary = calculate_metrics(pair, DashboardFixtureTests.actual_population())
        self.assertEqual(summary.complete_pairs, 1)
        self.assertEqual(summary.missing_vintage_pairs, 3)
        self.assertEqual(summary.eligible_observations, 1)
        self.assertEqual(summary.forecast_accuracy_pct, 90.0)

    def test_monthly_performance_contains_all_chart_metric_series(self):
        view = build_dashboard_view(
            DashboardFixtureTests.frame(), DashboardFixtureTests.actual_population()
        )
        self.assertEqual(
            view.monthly_performance.columns,
            [
                "source",
                "snop_month",
                "forecast_accuracy_pct",
                "bias_pct",
                "absolute_error_kl",
                "actual_kl",
                "forecast_kl",
                "coverage_pct",
                "eligible_observations",
                "population_observations",
            ],
        )
        self.assertIn(date(2026, 1, 1), view.monthly_performance["snop_month"].to_list())
        self.assertIn("forecast_accuracy_pct", view.monthly_performance.columns)
        self.assertIn("bias_pct", view.monthly_performance.columns)
        self.assertIn("absolute_error_kl", view.monthly_performance.columns)
        self.assertIn("forecast_kl", view.monthly_performance.columns)
        self.assertIn("actual_kl", view.monthly_performance.columns)


class RealDashboardCoverageTests(unittest.TestCase):
    def test_real_selected_actual_population_includes_actual_only_volume(self):
        root = Path(__file__).parents[1]
        inputs = load_analysis_inputs(
            root / "artifacts/forecast_history/consolidated/forecast_history_waterfall.csv",
            root / "artifacts/ph/PH_FG.xlsx",
            root / "artifacts/secondary_sales/Mode_Sec_Month on Month_2026_04_30.xlsb",
        )
        dataset = build_analysis_dataset(inputs)
        forecast_keys = dataset.frame.select(["parent_code", "snop_month"]).unique()
        actual_only = dataset.actual_population.select(
            ["parent_code", "snop_month"]
        ).join(forecast_keys, on=["parent_code", "snop_month"], how="anti")
        self.assertGreater(actual_only.height, 0)

        view = build_dashboard_view(
            dataset.frame,
            dataset.actual_population,
            DashboardFilters(source="tm"),
        )
        total_actual_value = dataset.actual_population["actual_kl"].sum()
        self.assertIsInstance(total_actual_value, (int, float))
        assert isinstance(total_actual_value, (int, float))
        total_actual = total_actual_value + 0.0
        self.assertIsNotNone(view.metrics.actual_kl)
        self.assertIsNotNone(view.metrics.coverage_pct)
        assert view.metrics.actual_kl is not None
        assert view.metrics.coverage_pct is not None
        self.assertAlmostEqual(
            view.metrics.coverage_pct,
            view.metrics.actual_kl / total_actual * 100,
        )
        self.assertLess(view.metrics.coverage_pct, 100.0)


if __name__ == "__main__":
    unittest.main()
