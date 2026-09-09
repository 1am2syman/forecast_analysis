from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
import csv
import io
import json
from threading import Barrier
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

        self.assertEqual(payload["contract"]["name"], "dashboard-view")
        self.assertEqual(payload["contract"]["kind"], "bootstrap")
        self.assertEqual(payload["contract"]["module_merge"], "shallow-root")
        self.assertFalse(payload["meta"]["synthetic"])
        self.assertEqual(payload["meta"]["dataset_rows"], 16_035)
        self.assertEqual(payload["meta"]["actual_population_rows"], 2_269)
        self.assertEqual(payload["request"], self.defaults)
        self.assertEqual(payload["request"]["source"], "ml")
        self.assertGreaterEqual(len(payload["options"]["brands"]), 40)
        self.assertGreater(len(payload["options"]["parent_products"]), 100)
        self.assertEqual(payload["options"]["horizons"], [5, 4, 3, 2, 1])
        self.assertEqual(
            payload["options"]["sku_classes"],
            ["A", "B", "C", "Unclassified"],
        )
        self.assertEqual(payload["request"]["brands"], [])
        self.assertEqual(payload["request"]["sku_classes"], [])
        self.assertEqual(payload["request"]["parent_codes"], [])
        self.assertNotIn("brand", payload["request"])
        self.assertNotIn("sku_class", payload["request"])
        self.assertNotIn("parent_code", payload["request"])

        summary = payload["population_summary"]
        self.assertEqual(summary["products"], 101)
        self.assertEqual(summary["forecast_rows"], 6_629)
        self.assertEqual(summary["selected_pair_rows"], 1_563)
        self.assertEqual(summary["eligible_observations"], 1_543)
        self.assertAlmostEqual(summary["actual_volume_kl"], 42_185.737352, places=5)

        metrics = payload["metrics"]
        self.assertAlmostEqual(metrics["forecast_accuracy_pct"], 83.0358421, places=5)
        self.assertAlmostEqual(metrics["bias_pct"], -6.6476319, places=5)
        self.assertAlmostEqual(metrics["absolute_error_kl"], 7_116.6831867, places=5)
        self.assertAlmostEqual(metrics["coverage_pct"], 99.4005124, places=5)
        self.assertAlmostEqual(metrics["accuracy_delta_pp"], 4.2010248, places=5)
        self.assertAlmostEqual(
            metrics["revision_effectiveness_pct"], 57.2275760, places=5
        )

        self.assertGreater(payload["monthly_performance"]["total"], 0)
        forbidden = {
            "monthly_audit",
            "horizon_performance",
            "horizon_audit",
            "brand_target_month_performance",
            "revision_diagnostics",
            "revision_history",
            "revision_scatter",
            "revision_actions",
            "revision_drilldown",
            "exceptions",
            "comparison",
            "product_detail",
            "quality",
        }
        self.assertTrue(forbidden.isdisjoint(payload))
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.assertLess(len(encoded), 150 * 1024)

    def test_named_modules_are_coherent_slices_of_one_cached_view(self) -> None:
        full = self.service.view(self.defaults)
        expected_fields = {
            "trends": {
                "monthly_performance",
                "monthly_audit",
                "horizon_performance",
                "horizon_audit",
            },
            "heatmap": {"brand_target_month_performance"},
            "comparison": {"comparison"},
            "exceptions": {
                "metrics",
                "exceptions",
                "revision_diagnostics",
                "revision_history",
                "revision_scatter",
                "revision_actions",
                "revision_drilldown",
            },
            "quality": {"quality"},
        }

        for module_name, fields in expected_fields.items():
            response = self.service.module(module_name, self.defaults)
            self.assertEqual(response["module"], module_name)
            self.assertEqual(response["request"], self.defaults)
            self.assertEqual(
                response["meta"]["dataset_version"],
                self.bootstrap["meta"]["dataset_version"],
            )
            self.assertEqual(set(response["data"]), fields)
            for field in fields:
                self.assertEqual(response["data"][field], full[field])

    def test_concurrent_same_key_requests_return_one_coherent_view(self) -> None:
        request = dict(self.defaults)
        request["brands"] = [self.bootstrap["options"]["brands"][0]]
        barrier = Barrier(4)

        def call_view() -> dict[str, object]:
            barrier.wait()
            return self.service.view(request)

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: call_view(), range(4)))
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(results[0]["request"], request)

    def test_metrics_expose_wape_as_absolute_error_share_of_actuals(self) -> None:
        metrics = self.bootstrap["metrics"]

        self.assertAlmostEqual(
            metrics["wape_pct"],
            metrics["accuracy_numerator_kl"]
            / metrics["accuracy_denominator_actual_kl"]
            * 100,
        )

    def test_volume_distributions_summarize_aggregated_monthly_outcomes(self) -> None:
        distributions = self.bootstrap["volume_distributions"]
        actual = distributions["actual"]
        forecast = distributions["forecast"]

        self.assertEqual(actual["count"], 16)
        self.assertEqual(forecast["count"], actual["count"])
        self.assertAlmostEqual(actual["median"], 2_595.2895310, places=6)
        self.assertAlmostEqual(forecast["median"], 2_414.224535592, places=6)
        self.assertAlmostEqual(actual["whisker_high"], 3_275.015952, places=6)
        self.assertAlmostEqual(forecast["whisker_high"], 2_792.059525762, places=6)
        for distribution in distributions.values():
            self.assertLessEqual(distribution["whisker_low"], distribution["q1"])
            self.assertLessEqual(distribution["q1"], distribution["median"])
            self.assertLessEqual(distribution["median"], distribution["q3"])
            self.assertLessEqual(distribution["q3"], distribution["whisker_high"])

    def test_monthly_chart_flow_omits_periods_without_plottable_values(self) -> None:
        rows = self.bootstrap["monthly_performance"]["rows"]
        chart_value_fields = {
            "forecast_accuracy_pct",
            "vintage_a_accuracy_pct",
            "vintage_b_accuracy_pct",
            "bias_pct",
            "absolute_error_kl",
            "actual_kl",
            "forecast_kl",
            "vintage_a_forecast_kl",
            "vintage_b_forecast_kl",
            "coverage_pct",
        }

        self.assertTrue(rows)
        self.assertTrue(
            all(any(row[field] is not None for field in chart_value_fields) for row in rows)
        )
        self.assertEqual(rows[-1]["snop_month"], "2026-08-01")

    def test_accuracy_vintage_request_defaults_and_validation(self) -> None:
        option_ids = [
            option["id"] for option in self.bootstrap["accuracy_vintages"]["options"]
        ]

        self.assertEqual(self.defaults["accuracy_vintage_ids"], ["oldest_available"])
        self.assertEqual(
            option_ids,
            [
                "oldest_available",
                "specific_horizon:4",
                "specific_horizon:3",
                "specific_horizon:2",
            ],
        )
        self.assertNotIn(
            self.bootstrap["accuracy_vintages"]["latest"]["id"],
            option_ids,
        )

        request = dict(self.defaults)
        request["accuracy_vintage_ids"] = [
            "specific_horizon:2",
            "oldest_available",
            "specific_horizon:4",
        ]
        normalized = self.service.compact_view(request)["request"]
        self.assertEqual(
            normalized["accuracy_vintage_ids"],
            ["oldest_available", "specific_horizon:4", "specific_horizon:2"],
        )

        request["accuracy_vintage_ids"] = []
        latest_only = self.service.compact_view(request)
        self.assertEqual(latest_only["request"]["accuracy_vintage_ids"], [])
        self.assertFalse(
            any(
                option["selected"]
                for option in latest_only["accuracy_vintages"]["options"]
            )
        )
        self.assertTrue(latest_only["accuracy_vintages"]["latest"]["rows"])
        self.assertEqual(
            latest_only["accuracy_vintages"]["overview"]["primary"]["id"],
            "latest_available",
        )

        invalid_values = (
            "oldest_available",
            ["oldest_available", 4],
            ["oldest_available", "oldest_available"],
            ["latest_available"],
            ["specific_horizon:5"],
            ["unsupported"],
        )
        for invalid in invalid_values:
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(
                    DashboardRequestError,
                    "accuracy_vintage_ids",
                ):
                    self.service.compact_view({"accuracy_vintage_ids": invalid})

    def test_accuracy_vintages_use_common_cohort_without_changing_global_metrics(
        self,
    ) -> None:
        request = dict(self.defaults)
        request["accuracy_vintage_ids"] = [
            "specific_horizon:3",
            "oldest_available",
            "specific_horizon:4",
        ]
        payload = self.service.compact_view(request)
        vintages = payload["accuracy_vintages"]
        options = vintages["options"]
        selected = [option for option in options if option["selected"]]
        series = [*selected, vintages["latest"]]

        self.assertEqual(
            [option["id"] for option in selected],
            ["oldest_available", "specific_horizon:4", "specific_horizon:3"],
        )
        self.assertEqual(
            [option["id"] for option in options],
            [
                "oldest_available",
                "specific_horizon:4",
                "specific_horizon:3",
                "specific_horizon:2",
            ],
        )
        self.assertEqual(options[-1]["rows"], [])
        self.assertTrue(vintages["latest"]["fixed"])
        self.assertNotIn(
            vintages["latest"]["id"],
            payload["request"]["accuracy_vintage_ids"],
        )

        row_fields = {
            "snop_month",
            "forecast_accuracy_pct",
            "forecast_kl",
            "wape_pct",
            "bias_pct",
            "revision_effectiveness_pct",
            "effectiveness_numerator",
            "effectiveness_denominator",
            "eligible_parents",
            "actual_denominator_kl",
            "absolute_error_numerator_kl",
            "latest_absolute_error_numerator_kl",
        }
        rows_by_series = {
            item["id"]: {row["snop_month"]: row for row in item["rows"]}
            for item in series
        }
        self.assertTrue(all(rows for rows in rows_by_series.values()))
        self.assertEqual(
            {tuple(rows) for rows in rows_by_series.values()},
            {tuple(rows_by_series[series[0]["id"]])},
        )
        for target_month in rows_by_series[series[0]["id"]]:
            monthly_rows = [rows[target_month] for rows in rows_by_series.values()]
            self.assertTrue(all(set(row) == row_fields for row in monthly_rows))
            self.assertEqual(
                {row["eligible_parents"] for row in monthly_rows},
                {monthly_rows[0]["eligible_parents"]},
            )
            self.assertEqual(
                {row["actual_denominator_kl"] for row in monthly_rows},
                {monthly_rows[0]["actual_denominator_kl"]},
            )
            self.assertTrue(
                all(
                    row["wape_pct"] is None or row["wape_pct"] >= 0
                    for row in monthly_rows
                )
            )
            self.assertTrue(
                all(row["latest_absolute_error_numerator_kl"] >= 0 for row in monthly_rows)
            )

        overview = vintages["overview"]
        overview_metrics = overview["metrics"]
        self.assertEqual(overview["primary"]["id"], "oldest_available")
        self.assertEqual(overview["primary"]["label"], "Oldest (5 months ahead)")
        self.assertEqual(overview["cohort_months"], 12)
        examples = overview["wape_examples"]
        self.assertEqual(len(examples), 8)
        self.assertEqual(
            set(examples[0]),
            {
                "parent_code",
                "parent_description",
                "snop_month",
                "forecast_kl",
                "actual_kl",
                "absolute_error_kl",
                "direction",
            },
        )
        self.assertEqual(
            [row["absolute_error_kl"] for row in examples],
            sorted(
                [row["absolute_error_kl"] for row in examples],
                reverse=True,
            ),
        )
        self.assertTrue(
            all(row["direction"] in {"over", "under", "match"} for row in examples)
        )
        self.assertEqual(overview_metrics["eligible_observations"], 1_062)
        self.assertAlmostEqual(
            overview_metrics["forecast_accuracy_pct"], 78.21442194899741
        )
        self.assertAlmostEqual(overview_metrics["wape_pct"], 21.785578051002584)
        self.assertAlmostEqual(overview_metrics["bias_pct"], -9.716576963132724)
        self.assertAlmostEqual(
            overview_metrics["revision_effectiveness_pct"], 56.77290836653387
        )
        self.assertEqual(overview_metrics["effectiveness_numerator"], 570)
        self.assertEqual(overview_metrics["effectiveness_denominator"], 1_004)
        self.assertAlmostEqual(
            overview_metrics["primary_error_kl"], 6_953.23024261829
        )
        self.assertEqual(
            overview["volume_distributions"]["actual"]["count"],
            overview["cohort_months"],
        )
        self.assertEqual(
            overview["volume_distributions"]["forecast"]["count"],
            overview["cohort_months"],
        )

        self.assertEqual(payload["metrics"], self.bootstrap["metrics"])
        self.assertEqual(
            payload["monthly_performance"],
            self.bootstrap["monthly_performance"],
        )
        full_payload = self.service.view(request)
        baseline_full_payload = self.service.view(self.defaults)
        for field in (
            "population_summary",
            "revision_diagnostics",
            "revision_history",
            "revision_scatter",
            "revision_actions",
            "revision_drilldown",
            "exceptions",
            "quality",
        ):
            with self.subTest(unchanged_field=field):
                self.assertEqual(full_payload[field], baseline_full_payload[field])
        single_request = dict(self.defaults)
        single_request["accuracy_vintage_ids"] = ["specific_horizon:3"]
        single = self.service.compact_view(single_request)["accuracy_vintages"][
            "overview"
        ]
        self.assertEqual(single["primary"]["id"], "specific_horizon:3")

        default_oldest = self.bootstrap["accuracy_vintages"]["options"][0]["rows"]
        selected_oldest = selected[0]["rows"]
        self.assertTrue(
            any(
                default_row["eligible_parents"] != selected_row["eligible_parents"]
                for default_row, selected_row in zip(
                    default_oldest,
                    selected_oldest,
                    strict=True,
                )
            )
        )

    def test_vintage_gap_drilldown_reconciles_without_inflating_overview(self) -> None:
        self.assertNotIn("vintage_gap_drilldown", self.bootstrap)
        target_month = next(
            row["snop_month"]
            for row in self.bootstrap["accuracy_vintages"]["options"][0]["rows"]
            if row["eligible_parents"] > 0
        )
        request = {
            **self.defaults,
            "vintage_gap_target_month": target_month,
        }

        response = self.service.vintage_gap_drilldown(request)
        drilldown = response["drilldown"]
        summary = drilldown["summary"]

        self.assertEqual(response["contract"]["name"], "vintage-gap-drilldown")
        self.assertEqual(response["request"], self.defaults)
        self.assertEqual(drilldown["target_month"], target_month)
        self.assertEqual(drilldown["baseline"]["id"], "oldest_available")
        self.assertEqual(drilldown["latest"]["id"], "latest_available")
        self.assertEqual(summary["eligible_parents"], len(drilldown["parents"]))
        self.assertAlmostEqual(
            sum(row["wape_contribution_pp"] for row in drilldown["parents"]),
            summary["net_wape_improvement_pp"],
        )
        self.assertAlmostEqual(
            sum(row["wape_contribution_pp"] for row in drilldown["brands"]),
            summary["net_wape_improvement_pp"],
        )
        self.assertAlmostEqual(
            summary["gross_fix_kl"] - summary["regression_kl"],
            summary["baseline_absolute_error_kl"]
            - summary["latest_absolute_error_kl"],
        )
        self.assertTrue(
            any(row["error_change_kl"] > 0 for row in drilldown["parents"])
        )
        self.assertTrue(
            any(row["error_change_kl"] < 0 for row in drilldown["parents"])
        )
        self.assertEqual(
            {row["brand"] for row in drilldown["parents"]},
            {row["brand"] for row in drilldown["brands"]},
        )

    def test_vintage_gap_drilldown_validates_month_and_historical_selection(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            DashboardRequestError,
            "vintage_gap_target_month is required",
        ):
            self.service.vintage_gap_drilldown(self.defaults)

        request = {
            **self.defaults,
            "accuracy_vintage_ids": [],
            "vintage_gap_target_month": "2026-01-01",
        }
        with self.assertRaisesRegex(
            DashboardRequestError,
            "select at least one historical accuracy vintage",
        ):
            self.service.vintage_gap_drilldown(request)

        request["vintage_gap_target_month"] = "not-a-month"
        with self.assertRaisesRegex(
            DashboardRequestError,
            "vintage_gap_target_month must be an ISO date",
        ):
            self.service.vintage_gap_drilldown(request)

    def test_vintage_gap_uses_oldest_selected_rule_and_all_selected_cohort(
        self,
    ) -> None:
        target_month = next(
            row["snop_month"]
            for row in self.bootstrap["accuracy_vintages"]["options"][0]["rows"]
            if row["eligible_parents"] > 0
        )
        request = {
            **self.defaults,
            "accuracy_vintage_ids": [
                "specific_horizon:2",
                "specific_horizon:4",
            ],
            "vintage_gap_target_month": target_month,
        }
        response = self.service.vintage_gap_drilldown(request)

        self.assertEqual(
            response["request"]["accuracy_vintage_ids"],
            ["specific_horizon:4", "specific_horizon:2"],
        )
        self.assertEqual(
            response["drilldown"]["baseline"]["id"],
            "specific_horizon:4",
        )

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
                "target_end": self.bootstrap["options"]["target_months"][-1],
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

    def test_target_end_is_capped_to_filter_scoped_latest_actual_month(self) -> None:
        request = dict(self.defaults)
        request.update(
            {
                "parent_code": 726858,
                "target_end": self.bootstrap["options"]["target_months"][-1],
            }
        )

        payload = self.service.view(request)

        self.assertEqual(payload["request"]["target_end"], "2026-03-01")
        self.assertEqual(payload["options"]["target_months"][-1], "2026-03-01")
        self.assertTrue(payload["monthly_performance"]["rows"])
        self.assertTrue(
            all(
                row["snop_month"] <= payload["request"]["target_end"]
                for row in payload["monthly_performance"]["rows"]
            )
        )

    def test_running_actual_month_is_available_but_not_selected_by_default(
        self,
    ) -> None:
        service = DashboardDataService(
            self.service.dataset,
            refresh_timestamp=self.service.refresh_timestamp,
            source_label=self.service.source_label,
            cache_size=2,
            today=date(2026, 9, 15),
        )

        bootstrap = service.bootstrap()
        self.assertEqual(bootstrap["options"]["target_months"][-1], "2026-09-01")
        self.assertEqual(
            bootstrap["options"]["latest_completed_target_month"],
            "2026-08-01",
        )
        self.assertEqual(bootstrap["defaults"]["target_end"], "2026-08-01")
        self.assertEqual(bootstrap["request"]["target_end"], "2026-08-01")

        explicit = service.compact_view(
            {**bootstrap["defaults"], "target_end": "2026-09-01"}
        )
        self.assertEqual(explicit["request"]["target_end"], "2026-09-01")

    def test_product_multi_selects_filter_every_projection(self) -> None:
        parent_codes = [706090, 710085]
        request = dict(self.defaults)
        request.update(
            {
                "brands": [],
                "sku_classes": ["A", "B"],
                "parent_codes": parent_codes,
            }
        )

        payload = self.service.view(request)

        self.assertEqual(payload["request"]["sku_classes"], ["A", "B"])
        self.assertEqual(payload["request"]["parent_codes"], parent_codes)
        self.assertFalse(payload["state"]["empty"])
        self.assertEqual(payload["population_summary"]["products"], 2)
        self.assertTrue(payload["exceptions"]["rows"])
        self.assertTrue(
            all(row["parent_code"] in parent_codes for row in payload["exceptions"]["rows"])
        )
        class_a = self.service.view({**self.defaults, "sku_classes": ["A"]})
        classes_a_b = self.service.view(
            {**self.defaults, "sku_classes": ["A", "B"]}
        )
        self.assertGreaterEqual(
            classes_a_b["population_summary"]["products"],
            class_a["population_summary"]["products"],
        )
        self.assertLess(
            classes_a_b["population_summary"]["products"],
            self.bootstrap["population_summary"]["products"],
        )

    def test_product_facets_interconnect_brand_class_and_parent_options(self) -> None:
        class_a = self.service.compact_view(
            {**self.defaults, "sku_classes": ["A"]}
        )
        class_a_parents = {
            row["parent_code"] for row in class_a["options"]["parent_products"]
        }
        class_a_availability = class_a["options"]["product_availability"]

        self.assertIn(706059, class_a_parents)
        self.assertNotIn(703584, class_a_parents)
        self.assertIn("BBEL_LUP", class_a["options"]["brands"])
        self.assertNotIn("BBEL_LUP", class_a_availability["brands"])

        parent_scope = self.service.compact_view(
            {**self.defaults, "parent_codes": [706059]}
        )
        parent_availability = parent_scope["options"]["product_availability"]

        self.assertEqual(parent_availability["brands"], ["BPCNO-SP"])
        self.assertEqual(parent_availability["sku_classes"], ["A"])
        self.assertIn("BBEL_LUP", parent_scope["options"]["brands"])
        self.assertIn("B", parent_scope["options"]["sku_classes"])

    def test_product_facets_preserve_or_within_each_field(self) -> None:
        payload = self.service.compact_view(
            {**self.defaults, "sku_classes": ["A", "B"]}
        )
        parent_codes = {
            row["parent_code"] for row in payload["options"]["parent_products"]
        }

        self.assertEqual(payload["request"]["sku_classes"], ["A", "B"])
        self.assertIn(706059, parent_codes)
        self.assertIn(707719, parent_codes)
        self.assertNotIn(703584, parent_codes)
        self.assertFalse(payload["state"]["empty"])

    def test_source_change_reports_removed_product_selection_counts(self) -> None:
        tm_options = self.service.view({**self.defaults, "source": "tm"})["options"]
        common_brand = next(
            brand
            for brand in self.bootstrap["options"]["brands"]
            if brand in tm_options["brands"]
        )

        self.service.compact_view(
            {**self.defaults, "source": "tm", "brands": [common_brand]}
        )
        payload = self.service.compact_view(
            {
                **self.defaults,
                "source": "tm",
                "brands": [common_brand, "BBEL_LUP"],
            }
        )

        self.assertEqual(payload["request"]["brands"], [common_brand])
        self.assertEqual(
            payload["filter_adjustments"]["removed_product_selections"],
            {"brands": 1, "sku_classes": 0, "parent_codes": 0},
        )

    def test_incompatible_product_filter_request_fails(self) -> None:
        with self.assertRaisesRegex(
            DashboardRequestError,
            "product filters are mutually incompatible: brands, sku_classes",
        ):
            self.service.compact_view(
                {
                    **self.defaults,
                    "brands": ["BBEL_LUP"],
                    "sku_classes": ["A"],
                }
            )

    def test_source_change_keeps_valid_product_selections_and_drops_unavailable(self) -> None:
        tm_options = self.service.view({**self.defaults, "source": "tm"})["options"]
        common_brand = next(
            brand
            for brand in self.bootstrap["options"]["brands"]
            if brand in tm_options["brands"]
        )

        payload = self.service.view(
            {
                **self.defaults,
                "source": "tm",
                "brands": [common_brand, "BBEL_LUP"],
            }
        )

        self.assertEqual(payload["request"]["brands"], [common_brand])
        self.assertFalse(payload["state"]["empty"])

    def test_legacy_singular_product_filters_normalize_to_plural_arrays(self) -> None:
        brand = "BPCNO-SP"
        parent_code = 706059

        payload = self.service.view(
            {
                **self.defaults,
                "brands": [],
                "sku_classes": [],
                "parent_codes": [],
                "brand": brand,
                "sku_class": "A",
                "parent_code": parent_code,
            }
        )

        self.assertEqual(payload["request"]["brands"], [brand])
        self.assertEqual(payload["request"]["sku_classes"], ["A"])
        self.assertEqual(payload["request"]["parent_codes"], [parent_code])
        self.assertNotIn("brand", payload["request"])
        self.assertNotIn("sku_class", payload["request"])
        self.assertNotIn("parent_code", payload["request"])

    def test_revision_history_uses_latest_six_actual_months_and_fixed_cohorts(self) -> None:
        payload = self.service.view(self.defaults)
        history = payload["revision_history"]
        months = history["months"]

        self.assertEqual(history["source"], "ml")
        self.assertEqual(history["month_limit"], 6)
        self.assertEqual(history["baseline"], "oldest_available")
        self.assertEqual(history["latest_actual_month"], "2026-08-01")
        self.assertEqual(len(months), 6)
        self.assertEqual(months[0]["snop_month"], "2026-03-01")
        self.assertEqual(months[-1]["snop_month"], history["latest_actual_month"])
        self.assertTrue(all(month["product_count"] > 0 for month in months))
        self.assertTrue(all(month["vintage_count"] == 5 for month in months))
        self.assertTrue(all(month["vintage_count"] == len(month["points"]) for month in months))
        self.assertTrue(all(month["effectiveness_baseline"] == 50 for month in months))
        self.assertTrue(
            all(
                month["latest_effectiveness_score"]
                == month["points"][-1]["revision_effectiveness_score"]
                for month in months
            )
        )
        for month in months:
            points = month["points"]
            self.assertEqual(
                [point["vintage_index"] for point in points], [1, 2, 3, 4, 5]
            )
            self.assertEqual(points[0]["revision_effectiveness_score"], 50)
            self.assertEqual(points[0]["accuracy_gain_score"], 50)
            self.assertEqual(points[0]["revision_efficiency_score"], 50)
            self.assertEqual(points[0]["revision_consistency_score"], 50)
            self.assertTrue(
                all(
                    0 <= point["revision_effectiveness_score"] <= 100
                    for point in points
                )
            )
            self.assertTrue(
                all(
                    point["cumulative_movement_kl"]
                    <= points[index + 1]["cumulative_movement_kl"]
                    for index, point in enumerate(points[:-1])
                )
            )
            for point in points:
                weighted_score = (
                    point["accuracy_gain_score"] * 0.5
                    + point["revision_efficiency_score"] * 0.3
                    + point["revision_consistency_score"] * 0.2
                )
                self.assertAlmostEqual(
                    point["revision_effectiveness_score"], weighted_score
                )
        self.assertTrue(all(month["points"][0]["delta_pct"] == 0 for month in months))
        self.assertTrue(
            all(month["points"][0]["revision_outcome"] == "baseline" for month in months)
        )
        self.assertTrue(
            all(
                point["revision_outcome"] in {"improved", "worsened", "neutral"}
                for month in months
                for point in month["points"][1:]
            )
        )
        self.assertTrue(
            all(
                month["latest_delta_pct"] == month["points"][-1]["delta_pct"]
                for month in months
            )
        )
        self.assertTrue(
            all(
                abs(
                    month["net_fa_improvement_pp"]
                    - (
                        month["latest_forecast_accuracy_pct"]
                        - month["oldest_forecast_accuracy_pct"]
                    )
                )
                < 1e-9
                for month in months
            )
        )
        self.assertTrue(
            any(
                any(abs(point["delta_pct"] or 0) > 0.1 for point in month["points"])
                for month in months
            )
        )

        latest = months[-1]
        self.assertGreater(latest["vintage_count"], 1)
        self.assertNotEqual(latest["latest_delta_pct"], 0)
        self.assertTrue(
            all(point["actual_kl"] == latest["actual_kl"] for point in latest["points"])
        )
        self.assertTrue(
            any(
                point["revision_outcome"] == "improved"
                for month in months
                for point in month["points"][1:]
            )
        )
        self.assertTrue(
            any(
                point["revision_outcome"] == "worsened"
                for month in months
                for point in month["points"][1:]
            )
        )

    def test_revision_history_respects_source_and_product_scope(self) -> None:
        request = dict(self.defaults)
        request.update({"source": "tm", "parent_code": 703584})

        payload = self.service.view(request)
        history = payload["revision_history"]

        self.assertEqual(history["source"], "tm")
        self.assertTrue(history["months"])
        self.assertTrue(
            all(month["product_count"] == 1 for month in history["months"])
        )

    def test_revision_drilldown_ranks_top_parent_codes_by_category_impact(self) -> None:
        response = self.service.module("exceptions", self.defaults)
        drilldown = response["data"]["revision_drilldown"]

        self.assertEqual(drilldown["limit"], 20)
        self.assertEqual(drilldown["ranking"], "error_impact_desc")
        self.assertEqual(
            set(drilldown["categories"]),
            {"improved", "worsened", "neutral", "unchanged"},
        )
        for category, detail in drilldown["categories"].items():
            with self.subTest(category=category):
                rows = detail["rows"]
                self.assertLessEqual(len(rows), 20)
                self.assertLessEqual(len(rows), detail["total_parents"])
                if detail["total_parents"] > 20:
                    self.assertEqual(len(rows), 20)
                self.assertEqual(
                    [row["rank"] for row in rows],
                    list(range(1, len(rows) + 1)),
                )
                self.assertTrue(all(row["category"] == category for row in rows))
                self.assertEqual(
                    [row["impact_kl"] for row in rows],
                    sorted(
                        (row["impact_kl"] for row in rows),
                        reverse=True,
                    ),
                )
                self.assertEqual(
                    len({row["parent_code"] for row in rows}),
                    len(rows),
                )
                self.assertTrue(
                    all(
                        row["observations"] >= row["target_months"] >= 1
                        and row["actual_kl"] >= 0
                        and row["absolute_error_kl"] >= 0
                        and row["impact_kl"] >= 0
                        for row in rows
                    )
                )
                self.assertTrue(
                    {
                        "parent_code",
                        "parent_description",
                        "brand",
                        "observations",
                        "target_months",
                        "actual_kl",
                        "absolute_error_kl",
                        "net_error_improvement_kl",
                        "revision_kl",
                        "impact_kl",
                    }.issubset(rows[0])
                )

    def test_revision_drilldown_parent_selection_recomputes_exception_module(self) -> None:
        base = self.service.module("exceptions", self.defaults)["data"]
        candidates = base["revision_drilldown"]["categories"]["worsened"]["rows"]
        self.assertGreaterEqual(len(candidates), 2)
        selected = [row["parent_code"] for row in candidates[:2]]
        request = dict(self.defaults)
        request["drilldown_parent_codes"] = selected

        response = self.service.module("exceptions", request)
        data = response["data"]
        selected_set = set(selected)

        self.assertEqual(response["request"]["drilldown_parent_codes"], selected)
        self.assertEqual(
            set(data),
            {
                "metrics",
                "exceptions",
                "revision_diagnostics",
                "revision_history",
                "revision_scatter",
                "revision_actions",
                "revision_drilldown",
            },
        )
        self.assertNotEqual(
            data["metrics"]["absolute_error_kl"],
            base["metrics"]["absolute_error_kl"],
        )
        self.assertTrue(data["exceptions"]["rows"])
        self.assertTrue(
            all(
                row["parent_code"] in selected_set
                for row in data["exceptions"]["rows"]
            )
        )
        self.assertTrue(data["revision_scatter"]["rows"])
        self.assertTrue(
            all(
                row["parent_code"] in selected_set
                for row in data["revision_scatter"]["rows"]
            )
        )
        self.assertTrue(
            all(
                row["parent_code"] in selected_set
                for row in data["revision_actions"]["rows"]
            )
        )
        self.assertTrue(
            all(
                month["product_count"] <= len(selected)
                for month in data["revision_history"]["months"]
            )
        )
        self.assertEqual(
            sum(
                row["observations"]
                for row in data["revision_diagnostics"]["rows"]
            ),
            data["metrics"]["complete_pairs"],
        )

    def test_revision_actions_respect_the_selected_source(self) -> None:
        for source in ("tm", "ml"):
            with self.subTest(source=source):
                request = dict(self.defaults)
                request["source"] = source

                payload = self.service.view(request)
                scatter = payload["revision_scatter"]
                actions = payload["revision_actions"]

                self.assertEqual(actions["source"], source)
                self.assertTrue(scatter["rows"])
                self.assertEqual(
                    scatter["total"],
                    len({row["parent_code"] for row in scatter["rows"]}),
                )
                self.assertTrue(
                    all(
                        row["target_months_used"] == 6
                        and row["vintages_per_month"] == 5
                        and row["transitions_used"] == 24
                        and row["absolute_error_kl"] >= 0
                        and row["sku_class"] in {"A", "B", "C", "Unclassified"}
                        and row["winsorized_months"] == 0
                        for row in scatter["rows"]
                    )
                )
                self.assertEqual(
                    {row["source"] for row in scatter["rows"]},
                    {source},
                )
                self.assertTrue(
                    {row["brand"] for row in scatter["rows"]}.isdisjoint(
                        {
                            "PA-BDYLOT",
                            "JFB_POWDR",
                            "RK_CLO_R",
                            "RK_CLO_S",
                            "SAF_HONEY",
                            "BPA_PET_J",
                        }
                    )
                )
                self.assertTrue(
                    all(
                        not (
                            "PCNO" in row["parent_description"].upper()
                            and "EJ" in row["parent_description"].upper()
                        )
                        for row in scatter["rows"]
                    )
                )
                self.assertEqual(
                    {row["source"] for row in actions["rows"]},
                    {source},
                )
                self.assertEqual(
                    actions["material"],
                    actions["improved"] + actions["worsened"] + actions["neutral"],
                )
                self.assertGreater(actions["harmful_error_kl"], 0)
                self.assertLessEqual(
                    actions["top_action_error_kl"],
                    actions["harmful_error_kl"],
                )
                self.assertEqual(len(actions["rows"]), actions["worsened"])
                self.assertTrue(
                    all(row["revision_outcome"] == "worsened" for row in actions["rows"])
                )
                sku_rows = actions["sku_rows"]
                self.assertTrue(sku_rows)
                self.assertEqual(
                    len({row["parent_code"] for row in sku_rows}),
                    len(sku_rows),
                )
                self.assertLessEqual(len(sku_rows), len(actions["rows"]))
                self.assertEqual(
                    [row["priority_rank"] for row in sku_rows],
                    list(range(1, len(sku_rows) + 1)),
                )
                self.assertTrue(
                    any(row["month_count"] > 1 for row in sku_rows)
                )
                outcomes = {
                    point["revision_outcome"]
                    for row in sku_rows
                    for point in row["monthly_performance"]
                }
                self.assertIn("improved", outcomes)
                self.assertIn("worsened", outcomes)
                for row in sku_rows:
                    monthly = row["monthly_performance"]
                    self.assertEqual(row["month_count"], len(monthly))
                    self.assertEqual(
                        [point["snop_month"] for point in monthly],
                        sorted(point["snop_month"] for point in monthly),
                    )
                    self.assertAlmostEqual(
                        row["impact_kl"],
                        sum(
                            point["impact_kl"]
                            for point in monthly
                            if point["revision_outcome"] == "worsened"
                        ),
                    )
                    self.assertIn(
                        row["planner_action"],
                        {"Validate uplift", "Check demand reduction"},
                    )
                self.assertTrue(
                    all(row["parent_description"] for row in actions["rows"])
                )
                self.assertTrue(
                    {
                        "actual_kl",
                        "vintage_a_forecast_kl",
                        "vintage_b_forecast_kl",
                        "revision_kl",
                        "error_improvement_kl",
                        "impact_kl",
                    }.issubset(actions["rows"][0])
                )

    def test_revision_action_export_contains_flag_evidence(self) -> None:
        for source in ("tm", "ml"):
            with self.subTest(source=source):
                request = dict(self.defaults)
                request["source"] = source
                payload = self.service.view(request)

                filename, csv_text = self.service.export_csv(
                    request,
                    kind="revision_actions",
                )
                rows = list(csv.DictReader(io.StringIO(csv_text)))

                self.assertEqual(
                    filename,
                    f"forecast_{source}_revision_action_queue.csv",
                )
                self.assertEqual(len(rows), payload["revision_actions"]["worsened"])
                self.assertTrue(rows)
                self.assertEqual({row["source"] for row in rows}, {source})
                self.assertTrue(all(row["parent_description"] for row in rows))
                self.assertEqual(rows[0]["priority_rank"], "1")
                self.assertIn(rows[0]["planner_action"], {
                    "Validate uplift",
                    "Check demand reduction",
                })
                self.assertTrue(
                    {
                        "vintage_a_forecast_kl",
                        "vintage_b_forecast_kl",
                        "actual_kl",
                        "revision_kl",
                        "error_improvement_kl",
                        "impact_kl",
                    }.issubset(rows[0])
                )

    def test_source_comparison_uses_exact_common_population(self) -> None:
        request = dict(self.defaults)
        request.update({"comparison_mode": True, "horizon": 1})

        payload = self.service.view(request)
        comparison = payload["comparison"]

        self.assertTrue(comparison["ready"])
        self.assertFalse(comparison["blocked"])
        self.assertEqual(comparison["selected_horizon"], 1)
        self.assertEqual(comparison["comparable_pairs"], 1_365)
        self.assertAlmostEqual(
            comparison["tm_metrics"]["forecast_accuracy_pct"],
            76.7095594,
            places=5,
        )
        self.assertAlmostEqual(
            comparison["ml_metrics"]["forecast_accuracy_pct"],
            83.1072136,
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
        self.assertIn(detail["sku_class"], {"A", "B", "C", "Unclassified"})
        self.assertGreater(detail["points"]["total"], 0)
        self.assertGreater(detail["stability"]["total"], 0)

    def test_product_detail_exposes_auditable_postmortem_projection(self) -> None:
        detail = self.service.product_detail(self.defaults)

        self.assertIsNotNone(detail)
        assert detail is not None
        postmortem = detail["postmortem"]
        year_overlay = detail["year_overlay"]
        self.assertEqual(year_overlay["source"], self.defaults["source"])
        self.assertIsNotNone(year_overlay["actual_through"])
        self.assertGreater(year_overlay["points"]["total"], 0)
        actual_through = year_overlay["actual_through"]
        forecast_points = [
            row
            for row in year_overlay["points"]["rows"]
            if row["forecast_kl"] is not None
        ]
        self.assertTrue(forecast_points)
        self.assertTrue(
            all(row["snop_month"] > actual_through for row in forecast_points)
        )
        self.assertTrue(
            all(
                row["calendar_year"] == int(row["snop_month"][:4])
                and row["calendar_month"] == int(row["snop_month"][5:7])
                and row["fiscal_year"]
                == (
                    int(row["snop_month"][:4])
                    if int(row["snop_month"][5:7]) >= 4
                    else int(row["snop_month"][:4]) - 1
                )
                and row["fiscal_month"]
                == (
                    int(row["snop_month"][5:7]) - 3
                    if int(row["snop_month"][5:7]) >= 4
                    else int(row["snop_month"][5:7]) + 9
                )
                for row in year_overlay["points"]["rows"]
            )
        )
        self.assertEqual(postmortem["source"], self.defaults["source"])
        self.assertIn(postmortem["status"], {"ready", "insufficient_history"})
        self.assertIn("forecast_accuracy_pct", postmortem["summary"])
        self.assertIn("revision_efficiency_pct", postmortem["summary"])
        self.assertGreater(postmortem["rolling_performance"]["total"], 0)
        self.assertGreater(postmortem["peer_benchmarks"]["total"], 0)
        self.assertGreater(postmortem["commentary"]["total"], 0)
        self.assertIn(
            postmortem["treatment"]["action"],
            {"hold", "rebase", "rephase", "scenario", "escalate"},
        )
        self.assertTrue(
            all(
                row["evidence_refs"]
                for row in postmortem["commentary"]["rows"]
            )
        )

    def test_year_overlay_is_target_independent_and_source_specific(self) -> None:
        ml_detail = self.service.product_detail(self.defaults)
        self.assertIsNotNone(ml_detail)
        assert ml_detail is not None
        target_options = ml_detail["target_options"]
        self.assertGreater(len(target_options), 1)

        alternate_target = self.service.product_detail(
            {
                **self.defaults,
                "product_parent_code": ml_detail["parent_code"],
                "product_target_month": target_options[0],
            }
        )
        self.assertIsNotNone(alternate_target)
        assert alternate_target is not None
        self.assertEqual(
            alternate_target["year_overlay"],
            ml_detail["year_overlay"],
        )

        tm_detail = self.service.product_detail(
            {
                **self.defaults,
                "source": "tm",
                "product_parent_code": ml_detail["parent_code"],
            }
        )
        self.assertIsNotNone(tm_detail)
        assert tm_detail is not None
        ml_actuals = [
            row
            for row in ml_detail["year_overlay"]["points"]["rows"]
            if row["actual_kl"] is not None
        ]
        tm_actuals = [
            row
            for row in tm_detail["year_overlay"]["points"]["rows"]
            if row["actual_kl"] is not None
        ]
        self.assertEqual(tm_actuals, ml_actuals)
        self.assertEqual(tm_detail["year_overlay"]["source"], "tm")

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

        self.assertEqual(filename, "forecast_ml_filtered_vintages.csv")
        self.assertEqual(len(rows), payload["exceptions"]["total"])
        self.assertTrue(rows)
        self.assertTrue(all(row["parent_code"] == "703584" for row in rows))
        self.assertIn("vintage_b_forecast_kl", rows[0])
        self.assertIn("revision_outcome", rows[0])

    def test_invalid_requests_fail_with_field_specific_errors(self) -> None:
        with self.assertRaisesRegex(DashboardRequestError, "source must be one of"):
            self.service.view({"source": "other"})
        with self.assertRaisesRegex(DashboardRequestError, "sku_class must be one of"):
            self.service.view({"sku_class": "D"})
        with self.assertRaisesRegex(DashboardRequestError, "target_start"):
            self.service.view(
                {"target_start": "2026-12-01", "target_end": "2025-05-01"}
            )
        with self.assertRaisesRegex(DashboardRequestError, "quality category"):
            self.service.export_csv(self.defaults, kind="quality", category="other")


if __name__ == "__main__":
    unittest.main()
