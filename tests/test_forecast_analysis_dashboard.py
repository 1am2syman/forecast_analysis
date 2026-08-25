import unittest
from datetime import date
from pathlib import Path
from typing import cast

import polars as pl

from forecast_analysis import (
    AnalysisInputs,
    normalize_actuals,
    normalize_forecast_history,
    normalize_hierarchy,
)
from forecast_analysis.analysis_frame import (
    build_analysis_dataset,
    load_analysis_inputs,
)
from forecast_analysis.comparison import build_source_comparison  # pyright: ignore[reportMissingImports]
from forecast_analysis.dashboard import (  # pyright: ignore[reportMissingImports]
    DashboardView,
    build_dashboard_view,
    build_product_detail,
)
from forecast_analysis.filters import (  # pyright: ignore[reportMissingImports]
    DashboardFilters,
    apply_dashboard_filters,
    available_filter_values,
)
from forecast_analysis.metrics import (  # pyright: ignore[reportMissingImports]
    brand_target_month_order,
    build_brand_target_month_performance,
    calculate_metrics,
    calculate_revision_metrics,
    format_revision_tolerance,
)
from forecast_analysis.product_history import (  # pyright: ignore[reportMissingImports]
    build_product_history,
    search_parent_products,
)
from forecast_analysis.vintages import VintageRule, select_vintage_pair  # pyright: ignore[reportMissingImports]
from forecast_accuracy_app import (
    _build_mapped_filter_controls,
    _build_product_detail_controls,
    _build_view_controls,
)


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

    @staticmethod
    def comparison_frame() -> pl.DataFrame:
        rows = [
            ("tm", 100, "Product 100", "Brand A", "2025-11", 2, 80.0, 100.0),
            ("ml", 100, "Product 100", "Brand A", "2025-11", 2, 105.0, 100.0),
            ("tm", 100, "Product 100", "Brand A", "2025-12", 1, 95.0, 100.0),
            ("ml", 100, "Product 100", "Brand A", "2025-12", 1, 110.0, 100.0),
            ("tm", 200, "Product 200", "Brand B", "2025-12", 1, 120.0, 100.0),
            ("ml", 200, "Product 200", "Brand B", "2025-12", 1, 105.0, 100.0),
            ("tm", 300, "Product 300", "Brand C", "2025-12", 1, 100.0, 100.0),
            ("ml", 300, "Product 300", "Brand C", "2025-12", 1, 100.0, 100.0),
            ("tm", 400, "Product 400", "Brand D", "2025-12", 1, 90.0, 20.0),
            ("ml", 500, "Product 500", "Brand E", "2025-12", 1, 55.0, 80.0),
        ]
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
                "snop_month": ["2026-01"] * len(rows),
                "forecast_horizon_months": [row[5] for row in rows],
                "forecast_kl": [row[6] for row in rows],
                "actual_kl": [row[7] for row in rows],
                "actual_status": ["matched_positive"] * len(rows),
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
    def comparison_actual_population() -> pl.DataFrame:
        return pl.DataFrame(
            {
                "parent_code": [100, 200, 300, 400, 500],
                "snop_month": [date(2026, 1, 1)] * 5,
                "actual_kl": [100.0, 100.0, 100.0, 20.0, 80.0],
            }
        ).with_columns(pl.col("parent_code").cast(pl.Int64))


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
        self.assertEqual(
            set(tm.brand_target_month_performance["source"].unique()), {"tm"}
        )
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
        self.assertEqual(
            set(ml.brand_target_month_performance["source"].unique()), {"ml"}
        )
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
        heatmap = view.brand_target_month_performance
        self.assertEqual(
            heatmap.filter(pl.col("brand_display") == "Brand B")["actual_kl"].item(),
            10.0,
        )
        self.assertEqual(
            heatmap.filter(pl.col("brand_display") == "Brand B")["forecast_kl"].item(),
            20.0,
        )
        self.assertEqual(heatmap["brand_display"].to_list(), ["All brands", "Brand B"])

        empty = build_dashboard_view(
            frame,
            DashboardFixtureTests.actual_population(),
            DashboardFilters(source="tm", brands=()),
        )
        self.assertEqual(empty.filtered_population.height, 0)
        self.assertEqual(empty.vintage_pairs.height, 0)
        self.assertEqual(empty.monthly_performance.height, 0)
        self.assertIsNone(empty.metrics.forecast_accuracy_pct)

    def test_cleaned_hierarchy_duplicates_do_not_multiply_brand_target_month_volume(self):
        forecast = normalize_forecast_history(
            pl.DataFrame(
                {
                    "calculation_month": ["2025-01", "2025-02"],
                    "snop_month": ["2026-01", "2026-01"],
                    "parent_code": [100, 100],
                    "parent_description": ["Product 100", "Product 100"],
                    "qty": [80.0, 110.0],
                    "source": ["tm", "tm"],
                }
            )
        )
        hierarchy = normalize_hierarchy(
            pl.DataFrame(
                {
                    "material_code": [100, 100],
                    "material_desc": ["Product 100", "Product 100"],
                    "material_group_code": [" Brand A ", "Brand A"],
                }
            )
        )
        actuals = normalize_actuals(
            pl.DataFrame(
                {
                    "parent_material_code": [100],
                    "Month-Year": ["Jan-2026"],
                    "sec_vol_kl_mth (billwise)": [100.0],
                }
            )
        )
        dataset = build_analysis_dataset(
            AnalysisInputs(
                forecast_history=forecast,
                hierarchy=hierarchy.frame,
                actuals=actuals,
                hierarchy_diagnostics=hierarchy.diagnostics,
            )
        )
        view = build_dashboard_view(dataset.frame, dataset.actual_population)
        row = view.brand_target_month_performance.filter(
            (pl.col("brand_display") == "Brand A")
            & (pl.col("snop_month") == date(2026, 1, 1))
        ).row(0, named=True)

        self.assertEqual(dataset.frame.height, 2)
        self.assertEqual(dataset.actual_population["actual_kl"].sum(), 100.0)
        self.assertEqual(row["population_observations"], 1)
        self.assertEqual(row["actual_kl"], 100.0)
        self.assertEqual(row["forecast_kl"], 110.0)

    def test_quality_brand_labels_include_unmapped_and_conflict_groups(self):
        frame = DashboardFixtureTests.frame()
        conflict = frame.filter(pl.col("parent_code") == 100).head(1).with_columns(
            pl.lit(600).cast(pl.Int64).alias("parent_code"),
            pl.lit(None, dtype=pl.String).alias("brand"),
            pl.lit("conflict").alias("mapping_status"),
            pl.lit("conflicting brand mappings").alias("mapping_diagnostic"),
        )
        options = available_filter_values(pl.concat([frame, conflict]), "tm")
        brand_options = cast(list[str], options["brands"])
        self.assertIn("Unmapped", brand_options)
        self.assertIn("Hierarchy conflict", brand_options)

        filtered = apply_dashboard_filters(
            pl.concat([frame, conflict]),
            DashboardFilters(source="tm", brands=("Hierarchy conflict",)),
        )
        self.assertEqual(filtered["parent_code"].unique().to_list(), [600])
        self.assertEqual(
            filtered["brand_display"].unique().to_list(), ["Hierarchy conflict"]
        )
        unmapped = apply_dashboard_filters(
            frame,
            DashboardFilters(source="tm", brands=("Unmapped",)),
        )
        self.assertEqual(unmapped["parent_code"].unique().to_list(), [500])

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


