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


class DashboardUiSourceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (ROOT / "dashboard/app.js").read_text(encoding="utf-8")
        cls.styles = (ROOT / "dashboard/styles.css").read_text(encoding="utf-8")
        cls.index = (ROOT / "dashboard/index.html").read_text(encoding="utf-8")
        cls.server = (ROOT / "dashboard/server.py").read_text(encoding="utf-8")
        cls.filter_multiselect = (ROOT / "dashboard/filter-multiselect.js").read_text(
            encoding="utf-8"
        )

    def test_overview_renders_volume_box_plots_and_monthly_kpi_microbars(self) -> None:
        self.assertIn("function volumeBoxPlotCard", self.source)
        self.assertIn('"Actual volume",\n          volumeDistributions.actual', self.source)
        self.assertIn('"Forecast volume",\n          volumeDistributions.forecast', self.source)
        self.assertIn("const wape = finite(metrics.wape_pct)", self.source)
        self.assertIn("function overviewPrimaryRows", self.source)
        self.assertIn("function kpiMicroBars", self.source)
        self.assertIn(".filter((row) => row.actual_denominator_kl > 0)", self.source)
        self.assertIn("function overviewKpiBarCard", self.source)
        for field in (
            'field: "bias_pct"',
            'field: "wape_pct"',
            'field: "revision_effectiveness_pct"',
            'field: "absolute_error_numerator_kl"',
        ):
            self.assertIn(field, self.source)
        self.assertIn("signed: true", self.source)
        self.assertIn('class="kpi-microchart__zero"', self.source)
        self.assertIn(".kpi-micro__summary {", self.styles)
        self.assertIn(".kpi-micro__label .kpi-guide-trigger", self.styles)
        self.assertIn(".kpi-microchart__bar.is-latest", self.styles)
        self.assertNotIn(">WAPE ${escapeHtml(pct(wape))}</text>", self.source)
        self.assertNotIn('"MAE"', self.source)

    def test_overview_uses_one_kpi_row_and_scales_charts_into_freed_height(self) -> None:
        self.assertNotIn('kpi(\n          "Absolute error"', self.source)
        self.assertNotIn('kpi(\n          "Coverage"', self.source)
        self.assertIn("function overviewChartHeight", self.source)
        self.assertIn("overviewChartHeight(performanceChart)", self.source)
        self.assertIn("overviewChartHeight(volumeChart)", self.source)
        self.assertIn('viewBox="0 0 ${width} ${height}"', self.source)

    def test_forecast_vs_actual_month_tooltip_exposes_shared_values(self) -> None:
        self.assertIn('data-tooltip-kind="volume"', self.source)
        self.assertIn('class="chart__month-hit chart__point chart__volume-hit"', self.source)
        self.assertIn("Vintage A forecast</dt>", self.source)
        self.assertIn("Vintage B forecast</dt>", self.source)
        self.assertIn("Actual</dt>", self.source)
        self.assertIn("Latest − actual</dt>", self.source)
        self.assertIn("data-tooltip-volume-series", self.source)
        self.assertIn("data-tooltip-variance", self.source)

    def test_forecast_vs_actual_palette_is_stable_across_filter_renders(self) -> None:
        self.assertIn("--series-actual: #1e3a8a", self.styles)
        self.assertIn("--series-vintage-a: #d6b98c", self.styles)
        self.assertIn("--series-vintage-b: #15803d", self.styles)
        self.assertIn(
            ".chart--overview-volume .chart__series--vintage-a",
            self.styles,
        )
        self.assertIn("stroke-dasharray: 13 8", self.styles)
        self.assertIn(".chart-tooltip {\n  position: fixed;\n  z-index: 60;", self.styles)
        self.assertIn("function accuracyVintageSeriesColor", self.source)
        self.assertIn("accuracyVintageSeriesColor(series, vintagePayload)", self.source)
        self.assertIn("payload.accuracy_vintages", self.source)
        self.assertGreaterEqual(self.source.count("accuracyVintageSeriesColor("), 4)
        self.assertIn('data-volume-role="forecast"', self.source)
        self.assertIn('data-volume-role="actual"', self.source)
        self.assertIn("data-volume-chart-legend", self.index)
        self.assertIn(".frame__head--volume > .legend", self.styles)

    def test_fullscreen_chart_tooltip_uses_the_shared_tooltip_layer(self) -> None:
        self.assertIn('document.addEventListener("pointerover"', self.source)
        self.assertIn('event.target.closest?.(".chart__point")', self.source)
        self.assertIn("showChartTooltip(point, event)", self.source)
        self.assertIn("chartTooltip.id = \"active-chart-tooltip\"", self.source)
        self.assertIn("z-index: 60", self.styles)

    def test_trend_accuracy_reuses_the_exact_overview_chart_spec(self) -> None:
        self.assertIn("function renderTrendMonthlyChart(payload)", self.source)
        self.assertIn('monthlyMetric === "forecast_accuracy_pct"', self.source)
        self.assertIn("title.textContent = chartDialogContent.accuracy.title", self.source)
        self.assertIn("setHtml(legend, accuracyVintageLegend(payload))", self.source)
        self.assertIn("overviewPerformanceChart(monthly.rows", self.source)
        self.assertIn("height: overviewChartHeight(chartContainer)", self.source)
        self.assertIn("[data-trend-chart]", self.source)
        self.assertIn(".trend-main .chart--overview", self.styles)

    def test_overview_charts_hide_months_without_selected_vintage_cohort_data(
        self,
    ) -> None:
        accuracy_chart = self.source[
            self.source.index("  function overviewPerformanceChart(") : self.source.index(
                "  function overviewVolumeChart("
            )
        ]
        volume_chart = self.source[
            self.source.index("  function overviewVolumeChart(") : self.source.index(
                "  function lineChart("
            )
        ]
        trend_chart = self.source[
            self.source.index("  function renderTrendMonthlyChart(") : self.source.index(
                "  function renderTrends("
            )
        ]

        self.assertIn("function overviewApplicableMonths", self.source)
        self.assertIn("hideUnavailableMonths: true", self.source)
        self.assertIn("overviewApplicableMonths(vintagePayload)", accuracy_chart)
        self.assertIn("applicableMonthSet.has(row.snop_month)", accuracy_chart)
        self.assertIn("overviewApplicableMonths(vintagePayload)", volume_chart)
        self.assertIn("applicableMonthSet.has(row.snop_month)", volume_chart)
        self.assertNotIn("hideUnavailableMonths: true", trend_chart)

    def test_timeline_all_preset_stops_at_latest_completed_month(self) -> None:
        preset = self.source[
            self.source.index("  function applyTimelinePreset(") : self.source.index(
                "  function syncControls("
            )
        ]

        self.assertIn("latest_completed_target_month", preset)
        self.assertIn("ForecastTimeline.clampRange", preset)

    def test_accuracy_selector_requests_common_cohort_series(self) -> None:
        build_request = self.source[
            self.source.index("  function buildRequest()") : self.source.index(
                "  function updateFilterCount()"
            )
        ]
        selector_change = self.source[
            self.source.index(
                '  document.addEventListener("change", (event) => {'
            ) : self.source.index(
                '  document\n    .querySelector("[data-exception-limit]")'
            )
        ]
        accuracy_chart = self.source[
            self.source.index("  function overviewPerformanceChart(") : self.source.index(
                "  function overviewVolumeChart("
            )
        ]

        self.assertIn("accuracy_vintage_ids: requestedAccuracyVintageIds()", build_request)
        self.assertIn('event.target.matches?.("[data-vintage-option]")', selector_change)
        self.assertIn(
            "scheduleRefresh({ immediate: true, closeSelector: false })",
            selector_change,
        )
        self.assertIn("closeSelector = true", self.source)
        self.assertIn("if (closeSelector) closeVintageSelector();", self.source)
        self.assertNotIn("renderAccuracyVintageCharts()", selector_change)
        self.assertIn("option.selected", self.source)
        self.assertIn('jsonRequest("api/view/compact"', self.source)
        self.assertIn("closeVintageSelector();", self.source)
        self.assertIn('"accuracy_vintage_ids",', self.source)
        self.assertIn("eligible_parents", accuracy_chart)
        self.assertIn("actual_denominator_kl", accuracy_chart)
        self.assertIn("data-tooltip-common-cohort", accuracy_chart)
        self.assertIn("data-tooltip-actual-denominator", accuracy_chart)
        self.assertNotIn("selectedAccuracyVintages", self.source)
        self.assertNotIn("accuracyVintageSignature", self.source)
        self.assertNotIn("accuracyVintageSelectionInitialized", self.source)
        self.assertNotIn(
            "metrics.accuracy_numerator_kl /",
            self.source,
        )

    def test_overview_kpis_use_accuracy_chart_common_cohort_projection(self) -> None:
        overview = self.source[
            self.source.index("  function renderOverview(payload)") : self.source.index(
                "  function chartExtent("
            )
        ]
        accumulated = self.source[
            self.source.index("  function errorAccumulatedSeries(payload)") : self.source.index(
                "  function renderOverview(payload)"
            )
        ]

        self.assertIn("payload.accuracy_vintages?.overview", overview)
        self.assertIn("const metrics = cohortOverview?.metrics || payload.metrics", overview)
        self.assertIn("cohortOverview?.volume_distributions", overview)
        self.assertIn("payload.volume_distributions", overview)
        self.assertIn("cohortOverview?.primary?.label", overview)
        self.assertIn("payload.accuracy_vintages?.overview", accumulated)
        self.assertIn("metrics.primary_error_kl", accumulated)
        self.assertIn("metrics.latest_error_kl", accumulated)
        self.assertNotIn("vintages.options || []", accumulated)

    def test_accuracy_chart_exposes_local_multi_vintage_selector(self) -> None:
        accuracy_start = self.index.index('id="overview-chart-title"')
        accuracy_end = self.index.index('id="volume-chart-title"')
        accuracy = self.index[accuracy_start:accuracy_end]

        self.assertIn("data-vintage-selector-trigger", accuracy)
        self.assertIn("data-vintage-selector-count", accuracy)
        self.assertLess(
            accuracy.index("data-vintage-selector-trigger"),
            accuracy.index('data-chart-fullscreen="accuracy"'),
        )
        self.assertEqual(self.index.count("data-vintage-selector-trigger"), 2)
        self.assertIn("function syncAccuracyVintageSelection", self.source)
        self.assertIn("function requestedAccuracyVintageIds", self.source)
        self.assertIn("function accuracyVintageSeries", self.source)
        self.assertIn("Latest forecast fixed", self.source)
        self.assertIn('data-vintage-fixed="${isLatest}"', self.source)
        self.assertIn("data-vintage-option", self.source)
        self.assertIn("option.selected", self.source)
        self.assertIn(".vintage-selector__trigger {", self.styles)
        self.assertIn(".vintage-selector {", self.styles)
        self.assertIn(".vintage-selector__option {", self.styles)

    def test_overview_axis_labels_have_clear_line_spacing_without_bias_caption(self) -> None:
        self.assertNotIn('class="chart__section-label"', self.source)
        self.assertEqual(self.source.count('class="chart__axis-year" x="${x(month)}" dy="16"'), 2)

    def test_overview_volume_axis_uses_absolute_whole_kl_values(self) -> None:
        self.assertIn("const OVERVIEW_VOLUME_Y_MIN_KL = 1600", self.source)
        self.assertIn("const OVERVIEW_VOLUME_Y_MAX_KL = 4500", self.source)
        self.assertIn(
            "return [OVERVIEW_VOLUME_Y_MIN_KL, OVERVIEW_VOLUME_Y_MAX_KL]",
            self.source,
        )
        self.assertIn("number(value, 0)", self.source)
        self.assertNotIn("number(value / 1000, 1)", self.source)
        self.assertIn(">KL</text><g class=\"chart__grid chart__grid--volume\"", self.source)
        self.assertNotIn(">'000 KL</text>", self.source)

    def test_overview_and_workbench_share_product_and_time_controls(self) -> None:
        overview_start = self.index.index('id="pane-overview"')
        overview_end = self.index.index('class="kpis kpis--overview"')
        quick_row = self.index[overview_start:overview_end]
        workbench_start = self.index.index('id="scope-drawer"')
        workbench_end = self.index.index('class="state-banner"')
        workbench = self.index[workbench_start:workbench_end]

        self.assertIn('class="overview-health quick-filter-row"', quick_row)
        self.assertEqual(self.index.count("data-product-filter="), 6)
        for name in ("parent_codes", "brands", "sku_classes"):
            selector = f'data-product-filter="{name}"'
            self.assertIn(selector, quick_row)
            self.assertIn(selector, workbench)
        self.assertIn("<legend>Product &amp; period</legend>", workbench)
        self.assertEqual(self.index.count("data-timeline-control"), 2)
        self.assertIn("data-timeline-control", quick_row)
        self.assertIn("data-timeline-control", workbench)
        self.assertIn('data-control="horizon"', workbench)
        self.assertIn('data-control="minimum_actual_volume"', workbench)
        self.assertIn("data-timeline-start-select", workbench)
        self.assertIn("data-timeline-end-select", workbench)
        self.assertNotIn('class="overview-health__facts"', quick_row)
        self.assertNotIn("data-population></div>", quick_row)
        self.assertIn('<script src="filter-multiselect.js"></script>', self.index)
        self.assertIn("grid-template-columns:", self.styles)
        self.assertIn(".quick-filter-row {", self.styles)
        self.assertIn("white-space: nowrap", self.styles)
        self.assertIn(".quick-timeline {", self.styles)
        self.assertIn("height: 3px;", self.styles)
        self.assertIn(
            "linear-gradient(var(--teal), var(--teal)) center / 2px 14px no-repeat;",
            self.styles,
        )
        self.assertIn("width: 20px;", self.styles)
        self.assertIn("left: -10px;", self.styles)
        self.assertIn("width: calc(100% + 20px);", self.styles)
        self.assertIn("box-shadow: none;", self.styles)
        self.assertIn("FilterMultiSelect.create", self.source)
        self.assertIn('brands: productFilterValue("brands")', self.source)
        self.assertIn('sku_classes: productFilterValue("sku_classes")', self.source)
        self.assertIn('parent_codes: productFilterValue("parent_codes")', self.source)
        self.assertIn('horizon: numeric("horizon")', self.source)
        self.assertIn('minimum_actual_volume: numeric("minimum_actual_volume") ?? 0', self.source)
        self.assertIn("candidate.setValue(selected)", self.source)
        self.assertIn("timelines.forEach", self.source)
        self.assertIn(".filter-multiselect__popover {", self.styles)
        self.assertIn(".filter-multiselect__option {", self.styles)
        self.assertIn('aria-disabled="${isDisabled}"', self.filter_multiselect)
        self.assertIn("option.disabled", self.filter_multiselect)
        self.assertIn("options.product_availability", self.source)
        self.assertIn("disabled: !availableBrands.has(value)", self.source)
        self.assertIn("disabled: !availableSkuClasses.has(value)", self.source)
        self.assertIn("filter_adjustments", self.source)
        self.assertIn('removed_product_selections', self.source)
        self.assertIn('["parent_codes", "Parent product"]', self.source)

    def test_revision_scatter_has_local_sku_class_filter_and_full_default_viewbox(self) -> None:
        scatter = self.source[
            self.source.index("  function scatterChart(") : self.source.index(
                "  function pairedScatter("
            )
        ]
        self.assertIn('data-scatter-sku-class', self.source)
        self.assertIn('revisionScatterSkuClass', self.source)
        self.assertIn('data-tooltip-sku-class', self.source)
        self.assertIn('let revisionScatterMode = "error";', self.source)
        self.assertIn('"mode-error", "Error"', self.source)
        self.assertIn('aria-label="Size bubbles by latest-vintage absolute error"', self.source)
        self.assertIn('data-radius-error', self.source)
        self.assertIn('data-tooltip-absolute-error', self.source)
        self.assertIn('Latest-vintage absolute error', self.source)
        self.assertIn('Size by volume / Uniform dots', self.index)
        self.assertNotIn('preserveAspectRatio="none"', scatter)
        self.assertIn('const centerX = baseWidth / 2 + revisionScatterPan.x', self.source)
        self.assertIn('Seasonal extremes retained · six-month median', self.source)
        self.assertIn('six complete target months × five vintages', self.source)
        self.assertNotIn('selected end month · five vintages per month', self.source)
        self.assertNotIn('Winsorized months', self.source)
        self.assertIn('.scatter-toolbar__filter', self.styles)
        self.assertIn('Out of scope · super seasonal:', self.source)
        self.assertIn(
            'PA Bodylot · JFB Powder · RK Cooling · Saff Honey · SP Petroleum Jelly (all SKUs) · PCNO EJ (all matching SKUs)',
            self.source,
        )

    def test_revision_selection_focuses_the_full_scatter_population(self) -> None:
        self.assertIn(
            'revisionScatterSelection.size && revisionDrilldownBasePayload',
            self.source,
        )
        self.assertIn('scatter__point--context', self.source)
        self.assertIn('scatter__point--context', self.styles)
        self.assertIn('Selected parents highlighted · others stay pale for context', self.source)
        self.assertIn('Scatter keeps all parents visible for context', self.source)
        self.assertIn('const uniformRadius = 7.2', self.source)
        self.assertIn('return uniformRadius + Math.sqrt(normalized) * 18.45', self.source)
        self.assertNotIn('click to filter · Shift-click to add', self.source)

    def test_default_source_is_ml(self) -> None:
        index = (ROOT / "dashboard/index.html").read_text(encoding="utf-8")
        adapter = (ROOT / "dashboard/adapter.py").read_text(encoding="utf-8")
        self.assertIn('<option value="ml" selected>ML</option>', index)
        self.assertIn('options = self._filter_options("ml", False)', adapter)
        self.assertIn('"source": "ml"', adapter)
        self.assertIn('raw, "source", default="ml"', adapter)

    def test_comparison_mode_switcher_sits_in_the_page_header(self) -> None:
        comparison_start = self.index.index('id="pane-comparison"')
        comparison_end = self.index.index('id="pane-history"')
        comparison = self.index[comparison_start:comparison_end]

        header_start = comparison.index('class="pane__head pane__head--with-control"')
        header_end = comparison.index('class="subpanel is-active"')
        header = comparison[header_start:header_end]
        self.assertIn('data-subtabs="comparison"', header)
        self.assertIn('class="pane__head-actions"', header)
        self.assertNotIn("explicit analytical modes", comparison.lower())
        self.assertIn(".pane__head-actions .subtabs", self.styles)

    def test_history_controls_and_nonduplicated_context_share_one_row(self) -> None:
        history_start = self.index.index('id="pane-history"')
        history_end = self.index.index('id="pane-quality"')
        history = self.index[history_start:history_end]

        header_end = history.index('class="subpanel is-active"')
        header = history[:header_end]
        context_start = history.index('class="history-context"')
        context_end = history.index('class="postmortem-metrics"')
        context = history[context_start:context_end]

        self.assertIn('data-subtabs="history"', header)
        self.assertIn('class="pane__head-actions"', header)
        self.assertIn('data-product-summary', context)
        self.assertIn('class="toolbar history-toolbar"', context)
        self.assertLess(
            context.index('class="toolbar history-toolbar"'),
            context.index('data-product-summary'),
        )
        self.assertNotIn('data-product-source', history)
        self.assertIn(".history-context {", self.styles)
        self.assertIn(".history-context .history-toolbar {", self.styles)
        self.assertIn(".history-context .product-summary {", self.styles)
        self.assertNotIn('populationItem("Product", detail.parent_code)', self.source)
        self.assertNotIn(
            'populationItem("Description", detail.parent_description)', self.source
        )
        self.assertNotIn(
            'populationItem("Mapping", labelize(detail.mapping_status))', self.source
        )
        self.assertNotIn(
            'populationItem("Target", monthLabel(detail.target_month))', self.source
        )
        summary_start = self.source.index(
            'document.querySelector("[data-product-summary]")'
        )
        summary_end = self.source.index("renderProductPostmortem(detail)", summary_start)
        summary = self.source[summary_start:summary_end]
        self.assertIn('populationItem("Brand", detail.brand || "Unmapped")', summary)
        self.assertIn(
            'populationItem("SKU class", detail.sku_class || "Unclassified")',
            summary,
        )

    def test_revision_instruction_tags_are_embedded_in_outcome_strip(self) -> None:
        self.assertIn("function revisionOutcomeInstructions", self.source)
        self.assertIn('class="outcome__instructions"', self.source)
        self.assertIn(">Review now</span>", self.source)
        self.assertIn(">Pattern</span>", self.source)
        self.assertIn(">Keep</span>", self.source)
        self.assertNotIn("revisionActionCallouts", self.source)
        self.assertNotIn('class="revision-callouts"', self.source)
        self.assertIn(".outcome__instructions", self.styles)
        self.assertIn("grid-template-columns: minmax(0, 1fr) auto", self.styles)
        self.assertIn(".outcome__content > strong {\n  grid-column: 2;\n  justify-self: end;", self.styles)
        self.assertIn("align-items: flex-start", self.styles)
        self.assertIn("font: 600 8.5px / 1.2 var(--mono)", self.styles)
        self.assertIn("text-align: right", self.styles)
        self.assertNotIn(".revision-callout {", self.styles)

    def test_revision_action_queue_deduplicates_skus_and_renders_error_sparklines(self) -> None:
        self.assertIn("function revisionActionSkuRows()", self.source)
        self.assertIn('actions.sku_rows', self.source)
        self.assertIn('class="revision-queue__sparkline"', self.source)
        self.assertIn('data-tooltip-kind="revision-action-sparkline"', self.source)
        self.assertIn("Error improvement · zero baseline", self.source)
        self.assertIn("Monthly error improvement", self.source)
        self.assertIn("data-tooltip-month", self.source)
        self.assertIn("revision-queue__sparkline", self.styles)
        self.assertIn("grid-template-columns: 0.62fr 1.75fr 1.22fr 0.72fr 0.82fr 1.18fr", self.styles)

    def test_product_history_is_a_dashboard_native_sku_postmortem(self) -> None:
        self.assertIn("SKU post-mortem", self.index)
        self.assertNotIn("data-postmortem-decision", self.index)
        self.assertIn("data-postmortem-metrics", self.index)
        self.assertIn("data-postmortem-performance-chart", self.index)
        self.assertIn("data-postmortem-revision-chart", self.index)
        self.assertIn("data-postmortem-peers", self.index)
        self.assertNotIn("data-postmortem-commentary", self.index)
        self.assertNotIn("data-postmortem-evidence", self.index)
        self.assertNotIn("data-postmortem-treatment", self.index)
        self.assertIn('data-chart-fullscreen="postmortem-performance"', self.index)
        self.assertIn('data-chart-fullscreen="postmortem-revision"', self.index)
        self.assertNotIn('data-chart-fullscreen="product-history"', self.index)
        self.assertIn('"postmortem-performance": {', self.source)
        self.assertIn('"postmortem-revision": {', self.source)
        self.assertNotIn('"product-history": {', self.source)
        self.assertIn("function renderProductPostmortem", self.source)
        self.assertIn("Actual demand + forward outlook", self.index)
        self.assertIn("data-year-overlay-summary", self.index)
        self.assertIn("data-year-overlay-legend", self.index)
        self.assertIn("function productYearOverlayChart", self.source)
        self.assertIn("function yearOverlayLegend", self.source)
        self.assertIn("function toggleYearOverlay", self.source)
        self.assertIn("function resetYearOverlay", self.source)
        self.assertIn("function productLongHorizonChart", self.source)
        self.assertIn("function financialYearLabel", self.source)
        self.assertIn('data-year-overlay-mode="long"', self.source)
        self.assertIn("FINANCIAL_MONTH_NAMES", self.source)
        self.assertIn('data-year-overlay-year="${year}"', self.source)
        self.assertIn("data-year-overlay-reset", self.source)
        self.assertIn('data-tooltip-kind="year-overlay"', self.source)
        self.assertIn('data-tooltip-year-series', self.source)
        self.assertIn('label: "Forecast run"', self.source)
        self.assertIn('label: "FY"', self.source)
        self.assertIn('yearOverlayPath(forecast, x, y, "forecast", color)', self.source)
        self.assertIn("year-overlay-fy-separator", self.styles)
        self.assertIn("fiscal_year", self.source)
        self.assertIn('aria-label="Actual demand and forward forecast by FY"', self.source)
        self.assertIn(".year-overlay-month-hit", self.styles)
        self.assertIn(".year-overlay-path.forecast", self.styles)
        self.assertIn("stroke-dasharray: 7 5", self.styles)
        self.assertIn(".year-overlay-control.is-off", self.styles)
        self.assertIn(".chart--overview .chart__month-hit:not(.chart__volume-hit)", self.source)
        self.assertIn("function productRevisionOutcomeChart", self.source)
        self.assertIn("function baselineAdjustment", self.source)
        self.assertIn('data-baseline-adjustment', self.source)
        self.assertIn("function treatmentReviewLabel", self.source)
        self.assertNotIn("function productCommentary", self.source)
        self.assertIn("function productPeerBenchmark", self.source)
        self.assertNotIn("function historyChart", self.source)
        self.assertNotIn("Selected target · forecast development", self.index)
        self.assertIn("Error improvement · zero baseline", self.index)
        self.assertIn("postmortem-revision-chart__point--improved", self.styles)
        self.assertIn("postmortem-revision-chart__point--worsened", self.styles)
        self.assertIn("var(--display)", self.styles)
        self.assertIn("var(--mono)", self.styles)
        self.assertNotIn("linear-gradient", self.index[self.index.index('id=\"pane-history\"'):self.index.index('id=\"pane-quality\"')])

    def test_revision_history_is_stepped_effectiveness_evolution_with_overlay(self) -> None:
        self.assertIn("function revisionHistoryChart(history)", self.source)
        self.assertIn("function effectivenessScoreTone(score)", self.source)
        self.assertIn("function effectivenessScoreLabel(score)", self.source)
        self.assertIn("function revisionEffectivenessOverlay(month, point)", self.source)
        self.assertIn("function openRevisionEffectiveness(month, point, trigger)", self.source)
        self.assertIn("function closeRevisionEffectiveness", self.source)
        self.assertIn("function openRevisionEffectivenessPoint", self.source)
        self.assertIn("function revisionEffectivenessGuideButton", self.source)
        self.assertIn("function openRevisionEffectivenessGuide", self.source)
        self.assertIn("function closeRevisionEffectivenessGuide", self.source)
        self.assertIn("const width = 720", self.source)
        self.assertIn("const height = 300", self.source)
        self.assertIn('class="revision-history__band"', self.source)
        self.assertIn('data-target-month=', self.source)
        self.assertIn("H ${current.x} V ${current.y}", self.source)
        self.assertIn('class="chart__point revision-history__point', self.source)
        self.assertIn('data-tooltip-kind="revision-effectiveness"', self.source)
        self.assertIn(
            'data-tooltip-kind="revision-effectiveness-segment"', self.source
        )
        self.assertIn("revision-history__node--${tone}", self.source)
        self.assertIn("Balanced revision effectiveness score", self.source)
        self.assertIn("Each month resets at V1", self.source)
        self.assertIn("Click any vintage for the breakdown", self.source)
        self.assertIn("Revision effectiveness evolution", self.source)
        self.assertIn('revisionFullscreenMenu("revision-history", "scatter")', self.source)
        self.assertIn('"revision-history": {', self.source)
        self.assertIn("revisionHistoryChart(payload.revision_history)", self.source)
        self.assertIn('id="revision-effectiveness-dialog"', self.index)
        self.assertIn("data-effectiveness-body", self.index)
        self.assertIn('data-action="revision-effectiveness-close"', self.index)
        self.assertIn('id="revision-effectiveness-guide-dialog"', self.index)
        self.assertIn(
            'data-action="revision-effectiveness-guide-open"', self.source
        )
        self.assertIn(
            'data-action="revision-effectiveness-guide-close"', self.index
        )
        self.assertIn("Two related measures, two different questions", self.index)
        self.assertIn("Three ingredients build the score", self.index)
        self.assertIn("With the forecasting team", self.index)
        self.assertIn("With the business team", self.index)
        self.assertIn(".chart-guide-trigger", self.styles)
        self.assertIn(".revision-effectiveness-guide-dialog", self.styles)
        self.assertIn("overflow: hidden", self.styles)
        self.assertIn(".revision-history__point", self.styles)
        self.assertIn(".revision-history__baseline", self.styles)
        self.assertIn(".revision-history__separator", self.styles)
        self.assertIn(".revision-history__segment--improved", self.styles)
        self.assertIn(".revision-history__segment--worsened", self.styles)
        self.assertIn(".revision-history__segment--neutral", self.styles)
        self.assertIn(".revision-effectiveness-dialog", self.styles)
        self.assertIn(".revision-effectiveness__summary", self.styles)
        self.assertIn(".revision-effectiveness__metrics", self.styles)
        self.assertNotIn("function revisionTable(rows)", self.source)
        self.assertNotIn("<b>Outcome</b><strong>Rows</strong>", self.source)
        self.assertNotIn('data-interpolation="linear"', self.source)

    def test_comparison_scatter_and_kpis_use_full_canvas_explainers(self) -> None:
        self.assertIn("function revisionScatterGuideButton", self.source)
        self.assertIn("function openRevisionScatterGuide", self.source)
        self.assertIn("function closeRevisionScatterGuide", self.source)
        self.assertIn('data-action="revision-scatter-guide-open"', self.source)
        self.assertIn('id="revision-scatter-guide-dialog"', self.index)
        self.assertIn('data-action="revision-scatter-guide-close"', self.index)
        self.assertIn("Start with the two axes", self.index)
        self.assertIn("How one bubble is calculated", self.index)
        self.assertIn("Use the controls intentionally", self.index)
        self.assertIn("Heatmap = concentration, not performance", self.index)
        self.assertIn("14 × 8 cells", self.index)
        self.assertIn("counts", self.index)
        self.assertIn("parents, not KL or impact", self.index)
        self.assertIn("heatmap as population context", self.index)
        self.assertIn(".scatter-guide__body", self.styles)
        self.assertIn(".scatter-guide__quadrant", self.styles)
        self.assertIn(".scatter-guide__heat-cells", self.styles)
        self.assertIn(".scatter-guide__heatmap-scale", self.styles)
        self.assertIn(".chart-dialog-pair__title-row", self.styles)

        self.assertIn("function comparisonKpiGuideButton", self.source)
        self.assertIn("function openComparisonKpiGuide", self.source)
        self.assertIn("function closeComparisonKpiGuide", self.source)
        self.assertIn('data-action="comparison-kpi-guide-open"', self.source)
        self.assertIn('id="comparison-kpi-guide-dialog"', self.index)
        self.assertIn('data-comparison-kpi-guide="accuracy-delta"', self.index)
        self.assertIn('data-comparison-kpi-guide="effectiveness"', self.index)
        self.assertIn('data-comparison-kpi-guide="error-improvement"', self.index)
        self.assertIn("How to read vintage accuracy delta", self.source)
        self.assertIn("How to read revision effectiveness", self.source)
        self.assertIn("How to read total error improvement", self.source)
        self.assertIn("Always triangulate", self.index)
        self.assertIn("all three cards", self.index)
        self.assertIn(".kpi-guide-trigger", self.styles)
        self.assertIn(".comparison-kpi-guide__body", self.styles)
        self.assertIn(".comparison-kpi-guide__equation", self.styles)

    def test_monthly_accuracy_chart_has_wape_gap_driver_overlay(self) -> None:
        self.assertIn('id="vintage-gap-dialog"', self.index)
        self.assertIn("data-vintage-gap-body", self.index)
        self.assertIn('data-action="vintage-gap-close"', self.index)
        self.assertIn("function openVintageGapDrilldown(point)", self.source)
        self.assertIn("function renderVintageGapDrilldown()", self.source)
        self.assertIn("function closeVintageGapDrilldown", self.source)
        self.assertIn("function openVintageGapProduct(parentCode)", self.source)
        self.assertIn('data-target-month="${escapeHtml(row.snop_month)}"', self.source)
        self.assertIn('data-vintage-gap-enabled="${activePayload.options.some', self.source)
        self.assertIn("Click for WAPE gap drivers", self.source)
        self.assertIn("Select a historical vintage to see WAPE gap drivers", self.source)
        self.assertIn('data-vintage-gap-mode="fixes"', self.source)
        self.assertIn('data-vintage-gap-mode="regressions"', self.source)
        self.assertIn("data-vintage-gap-brand", self.source)
        self.assertIn("data-vintage-gap-parent", self.source)
        self.assertIn("data-vintage-gap-show-all", self.source)
        self.assertIn("data-vintage-gap-brand-search", self.source)
        self.assertIn("data-vintage-gap-parent-search", self.source)
        self.assertIn("data-vintage-gap-open-product", self.source)
        self.assertIn('activate("history", { historyMode: "push" })', self.source)
        self.assertIn('"api/vintage-gap-drilldown"', self.source)
        self.assertIn('path == "/api/vintage-gap-drilldown"', self.server)
        self.assertIn(".vintage-gap-dialog", self.styles)
        self.assertIn(".vintage-gap__summary", self.styles)
        self.assertIn(".vintage-gap__workspace", self.styles)
        self.assertIn(".vintage-gap__brand-list", self.styles)
        self.assertIn(".vintage-gap__parent-list", self.styles)
        self.assertIn(".vintage-gap__parent-detail", self.styles)

    def test_overview_kpis_and_charts_use_full_canvas_explainers(self) -> None:
        self.assertIn("function overviewGuideButton", self.source)
        self.assertIn("function openOverviewGuide", self.source)
        self.assertIn("function closeOverviewGuide", self.source)
        self.assertIn('data-action="overview-guide-open"', self.source)
        self.assertIn('data-action="overview-guide-close"', self.index)
        self.assertIn('id="overview-guide-dialog"', self.index)
        for guide_key in (
            "accuracy",
            "bias",
            "actual-volume",
            "forecast-volume",
            "wape",
            "effectiveness",
            "error-accumulated",
            "accuracy-chart",
            "volume-chart",
        ):
            self.assertIn(f'data-overview-guide="{guide_key}"', self.index)
        self.assertIn('"accuracy-chart": {', self.source)
        self.assertIn('"volume-chart": {', self.source)
        self.assertIn('"error-accumulated": {', self.source)
        self.assertIn('errorAccumulatedCard(payload, kpiRows),', self.source)
        self.assertIn('label: "Error accumulated",', self.source)
        self.assertIn("function renderErrorAccumulatedGuide", self.source)
        self.assertIn("Every shaded gap becomes part of the total", self.source)
        self.assertIn("First, measure the gap each month", self.index)
        self.assertIn("Continuous shaded space between forecast and actual", self.index)
        self.assertIn("data-error-accumulated-months", self.index)
        self.assertIn("error-accumulated-guide__chart", self.styles)
        self.assertIn("error-accumulated-guide__month-errors", self.styles)
        self.assertIn('overviewGuideButton(\n                fullscreenTitle,', self.source)
        self.assertIn("Read it as 100% minus the error burden", self.index)
        self.assertIn("One shared cohort, recomputed", self.index)
        self.assertIn("data-bias-guide-lanes", self.index)
        self.assertIn("Each signed bracket is", self.index)
        self.assertIn("function renderBiasGuide", self.source)
        self.assertIn("One observation is one month", self.index)
        self.assertIn("One shared scale, two boxes", self.index)
        self.assertIn("Actual volume with the forecast laid over it", self.index)
        self.assertIn("Each bracket is", self.index)
        self.assertIn("data-wape-guide-lanes", self.index)
        self.assertIn("function renderWapeGuide", self.source)
        self.assertIn(".wape-guide__bracket", self.styles)
        self.assertIn("Read it as a hit rate", self.index)
        self.assertIn("Read every selected line", self.index)
        self.assertIn("Bias uses the KPI vintage on this same cohort", self.index)
        self.assertNotIn("Lines and bias bars use different parent sets", self.index)
        self.assertIn(".has-overview-guide-dialog", self.styles)
        self.assertIn(".overview-guide__boxes", self.styles)
        self.assertIn(".overview-guide__micro", self.styles)

    def test_normal_filter_flow_uses_compact_and_lazy_module_endpoints(self) -> None:
        self.assertIn('jsonRequest("api/view/compact"', self.source)
        self.assertIn("jsonRequest(`api/module/${moduleName}`", self.source)
        self.assertNotIn('jsonRequest("api/view"', self.source)
        self.assertIn('trends: ["trends"]', self.source)
        self.assertIn('heatmap: ["trends"]', self.source)
        self.assertIn('product: ["history"]', self.source)

    def test_request_owner_aborts_and_rejects_stale_module_merges(self) -> None:
        self.assertIn("new AbortController()", self.source)
        self.assertIn("compactController?.abort()", self.source)
        self.assertIn("pending?.controller.abort()", self.source)
        self.assertIn("generation !== requestGeneration", self.source)
        self.assertIn("payload.meta?.dataset_version", self.source)
        self.assertIn("requestKey(payload.request) === expected", self.source)

    def test_discrete_controls_dispatch_immediately_and_inputs_are_debounced(self) -> None:
        self.assertIn("const INPUT_DEBOUNCE_MS = 160", self.source)
        self.assertIn("scheduleRefresh({\n        immediate: !control.matches", self.source)
        self.assertIn('control.addEventListener("input"', self.source)
        self.assertNotIn("setTimeout(() => refreshView({ announce: true }), 220)", self.source)


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
