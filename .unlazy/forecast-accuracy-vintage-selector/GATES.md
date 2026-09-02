# Gates: forecast accuracy vintage selector root

OWNS: dashboard/adapter.py, dashboard/app.js, dashboard/index.html, dashboard/styles.css, tests/test_static_dashboard_adapter.py, tests/test_forecast_analysis_dashboard_ui.py, scripts/validate_vintage_selector.mjs, validation-artifacts/vintage-selector/**

Scope: planners can compare one or more historical forecast vintages against an always-visible latest accuracy series

- [x] G1: leaf-1.1 data-contract ledger is independently reverified
  EVIDENCE: Parent reverification ran both adapter oracles from the repository root; 2/2 gates met with no abandonment.

- [x] G2: leaf-1.2 UI and visual ledger is independently reverified
  EVIDENCE: Parent reverification reran source and Chromium oracles; manual screenshot evidence was reviewed after the final rerender; 3/3 gates met with no abandonment.

- [x] G3: node-1 integration ledger is independently reverified with no abandoned gates
  EVIDENCE: Bottom-up integration reverified 43 backend/UI tests and the fresh-server Chromium workflow, then reviewed diagnostics and final screenshots; 4/4 gates met with no abandonment.
