# Plan: canonical forecast horizons

## Depth tree (requested depth 3)

- Root `node-1`: both ML and TM histories expose deterministic M1–M5 vintages and the forecast-accuracy chart treats Oldest/Latest as exact M5/M1.
  - Branch `node-1.1`: canonical data-pipeline provenance.
    - Leaf `leaf-1.1.1`: correct TM workbook provenance so the month before the first target is the calculation month.
    - Leaf `leaf-1.1.2`: enforce the shared M1–M5 waterfall invariant and regenerate the consolidated artifact. Needs `leaf-1.1.1`.
  - Branch `node-1.2`: deterministic analytical consumption and proof.
    - Leaf `leaf-1.2.1`: make forecast-accuracy Oldest/Latest exact M5/M1 with no nearest-available fallback. Needs `node-1.1`.
    - Leaf `leaf-1.2.2`: independently verify data, common-cohort calculations, dashboard request behavior, and responsive rendering. Needs `leaf-1.2.1`.

## Agreed contracts

1. The six-column waterfall CSV remains the durable boundary; `calculation_month` is authoritative provenance.
2. `forecast_horizon_months` remains derived as `target month - calculation month`; it is not duplicated in the CSV.
3. TM files named from the first through fifth target month use the preceding month as `calculation_month`.
4. ML and TM waterfall rows must derive only exact horizons M1 through M5.
5. Oldest means exact M5 and Latest means exact M1.
6. Missing M5 or M1 is unavailable/ineligible. No M4/M2 substitution is permitted.
7. Zero is a valid forecast value; only a missing parent-target-vintage row is unavailable.
8. Every plotted forecast-accuracy line for a target month uses the same eligible parent cohort.
9. Existing unrelated dirty work is preserved.

## Ownership and readiness

| ID | State | Needs | OWNS |
| --- | --- | --- | --- |
| leaf-1.1.1 | READY | — | `forecast_history_pipeline.py`, `tests/test_forecast_history_etl.py` |
| leaf-1.1.2 | WAITING | leaf-1.1.1 | `forecast_history_pipeline.py`, `tests/test_forecast_history_etl.py`, `scripts/verify_canonical_horizons.py`, `artifacts/forecast_history/consolidated/forecast_history_waterfall.csv`, `artifacts/forecast_history/consolidated/source_summary.csv`, `artifacts/forecast_history/consolidated/validation_status.csv`, `artifacts/forecast_history/consolidated/tm_validation.csv`, `artifacts/forecast_history/consolidated/ml_validation.csv` |
| node-1.1 | OPEN | both pipeline leaves | integration only |
| leaf-1.2.1 | WAITING | node-1.1 | `dashboard/adapter.py`, `forecast_analysis/vintage_accuracy.py`, `tests/test_common_vintage_accuracy.py`, `tests/test_static_dashboard_adapter.py` |
| leaf-1.2.2 | WAITING | leaf-1.2.1 | `scripts/verify_canonical_horizons.py`, `scripts/validate_vintage_selector.mjs`, `validation-artifacts/vintage-selector/**` |
| node-1.2 | OPEN | both analytical leaves | integration only |
| node-1 | OPEN | node-1.1, node-1.2 | integration only |

Work is sequential because the ETL and analytical contracts depend on the regenerated canonical artifact; no concurrent ownership claims are needed.

## Toolchain

- Repository root working directory; `/bin/sh`.
- Python: `uv run python` and `uv run python -m unittest`.
- Browser: existing Node/Chromium validator against a fresh `dashboard.server`.
- Diagnostics: primary LSP, `lens_diagnostics mode=all`, `git diff --check`.
