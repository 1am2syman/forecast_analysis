# Gates: integrated forecast accuracy vintage selector

OWNS: dashboard/adapter.py, dashboard/app.js, dashboard/index.html, dashboard/styles.css, tests/test_static_dashboard_adapter.py, tests/test_forecast_analysis_dashboard_ui.py, scripts/validate_vintage_selector.mjs, validation-artifacts/vintage-selector/**

Scope: integrate data, UI, behavior, accessibility, and visual validation for selectable historical accuracy vintages

- [x] G1: backend and UI regression suites pass together
  CHECK: uv run python -m unittest tests.test_static_dashboard_adapter tests.test_forecast_analysis_dashboard_ui.DashboardUiSourceContractTests
  EXPECT: OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 43 tests in 9.388s | OK

- [x] G2: the integrated real-browser feature validation passes from a fresh server
  CHECK: node scripts/validate_vintage_selector.mjs --output validation-artifacts/vintage-selector
  EXPECT: VINTAGE SELECTOR VALIDATION PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=VINTAGE SELECTOR VALIDATION PASSED

- [x] G3: LSP and session diagnostics report no new blocking errors in edited source files
  EVIDENCE: LSP checked all seven edited source/test files with zero diagnostics in six confirmed files; one auxiliary HTML/CSS server remained timing-inconclusive. `node --check` passed for both JavaScript files, `git diff --check` passed, and `lens_diagnostics mode=all` found only three pre-existing `!important` style warnings at unchanged lines 94, 1382, and 1386.

- [x] G4: final screenshot review confirms desktop, wide, compact, and full-screen states preserve alignment, spacing, hierarchy, wrapping, and overflow
  EVIDENCE: Re-read all six current PNG artifacts after final rerender. Desktop open/multi, 1680×1050 wide, 800×700 compact, full-screen latest-only, and full-screen selector-open states preserve toolbar order, containment, chart bounds, and readable hierarchy. The browser oracle independently confirms zero page overflow, path containment, fixed latest uniqueness, and in-viewport popover geometry in `validation-artifacts/vintage-selector/validation-report.json`.
