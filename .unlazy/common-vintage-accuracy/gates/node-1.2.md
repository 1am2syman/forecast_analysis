# Gates: browser delivery integration

OWNS: dashboard/app.js, tests/test_forecast_analysis_dashboard_ui.py, scripts/validate_vintage_selector.mjs, validation-artifacts/vintage-selector/**

Scope: browser behavior consumes canonical common-cohort data correctly across interaction and responsive states

- [x] G1: UI source and fresh Chromium workflows pass together
  CHECK: uv run python -m unittest tests.test_forecast_analysis_dashboard_ui.DashboardUiSourceContractTests && node scripts/validate_vintage_selector.mjs --output validation-artifacts/vintage-selector
  EXPECT: VINTAGE SELECTOR VALIDATION PASSED
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/root/GitHub/forecast_analysis; path=cda89a5385a8/24 entries; output=Ran 23 tests in 0.010s | OK

- [x] G2: final screenshot artifacts and geometry report are reviewed after the final browser run
  EVIDENCE: Re-read validation-report.json and reviewed all six regenerated screenshots after node-1.2:G1. Report proves zero page overflow, one fixed latest line, selected counts 1→3→2→0, four common-cohort series across 16 target months, non-empty tooltip evidence (97 parents / 2,597.6 KL), and full-screen popover containment; visual review found no alignment, wrapping, clipping, hierarchy, or responsive regression.