class DashboardComparisonTests(unittest.TestCase):
    def test_comparison_uses_common_one_month_horizon_and_separate_source_kpis(self):
        frame = DashboardFixtureTests.comparison_frame()
        actuals = DashboardFixtureTests.comparison_actual_population()
        view = build_dashboard_view(
            frame,
            actuals,
            DashboardFilters(comparison_mode=True),
        )

        self.assertIsNotNone(view.comparison)
        comparison = view.comparison
        assert comparison is not None
        self.assertFalse(comparison.blocked)
        self.assertEqual(comparison.selected_horizon, 1)
        self.assertEqual(comparison.common_horizons, (1, 2))
        self.assertEqual(
            set(view.filtered_population["source"].unique().to_list()), {"tm", "ml"}
        )
        self.assertEqual(
            set(view.monthly_performance["source"].unique().to_list()), {"tm", "ml"}
        )
        self.assertEqual(
            set(view.brand_target_month_performance["source"].unique().to_list()),
            {"tm", "ml"},
        )

        tm = comparison.source_metrics.filter(pl.col("source") == "tm").row(
            0, named=True
        )
        ml = comparison.source_metrics.filter(pl.col("source") == "ml").row(
            0, named=True
        )
        self.assertAlmostEqual(tm["forecast_accuracy_pct"], (1 - 25 / 300) * 100)
        self.assertAlmostEqual(ml["forecast_accuracy_pct"], (1 - 15 / 300) * 100)
        self.assertEqual(tm["actual_kl"], 300.0)
        self.assertEqual(ml["actual_kl"], 300.0)
        self.assertEqual(tm["forecast_kl"], 315.0)
        self.assertEqual(ml["forecast_kl"], 315.0)
        self.assertEqual(tm["absolute_error_kl"], 25.0)
        self.assertEqual(ml["absolute_error_kl"], 15.0)
        self.assertEqual(tm["coverage_pct"], 80.0)
        self.assertEqual(ml["coverage_pct"], 95.0)

        delta_values = {
            row["metric"]: row["delta_ml_minus_tm"]
            for row in comparison.deltas.iter_rows(named=True)
        }
        self.assertAlmostEqual(
            delta_values["Forecast accuracy"], (10 / 300) * 100
        )
        self.assertEqual(delta_values["Bias"], 0.0)
        self.assertEqual(delta_values["Absolute error"], -10.0)
        self.assertEqual(delta_values["Coverage"], 15.0)
        self.assertEqual(
            comparison.population_summary.select("status").to_series().to_list(),
            ["both_sources", "tm_only", "ml_only"],
        )
        self.assertEqual(
            comparison.population_summary.select("observations").to_series().to_list(),
            [3, 1, 1],
        )
        self.assertEqual(
            comparison.population_summary.select("actual_kl").to_series().to_list(),
            [300.0, 20.0, 80.0],
        )
        self.assertEqual(
            comparison.winner_counts.select("observations").to_series().to_list(),
            [1, 1, 1],
        )
        self.assertEqual(
            comparison.paired_comparison.select("winner").to_series().to_list(),
            ["tm_better", "ml_better", "tied"],
        )

    def test_comparison_is_order_invariant_and_mismatched_horizons_are_blocked(self):
        frame = DashboardFixtureTests.comparison_frame()
        actuals = DashboardFixtureTests.comparison_actual_population()
        filters = DashboardFilters(comparison_mode=True)
        first = build_source_comparison(frame, actuals, filters)
        reversed_result = build_source_comparison(frame.reverse(), actuals, filters)

        columns = [
            "parent_code",
            "snop_month",
            "tm_forecast_kl",
            "ml_forecast_kl",
            "winner",
        ]
        self.assertEqual(
            first.paired_comparison.select(columns).to_dicts(),
            reversed_result.paired_comparison.select(columns).to_dicts(),
        )
        self.assertEqual(
            first.source_metrics.to_dicts(),
            reversed_result.source_metrics.to_dicts(),
        )

        blocked = build_dashboard_view(
            frame,
            actuals,
            DashboardFilters(comparison_mode=True, horizons=(1, 2)),
        )
        assert blocked.comparison is not None
        self.assertTrue(blocked.comparison.blocked)
        self.assertIn("one shared exact horizon", blocked.comparison.warning or "")

        conflicting_horizon_filter = build_dashboard_view(
            frame,
            actuals,
            DashboardFilters(
                comparison_mode=True,
                horizons=(1,),
                comparison_horizon=2,
            ),
        )
        assert conflicting_horizon_filter.comparison is not None
        self.assertTrue(conflicting_horizon_filter.comparison.blocked)
        self.assertIn(
            "comparison horizon and forecast-horizon filter do not match",
            conflicting_horizon_filter.comparison.warning or "",
        )

        unavailable_horizon = build_dashboard_view(
            frame,
            actuals,
            DashboardFilters(comparison_mode=True, comparison_horizon=3),
        )
        assert unavailable_horizon.comparison is not None
        self.assertTrue(unavailable_horizon.comparison.blocked)
        self.assertIn(
            "selected exact horizon",
            unavailable_horizon.comparison.warning or "",
        )

    def test_comparison_is_exact_horizon_only_and_ignores_vintage_revision_controls(self):
        frame = DashboardFixtureTests.comparison_frame()
        actuals = DashboardFixtureTests.comparison_actual_population()
        baseline = build_dashboard_view(
            frame,
            actuals,
            DashboardFilters(comparison_mode=True, horizons=(1,)),
        )
        controlled = build_dashboard_view(
            frame,
            actuals,
            DashboardFilters(
                comparison_mode=True,
                horizons=(1,),
                revision_directions=("up",),
                revision_outcomes=("improved",),
            ),
            vintage_a=VintageRule.specific_horizon(2),
            vintage_b=VintageRule.latest_available(),
        )

        assert baseline.comparison is not None
        assert controlled.comparison is not None
        self.assertIsNone(controlled.filters.revision_directions)
        self.assertIsNone(controlled.filters.revision_outcomes)
        self.assertEqual(controlled.comparison.selected_horizon, 1)
        self.assertEqual(
            controlled.comparison.alignment_rule,
            "specific_horizon:1",
        )
        self.assertEqual(
            baseline.comparison.paired_comparison.to_dicts(),
            controlled.comparison.paired_comparison.to_dicts(),
        )
        self.assertEqual(
            baseline.comparison.source_metrics.to_dicts(),
            controlled.comparison.source_metrics.to_dicts(),
        )


