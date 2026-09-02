# Plan: common-cohort vintage accuracy

## Depth tree (requested depth 3)

- Root `node-1`: every plotted vintage accuracy line is calculated from one deterministic common parent-target cohort.
  - Branch `node-1.1`: analytical pipeline correctness.
    - Leaf `leaf-1.1.1`: canonical multi-vintage cohort and FA/WAPE calculation.
    - Leaf `leaf-1.1.2`: adapter request normalization and auditable payload. Needs `leaf-1.1.1`.
  - Branch `node-1.2`: browser integration and proof.
    - Leaf `leaf-1.2.1`: selector submits selected vintages to the backend and renders returned cohort results. Needs `node-1.1`.
    - Leaf `leaf-1.2.2`: adversarial live-browser and screenshot validation. Needs `leaf-1.2.1`.

## Agreed seams

1. Canonical seam: `forecast_analysis.build_common_vintage_accuracy(...)` owns rule resolution, cohort intersection, WAPE, and FA.
2. Adapter seam: compact/bootstrap requests accept `accuracy_vintage_ids`; responses expose selected series plus common-cohort evidence.
3. Browser seam: checkbox changes submit a compact request; JavaScript never calculates eligibility, WAPE, or FA.

## Analytical contract

For each target month independently:

- Resolve one forecast per parent for fixed `latest_available` and every selected comparison rule.
- Retain only parent-target rows with positive actual and non-null forecasts for every plotted rule.
- Calculate each line as `100 * (1 - sum(abs(forecast - actual)) / sum(actual))` over that identical retained cohort.
- Expose identical `eligible_parents` and `actual_denominator_kl` on every series row for the same target month.
- Preserve deterministic rule order: historical options in canonical option order, then fixed latest.
- Default selection is `oldest_available`; an empty historical selection is valid and computes latest alone.
- Duplicate or unsupported IDs fail at the adapter boundary with a field-specific error.
- Chart selection does not alter global KPI, revision, quality, or forecast-volume populations.

## Ownership and readiness

| ID | State | Needs | OWNS |
| --- | --- | --- | --- |
| leaf-1.1.1 | READY | — | `forecast_analysis/vintage_accuracy.py`, `forecast_analysis/__init__.py`, `tests/test_common_vintage_accuracy.py` |
| leaf-1.1.2 | WAITING | leaf-1.1.1 | `dashboard/adapter.py`, `tests/test_static_dashboard_adapter.py`, `scripts/verify_common_vintage_accuracy.py` |
| node-1.1 | OPEN | both analytical leaves | integration only |
| leaf-1.2.1 | WAITING | node-1.1 | `dashboard/app.js`, `tests/test_forecast_analysis_dashboard_ui.py` |
| leaf-1.2.2 | WAITING | leaf-1.2.1 | `scripts/validate_vintage_selector.mjs`, `validation-artifacts/vintage-selector/**` |
| node-1.2 | OPEN | both browser leaves | integration only |
| node-1 | OPEN | node-1.1, node-1.2 | integration only |

## Toolchain

- Repository root working directory; `/bin/sh`.
- Python: `uv run python -m unittest`.
- Browser: Node.js + Chromium against a fresh `dashboard.server`.
- Existing unrelated dirty changes are preserved.
