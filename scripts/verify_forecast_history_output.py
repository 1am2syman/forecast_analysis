"""Read-only validation of an existing forecast-history CSV.

The default mode checks only the durable six-column output contract.  The
opt-in ``--current-input-regression`` mode additionally checks today's source
snapshot against the immutable TM oracle and its explicit current-input
manifest.  This script never writes the production CSV.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
from pathlib import Path

import polars as pl
from polars.testing import assert_frame_equal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_OUTPUT = (
    ROOT / "artifacts/forecast_history/consolidated/forecast_history_waterfall.csv"
)
TM_ORACLE_MANIFEST = ROOT / "tests/fixtures/tm_forecast_history_baseline.json"
CURRENT_INPUT_MANIFEST = ROOT / "tests/fixtures/current_input_regression.json"
TM_SORT_COLUMNS = ["parent_code", "snop_month", "calculation_month"]
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def check(condition: bool, message: str) -> None:
    """Raise a concise verification failure instead of continuing."""
    if not condition:
        raise AssertionError(message)


def _repo_path(value: str) -> Path:
    """Resolve a manifest path while refusing absolute/traversal paths."""
    relative = Path(value)
    check(
        not relative.is_absolute() and ".." not in relative.parts,
        f"manifest path must be repository-relative: {value!r}",
    )
    return ROOT / relative


def _read_json(path: Path) -> dict:
    """Read a JSON manifest and require an object at its root."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssertionError(f"unable to read manifest {path.name}: {exc}") from exc
    check(isinstance(value, dict), f"manifest {path.name} must contain an object")
    return value


def _git_blob_oid(content: bytes) -> str:
    """Calculate Git's SHA-1 identity for a blob's exact bytes."""
    header = f"blob {len(content)}\0".encode()
    return hashlib.new(
        "sha1", header + content, usedforsecurity=False
    ).hexdigest()


def load_tm_regression_oracle() -> tuple[pl.DataFrame, dict]:
    """Load and checksum the independent pre-ML TM oracle fixture."""
    manifest = _read_json(TM_ORACLE_MANIFEST)
    check(
        manifest.get("oracle_id") == "tm-forecast-history-pre-ml-v1",
        "unexpected TM oracle identity",
    )
    source_commit = manifest.get("source_commit")
    source_blob = manifest.get("source_git_blob_oid")
    check(
        isinstance(source_commit, str) and bool(HEX40.fullmatch(source_commit)),
        "invalid oracle source commit",
    )
    check(
        isinstance(source_blob, str) and bool(HEX40.fullmatch(source_blob)),
        "invalid oracle source blob identity",
    )
    fixture_path = _repo_path(str(manifest.get("fixture_path", "")))
    try:
        fixture_bytes = fixture_path.read_bytes()
    except OSError as exc:
        raise AssertionError(f"unable to read TM oracle fixture: {exc}") from exc
    expected_hash = manifest.get("fixture_sha256")
    check(
        isinstance(expected_hash, str) and bool(HEX64.fullmatch(expected_hash)),
        "invalid TM oracle checksum",
    )
    actual_hash = hashlib.sha256(fixture_bytes).hexdigest()
    check(
        actual_hash == expected_hash,
        "TM oracle fixture checksum does not match its manifest",
    )
    actual_blob_oid = _git_blob_oid(fixture_bytes)
    check(
        actual_blob_oid == source_blob,
        "TM oracle fixture does not match its recorded Git blob identity",
    )

    frame = pl.read_csv(io.BytesIO(fixture_bytes))
    expected_columns = manifest.get("columns")
    check(
        frame.columns == expected_columns, f"TM oracle schema mismatch: {frame.columns}"
    )
    check(
        frame.height == manifest.get("row_count"),
        f"TM oracle row count mismatch: {frame.height}",
    )
    return frame, manifest


