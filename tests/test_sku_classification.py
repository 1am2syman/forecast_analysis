from __future__ import annotations

import unittest
from datetime import date

import polars as pl

from forecast_analysis.sku_classification import (  # pyright: ignore[reportMissingImports]
    SKU_CLASS_UNCLASSIFIED,
    attach_sku_classification,
    build_sku_classifications,
    required_sku_class_actual_months,
)


class SkuClassificationTests(unittest.TestCase):
    @staticmethod
    def actual_history(*, include_target_month: bool = False) -> pl.DataFrame:
        rows: list[dict[str, object]] = []
        monthly_volume = {
            100: 10.0,
            200: 10.0 / 6.0,
            300: 10.0 / 6.0,
            400: 10.0 / 6.0,
            500: 10.0 / 6.0,
        }
        for month in range(1, 7):
            for parent_code, actual_kl in monthly_volume.items():
                rows.append(
                    {
                        "parent_code": parent_code,
                        "snop_month": date(2025, month, 1),
                        "actual_kl": actual_kl,
                    }
                )
        if include_target_month:
            rows.append(
                {
                    "parent_code": 500,
                    "snop_month": date(2025, 7, 1),
                    "actual_kl": 1_000.0,
                }
            )
        return pl.DataFrame(rows).with_columns(
            pl.col("parent_code").cast(pl.Int64),
            pl.col("snop_month").cast(pl.Date),
            pl.col("actual_kl").cast(pl.Float64),
        )

    def test_uses_preceding_six_completed_months_and_70_20_10_crossing_policy(self) -> None:
        result = build_sku_classifications(
            self.actual_history(include_target_month=True),
            [date(2025, 7, 1)],
        )

        classes = dict(
            result.select(["parent_code", "sku_class"]).iter_rows()
        )
        self.assertEqual(
            classes,
            {100: "A", 200: "A", 300: "B", 400: "B", 500: "C"},
        )
        self.assertEqual(result["sku_class_as_of_month"].unique().to_list(), [date(2025, 6, 1)])
        self.assertEqual(result["sku_class_window_start"].unique().to_list(), [date(2025, 1, 1)])
        self.assertAlmostEqual(
            result.filter(pl.col("parent_code") == 500)["sku_class_actual_6m_kl"].item(),
            10.0,
        )
        summary = (
            result.group_by("sku_class")
            .agg(pl.col("sku_class_actual_6m_kl").sum())
            .sort("sku_class")
        )
        self.assertEqual(summary["sku_class"].to_list(), ["A", "B", "C"])
        self.assertAlmostEqual(float(summary["sku_class_actual_6m_kl"].sum()), 100.0)

    def test_equal_volume_ties_break_by_parent_code(self) -> None:
        result = build_sku_classifications(
            self.actual_history(),
            [date(2025, 7, 1)],
        )

        self.assertEqual(
            result.filter(pl.col("parent_code").is_in([200, 300]))
            .sort("parent_code")["sku_class"]
            .to_list(),
            ["A", "B"],
        )

    def test_future_targets_carry_forward_latest_complete_actual_snapshot(self) -> None:
        result = build_sku_classifications(
            self.actual_history(),
            [date(2025, 7, 1), date(2025, 9, 1)],
        )

        july = result.filter(pl.col("snop_month") == date(2025, 7, 1)).sort("parent_code")
        september = result.filter(pl.col("snop_month") == date(2025, 9, 1)).sort("parent_code")
        self.assertEqual(july["sku_class"].to_list(), september["sku_class"].to_list())
        self.assertEqual(september["sku_class_as_of_month"].unique().to_list(), [date(2025, 6, 1)])
        self.assertTrue(september["sku_class_is_carried_forward"].all())
        self.assertFalse(july["sku_class_is_carried_forward"].any())

    def test_required_history_includes_six_months_before_earliest_target(self) -> None:
        self.assertEqual(
            required_sku_class_actual_months(
                [date(2025, 5, 1), date(2025, 7, 1)]
            ),
            (
                date(2024, 11, 1),
                date(2024, 12, 1),
                date(2025, 1, 1),
                date(2025, 2, 1),
                date(2025, 3, 1),
                date(2025, 4, 1),
                date(2025, 5, 1),
                date(2025, 6, 1),
                date(2025, 7, 1),
            ),
        )

    def test_incomplete_six_month_window_is_not_classified(self) -> None:
        incomplete = self.actual_history().filter(
            pl.col("snop_month") != date(2025, 3, 1)
        )

        result = build_sku_classifications(incomplete, [date(2025, 7, 1)])

        self.assertEqual(result.height, 0)

    def test_attach_marks_products_without_positive_history_unclassified(self) -> None:
        classifications = build_sku_classifications(
            self.actual_history(),
            [date(2025, 7, 1)],
        )
        population = pl.DataFrame(
            {
                "parent_code": [100, 999],
                "snop_month": [date(2025, 7, 1), date(2025, 7, 1)],
                "value": [1, 2],
            }
        ).with_columns(pl.col("parent_code").cast(pl.Int64))

        attached = attach_sku_classification(population, classifications).sort("parent_code")

        self.assertEqual(attached["sku_class"].to_list(), ["A", SKU_CLASS_UNCLASSIFIED])
        self.assertIsNone(attached["sku_class_actual_6m_kl"].to_list()[1])


if __name__ == "__main__":
    unittest.main()
