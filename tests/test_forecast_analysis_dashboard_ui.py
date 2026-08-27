"""Focused tests for the dashboard browser-capture and overflow oracle."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_forecast_analysis_dashboard_ui import (  # pyright: ignore[reportMissingImports]
    CAPTURE_CONTRACT,
    NORMALIZATION_CONTRACT,
    OVERFLOW_TOLERANCE_PX,
    evaluate_overflow,
    measure_overflow,
    normalize_browser_capture,
    png_dimensions,
    sha256_file,
    validate_capture_artifact,
    verify_baseline,
)

BASELINE_IMAGE = ROOT / "validation-artifacts/forecast-analysis-dashboard-long-full.png"
CAPTURE_ARTIFACT = ROOT / "validation-artifacts/forecast-analysis-dashboard-ui-baseline.json"


def _box(
    client_width: int,
    scroll_width: int,
    client_height: int = 800,
    scroll_height: int = 800,
) -> dict[str, int]:
    return {
        "clientWidth": client_width,
        "scrollWidth": scroll_width,
        "clientHeight": client_height,
        "scrollHeight": scroll_height,
    }


class DashboardUiOverflowTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        print("UI validation logic tests passed")
        super().tearDownClass()

    def test_two_pixel_tolerance_is_inclusive(self) -> None:
        result = measure_overflow(_box(1280, 1282))

        self.assertEqual(result["overflow_px"], 2)
        self.assertTrue(result["passes"])
        self.assertFalse(result["overflows"])
        self.assertEqual(result["tolerance_px"], OVERFLOW_TOLERANCE_PX)

    def test_overflowing_positive_control_fails(self) -> None:
        result = measure_overflow(_box(1280, 1283))

        self.assertEqual(result["overflow_px"], 3)
        self.assertFalse(result["passes"])
        self.assertTrue(result["overflows"])

    def test_document_and_application_results_are_independent(self) -> None:
        result = evaluate_overflow(
            _box(1280, 1280),
            _box(1280, 2000),
        )

        self.assertTrue(result["document"]["passes"])
        self.assertFalse(result["application"]["passes"])
        self.assertFalse(result["passes"])
        self.assertEqual(result["document"]["scroll_width"], 1280)
        self.assertEqual(result["application"]["scroll_width"], 2000)

        reverse_result = evaluate_overflow(
            _box(1280, 6650),
            _box(6650, 6650),
        )
        self.assertFalse(reverse_result["document"]["passes"])
        self.assertTrue(reverse_result["application"]["passes"])
        self.assertFalse(reverse_result["passes"])

    def test_native_browser_result_is_normalized_without_losing_state(self) -> None:
        result = normalize_browser_capture(
            {
                "origin": "http://127.0.0.1:8765/",
                "result": {
                    "url": "http://127.0.0.1:8765/",
                    "title": "forecast accuracy app",
                    "viewport": {
                        "width": 1280,
                        "height": 800,
                        "devicePixelRatio": 1,
                    },
                    "document": _box(1280, 6650, 800, 11082),
                    "app": _box(6650, 6650, 11082, 11082),
                    "body": _box(1280, 6650, 11082, 11082),
                    "normalized": True,
                    "normalization_contract": NORMALIZATION_CONTRACT,
                    "state": "expanded-audit",
                },
            }
        )

        self.assertEqual(result["application"]["scrollWidth"], 6650)
        self.assertTrue(result["normalized"])
        self.assertEqual(result["normalization_contract"], NORMALIZATION_CONTRACT)
        self.assertEqual(result["state"], "expanded-audit")


class DashboardUiArtifactTests(unittest.TestCase):
    def test_immutable_baseline_dimensions_and_digest_are_recomputed(self) -> None:
        result = verify_baseline(ROOT, BASELINE_IMAGE, 6650, 11082)

        self.assertEqual(result["width"], 6650)
        self.assertEqual(result["height"], 11082)
        self.assertEqual(result["sha256"], sha256_file(BASELINE_IMAGE))
        self.assertEqual(png_dimensions(BASELINE_IMAGE), (6650, 11082))

    def test_checked_in_capture_artifact_recomputes_measurements_and_screenshots(self) -> None:
        result = validate_capture_artifact(
            ROOT,
            CAPTURE_ARTIFACT,
            require_normalized=True,
        )

        self.assertFalse(result["pre_overflow"]["passes"])
        self.assertTrue(result["pre_overflow"]["application"]["overflows"])
        self.assertTrue(result["normalized_overflow"]["document"]["overflows"])
        self.assertTrue(result["normalized_overflow"]["application"]["passes"])
        self.assertEqual(
            result["normalized_screenshot"]["width"],
            result["normalized_overflow"]["document"]["scroll_width"],
        )
        self.assertEqual(
            result["normalized_screenshot"]["height"],
            result["expanded_screenshot"]["height"],
        )
        self.assertGreater(
            result["normalized_screenshot"]["height"],
            result["default_screenshot"]["height"],
        )

    def test_capture_contract_has_explicit_analytical_state_fields(self) -> None:
        payload = json.loads(CAPTURE_ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(payload["capture_contract"], CAPTURE_CONTRACT)
        self.assertEqual(payload["analytical_state"]["source"], "TM")
        self.assertEqual(payload["analytical_state"]["vintage_a_rule"], "Oldest available")
        self.assertEqual(payload["analytical_state"]["vintage_b_rule"], "Latest available")
        self.assertEqual(payload["analytical_state"]["performance_filters"]["top_n"], 0)
        self.assertFalse(
            payload["analytical_state"]["quality_filters"]["zero_forecasts_only"]
        )


if __name__ == "__main__":
    unittest.main()