class DashboardMetricTests(unittest.TestCase):
    def test_brand_target_month_metrics_include_all_required_views_and_sorting(self):
        pair = select_vintage_pair(
            DashboardFixtureTests.revision_frame(),
            "tm",
            vintage_a=VintageRule.specific_calculation_month(date(2025, 1, 1)),
            vintage_b=VintageRule.specific_calculation_month(date(2025, 2, 1)),
        ).filter(pl.col("parent_code").is_in([100, 200]))
        actual_population = pair.select(
            [
                "parent_code",
                "snop_month",
                "actual_kl",
                "brand",
                "mapping_status",
                "mapping_diagnostic",
            ]
        ).unique(subset=["parent_code", "snop_month"])

        heatmap = build_brand_target_month_performance(pair, actual_population)
        required_columns = {
            "source",
            "brand_display",
            "snop_month",
            "forecast_accuracy_pct",
            "bias_pct",
            "absolute_error_kl",
            "vintage_a_accuracy_pct",
            "vintage_b_accuracy_pct",
            "accuracy_delta_pp",
            "revision_effectiveness_pct",
            "actual_kl",
            "eligible_observations",
        }
        self.assertTrue(required_columns.issubset(set(heatmap.columns)))
        self.assertEqual(
            set(heatmap["brand_display"].to_list()),
            {"All brands", "Brand 100", "Brand 200"},
        )
        brand_100 = heatmap.filter(pl.col("brand_display") == "Brand 100").row(
            0, named=True
        )
        self.assertEqual(brand_100["actual_kl"], 100.0)
        self.assertEqual(brand_100["eligible_observations"], 1)
        self.assertEqual(brand_100["vintage_a_accuracy_pct"], 100.0)
        self.assertEqual(brand_100["vintage_b_accuracy_pct"], 80.0)
        self.assertEqual(brand_100["accuracy_delta_pp"], -20.0)
        self.assertEqual(brand_100["revision_effectiveness_pct"], 0.0)
        self.assertEqual(
            brand_target_month_order(heatmap, "vintage_b_accuracy")[:2],
            ["All brands", "Brand 100"],
        )
        self.assertEqual(
            brand_target_month_order(heatmap, "bias")[:2],
            ["All brands", "Brand 100"],
        )

    def test_brand_sorting_uses_weighted_aggregate_keys(self):
        pair = pl.DataFrame(
            {
                "source": ["tm"] * 4,
                "parent_code": [1, 2, 3, 4],
                "brand": ["Brand A", "Brand A", "Brand B", "Brand B"],
                "mapping_status": ["mapped"] * 4,
                "snop_month": [
                    date(2026, 1, 1),
                    date(2026, 2, 1),
                    date(2026, 1, 1),
                    date(2026, 2, 1),
                ],
                "actual_kl": [1000.0, 1.0, 1.0, 1000.0],
                "vintage_a_forecast_kl": [1000.0, 0.0, 1.0, 500.0],
                "vintage_b_forecast_kl": [500.0, 1.0, 0.4, 600.0],
                "pair_status": ["complete"] * 4,
            }
        )
        actual_population = pair.select(
            ["parent_code", "snop_month", "actual_kl", "brand", "mapping_status"]
        )
        heatmap = build_brand_target_month_performance(pair, actual_population)

        self.assertEqual(
            brand_target_month_order(heatmap, "forecast_accuracy"),
            ["All brands", "Brand A", "Brand B"],
        )
        self.assertEqual(
            brand_target_month_order(heatmap, "bias"),
            ["All brands", "Brand A", "Brand B"],
        )
        self.assertEqual(
            brand_target_month_order(heatmap, "accuracy_delta"),
            ["All brands", "Brand A", "Brand B"],
        )
        self.assertEqual(
            brand_target_month_order(heatmap, "absolute_error"),
            ["All brands", "Brand A", "Brand B"],
        )

    def test_revision_sorting_uses_aggregate_improvement_counts(self):
        rows = []
        parent_code = 1
        for brand, month, improved, worsened in (
            ("Brand A", date(2026, 1, 1), 1, 0),
            ("Brand A", date(2026, 2, 1), 0, 9),
            ("Brand B", date(2026, 1, 1), 2, 3),
            ("Brand B", date(2026, 2, 1), 2, 3),
        ):
            for _ in range(improved):
                rows.append(
                    {
                        "source": "tm",
                        "parent_code": parent_code,
                        "brand": brand,
                        "mapping_status": "mapped",
                        "snop_month": month,
                        "actual_kl": 100.0,
                        "vintage_a_forecast_kl": 0.0,
                        "vintage_b_forecast_kl": 100.0,
                        "pair_status": "complete",
                    }
                )
                parent_code += 1
            for _ in range(worsened):
                rows.append(
                    {
                        "source": "tm",
                        "parent_code": parent_code,
                        "brand": brand,
                        "mapping_status": "mapped",
                        "snop_month": month,
                        "actual_kl": 100.0,
                        "vintage_a_forecast_kl": 100.0,
                        "vintage_b_forecast_kl": 0.0,
                        "pair_status": "complete",
                    }
                )
                parent_code += 1
        pair = pl.DataFrame(rows)
        actual_population = pair.select(
            ["parent_code", "snop_month", "actual_kl", "brand", "mapping_status"]
        )
        heatmap = build_brand_target_month_performance(pair, actual_population)

        self.assertEqual(
            brand_target_month_order(heatmap, "revision_effectiveness"),
            ["All brands", "Brand A", "Brand B"],
        )

    def test_heatmap_counts_are_metric_specific(self):
        pair = select_vintage_pair(
            DashboardFixtureTests.revision_frame().filter(
                pl.col("parent_code").is_in([100, 900])
            ),
            "tm",
            vintage_a=VintageRule.specific_calculation_month(date(2025, 1, 1)),
            vintage_b=VintageRule.specific_calculation_month(date(2025, 2, 1)),
        )
        actual_population = pair.select(
            [
                "parent_code",
                "snop_month",
                "actual_kl",
                "brand",
                "mapping_status",
                "mapping_diagnostic",
            ]
        )
        heatmap = build_brand_target_month_performance(pair, actual_population)
        zero_actual = heatmap.filter(pl.col("brand_display") == "Brand 900").row(
            0, named=True
        )
        revised = heatmap.filter(pl.col("brand_display") == "Brand 100").row(
            0, named=True
        )

        self.assertEqual(zero_actual["eligible_observations"], 0)
        self.assertEqual(zero_actual["vintage_a_eligible_observations"], 0)
        self.assertEqual(zero_actual["vintage_b_eligible_observations"], 0)
        self.assertEqual(zero_actual["absolute_error_observations"], 1)
        self.assertEqual(revised["improved_revisions"], 0)
        self.assertEqual(revised["materially_revised_observations"], 1)

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

    def test_brand_heatmap_revision_metrics_use_active_tolerance(self):
        frame = DashboardFixtureTests.revision_frame().filter(
            pl.col("parent_code") == 300
        )
        actuals = DashboardFixtureTests.revision_actual_population()
        vintage_a = VintageRule.specific_calculation_month(date(2025, 1, 1))
        vintage_b = VintageRule.specific_calculation_month(date(2025, 2, 1))

        loose = build_dashboard_view(
            frame,
            actuals,
            DashboardFilters(source="tm", revision_tolerance_kl=0.005),
            vintage_a=vintage_a,
            vintage_b=vintage_b,
        )
        tight = build_dashboard_view(
            frame,
            actuals,
            DashboardFilters(source="tm", revision_tolerance_kl=0.001),
            vintage_a=vintage_a,
            vintage_b=vintage_b,
        )
        loose_row = loose.brand_target_month_performance.filter(
            pl.col("brand_display") == "Brand 300"
        ).row(0, named=True)
        tight_row = tight.brand_target_month_performance.filter(
            pl.col("brand_display") == "Brand 300"
        ).row(0, named=True)

        self.assertEqual(
            loose.vintage_pairs.select(
                ["revision_direction", "revision_outcome"]
            ).row(0),
            ("unchanged", "neutral"),
        )
        self.assertEqual(
            tight.vintage_pairs.select(
                ["revision_direction", "revision_outcome"]
            ).row(0),
            ("up", "worsened"),
        )
        self.assertEqual(loose.metrics.materially_revised_observations, 0)
        self.assertIsNone(loose.metrics.revision_effectiveness_pct)
        self.assertEqual(loose_row["materially_revised_observations"], 0)
        self.assertIsNone(loose_row["revision_effectiveness_pct"])
        self.assertEqual(tight.metrics.materially_revised_observations, 1)
        self.assertEqual(tight.metrics.revision_effectiveness_pct, 0.0)
        self.assertEqual(tight_row["materially_revised_observations"], 1)
        self.assertEqual(tight_row["revision_effectiveness_pct"], 0.0)

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

    def test_real_comparison_coverage_includes_asymmetric_source_only_volume(self):
        root = Path(__file__).parents[1]
        inputs = load_analysis_inputs(
            root / "artifacts/forecast_history/consolidated/forecast_history_waterfall.csv",
            root / "artifacts/ph/PH_FG.xlsx",
            root / "artifacts/secondary_sales/Mode_Sec_Month on Month_2026_04_30.xlsb",
        )
        dataset = build_analysis_dataset(inputs)
        view = build_dashboard_view(
            dataset.frame,
            dataset.actual_population,
            DashboardFilters(comparison_mode=True),
        )

        self.assertIsNotNone(view.comparison)
        comparison = view.comparison
        assert comparison is not None
        self.assertFalse(comparison.blocked)
        self.assertEqual(comparison.selected_horizon, 1)

        summary = {
            row["population"]: row
            for row in comparison.population_summary.iter_rows(named=True)
        }
        selected_actual = comparison.selected_actual_population["actual_kl"].sum()
        self.assertIsInstance(selected_actual, (int, float))
        assert isinstance(selected_actual, (int, float))
        expected_tm_coverage = (
            summary["common"]["actual_kl"] + summary["tm_only"]["actual_kl"]
        ) / selected_actual * 100
        expected_ml_coverage = (
            summary["common"]["actual_kl"] + summary["ml_only"]["actual_kl"]
        ) / selected_actual * 100
        self.assertEqual(
            [summary[key]["observations"] for key in ("common", "tm_only", "ml_only")],
            [1275, 430, 229],
        )
        self.assertGreater(summary["tm_only"]["actual_kl"], 0.0)
        self.assertGreater(summary["ml_only"]["actual_kl"], 0.0)

        metrics = {
            row["source"]: row
            for row in comparison.source_metrics.iter_rows(named=True)
        }
        self.assertAlmostEqual(metrics["tm"]["coverage_pct"], expected_tm_coverage)
        self.assertAlmostEqual(metrics["ml"]["coverage_pct"], expected_ml_coverage)
        self.assertAlmostEqual(metrics["tm"]["coverage_pct"], 89.9026408913838)
        self.assertAlmostEqual(metrics["ml"]["coverage_pct"], 97.62780544682361)
        self.assertGreater(metrics["ml"]["coverage_pct"], metrics["tm"]["coverage_pct"])
        coverage_delta = next(
            row["delta_ml_minus_tm"]
            for row in comparison.deltas.iter_rows(named=True)
            if row["metric"] == "Coverage"
        )
        self.assertAlmostEqual(
            coverage_delta,
            expected_ml_coverage - expected_tm_coverage,
        )
        self.assertGreater(coverage_delta, 0.0)


