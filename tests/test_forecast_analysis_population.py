import unittest
from datetime import date
from pathlib import Path

import polars as pl

from forecast_analysis import (
    AnalysisInputs,
    build_analysis_dataset,
    load_analysis_inputs,
    normalize_actuals,
    normalize_forecast_history,
    normalize_hierarchy,
)
from forecast_analysis.contracts import (
    ACTUAL_COLUMNS,
    ANALYSIS_COLUMNS,
    HIERARCHY_COLUMNS,
    NORMALIZED_FORECAST_COLUMNS,
)


class ForecastHistoryNormalizationTests(unittest.TestCase):
    @staticmethod
    def rows(**overrides):
        row = {
            "calculation_month": "2025-12",
            "snop_month": "2026-01",
            "parent_code": 100,
            "parent_description": " Product 100 ",
            "qty": 10,
            "source": "TM",
        }
        row.update(overrides)
        return pl.DataFrame([row])

    def test_normalizes_types_renames_qty_and_derives_horizon(self):
        result = normalize_forecast_history(
            pl.concat(
                [
                    self.rows(),
                    self.rows(source="ml", parent_code=101, qty=12),
                ]
            )
        )

        self.assertEqual(result.columns, NORMALIZED_FORECAST_COLUMNS)
        self.assertEqual(result.schema["calculation_month"], pl.Date)
        self.assertEqual(result.schema["snop_month"], pl.Date)
        self.assertEqual(result.schema["parent_code"], pl.Int64)
        self.assertEqual(result.schema["forecast_kl"], pl.Float64)
        self.assertEqual(result["parent_description"].to_list(), ["Product 100", "Product 100"])
        self.assertEqual(result["forecast_horizon_months"].to_list(), [1, 1])
        self.assertEqual(set(result["source"].to_list()), {"tm", "ml"})

    def test_same_key_across_sources_is_valid_but_duplicate_within_source_fails(self):
        same_key = pl.concat([self.rows(), self.rows(source="ml")])
        self.assertEqual(normalize_forecast_history(same_key).height, 2)

        with self.assertRaisesRegex(ValueError, "duplicate keys within a source"):
            normalize_forecast_history(pl.concat([self.rows(), self.rows()]))

    def test_blocking_forecast_quality_rules_are_explicit(self):
        with self.assertRaisesRegex(ValueError, "unsupported source"):
            normalize_forecast_history(self.rows(source="other"))

        with self.assertRaisesRegex(ValueError, "missing required column"):
            normalize_forecast_history(self.rows().drop("qty"))

        cases = [
            ("negative horizon", {"snop_month": "2025-11"}, "non-negative"),
            ("negative quantity", {"qty": -1}, "non-negative"),
            ("non-finite quantity", {"qty": float("nan")}, "finite non-negative"),
            ("invalid parent code", {"parent_code": "100.5"}, "exact Int64"),
            ("invalid calculation month", {"calculation_month": "not-a-month"}, "invalid month"),
            ("blank source", {"source": " "}, "non-null text"),
            ("null source", {"source": None}, "non-null text"),
            ("blank description", {"parent_description": " "}, "non-null text"),
            ("null description", {"parent_description": None}, "non-null text"),
        ]
        for name, overrides, message in cases:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, message):
                normalize_forecast_history(self.rows(**overrides))


class HierarchyNormalizationTests(unittest.TestCase):
    @staticmethod
    def source_rows():
        return pl.DataFrame(
            {
                "material_code": [100, 100, 200, 200, 300],
                "material_desc": [
                    " Z description ",
                    "A description",
                    "Conflict product",
                    "Conflict product",
                    "Unmapped product",
                ],
                "material_group_code": [" Brand A ", "Brand A", "Brand A", "Brand B", "   "],
            }
        )

    def test_agreeing_duplicates_collapse_and_description_ties_are_deterministic(self):
        result = normalize_hierarchy(self.source_rows())

        self.assertEqual(result.frame.columns, HIERARCHY_COLUMNS)
        self.assertEqual(result.frame.height, 3)
        self.assertEqual(
            result.frame.filter(pl.col("parent_code") == 100).row(0, named=True),
            {
                "parent_code": 100,
                "hierarchy_description": "A description",
                "brand": "Brand A",
                "mapping_status": "mapped",
            },
        )

    def test_conflicts_and_missing_brands_remain_visible_with_diagnostics(self):
        result = normalize_hierarchy(self.source_rows())

        self.assertEqual(
            result.frame.filter(pl.col("parent_code") == 200)["mapping_status"].item(),
            "conflict",
        )
        self.assertIsNone(result.frame.filter(pl.col("parent_code") == 200)["brand"].item())
        conflict = result.diagnostics.filter(pl.col("parent_code") == 200).row(0, named=True)
        self.assertIn("Brand A | Brand B", conflict["diagnostic"])

        self.assertEqual(
            result.frame.filter(pl.col("parent_code") == 300)["mapping_status"].item(),
            "unmapped",
        )
        self.assertEqual(
            result.diagnostics.filter(pl.col("parent_code") == 300)["diagnostic"].item(),
            "no usable brand mapping",
        )

    def test_empty_hierarchy_is_a_valid_all_unmapped_population(self):
        result = normalize_hierarchy(
            pl.DataFrame(
                {
                    "material_code": pl.Series([], dtype=pl.Int64),
                    "material_desc": pl.Series([], dtype=pl.String),
                    "material_group_code": pl.Series([], dtype=pl.String),
                }
            )
        )
        self.assertEqual(result.frame.height, 0)
        self.assertEqual(result.diagnostics.height, 0)

    def test_invalid_hierarchy_schema_and_key_are_blocking(self):
        with self.assertRaisesRegex(ValueError, "missing required column"):
            normalize_hierarchy(self.source_rows().drop("material_group_code"))
        invalid = self.source_rows().with_columns(
            pl.when(pl.col("material_code") == 100)
            .then(pl.lit("100.5"))
            .otherwise(pl.col("material_code").cast(pl.String))
            .alias("material_code")
        )
        with self.assertRaisesRegex(ValueError, "exact Int64"):
            normalize_hierarchy(invalid)


