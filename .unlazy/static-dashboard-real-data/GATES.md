# Gates: static dashboard real-data integration

OWNS: dashboard/**, tests/test_static_dashboard_adapter.py, scripts/verify_static_dashboard_server.py, scripts/validate_real_dashboard_ui.mjs, validation-artifacts/static-dashboard-real-data/**, .unlazy/static-dashboard-real-data/**

Scope: serve the approved static shell from the canonical forecast-analysis dataset, make shared filters recompute every analytical view, and provide faithful real-data downloads.

- [x] G1: adapter contract returns real canonical metrics, trends, comparisons, product history, quality diagnostics, and filter options
  CHECK: uv run python -m unittest tests.test_static_dashboard_adapter && printf 'STATIC DASHBOARD ADAPTER TESTS PASSED\n'
  EXPECT: STATIC DASHBOARD ADAPTER TESTS PASSED
  EVIDENCE: 2026-08-27 — 6 tests passed against 16,035 canonical forecast rows and 1,679 actual-population rows.

- [x] G2: server health, dashboard JSON, filter recomputation, product history, and CSV downloads work over HTTP
  CHECK: uv run python scripts/verify_static_dashboard_server.py
  EXPECT: STATIC DASHBOARD SERVER VERIFICATION PASSED
  EVIDENCE: 2026-08-27 — health, static HTML, bootstrap, one-row exact filter scope, M−1 TM/ML comparison, product 999173, exact-scope CSV, and HTTP 400 validation all passed.

- [x] G3: browser validation passes navigation, real-data rendering, shared-filter recomputation, comparison mode, product drilldown, downloads, accessibility, and fixed-viewport checks
  CHECK: node scripts/validate_real_dashboard_ui.mjs --output validation-artifacts/static-dashboard-real-data
  EXPECT: REAL DASHBOARD UI VALIDATION PASSED
  EVIDENCE: 2026-08-27 — 15 screenshots passed across 1440×900, 1440×720, and 800×700; no document scroll, console errors, page exceptions, network failures, or HTTP errors; real CSV download completed. See validation-artifacts/static-dashboard-real-data/validation-report.md.

- [x] G4: edited Python and JavaScript files have no blocking language diagnostics
  CHECK: uv run python -m compileall -q dashboard tests/test_static_dashboard_adapter.py scripts/verify_static_dashboard_server.py && node --check dashboard/app.js && node --check scripts/validate_real_dashboard_ui.mjs && printf 'DIAGNOSTIC CHECKS PASSED\n'
  EXPECT: DIAGNOSTIC CHECKS PASSED
  EVIDENCE: 2026-08-27 — compileall and both Node syntax checks passed; a fresh bounded pi-lens scan reported no error issues across the seven implementation and verification files.

- [x] G5: live preview is published through the shared preview helper and responds successfully
  EVIDENCE: 2026-08-27 — live dashboard <https://sazzadvps.taildd3bd9.ts.net/forecast-dashboard-real-data/> and gallery <https://sazzadvps.taildd3bd9.ts.net/forecast-dashboard-real-data-validation/> both returned HTTP 200. Live browser QA found the expected canonical status and metrics with no console, page, or network failures. Shared Serve status retained the single root preview path and added only the requested localhost proxy route.
