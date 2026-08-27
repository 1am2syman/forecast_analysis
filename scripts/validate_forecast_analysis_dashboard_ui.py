"""Validate deterministic live-browser evidence for the forecast dashboard UI.

The dashboard analysis is intentionally outside this module.  This verifier
checks the capture contract: immutable PNG identity, raw browser state,
Marimo full-page normalization actions, screenshot dimensions and content, and
independent document/application horizontal-overflow results.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
import zlib
from pathlib import Path
from typing import Any, Iterator, Mapping

SCHEMA_VERSION = 2
CAPTURE_CONTRACT = "forecast-analysis-dashboard-ui-baseline-v1"
NORMALIZATION_CONTRACT = "marimo-full-page-normalization-v1"
WORKFLOW_VERSION = "forecast-dashboard-live-capture-v1"
OVERFLOW_TOLERANCE_PX = 2
IMMUTABLE_BASELINE_RELATIVE_PATH = Path(
    "validation-artifacts/forecast-analysis-dashboard-long-full.png"
)
IMMUTABLE_BASELINE_SHA256 = (
    "29cd5651eadfec811b1c0671786f4a807dc846e1c59f9b5bddfab17e7261dfdd"
)
CAPTURE_ARTIFACT_RELATIVE_PATH = Path(
    "validation-artifacts/forecast-analysis-dashboard-ui-baseline.json"
)
MIN_APP_TEXT_LENGTH = 100
MIN_MEANINGFUL_ACTIVE_BANDS = 6
MIN_LAST_BAND_CONTENT_RATIO = 0.02
MIN_STATE_DIFFERENCE_RATIO = 0.0005


class CaptureValidationError(ValueError):
    """Raised when a browser capture artifact violates its contract."""


def sha256_file(path: Path) -> str:
    """Return the SHA256 digest of a file without loading it all at once."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_dimensions(path: Path) -> tuple[int, int]:
    """Read width and height from a PNG signature and IHDR chunk."""
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise CaptureValidationError(f"not a PNG file: {path}")
    chunk_length = struct.unpack(">I", header[8:12])[0]
    if header[12:16] != b"IHDR" or chunk_length < 8:
        raise CaptureValidationError(f"PNG has no usable IHDR chunk: {path}")
    width, height = struct.unpack(">II", header[16:24])
    if width == 0 or height == 0:
        raise CaptureValidationError(f"PNG has zero dimensions: {path}")
    return width, height


def _png_scanlines(path: Path) -> tuple[int, int, int, bytes]:
    """Return PNG dimensions, bytes-per-pixel, and decompressed scanlines."""
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise CaptureValidationError(f"could not read PNG: {path}") from exc
    if payload[:8] != b"\x89PNG\r\n\x1a\n":
        raise CaptureValidationError(f"not a PNG file: {path}")
    width = height = bit_depth = color_type = interlace = None
    compressed = bytearray()
    offset = 8
    while offset + 12 <= len(payload):
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        chunk_type = payload[offset + 4 : offset + 8]
        chunk_end = offset + 12 + length
        if chunk_end > len(payload):
            raise CaptureValidationError(f"truncated PNG chunk: {path}")
        chunk = payload[offset + 8 : offset + 8 + length]
        if chunk_type == b"IHDR":
            if len(chunk) != 13:
                raise CaptureValidationError(f"malformed PNG IHDR: {path}")
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(
                ">IIBBBBB", chunk
            )
        elif chunk_type == b"IDAT":
            compressed.extend(chunk)
        elif chunk_type == b"IEND":
            break
        offset = chunk_end
    if width is None or height is None or bit_depth is None or color_type is None or interlace is None:
        raise CaptureValidationError(f"PNG is missing IHDR: {path}")
    if bit_depth != 8 or interlace != 0 or color_type not in (0, 2, 4, 6):
        raise CaptureValidationError(
            f"unsupported PNG encoding in {path}: bit_depth={bit_depth}, "
            f"color_type={color_type}, interlace={interlace}"
        )
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[color_type]
    try:
        scanlines = zlib.decompress(bytes(compressed))
    except zlib.error as exc:
        raise CaptureValidationError(f"PNG IDAT data is invalid: {path}") from exc
    expected = height * (1 + width * channels)
    if len(scanlines) != expected:
        raise CaptureValidationError(
            f"PNG scanline length does not match dimensions: {path} "
            f"({len(scanlines)} != {expected})"
        )
    return width, height, channels, scanlines


def _paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    left_distance = abs(estimate - left)
    above_distance = abs(estimate - above)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= above_distance and left_distance <= upper_left_distance:
        return left
    if above_distance <= upper_left_distance:
        return above
    return upper_left


def _rgb_rows(path: Path, samples_per_row: int = 160) -> Iterator[tuple[int, bytes]]:
    """Yield sampled RGB bytes for each decoded PNG row."""
    width, height, channels, scanlines = _png_scanlines(path)
    stride = width * channels
    previous = bytearray(stride)
    offset = 0
    sample_step = max(1, width // samples_per_row)
    for row_index in range(height):
        filter_type = scanlines[offset]
        filtered = scanlines[offset + 1 : offset + 1 + stride]
        offset += stride + 1
        row = bytearray(stride)
        for index, value in enumerate(filtered):
            left = row[index - channels] if index >= channels else 0
            above = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) // 2
            elif filter_type == 4:
                predictor = _paeth(left, above, upper_left)
            else:
                raise CaptureValidationError(
                    f"unsupported PNG filter {filter_type} in {path}"
                )
            row[index] = (value + predictor) & 0xFF
        sampled = bytearray()
        for x in range(0, width, sample_step):
            pixel = row[x * channels : (x + 1) * channels]
            if channels == 1:
                sampled.extend((pixel[0], pixel[0], pixel[0]))
            elif channels == 2:
                sampled.extend((pixel[0], pixel[0], pixel[0]))
            else:
                sampled.extend(pixel[:3])
        yield row_index, bytes(sampled)
        previous = row


