from __future__ import annotations

import csv
import io
import unittest

from dashboard.adapter import (  # pyright: ignore[reportMissingImports]
    DashboardDataService,
    DashboardRequestError,
)


class StaticDashboardAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = DashboardDataService.from_paths(cache_size=8)
        cls.bootstrap = cls.service.bootstrap()
        cls.defaults = cls.bootstrap["defaults"]

    def test_bootstrap_exposes_real_canonical_contract(self) -> None:
        payload = self.bootstrap

        self.assertFalse(payload["meta"]["synthetic"])
        self.assertEqual(payload["meta"]["dataset_rows"], 16_035)
        self.assertEqual(payload["meta"]["actual_population_rows"], 1_679)
        self.assertEqual(payload["request"], self.defaults)
        self.assertGreater(len(payload["options"]["brands"]), 40)
        self.assertGreater(len(payload["options"]["parent_products"]), 100)
        self.assertEqual(payload["options"]["horizons"], [4, 3, 2, 1, 0])

        summary = payload["population_summary"]
        self.assertEqual(summary["products"], 141)
        self.assertEqual(summary["forecast_rows"], 8_515)
        self.assertEqual(summary["selected_pair_rows"], 2_260)
        self.assertEqual(summary["eligible_observations"], 1_203)
        self.assertAlmostEqual(summary["actual_volume_kl"], 31_930.357108, places=5)

        metrics = payload["metrics"]
        self.assertAlmostEqual(metrics["forecast_accuracy_pct"], 73.8876144, places=5)
        self.assertAlmostEqual(metrics["bias_pct"], 20.5252437, places=5)
        self.assertAlmostEqual(metrics["absolute_error_kl"], 8_276.5639689, places=5)
        self.assertAlmostEqual(metrics["coverage_pct"], 99.2658236, places=5)
        self.assertAlmostEqual(metrics["accuracy_delta_pp"], -1.5982972, places=5)
        self.assertAlmostEqual(
            metrics["revision_effectiveness_pct"], 49.0588235, places=5
        )

        self.assertGreater(payload["monthly_performance"]["total"], 0)
        self.assertGreater(payload["horizon_performance"]["total"], 0)
        self.assertGreater(payload["revision_scatter"]["total"], 0)
        self.assertEqual(set(payload["quality"]["categories"]), {
            "hierarchy",
            "actual",
            "pairs",
            "source_availability",
        })

    def test_specific_filters_recompute_every_projection(self) -> None:
        request = dict(self.defaults)
        request.update(
            {
                "parent_code": 703584,
                "horizon": 4,
                "minimum_actual_volume": 3.3,
                "vintage_a": {"kind": "specific_horizon", "value": 4},
                "vintage_b": {"kind": "specific_horizon", "value": 4},
                "hierarchy_status": "mapped",
                "actual_status": "matched_positive",
                "pair_status": "complete",
                "forecast_direction": "under",
                "revision_direction": "unchanged",
                "revision_outcome": "neutral",
                "minimum_absolute_error_kl": 1.0,
            }
        )

        payload = self.service.view(request)

        self.assertFalse(payload["state"]["empty"])
        self.assertEqual(payload["population_summary"]["products"], 1)
        self.assertEqual(payload["population_summary"]["forecast_rows"], 1)
        self.assertEqual(payload["population_summary"]["eligible_observations"], 1)
        self.assertEqual(payload["exceptions"]["total"], 1)
        row = payload["exceptions"]["rows"][0]
        self.assertEqual(row["parent_code"], 703584)
        self.assertEqual(row["vintage_a_horizon_months"], 4)
        self.assertEqual(row["vintage_b_horizon_months"], 4)
        self.assertEqual(row["revision_direction"], "unchanged")
        self.assertEqual(row["revision_outcome"], "neutral")
        self.assertLess(row["bias_b_kl"], 0)
        self.assertGreaterEqual(row["absolute_error_b_kl"], 1.0)
        self.assertEqual(payload["product_detail"]["parent_code"], 703584)

    def test_source_comparison_uses_exact_common_population(self) -> None:
        request = dict(self.defaults)
        request.update({"comparison_mode": True, "horizon": 1})

        payload = self.service.view(request)
        comparison = payload["comparison"]

        self.assertTrue(comparison["ready"])
        self.assertFalse(comparison["blocked"])
        self.assertEqual(comparison["selected_horizon"], 1)
        self.assertEqual(comparison["comparable_pairs"], 1_275)
        self.assertAlmostEqual(
            comparison["tm_metrics"]["forecast_accuracy_pct"],
            77.0019168,
            places=5,
        )
        self.assertAlmostEqual(
            comparison["ml_metrics"]["forecast_accuracy_pct"],
            81.2654955,
            places=5,
        )
        self.assertEqual(payload["request"]["revision_direction"], None)
        self.assertEqual(payload["request"]["revision_outcome"], None)

    def test_product_selection_preserves_requested_parent(self) -> None:
        requested_parent = self.bootstrap["options"]["parent_products"][-1][
            "parent_code"
        ]
        request = dict(self.defaults)
        request["product_parent_code"] = requested_parent

        detail = self.service.product_detail(request)

        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail["parent_code"], requested_parent)
        self.assertEqual(detail["target_month"], detail["target_options"][-1])
        self.assertGreater(detail["points"]["total"], 0)
        self.assertGreater(detail["stability"]["total"], 0)

    def test_csv_export_matches_the_exact_active_request(self) -> None:
        request = dict(self.defaults)
        request.update(
            {
                "parent_code": 703584,
                "horizon": 4,
                "vintage_a": {"kind": "specific_horizon", "value": 4},
                "vintage_b": {"kind": "specific_horizon", "value": 4},
            }
        )
        payload = self.service.view(request)

        filename, csv_text = self.service.export_csv(request, kind="vintages")
        rows = list(csv.DictReader(io.StringIO(csv_text)))

        self.assertEqual(filename, "forecast_tm_filtered_vintages.csv")
        self.assertEqual(len(rows), payload["exceptions"]["total"])
        self.assertTrue(rows)
        self.assertTrue(all(row["parent_code"] == "703584" for row in rows))
        self.assertIn("vintage_b_forecast_kl", rows[0])
        self.assertIn("revision_outcome", rows[0])

    def test_invalid_requests_fail_with_field_specific_errors(self) -> None:
        with self.assertRaisesRegex(DashboardRequestError, "source must be one of"):
            self.service.view({"source": "other"})
        with self.assertRaisesRegex(DashboardRequestError, "target_start"):
            self.service.view(
                {"target_start": "2026-12-01", "target_end": "2025-05-01"}
            )
        with self.assertRaisesRegex(DashboardRequestError, "quality category"):
            self.service.export_csv(self.defaults, kind="quality", category="other")


if __name__ == "__main__":
    unittest.main()
