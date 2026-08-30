"""Shared provenance contracts for the forecast dashboard UI capture."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

CAPTURE_SCHEMA_VERSION = 3
CAPTURE_CONTRACT = "forecast-analysis-dashboard-ui-baseline-v2"
NORMALIZATION_CONTRACT = "marimo-full-page-normalization-v1"
WORKFLOW_VERSION = "forecast-dashboard-live-capture-v1"
STATE_PROOF_CONTRACT = "forecast-analysis-dashboard-ui-state-proof-v1"
SCREENSHOT_BINDING_CONTRACT = "forecast-analysis-dashboard-ui-screenshot-binding-v1"
CAPTURE_ANCHOR_CONTRACT = "forecast-analysis-dashboard-ui-capture-anchor-v1"
PROVENANCE_HASH_ALGORITHM = "sha256-canonical-json-v1"
OVERFLOW_TOLERANCE_PX = 2

IMMUTABLE_BASELINE_RELATIVE_PATH = Path(
    "validation-artifacts/forecast-analysis-dashboard-long-full.png"
)
CAPTURE_ARTIFACT_RELATIVE_PATH = Path(
    "validation-artifacts/forecast-analysis-dashboard-ui-baseline.json"
)
STATE_ARTIFACT_RELATIVE_PATHS = {
    "default-closed": Path(
        "validation-artifacts/forecast-analysis-dashboard-ui-raw-default.json"
    ),
    "expanded-open": Path(
        "validation-artifacts/forecast-analysis-dashboard-ui-raw-expanded.json"
    ),
}
NORMALIZATION_ARTIFACT_RELATIVE_PATHS = {
    "default-closed": Path(
        "validation-artifacts/forecast-analysis-dashboard-ui-normalization-default.json"
    ),
    "expanded-open": Path(
        "validation-artifacts/forecast-analysis-dashboard-ui-normalization-expanded.json"
    ),
}
SCREENSHOT_RELATIVE_PATHS = {
    "default-closed": Path("validation-artifacts/forecast-analysis-dashboard-default.png"),
    "expanded-open": Path("validation-artifacts/forecast-analysis-dashboard-expanded.png"),
}
EXPECTED_DISCLOSURE_LABEL = "Data-quality filters"


def canonical_json_bytes(value: object) -> bytes:
    """Serialize contract values without formatting-dependent hash changes."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: object) -> str:
    """Hash a JSON-compatible contract value."""
    return sha256_bytes(canonical_json_bytes(value))


def relative_path(path: str | Path, root: Path) -> str:
    """Return a repository-relative path with a stable separator."""
    candidate = Path(path)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    return resolved.relative_to(root.resolve()).as_posix()


def normalize_paths(value: object, root: Path) -> object:
    """Replace repository-specific absolute paths before hashing JSON evidence."""
    if isinstance(value, Mapping):
        return {str(key): normalize_paths(item, root) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_paths(item, root) for item in value]
    if isinstance(value, str) and value.startswith("/"):
        candidate = Path(value)
        try:
            return relative_path(candidate, root)
        except ValueError:
            return value
    return value


