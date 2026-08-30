"""Focused tests for the dashboard browser-capture and overflow oracle."""

from __future__ import annotations

import binascii
import json
import shutil
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from forecast_analysis_dashboard_ui_contract import (  # pyright: ignore[reportMissingImports]
    sha256_json,
    sha256_json_file,
)
from validate_forecast_analysis_dashboard_ui import (  # pyright: ignore[reportMissingImports]
    CAPTURE_CONTRACT,
    CaptureValidationError,
    NORMALIZATION_CONTRACT,
    OVERFLOW_TOLERANCE_PX,
    evaluate_overflow,
    measure_overflow,
    normalize_browser_capture,
    png_difference_evidence,
    png_dimensions,
    _png_scanlines,
    sha256_file,
    validate_state_transition,
    validate_capture_artifact,
    verify_baseline,
    verify_live_capture,
)

BASELINE_IMAGE = ROOT / "validation-artifacts/forecast-analysis-dashboard-long-full.png"
CAPTURE_ARTIFACT = ROOT / "validation-artifacts/forecast-analysis-dashboard-ui-baseline.json"
CAPTURE_FIXTURE_FILES = (
    "forecast-analysis-dashboard-ui-baseline.json",
    "forecast-analysis-dashboard-ui-raw-default.json",
    "forecast-analysis-dashboard-ui-raw-expanded.json",
    "forecast-analysis-dashboard-ui-normalization-default.json",
    "forecast-analysis-dashboard-ui-normalization-expanded.json",
    "forecast-analysis-dashboard-long-full.png",
    "forecast-analysis-dashboard-default.png",
    "forecast-analysis-dashboard-expanded.png",
)


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _write_rgb_png(path: Path, rows: list[list[tuple[int, int, int]]]) -> None:
    """Write a tiny unfiltered RGB PNG for deterministic image regressions."""
    if not rows or not rows[0]:
        raise ValueError("PNG fixture needs at least one pixel")
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ValueError("PNG fixture rows must have equal widths")
    raw = b"".join(
        b"\x00" + bytes(channel for pixel in row for channel in pixel)
        for row in rows
    )
    signature = b"\x89PNG\r\n\x1a\n"
    path.write_bytes(
        signature
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, len(rows), 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw))
        + _png_chunk(b"IEND", b"")
    )


def _write_solid_rgb_png(
    path: Path,
    width: int,
    height: int,
    rgb: tuple[int, int, int] = (255, 255, 255),
) -> None:
    row = bytes(rgb) * width
    raw = b"".join(b"\x00" + row for _ in range(height))
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw))
        + _png_chunk(b"IEND", b"")
    )


def _pad_png(
    source: Path,
    destination: Path,
    target_height: int,
    fill: tuple[int, int, int] = (255, 255, 255),
) -> None:
    width, height, channels, scanlines = _png_scanlines(source)
    if channels != 3 or target_height < height:
        raise ValueError("fixture padding requires an RGB PNG and a taller target")
    fill_row = b"\x00" + bytes(fill) * width
    raw = scanlines + fill_row * (target_height - height)
    destination.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, target_height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw))
        + _png_chunk(b"IEND", b"")
    )


def _write_banded_rgb_png(path: Path, width: int, height: int) -> None:
    colors = (
        (40, 80, 120),
        (180, 70, 60),
        (60, 150, 90),
        (150, 100, 190),
        (220, 150, 40),
        (50, 160, 180),
        (190, 60, 140),
        (80, 90, 210),
    )
    compressor = zlib.compressobj()
    compressed = bytearray()
    for row_index in range(height):
        color = colors[row_index * len(colors) // height]
        compressed.extend(compressor.compress(b"\x00" + bytes(color) * width))
    compressed.extend(compressor.flush())
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", bytes(compressed))
        + _png_chunk(b"IEND", b"")
    )


def _update_screenshot_records(
    value: object,
    target_path: str,
    width: int,
    height: int,
    digest: str,
) -> None:
    if isinstance(value, dict):
        if (
            value.get("path") == target_path
            and all(field in value for field in ("width", "height", "sha256"))
        ):
            value["width"] = width
            value["height"] = height
            value["sha256"] = digest
        for child in value.values():
            _update_screenshot_records(child, target_path, width, height, digest)
    elif isinstance(value, list):
        for child in value:
            _update_screenshot_records(child, target_path, width, height, digest)


