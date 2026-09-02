from __future__ import annotations

import unittest
from datetime import date

import polars as pl

from forecast_analysis import (
    VintageAccuracyRow,
    VintageRule,
    build_common_vintage_accuracy,
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