def png_content_evidence(path: Path) -> dict[str, Any]:
    """Recompute bounded, pixel-based evidence that a PNG contains full content."""
    width, height = png_dimensions(path)
    band_count = 8
    bands = [
        {
            "index": index,
            "start_row": height * index // band_count,
            "end_row": height * (index + 1) // band_count,
            "sampled_rows": 0,
            "sampled_pixels": 0,
            "non_background_pixels": 0,
            "distinct_colors": set(),
            "digest": hashlib.sha256(),
        }
        for index in range(band_count)
    ]
    for row_index, sampled in _rgb_rows(path):
        band = bands[min(row_index * band_count // height, band_count - 1)]
        band["sampled_rows"] += 1
        band["sampled_pixels"] += len(sampled) // 3
        band["digest"].update(sampled)
        for index in range(0, len(sampled), 3):
            rgb = tuple(sampled[index : index + 3])
            if len(rgb) != 3:
                continue
            if min(rgb) < 245 or max(rgb) - min(rgb) > 10:
                band["non_background_pixels"] += 1
            if len(band["distinct_colors"]) < 2048:
                band["distinct_colors"].add(rgb)
    serialized_bands = []
    for band in bands:
        sampled_pixels = band["sampled_pixels"]
        non_background = band["non_background_pixels"]
        if not isinstance(sampled_pixels, int) or not isinstance(non_background, int):
            raise CaptureValidationError("PNG content counters are not integers")
        serialized_bands.append(
            {
                "index": band["index"],
                "start_row": band["start_row"],
                "end_row": band["end_row"],
                "sampled_rows": band["sampled_rows"],
                "sampled_pixels": sampled_pixels,
                "non_background_pixels": non_background,
                "non_background_ratio": (
                    non_background / sampled_pixels if sampled_pixels else 0.0
                ),
                "distinct_colors": len(band["distinct_colors"]),
                "sha256": band["digest"].hexdigest(),
            }
        )
    active_bands = [
        band
        for band in serialized_bands
        if band["non_background_ratio"] >= 0.005 and band["distinct_colors"] >= 2
    ]
    return {
        "width": width,
        "height": height,
        "band_count": band_count,
        "bands": serialized_bands,
        "active_band_count": len(active_bands),
        "last_band_non_background_ratio": serialized_bands[-1]["non_background_ratio"],
        "meaningful": (
            len(active_bands) >= MIN_MEANINGFUL_ACTIVE_BANDS
            and serialized_bands[-1]["non_background_ratio"]
            >= MIN_LAST_BAND_CONTENT_RATIO
        ),
    }


def png_difference_evidence(first: Path, second: Path) -> dict[str, Any]:
    """Compare two PNGs using independent sampled decoded pixels."""
    first_width, first_height = png_dimensions(first)
    second_width, second_height = png_dimensions(second)
    if (first_width, first_height) != (second_width, second_height):
        return {
            "same_dimensions": False,
            "width": [first_width, second_width],
            "height": [first_height, second_height],
            "sampled_pixels": 0,
            "changed_pixels": 0,
            "difference_ratio": 1.0,
        }
    changed = 0
    sampled = 0
    first_rows = _rgb_rows(first)
    second_rows = _rgb_rows(second)
    for (_, first_row), (_, second_row) in zip(first_rows, second_rows):
        if len(first_row) != len(second_row):
            raise CaptureValidationError("PNG row samples have different lengths")
        for index in range(0, len(first_row), 3):
            sampled += 1
            if first_row[index : index + 3] != second_row[index : index + 3]:
                changed += 1
    if sampled == 0:
        raise CaptureValidationError("PNG comparison produced no samples")
    return {
        "same_dimensions": True,
        "width": first_width,
        "height": first_height,
        "sampled_pixels": sampled,
        "changed_pixels": changed,
        "difference_ratio": changed / sampled,
    }


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CaptureValidationError(f"{label} is not numeric")
    try:
        numeric = float(value)
        result = int(value)
    except (OverflowError, ValueError, TypeError) as exc:
        raise CaptureValidationError(f"{label} is not a finite integer") from exc
    if not math.isfinite(numeric) or result != value:
        raise CaptureValidationError(f"{label} is not a finite integer")
    if result < 0:
        raise CaptureValidationError(f"{label} is negative")
    return result


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CaptureValidationError(f"{label} is not an object")
    return value


def _measurement(value: object, label: str) -> dict[str, int]:
    """Normalize a browser client/scroll dimension object."""
    source = _mapping(value, label)
    return {
        "clientWidth": _integer(source.get("clientWidth"), f"{label}.clientWidth"),
        "scrollWidth": _integer(source.get("scrollWidth"), f"{label}.scrollWidth"),
        "clientHeight": _integer(source.get("clientHeight"), f"{label}.clientHeight"),
        "scrollHeight": _integer(source.get("scrollHeight"), f"{label}.scrollHeight"),
    }


def _viewport(value: object, label: str = "viewport") -> dict[str, float | int]:
    source = _mapping(value, label)
    width = _integer(source.get("width"), f"{label}.width")
    height = _integer(source.get("height"), f"{label}.height")
    dpr_value = source.get("devicePixelRatio", 1)
    if isinstance(dpr_value, bool) or not isinstance(dpr_value, (int, float)):
        raise CaptureValidationError(f"{label}.devicePixelRatio is not numeric")
    try:
        dpr = float(dpr_value)
    except (OverflowError, ValueError, TypeError) as exc:
        raise CaptureValidationError(f"{label}.devicePixelRatio is invalid") from exc
    if not math.isfinite(dpr) or dpr <= 0:
        raise CaptureValidationError(f"{label}.devicePixelRatio is invalid")
    return {"width": width, "height": height, "devicePixelRatio": dpr}


def measure_overflow(
    measurement: Mapping[str, object],
    tolerance_px: int = OVERFLOW_TOLERANCE_PX,
) -> dict[str, int | bool]:
    """Measure horizontal overflow for one independently named container."""
    tolerance = _integer(tolerance_px, "tolerance_px")
    normalized = _measurement(measurement, "measurement")
    overflow_px = max(normalized["scrollWidth"] - normalized["clientWidth"], 0)
    passes = normalized["scrollWidth"] <= normalized["clientWidth"] + tolerance
    return {
        "client_width": normalized["clientWidth"],
        "scroll_width": normalized["scrollWidth"],
        "overflow_px": overflow_px,
        "tolerance_px": tolerance,
        "passes": passes,
        "overflows": not passes,
    }


def evaluate_overflow(
    document: Mapping[str, object],
    application: Mapping[str, object],
    tolerance_px: int = OVERFLOW_TOLERANCE_PX,
) -> dict[str, Any]:
    """Evaluate document and application overflow without combining their inputs."""
    tolerance = _integer(tolerance_px, "tolerance_px")
    document_result = measure_overflow(document, tolerance)
    application_result = measure_overflow(application, tolerance)
    return {
        "tolerance_px": tolerance,
        "document": document_result,
        "application": application_result,
        "passes": document_result["passes"] and application_result["passes"],
    }


def normalize_browser_capture(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Extract a stable measurement shape from native agent-browser JSON output."""
    source = _mapping(payload.get("result", payload), "browser result")
    application = source.get("app", source.get("application"))
    document = source.get("document")
    normalized = {
        "origin": payload.get("origin") or source.get("origin"),
        "url": source.get("url"),
        "title": source.get("title"),
        "viewport": _viewport(source.get("viewport")),
        "document": _measurement(document, "document"),
        "application": _measurement(application, "application"),
        "normalized": bool(source.get("normalized", False)),
    }
    if "normalization_contract" in source:
        normalized["normalization_contract"] = source["normalization_contract"]
    if "normalizationContract" in source:
        normalized["normalization_contract"] = source["normalizationContract"]
    if "state" in source:
        normalized["state"] = source["state"]
    if "body" in source:
        normalized["body"] = _measurement(source["body"], "body")
    if "expandedAria" in source:
        normalized["expanded_aria"] = source["expandedAria"]
    return normalized


def _resolve_path(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise CaptureValidationError(f"{label} path is missing")
    path = Path(value)
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise CaptureValidationError(
            f"{label} must be repository-contained: {value}"
        ) from exc
    return resolved


def _assert_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise CaptureValidationError(
            f"{label} does not match recomputed value: {actual!r} != {expected!r}"
        )


def _load_json(root: Path, value: object, label: str) -> tuple[Path, Mapping[str, Any]]:
    path = _resolve_path(root, value, label)
    if not path.is_file():
        raise CaptureValidationError(f"{label} does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaptureValidationError(f"{label} is not valid JSON: {path}") from exc
    return path, _mapping(payload, label)


def _validate_screenshot(
    root: Path,
    screenshot: Mapping[str, Any],
    label: str,
) -> dict[str, Any]:
    path = _resolve_path(root, screenshot.get("path"), f"{label}.screenshot")
    if not path.is_file():
        raise CaptureValidationError(f"{label}.screenshot does not exist: {path}")
    width, height = png_dimensions(path)
    _assert_equal(width, _integer(screenshot.get("width"), f"{label}.width"), f"{label}.width")
    _assert_equal(height, _integer(screenshot.get("height"), f"{label}.height"), f"{label}.height")
    digest = sha256_file(path)
    expected_digest = screenshot.get("sha256")
    if not isinstance(expected_digest, str) or len(expected_digest) != 64:
        raise CaptureValidationError(f"{label}.sha256 is missing or malformed")
    _assert_equal(digest, expected_digest, f"{label}.sha256")
    content = png_content_evidence(path)
    if not content["meaningful"]:
        raise CaptureValidationError(
            f"{label} is not meaningful full-height content: {content}"
        )
    return {
        "path": str(path),
        "width": width,
        "height": height,
        "sha256": digest,
        "content": content,
    }


def _label_map(state: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    controls = state.get("controls")
    if not isinstance(controls, list):
        raise CaptureValidationError("rendered state controls is not a list")
    result: dict[str, Mapping[str, Any]] = {}
    for control in controls:
        item = _mapping(control, "rendered control")
        label = item.get("label")
        if isinstance(label, str) and label:
            result[label] = item
    return result


def _validate_live_controls(state: Mapping[str, Any], label: str) -> None:
    controls = _label_map(state)
    required = {
        "View mode",
        "Forecast source (single-source mode)",
        "Target month range",
        "Brand",
        "Parent product",
        "Forecast horizon",
        "Minimum actual volume (KL)",
        "Hierarchy quality status",
        "Actual quality status",
        "Vintage-pair quality status",
        "Source availability",
        "Zero forecasts only",
        "Complete vintage history only",
        "Vintage A rule",
        "Vintage B rule",
        "Vintage B accuracy band",
        "Vintage B bias band",
        "Minimum Vintage B absolute error (KL)",
        "Top N product-target exceptions",
        "Top N ranking",
        "Revision direction (active with comparable pairs)",
        "Revision outcome (active with comparable pairs)",
        "Revision tolerance (KL)",
        "Forecast direction",
    }
    missing = sorted(required - controls.keys())
    if missing:
        raise CaptureValidationError(f"{label} missing live controls: {missing}")

    exact_values: dict[str, object] = {
        "View mode": "Single source",
        "Forecast source (single-source mode)": "TM",
        "Minimum actual volume (KL)": "0",
        "Zero forecasts only": False,
        "Complete vintage history only": False,
        "Vintage A rule": "Oldest available",
        "Vintage B rule": "Latest available",
        "Vintage B accuracy band": "All",
        "Vintage B bias band": "All",
        "Minimum Vintage B absolute error (KL)": "0",
        "Top N product-target exceptions": "0",
        "Top N ranking": "Actual volume",
        "Revision tolerance (KL)": "0.01",
    }
    for control_label, expected in exact_values.items():
        control = controls[control_label]
        actual = control.get("checked") if isinstance(expected, bool) else control.get("value")
        _assert_equal(actual, expected, f"{label}.{control_label}")
    _assert_equal(
        controls["Target month range"].get("values"),
        ["2025-05-01", "2026-12-01"],
        f"{label}.Target month range",
    )
    for control_label in (
        "Brand",
        "Parent product",
        "Forecast horizon",
        "Hierarchy quality status",
        "Actual quality status",
        "Vintage-pair quality status",
        "Source availability",
        "Revision direction (active with comparable pairs)",
        "Revision outcome (active with comparable pairs)",
        "Forecast direction",
    ):
        control = controls[control_label]
        _assert_equal(
            control.get("selectionSource"),
            "live-option-state",
            f"{label}.{control_label}.selectionSource",
        )
        selected = control.get("selectedValues")
        if not isinstance(selected, list) or not selected:
            raise CaptureValidationError(f"{label}.{control_label} has no selected values")
        _assert_equal(
            control.get("selectedCount"),
            len(selected),
            f"{label}.{control_label}.selectedCount",
        )
        _assert_equal(
            control.get("selectedCount"),
            control.get("optionCount"),
            f"{label}.{control_label}.all-selected",
        )


def _control_semantics(state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    controls = _label_map(state)
    fields = (
        "tag",
        "value",
        "values",
        "checked",
        "selectedValues",
        "selectedCount",
        "optionCount",
        "selectionSource",
    )
    return {
        label: {field: control.get(field) for field in fields}
        for label, control in controls.items()
    }


def _validate_disclosures(state: Mapping[str, Any], expected_open: bool, label: str) -> None:
    disclosures = state.get("disclosures")
    if not isinstance(disclosures, list):
        raise CaptureValidationError(f"{label}.disclosures is not a list")
    quality = [
        _mapping(item, f"{label}.disclosure")
        for item in disclosures
        if isinstance(item, Mapping) and item.get("label") == "Data-quality filters"
    ]
    if len(quality) != 1:
        raise CaptureValidationError(
            f"{label} must contain one labeled Data-quality filters disclosure"
        )
    item = quality[0]
    _assert_equal(item.get("kind"), "marimo-accordion", f"{label}.disclosure.kind")
    _assert_equal(item.get("open"), expected_open, f"{label}.disclosure.open")
    _assert_equal(
        item.get("regionVisible"), expected_open, f"{label}.disclosure.regionVisible"
    )
    _assert_equal(
        item.get("ariaExpanded"),
        "true" if expected_open else "false",
        f"{label}.disclosure.ariaExpanded",
    )
    _assert_equal(
        item.get("regionState"),
        "open" if expected_open else "closed",
        f"{label}.disclosure.regionState",
    )
    native = [
        _mapping(item, f"{label}.native-disclosure")
        for item in disclosures
        if isinstance(item, Mapping) and item.get("kind") == "native-details"
    ]
    for index, item in enumerate(native):
        _assert_equal(
            item.get("open"),
            False,
            f"{label}.native-details[{index}] (Vega action disclosures stay closed)",
        )


def _validate_raw_state(
    root: Path,
    path: Path,
    expected_state: str,
    expected_open: bool,
    execution_id: str,
    session: str,
) -> Mapping[str, Any]:
    try:
        payload = _mapping(json.loads(path.read_text(encoding="utf-8")), str(path))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaptureValidationError(f"raw state evidence is not valid JSON: {path}") from exc
    _assert_equal(payload.get("evidence_version"), 1, f"{path}.evidence_version")
    _assert_equal(payload.get("execution_id"), execution_id, f"{path}.execution_id")
    _assert_equal(payload.get("session"), session, f"{path}.session")
    _assert_equal(payload.get("state"), expected_state, f"{path}.state")
    _assert_equal(payload.get("source"), "agent-browser-eval", f"{path}.source")
    raw_result = _mapping(payload.get("raw_browser_result"), f"{path}.raw_browser_result")
    if "data" not in raw_result and "result" not in raw_result:
        raise CaptureValidationError(f"{path}.raw_browser_result has no browser payload")
    rendered = _mapping(payload.get("rendered_state"), f"{path}.rendered_state")
    _assert_equal(rendered.get("state"), "read-from-rendered-controls", f"{path}.rendered_state.state")
    _validate_live_controls(rendered, str(path))
    _validate_disclosures(rendered, expected_open, str(path))
    geometry = _mapping(rendered.get("geometry"), f"{path}.rendered_state.geometry")
    _viewport(geometry.get("viewport"), f"{path}.rendered_state.geometry.viewport")
    _measurement(geometry.get("document"), f"{path}.rendered_state.geometry.document")
    _measurement(geometry.get("application"), f"{path}.rendered_state.geometry.application")
    probe = _mapping(rendered.get("contentProbe"), f"{path}.rendered_state.contentProbe")
    if _integer(probe.get("appTextLength"), f"{path}.appTextLength") < MIN_APP_TEXT_LENGTH:
        raise CaptureValidationError(f"{path} has too little rendered app text")
    return payload


def _validate_normalization(
    root: Path,
    path: Path,
    expected_state: str,
    execution_id: str,
    session: str,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    try:
        payload = _mapping(json.loads(path.read_text(encoding="utf-8")), str(path))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaptureValidationError(f"normalization evidence is not valid JSON: {path}") from exc
    _assert_equal(payload.get("evidence_version"), 1, f"{path}.evidence_version")
    _assert_equal(payload.get("execution_id"), execution_id, f"{path}.execution_id")
    _assert_equal(payload.get("session"), session, f"{path}.session")
    _assert_equal(payload.get("state"), expected_state, f"{path}.state")
    _assert_equal(
        payload.get("normalization_contract"),
        NORMALIZATION_CONTRACT,
        f"{path}.normalization_contract",
    )
    state_path = _resolve_path(root, payload.get("source_state_artifact"), f"{path}.source_state_artifact")
    if not state_path.is_file():
        raise CaptureValidationError(f"{path}.source_state_artifact does not exist: {state_path}")
    normalization = _mapping(payload.get("normalization"), f"{path}.normalization")
    _assert_equal(
        normalization.get("normalizationContract"),
        NORMALIZATION_CONTRACT,
        f"{path}.normalization.normalizationContract",
    )
    contract = _mapping(normalization.get("actionContract"), f"{path}.normalization.actionContract")
    _assert_equal(
        contract.get("ancestorProperties"),
        {
            "height": "auto",
            "minHeight": "auto",
            "maxHeight": "none",
            "overflow": "visible",
            "position": "relative",
        },
        f"{path}.normalization.actionContract.ancestorProperties",
    )
    actions = normalization.get("actions")
    if not isinstance(actions, list) or not actions:
        raise CaptureValidationError(f"{path}.normalization.actions is empty")
    app_actions = [
        _mapping(action, f"{path}.normalization.action")
        for action in actions
        if isinstance(action, Mapping) and action.get("id") == "App"
    ]
    if len(app_actions) != 1:
        raise CaptureValidationError(f"{path}.normalization.actions lacks exactly one #App action")
    expected_after = {
        "height": "auto",
        "min-height": "auto",
        "max-height": "none",
        "overflow": "visible",
        "position": "relative",
    }
    for index, action in enumerate(actions):
        properties = _mapping(action.get("properties"), f"{path}.normalization.actions[{index}].properties")
        after = _mapping(properties.get("after"), f"{path}.normalization.actions[{index}].after")
        for property_name, expected in expected_after.items():
            after_property = _mapping(
                after.get(property_name),
                f"{path}.normalization.actions[{index}].after.{property_name}",
            )
            _assert_equal(
                after_property.get("inline"),
                expected,
                f"{path}.normalization.actions[{index}].after.{property_name}.inline",
            )
    measurements = _mapping(normalization.get("measurements"), f"{path}.normalization.measurements")
    post = _mapping(payload.get("post_measurement"), f"{path}.post_measurement")
    for name in ("viewport", "document", "body", "application"):
        if name == "viewport":
            expected = _viewport(measurements.get(name), f"{path}.normalization.measurements.viewport")
            actual = _viewport(post.get(name), f"{path}.post_measurement.viewport")
        else:
            expected = _measurement(measurements.get(name), f"{path}.normalization.measurements.{name}")
            actual = _measurement(post.get(name), f"{path}.post_measurement.{name}")
        _assert_equal(actual, expected, f"{path}.{name} after normalization")
    probe = _mapping(normalization.get("contentProbe"), f"{path}.normalization.contentProbe")
    if _integer(probe.get("appTextLength"), f"{path}.normalization.appTextLength") < MIN_APP_TEXT_LENGTH:
        raise CaptureValidationError(f"{path}.normalization has too little rendered app text")
    screenshot = _mapping(payload.get("screenshot"), f"{path}.screenshot")
    screenshot_result = _validate_screenshot(root, screenshot, str(path))
    document = _measurement(post.get("document"), f"{path}.post_measurement.document")
    _assert_equal(screenshot_result["width"], document["scrollWidth"], f"{path}.screenshot width")
    _assert_equal(screenshot_result["height"], document["scrollHeight"], f"{path}.screenshot height")
    raw_normalization = _mapping(payload.get("normalization_eval"), f"{path}.normalization_eval")
    raw_post = _mapping(payload.get("post_measurement_eval"), f"{path}.post_measurement_eval")
    if "data" not in raw_normalization and "result" not in raw_normalization:
        raise CaptureValidationError(f"{path}.normalization_eval has no raw browser payload")
    if "data" not in raw_post and "result" not in raw_post:
        raise CaptureValidationError(f"{path}.post_measurement_eval has no raw browser payload")
    return payload, screenshot_result


def _validate_analytical_state(
    state: Mapping[str, Any],
    rendered: Mapping[str, Any],
) -> None:
    _assert_equal(state.get("view_mode"), "Single source", "analytical_state.view_mode")
    _assert_equal(state.get("source"), "TM", "analytical_state.source")
    target = _mapping(state.get("target_month_range"), "analytical_state.target_month_range")
    _assert_equal(target.get("start"), "2025-05-01", "analytical_state.target_month_range.start")
    _assert_equal(target.get("end"), "2026-12-01", "analytical_state.target_month_range.end")
    _assert_equal(target.get("selection"), "full available range", "analytical_state.target_month_range.selection")
    for key in ("brands", "parent_products", "horizons"):
        selection = _mapping(state.get(key), f"analytical_state.{key}")
        _assert_equal(selection.get("selection"), "all available", f"analytical_state.{key}.selection")
        selected = selection.get("selected")
        if not isinstance(selected, list) or not selected:
            raise CaptureValidationError(f"analytical_state.{key}.selected is empty")
        _assert_equal(selection.get("selected_count"), len(selected), f"analytical_state.{key}.selected_count")
        _assert_equal(selection.get("selected_count"), selection.get("option_count"), f"analytical_state.{key}.all-selected")
    _assert_equal(state.get("vintage_a_rule"), "Oldest available", "analytical_state.vintage_a_rule")
    _assert_equal(state.get("vintage_b_rule"), "Latest available", "analytical_state.vintage_b_rule")
    _assert_equal(state.get("minimum_actual_volume_kl"), 0.0, "analytical_state.minimum_actual_volume_kl")
    performance = _mapping(state.get("performance_filters"), "analytical_state.performance_filters")
    _assert_equal(performance.get("accuracy_band"), "All", "analytical_state.performance_filters.accuracy_band")
    _assert_equal(performance.get("bias_band"), "All", "analytical_state.performance_filters.bias_band")
    _assert_equal(performance.get("minimum_absolute_error_kl"), 0.0, "analytical_state.performance_filters.minimum_absolute_error_kl")
    _assert_equal(performance.get("top_n"), 0, "analytical_state.performance_filters.top_n")
    _assert_equal(performance.get("top_n_metric"), "Actual volume", "analytical_state.performance_filters.top_n_metric")
    _assert_equal(performance.get("revision_tolerance_kl"), 0.01, "analytical_state.performance_filters.revision_tolerance_kl")
    quality = _mapping(state.get("quality_filters"), "analytical_state.quality_filters")
    _assert_equal(quality.get("zero_forecasts_only"), False, "analytical_state.quality_filters.zero_forecasts_only")
    _assert_equal(quality.get("complete_vintage_history_only"), False, "analytical_state.quality_filters.complete_vintage_history_only")
    rendered_controls = _label_map(rendered)
    _assert_equal(state.get("view_mode"), rendered_controls["View mode"].get("value"), "analytical_state.rendered.view_mode")
    _assert_equal(state.get("source"), rendered_controls["Forecast source (single-source mode)"].get("value"), "analytical_state.rendered.source")


def validate_capture_artifact(
    root: Path,
    artifact: Path,
    *,
    require_normalized: bool = False,
) -> dict[str, Any]:
    """Validate a live-browser capture artifact and return recomputed evidence."""
    if not artifact.is_file():
        raise CaptureValidationError(f"capture artifact does not exist: {artifact}")
    try:
        document = _mapping(json.loads(artifact.read_text(encoding="utf-8")), "capture artifact")
    except (OSError, json.JSONDecodeError) as exc:
        raise CaptureValidationError(f"capture artifact is not valid JSON: {artifact}") from exc
    _assert_equal(document.get("schema_version"), SCHEMA_VERSION, "schema_version")
    _assert_equal(document.get("capture_contract"), CAPTURE_CONTRACT, "capture_contract")
    _assert_equal(document.get("overflow_tolerance_px"), OVERFLOW_TOLERANCE_PX, "overflow_tolerance_px")
    if not isinstance(document.get("capture_date"), str) or not document["capture_date"]:
        raise CaptureValidationError("capture_date is missing")
    workflow = _mapping(document.get("workflow"), "workflow")
    _assert_equal(workflow.get("name"), WORKFLOW_VERSION, "workflow.name")
    _assert_equal(workflow.get("path"), "scripts/capture_forecast_analysis_dashboard_ui.py", "workflow.path")
    execution_id = workflow.get("execution_id")
    session = workflow.get("browser_session")
    if not isinstance(execution_id, str) or not execution_id:
        raise CaptureValidationError("workflow.execution_id is missing")
    if not isinstance(session, str) or not session:
        raise CaptureValidationError("workflow.browser_session is missing")
    _assert_equal(document.get("state"), "default-closed", "state")
    viewport = _viewport(document.get("viewport"))
    _assert_equal(viewport["width"], 1280, "viewport.width")
    _assert_equal(viewport["height"], 800, "viewport.height")
    analytical_state = _mapping(document.get("analytical_state"), "analytical_state")

    raw_evidence = _mapping(document.get("raw_evidence"), "raw_evidence")
    default_state_path = _resolve_path(root, raw_evidence.get("default_state"), "raw_evidence.default_state")
    expanded_state_path = _resolve_path(root, raw_evidence.get("expanded_state"), "raw_evidence.expanded_state")
    default_norm_path = _resolve_path(root, raw_evidence.get("default_normalization"), "raw_evidence.default_normalization")
    expanded_norm_path = _resolve_path(root, raw_evidence.get("expanded_normalization"), "raw_evidence.expanded_normalization")
    default_raw = _validate_raw_state(root, default_state_path, "default-closed", False, execution_id, session)
    expanded_raw = _validate_raw_state(root, expanded_state_path, "expanded-open", True, execution_id, session)
    default_rendered = _mapping(default_raw.get("rendered_state"), "default rendered state")
    expanded_rendered = _mapping(expanded_raw.get("rendered_state"), "expanded rendered state")
    _validate_live_controls(default_rendered, "default controls")
    _validate_live_controls(expanded_rendered, "expanded controls")
    _assert_equal(
        _control_semantics(default_rendered),
        _control_semantics(expanded_rendered),
        "default/expanded live controls",
    )
    _validate_analytical_state(analytical_state, default_rendered)

    default_norm, default_norm_screenshot = _validate_normalization(
        root, default_norm_path, "default-closed", execution_id, session
    )
    expanded_norm, expanded_norm_screenshot = _validate_normalization(
        root, expanded_norm_path, "expanded-open", execution_id, session
    )
    _assert_equal(
        default_norm.get("source_state_artifact"),
        str(default_state_path.relative_to(root.resolve())),
        "default normalization state binding",
    )
    _assert_equal(
        expanded_norm.get("source_state_artifact"),
        str(expanded_state_path.relative_to(root.resolve())),
        "expanded normalization state binding",
    )
    default_pre = _mapping(default_rendered.get("geometry"), "default pre-normalization geometry")
    final_pre = _mapping(document.get("pre_normalization"), "pre_normalization")
    _assert_equal(final_pre, default_pre, "pre_normalization raw binding")
    normalized_capture = _mapping(document.get("normalized_capture"), "normalized_capture")
    if require_normalized:
        _assert_equal(normalized_capture.get("normalized"), True, "normalized_capture.normalized")
        _assert_equal(normalized_capture.get("normalization_contract"), NORMALIZATION_CONTRACT, "normalized_capture.normalization_contract")
    _assert_equal(normalized_capture.get("state"), "expanded-open", "normalized_capture.state")
    normalized_geometry = _mapping(expanded_norm.get("post_measurement"), "expanded post measurement")
    _assert_equal(normalized_capture.get("viewport"), normalized_geometry.get("viewport"), "normalized_capture.viewport")
    _assert_equal(normalized_capture.get("document"), normalized_geometry.get("document"), "normalized_capture.document")
    _assert_equal(normalized_capture.get("application"), normalized_geometry.get("application"), "normalized_capture.application")
    _assert_equal(normalized_capture.get("body"), normalized_geometry.get("body"), "normalized_capture.body")
    normalized_screenshot = _mapping(normalized_capture.get("screenshot"), "normalized_capture.screenshot")
    normalized_screenshot_path = _resolve_path(
        root,
        normalized_screenshot.get("path"),
        "normalized_capture.screenshot",
    )
    _assert_equal(
        normalized_screenshot_path,
        Path(expanded_norm_screenshot["path"]).resolve(),
        "normalized_capture.screenshot.path",
    )
    _assert_equal(normalized_screenshot.get("sha256"), expanded_norm_screenshot["sha256"], "normalized_capture.screenshot.sha256")
    _assert_equal(normalized_screenshot.get("width"), expanded_norm_screenshot["width"], "normalized_capture.screenshot.width")
    _assert_equal(normalized_screenshot.get("height"), expanded_norm_screenshot["height"], "normalized_capture.screenshot.height")

    screenshots = _mapping(document.get("screenshots"), "screenshots")
    immutable = _validate_screenshot(root, _mapping(screenshots.get("immutable_before_state"), "screenshots.immutable_before_state"), "screenshots.immutable_before_state")
    if immutable["path"] == str((root / IMMUTABLE_BASELINE_RELATIVE_PATH).resolve()):
        _assert_equal(immutable["width"], 6650, "immutable baseline width")
        _assert_equal(immutable["height"], 11082, "immutable baseline height")
        _assert_equal(immutable["sha256"], IMMUTABLE_BASELINE_SHA256, "immutable baseline SHA256")
    default_screenshot = _validate_screenshot(root, _mapping(screenshots.get("default"), "screenshots.default"), "screenshots.default")
    expanded_screenshot = _validate_screenshot(root, _mapping(screenshots.get("expanded"), "screenshots.expanded"), "screenshots.expanded")
    if default_screenshot["sha256"] == expanded_screenshot["sha256"]:
        raise CaptureValidationError("default and expanded screenshots are the same file content")
    difference = png_difference_evidence(Path(default_screenshot["path"]), Path(expanded_screenshot["path"]))
    if difference["same_dimensions"]:
        if difference["difference_ratio"] < MIN_STATE_DIFFERENCE_RATIO:
            raise CaptureValidationError(
                f"default and expanded screenshots lack structural difference: {difference}"
            )
    elif expanded_screenshot["height"] <= default_screenshot["height"]:
        raise CaptureValidationError(
            f"expanded screenshot is not larger than default screenshot: {difference}"
        )

    observations = _mapping(document.get("baseline_observations"), "baseline_observations")
    pre_overflow = evaluate_overflow(
        _mapping(final_pre.get("document"), "pre_normalization.document"),
        _mapping(final_pre.get("application"), "pre_normalization.application"),
        OVERFLOW_TOLERANCE_PX,
    )
    normalized_overflow = evaluate_overflow(
        _mapping(normalized_geometry.get("document"), "normalized_capture.document"),
        _mapping(normalized_geometry.get("application"), "normalized_capture.application"),
        OVERFLOW_TOLERANCE_PX,
    )
    _assert_equal(observations.get("pre_normalization_application_overflows"), pre_overflow["application"]["overflows"], "baseline_observations.pre_normalization_application_overflows")
    _assert_equal(observations.get("normalized_document_overflows"), normalized_overflow["document"]["overflows"], "baseline_observations.normalized_document_overflows")
    _assert_equal(observations.get("normalized_application_overflows"), normalized_overflow["application"]["overflows"], "baseline_observations.normalized_application_overflows")
    _assert_equal(observations.get("full_page_screenshot_width_px"), expanded_screenshot["width"], "baseline_observations.full_page_screenshot_width_px")
    _assert_equal(observations.get("default_and_expanded_states_differ"), True, "baseline_observations.default_and_expanded_states_differ")
    return {
        "payload": document,
        "pre_overflow": pre_overflow,
        "normalized_overflow": normalized_overflow,
        "normalized_screenshot": expanded_screenshot,
        "default_screenshot": default_screenshot,
        "expanded_screenshot": expanded_screenshot,
        "screenshot_difference": difference,
        "default_normalization": default_norm,
        "expanded_normalization": expanded_norm,
    }


def verify_baseline(
    root: Path,
    artifact: Path,
    expected_width: int,
    expected_height: int,
) -> dict[str, Any]:
    """Verify the immutable before-state PNG and its recorded dimensions."""
    if not artifact.is_file():
        raise CaptureValidationError(f"baseline artifact does not exist: {artifact}")
    actual_width, actual_height = png_dimensions(artifact)
    _assert_equal(actual_width, expected_width, "baseline width")
    _assert_equal(actual_height, expected_height, "baseline height")
    digest = sha256_file(artifact)
    expected_path = (root / IMMUTABLE_BASELINE_RELATIVE_PATH).resolve()
    if artifact.resolve() == expected_path:
        _assert_equal(digest, IMMUTABLE_BASELINE_SHA256, "immutable baseline SHA256")
        metadata_path = (root / CAPTURE_ARTIFACT_RELATIVE_PATH).resolve()
        if not metadata_path.is_file():
            raise CaptureValidationError(
                f"immutable baseline metadata does not exist: {metadata_path}"
            )
        try:
            metadata = _mapping(
                json.loads(metadata_path.read_text(encoding="utf-8")),
                "immutable baseline metadata",
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise CaptureValidationError(
                f"immutable baseline metadata is not valid JSON: {metadata_path}"
            ) from exc
        screenshots = _mapping(metadata.get("screenshots"), "metadata.screenshots")
        recorded = _mapping(
            screenshots.get("immutable_before_state"),
            "metadata.screenshots.immutable_before_state",
        )
        recorded_path = _resolve_path(root, recorded.get("path"), "metadata immutable baseline")
        _assert_equal(recorded_path, artifact.resolve(), "recorded immutable baseline path")
        _assert_equal(recorded.get("width"), actual_width, "recorded immutable baseline width")
        _assert_equal(recorded.get("height"), actual_height, "recorded immutable baseline height")
        _assert_equal(recorded.get("sha256"), digest, "recorded immutable baseline SHA256")
        capture_date = recorded.get("capture_date")
        if not isinstance(capture_date, str) or not capture_date:
            raise CaptureValidationError("recorded immutable baseline capture date is missing")
    return {
        "path": str(artifact.resolve()),
        "width": actual_width,
        "height": actual_height,
        "sha256": digest,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    baseline = subparsers.add_parser("verify-baseline")
    baseline.add_argument("--root", type=Path, default=Path("."))
    baseline.add_argument("--artifact", type=Path, required=True)
    baseline.add_argument("--expected-width", type=int, default=6650)
    baseline.add_argument("--expected-height", type=int, default=11082)

    capture = subparsers.add_parser("verify-capture")
    capture.add_argument("--root", type=Path, default=Path("."))
    capture.add_argument("--artifact", type=Path, required=True)
    capture.add_argument("--require-normalized", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the requested UI evidence verification command."""
    args = _parser().parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "verify-baseline":
            artifact = _resolve_path(root, str(args.artifact), "baseline artifact")
            result = verify_baseline(
                root,
                artifact,
                args.expected_width,
                args.expected_height,
            )
            print(
                "baseline verification passed: "
                f"{result['width']}x{result['height']} px, SHA256 {result['sha256']}"
            )
            return 0

        artifact = _resolve_path(root, str(args.artifact), "capture artifact")
        result = validate_capture_artifact(
            root,
            artifact,
            require_normalized=args.require_normalized,
        )
        pre = result["pre_overflow"]
        normalized = result["normalized_overflow"]
        print("capture verification passed")
        print(
            "  pre-normalization overflow: "
            f"document={'yes' if pre['document']['overflows'] else 'no'}, "
            f"application={'yes' if pre['application']['overflows'] else 'no'}"
        )
        print(
            "  normalized capture overflow: "
            f"document={'yes' if normalized['document']['overflows'] else 'no'}, "
            f"application={'yes' if normalized['application']['overflows'] else 'no'}"
        )
        print(
            "  full-page screenshot: "
            f"{result['normalized_screenshot']['width']}x"
            f"{result['normalized_screenshot']['height']} px"
        )
        print(
            "  disclosure state difference: "
            f"{result['screenshot_difference']['difference_ratio']:.4f} sampled-pixel ratio"
        )
        return 0
    except (CaptureValidationError, OSError, TypeError, ValueError) as exc:
        label = "baseline" if args.command == "verify-baseline" else "capture"
        print(f"{label} verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