def _relocate_paths(value: object, source_root: Path, target_root: Path) -> object:
    if isinstance(value, dict):
        return {key: _relocate_paths(child, source_root, target_root) for key, child in value.items()}
    if isinstance(value, list):
        return [_relocate_paths(child, source_root, target_root) for child in value]
    if isinstance(value, str) and value.startswith(str(source_root)):
        return str(target_root) + value[len(str(source_root)) :]
    return value


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _fast_static_validation(root: Path, artifact: Path, **kwargs: object) -> dict[str, object]:
    del root, kwargs
    return {"payload": json.loads(artifact.read_text(encoding="utf-8"))}


def _copy_capture_fixture(directory: Path) -> Path:
    artifact_directory = directory / "validation-artifacts"
    artifact_directory.mkdir(exist_ok=True)
    source_directory = ROOT / "validation-artifacts"
    for filename in CAPTURE_FIXTURE_FILES:
        shutil.copy2(source_directory / filename, artifact_directory / filename)
    for filename in (
        "forecast-analysis-dashboard-ui-baseline.json",
        "forecast-analysis-dashboard-ui-raw-default.json",
        "forecast-analysis-dashboard-ui-raw-expanded.json",
        "forecast-analysis-dashboard-ui-normalization-default.json",
        "forecast-analysis-dashboard-ui-normalization-expanded.json",
    ):
        path = artifact_directory / filename
        payload = json.loads(path.read_text(encoding="utf-8"))
        _write_json(path, _relocate_paths(payload, ROOT, directory))
    return artifact_directory / "forecast-analysis-dashboard-ui-baseline.json"


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

    def test_padded_closed_screenshot_is_not_an_expanded_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            default = root / "default.png"
            padded = root / "padded-default.png"
            rows = [
                [(20, 30, 40), (240, 240, 240)],
                [(60, 70, 80), (220, 220, 220)],
            ]
            _write_rgb_png(default, rows)
            _write_rgb_png(padded, rows + [[(255, 255, 255), (255, 255, 255)]])

            evidence = png_difference_evidence(default, padded)

            self.assertFalse(evidence["same_dimensions"])
            self.assertEqual(evidence["overlap_height"], 2)
            self.assertEqual(evidence["changed_pixels"], 0)
            self.assertEqual(evidence["overlap_difference_ratio"], 0.0)
            self.assertFalse(evidence["state_difference"])
            with self.assertRaisesRegex(
                CaptureValidationError,
                "changed overlapping content",
            ):
                validate_state_transition(default, padded)

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
    def _assert_substituted_expanded_capture_is_rejected(
        self,
        replace_image,
        *,
        require_live: bool = False,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture_root = Path(directory)
            fixture_artifact = _copy_capture_fixture(fixture_root)
            expanded_image = fixture_root / "validation-artifacts/forecast-analysis-dashboard-expanded.png"
            replace_image(fixture_root, expanded_image)
            width, height = png_dimensions(expanded_image)
            digest = sha256_file(expanded_image)
            target_path = "validation-artifacts/forecast-analysis-dashboard-expanded.png"

            normalization_payload = json.loads(
                (fixture_root / "validation-artifacts/forecast-analysis-dashboard-ui-normalization-expanded.json").read_text(encoding="utf-8")
            )
            binding = normalization_payload["screenshot_binding"]
            binding["screenshot"] = {
                "path": target_path,
                "width": width,
                "height": height,
                "sha256": digest,
            }
            binding["binding_sha256"] = sha256_json(
                {key: value for key, value in binding.items() if key != "binding_sha256"}
            )
            normalization_payload["screenshot"] = {
                **binding["screenshot"],
                "binding_sha256": binding["binding_sha256"],
            }
            if require_live:
                normalization_payload["screenshot_command"]["capture_output"].update(
                    {
                        "width": width,
                        "height": height,
                        "sha256": digest,
                        "binding_sha256": binding["binding_sha256"],
                    }
                )
            normalization_path = fixture_root / "validation-artifacts/forecast-analysis-dashboard-ui-normalization-expanded.json"
            _write_json(normalization_path, normalization_payload)

            artifact_payload = json.loads(fixture_artifact.read_text(encoding="utf-8"))
            _update_screenshot_records(artifact_payload, target_path, width, height, digest)
            expanded_capture = artifact_payload["expanded_capture"]
            expanded_capture["screenshot_binding"] = binding
            expanded_capture["normalized_capture"]["screenshot"] = normalization_payload["screenshot"]
            artifact_payload["normalized_capture"]["screenshot"] = normalization_payload["screenshot"]
            artifact_payload["screenshots"]["expanded"] = normalization_payload["screenshot"]
            anchor_state = artifact_payload["capture_anchor"]["states"]["expanded-open"]
            anchor_state.update(
                {
                    "normalization_artifact_sha256": sha256_json_file(normalization_path, fixture_root),
                    "screenshot_width": width,
                    "screenshot_height": height,
                    "screenshot_sha256": digest,
                    "binding_sha256": binding["binding_sha256"],
                }
            )
            anchor = artifact_payload["capture_anchor"]
            anchor["anchor_sha256"] = sha256_json(
                {key: value for key, value in anchor.items() if key != "anchor_sha256"}
            )
            _write_json(fixture_artifact, artifact_payload)

            if not require_live:
                with self.assertRaisesRegex(
                    CaptureValidationError,
                    "screenshot_command_proof|capture_output|binding|screenshot width|screenshot height",
                ):
                    validate_capture_artifact(
                        fixture_root,
                        fixture_artifact,
                        require_normalized=True,
                    )
                return

            _fast_static_validation(
                fixture_root,
                fixture_artifact,
                require_normalized=True,
            )

            def trusted_recapture(
                capture_root: Path,
                url: str,
                browser: str,
            ) -> object:
                del url, browser
                fresh_artifact = _copy_capture_fixture(capture_root)
                return {
                    "payload": json.loads(fresh_artifact.read_text(encoding="utf-8")),
                }

            with self.assertRaisesRegex(
                CaptureValidationError,
                "live recapture does not match",
            ):
                verify_live_capture(
                    fixture_root,
                    fixture_artifact,
                    recapture=trusted_recapture,
                    validator=_fast_static_validation,
                )

    def test_viewport_only_expanded_substitution_is_rejected_by_full_artifact(self) -> None:
        def replace(root: Path, destination: Path) -> None:
            _write_solid_rgb_png(destination, 1280, 800, (40, 50, 60))

        self._assert_substituted_expanded_capture_is_rejected(replace)

    def test_padded_default_expanded_substitution_is_rejected_by_full_artifact(self) -> None:
        def replace(root: Path, destination: Path) -> None:
            _pad_png(
                root / "validation-artifacts/forecast-analysis-dashboard-default.png",
                destination,
                11186,
            )

        self._assert_substituted_expanded_capture_is_rejected(replace)

    def test_wrong_state_expanded_substitution_is_rejected_by_full_artifact(self) -> None:
        def replace(root: Path, destination: Path) -> None:
            shutil.copy2(root / "validation-artifacts/forecast-analysis-dashboard-default.png", destination)

        self._assert_substituted_expanded_capture_is_rejected(replace)

    def test_independent_meaningful_expanded_substitution_is_rejected_by_full_artifact(self) -> None:
        def replace(root: Path, destination: Path) -> None:
            _write_banded_rgb_png(destination, 6650, 11186)

        self._assert_substituted_expanded_capture_is_rejected(replace)

    def test_immutable_baseline_padded_expanded_substitution_is_rejected_by_full_artifact(self) -> None:
        def replace(root: Path, destination: Path) -> None:
            _pad_png(
                root / "validation-artifacts/forecast-analysis-dashboard-long-full.png",
                destination,
                11186,
            )

        self._assert_substituted_expanded_capture_is_rejected(
            replace,
            require_live=True,
        )

    def test_live_recapture_matches_checked_in_capture_with_injected_runner(self) -> None:
        def trusted_recapture(
            capture_root: Path,
            url: str,
            browser: str,
        ) -> object:
            del url, browser
            fresh_artifact = _copy_capture_fixture(capture_root)
            return {
                "payload": json.loads(fresh_artifact.read_text(encoding="utf-8")),
            }

        result = verify_live_capture(
            ROOT,
            CAPTURE_ARTIFACT,
            recapture=trusted_recapture,
            validator=_fast_static_validation,
        )

        self.assertEqual(result["contract"]["screenshots"]["expanded"]["sha256"], sha256_file(
            ROOT / "validation-artifacts/forecast-analysis-dashboard-expanded.png"
        ))

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
