# Gates: vintage selector UI and visual behavior

OWNS: dashboard/app.js, dashboard/index.html, dashboard/styles.css, tests/test_forecast_analysis_dashboard_ui.py, scripts/validate_vintage_selector.mjs, validation-artifacts/vintage-selector/**

Scope: render an accessible multi-select before full screen and update only the forecast accuracy chart while keeping latest visible

- [x] G1: source contract tests cover selector placement, default state, fixed latest rendering, and multi-series semantics
  CHECK: uv run python -m unittest tests.test_forecast_analysis_dashboard_ui.DashboardUiSourceContractTests
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 22 tests in 0.011s | OK

- [x] G2: Chromium proves default oldest selection, multi-select/deselect behavior, fixed latest, full-screen parity, and responsive geometry
  CHECK: node scripts/validate_vintage_selector.mjs --output validation-artifacts/vintage-selector
  EXPECT: VINTAGE SELECTOR VALIDATION PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=VINTAGE SELECTOR VALIDATION PASSED

- [x] G3: exact-state desktop, wider, and compact screenshots show no overlap, clipping, or control loss
  EVIDENCE: Reviewed `validation-artifacts/vintage-selector/desktop-open.png`, `desktop-multi.png`, `wide.png`, `compact.png`, `fullscreen-latest-only.png`, and `fullscreen-selector-open.png`. Toolbar controls stay ordered and contained; popovers are anchored within the viewport; selected lines stay within chart bounds; multi-series labels are intentionally limited to avoid collisions; no page overflow or control loss is visible. Automated geometry is recorded in `validation-report.json`.
