from __future__ import annotations

import unittest
from datetime import date

import polars as pl

from forecast_analysis import (
    VintageAccuracyRow,
    VintageRule,
    build_common_vintage_accuracy,
    build_vintage_gap_drilldown,
)


class CommonVintageAccuracyTests(unittest.TestCase):
    @staticmethod
    def frame() -> pl.DataFrame:
        records: list[dict[str, object]] = []

        def add_history(
            parent_code: int,
            target_month: date,
            actual_kl: float | None,
            forecasts: tuple[
                float | None,
                float | None,
                float | None,
                float | None,
            ],
        ) -> None:
            for calculation_month, horizon, forecast_kl in zip(
                (
                    date(2025, 8, 1),
                    date(2025, 9, 1),
                    date(2025, 11, 1),
                    date(2025, 12, 1),
                ),
                (5, 4, 2, 1),
                forecasts,
                strict=True,
            ):
                if forecast_kl is None:
                    continue
                records.append(
                    {
                        "source": "tm",
                        "parent_code": parent_code,
                        "parent_description": f"Parent {parent_code}",
                        "brand_display": (
                            "Brand A" if parent_code % 2 else "Brand B"
                        ),
                        "calculation_month": calculation_month,
                        "snop_month": target_month,
                        "forecast_horizon_months": horizon,
                        "forecast_kl": forecast_kl,
                        "actual_kl": actual_kl,
                    }
                )

        january = date(2026, 1, 1)
        add_history(101, january, 100.0, (80.0, 85.0, 90.0, 130.0))
        # Parent 102 has M4 but no M5. Oldest must not fall forward to M4.
        add_history(102, january, 50.0, (None, 40.0, None, 55.0))
        add_history(103, january, 25.0, (25.0, 24.0, 20.0, 20.0))
        add_history(104, january, 0.0, (0.0, 0.0, 0.0, 0.0))
        add_history(105, january, None, (10.0, 10.0, 10.0, 10.0))

        february = date(2026, 2, 1)
        add_history(201, february, 200.0, (150.0, 160.0, 190.0, 210.0))
        add_history(202, february, 100.0, (90.0, 95.0, 120.0, 70.0))

        return pl.DataFrame(records).with_columns(
            pl.col("parent_code").cast(pl.Int64),
            pl.col("calculation_month").cast(pl.Date),
            pl.col("snop_month").cast(pl.Date),
            pl.col("forecast_horizon_months").cast(pl.Int64),
            pl.col("forecast_kl").cast(pl.Float64),
            pl.col("actual_kl").cast(pl.Float64),
        )

    @staticmethod
    def rows_by_month(
        rows: tuple[VintageAccuracyRow, ...],
    ) -> dict[date, VintageAccuracyRow]:
        return {row.target_month: row for row in rows}

    def test_missing_selected_vintage_is_excluded_from_every_series(self) -> None:
        result = build_common_vintage_accuracy(
            self.frame().reverse(),
            "tm",
            comparison_rules=(
                VintageRule.oldest_available(),
                VintageRule.specific_horizon(2),
            ),
        )

        self.assertEqual(
            [series.rule_id for series in result.series],
            ["oldest_available", "specific_horizon:2", "latest_available"],
        )
        january_rows = [
            self.rows_by_month(series.rows)[date(2026, 1, 1)]
            for series in result.series
        ]
        self.assertEqual([row.eligible_parents for row in january_rows], [2, 2, 2])
        self.assertEqual(
            [row.actual_denominator_kl for row in january_rows],
            [125.0, 125.0, 125.0],
        )
        self.assertEqual(
            [row.absolute_error_numerator_kl for row in january_rows],
            [20.0, 15.0, 35.0],
        )

    def test_series_share_common_denominator_and_worked_fa_values(self) -> None:
        result = build_common_vintage_accuracy(
            self.frame(),
            "tm",
            comparison_rules=(
                VintageRule.oldest_available(),
                VintageRule.specific_horizon(2),
            ),
        )
        expected = {
            "oldest_available": (60.0, 80.0),
            "specific_horizon:2": (30.0, 90.0),
            "latest_available": (40.0, 100.0 * (1.0 - 40.0 / 300.0)),
        }

        for series in result.series:
            row = self.rows_by_month(series.rows)[date(2026, 2, 1)]
            expected_numerator, expected_fa = expected[series.rule_id]
            self.assertEqual(row.eligible_parents, 2)
            self.assertEqual(row.actual_denominator_kl, 300.0)
            self.assertEqual(row.absolute_error_numerator_kl, expected_numerator)
            self.assertIsNotNone(row.forecast_accuracy_pct)
            self.assertAlmostEqual(row.forecast_accuracy_pct or 0.0, expected_fa)

        overview = result.overview
        self.assertEqual(overview.primary_rule_id, "oldest_available")
        self.assertEqual(overview.primary_label, "Oldest (5 months ahead)")
        self.assertEqual(overview.eligible_observations, 4)
        self.assertEqual(overview.accuracy_numerator_kl, 80.0)
        self.assertEqual(overview.accuracy_denominator_actual_kl, 425.0)
        self.assertEqual(overview.bias_numerator_kl, -80.0)
        self.assertAlmostEqual(
            overview.forecast_accuracy_pct or 0.0,
            100.0 * (1.0 - 80.0 / 425.0),
        )
        self.assertAlmostEqual(overview.wape_pct or 0.0, 100.0 * 80.0 / 425.0)
        self.assertAlmostEqual(overview.bias_pct or 0.0, -100.0 * 80.0 / 425.0)
        self.assertAlmostEqual(
            overview.accuracy_delta_pp or 0.0,
            100.0 * (80.0 - 75.0) / 425.0,
        )
        self.assertAlmostEqual(overview.revision_effectiveness_pct or 0.0, 25.0)
        self.assertEqual(overview.effectiveness_numerator, 1)
        self.assertEqual(overview.effectiveness_denominator, 4)
        self.assertEqual(overview.primary_error_kl, 80.0)
        self.assertEqual(overview.latest_error_kl, 75.0)
        self.assertEqual(
            [
                (
                    row.parent_code,
                    row.target_month,
                    row.forecast_kl,
                    row.actual_kl,
                    row.absolute_error_kl,
                    row.direction,
                )
                for row in result.wape_examples
            ],
            [
                (201, date(2026, 2, 1), 150.0, 200.0, 50.0, "under"),
                (101, date(2026, 1, 1), 80.0, 100.0, 20.0, "under"),
                (202, date(2026, 2, 1), 90.0, 100.0, 10.0, "under"),
                (103, date(2026, 1, 1), 25.0, 25.0, 0.0, "match"),
            ],
        )
        self.assertTrue(
            all(
                row.parent_description == f"Parent {row.parent_code}"
                for row in result.wape_examples
            )
        )
        primary_rows = self.rows_by_month(result.series[0].rows)
        january = primary_rows[date(2026, 1, 1)]
        february = primary_rows[date(2026, 2, 1)]
        self.assertEqual(january.forecast_kl, 105.0)
        self.assertEqual(february.forecast_kl, 240.0)
        self.assertEqual(january.revision_effectiveness_pct, 0.0)
        self.assertEqual(january.effectiveness_numerator, 0)
        self.assertEqual(january.effectiveness_denominator, 2)
        self.assertEqual(january.latest_absolute_error_numerator_kl, 35.0)
        self.assertEqual(february.revision_effectiveness_pct, 50.0)
        self.assertEqual(february.effectiveness_numerator, 1)
        self.assertEqual(february.effectiveness_denominator, 2)
        self.assertEqual(february.latest_absolute_error_numerator_kl, 40.0)

    def test_single_selected_vintage_becomes_overview_primary(self) -> None:
        result = build_common_vintage_accuracy(
            self.frame(),
            "tm",
            comparison_rules=(VintageRule.specific_horizon(2),),
        )

        self.assertEqual(result.overview.primary_rule_id, "specific_horizon:2")
        self.assertEqual(result.overview.primary_label, "2 months ahead")
        self.assertEqual(result.overview.accuracy_numerator_kl, 45.0)
        self.assertAlmostEqual(
            result.overview.forecast_accuracy_pct or 0.0,
            100.0 * (1.0 - 45.0 / 425.0),
        )

    def test_monthly_gap_drivers_reconcile_wape_by_parent_and_brand(self) -> None:
        result = build_vintage_gap_drilldown(
            self.frame(),
            "tm",
            comparison_rules=(
                VintageRule.oldest_available(),
                VintageRule.specific_horizon(2),
            ),
            target_month=date(2026, 2, 1),
        )

        self.assertEqual(result.baseline_rule_id, "oldest_available")
        self.assertEqual(result.latest_rule_id, "latest_available")
        self.assertEqual(result.eligible_parents, 2)
        self.assertEqual(result.actual_denominator_kl, 300.0)
        self.assertEqual(result.baseline_absolute_error_kl, 60.0)
        self.assertEqual(result.latest_absolute_error_kl, 40.0)
        self.assertAlmostEqual(result.baseline_wape_pct or 0.0, 20.0)
        self.assertAlmostEqual(result.latest_wape_pct or 0.0, 100.0 * 40.0 / 300.0)
        self.assertAlmostEqual(result.net_wape_improvement_pp or 0.0, 100.0 * 20.0 / 300.0)
        self.assertEqual(result.gross_fix_kl, 40.0)
        self.assertEqual(result.regression_kl, 20.0)
        self.assertAlmostEqual(
            sum(row.wape_contribution_pp for row in result.parents),
            result.net_wape_improvement_pp or 0.0,
        )
        self.assertAlmostEqual(
            sum(row.wape_contribution_pp for row in result.brands),
            result.net_wape_improvement_pp or 0.0,
        )
        self.assertEqual(
            [
                (
                    row.parent_code,
                    row.brand,
                    row.error_change_kl,
                    row.baseline_direction,
                    row.latest_direction,
                )
                for row in result.parents
            ],
            [
                (201, "Brand A", 40.0, "under", "over"),
                (202, "Brand B", -20.0, "under", "under"),
            ],
        )
        self.assertEqual(
            [(row.brand, row.parent_count, row.error_change_kl) for row in result.brands],
            [("Brand A", 1, 40.0), ("Brand B", 1, -20.0)],
        )

    def test_monthly_gap_drivers_require_a_historical_vintage(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "at least one historical accuracy vintage is required",
        ):
            build_vintage_gap_drilldown(
                self.frame(),
                "tm",
                comparison_rules=(),
                target_month=date(2026, 1, 1),
            )

    def test_latest_only_and_duplicate_rule_contract(self) -> None:
        frame = self.frame()
        default_result = build_common_vintage_accuracy(frame, "tm")
        self.assertEqual(
            [series.rule_id for series in default_result.series],
            ["oldest_available", "latest_available"],
        )
        self.assertEqual(
            [
                (series.label, series.fixed, series.selected_by_default)
                for series in default_result.series
            ],
            [
                ("Oldest (5 months ahead)", False, True),
                ("Latest (1 month ahead)", True, False),
            ],
        )

        default_january = self.rows_by_month(default_result.series[0].rows)[
            date(2026, 1, 1)
        ]
        self.assertEqual(default_january.eligible_parents, 2)
        self.assertEqual(default_january.actual_denominator_kl, 125.0)

        latest_only = build_common_vintage_accuracy(
            frame,
            "tm",
            comparison_rules=(),
        )
        self.assertEqual(
            [series.rule_id for series in latest_only.series],
            ["latest_available"],
        )
        january = self.rows_by_month(latest_only.series[0].rows)[date(2026, 1, 1)]
        self.assertEqual(january.eligible_parents, 3)
        self.assertEqual(january.actual_denominator_kl, 175.0)
        self.assertEqual(january.absolute_error_numerator_kl, 40.0)
        self.assertIsNotNone(january.forecast_accuracy_pct)
        self.assertAlmostEqual(
            january.forecast_accuracy_pct or 0.0,
            100.0 * (1.0 - 40.0 / 175.0),
        )
        self.assertEqual(latest_only.overview.primary_rule_id, "latest_available")
        self.assertEqual(latest_only.overview.primary_label, "Latest (1 month ahead)")
        self.assertEqual(latest_only.overview.eligible_observations, 5)
        self.assertEqual(latest_only.overview.accuracy_numerator_kl, 80.0)
        self.assertEqual(latest_only.overview.accuracy_denominator_actual_kl, 475.0)
        self.assertEqual(latest_only.overview.effectiveness_numerator, 0)
        self.assertEqual(latest_only.overview.effectiveness_denominator, 0)
        self.assertIsNone(latest_only.overview.revision_effectiveness_pct)
        self.assertEqual(latest_only.overview.primary_error_kl, 80.0)
        self.assertEqual(latest_only.overview.latest_error_kl, 80.0)

        duplicate = VintageRule.oldest_available()
        with self.assertRaisesRegex(
            ValueError,
            "^duplicate vintage rule: oldest_available$",
        ):
            build_common_vintage_accuracy(
                frame,
                "tm",
                comparison_rules=(duplicate, duplicate),
            )

        with self.assertRaisesRegex(
            ValueError,
            "^duplicate vintage rule: latest_available$",
        ):
            build_common_vintage_accuracy(
                frame,
                "tm",
                comparison_rules=(VintageRule.latest_available(),),
            )


if __name__ == "__main__":
    unittest.main()
