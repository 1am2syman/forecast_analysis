"""Deferred browser contract tests for the Marimo dashboard.

Run only as an explicit e2e job after starting the app, for example:

    uv run marimo run forecast_accuracy_app.py --headless --port 8765
    FORECAST_DASHBOARD_URL=http://127.0.0.1:8765 \
        uv run python -m unittest discover -s tests/e2e -p 'test_*.py'

The release task intentionally does not run this module. It requires a
browser runtime and validates presentation behavior rather than pure analysis
contracts.
"""

from __future__ import annotations

import csv
import importlib
import os
import unittest
from datetime import date
from pathlib import Path

CSV_COLUMNS = [
    "source",
    "parent_code",
    "parent_description",
    "brand",
    "snop_month",
    "actual_kl",
    "actual_status",
    "vintage_a_calculation_month",
    "vintage_a_horizon_months",
    "vintage_a_forecast_kl",
    "vintage_b_calculation_month",
    "vintage_b_horizon_months",
    "vintage_b_forecast_kl",
    "absolute_error_b_kl",
    "bias_b_kl",
    "revision_kl",
    "error_improvement_kl",
    "revision_direction",
    "revision_outcome",
    "pair_status",
    "mapping_status",
]
NUMERIC_COLUMNS = {
    "actual_kl",
    "vintage_a_forecast_kl",
    "vintage_b_forecast_kl",
    "absolute_error_b_kl",
    "bias_b_kl",
    "revision_kl",
    "error_improvement_kl",
}
EXPECTED_FILTERED_ROW = {
    "source": "tm",
    "parent_code": "703584",
    "parent_description": "PCNO ADV 300ml FT",
    "brand": "BPAR-ADV",
    "snop_month": "2025-11-01",
    "actual_kl": 3.320737,
    "actual_status": "matched_positive",
    "vintage_a_calculation_month": "2025-07-01",
    "vintage_a_horizon_months": "4",
    "vintage_a_forecast_kl": 1.496027962,
    "vintage_b_calculation_month": "2025-07-01",
    "vintage_b_horizon_months": "4",
    "vintage_b_forecast_kl": 1.496027962,
    "absolute_error_b_kl": 1.824709038,
    "bias_b_kl": -1.824709038,
    "revision_kl": 0.0,
    "error_improvement_kl": 0.0,
    "revision_direction": "unchanged",
    "revision_outcome": "neutral",
    "pair_status": "complete",
    "mapping_status": "mapped",
}