class ActualNormalizationTests(unittest.TestCase):
    @staticmethod
    def source_rows():
        return pl.DataFrame(
            {
                "parent_material_code": [100, 100, 101, 102],
                "Month-Year": ["Jan-2026", "Jan-2026", "Feb-2026", "Mar-2026"],
                "sec_vol_kl_mth (billwise)": [1.25, 2.75, 0.0, 4.0],
            }
        )

    def test_actuals_normalize_and_aggregate_to_parent_target_grain(self):
        result = normalize_actuals(self.source_rows())

        self.assertEqual(result.columns, ACTUAL_COLUMNS)
        self.assertEqual(result.schema["snop_month"], pl.Date)
        self.assertEqual(result.schema["parent_code"], pl.Int64)
        self.assertEqual(result.filter(pl.col("parent_code") == 100)["actual_kl"].item(), 4.0)
        self.assertEqual(result.filter(pl.col("parent_code") == 101)["actual_kl"].item(), 0.0)
        self.assertEqual(result.height, 3)

    def test_empty_actuals_are_valid_and_leave_forecasts_missing(self):
        result = normalize_actuals(
            pl.DataFrame(
                {
                    "parent_material_code": pl.Series([], dtype=pl.String),
                    "Month-Year": pl.Series([], dtype=pl.String),
                    "sec_vol_kl_mth (billwise)": pl.Series([], dtype=pl.Float64),
                }
            )
        )
        self.assertEqual(result.schema["actual_kl"], pl.Float64)
        self.assertEqual(result.height, 0)

    def test_actuals_block_material_invariants(self):
        cases = [
            ("NaN actual", float("nan"), [100], "finite numeric"),
            ("positive infinity actual", float("inf"), [100], "finite numeric"),
            ("negative infinity actual", float("-inf"), [100], "finite numeric"),
            ("null actual", None, [100], "finite numeric"),
            ("invalid parent code", 1.0, ["100.5"], "exact Int64"),
            ("null parent code", 1.0, [None], "exact Int64"),
        ]
        for name, actual, parent_codes, message in cases:
            with self.subTest(name=name):
                frame = pl.DataFrame(
                    {
                        "parent_material_code": parent_codes,
                        "Month-Year": ["Jan-2026"],
                        "sec_vol_kl_mth (billwise)": [actual],
                    }
                )
                with self.assertRaisesRegex(ValueError, message):
                    normalize_actuals(frame)

        with self.assertRaisesRegex(ValueError, "invalid month"):
            normalize_actuals(
                self.source_rows().with_columns(
                    pl.lit("not-a-month").alias("Month-Year")
                )
            )
        with self.assertRaisesRegex(ValueError, "missing required field"):
            normalize_actuals(self.source_rows().drop("Month-Year"))

    def test_out_of_window_invalid_actuals_are_ignored(self):
        result = normalize_actuals(
            pl.DataFrame(
                {
                    "parent_material_code": [100, 100, 100],
                    "Month-Year": ["Aug-2024", "Sep-2024", "Jun-2025"],
                    "sec_vol_kl_mth (billwise)": [-1.0, float("nan"), 2.0],
                }
            ),
            target_months=[date(2025, 6, 1)],
        )
        self.assertEqual(
            result.to_dicts(),
            [{"parent_code": 100, "snop_month": date(2025, 6, 1), "actual_kl": 2.0}],
        )

    def test_in_window_negative_actuals_are_blocking(self):
        with self.assertRaisesRegex(ValueError, "non-negative"):
            normalize_actuals(
                pl.DataFrame(
                    {
                        "parent_material_code": [100],
                        "Month-Year": ["Jun-2025"],
                        "sec_vol_kl_mth (billwise)": [-1.0],
                    }
                ),
                target_months=[date(2025, 6, 1)],
            )

    def test_aggregation_overflow_is_blocking(self):
        with self.assertRaisesRegex(ValueError, "aggregated actual_kl.*finite"):
            normalize_actuals(
                pl.DataFrame(
                    {
                        "parent_material_code": [100, 100],
                        "Month-Year": ["Jan-2026", "Jan-2026"],
                        "sec_vol_kl_mth (billwise)": [1e308, 1e308],
                    }
                )
            )


