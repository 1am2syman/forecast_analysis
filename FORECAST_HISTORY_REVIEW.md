# Forecast History Implementation Review

## Verdict

The implementation is close, but it is not complete. Four findings remain: one standards issue and three specification gaps.

## Standards

### P2 — Atomic writes change output permissions to `0600`

**Location:** `forecast_history_pipeline.py:1132-1147`

`tempfile.mkstemp()` creates the temporary file with mode `0600`. The subsequent `os.replace()` publishes the temporary file with that mode, even when the previous output was `0644`.

Observed behavior:

```text
existing file: 0644
after atomic replacement: 0600
current production CSV: 0600
```

This can prevent other users or processes from reading the generated artifact.

#### Suggested solution

Before replacement, apply an appropriate mode to the temporary file:

1. If the output already exists, preserve its current mode.
2. If it does not exist, use a documented default such as `0644`, subject to the process umask.
3. Apply the mode only after the temporary CSV has passed validation and before `os.replace()`.

Example implementation shape:

```python
existing_mode = (
    stat.S_IMODE(output_path.stat().st_mode) if output_path.exists() else 0o644
)

# Write and validate temporary_path first.
os.chmod(temporary_path, existing_mode)
os.replace(temporary_path, output_path)
```

Add tests proving that:

- replacement preserves an existing `0644` mode;
- replacement preserves another explicitly selected existing mode;
- a newly created output receives the documented default mode;
- failed generation leaves both the previous bytes and mode unchanged.

## Specification

### P2 — Source-family invariants are not enforced

**Locations:**

- `forecast_history_pipeline.py:953-1045`
- `scripts/verify_forecast_history_output.py:134-147`
- `tests/test_forecast_history_etl.py:317-328`

Validation currently checks only that each source value belongs to `{tm, ml}`. It does not ensure that:

- the `tm` argument contains only rows labeled `tm`;
- the `ml` argument contains only rows labeled `ml`;
- a consolidated output contains both source families.

The following invalid inputs are currently accepted:

```text
TM and ML labels swapped
both inputs labeled tm
both inputs labeled ml
TM-only consolidated output
ML-only consolidated output
```

The command-line verifier also accepts a one-row, TM-only CSV as a valid consolidated output.

#### Suggested solution

Separate source-specific validation from generic frame validation.

For internal inputs, add an expected-source assertion:

```python
def _validate_expected_source(
    frame: pl.DataFrame,
    expected_source: str,
    label: str,
) -> None:
    actual_sources = set(frame.get_column("source").unique().to_list())
    if actual_sources != {expected_source}:
        raise ValueError(
            f"{label} validation failed: expected only source "
            f"{expected_source!r}, found {sorted(actual_sources)}"
        )
```

Call it before concatenation:

```python
_validate_expected_source(tm, "tm", "TM source")
_validate_expected_source(ml, "ml", "ML source")
```

For the published consolidated contract, require both source families:

```python
actual_sources = set(frame.get_column("source").unique().to_list())
if actual_sources != set(FORECAST_SOURCES):
    raise ValueError(
        "formatted forecast history validation failed: expected both "
        f"tm and ml sources, found {sorted(actual_sources)}"
    )
```

If a reusable validator must also support source-specific intermediate frames, expose that difference explicitly rather than weakening the consolidated contract. For example:

```python
validate_formatted_history(frame, required_sources={"tm", "ml"})
```

Add tests for:

- swapped source labels;
- a TM argument containing an ML row;
- an ML argument containing a TM row;
- TM-only consolidated output;
- ML-only consolidated output;
- valid output containing both sources;
- the command-line verifier rejecting one-source output.

### P2 — Explicit validation status is missing from the Marimo report

**Locations:**

- `forecast_history_pipeline.py:1078-1082`
- `forecast_history_etl.py:114-144`

The implementation displays measured validation evidence, but it explicitly states that no status is synthesized. The implementation plan requires a validation status for both source pipelines.

#### Suggested solution

Keep the detailed evidence tables, but add a small explicit status table derived from successful completion of the validation gates.

Example:

```python
validation_status = pl.DataFrame(
    {
        "source": ["tm", "ml"],
        "status": ["passed", "passed"],
    }
)
```

A better design is to construct each status from the validation result that was actually produced:

```python
validation_status = build_validation_status(
    tm_validation=build.tm_validation,
    ml_validation=build.ml_validation,
)
```

The status should not replace measured evidence. The report should show both:

| source | status |
| --- | --- |
| tm | passed |
| ml | passed |

Because the pipeline fails fast, a failed pipeline normally prevents the completed report from rendering. The displayed `passed` status therefore means that the corresponding validation result was successfully created, not merely that a label was hard-coded without validation.

Add a focused test for the status-building helper, avoiding tests coupled to Marimo UI rendering.

### P3 — TM oracle provenance is not independently verified

**Location:** `scripts/verify_forecast_history_output.py:68-91`

The manifest records a source commit and Git blob OID, but the verifier only confirms that these values look like 40-character hexadecimal hashes. It does not calculate the fixture's Git blob OID or compare the fixture with the recorded source identity.

A modified fixture can therefore be accepted if its adjacent manifest is updated with a matching SHA-256 checksum and arbitrary well-formed provenance values.

#### Suggested solution

Calculate the fixture's Git blob OID directly from its bytes:

```python
def _git_blob_oid(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content).hexdigest()
```

Then compare it with the manifest:

```python
actual_blob_oid = _git_blob_oid(fixture_bytes)
check(
    actual_blob_oid == source_blob,
    "TM oracle fixture does not match its recorded Git blob identity",
)
```

This confirms that the current fixture bytes match `source_git_blob_oid`. The currently recorded fixture produces:

```text
8f56f41cfc3a286676001f4d109c41f64fd465ca
```

For stronger provenance, also verify that the recorded commit contains that blob at the recorded source path when Git history is available. Keep the byte-derived blob check as the durable, Git-independent minimum.

Add tests proving that:

- the current fixture matches the recorded blob OID;
- changing fixture bytes without changing the blob OID fails;
- changing the blob OID to an arbitrary valid-looking hash fails;
- an incorrect SHA-256 checksum still fails.

## Checks that currently pass

- 24 automated tests
- Current-input regression verification
- Touched-file Ruff lint and formatting
- Marimo source validation
- LSP diagnostics
- Current output count: 16,035 rows
- Current source counts: 8,515 TM and 7,520 ML rows
- Six-column schema, deterministic ordering, and final-key uniqueness
- TM oracle fixture currently matches the recorded baseline Git blob

## Recommended completion order

1. Enforce source roles and require both sources in consolidated output.
2. Preserve output permissions during atomic replacement.
3. Add explicit TM and ML validation statuses to the report.
4. Verify the oracle fixture's calculated Git blob identity.
5. Add adversarial tests for every repaired invariant.
6. Regenerate the output and rerun all gates.

The implementation should be considered complete only after these four findings are resolved and their failure modes are covered by automated tests.
