from __future__ import annotations

import unittest
from datetime import date

import polars as pl

from forecast_analysis import build_product_postmortem
from forecast_analysis.vintages import select_vintage_pair


def _month_distance(calculation_month: date, target_month: date) -> int:
    return (target_month.year - calculation_month.year) * 12 + (
        target_month.month - calculation_month.month
    )


def _analysis_frame(
    rows: list[
        tuple[
            str,
            int,
            str,
            str | None,
            str,
            date,
            date,
            float,
            float | None,
        ]
    ],
) -> pl.DataFrame:
    records: list[dict[str, object]] = []
    for (
        source,
        parent_code,
        description,
        brand,
        sku_class,
        calculation_month,
        target_month,
        forecast_kl,
        actual_kl,
    ) in rows:
        records.append(
            {
                "source": source,
                "parent_code": parent_code,
                "parent_description": description,
                "hierarchy_description": description,
                "brand": brand,
                "mapping_status": "mapped" if brand is not None else "unmapped",
                "mapping_diagnostic": None if brand is not None else "no hierarchy mapping",
                "calculation_month": calculation_month,
                "snop_month": target_month,
                "forecast_horizon_months": _month_distance(
                    calculation_month, target_month
                ),
                "forecast_kl": forecast_kl,
                "actual_kl": actual_kl,
                "actual_status": (
                    "missing"
                    if actual_kl is None
                    else "matched_zero"
                    if actual_kl == 0
                    else "matched_positive"
                ),
                "sku_class": sku_class,
            }
        )
    return pl.DataFrame(records).with_columns(
        pl.col("source").cast(pl.String),
        pl.col("parent_code").cast(pl.Int64),
        pl.col("calculation_month").cast(pl.Date),
        pl.col("snop_month").cast(pl.Date),
        pl.col("forecast_horizon_months").cast(pl.Int64),
        pl.col("forecast_kl").cast(pl.Float64),
        pl.col("actual_kl").cast(pl.Float64),
    )


def _pairs(frame: pl.DataFrame, source: str = "tm") -> pl.DataFrame:
    return select_vintage_pair(frame, source)