class ProductVintageHistoryTests(unittest.TestCase):
    @staticmethod
    def history_frame() -> pl.DataFrame:
        rows = [
            # Deliberately unordered: the implementation must sort by calculation month.
            ("tm", 100, "Alpha 100", "2025-03", 130.0, 10, 110.0, "matched_positive"),
            ("tm", 100, "Alpha 100", "2025-01", 100.0, 12, 110.0, "matched_positive"),
            ("ml", 100, "Alpha 100", "2025-03", 100.0, 10, 110.0, "matched_positive"),
            ("tm", 100, "Alpha 100", "2025-02", 120.0, 11, 110.0, "matched_positive"),
            ("ml", 100, "Alpha 100", "2025-01", 90.0, 12, 110.0, "matched_positive"),
            # One vintage is an explicit insufficient-history case.
            ("tm", 200, "Beta 200", "2025-01", 50.0, 12, 100.0, "matched_positive"),
            # Two source-specific vintages with incomplete actual history.
            ("tm", 300, "Gamma 300", "2025-03", 15.0, 10, None, "missing"),
            ("tm", 300, "Gamma 300", "2025-01", 10.0, 12, None, "missing"),
        ]
        return pl.DataFrame(
            {
                "source": [row[0] for row in rows],
                "parent_code": [row[1] for row in rows],
                "parent_description": [row[2] for row in rows],
                "hierarchy_description": [row[2] for row in rows],
                "brand": ["Brand A" if row[1] == 100 else "Brand B" for row in rows],
                "mapping_status": ["mapped"] * len(rows),
                "mapping_diagnostic": [None] * len(rows),
                "calculation_month": [row[3] for row in rows],
                "snop_month": ["2026-01"] * len(rows),
                "forecast_horizon_months": [row[5] for row in rows],
                "forecast_kl": [row[4] for row in rows],
                "actual_kl": [row[6] for row in rows],
                "actual_status": [row[7] for row in rows],
            }
        ).with_columns(
            pl.col("parent_code").cast(pl.Int64),
            pl.col("calculation_month").str.to_date("%Y-%m"),
            pl.col("snop_month").str.to_date("%Y-%m"),
            pl.col("forecast_horizon_months").cast(pl.Int64),
            pl.col("forecast_kl").cast(pl.Float64),
            pl.col("actual_kl").cast(pl.Float64),
        )

    def test_search_matches_code_or_description_and_respects_target_month(self):
        frame = self.history_frame()
        by_code = search_parent_products(
            frame,
            "200",
            sources=("tm",),
            target_month=date(2026, 1, 1),
        )
        self.assertEqual(by_code["parent_code"].to_list(), [200])
        by_description = search_parent_products(
            frame,
            "alpha",
            sources=("tm", "ml"),
            target_month="2026-01",
        )
        self.assertEqual(by_description["parent_code"].to_list(), [100])
        self.assertEqual(by_description["display_label"].item(), "100 — Alpha 100")

    def test_history_is_order_invariant_and_exposes_auditable_points(self):
        frame = self.history_frame()
        ordered = build_product_history(
            frame.sort(["source", "calculation_month"]),
            100,
            date(2026, 1, 1),
            sources=("tm", "ml"),
        )
        unordered = build_product_history(
            frame.reverse(),
            100,
            "2026-01",
            sources=("tm", "ml"),
        )

        self.assertEqual(ordered.points.to_dicts(), unordered.points.to_dicts())
        self.assertEqual(ordered.revisions.to_dicts(), unordered.revisions.to_dicts())
        self.assertEqual(ordered.stability.to_dicts(), unordered.stability.to_dicts())
        self.assertEqual(
            ordered.points.columns,
            [
                "source",
                "parent_code",
                "parent_description",
                "hierarchy_description",
                "brand",
                "mapping_status",
                "snop_month",
                "calculation_month",
                "forecast_horizon_months",
                "forecast_kl",
                "actual_kl",
                "actual_status",
                "error_kl",
                "bias_pct",
            ],
        )
        self.assertEqual(
            ordered.points.filter(pl.col("source") == "tm")["calculation_month"].to_list(),
            [date(2025, 1, 1), date(2025, 2, 1), date(2025, 3, 1)],
        )
        self.assertEqual(ordered.actual_reference["actual_kl"].to_list(), [110.0])
        self.assertEqual(ordered.points.filter(pl.col("source") == "tm")["error_kl"].to_list(), [-10.0, 10.0, 20.0])

    def test_revisions_are_consecutive_and_source_specific(self):
        history = build_product_history(
            self.history_frame(),
            100,
            date(2026, 1, 1),
            sources=("tm", "ml"),
        )
        revisions = history.revisions
        self.assertEqual(revisions.filter(pl.col("source") == "tm")["revision_kl"].to_list(), [20.0, 10.0])
        self.assertEqual(revisions.filter(pl.col("source") == "tm")["revision_direction"].to_list(), ["up", "up"])
        self.assertEqual(revisions.filter(pl.col("source") == "tm")["revision_outcome"].to_list(), ["neutral", "worsened"])
        self.assertEqual(revisions.filter(pl.col("source") == "ml")["revision_kl"].to_list(), [10.0])
        self.assertEqual(revisions.filter(pl.col("source") == "ml")["revision_outcome"].to_list(), ["improved"])
        self.assertEqual(
            revisions.filter(pl.col("source") == "tm")["previous_calculation_month"].to_list(),
            [date(2025, 1, 1), date(2025, 2, 1)],
        )
        self.assertEqual(
            revisions.filter(pl.col("source") == "ml")["previous_calculation_month"].to_list(),
            [date(2025, 1, 1)],
        )

    def test_stability_metrics_are_independent_and_use_population_standard_deviation(self):
        history = build_product_history(
            self.history_frame(),
            100,
            date(2026, 1, 1),
            sources=("tm", "ml"),
        )
        stability = {
            row["source"]: row for row in history.stability.iter_rows(named=True)
        }
        tm = stability["tm"]
        ml = stability["ml"]
        self.assertEqual(tm["vintage_count"], 3)
        self.assertEqual(tm["forecast_range_kl"], 30.0)
        self.assertAlmostEqual(
            tm["population_std_dev_kl"],
            sum((value - (100 + 120 + 130) / 3) ** 2 for value in (100, 120, 130))
            ** 0.5
            / 3**0.5,
        )
        self.assertEqual(tm["revision_count"], 2)
        self.assertEqual(tm["maximum_absolute_revision_kl"], 20.0)
        self.assertEqual(ml["vintage_count"], 2)
        self.assertEqual(ml["forecast_range_kl"], 10.0)
        self.assertEqual(ml["population_std_dev_kl"], 5.0)
        self.assertEqual(ml["revision_count"], 1)
        self.assertEqual(ml["maximum_absolute_revision_kl"], 10.0)
        self.assertEqual(history.status, "ready")

    def test_view_and_source_dropdowns_use_display_keys_and_domain_values(self):
        import marimo as mo

        view_mode, source = _build_view_controls(mo)

        self.assertEqual(view_mode.selected_key, "Single source")
        self.assertEqual(view_mode.value, "single")
        self.assertEqual(source.selected_key, "TM")
        self.assertEqual(source.value, "tm")

    def test_mapped_filter_controls_use_display_keys_and_domain_values(self):
        import marimo as mo

        (
            horizons,
            vintage_a_rule,
            vintage_b_rule,
            vintage_a_month,
            vintage_b_month,
            vintage_a_horizon,
            vintage_b_horizon,
            revision_directions,
            revision_outcomes,
        ) = _build_mapped_filter_controls(
            mo,
            [12, 6],
            [12],
            [date(2025, 1, 1), date(2025, 2, 1)],
            horizon_label="Comparison horizon (exact)",
        )

        self.assertEqual(horizons.value, [12])
        self.assertEqual(horizons.options, {"12 months ahead": 12, "6 months ahead": 6})
        self.assertEqual(vintage_a_rule.selected_key, "Oldest available")
        self.assertEqual(vintage_a_rule.value, "oldest_available")
        self.assertEqual(vintage_b_rule.selected_key, "Latest available")
        self.assertEqual(vintage_b_rule.value, "latest_available")
        self.assertEqual(vintage_a_month.selected_key, "2025-01-01")
        self.assertEqual(vintage_a_month.value, date(2025, 1, 1))
        self.assertEqual(vintage_b_month.selected_key, "2025-01-01")
        self.assertEqual(vintage_b_month.value, date(2025, 1, 1))
        self.assertEqual(vintage_a_horizon.selected_key, "12 months ahead")
        self.assertEqual(vintage_a_horizon.value, 12)
        self.assertEqual(vintage_b_horizon.selected_key, "12 months ahead")
        self.assertEqual(vintage_b_horizon.value, 12)
        self.assertEqual(revision_directions.value, ["up", "down", "unchanged"])
        self.assertEqual(revision_outcomes.value, ["improved", "worsened", "neutral"])

    def test_product_detail_dropdowns_use_valid_option_keys_and_domain_values(self):
        frame = DashboardFixtureTests.frame()
        options = available_filter_values(frame, "tm")
        products = options["parent_products"]
        target_months = options["target_months"]

        import marimo as mo

        product_dropdown, target_month_dropdown = _build_product_detail_controls(
            mo,
            products,
            target_months,
        )

        self.assertEqual(product_dropdown.selected_key, "100 — A")
        self.assertEqual(product_dropdown.value, 100)
        self.assertEqual(target_month_dropdown.selected_key, "2026-01-01")
        self.assertEqual(target_month_dropdown.value, date(2026, 1, 1))

    def test_comparison_detail_uses_comparison_horizon_when_horizon_filter_is_none(self):
        detail = build_product_detail(
            self.history_frame(),
            DashboardFilters(
                comparison_mode=True,
                comparison_horizon=12,
                horizons=None,
            ),
            100,
            date(2026, 1, 1),
        )
        self.assertEqual(detail.points["forecast_horizon_months"].to_list(), [12, 12])
        self.assertEqual(detail.revisions.height, 0)

    def test_comparison_detail_rejects_conflicting_or_multi_horizon_filters(self):
        for horizons in ((10,), (12, 10)):
            with self.subTest(horizons=horizons):
                with self.assertRaisesRegex(ValueError, "one exact horizon"):
                    build_product_detail(
                        self.history_frame(),
                        DashboardFilters(
                            comparison_mode=True,
                            comparison_horizon=12,
                            horizons=horizons,
                        ),
                        100,
                        date(2026, 1, 1),
                    )

    def test_comparison_detail_uses_exact_horizon_and_keeps_sources_separate(self):
        detail = build_product_detail(
            self.history_frame(),
            DashboardFilters(
                comparison_mode=True,
                comparison_horizon=12,
                horizons=(12,),
            ),
            100,
            date(2026, 1, 1),
        )
        self.assertEqual(set(detail.points["source"].to_list()), {"tm", "ml"})
        self.assertEqual(detail.points.group_by("source").len().sort("source").to_dicts(), [
            {"source": "ml", "len": 1},
            {"source": "tm", "len": 1},
        ])
        self.assertEqual(detail.points["forecast_horizon_months"].to_list(), [12, 12])
        self.assertEqual(detail.revisions.height, 0)
        self.assertEqual(
            set(detail.stability["history_status"].to_list()),
            {"insufficient_history"},
        )

        standard = build_product_detail(
            self.history_frame(),
            DashboardFilters(source="tm", horizons=(12,)),
            100,
            date(2026, 1, 1),
        )
        self.assertEqual(standard.points["calculation_month"].to_list(), [date(2025, 1, 1)])
        self.assertEqual(
            standard.stability["history_status"].to_list(),
            ["insufficient_history"],
        )

    def test_incomplete_and_single_vintage_histories_show_explicit_states(self):
        single = build_product_history(
            self.history_frame(),
            200,
            date(2026, 1, 1),
            sources=("tm", "ml"),
        )
        self.assertEqual(single.status, "insufficient_history")
        self.assertIn("At least two", single.status_message)
        self.assertEqual(
            single.stability.filter(pl.col("source") == "tm")["history_status"].item(),
            "insufficient_history",
        )
        self.assertIsNone(
            single.stability.filter(pl.col("source") == "tm")["forecast_range_kl"].item()
        )
        self.assertEqual(
            single.stability.filter(pl.col("source") == "ml")["history_status"].item(),
            "no_history",
        )
        incomplete_actual = build_product_history(
            self.history_frame(),
            300,
            date(2026, 1, 1),
            sources=("tm",),
        )
        self.assertEqual(incomplete_actual.status, "ready")
        self.assertEqual(incomplete_actual.revisions.height, 1)
        self.assertIsNone(incomplete_actual.revisions["error_improvement_kl"].item())


if __name__ == "__main__":
    unittest.main()
