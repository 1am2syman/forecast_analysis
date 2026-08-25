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
    calculate_revision_metrics,
    format_revision_tolerance,
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

    @staticmethod
    def revision_frame() -> pl.DataFrame:
        rows = [
            (100, "Product 100", "2025-01", 100.0, 100.0),
            (100, "Product 100", "2025-02", 120.0, 100.0),
            (200, "Product 200", "2025-01", 120.0, 100.0),
            (200, "Product 200", "2025-02", 90.0, 100.0),
            (300, "Product 300", "2025-01", 100.0, 100.0),
            (300, "Product 300", "2025-02", 100.005, 100.0),
            (400, "Product 400", "2025-01", 100.0, 105.0),
            (400, "Product 400", "2025-02", 110.0, 105.0),
            (500, "Product 500", "2025-01", 100.0, 100.0),
            (600, "Product 600", "2025-02", 90.0, 100.0),
            (800, "Product 800", "2025-01", 100.0, None),
            (800, "Product 800", "2025-02", 120.0, None),
            (900, "Product 900", "2025-01", 0.0, 0.0),
            (900, "Product 900", "2025-02", 5.0, 0.0),
        ]
        return pl.DataFrame(
            {
                "source": ["tm"] * len(rows),
                "parent_code": [row[0] for row in rows],
                "parent_description": [row[1] for row in rows],
                "hierarchy_description": [row[1] for row in rows],
                "brand": [f"Brand {row[0]}" for row in rows],
                "mapping_status": ["mapped"] * len(rows),
                "mapping_diagnostic": [None] * len(rows),
                "calculation_month": [row[2] for row in rows],
                "snop_month": ["2026-01"] * len(rows),
                "forecast_horizon_months": [
                    2 if row[2] == "2025-01" else 1 for row in rows
                ],
                "forecast_kl": [row[3] for row in rows],
                "actual_kl": [row[4] for row in rows],
                "actual_status": [
                    "missing"
                    if row[4] is None
                    else "matched_zero"
                    if row[4] == 0
                    else "matched_positive"
                    for row in rows
                ],
            }
        ).with_columns(
            pl.col("parent_code").cast(pl.Int64),
            pl.col("calculation_month").str.to_date("%Y-%m"),
            pl.col("snop_month").str.to_date("%Y-%m"),
            pl.col("forecast_horizon_months").cast(pl.Int64),
            pl.col("forecast_kl").cast(pl.Float64),
            pl.col("actual_kl").cast(pl.Float64),
        )

    @staticmethod
    def revision_actual_population() -> pl.DataFrame:
        values = {
            100: 100.0,
            200: 100.0,
            300: 100.0,
            400: 105.0,
            500: 100.0,
            600: 100.0,
            800: None,
            900: 0.0,
        }
        return pl.DataFrame(
            {
                "parent_code": list(values),
                "snop_month": [date(2026, 1, 1)] * len(values),
                "actual_kl": list(values.values()),
            }
        ).with_columns(pl.col("parent_code").cast(pl.Int64))

    @staticmethod
    def revision_boundary_frame() -> pl.DataFrame:
        rows = [
            (301, 100.0, 100.01, 100.0),
            (302, 100.0, 99.99, 100.0),
            (303, 100.0, 100.011, 100.0),
            (304, 100.0, 99.989, 99.98),
        ]
        records = []
        for parent_code, vintage_a, vintage_b, actual in rows:
            for calculation_month, forecast in (
                ("2025-01", vintage_a),
                ("2025-02", vintage_b),
            ):
                records.append(
                    {
                        "source": "tm",
                        "parent_code": parent_code,
                        "parent_description": f"Product {parent_code}",
                        "hierarchy_description": f"Product {parent_code}",
                        "brand": f"Brand {parent_code}",
                        "mapping_status": "mapped",
                        "mapping_diagnostic": None,
                        "calculation_month": calculation_month,
                        "snop_month": "2026-01",
                        "forecast_horizon_months": 12,
                        "forecast_kl": forecast,
                        "actual_kl": actual,
                        "actual_status": "matched_positive",
                    }
                )
        return pl.DataFrame(records).with_columns(
            pl.col("parent_code").cast(pl.Int64),
            pl.col("calculation_month").str.to_date("%Y-%m"),
            pl.col("snop_month").str.to_date("%Y-%m"),
            pl.col("forecast_horizon_months").cast(pl.Int64),
            pl.col("forecast_kl").cast(pl.Float64),
            pl.col("actual_kl").cast(pl.Float64),
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


class DashboardRevisionTests(unittest.TestCase):
    def test_tolerance_display_preserves_tighter_values(self):
        self.assertEqual(format_revision_tolerance(0.01), "0.010 KL")
        self.assertEqual(format_revision_tolerance(0.001), "0.0010 KL")

    def test_tolerance_boundaries_are_inclusive_for_both_signs(self):
        pair = select_vintage_pair(
            DashboardFixtureTests.revision_boundary_frame(),
            "tm",
            vintage_a=VintageRule.specific_calculation_month(date(2025, 1, 1)),
            vintage_b=VintageRule.specific_calculation_month(date(2025, 2, 1)),
            revision_tolerance_kl=0.01,
        )
        classifications = pair.select(
            ["parent_code", "revision_direction", "revision_outcome"]
        ).to_dicts()
        self.assertEqual(
            classifications,
            [
                {
                    "parent_code": 301,
                    "revision_direction": "unchanged",
                    "revision_outcome": "neutral",
                },
                {
                    "parent_code": 302,
                    "revision_direction": "unchanged",
                    "revision_outcome": "neutral",
                },
                {
                    "parent_code": 303,
                    "revision_direction": "up",
                    "revision_outcome": "worsened",
                },
                {
                    "parent_code": 304,
                    "revision_direction": "down",
                    "revision_outcome": "improved",
                },
            ],
        )

    def test_calculate_revision_metrics_reclassifies_using_requested_tolerance(self):
        pair = select_vintage_pair(
            DashboardFixtureTests.revision_frame().filter(
                pl.col("parent_code") == 300
            ),
            "tm",
            vintage_a=VintageRule.specific_calculation_month(date(2025, 1, 1)),
            vintage_b=VintageRule.specific_calculation_month(date(2025, 2, 1)),
            revision_tolerance_kl=0.01,
        )
        summary = calculate_revision_metrics(pair, revision_tolerance_kl=0.001)
        self.assertEqual(summary.materially_revised_observations, 1)
        self.assertEqual(summary.worsened_revisions, 1)
        self.assertEqual(summary.revision_effectiveness_pct, 0.0)

    def test_vintage_rules_select_exact_months_and_horizons_without_mixing_sources(self):
        frame = DashboardFixtureTests.revision_frame()
        with_extra_history = pl.concat(
            [
                frame,
                frame.filter(pl.col("parent_code") == 500).head(1).with_columns(
                    pl.lit(700).cast(pl.Int64).alias("parent_code"),
                    pl.lit("Product 700").alias("parent_description"),
                    pl.lit("2025-03").str.to_date("%Y-%m").alias("calculation_month"),
                    pl.lit(0).cast(pl.Int64).alias("forecast_horizon_months"),
                ),
            ],
            how="vertical",
        )
        exact_month = select_vintage_pair(
            with_extra_history,
            "tm",
            vintage_a=VintageRule.specific_calculation_month(date(2025, 1, 15)),
            vintage_b=VintageRule.specific_calculation_month(date(2025, 2, 1)),
        )
        product_100 = exact_month.filter(pl.col("parent_code") == 100).row(
            0, named=True
        )
        self.assertEqual(product_100["vintage_a_calculation_month"], date(2025, 1, 1))
        self.assertEqual(product_100["vintage_b_calculation_month"], date(2025, 2, 1))
        self.assertEqual(
            exact_month.filter(pl.col("parent_code") == 500)["pair_status"].item(),
            "missing_b",
        )
        self.assertEqual(
            exact_month.filter(pl.col("parent_code") == 600)["pair_status"].item(),
            "missing_a",
        )
        self.assertEqual(
            exact_month.filter(pl.col("parent_code") == 700)["pair_status"].item(),
            "missing_both",
        )

        exact_horizon = select_vintage_pair(
            frame,
            "tm",
            vintage_a=VintageRule.specific_horizon(2),
            vintage_b=VintageRule.specific_horizon(1),
        )
        self.assertEqual(
            exact_horizon.filter(pl.col("parent_code") == 100)
            .select(["vintage_a_horizon_months", "vintage_b_horizon_months"])
            .row(0),
            (2, 1),
        )
        self.assertEqual(
            exact_horizon.filter(pl.col("parent_code") == 500)["pair_status"].item(),
            "missing_b",
        )

    def test_revision_metrics_match_hand_calculated_values_and_exclude_invalid_denominators(self):
        frame = DashboardFixtureTests.revision_frame()
        pair = select_vintage_pair(
            frame,
            "tm",
            vintage_a=VintageRule.specific_calculation_month(date(2025, 1, 1)),
            vintage_b=VintageRule.specific_calculation_month(date(2025, 2, 1)),
        )
        summary = calculate_metrics(
            pair,
            DashboardFixtureTests.revision_actual_population(),
        )

        product_100 = pair.filter(pl.col("parent_code") == 100).row(0, named=True)
        self.assertEqual(product_100["revision_kl"], 20.0)
        self.assertEqual(product_100["revision_pct"], 20.0)
        self.assertEqual(product_100["error_improvement_kl"], -20.0)
        self.assertEqual(product_100["revision_direction"], "up")
        self.assertEqual(product_100["revision_outcome"], "worsened")

        self.assertAlmostEqual(summary.accuracy_delta_pp or 0.0, -10.005 / 405 * 100)
        self.assertAlmostEqual(summary.total_error_improvement_kl or 0.0, -10.005)
        self.assertAlmostEqual(summary.revision_effectiveness_pct or 0.0, 1 / 3 * 100)
        self.assertEqual(summary.materially_revised_observations, 3)
        self.assertEqual(summary.improved_revisions, 1)
        self.assertEqual(summary.worsened_revisions, 1)
        self.assertEqual(summary.neutral_revisions, 1)
        self.assertEqual(summary.unchanged_revisions, 1)
        self.assertEqual(summary.complete_pairs, 4)
        self.assertEqual(summary.zero_actual_observations, 1)
        self.assertEqual(summary.missing_actual_observations, 1)

        zero_actual = pair.filter(pl.col("parent_code") == 900).row(0, named=True)
        self.assertEqual(zero_actual["pair_status"], "zero_actual")
        self.assertEqual(zero_actual["revision_kl"], 5.0)
        self.assertIsNone(zero_actual["revision_pct"])

    def test_tolerance_and_revision_filters_change_pair_outputs_but_keep_coverage(self):
        frame = DashboardFixtureTests.revision_frame()
        actuals = DashboardFixtureTests.revision_actual_population()
        default_pair = select_vintage_pair(
            frame,
            "tm",
            vintage_a=VintageRule.specific_calculation_month(date(2025, 1, 1)),
            vintage_b=VintageRule.specific_calculation_month(date(2025, 2, 1)),
        )
        default_300 = default_pair.filter(pl.col("parent_code") == 300).row(
            0, named=True
        )
        self.assertEqual(default_300["revision_direction"], "unchanged")
        self.assertEqual(default_300["revision_outcome"], "neutral")

        tight = select_vintage_pair(
            frame,
            "tm",
            vintage_a=VintageRule.specific_calculation_month(date(2025, 1, 1)),
            vintage_b=VintageRule.specific_calculation_month(date(2025, 2, 1)),
            revision_tolerance_kl=0.001,
        )
        tight_300 = tight.filter(pl.col("parent_code") == 300).row(0, named=True)
        self.assertEqual(tight_300["revision_direction"], "up")
        self.assertEqual(tight_300["revision_outcome"], "worsened")

        improved = build_dashboard_view(
            frame,
            actuals,
            DashboardFilters(
                source="tm",
                revision_outcomes=("improved",),
            ),
            vintage_a=VintageRule.specific_calculation_month(date(2025, 1, 1)),
            vintage_b=VintageRule.specific_calculation_month(date(2025, 2, 1)),
        )
        self.assertEqual(improved.vintage_pairs["parent_code"].to_list(), [200])
        self.assertEqual(improved.metrics.total_error_improvement_kl, 10.0)
        self.assertEqual(improved.coverage_pairs.height, default_pair.height)
        self.assertIn("missing_b", improved.coverage_pairs["pair_status"].to_list())
        self.assertIn("missing_a", improved.coverage_pairs["pair_status"].to_list())
        self.assertIn("missing_actual", improved.coverage_pairs["pair_status"].to_list())
        self.assertIn("zero_actual", improved.coverage_pairs["pair_status"].to_list())

    def test_revision_diagnostics_partition_valid_pairs_and_expose_scatter_points(self):
        view = build_dashboard_view(
            DashboardFixtureTests.revision_frame(),
            DashboardFixtureTests.revision_actual_population(),
            vintage_a=VintageRule.specific_calculation_month(date(2025, 1, 1)),
            vintage_b=VintageRule.specific_calculation_month(date(2025, 2, 1)),
        )
        diagnostics = view.revision_diagnostics
        self.assertEqual(diagnostics["category"].to_list(), [
            "improved",
            "worsened",
            "neutral",
            "unchanged",
        ])
        self.assertEqual(diagnostics["observations"].to_list(), [1, 1, 1, 1])
        self.assertEqual(diagnostics["observations"].sum(), view.metrics.complete_pairs)
        self.assertEqual(view.revision_scatter.height, 4)
        self.assertEqual(
            set(view.revision_scatter.columns),
            {
                "source",
                "parent_code",
                "parent_description",
                "brand",
                "snop_month",
                "actual_kl",
                "revision_kl",
                "error_improvement_kl",
                "revision_direction",
                "revision_outcome",
            },
        )


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
