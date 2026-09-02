# Gates: common-cohort vintage accuracy root

OWNS: forecast_analysis/vintage_accuracy.py, forecast_analysis/__init__.py, dashboard/adapter.py, dashboard/app.js, tests/test_common_vintage_accuracy.py, tests/test_static_dashboard_adapter.py, tests/test_forecast_analysis_dashboard_ui.py, scripts/verify_common_vintage_accuracy.py, scripts/validate_vintage_selector.mjs, validation-artifacts/vintage-selector/**

Scope: forecast accuracy comparisons use one common eligible parent-target cohort for every plotted vintage

- [x] G1: analytical branch is independently reverified
  EVIDENCE: Reverified all runnable gates in `leaf-1.1.1`, `leaf-1.1.2`, and `node-1.1` after the concurrent forecast-history artifact update. Canonical adversarial tests, feature-scoped adapter contracts, and the independent common-cohort oracle all pass.

- [x] G2: browser branch is independently reverified
  EVIDENCE: Reverified all runnable gates in `leaf-1.2.1`, `leaf-1.2.2`, and `node-1.2`. The 23-test UI source contract and fresh Chromium request/geometry oracle pass; the six regenerated responsive screenshots were manually reviewed.

- [x] G3: root integration is independently reverified with all required gates met
  EVIDENCE: `node-1` passes the 29-test feature-scoped suite and both independent oracles; syntax, diff, command-line Pyright, primary LSP, and session diagnostics have no new blocking findings. All 22 required gates across the depth-3 tree are met, with zero unmet and zero abandoned.