def sha256_json_file(path: Path, root: Path) -> str:
    """Hash JSON evidence after normalizing only repository-local paths."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"JSON evidence is not readable: {path}") from exc
    return sha256_json(normalize_paths(payload, root))


def expected_state_artifact(state: str) -> Path:
    try:
        return STATE_ARTIFACT_RELATIVE_PATHS[state]
    except KeyError as exc:
        raise ValueError(f"unknown dashboard capture state: {state}") from exc


def expected_normalization_artifact(state: str) -> Path:
    try:
        return NORMALIZATION_ARTIFACT_RELATIVE_PATHS[state]
    except KeyError as exc:
        raise ValueError(f"unknown dashboard capture state: {state}") from exc


def expected_screenshot(state: str) -> Path:
    try:
        return SCREENSHOT_RELATIVE_PATHS[state]
    except KeyError as exc:
        raise ValueError(f"unknown dashboard capture state: {state}") from exc


def expected_disclosure(state: str) -> dict[str, Any]:
    return {
        "label": EXPECTED_DISCLOSURE_LABEL,
        "open": state == "expanded-open",
    }


def disclosure_evidence(
    rendered_state: Mapping[str, Any],
    label: str = EXPECTED_DISCLOSURE_LABEL,
) -> dict[str, Any]:
    """Select the state-bearing disclosure record from rendered browser evidence."""
    disclosures = rendered_state.get("disclosures")
    if not isinstance(disclosures, list):
        raise ValueError("rendered state disclosures is not a list")
    matches = [
        item
        for item in disclosures
        if isinstance(item, Mapping) and item.get("label") == label
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one {label!r} disclosure, found {len(matches)}")
    source = matches[0]
    fields = (
        "kind",
        "label",
        "controlId",
        "regionId",
        "ariaExpanded",
        "state",
        "open",
        "regionVisible",
        "regionState",
        "contentLength",
    )
    return {field: source.get(field) for field in fields}


def geometry_evidence(
    rendered_state: Mapping[str, Any],
    normalization: Mapping[str, Any],
) -> dict[str, Any]:
    """Keep the pre/post geometry and content probes in the screenshot proof."""
    return {
        "pre": rendered_state.get("geometry"),
        "post": normalization.get("post_measurement"),
        "pre_content_probe": rendered_state.get("contentProbe"),
        "post_content_probe": normalization.get("normalization", {}).get("contentProbe")
        if isinstance(normalization.get("normalization"), Mapping)
        else None,
    }


def screenshot_command_contract(
    command_result: Mapping[str, Any],
    root: Path,
    expected_repository_path: str | Path,
) -> dict[str, Any]:
    """Extract stable command evidence while retaining the session and result proof."""
    command = command_result.get("command")
    if not isinstance(command, list) or not command:
        raise ValueError("screenshot command is missing argv")
    expected_path = Path(expected_repository_path).as_posix()
    argv = [str(item) for item in command]
    argv[0] = Path(argv[0]).name
    if argv:
        argv[-1] = expected_path
    return {
        "argv": argv,
        "exit_code": command_result.get("exit_code"),
        "envelope": normalize_paths(command_result.get("envelope"), root),
        "data": normalize_paths(command_result.get("data"), root),
    }


def state_proof(
    *,
    state: str,
    rendered_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a state-specific proof for the disclosure and pre-capture geometry."""
    payload = {
        "state": state,
        "expected_disclosure": expected_disclosure(state),
        "disclosure": disclosure_evidence(rendered_state),
        "geometry": rendered_state.get("geometry"),
        "content_probe": rendered_state.get("contentProbe"),
    }
    return {
        "contract": STATE_PROOF_CONTRACT,
        "algorithm": PROVENANCE_HASH_ALGORITHM,
        "payload": payload,
        "proof_sha256": sha256_json(payload),
    }


def screenshot_binding(
    *,
    execution_id: str,
    session: str,
    state: str,
    expected_repository_path: str | Path,
    state_artifact_path: str | Path,
    state_artifact_sha256: str,
    state_proof_sha256: str,
    normalization_artifact_path: str | Path,
    command_sha256: str,
    disclosure: Mapping[str, Any],
    geometry: Mapping[str, Any],
    screenshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a content-addressed proof joining screenshot and capture evidence."""
    payload: dict[str, Any] = {
        "contract": SCREENSHOT_BINDING_CONTRACT,
        "algorithm": PROVENANCE_HASH_ALGORITHM,
        "execution_id": execution_id,
        "session": session,
        "state": state,
        "expected_repository_path": Path(expected_repository_path).as_posix(),
        "state_artifact": {
            "path": Path(state_artifact_path).as_posix(),
            "sha256": state_artifact_sha256,
        },
        "state_proof_sha256": state_proof_sha256,
        "normalization_artifact_path": Path(normalization_artifact_path).as_posix(),
        "screenshot_command_sha256": command_sha256,
        "disclosure": dict(disclosure),
        "disclosure_sha256": sha256_json(disclosure),
        "geometry": dict(geometry),
        "geometry_sha256": sha256_json(geometry),
        "screenshot": dict(screenshot),
    }
    return {**payload, "binding_sha256": sha256_json(payload)}


def capture_anchor(
    *,
    execution_id: str,
    session: str,
    workflow_name: str,
    workflow_path: str,
    capture_artifact_path: str | Path,
    immutable_before_state: Mapping[str, Any],
    states: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Create one cross-state receipt for the capture execution."""
    payload: dict[str, Any] = {
        "contract": CAPTURE_ANCHOR_CONTRACT,
        "algorithm": PROVENANCE_HASH_ALGORITHM,
        "execution_id": execution_id,
        "session": session,
        "workflow": {"name": workflow_name, "path": workflow_path},
        "capture_artifact_path": Path(capture_artifact_path).as_posix(),
        "immutable_before_state": dict(immutable_before_state),
        "states": {state: dict(value) for state, value in sorted(states.items())},
    }
    return {**payload, "anchor_sha256": sha256_json(payload)}