class CanonicalPopulationTests(unittest.TestCase):
    def test_population_preserves_quality_states_and_reports_source_coverage(self):
        forecast = normalize_forecast_history(
            pl.DataFrame(
                {
                    "calculation_month": ["2025-05", "2025-05", "2025-05", "2025-05"],
                    "snop_month": ["2025-06", "2025-06", "2025-06", "2025-07"],
                    "parent_code": [100, 100, 200, 300],
                    "parent_description": ["A", "A", "B", "C"],
                    "qty": [10.0, 12.0, 0.0, 5.0],
                    "source": ["tm", "ml", "tm", "ml"],
                }
            )
        )
        hierarchy = normalize_hierarchy(
            pl.DataFrame(
                {
                    "material_code": [100, 200, 200],
                    "material_desc": ["A", "B", "B"],
                    "material_group_code": ["Brand A", "Brand A", "Brand B"],
                }
            )
        )
        actuals = normalize_actuals(
            pl.DataFrame(
                {
                    "parent_material_code": [100, 200],
                    "Month-Year": ["Jun-2025", "Jun-2025"],
                    "sec_vol_kl_mth (billwise)": [8.0, 0.0],
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

        self.assertEqual(dataset.frame.columns, ANALYSIS_COLUMNS)
        self.assertEqual(dataset.frame.height, 4)
        self.assertEqual(set(dataset.frame["source"].to_list()), {"tm", "ml"})
        self.assertEqual(
            dataset.frame.group_by("actual_status").len().sort("actual_status").to_dicts(),
            [
                {"actual_status": "matched_positive", "len": 2},
                {"actual_status": "matched_zero", "len": 1},
                {"actual_status": "missing", "len": 1},
            ],
        )
        self.assertEqual(
            dataset.frame.filter(pl.col("parent_code") == 200)["mapping_status"].unique().to_list(),
            ["conflict"],
        )
        self.assertEqual(
            dataset.frame.filter(pl.col("parent_code") == 300)["mapping_status"].unique().to_list(),
            ["unmapped"],
        )
        self.assertEqual(
            dataset.frame.filter(pl.col("parent_code") == 300)["actual_status"].item(),
            "missing",
        )
        self.assertEqual(
            dataset.frame.filter(pl.col("parent_code") == 300)["mapping_diagnostic"].item(),
            "no hierarchy mapping",
        )

        diagnostics = dataset.diagnostics
        self.assertEqual(diagnostics.filter(pl.col("diagnostic_group") == "summary")["rows"].item(), 4)
        self.assertEqual(
            set(
                diagnostics.filter(pl.col("diagnostic_group") == "source")["source"].to_list()
            ),
            {"tm", "ml"},
        )
        self.assertEqual(
            set(
                diagnostics.filter(pl.col("diagnostic_group") == "hierarchy_status")["status"].to_list()
            ),
            {"mapped", "unmapped", "conflict"},
        )
        coverage = diagnostics.filter(pl.col("diagnostic_group") == "source_coverage")
        self.assertEqual(coverage.height, 9)
        self.assertEqual(set(coverage["source"].to_list()), {"all", "tm", "ml"})
        self.assertEqual(
            set(coverage.filter(pl.col("source") != "all")["status"].to_list()),
            {"matched_positive", "matched_zero", "missing"},
        )
        self.assertEqual(
            coverage.filter(
                (pl.col("source") == "all") & (pl.col("status") == "both_sources")
            )["rows"].item(),
            1,
        )


class CurrentConsolidatedArtifactTests(unittest.TestCase):
    def test_current_consolidated_artifact_normalizes_with_both_sources(self):
        path = Path(__file__).parents[1] / "artifacts/forecast_history/consolidated/forecast_history_waterfall.csv"
        result = normalize_forecast_history(pl.read_csv(path))

        self.assertEqual(result.height, 16_035)
        self.assertEqual(result["source"].value_counts().sort("source").to_dicts(), [
            {"source": "ml", "count": 7520},
            {"source": "tm", "count": 8515},
        ])
        self.assertEqual(result.select("source").n_unique(), 2)

    def test_current_inputs_build_canonical_population(self):
        root = Path(__file__).parents[1]
        inputs = load_analysis_inputs(
            root / "artifacts/forecast_history/consolidated/forecast_history_waterfall.csv",
            root / "artifacts/ph/PH_FG.xlsx",
            root / "artifacts/secondary_sales/Mode_Sec_Month on Month_2026_04_30.xlsb",
        )
        dataset = build_analysis_dataset(inputs)

        self.assertEqual(dataset.frame.height, inputs.forecast_history.height)
        self.assertEqual(dataset.frame.height, 16_035)
        self.assertEqual(inputs.actuals.height, 1_679)
        self.assertEqual(dataset.diagnostics.height, 18)
        self.assertEqual(set(dataset.frame["source"].unique().to_list()), {"ml", "tm"})


if __name__ == "__main__":
    unittest.main()