def _load_current_input_manifest() -> dict:
    """Load the explicit, opt-in current source snapshot identity."""
    manifest = _read_json(CURRENT_INPUT_MANIFEST)
    check(
        manifest.get("regression_id") == "forecast-history-current-inputs-v1",
        "unexpected current-input regression identity",
    )
    check(
        manifest.get("tm_oracle_id") == "tm-forecast-history-pre-ml-v1",
        "current-input regression is not tied to the TM oracle",
    )
    ml_source = manifest.get("ml_source")
    if not isinstance(ml_source, dict):
        raise TypeError("current-input manifest is missing ML source identity")
    ml_path = _repo_path(str(ml_source.get("path", "")))
    try:
        ml_hash = hashlib.sha256(ml_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise AssertionError(f"unable to read current ML source: {exc}") from exc
    check(ml_hash == ml_source.get("sha256"), "current ML workbook checksum changed")
    return manifest


def _month_keys(frame: pl.DataFrame, column: str) -> list[str]:
    """Return sorted YYYY-MM keys from an internal Date column."""
    return [value.strftime("%Y-%m") for value in sorted(frame[column].unique())]


def verify_output_contract(output_path: Path) -> pl.DataFrame:
    """Validate an existing CSV without rebuilding or mutating it."""
    check(output_path.is_file(), f"forecast history output not found: {output_path}")
    try:
        output = pl.read_csv(output_path)
    except Exception as exc:
        raise AssertionError(f"unable to read forecast history output: {exc}") from exc
    try:
        import forecast_history_pipeline as pipeline  # pyright: ignore[reportMissingImports]

        pipeline.validate_formatted_history(output)
    except (AssertionError, ValueError, RuntimeError) as exc:
        raise AssertionError(str(exc)) from exc
    return output


def verify_current_input_regression(output: pl.DataFrame) -> None:
    """Run the explicit current-workbook regression against durable facts.

    The row counts and coverage below are intentionally snapshot expectations,
    loaded from ``current_input_regression.json``.  They are not part of the
    general output verifier; a future workbook refresh can pass the default
    contract check without being rejected by these current-input values.
    """
    import forecast_history_pipeline as pipeline  # pyright: ignore[reportMissingImports]

    oracle, oracle_manifest = load_tm_regression_oracle()
    current_manifest = _load_current_input_manifest()
    expected = current_manifest.get("expected")
    if not isinstance(expected, dict):
        raise TypeError("current-input manifest is missing expectations")
    check(
        oracle.height == oracle_manifest["row_count"],
        "TM oracle manifest is internally inconsistent",
    )

    build = pipeline.build_forecast_history_from_paths()
    expected_tm = oracle.sort(TM_SORT_COLUMNS)
    actual_tm = pipeline.format_forecast_history_output(
        build.tm, required_sources={"tm"}
    ).select(expected_tm.columns)
    assert_frame_equal(actual_tm.sort(TM_SORT_COLUMNS), expected_tm, check_dtypes=False)

    check(
        build.tm.height == expected["tm_rows"],
        f"unexpected TM row count: {build.tm.height}",
    )
    check(
        build.ml.height == expected["ml_rows"],
        f"unexpected ML row count: {build.ml.height}",
    )
    check(
        build.consolidated.height == expected["combined_rows"],
        f"unexpected combined row count: {build.consolidated.height}",
    )
    check(
        build.tm.get_column("parent_code").n_unique() == expected["tm_parents"],
        "unexpected TM parent count",
    )
    check(
        build.ml.get_column("parent_code").n_unique() == expected["ml_parents"],
        "unexpected ML parent count",
    )
    check(
        _month_keys(build.tm, "calculation_month") == expected["tm_calculation_months"],
        "TM calculation-month coverage changed",
    )
    check(
        _month_keys(build.ml, "calculation_month") == expected["ml_calculation_months"],
        "ML calculation-month coverage changed",
    )
    expected_snop = expected["snop_months"]
    check(
        _month_keys(build.tm, "snop_month") == expected_snop,
        "TM target-month coverage changed",
    )
    check(
        _month_keys(build.ml, "snop_month") == expected_snop,
        "ML target-month coverage changed",
    )
    check(
        list(build.ml_validation.horizon_counts)
        == [tuple(item) for item in expected["ml_horizon_counts"]],
        "ML horizon coverage changed",
    )
    check(
        build.ml_validation.duplicate_final_key_count == 0,
        "ML duplicate count is not zero",
    )
    assert_frame_equal(output, build.consolidated, check_dtypes=False)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="CSV to verify (relative paths are resolved from the repository root)",
    )
    parser.add_argument(
        "--current-input-regression",
        action="store_true",
        help="also check the explicit current workbook snapshot and TM oracle",
    )
    return parser.parse_args()


def main() -> int:
    """Run read-only output verification and return a process status."""
    args = _parse_args()
    output_path = args.output if args.output.is_absolute() else ROOT / args.output
    try:
        output = verify_output_contract(output_path)
        if args.current_input_regression:
            verify_current_input_regression(output)
    except (AssertionError, OSError, TypeError, ValueError, RuntimeError) as exc:
        print(f"FORECAST HISTORY OUTPUT VERIFICATION FAILED: {exc}", file=sys.stderr)
        return 1

    print(
        "FORECAST HISTORY OUTPUT VERIFIED "
        f"rows={output.height} columns={len(output.columns)}"
    )
    if args.current_input_regression:
        print("FORECAST HISTORY CURRENT REGRESSION VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
