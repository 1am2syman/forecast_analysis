import unittest
from datetime import date

import polars as pl

from forecast_analysis import (
    AnalysisInputs,
    DashboardFilters,
    build_analysis_dataset,
    build_dashboard_view,
    build_product_detail,
    normalize_actuals,
    normalize_forecast_history,
    normalize_hierarchy,
)
from forecast_analysis.quality import build_quality_view  # pyright: ignore[reportMissingImports]


class QualityFixture:
    @staticmethod
    def frame() -> pl.DataFrame:
        rows = [
            ("tm", 100, "Mapped product", "Brand A", "mapped", "2025-01", 80.0, 100.0),
            ("tm", 100, "Mapped product", "Brand A", "mapped", "2025-02", 110.0, 100.0),
            ("ml", 100, "Mapped product", "Brand A", "mapped", "2025-01", 75.0, 100.0),
            ("ml", 100, "Mapped product", "Brand A", "mapped", "2025-02", 105.0, 100.0),
            ("tm", 200, "Unmapped product", None, "unmapped", "2025-01", 0.0, 0.0),
            ("tm", 200, "Unmapped product", None, "unmapped", "2025-02", 5.0, 0.0),
            ("tm", 300, "Missing actual", "Brand C", "mapped", "2025-01", 10.0, None),
            ("tm", 300, "Missing actual", "Brand C", "mapped", "2025-02", 12.0, None),
            ("tm", 400, "TM only", "Brand D", "mapped", "2025-01", 20.0, 40.0),
            ("tm", 400, "TM only", "Brand D", "mapped", "2025-02", 25.0, 40.0),
            ("ml", 500, "ML only", "Brand E", "mapped", "2025-01", 30.0, 50.0),
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
                    None if row[4] == "mapped" else "no usable brand mapping"
                    for row in rows
                ],
                "calculation_month": [row[5] for row in rows],
                "snop_month": ["2026-01"] * len(rows),
                "forecast_horizon_months": [12] * len(rows),
                "forecast_kl": [row[6] for row in rows],
                "actual_kl": [row[7] for row in rows],
                "actual_status": [
                    "missing"
                    if row[7] is None
                    else "matched_zero"
                    if row[7] == 0
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
    def actual_population() -> pl.DataFrame:
        return pl.DataFrame(
            {
                "parent_code": [100, 200, 300, 400, 500],
                "snop_month": [date(2026, 1, 1)] * 5,
                "actual_kl": [100.0, 0.0, None, 40.0, 50.0],
            }
        ).with_columns(pl.col("parent_code").cast(pl.Int64))

    @staticmethod
    def horizon_frame() -> pl.DataFrame:
        rows = [
            ("tm", 100, "Brand A", date(2025, 11, 1), 2, 80.0),
            ("tm", 100, "Brand A", date(2025, 12, 1), 1, 90.0),
            ("tm", 200, "Brand B", date(2025, 12, 1), 1, 20.0),
            ("tm", 300, "Brand C", date(2025, 11, 1), 2, 120.0),
        ]
        return pl.DataFrame(
            {
                "source": [row[0] for row in rows],
                "parent_code": [row[1] for row in rows],
                "parent_description": [f"Product {row[1]}" for row in rows],
                "hierarchy_description": [f"Product {row[1]}" for row in rows],
                "brand": [row[2] for row in rows],
                "mapping_status": ["mapped"] * len(rows),
                "mapping_diagnostic": [None] * len(rows),
                "calculation_month": [row[3] for row in rows],
                "snop_month": [date(2026, 1, 1)] * len(rows),
                "forecast_horizon_months": [row[4] for row in rows],
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
    def horizon_availability_frame() -> pl.DataFrame:
        rows = [
            ("tm", 10, date(2025, 11, 1), 2, 10.0, 100.0),
            ("ml", 10, date(2025, 12, 1), 1, 11.0, 100.0),
            ("tm", 20, date(2025, 11, 1), 2, 20.0, 200.0),
            ("ml", 20, date(2025, 11, 1), 2, 21.0, 200.0),
            ("ml", 30, date(2025, 11, 1), 2, 30.0, 300.0),
        ]
        return pl.DataFrame(
            {
                "source": [row[0] for row in rows],
                "parent_code": [row[1] for row in rows],
                "parent_description": [f"Product {row[1]}" for row in rows],
                "hierarchy_description": [f"Product {row[1]}" for row in rows],
                "brand": [f"Brand {row[1]}" for row in rows],
                "mapping_status": ["mapped"] * len(rows),
                "mapping_diagnostic": [None] * len(rows),
                "calculation_month": [row[2] for row in rows],
                "snop_month": [date(2026, 1, 1)] * len(rows),
                "forecast_horizon_months": [row[3] for row in rows],
                "forecast_kl": [row[4] for row in rows],
                "actual_kl": [row[5] for row in rows],
                "actual_status": ["matched_positive"] * len(rows),
            }
        ).with_columns(
            pl.col("parent_code").cast(pl.Int64),
            pl.col("forecast_horizon_months").cast(pl.Int64),
            pl.col("forecast_kl").cast(pl.Float64),
            pl.col("actual_kl").cast(pl.Float64),
        )

    @staticmethod
    def actual_union_frame() -> tuple[pl.DataFrame, pl.DataFrame]:
        frame = pl.DataFrame(
            {
                "source": ["tm", "ml", "tm"],
                "parent_code": [100, 100, 200],
                "parent_description": ["Product 100", "Product 100", "Product 200"],
                "hierarchy_description": ["Product 100", "Product 100", "Product 200"],
                "brand": ["Brand A", "Brand A", "Brand B"],
                "mapping_status": ["mapped"] * 3,
                "mapping_diagnostic": [None] * 3,
                "calculation_month": [date(2025, 12, 1)] * 3,
                "snop_month": [date(2026, 1, 1)] * 3,
                "forecast_horizon_months": [1] * 3,
                "forecast_kl": [10.0, 11.0, 20.0],
                "actual_kl": [100.0, 100.0, None],
                "actual_status": ["matched_positive", "matched_positive", "missing"],
            }
        ).with_columns(
            pl.col("parent_code").cast(pl.Int64),
            pl.col("forecast_horizon_months").cast(pl.Int64),
            pl.col("forecast_kl").cast(pl.Float64),
            pl.col("actual_kl").cast(pl.Float64),
        )
        actuals = pl.DataFrame(
            {
                "parent_code": [100, 200, 300, 301],
                "snop_month": [date(2026, 1, 1)] * 4,
                "actual_kl": [100.0, None, 300.0, 0.0],
            }
        ).with_columns(pl.col("parent_code").cast(pl.Int64))
        return frame, actuals

    @staticmethod
    def history_filter_frame() -> pl.DataFrame:
        rows = [
            (100, date(2025, 11, 1), 1, 0.0),
            (100, date(2025, 10, 1), 2, 10.0),
            (200, date(2025, 12, 1), 1, 5.0),
            (300, date(2025, 11, 1), 1, 6.0),
            (300, date(2025, 10, 1), 2, 0.0),
        ]
        return pl.DataFrame(
            {
                "source": ["tm"] * len(rows),
                "parent_code": [row[0] for row in rows],
                "parent_description": [f"Product {row[0]}" for row in rows],
                "hierarchy_description": [f"Product {row[0]}" for row in rows],
                "brand": ["Brand A", "Brand A", "Brand B", "Brand C", "Brand C"],
                "mapping_status": ["mapped"] * len(rows),
                "mapping_diagnostic": [None] * len(rows),
                "calculation_month": [row[1] for row in rows],
                "snop_month": [date(2026, 1, 1)] * len(rows),
                "forecast_horizon_months": [row[2] for row in rows],
                "forecast_kl": [row[3] for row in rows],
                "actual_kl": [100.0, 100.0, 200.0, 300.0, 300.0],
                "actual_status": ["matched_positive"] * len(rows),
            }
        ).with_columns(
            pl.col("parent_code").cast(pl.Int64),
            pl.col("forecast_horizon_months").cast(pl.Int64),
            pl.col("forecast_kl").cast(pl.Float64),
            pl.col("actual_kl").cast(pl.Float64),
        )


class QualityWorkflowTests(unittest.TestCase):
    def test_quality_panel_keeps_excluded_actual_rows_and_reports_all_populations(self):
        view = build_dashboard_view(
            QualityFixture.frame(),
            QualityFixture.actual_population(),
        )

        self.assertEqual(
            set(view.quality.hierarchy["status"].to_list()),
            {"mapped", "unmapped", "conflict"},
        )
        self.assertEqual(
            set(view.quality.actual["status"].to_list()),
            {"matched_positive", "matched_zero", "missing"},
        )
        self.assertEqual(
            set(view.quality.pairs["status"].to_list()),
            {
                "complete",
                "missing_a",
                "missing_b",
                "missing_both",
                "missing_actual",
                "zero_actual",
            },
        )
        self.assertEqual(
            set(view.quality.source_availability["status"].to_list()),
            {"tm_only", "both_sources"},
        )
        self.assertEqual(
            view.quality.actual.filter(pl.col("status") == "missing")[
                "observations"
            ].item(),
            1,
        )
        self.assertEqual(view.metrics.eligible_observations, 2)
        self.assertIn("actual", view.quality.exceptions)
        self.assertIn("missing", view.quality.explanations["actual"])

    def test_quality_status_filters_isolate_metrics_without_rewriting_quality_totals(self):
        missing = build_dashboard_view(
            QualityFixture.frame(),
            QualityFixture.actual_population(),
            DashboardFilters(source="tm", actual_statuses=("missing",)),
        )
        self.assertIsNone(missing.metrics.forecast_accuracy_pct)
        self.assertEqual(
            missing.quality.actual.filter(pl.col("status") == "missing")[
                "observations"
            ].item(),
            1,
        )
        self.assertEqual(missing.quality.pairs["observations"].sum(), 4)

        complete_only = build_dashboard_view(
            QualityFixture.frame(),
            QualityFixture.actual_population(),
            DashboardFilters(source="tm", pair_statuses=("complete",)),
        )
        self.assertEqual(
            set(complete_only.vintage_pairs["pair_status"].to_list()), {"complete"}
        )
        self.assertEqual(
            set(complete_only.quality.pairs["status"].to_list()),
            {
                "complete",
                "missing_a",
                "missing_b",
                "missing_both",
                "missing_actual",
                "zero_actual",
            },
        )
        self.assertEqual(complete_only.metrics.eligible_observations, 2)
        assert complete_only.metrics.coverage_pct is not None
        self.assertAlmostEqual(complete_only.metrics.coverage_pct, 100.0)

        unmapped = build_dashboard_view(
            QualityFixture.frame(),
            QualityFixture.actual_population(),
            DashboardFilters(source="tm", hierarchy_statuses=("unmapped",)),
        )
        self.assertEqual(unmapped.vintage_pairs["parent_code"].unique().to_list(), [200])
        self.assertEqual(unmapped.quality.hierarchy["observations"].sum(), 4)

        tm_only = build_dashboard_view(
            QualityFixture.frame(),
            QualityFixture.actual_population(),
            DashboardFilters(source="tm", source_availability=("tm_only",)),
        )
        self.assertEqual(
            set(tm_only.vintage_pairs["parent_code"].to_list()), {200, 300, 400}
        )
        self.assertEqual(tm_only.quality.source_availability["observations"].sum(), 4)

    def test_quality_explanations_and_exception_download_frames_cover_each_category(self):
        view = build_dashboard_view(
            QualityFixture.frame(),
            QualityFixture.actual_population(),
        )

        for category in ("hierarchy", "actual", "pairs", "source_availability"):
            self.assertTrue(view.quality.explanations[category])
            self.assertIn(category, view.quality.exceptions)
            exceptions = view.quality.exceptions[category]
            self.assertIn("quality_status", exceptions.columns)
            self.assertIn("quality_explanation", exceptions.columns)
            self.assertGreater(exceptions.height, 0)
            self.assertIn("quality_explanation", exceptions.write_csv())

    def test_blocking_input_errors_are_separate_from_non_blocking_quality(self):
        quality = build_quality_view(
            QualityFixture.frame(),
            QualityFixture.actual_population(),
            build_dashboard_view(
                QualityFixture.frame(), QualityFixture.actual_population()
            ).coverage_pairs,
            source_availability_population=QualityFixture.frame(),
            blocking_errors=("forecast history duplicate key",),
        )

        self.assertEqual(quality.blocking_errors, ("forecast history duplicate key",))
        self.assertTrue(quality.non_blocking_diagnostics.height > 0)
        self.assertTrue(all(not value for value in quality.counts["blocking"].to_list()))

    def test_exact_horizon_and_product_detail_share_quality_selection(self):
        actuals = pl.DataFrame(
            {
                "parent_code": [100, 200, 300],
                "snop_month": [date(2026, 1, 1)] * 3,
                "actual_kl": [100.0, 100.0, 100.0],
            }
        ).with_columns(pl.col("parent_code").cast(pl.Int64))
        view = build_dashboard_view(
            QualityFixture.horizon_frame(),
            actuals,
            DashboardFilters(source="tm", horizons=(2,)),
        )
        self.assertEqual(view.quality.pairs["observations"].sum(), 3)
        self.assertEqual(
            view.quality.pairs.filter(pl.col("status") == "missing_both")[
                "observations"
            ].item(),
            1,
        )

        detail = build_product_detail(
            QualityFixture.frame(),
            DashboardFilters(source="tm", actual_statuses=("missing",)),
            300,
            date(2026, 1, 1),
        )
        self.assertEqual(detail.points.height, 2)
        self.assertTrue((detail.points["actual_status"] == "missing").all())

    def test_comparison_quality_keeps_source_availability_populations(self):
        view = build_dashboard_view(
            QualityFixture.frame(),
            QualityFixture.actual_population(),
            DashboardFilters(comparison_mode=True, horizons=(12,)),
        )
        availability = view.quality.source_availability
        self.assertEqual(
            availability.filter(pl.col("status") == "both_sources")[
                "observations"
            ].item(),
            1,
        )
        self.assertEqual(
            availability.filter(pl.col("status") == "tm_only")[
                "observations"
            ].item(),
            3,
        )
        self.assertEqual(
            availability.filter(pl.col("status") == "ml_only")[
                "observations"
            ].item(),
            1,
        )

    def test_source_availability_is_horizon_specific_and_standard_mode_hides_opposite_only_rows(self):
        frame = QualityFixture.horizon_availability_frame()
        actuals = pl.DataFrame(
            {
                "parent_code": [10, 20, 30],
                "snop_month": [date(2026, 1, 1)] * 3,
                "actual_kl": [100.0, 200.0, 300.0],
            }
        ).with_columns(pl.col("parent_code").cast(pl.Int64))

        comparison = build_dashboard_view(
            frame,
            actuals,
            DashboardFilters(comparison_mode=True, horizons=(2,)),
        )
        comparison_statuses = {
            row["status"]: row["observations"]
            for row in comparison.quality.source_availability.iter_rows(named=True)
        }
        self.assertEqual(comparison_statuses, {"tm_only": 1, "ml_only": 1, "both_sources": 1})
        self.assertEqual(comparison.selected_actual_population["actual_kl"].sum(), 600.0)
        self.assertIsNotNone(comparison.comparison)
        aligned = comparison.comparison
        assert aligned is not None
        self.assertEqual(
            aligned.population_summary.select("status").to_series().to_list(),
            ["both_sources", "tm_only", "ml_only"],
        )
        self.assertEqual(
            aligned.population_summary.select("observations").to_series().to_list(),
            [1, 1, 1],
        )

        standard = build_dashboard_view(
            frame,
            actuals,
            DashboardFilters(source="tm", horizons=(2,)),
        )
        standard_statuses = {
            row["status"]: row["observations"]
            for row in standard.quality.source_availability.iter_rows(named=True)
            if row["observations"]
        }
        self.assertEqual(standard_statuses, {"tm_only": 1, "both_sources": 1})
        self.assertEqual(set(standard.filtered_population["parent_code"].to_list()), {10, 20})
        self.assertEqual(standard.selected_actual_population["actual_kl"].sum(), 300.0)

        tm_only = build_dashboard_view(
            frame,
            actuals,
            DashboardFilters(source="tm", horizons=(2,), source_availability=("tm_only",)),
        )
        both_only = build_dashboard_view(
            frame,
            actuals,
            DashboardFilters(source="tm", horizons=(2,), source_availability=("both_sources",)),
        )
        self.assertEqual(set(tm_only.filtered_population["parent_code"].to_list()), {10})
        self.assertEqual(set(both_only.filtered_population["parent_code"].to_list()), {20})
        self.assertEqual(tm_only.selected_actual_population["actual_kl"].sum(), 100.0)
        opposite_only = build_dashboard_view(
            frame,
            actuals,
            DashboardFilters(
                source="tm", horizons=(2,), source_availability=("ml_only",)
            ),
        )
        self.assertEqual(opposite_only.filtered_population.height, 0)
        self.assertEqual(opposite_only.selected_actual_population.height, 0)

    def test_actual_quality_is_forecast_actual_key_union_without_comparison_duplication(self):
        frame, actuals = QualityFixture.actual_union_frame()
        view = build_dashboard_view(
            frame,
            actuals,
            DashboardFilters(comparison_mode=True, horizons=(1,)),
        )
        counts = {
            row["status"]: row["observations"]
            for row in view.quality.actual.iter_rows(named=True)
        }
        self.assertEqual(counts, {"matched_positive": 2, "matched_zero": 1, "missing": 1})
        self.assertEqual(view.quality.actual["observations"].sum(), 4)
        actual_exception_codes = set(view.quality.exceptions["actual"]["parent_code"].to_list())
        self.assertEqual(actual_exception_codes, {200, 300, 301})
        self.assertIn(
            "actual_only",
            set(
                view.quality.exceptions["actual"].filter(
                    pl.col("parent_code") == 300
                )["quality_status"].to_list()
            ),
        )
        self.assertEqual(view.selected_actual_population["parent_code"].n_unique(), 4)

    def test_hierarchy_exception_decorates_production_conflict_candidates_and_csv(self):
        frame = QualityFixture.frame().with_columns(
            pl.when(pl.col("parent_code") == 100)
            .then(pl.lit("conflict"))
            .otherwise(pl.col("mapping_status"))
            .alias("mapping_status"),
            pl.when(pl.col("parent_code") == 100)
            .then(pl.lit("conflicting brand mappings: Brand A | Brand B"))
            .otherwise(pl.col("mapping_diagnostic"))
            .alias("mapping_diagnostic"),
        )
        hierarchy_diagnostics = normalize_hierarchy(
            pl.DataFrame(
                {
                    "material_code": [100, 100],
                    "material_desc": ["P100 A", "P100 B"],
                    "material_group_code": ["Brand A", "Brand B"],
                }
            )
        ).diagnostics
        view = build_dashboard_view(
            frame,
            QualityFixture.actual_population(),
            hierarchy_diagnostics=hierarchy_diagnostics,
        )

        hierarchy_exceptions = view.quality.exceptions["hierarchy"].filter(
            pl.col("parent_code") == 100
        )
        self.assertEqual(
            hierarchy_exceptions["candidate_brands"].to_list(),
            ["Brand A | Brand B"],
        )
        self.assertEqual(
            hierarchy_exceptions["candidate_descriptions"].to_list(),
            ["P100 A | P100 B"],
        )
        self.assertIn("Brand A | Brand B", hierarchy_exceptions.write_csv())
        self.assertIn("P100 A | P100 B", hierarchy_exceptions.write_csv())

    def test_exception_downloads_are_exception_only_and_preserve_category_evidence(self):
        frame = QualityFixture.frame().with_columns(
            pl.lit("candidate A | candidate B").alias("candidate_brands"),
            pl.lit("description A | description B").alias("candidate_descriptions"),
        )
        view = build_dashboard_view(frame, QualityFixture.actual_population())

        hierarchy_exceptions = view.quality.exceptions["hierarchy"]
        self.assertNotIn("mapped", set(hierarchy_exceptions["quality_status"].to_list()))
        self.assertIn("candidate_brands", hierarchy_exceptions.columns)
        self.assertIn("candidate_descriptions", hierarchy_exceptions.columns)
        self.assertIn("mapping_diagnostic", hierarchy_exceptions.columns)

        actual_exceptions = view.quality.exceptions["actual"]
        self.assertNotIn("matched_positive", set(actual_exceptions["quality_status"].to_list()))
        self.assertTrue({"missing", "matched_zero"}.issuperset(actual_exceptions["quality_status"].unique()))

        pair_exceptions = view.quality.exceptions["pairs"]
        self.assertNotIn("complete", set(pair_exceptions["quality_status"].to_list()))
        self.assertTrue(
            {
                "vintage_a_rule",
                "vintage_b_rule",
                "vintage_a_calculation_month",
                "vintage_b_calculation_month",
                "vintage_a_horizon_months",
                "vintage_b_horizon_months",
                "vintage_a_forecast_kl",
                "vintage_b_forecast_kl",
                "revision_kl",
                "error_improvement_kl",
            }.issubset(pair_exceptions.columns)
        )

        source_exceptions = view.quality.exceptions["source_availability"]
        self.assertNotIn("both_sources", set(source_exceptions["quality_status"].to_list()))
        self.assertIn("available_sources", source_exceptions.columns)
        self.assertIn("available_horizons", source_exceptions.columns)

    def test_zero_forecast_only_selects_latest_vintage_before_filtering_pairs(self):
        rows = [
            (100, date(2025, 10, 1), 2, 0.0, 1000.0),
            (100, date(2025, 11, 1), 1, 10.0, 1000.0),
            (300, date(2025, 10, 1), 2, 5.0, 300.0),
            (300, date(2025, 11, 1), 1, 0.0, 300.0),
        ]
        frame = pl.DataFrame(
            {
                "source": ["tm"] * len(rows),
                "parent_code": [row[0] for row in rows],
                "parent_description": [f"Product {row[0]}" for row in rows],
                "hierarchy_description": [f"Product {row[0]}" for row in rows],
                "brand": ["Brand A", "Brand A", "Brand C", "Brand C"],
                "mapping_status": ["mapped"] * len(rows),
                "mapping_diagnostic": [None] * len(rows),
                "calculation_month": [row[1] for row in rows],
                "snop_month": [date(2026, 1, 1)] * len(rows),
                "forecast_horizon_months": [row[2] for row in rows],
                "forecast_kl": [row[3] for row in rows],
                "actual_kl": [row[4] for row in rows],
                "actual_status": ["matched_positive"] * len(rows),
            }
        ).with_columns(
            pl.col("parent_code").cast(pl.Int64),
            pl.col("forecast_horizon_months").cast(pl.Int64),
            pl.col("forecast_kl").cast(pl.Float64),
            pl.col("actual_kl").cast(pl.Float64),
        )
        actuals = pl.DataFrame(
            {
                "parent_code": [100, 300],
                "snop_month": [date(2026, 1, 1)] * 2,
                "actual_kl": [1000.0, 300.0],
            }
        ).with_columns(pl.col("parent_code").cast(pl.Int64))

        view = build_dashboard_view(
            frame,
            actuals,
            DashboardFilters(source="tm", zero_forecast_only=True),
        )

        self.assertEqual(view.vintage_pairs["parent_code"].to_list(), [300])
        selected = view.vintage_pairs.row(0, named=True)
        self.assertEqual(selected["vintage_a_calculation_month"], date(2025, 10, 1))
        self.assertEqual(selected["vintage_b_calculation_month"], date(2025, 11, 1))
        self.assertEqual(selected["vintage_a_forecast_kl"], 5.0)
        self.assertEqual(selected["vintage_b_forecast_kl"], 0.0)
        self.assertEqual(selected["revision_kl"], -5.0)
        self.assertEqual(view.selected_actual_population["parent_code"].to_list(), [300])
        self.assertEqual(view.selected_actual_population["actual_kl"].sum(), 300.0)
        self.assertEqual(view.filtered_population["parent_code"].unique().to_list(), [300])
        self.assertEqual(
            view.horizon_performance["forecast_horizon_months"].to_list(),
            [1],
        )
        self.assertEqual(
            set(view.filtered_population["parent_code"].unique().to_list()),
            set(view.vintage_pairs["parent_code"].to_list()),
        )
        self.assertEqual(
            set(view.filtered_population["parent_code"].unique().to_list()),
            set(view.selected_actual_population["parent_code"].to_list()),
        )
        self.assertEqual(view.metrics.coverage_pct, 100.0)
        self.assertTrue(
            all(
                coverage <= 100.0
                for coverage in view.horizon_performance["coverage_pct"].drop_nulls().to_list()
            )
        )

    def test_zero_forecast_and_complete_history_filters_have_explicit_denominator_semantics(self):
        frame = QualityFixture.history_filter_frame()
        actuals = pl.DataFrame(
            {
                "parent_code": [100, 200, 300],
                "snop_month": [date(2026, 1, 1)] * 3,
                "actual_kl": [100.0, 200.0, 300.0],
            }
        ).with_columns(pl.col("parent_code").cast(pl.Int64))

        zero_forecasts = build_dashboard_view(
            frame,
            actuals,
            DashboardFilters(source="tm", horizons=(2,), zero_forecast_only=True),
        )
        self.assertEqual(set(zero_forecasts.filtered_population["parent_code"].to_list()), {300})
        self.assertEqual(zero_forecasts.selected_actual_population["actual_kl"].sum(), 300.0)
        self.assertEqual(zero_forecasts.metrics.forecast_kl, 0.0)
        self.assertEqual(zero_forecasts.quality.hierarchy["observations"].sum(), 3)

        complete_history = build_dashboard_view(
            frame,
            actuals,
            DashboardFilters(
                source="tm",
                horizons=(1, 2),
                complete_vintage_history_only=True,
            ),
        )
        self.assertEqual(set(complete_history.filtered_population["parent_code"].to_list()), {100, 300})
        self.assertEqual(complete_history.selected_actual_population["actual_kl"].sum(), 400.0)
        self.assertEqual(complete_history.quality.hierarchy["observations"].sum(), 3)


if __name__ == "__main__":
    unittest.main()