class ProductPostmortemTests(unittest.TestCase):
    def test_builds_latest_monthly_performance_revision_points_and_target_summary(self) -> None:
        january = date(2026, 1, 1)
        february = date(2026, 2, 1)
        frame = _analysis_frame(
            [
                ("tm", 100, "Selected", "Alpha", "A", date(2025, 11, 1), january, 80.0, 100.0),
                ("tm", 100, "Selected", "Alpha", "A", date(2025, 12, 1), january, 95.0, 100.0),
                ("tm", 100, "Selected", "Alpha", "A", date(2025, 12, 1), february, 100.0, 100.0),
                ("tm", 100, "Selected", "Alpha", "A", date(2026, 1, 1), february, 110.0, 100.0),
            ]
        )

        result = build_product_postmortem(
            frame,
            _pairs(frame),
            100,
            february,
            source="tm",
            rolling_months=2,
        )

        self.assertEqual(result.status, "ready")
        self.assertEqual(
            result.rolling_performance.select(
                ["snop_month", "calculation_month", "forecast_kl"]
            ).rows(),
            [
                (january, date(2025, 12, 1), 95.0),
                (february, date(2026, 1, 1), 110.0),
            ],
        )
        self.assertEqual(
            result.revision_outcomes.select(
                ["snop_month", "error_improvement_kl", "revision_outcome"]
            ).rows(),
            [(january, 15.0, "improved"), (february, -10.0, "worsened")],
        )
        self.assertEqual(result.summary.latest_forecast_kl, 110.0)
        self.assertEqual(result.summary.actual_kl, 100.0)
        self.assertEqual(result.summary.absolute_error_kl, 10.0)
        self.assertEqual(result.summary.bias_kl, 10.0)
        self.assertEqual(result.summary.bias_pct, 10.0)
        self.assertEqual(result.summary.forecast_accuracy_pct, 90.0)
        self.assertEqual(result.summary.first_to_latest_fva_kl, -10.0)
        self.assertEqual(result.summary.revision_efficiency_pct, -100.0)
        self.assertEqual(result.summary.material_revision_hits, 0)
        self.assertEqual(result.summary.material_revisions, 1)
        self.assertEqual(result.summary.material_hit_rate_pct, 0.0)

    def test_low_positive_actual_keeps_signed_ratio_metrics_without_clamping(self) -> None:
        target = date(2026, 1, 1)
        frame = _analysis_frame(
            [
                ("tm", 100, "Low volume", "Alpha", "C", date(2025, 12, 1), target, 0.3, 0.1),
            ]
        )

        result = build_product_postmortem(frame, _pairs(frame), 100, target)

        self.assertAlmostEqual(result.summary.absolute_error_kl or 0.0, 0.2)
        self.assertAlmostEqual(result.summary.bias_pct or 0.0, 200.0)
        self.assertAlmostEqual(result.summary.forecast_accuracy_pct or 0.0, -100.0)

    def test_zero_actual_keeps_absolute_error_but_ratio_metrics_are_undefined(self) -> None:
        target = date(2026, 1, 1)
        frame = _analysis_frame(
            [
                ("tm", 100, "Zero actual", "Alpha", "C", date(2025, 11, 1), target, 0.0, 0.0),
                ("tm", 100, "Zero actual", "Alpha", "C", date(2025, 12, 1), target, 5.0, 0.0),
                ("tm", 200, "Positive peer", "Alpha", "C", date(2025, 12, 1), target, 9.0, 10.0),
            ]
        )

        result = build_product_postmortem(frame, _pairs(frame), 100, target)

        self.assertEqual(result.summary.absolute_error_kl, 5.0)
        self.assertEqual(result.summary.bias_kl, 5.0)
        self.assertIsNone(result.summary.bias_pct)
        self.assertIsNone(result.summary.forecast_accuracy_pct)
        self.assertIsNone(result.summary.first_to_latest_fva_kl)
        self.assertIsNone(result.summary.revision_efficiency_pct)
        self.assertFalse(result.peer_benchmarks["selected_eligible"].any())
        self.assertTrue(
            all(value is None for value in result.peer_benchmarks["selected_rank"])
        )

    def test_insufficient_target_history_is_explicit_and_does_not_invent_revision_metrics(self) -> None:
        target = date(2026, 1, 1)
        frame = _analysis_frame(
            [
                ("tm", 100, "One vintage", "Alpha", "B", date(2025, 12, 1), target, 90.0, 100.0),
            ]
        )

        result = build_product_postmortem(frame, _pairs(frame), 100, target)

        self.assertEqual(result.status, "insufficient_history")
        self.assertEqual(result.summary.vintage_count, 1)
        self.assertIsNone(result.summary.first_to_latest_fva_kl)
        self.assertIsNone(result.summary.revision_efficiency_pct)
        self.assertIsNone(result.summary.material_hit_rate_pct)
        self.assertEqual(result.treatment.action, "hold")
        self.assertTrue(
            any(row["category"] == "history" for row in result.commentary.to_dicts())
        )

    def test_negative_revision_efficiency_recommends_a_guarded_rebase_to_better_history(self) -> None:
        target = date(2026, 1, 1)
        frame = _analysis_frame(
            [
                ("tm", 100, "Selected", "Alpha", "A", date(2025, 11, 1), target, 100.0, 100.0),
                ("tm", 100, "Selected", "Alpha", "A", date(2025, 12, 1), target, 80.0, 100.0),
            ]
        )

        result = build_product_postmortem(frame, _pairs(frame), 100, target)

        self.assertEqual(result.summary.first_to_latest_fva_kl, -20.0)
        self.assertEqual(result.summary.revision_efficiency_pct, -100.0)
        self.assertEqual(result.treatment.action, "rebase")
        self.assertEqual(result.treatment.impact_kl, 20.0)
        self.assertIn("forecast history", result.treatment.rationale.lower())
        self.assertNotIn("promotion", result.treatment.rationale.lower())

    def test_peer_benchmarks_use_eligible_brand_and_sku_class_cohorts(self) -> None:
        target = date(2026, 1, 1)
        frame = _analysis_frame(
            [
                ("tm", 100, "Selected", "Alpha", "A", date(2025, 12, 1), target, 90.0, 100.0),
                ("tm", 200, "Brand peer", "Alpha", "A", date(2025, 12, 1), target, 80.0, 100.0),
                ("tm", 300, "Class peer", "Beta", "A", date(2025, 12, 1), target, 95.0, 100.0),
                ("tm", 400, "Zero peer", "Alpha", "B", date(2025, 12, 1), target, 0.0, 0.0),
            ]
        )

        result = build_product_postmortem(frame, _pairs(frame), 100, target)
        peers = {row["cohort_type"]: row for row in result.peer_benchmarks.to_dicts()}

        brand = peers["brand"]
        self.assertEqual(brand["cohort_value"], "Alpha")
        self.assertEqual(brand["cohort_size"], 2)
        self.assertEqual(brand["selected_rank"], 1)
        self.assertEqual(brand["selected_percentile_pct"], 100.0)
        self.assertEqual(brand["median_accuracy_pct"], 85.0)

        sku_class = peers["sku_class"]
        self.assertEqual(sku_class["cohort_value"], "A")
        self.assertEqual(sku_class["cohort_size"], 3)
        self.assertEqual(sku_class["selected_rank"], 2)
        self.assertAlmostEqual(sku_class["selected_percentile_pct"], 200 / 3)
        self.assertEqual(sku_class["median_accuracy_pct"], 90.0)

        brand_class = peers["brand_sku_class"]
        self.assertEqual(brand_class["cohort_value"], "Alpha · A")
        self.assertEqual(brand_class["cohort_size"], 2)
        self.assertEqual(brand_class["median_accuracy_pct"], 85.0)

    def test_rolling_limit_and_tolerance_apply_to_sparkline_and_target_revision_metrics(self) -> None:
        january = date(2026, 1, 1)
        february = date(2026, 2, 1)
        frame = _analysis_frame(
            [
                ("tm", 100, "Selected", "Alpha", "A", date(2025, 11, 1), january, 100.0, 100.0),
                ("tm", 100, "Selected", "Alpha", "A", date(2025, 12, 1), january, 100.5, 100.0),
                ("tm", 100, "Selected", "Alpha", "A", date(2025, 12, 1), february, 100.0, 100.0),
                ("tm", 100, "Selected", "Alpha", "A", date(2026, 1, 1), february, 100.5, 100.0),
            ]
        )

        result = build_product_postmortem(
            frame,
            _pairs(frame),
            100,
            february,
            rolling_months=1,
            revision_tolerance_kl=1.0,
        )

        self.assertEqual(result.rolling_performance.height, 1)
        self.assertEqual(result.revision_outcomes.height, 1)
        self.assertEqual(result.revision_outcomes["revision_direction"].item(), "unchanged")
        self.assertEqual(result.revision_outcomes["revision_outcome"].item(), "neutral")
        self.assertEqual(result.summary.material_revisions, 0)
        self.assertIsNone(result.summary.revision_efficiency_pct)
        self.assertEqual(result.treatment.action, "hold")

    def test_commentary_and_treatment_are_deterministic_and_never_claim_external_causes(self) -> None:
        target = date(2026, 1, 1)
        frame = _analysis_frame(
            [
                ("tm", 100, "Selected", "Alpha", "A", date(2025, 11, 1), target, 100.0, 100.0),
                ("tm", 100, "Selected", "Alpha", "A", date(2025, 12, 1), target, 80.0, 100.0),
            ]
        )
        pairs = _pairs(frame)

        first = build_product_postmortem(frame, pairs, 100, target)
        second = build_product_postmortem(frame, pairs, 100, target)

        self.assertEqual(first.commentary.to_dicts(), second.commentary.to_dicts())
        self.assertEqual(first.treatment, second.treatment)
        self.assertIn(
            first.treatment.action,
            {"hold", "rebase", "rephase", "scenario", "escalate"},
        )
        evidence_gaps = first.commentary.filter(pl.col("category") == "evidence_gap")
        self.assertEqual(evidence_gaps.height, 1)
        gap = evidence_gaps.row(0, named=True)
        self.assertEqual(gap["severity"], "warning")
        self.assertEqual(gap["confidence"], "high")
        self.assertEqual(
            gap["evidence_refs"],
            [
                "missing:promotion",
                "missing:availability",
                "missing:price",
                "missing:distribution",
            ],
        )
        text = " ".join(
            str(value).lower()
            for row in first.commentary.to_dicts()
            for value in (row["headline"], row["body"])
        )
        for invented_claim in (
            "promotion caused",
            "stockout caused",
            "price caused",
            "distribution caused",
            "due to promotion",
            "driven by stockout",
        ):
            self.assertNotIn(invented_claim, text)


if __name__ == "__main__":
    unittest.main()