@unittest.skipUnless(
    os.environ.get("FORECAST_DASHBOARD_URL"),
    "deferred e2e suite; set FORECAST_DASHBOARD_URL to run",
)
class ForecastAnalysisDashboardBrowserTests(unittest.TestCase):
    """Exercise concrete user-visible dashboard workflows."""

    @classmethod
    def setUpClass(cls) -> None:
        # Keep Playwright optional for the targeted non-e2e test environment.
        playwright_module = importlib.import_module("playwright.sync_api")
        cls._playwright_timeout = playwright_module.__dict__["TimeoutError"]
        cls._playwright = playwright_module.__dict__["sync_playwright"]().start()
        cls._browser = cls._playwright.chromium.launch(headless=True)
        cls._page = cls._browser.new_page()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._browser.close()
        cls._playwright.stop()

    @property
    def page(self):
        page = self._page
        page.goto(
            os.environ["FORECAST_DASHBOARD_URL"],
            wait_until="domcontentloaded",
        )
        self._wait_for_text("Population summary")
        return page

    def _wait_for_text(self, text: str) -> None:
        self._page.get_by_text(text, exact=False).first.wait_for(
            state="visible",
            timeout=30_000,
        )

    def _body(self) -> str:
        return self._page.locator("body").inner_text()

    def _visible_filtered_pair_row(self) -> dict[str, str]:
        """Read the one selected-pair row in the named filtered-vintage table."""
        wrapper = self._page.get_by_test_id("filtered-vintage-table")
        wrapper.wait_for(state="visible", timeout=10_000)
        table = wrapper.locator("marimo-table")
        self.assertEqual(table.count(), 1)
        table.wait_for(state="visible", timeout=10_000)
        headers = table.locator("thead th").all_inner_texts()
        rows = table.locator("tbody tr")
        self.assertEqual(rows.count(), 1)
        values = rows.first.locator("td").all_inner_texts()
        self.assertEqual(len(headers), len(values))
        return {
            " ".join(header.replace("_", " ").lower().split()): " ".join(
                value.split()
            )
            for header, value in zip(headers, values)
        }

    def _open_data_quality_filters(self) -> None:
        control = self._page.get_by_label("Vintage-pair quality status")
        if not control.is_visible():
            self._page.get_by_text("Data-quality filters", exact=True).click()
        control.wait_for(state="visible", timeout=10_000)

    def _replace_multiselect(self, label: str, option: str) -> None:
        """Use Marimo's real multiselect trigger and bulk deselection option."""
        control = self._page.get_by_label(label)
        if not control.is_visible():
            self._page.get_by_text("Data-quality filters", exact=True).click()
            control.wait_for(state="visible", timeout=10_000)
        control.click()
        deselect_locator = self._page.get_by_role(
            "option",
            name="Deselect all",
            exact=True,
        )
        deselect_locator.wait_for(state="visible", timeout=10_000)
        deselect_locator.click()
        option_locator = self._page.get_by_role(
            "option",
            name=option,
            exact=True,
        )
        try:
            option_locator.wait_for(state="visible", timeout=1_000)
        except self._playwright_timeout:
            # Marimo closes a multiselect after a bulk action in some versions.
            control.click()
            option_locator.wait_for(state="visible", timeout=10_000)
        option_locator.click()
        self._page.keyboard.press("Escape")

    def _apply_deterministic_filtered_scope(self) -> None:
        """Select one real product, horizon, volume, and pair-quality status."""
        self._replace_multiselect(
            "Parent product",
            "703584 — PCNO ADV 300ml FT",
        )
        self._replace_multiselect("Forecast horizon", "4 months ahead")
        self._page.get_by_label("Minimum actual volume (KL)").fill("3.3")
        self._page.get_by_label("Vintage A rule").select_option(
            label="Exact horizon"
        )
        self._page.get_by_label("Vintage B rule").select_option(
            label="Exact horizon"
        )
        self._page.get_by_label("Vintage A exact horizon").select_option(
            label="4 months ahead"
        )
        self._page.get_by_label("Vintage B exact horizon").select_option(
            label="4 months ahead"
        )
        self._open_data_quality_filters()
        self._replace_multiselect("Hierarchy quality status", "Mapped")
        self._replace_multiselect("Actual quality status", "Positive actual")
        self._replace_multiselect("Vintage-pair quality status", "Complete pair")
        self._replace_multiselect("Forecast direction", "Under forecast")
        self._replace_multiselect(
            "Revision direction (active with comparable pairs)",
            "Unchanged",
        )
        self._replace_multiselect(
            "Revision outcome (active with comparable pairs)",
            "Neutral",
        )
        self._page.get_by_label(
            "Minimum Vintage B absolute error (KL)"
        ).fill("1.0")
        self._wait_for_text("Products: 1 · Forecast rows: 1")

    def test_standard_tm_mode_has_concrete_population_and_quality_values(self):
        page = self.page
        self._wait_for_text("2,641")
        body = self._body()
        self.assertIn("Forecast performance — TM", body)
        self.assertIn("Products: 141 · Forecast rows: 8,515", body)
        self.assertIn("Actual volume: 31,930.4 KL", body)
        self.assertIn("Eligible observations: 1,203", body)
        self.assertIn("Comparable pairs: 1,203", body)
        self.assertIn("Coverage (selected source population): 99.3%", body)
        self.assertIn("Selected pair rows: 2,260", body)
        self.assertIn("Vintage rules: Vintage A = oldest_available", body)
        self.assertIn("Hierarchy mapping", body)
        self.assertIn("Actual availability", body)
        self.assertIn("Vintage pairs", body)
        self.assertIn("Source availability", body)
        self.assertEqual(
            page.get_by_role(
                "link",
                name="Download filtered vintage CSV",
                exact=True,
            ).count(),
            1,
        )

    def test_standard_ml_mode_recalculates_concrete_population_values(self):
        page = self.page
        page.get_by_label("Forecast source (single-source mode)").select_option(
            label="ML"
        )
        self._wait_for_text("Forecast performance — ML")
        body = self._body()
        self.assertIn("Products: 101 · Forecast rows: 7,520", body)
        self.assertIn("Actual volume: 31,427.6 KL", body)
        self.assertIn("Eligible observations: 1,165", body)
        self.assertIn("Comparable pairs: 1,165", body)
        self.assertIn("Coverage (selected source population): 99.3%", body)
        self.assertNotIn("Forecast performance — TM\n", body)

    def test_comparison_mode_shows_concrete_aligned_population_and_source_metrics(self):
        page = self.page
        page.get_by_label("View mode").select_option(
            label="Compare TM vs ML"
        )
        self._wait_for_text("Forecast performance — TM vs ML comparison")
        body = self._body()
        self.assertIn("Products: 138 · Forecast rows: 3,209", body)
        self.assertIn("Actual volume: 31,936.6 KL", body)
        self.assertIn("Eligible observations: 963", body)
        self.assertIn("Comparable pairs: 1,275", body)
        self.assertIn(
            "Common population: 1,275 paired product-target observations",
            body,
        )
        self.assertIn(
            "Coverage: 28,261.1 KL common actual volume · 430 TM-only · 229 ML-only",
            body,
        )
        self.assertIn("Accuracy (%): 77.0%", body)
        self.assertIn("Accuracy (%): 81.3%", body)
        self.assertIn("TM ↔ ML aligned population", body)

    def test_comparison_pair_status_filter_narrows_population_and_quality(self):
        page = self.page
        page.get_by_label("View mode").select_option(
            label="Compare TM vs ML"
        )
        self._wait_for_text("Forecast performance — TM vs ML comparison")
        self._open_data_quality_filters()
        self._replace_multiselect("Vintage-pair quality status", "Complete pair")
        self._wait_for_text("Products: 115 · Forecast rows: 2,226")
        body = self._body()
        self.assertIn("Actual volume: 31,629.7 KL", body)
        self.assertIn("Eligible observations: 963", body)
        self.assertIn("Comparable pairs: 963", body)
        self.assertIn("Selected pair rows: 2,226", body)
        self.assertIn("Coverage (common aligned population): 89.3%", body)
        self.assertIn("complete", body)
        self.assertIn("2,226", body)

    def test_valid_shared_filters_narrow_kpis_quality_and_visible_population(self):
        page = self.page
        self._apply_deterministic_filtered_scope()
        self.assertEqual(
            page.get_by_label("Minimum actual volume (KL)").input_value(),
            "3.3",
        )
        body = self._body()
        self.assertIn("Forecast performance — TM", body)
        self.assertIn("Products: 1 · Forecast rows: 1", body)
        self.assertIn("Actual volume: 3.3 KL", body)
        self.assertIn("Eligible observations: 1", body)
        self.assertIn("Comparable pairs: 1", body)
        self.assertIn("Selected pair rows: 1", body)
        self.assertIn("Selected horizons: 4 months ahead", body)
        self.assertIn("2025-11-01", body)
        self.assertIn("703584", body)
        self.assertIn("BPAR-ADV", body)
        self.assertIn("matched_positive", body)
        self.assertIn("complete", body)
        self.assertIn("Coverage (selected source population): 100.0%", body)

    def test_quality_sections_have_concrete_download_controls(self):
        page = self.page
        self._wait_for_text("2,641")
        body = self._body()
        for value in ("2,641", "1,579", "1,203", "499"):
            self.assertIn(value, body)
        expected_links = [
            "Download hierarchy mapping exceptions",
            "Download actual availability exceptions",
            "Download vintage pairs exceptions",
            "Download source availability exceptions",
        ]
        for label in expected_links:
            with self.subTest(label=label):
                self.assertEqual(
                    page.get_by_role("link", name=label, exact=True).count(),
                    1,
                )

    def test_download_matches_every_visible_filtered_row_and_value(self):
        page = self.page
        self._apply_deterministic_filtered_scope()
        body = self._body()
        self.assertIn(
            "Vintage rules: Vintage A = specific_horizon:4 · Vintage B = specific_horizon:4",
            body,
        )
        self.assertIn("Products: 1 · Forecast rows: 1", body)
        self.assertIn("Selected pair rows: 1", body)
        visible = self._visible_filtered_pair_row()

        with page.expect_download(timeout=30_000) as download_info:
            page.get_by_role(
                "link",
                name="Download filtered vintage CSV",
                exact=True,
            ).click()
        download = download_info.value
        self.assertEqual(download.suggested_filename, "forecast_tm_filtered_vintages.csv")
        with Path(download.path()).open(newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            self.assertEqual(reader.fieldnames, CSV_COLUMNS)
            rows = list(reader)

        self.assertEqual(len(rows), 1)
        actual = rows[0]
        for column in CSV_COLUMNS:
            expected = EXPECTED_FILTERED_ROW[column]
            if column in NUMERIC_COLUMNS:
                self.assertAlmostEqual(float(actual[column]), expected, places=9)
            else:
                self.assertEqual(actual[column], expected)
        self.assertEqual({actual["source"]}, {"tm"})
        self.assertEqual(actual["parent_code"], "703584")
        self.assertEqual(actual["snop_month"], "2025-11-01")
        self.assertEqual(actual["vintage_a_horizon_months"], "4")
        self.assertEqual(actual["vintage_b_horizon_months"], "4")

        visible_to_download = {
            "source label": "source",
            "parent code": "parent_code",
            "parent description": "parent_description",
            "brand display": "brand",
            "mapping status": "mapping_status",
            "snop month": "snop_month",
            "actual kl": "actual_kl",
            "actual status": "actual_status",
            "vintage a calculation month": "vintage_a_calculation_month",
            "vintage a horizon months": "vintage_a_horizon_months",
            "vintage a forecast kl": "vintage_a_forecast_kl",
            "vintage b calculation month": "vintage_b_calculation_month",
            "vintage b horizon months": "vintage_b_horizon_months",
            "vintage b forecast kl": "vintage_b_forecast_kl",
            "vintage b absolute error kl": "absolute_error_b_kl",
            "vintage b bias kl": "bias_b_kl",
            "revision kl": "revision_kl",
            "error improvement kl": "error_improvement_kl",
            "revision direction": "revision_direction",
            "revision outcome": "revision_outcome",
            "pair status": "pair_status",
        }
        date_columns = {
            "snop_month",
            "vintage_a_calculation_month",
            "vintage_b_calculation_month",
        }
        for visible_column, download_column in visible_to_download.items():
            with self.subTest(visible_column=visible_column):
                self.assertIn(visible_column, visible)
                displayed = visible[visible_column]
                expected = actual[download_column]
                if download_column == "source":
                    self.assertEqual(displayed.lower(), expected)
                elif download_column in NUMERIC_COLUMNS:
                    self.assertAlmostEqual(
                        float(displayed.replace(",", "").replace("KL", "")),
                        float(expected),
                        places=2,
                    )
                elif download_column in date_columns:
                    expected_date = date.fromisoformat(expected)
                    self.assertTrue(
                        expected in displayed
                        or expected_date.strftime("%b %-d, %Y") in displayed
                        or expected_date.strftime("%B %-d, %Y") in displayed
                    )
                else:
                    self.assertEqual(displayed, expected)

    def test_empty_state_after_valid_empty_product_selection(self):
        page = self.page
        control = page.get_by_label("Parent product")
        control.click()
        page.get_by_role("option", name="Deselect all", exact=True).click()
        page.keyboard.press("Escape")
        self._wait_for_text("Products: 0 · Forecast rows: 0")
        body = self._body()
        self.assertIn("No forecast rows match the active filters", body)
        self.assertIn("Products: 0 · Forecast rows: 0", body)
        self.assertIn("Forecast accuracy (%)", body)
        self.assertNotIn("Traceback", body)


if __name__ == "__main__":
    unittest.main()
